"""녹화 세션 관리: 감지 결과를 받아 OBS 녹화를 켜고 끄고, 끝난 파일을 정리한다.

- 한 번에 게임 하나만 녹화한다. 후보가 여럿이면 창이 있는 쪽을 먼저.
- 창을 못 찾은 채 시작했으면 계속 다시 찾아 캡처 대상을 고친다. 끝까지 못 찾으면 중단하고 영상을 지운다.
- 창을 찾은 뒤에도 주기적으로 다시 확인한다(로딩 창에서 본 창으로 바뀌는 게임).
- 이 앱이 시작하지 않은 녹화(사용자가 직접 켠 녹화)는 건드리지 않는다.
"""
import os
import time

from .. import thumbs
from ..detect import win32
from . import files, naming
from .obs import Obs, window_value

WINDOW_RECHECK_SECONDS = 15
WINDOW_FIND_TIMEOUT = 300       # 이 안에 창을 못 찾으면 게임이 아닌 것으로 보고 중단
OBS_RETRY_SECONDS = 5
FAIL_COOLDOWN = 10
ABORT_COOLDOWN = 300


def find_window(pid, exe):
    """pid 의 가장 큰 보이는 창으로 OBS 창 지정 문자열을 만든다. 없으면 None."""
    wins = win32.visible_windows().get(pid, [])
    best = None
    for hwnd, w, h in wins:
        title = win32.window_title(hwnd)
        if not title:
            continue
        if best is None or w * h > best[0]:
            best = (w * h, hwnd, title)
    if not best:
        return None
    return window_value(best[2], win32.window_class(best[1]), exe)


class Session:
    __slots__ = ("pid", "exe", "path", "reason", "game", "folder", "start", "target", "confirmed", "deadline", "next_check")


