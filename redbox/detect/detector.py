"""게임 감지. 실행 중인 프로세스를 보고 녹화할 게임인지, 왜 그런지를 정한다.
자동 녹화는 스팀 게임만. 그 밖의 게임은 사용자가 '게임 추가'로 직접 넣은 것만 녹화한다.

판정 순서(먼저 걸리는 것이 답):
  1. 사용자 목록: '녹화 안 함', '항상 녹화'(예전 설정)
  2. 직접 추가한 게임: 실행 파일이면 그 파일, 폴더면 그 안에서 게임 창을 띄운 것
  3. 기본 제외: 브라우저, 플레이어, 에디터, 런처, 설치 프로그램 등
  4. 스팀 게임 폴더 안: 그래픽 모듈을 불러오고 큰 창을 띄운 것(스팀으로 깐 도구를 거르기 위해)
녹화하지 않는 프로그램이 전체 화면 + 그래픽 모듈로 일정 시간 돌면 '게임 추가' 후보로 기억해 둔다.
"""
import json
import os
import time

from .. import paths
from . import rules, win32
from .catalog import Catalog
from .nonplay import NonPlay

MIN_GAME_WINDOW = (800, 600)
CATALOG_REFRESH_SECONDS = 3600
GFX_RECHECK_SECONDS = 5


class Decision:
    __slots__ = ("pid", "exe", "path", "record", "reason", "name")

    def __init__(self, pid, exe, path, record, reason, name=""):
        self.pid, self.exe, self.path, self.record, self.reason, self.name = pid, exe, path, record, reason, name

    def key(self):
        return (self.record, self.reason)


