"""업로드 스레드: 대기열의 녹화를 유튜브에 비공개로 올리고, 처리가 끝나면 보관 기간 뒤 PC 에서 지운다.

한 바퀴(cycle)에 하는 일:
  1. 영상 폴더에서 등록 안 된 파일 찾기(앱이 꺼져 있던 동안 생긴 것)
  2. 길이 규칙: 너무 짧으면 삭제, 기준보다 짧으면 제외(파일은 남김)
  3. 올린 영상의 유튜브 처리 확인, 보관 기간이 지나면 PC 에서 삭제, 처리가 멈춘 영상은 지우고 다시 올리기
  4. 대기열에서 하나 올리기(올릴 게 더 있으면 바로 다음 바퀴)
"""
import datetime
import os
import threading
import time

from . import media, youtube
from .store import file_key, now_iso

VIDEO_EXTS = (".mp4", ".mkv")
SETTLE_SECONDS = 120          # 수정된 지 이만큼 지난 파일만 폴더 훑기로 등록
TITLES_CACHE_SECONDS = 600


def _parse_time(s):
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _hours_since(s):
    dt = _parse_time(s)
    if dt is None:
        return None
    now = datetime.datetime.now(dt.tzinfo) if dt.tzinfo else datetime.datetime.now()
    return (now - dt).total_seconds() / 3600


def _http_status(e):
    return getattr(getattr(e, "resp", None), "status", None)


