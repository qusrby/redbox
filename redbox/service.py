"""상시 실행 본체: 2초마다 게임을 감지하고 녹화를 맞춘다(화면 없이도 돈다. 화면은 나중에 이 위에 얹는다)."""
import ctypes
import datetime
import os
import threading
import time
import zlib

from . import APP_ID, APP_NAME, VERSION, paths
from .detect import Detector, win32
from .detect.catalog import source_name
from .recorder import Recorder
from .uploader import Store, Uploader

POLL_SECONDS = 2


class Log:
    def __init__(self, name="redbox.log"):
        self.path = os.path.join(paths.log_dir(), name)

    def __call__(self, msg):
        line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


def single_instance():
    """이미 실행 중이면 None. 이름 있는 뮤텍스는 프로세스가 끝나면 윈도우가 알아서 푼다."""
    k32 = ctypes.windll.kernel32
    home = os.environ.get("REDBOX_HOME")          # 개발용 데이터 폴더로 띄운 것은 따로 센다
    name = f"Local\\{APP_ID}" + (f"-{zlib.crc32(os.path.normcase(home).encode()):08x}" if home else "")
    h = k32.CreateMutexW(None, False, name)
    if k32.GetLastError() == 183:    # ERROR_ALREADY_EXISTS
        if h:
            k32.CloseHandle(h)
        return None
    return h


class Service:
    def __init__(self, cfg):
        self.cfg = cfg
        self.log = Log()
        self.detector = Detector(cfg)
        self.store = Store()
        self.recorder = Recorder(cfg, self.log, on_finished=self.on_recording_finished)
        self.uploader = Uploader(cfg, self.store, Log("upload.log"))
        self.stop_flag = os.path.join(paths.data_dir(), "stop")
        self.stop_event = threading.Event()
        self.paused = False          # 화면의 '녹화 잠시 멈춤'
        self.recent_decisions = {}
        self.last_tick = 0.0          # 감지가 마지막으로 돈 시각(화면의 '정상' 판단)
        self.last_error = None        # (시각, 문구)
        self.obs_pid = None           # OBS Studio 프로세스(없으면 None)
        self.obs_since = None         # OBS Studio 를 켠 시각
        self._carry_over_custom_games()

    def _carry_over_custom_games(self):
        """스팀 전용으로 바뀌기 전에 녹화하던 스팀 밖 게임(예: 라이엇 게임)은 처음 한 번 '직접 추가한 게임'으로 옮긴다.
        녹화 기록이 있고 지금 설치돼 있는 게임만. 그래야 업데이트 뒤에도 녹화가 끊기지 않는다."""
        det = self.cfg["detection"]
        if det.get("custom_carried_over"):
            return
        from . import config
        from .artwork import norm
        recorded = {norm(r.get("game")) for r in self.store.data["recordings"].values() if r.get("game")}
        have = {str(g.get("path", "")).lower() for g in det.setdefault("custom_games", [])}
        for _d, e in self.detector.catalog.dirs:
            if e.source != "steam" and e.name and norm(e.name) in recorded and e.dir.lower() not in have:
                det["custom_games"].append({"name": e.name, "path": e.dir})
                have.add(e.dir.lower())
                self.log(f"직접 추가한 게임으로 옮김: {e.name} ({e.dir})")
        det["custom_carried_over"] = True
        config.save(self.cfg)

    def on_recording_finished(self, path, game, duration):
        """녹화가 끝나 이름까지 정리된 파일을 업로드 대기열에 넣는다."""
        if self.store.add_recording(path, game, duration):
            self.uploader.nudge()

    def _check_obs(self):
        obs = next((pid for pid, name in self.detector.last_procs
                    if name.lower() in ("obs64.exe", "obs32.exe", "obs.exe")), None)
        if obs != self.obs_pid:
            self.obs_pid = obs
            self.obs_since = None
            if obs:
                try:
                    import psutil
                    self.obs_since = psutil.Process(obs).create_time()
                except Exception:
                    self.obs_since = None

    def tick(self):
        decisions = self.detector.evaluate()
        self._check_obs()
        self.last_tick = time.time()
        self.recent_decisions = decisions
        if self.paused:
            decisions = {}           # 진행 중이던 녹화는 정상적으로 끝내고 새 녹화는 시작하지 않는다
        self.recorder.update(decisions)

    def run(self):
        win32.set_dpi_aware()
        c = self.detector.catalog
        self.log("=" * 60)
        self.log(f"{APP_NAME} {VERSION} 시작. 영상 폴더: {self.recorder.video_root()}")
        self.log("모은 게임 목록: " + ", ".join(f"{source_name(k)} {v}" for k, v in c.counts.items()))
        if os.path.exists(self.stop_flag):
            os.remove(self.stop_flag)
        self.uploader.start()
        try:
            while not os.path.exists(self.stop_flag) and not self.stop_event.is_set():
                try:
                    self.tick()
                except Exception as e:
                    self.last_error = (time.time(), f"{type(e).__name__}: {e}")
                    self.log(f"[루프 오류] {type(e).__name__}: {e}")
                self.stop_event.wait(POLL_SECONDS)
            if os.path.exists(self.stop_flag):
                os.remove(self.stop_flag)
            self.log("종료 요청을 받아 끝냄")
        except KeyboardInterrupt:
            self.log("사용자가 끝냄")
        finally:
            self.recorder.shutdown()
            self.uploader.stop()
            self.uploader.join(timeout=5)