class Detector:
    def __init__(self, cfg):
        self.cfg = cfg
        self.catalog = None
        self.catalog_at = 0
        self._paths = {}         # (pid, 이름) -> 경로
        self._gfx = {}           # pid -> (그래픽 모듈 여부 True/False/None, 확인 시각)
        self._full_since = {}    # pid -> 전체 화면이 시작된 시각
        self._names = {}         # 경로 -> 게임 이름
        self._confirmed = {}     # pid -> 이유. 화면 판정 등으로 한 번 게임이 되면 꺼질 때까지 유지(알트탭해도 녹화 유지)
        self.nonplay = NonPlay()
        self.last_procs = []
        self.suggestions = self._load_suggestions()
        self.refresh_catalog()

    # -- 목록 ---------------------------------------------------------------------------------
    def refresh_catalog(self):
        self.catalog = Catalog(self.cfg["detection"])
        self.catalog_at = time.time()
        self._names.clear()

    # -- 직접 추가한 게임 -----------------------------------------------------------------------------
    def custom_game(self, path_lower):
        """직접 추가한 게임 중 이 실행 파일에 해당하는 것 {"name", "path"} 또는 None."""
        for g in self.cfg["detection"].get("custom_games", []):
            p = str(g.get("path", "")).lower().rstrip("\\/")
            if p and (path_lower == p or path_lower.startswith(p + "\\")):
                return g
        return None

    # -- 추가 후보(녹화하지 않았지만 게임처럼 돈 프로그램) ----------------------------------------------------
    @staticmethod
    def _suggest_file():
        return os.path.join(paths.data_dir(), "suggestions.json")

    def _load_suggestions(self):
        try:
            with open(self._suggest_file(), encoding="utf-8") as f:
                return dict(json.load(f))
        except (OSError, ValueError):
            return {}

    def _suggest(self, path, now):
        key = path.lower()
        new = key not in self.suggestions
        self.suggestions[key] = {"path": path, "name": self.game_name(path), "last": int(now)}
        if new:
            keep = sorted(self.suggestions.items(), key=lambda kv: kv[1]["last"], reverse=True)[:40]
            self.suggestions = dict(keep)
            try:
                with open(self._suggest_file() + ".tmp", "w", encoding="utf-8") as f:
                    json.dump(self.suggestions, f, ensure_ascii=False, indent=1)
                os.replace(self._suggest_file() + ".tmp", self._suggest_file())
            except OSError:
                pass

    def game_name(self, path):
        if path in self._names:
            return self._names[path]
        pl = path.lower()
        custom = self.custom_game(pl)
        name = custom.get("name") if custom else None
        name = name or self.cfg["detection"].get("names", {}).get(pl)
        if not name:
            entry, _exact = self.catalog.launcher_entry(pl)
            name = entry.name if entry and entry.name else None
        if not name:
            name = win32.product_name(path)
        if not name:
            name = os.path.splitext(os.path.basename(path))[0]
        self._names[path] = name
        return name

    # -- 그래픽 모듈 ------------------------------------------------------------------------------
    def _uses_gfx(self, pid, now):
        """True(불러옴) / False(아직 안 불러옴) / None(권한 없음: 안티치트 게임 등)."""
        got = self._gfx.get(pid)
        if got and (got[0] is not False or now - got[1] < GFX_RECHECK_SECONDS):
            return got[0]
        mods = win32.module_names(pid)
        val = None if mods is None else bool(mods & rules.GFX_MODULES)
        self._gfx[pid] = (val, now)
        return val

    # -- 판정 -----------------------------------------------------------------------------------
    def evaluate(self, now=None):
        """{pid: Decision} 녹화 대상이거나 판정이 의미 있는 프로세스만."""
        now = now or time.time()
        if now - self.catalog_at > CATALOG_REFRESH_SECONDS:
            self.refresh_catalog()
        det = self.cfg["detection"]
        procs = win32.list_processes()
        self.last_procs = procs
        alive = {(pid, name.lower()) for pid, name in procs}
        for k in [k for k in self._paths if k not in alive]:
            del self._paths[k]
        pids = {pid for pid, _ in alive}
        for d in (self._gfx, self._full_since, self._confirmed):
            for pid in [p for p in d if p not in pids]:
                del d[pid]

        fg_hwnd, fg_pid, fg_full = win32.foreground()
        windows = None   # 필요할 때만 한 번 훑는다
        out = {}
        for pid, name in procs:
            nl = name.lower()
            if pid in (0, 4):
                continue
            key = (pid, nl)
            path = self._paths.get(key)
            if path is None:
                path = win32.exe_path(pid)
                self._paths[key] = path
            pl = path.lower()

            if rules.in_user_list(det.get("never_record", []), nl, pl):
                continue
            if rules.in_user_list(det.get("always_record", []), nl, pl):
                out[pid] = Decision(pid, name, path, True, "항상 녹화 목록")
                continue
            custom = self.custom_game(pl) if pl else None
            if custom and pl == str(custom.get("path", "")).lower():
                out[pid] = Decision(pid, name, path, True, "직접 추가한 게임")
                continue
            if rules.is_default_excluded(nl) or not path:
                continue
            if pid in self._confirmed:
                out[pid] = Decision(pid, name, path, True, self._confirmed[pid])
                continue
            entry, _exact = self.catalog.launcher_entry(pl)
            steam = entry if entry and entry.source == "steam" else None
            if custom or steam:
                label = "직접 추가한 게임" if custom else "Steam"
                gfx = self._uses_gfx(pid, now)
                if windows is None:
                    windows = win32.visible_windows()
                big = any(w >= MIN_GAME_WINDOW[0] and h >= MIN_GAME_WINDOW[1] for _hw, w, h in windows.get(pid, []))
                if gfx is not False and big:
                    out[pid] = Decision(pid, name, path, True, f"{label} 폴더 + 게임 창")
                else:
                    out[pid] = Decision(pid, name, path, False, f"{label} 폴더(게임 창 아직 없음)")
                continue
            # 녹화하지 않는 프로그램: 게임처럼 전체 화면으로 돌면 '게임 추가' 후보로만 기억한다
            if det.get("screen_detect", True) and pid == fg_pid and fg_full and not rules.is_system_path(pl):
                if self._uses_gfx(pid, now) is False:
                    self._full_since.pop(pid, None)
                    continue
                since = self._full_since.setdefault(pid, now)
                if now - since >= det.get("screen_detect_seconds", 10):
                    self._suggest(path, now)
            else:
                self._full_since.pop(pid, None)
        self.nonplay.forget(alive)
        for d in out.values():
            if d.record:
                np = self.nonplay.check(d.pid, d.exe.lower(), d.path)
                if np is None:
                    d.record, d.reason = False, "실행 인자 확인 중"
                elif np:
                    d.record, d.reason = False, "다시보기 또는 관전"
            if d.record:
                d.name = self.game_name(d.path)
                if d.reason.endswith("게임 창"):
                    self._confirmed[d.pid] = d.reason
        return out