class Uploader(threading.Thread):
    def __init__(self, cfg, store, log, yt=youtube, data_dir=None):
        super().__init__(daemon=True, name="uploader")
        self.cfg = cfg
        self.store = store
        self.log = log
        self.yt = yt
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.svc = None
        self.sig = None
        self.auth_problem = None       # 로그인이 필요하면 그 이유(화면에 보여 줄 것)
        self.progress = None           # (파일 이름, 0~1) 업로드 중일 때
        self._titles = (0, None)
        self._recovered = False
        self._once = {}
        self._rules_lock = threading.Lock()     # 길이 규칙은 업로드 스레드와 녹화 쪽(apply_rules_now)에서 같이 부른다

    # -- 설정 도우미 -----------------------------------------------------------------------------
    @property
    def up(self):
        return self.cfg["upload"]

    def rules_for(self, game):
        """(최소 길이 초, 자동 삭제 길이 초, 보관 시간) 게임별 예외가 있으면 그 값."""
        over = next((v for k, v in (self.up.get("game_overrides") or {}).items()
                     if k.lower() == (game or "").lower()), {})
        mn = float(over.get("min_minutes", self.up.get("min_minutes", 0)) or 0)
        dl = float(over.get("auto_delete_minutes", self.up.get("auto_delete_minutes", 0)) or 0)
        keep = float(over.get("keep_days", self.up.get("keep_days", 7)) or 0)
        return mn * 60, dl * 60, keep * 24

    def log_once(self, kind, msg):
        if self._once.get(kind) != msg:
            self._once[kind] = msg
            self.log(msg)

    # -- 스레드 ---------------------------------------------------------------------------------
    def stop(self):
        self.stop_event.set()
        self.wake.set()

    def nudge(self):
        """녹화가 하나 끝났을 때 기다리지 말고 바로 한 바퀴 돌게 한다."""
        self.wake.set()

    def apply_rules_now(self):
        """녹화가 끝나자마자 길이 규칙(자동 삭제, 업로드 제외)을 맞춘다.
        업로드 스레드는 큰 영상을 올리는 동안 다음 바퀴로 못 가므로, 그동안 짧은 영상이 '업로드 대기'로 남지 않게."""
        try:
            self.apply_length_rules(bool(self.up.get("enabled")))
        except Exception as e:
            self.log(f"[길이 규칙 오류] {type(e).__name__}: {e}")

    def run(self):
        while not self.stop_event.is_set():
            more = False
            try:
                more = self.cycle()
            except Exception as e:
                self.log(f"[업로드 오류] {type(e).__name__}: {e}")
                self.svc = None
            if not more:
                self.wake.wait(self.up.get("poll_seconds", 30))
                self.wake.clear()

    # -- 한 바퀴 --------------------------------------------------------------------------------
    def cycle(self):
        upload_on = bool(self.up.get("enabled"))
        if upload_on:
            self.scan_folder()
        self.apply_length_rules(upload_on)    # 자동 삭제는 업로드를 꺼도 동작한다(녹화 규칙)
        if not upload_on:
            return False
        svc = self.service()
        if svc is None:
            return False
        if not self._recovered:
            self.recover_interrupted(svc)
            self._recovered = True
        self.cleanup(svc)
        return self.upload_next(svc)

    def service(self):
        sig = self.yt.signature()
        if self.svc is not None and sig == self.sig:
            return self.svc
        try:
            self.svc = self.yt.service(interactive=False)
            self.sig = sig
            if self.auth_problem:
                self.log("유튜브 로그인 확인됨 -> 업로드 다시 시작")
            self.auth_problem = None
        except self.yt.AuthNeeded as e:
            self.svc = None
            self.auth_problem = str(e)
            self.log_once("auth", f"[로그인 필요] {e} 업로드는 로그인할 때까지 쉰다")
        return self.svc

    # -- 1. 폴더 훑기 ----------------------------------------------------------------------------
    def scan_folder(self):
        root = self.cfg["recording"]["video_root"]
        if not os.path.isdir(root):
            return
        known = self.store.data["recordings"]
        now = time.time()
        for dp, _dn, names in os.walk(root):
            for n in names:
                if not n.lower().endswith(VIDEO_EXTS):
                    continue
                p = os.path.join(dp, n)
                if file_key(p) in known:
                    continue
                try:
                    if now - os.path.getmtime(p) < SETTLE_SECONDS or media.in_use(p):
                        continue
                except OSError:
                    continue
                game = os.path.basename(dp) if os.path.normcase(dp) != os.path.normcase(root) else ""
                dur = media.duration_seconds(p) or 0
                if self.store.add_recording(p, game, dur):
                    self.log(f"새 파일 등록(폴더 훑기): {n} ({dur / 60:.1f}분)")

    # -- 2. 길이 규칙 ----------------------------------------------------------------------------
    def apply_length_rules(self, upload_on=True):
        with self._rules_lock:
            self._apply_length_rules(upload_on)

    def _apply_length_rules(self, upload_on):
        for key, rec in self.store.waiting():
            path = rec.get("path") or key
            if not os.path.exists(path):
                self.store.update(key, status="missing")
                continue
            if rec.get("checked"):
                continue
            mn, dl, _keep = self.rules_for(rec.get("game"))
            dur = rec.get("duration") or 0
            if dl > 0 and dur <= dl:
                try:
                    media.force_remove(path)
                except OSError as e:
                    self.log(f"  [오류] 짧은 영상 삭제 실패: {e}")
                    continue
                self.store.update(key, status="auto_deleted", reason="too_short_deleted", rule_at=[mn, dl])
                self.log(f"  [삭제] {dur / 60:.1f}분 (기준 {dl / 60:g}분 이하) -> 너무 짧아서 자동 삭제: {rec['name']}")
            elif not upload_on:
                continue           # 업로드 판단은 업로드를 켤 때 한다
            elif mn > 0 and dur < mn:
                self.store.update(key, status="excluded", reason="too_short", rule_at=[mn, dl])
                self.log(f"  [제외] {dur / 60:.1f}분 (기준 {mn / 60:g}분 미만) -> 업로드 안 함: {rec['name']}")
            else:
                self.store.update(key, checked=True, rule_at=[mn, dl])

    # -- 2-1. 바뀐 길이 규칙 ------------------------------------------------------------------------
    # 길이 규칙은 녹화가 끝날 때 한 번 판정한다. 나중에 설정을 바꿔도 이미 판정한 영상은 저절로 바꾸지 않고,
    # 화면에서 영상마다 경고를 띄우고, 확인 창에서 적용해야 바뀐다(취소하면 경고는 남는다).
    def rule_change(self, rec):
        """지금 규칙으로는 판정이 달라지는 기록이면 'upload', 'exclude', 'delete'. 아니면 None."""
        st = rec.get("status")
        if st == "excluded":
            if rec.get("reason") != "too_short":
                return None
            old = "exclude"
        elif st == "waiting" and rec.get("checked"):
            old = "upload"
        else:
            return None
        path = rec.get("path") or ""
        info = self.store.data.get("in_progress") or {}
        if info.get("key") == file_key(path) or not os.path.exists(path):
            return None
        mn, dl, _keep = self.rules_for(rec.get("game"))
        dur = rec.get("duration") or 0
        if dl > 0 and dur <= dl:
            new = "delete"
        elif not self.up.get("enabled"):
            return None                    # 업로드를 꺼 두었으면 올릴지 말지는 판정하지 않는다
        elif mn > 0 and dur < mn:
            new = "exclude"
        else:
            new = "upload"
        return new if new != old else None

    def apply_rule_change(self, key):
        """바뀐 규칙을 이 기록에 적용한다. 적용한 결과('upload', 'exclude', 'delete')나 None."""
        with self._rules_lock:
            rec = self.store.data["recordings"].get(key)
            act = self.rule_change(rec) if rec else None
            if act is None:
                return None
            name, dur = rec.get("name", ""), (rec.get("duration") or 0) / 60
            mn, dl, _keep = self.rules_for(rec.get("game"))
            if act == "delete":
                try:
                    media.force_remove(rec.get("path") or key)
                except OSError as e:
                    self.log(f"  [오류] 바뀐 규칙으로 삭제 실패: {e}")
                    return None
                self.store.update(key, status="auto_deleted", reason="too_short_deleted", rule_at=[mn, dl])
                self.log(f"  [바뀐 규칙 적용] {dur:.1f}분 -> 원본 삭제: {name}")
            elif act == "exclude":
                self.store.update(key, status="excluded", reason="too_short", rule_at=[mn, dl])
                self.log(f"  [바뀐 규칙 적용] {dur:.1f}분 -> 업로드 안 함: {name}")
            else:
                self.store.update(key, status="waiting", reason=None, checked=True, rule_at=[mn, dl])
                self.log(f"  [바뀐 규칙 적용] {dur:.1f}분 -> 업로드 대기: {name}")
        self.nudge()
        return act

    def delete_original(self, key):
        """검토 창에서 사용자가 고른 원본 삭제. 올리지 않고 지운 것으로 남긴다(업로드 대기에서 빠진다)."""
        with self._rules_lock:
            rec = self.store.data["recordings"].get(key)
            info = self.store.data.get("in_progress") or {}
            if not rec or info.get("key") == key:
                return False
            try:
                media.force_remove(rec.get("path") or key)
            except FileNotFoundError:
                pass
            except OSError as e:
                self.log(f"  [오류] 원본 삭제 실패: {e}")
                return False
            self.store.update(key, status="auto_deleted", reason="user_deleted")
            self.log(f"  [삭제] 검토 창에서 원본 삭제: {rec.get('name', '')}")
        return True

    def rules_signature(self):
        """화면이 다시 그릴지 정할 때 쓰는 길이 규칙 값."""
        up = self.up
        return (bool(up.get("enabled")), up.get("min_minutes"), up.get("auto_delete_minutes"),
                repr(sorted((k.lower(), sorted(v.items())) for k, v in (up.get("game_overrides") or {}).items())))

    # -- 3. 처리 확인과 정리 ---------------------------------------------------------------------
    def cleanup(self, svc):
        pending = [(k, r) for k, r in self.store.uploaded_not_cleaned() if os.path.exists(r.get("path") or k)]
        if not pending:
            return
        ask = [r["video_id"] for _k, r in pending if not r.get("processing_ok")]
        if ask:
            try:
                ok = self.yt.processed_ok(svc, ask)
            except Exception as e:
                self.log(f"  [오류] 처리 상태 확인 실패: {e}")
                ok = set()
            for k, r in pending:
                if r["video_id"] in ok:
                    self.store.update(k, processing_ok=True)
                    r["processing_ok"] = True
        stuck_hours = self.up.get("stuck_hours", 10)
        for k, r in pending:
            path = r.get("path") or k
            age = _hours_since(r.get("uploaded_at"))
            if r.get("processing_ok"):
                if not self.up.get("delete_after_upload", True):
                    continue
                _mn, _dl, keep = self.rules_for(r.get("game"))
                if keep > 0 and age is not None and age < keep:
                    continue
                try:
                    media.force_remove(path)
                except OSError as e:
                    self.log(f"  [오류] 로컬 파일 삭제 실패: {e}")
                    continue
                self.store.update(k, cleaned_up=True)
                self.log(f"  [삭제] 처리 완료 확인 후 로컬 정리: {r['name']}")
            elif age is not None and age >= stuck_hours:
                self.log(f"  [정체] {r['name']} 이(가) {age:.1f}시간째 유튜브 처리 대기 중 -> 지우고 다시 올림")
                try:
                    self.yt.delete(svc, r["video_id"])
                except Exception as e:
                    if _http_status(e) != 404:
                        self.log(f"  [오류] 정체된 영상 삭제 실패: {e}")
                        continue
                self.store.update(k, status="waiting", video_id=None, url=None, uploaded_at=None,
                                  processing_ok=False, checked=True)

    # -- 4. 업로드 -------------------------------------------------------------------------------
    def quota_left(self):
        return self.up["daily_limit"] - self.store.uploads_today()

    def title_for(self, path):
        stem = os.path.splitext(os.path.basename(path))[0]
        return (self.up.get("title_template") or "{name}").format(name=stem)[:100]

    def channel_titles(self, svc):
        at, titles = self._titles
        if titles is None or time.time() - at > TITLES_CACHE_SECONDS:
            titles = self.yt.channel_titles(svc)
            self._titles = (time.time(), titles)
        return titles

    def upload_next(self, svc):
        ready = [(k, r) for k, r in self.store.waiting() if r.get("checked")]
        if not ready:
            return False
        if self.quota_left() <= 0:
            self.log_once("quota", f"오늘 업로드 한도({self.up['daily_limit']}개) 소진 -> 남은 영상은 내일 [{datetime.date.today()}]")
            return False
        key, rec = ready[0]
        path = rec.get("path") or key
        if media.in_use(path):
            return False
        title = self.title_for(path)
        existing = self.channel_titles(svc)
        if existing and title in existing:
            vid, published = existing[title]
            self.log(f"  [경고] 채널에 같은 제목의 영상이 이미 있음 -> 다시 올리지 않고 그 영상으로 기록: {rec['name']}")
            self.store.update(key, status="uploaded", video_id=vid, url=f"https://youtu.be/{vid}",
                              uploaded_at=published, reason="duplicate_title")
            self.add_playlist(svc, rec.get("game"), vid)
            return True
        size = os.path.getsize(path) / 1024 / 1024
        self.log(f"  업로드 시작: {rec['name']} ({size:.1f}MB)")
        self.store.set("in_progress", {"key": key, "title": title})
        last = [-10]

        def prog(p):
            self.progress = (rec["name"], p)
            pct = int(p * 100)
            if pct >= last[0] + 10:
                last[0] = pct
                self.log(f"    업로드 중... {pct}%")

        try:
            vid = self.yt.upload(svc, path, title, self.up.get("privacy", "private"), self.up.get("description", ""),
                                 self.up.get("tags", []), self.up.get("category", "20"), prog)
        except Exception as e:
            self.store.set("in_progress", None)
            self.progress = None
            if "quota" in str(e).lower():
                self.log("  [한도 초과] 유튜브 업로드 할당량을 다 씀 -> 내일 다시")
                self.store.data["uploads"]["count"] = max(self.store.uploads_today(), self.up["daily_limit"])
                self.store.data["uploads"]["date"] = datetime.date.today().isoformat()
                self.store.save()
                return False
            self.log(f"  [실패] {rec['name']}: {e}")
            return False
        self.store.set("in_progress", None)
        self.progress = None
        self.store.update(key, status="uploaded", video_id=vid, url=f"https://youtu.be/{vid}", uploaded_at=now_iso())
        self.store.bump_uploads()
        if self.store.data.get("priority") == key:
            self.store.set("priority", None)
        if existing is not None:
            existing[title] = (vid, now_iso())
        self.log(f"  [완료] {self.up.get('privacy', 'private')} 업로드 -> https://youtu.be/{vid}")
        self.add_playlist(svc, rec.get("game"), vid)
        return True

    def add_playlist(self, svc, game, vid):
        """게임 이름의 비공개 재생목록에 넣는다. 실패해도 업로드는 끝난 것이라 기록만 남긴다."""
        if not game or not self.up.get("game_playlists", True):
            return
        try:
            cache = self.store.data["playlists"]
            pid = cache.get(game) or self.yt.find_playlist(svc, game)
            if not pid:
                pid = self.yt.create_playlist(svc, game)
                self.log(f"  [재생목록] 새로 만듦(비공개): {game}")
            if cache.get(game) != pid:
                cache[game] = pid
                self.store.save()
            self.yt.add_to_playlist(svc, pid, vid)
            self.log(f"  [재생목록] '{game}'에 추가")
        except Exception as e:
            self.log(f"  [오류] 재생목록 추가 실패({game}): {e}")

    def recover_interrupted(self, svc):
        """지난번 업로드 도중 꺼졌으면 서버에 반쯤 올라간 영상을 지우고 그 파일을 먼저 다시 올린다."""
        info = self.store.data.get("in_progress")
        if not info:
            return
        self.store.set("in_progress", None)
        key = info.get("key")
        rec = self.store.get(key) if key else None
        if not rec or not os.path.exists(rec.get("path") or key):
            return
        self.log(f"  [복구] 지난번 업로드 도중 중단된 파일 -> 서버 잔재 확인 후 먼저 다시 올림: {rec['name']}")
        existing = self.yt.channel_titles(svc) or {}
        if info.get("title") in existing:
            try:
                self.yt.delete(svc, existing[info["title"]][0])
                self.log("  [복구] 불완전하게 남은 서버 영상 삭제")
            except Exception as e:
                self.log(f"  [복구] 서버 영상 삭제 중 오류(이미 없을 수 있음): {e}")
        self._titles = (0, None)
        self.store.set("priority", key)