class Recorder:
    def __init__(self, cfg, log, on_finished=None):
        self.cfg = cfg
        self.log = log
        self.on_finished = on_finished   # (경로, 게임, 길이) 녹화가 끝나 파일이 정리되면 부른다
        self.obs = Obs(cfg["obs"])
        self.shooter = thumbs.Shooter(log)      # 녹화 중 장면을 찍어 두었다가 녹화본 썸네일로
        self.connected = False
        self.down_since = None
        self.next_try = 0
        self.session = None
        self.retry_after = {}         # 실행 파일 경로 -> 다시 시도해도 되는 시각
        self.external = False         # 사용자가 직접 켠 녹화가 진행 중
        self.next_sweep = 0
        self.healed_obs = set()       # 비정상 종료 확인 창에서 멈춰 다시 켜 준 OBS pid(한 번만)
        self.subtitle = []            # 녹화에 얹은 그림과 자막(설정에 파일이 있을 때)

    # -- OBS 연결 ------------------------------------------------------------------------------
    def ensure_connected(self):
        if self.connected:
            return True
        if time.time() < self.next_try:
            return False
        self.next_try = time.time() + OBS_RETRY_SECONDS
        try:
            self.obs.connect()
        except Exception as e:
            if self.down_since is None:
                self.down_since = time.time()
                self.log(f"OBS 연결 실패({e}) -> OBS 가 켜질 때까지 {OBS_RETRY_SECONDS}초마다 조용히 다시 시도")
            self._heal_crash_prompt()
            return False
        self.connected = True
        if self.obs.seeded:            # 오디오 설정을 OBS 의 지금 상태로 처음 정했으면 저장
            self.obs.seeded = False
            from .. import config
            config.save(self.cfg)
            self.log(f"오디오 설정: 마이크 {'켬' if self.cfg['obs']['mic'] else '끔'}, "
                     f"녹음 대상 {'PC 전체 소리' if self.cfg['obs']['audio'] == 'all' else '게임 소리만'}")
        if self.down_since is not None:
            self.log(f"OBS 다시 연결됨 (끊겨 있던 시간 {files.format_duration(time.time() - self.down_since)})")
            self.down_since = None
        else:
            self.log(f"OBS 연결 성공 (캡처 소스: {self.obs.capture})")
        self._adopt_orphan()
        return True

    def _heal_crash_prompt(self):
        """PC 가 갑자기 꺼진 뒤 OBS 가 '비정상 종료가 감지됨' 창에서 멈춰 연결되지 않으면 알아서 푼다.
        OBS 가 꺼져 있으면 남은 표시만 지워 두고(나중에 켜질 때 창이 뜨지 않게),
        켜진 지 30초가 넘었는데 연결이 안 되고 지난번 표시가 남아 있으면 OBS 를 끄고 표시를 지운 뒤 다시 켠다."""
        from .obs import clear_crash_marks, crash_marks, launch_obs, find_obs, obs_process
        try:
            proc = obs_process()
            if proc is None:
                if crash_marks() and clear_crash_marks():
                    self.log("OBS 비정상 종료 표시 정리(다음에 켤 때 확인 창이 뜨지 않게)")
                return
            pid, started, exe = proc
            if pid in self.healed_obs or time.time() - started < 30 or len(crash_marks()) < 2:
                return
            self.healed_obs.add(pid)
            self.log("[복구] OBS 가 비정상 종료 확인 창에서 멈춰 연결되지 않음 -> OBS 를 다시 켬")
            import psutil
            p = psutil.Process(pid)
            p.kill()
            try:
                p.wait(10)
            except psutil.Error:
                pass
            clear_crash_marks()
            exe = exe or find_obs()
            if exe:
                launch_obs(exe)
        except Exception as e:
            self.log(f"  [복구] OBS 다시 켜기 실패: {e}")

    def _heal_crash(self):
        """OBS 가 녹화 도중 충돌해 'OBS has crashed!' 창에 멈춰 있으면 끄고 다시 켠다.
        충돌한 OBS 는 웹소켓에 한동안 '녹화 중'으로 답해 직접 켠 녹화로 잘못 보이므로 창으로 알아본다.
        그래픽 드라이버에 걸려 끝나지 않는 OBS 가 남으면 새 OBS 는 '이미 실행 중' 확인 없이 켠다."""
        from .obs import clear_crash_marks, crash_window, find_obs, launch_obs, obs_processes
        try:
            hit = crash_window()
            if not hit or hit[0] in self.healed_obs:
                return
            pid = hit[0]
            self.healed_obs.add(pid)
            lost = self.session
            self.log("[복구] OBS 가 충돌함 -> OBS 를 다시 켬" + (f" (녹화 중이던 {lost.game} 영상은 저장되지 않았을 수 있음)" if lost else ""))
            if lost:
                self.session = None
                self.shooter.cancel()
                self._stop_subtitle()
                self.retry_after.pop(lost.path.lower(), None)
            self.obs.disconnect()
            self.connected, self.external = False, False
            if self.down_since is None:
                self.down_since = time.time()
            import psutil
            exe = None
            for p in [psutil.Process(x) for x in obs_processes()]:
                try:
                    exe = exe or p.exe()
                    p.kill()
                except psutil.Error:
                    pass
            deadline = time.time() + 8
            while obs_processes() and time.time() < deadline:
                time.sleep(0.5)
            stuck = bool(obs_processes())
            clear_crash_marks()
            exe = exe or find_obs()
            if exe:
                launch_obs(exe, multi=stuck)
                if stuck:
                    self.log("  [복구] 앞 OBS 가 끝나지 않아(그래픽 드라이버 대기) 새 OBS 를 따로 켬")
            self.next_try = time.time() + 10      # OBS 가 웹소켓을 열 시간
        except Exception as e:
            self.log(f"  [복구] 충돌한 OBS 다시 켜기 실패: {e}")

    def _drop(self, e):
        self.log(f"[연결 끊김] OBS ({e}) -> 다시 연결 시도")
        self.obs.disconnect()
        self.connected = False

    def _adopt_orphan(self):
        """앱이 비정상 종료돼 우리 녹화가 그대로 돌고 있으면(녹화 폴더가 우리 폴더 아래) 멈추고 정리한다."""
        if self.session or not self.obs.recording():
            return
        root = os.path.normcase(os.path.abspath(self.video_root()))
        cur = os.path.normcase(os.path.abspath(self.obs.record_dir() or ""))
        if cur.startswith(root + os.sep) or cur == root:
            path = self.obs.stop()
            self.log(f"[정리] 이전 실행에서 남은 녹화를 멈춤: {os.path.basename(path or '')}")

    # -- 설정 ----------------------------------------------------------------------------------
    def video_root(self):
        return self.cfg["recording"]["video_root"]

    # -- 메인 ----------------------------------------------------------------------------------
    def update(self, decisions):
        """감지 결과({pid: Decision})를 받아 녹화를 맞춘다. 2초마다 부른다."""
        self._heal_crash()
        if not self.ensure_connected():
            return
        try:
            self._update(decisions)
        except Exception as e:      # 웹소켓 쪽 예외는 종류가 많아 전부 연결 끊김으로 본다
            self._drop(e)

    def _update(self, decisions):
        now = time.time()
        active = self.obs.recording()
        if self.session and not active and now - self.session.start > 5:   # 시작 직후엔 OBS 상태가 늦게 바뀐다
            self.log(f"[경고] OBS 녹화가 꺼져 있음(직접 멈춘 것으로 봄) -> 세션 정리: {self.session.exe}")
            self.session = None
        if not self.session:
            if active:
                if not self.external:
                    self.log("직접 켠 녹화가 진행 중 -> 끝날 때까지 자동 녹화를 쉰다")
                self.external = True
                return
            if self.external:
                self.log("직접 켠 녹화가 끝남 -> 자동 녹화 다시 시작")
            self.external = False

        if self.session:
            d = decisions.get(self.session.pid)
            if not d or not d.record:
                self.stop()
            else:
                self._heal_window(now)
                if self.session and self.session.confirmed:
                    self.shooter.tick(self.obs, now)
        if not self.session:
            cand = self._pick(decisions, now)
            if cand:
                self.start(cand)
        self._sweep(now)

    def _pick(self, decisions, now):
        cands = [d for d in decisions.values() if d.record and now >= self.retry_after.get(d.path.lower(), 0)]
        if not cands:
            return None
        wins = win32.visible_windows()
        with_window = [d for d in cands if wins.get(d.pid)]
        return (with_window or cands)[0]

    # -- 시작과 정지 -----------------------------------------------------------------------------
    def start(self, d):
        rec = self.cfg["recording"]
        game = naming.folder_name(d.name, self.cfg["extras"].get("match_folder_names", ""))
        folder = os.path.join(self.video_root(), game) if rec.get("per_game_folder", True) else self.video_root()
        try:
            os.makedirs(folder, exist_ok=True)
            target = find_window(d.pid, d.exe)
            self.obs.set_target(target or window_value("", "", d.exe))
            time.sleep(1.0)        # 캡처가 창에 붙을 시간
            self._start_subtitle()
            self.obs.start(folder)
        except Exception as e:
            self.log(f"[오류] 녹화 시작 실패({d.exe}): {e}")
            self._stop_subtitle()
            self.retry_after[d.path.lower()] = time.time() + FAIL_COOLDOWN
            try:
                if self.obs.recording():
                    self.obs.stop()
            except Exception:
                pass
            return
        s = Session()
        s.pid, s.exe, s.path, s.game, s.folder, s.start = d.pid, d.exe, d.path, game, folder, time.time()
        s.reason = d.reason
        s.target, s.confirmed = target, bool(target)
        s.deadline = s.start + WINDOW_FIND_TIMEOUT
        s.next_check = s.start + WINDOW_RECHECK_SECONDS
        self.session = s
        self.shooter.begin(s.start)
        self.log(f"캡처 대상 지정: {target or '(창 찾는 중)'}")
        self.log(f"녹화 시작: {d.exe.lower()} -> {folder}")
        self.log(f"  감지 근거: {d.reason}, 게임: {d.name}")
        if not s.confirmed:
            self.log("  [주의] 창을 아직 못 찾음 -> 계속 다시 찾아 고칠 예정")

    def stop(self):
        s, self.session = self.session, None
        if not s:
            return None
        duration = time.time() - s.start
        try:
            path = self.obs.stop()
        except Exception as e:
            self.log(f"[오류] 녹화 정지 실패: {e}")
            self._stop_subtitle()
            raise
        self._stop_subtitle()
        self.log(f"녹화 정지: {s.exe.lower()}")
        new = None
        if path and os.path.exists(path):
            name = files.recording_name(self.cfg["recording"].get("file_name"), s.game, s.start, duration,
                                        os.path.splitext(path)[1])
            time.sleep(0.5)
            new = files.rename_with_retry(path, os.path.join(os.path.dirname(path), name))
            if new:
                self.log(f"  파일명 변경: {os.path.basename(new)}")
            else:
                self.log(f"  [오류] 파일명 변경 실패: {os.path.basename(path)}")
                new = path
            limit = self.cfg["recording"].get("discard_no_window_seconds", 30)
            if not s.confirmed and duration < limit:
                if files.remove_with_retry(new):
                    self.log(f"  [폐기] 창 없이 {duration:.0f}초 만에 끝난 실행이라 영상 삭제: {os.path.basename(new)}")
                new = None
        self.shooter.finish(new, duration)
        self._reset_dir()
        self._sweep(time.time(), force=True)
        if new and self.on_finished:
            self.on_finished(new, s.game, duration)
        return new

    def _start_subtitle(self):
        """설정에 그림 파일, 자막 파일이 있으면 녹화될 장면에 얹는다(그림 위에 자막). 실패해도 녹화는 그대로 한다."""
        rec = self.cfg["recording"]
        image = (rec.get("overlay_image") or "").strip()
        text = (rec.get("subtitle_file") or "").strip()
        if not image and not text:
            return
        from .obs import open_client
        from .subtitle import ImageOverlay, Overlay
        try:
            scene = self.obs.record_scene()
        except Exception as e:
            self.log(f"  [자막] 장면을 못 읽음: {e}")
            return
        connect = lambda: open_client(self.cfg["obs"])     # noqa: E731
        if image:
            ov = ImageOverlay(image, connect, self.log)
            if ov.start(scene, self.obs.capture):
                self.subtitle.append(ov)
        if text:
            ov = Overlay(text, connect, self.log)
            if ov.start(scene):
                self.subtitle.append(ov)

    def _stop_subtitle(self):
        ovs, self.subtitle = self.subtitle, []
        for ov in ovs:
            ov.stop()

    def _reset_dir(self):
        """세션이 끝나면 녹화 폴더를 되돌린다(게임 밖에서 찍은 스크린샷이 방금 게임 폴더로 가지 않게).
        스크린샷 폴더를 정해 두었으면 그곳으로, 아니면 영상 폴더 최상위로."""
        target = self.cfg["extras"].get("screenshot_folder") or self.video_root()
        try:
            os.makedirs(target, exist_ok=True)
            self.obs.set_record_dir(target)
        except Exception as e:
            self.log(f"[오류] 녹화 폴더 되돌리기 실패: {e}")

    def abort(self):
        """창을 끝내 못 찾은 녹화를 멈추고 검은 화면뿐인 파일을 지운다."""
        s, self.session = self.session, None
        self.shooter.cancel()
        path = self.obs.stop()
        self._stop_subtitle()
        if path and files.remove_with_retry(path):
            self.log(f"  검은 화면 녹화 파일 삭제: {os.path.basename(path)}")
        self.retry_after[s.path.lower()] = time.time() + ABORT_COOLDOWN
        self._reset_dir()

    def shutdown(self):
        """앱을 끌 때: 녹화 중이면 정상적으로 멈추고 정리한다."""
        if self.session and self.connected:
            try:
                self.stop()
            except Exception:
                pass
        self.obs.disconnect()

    # -- 창 다시 찾기 ----------------------------------------------------------------------------
    def _heal_window(self, now):
        s = self.session
        if not s.confirmed:
            if now > s.deadline:
                self.log(f"  [중단] {s.exe}: {WINDOW_FIND_TIMEOUT // 60}분 넘게 창을 못 찾음 -> 게임이 아닌 것으로 보고 녹화 중단")
                self.abort()
                return
            target = find_window(s.pid, s.exe)
            if target:
                self._apply(target)
            return
        if now < s.next_check:
            return
        s.next_check = now + WINDOW_RECHECK_SECONDS
        target = find_window(s.pid, s.exe)
        if target and target != s.target:
            self.log(f"  창 변경 감지 -> 캡처 대상 갱신: {s.target} -> {target}")
            self._apply(target)

    def _apply(self, target):
        self.obs.set_target(target)
        self.session.target, self.session.confirmed = target, True
        self.log(f"  캡쳐 대상 갱신: {target}")

    # -- 스크린샷 ------------------------------------------------------------------------------
    def _sweep(self, now, force=False):
        dest = self.cfg["extras"].get("screenshot_folder")
        if not dest or (not force and now < self.next_sweep):
            return
        self.next_sweep = now + 10
        try:
            for orig, dst in files.sweep_screenshots(self.video_root(), dest):
                self.log(f"스크린샷 이동: {orig} -> {os.path.relpath(dst, dest)}")
        except Exception as e:
            self.log(f"[오류] 스크린샷 정리 실패(다음에 다시): {e}")
