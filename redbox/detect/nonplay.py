"""같은 실행 파일이지만 직접 플레이가 아닌 실행(다시보기, 관전)을 가려낸다."""
import os
import re
import time

import psutil

# 실행 파일 이름(소문자) -> 실행 인자에서 찾을 패턴
NON_PLAY_ARGS = {
    # 리그 오브 레전드: 다시보기는 .rofl 파일, 관전은 'spectator 서버 ...' 로 실행된다
    "league of legends.exe": re.compile(r"\.rofl\b|\bspectator\s", re.I),
}
DECIDE_SECONDS = 20    # 이 시간 안에 실행 인자를 못 읽으면 직접 플레이로 본다


def _riot_log_cmdline(exe_path, started):
    """롤은 안티치트 때문에 실행 인자를 못 읽을 때가 있다. 게임이 남기는 로그 첫머리의 'Command Line:' 으로 대신한다."""
    logs = os.path.join(os.path.dirname(os.path.dirname(exe_path)), "Logs", "GameLogs")
    try:
        dirs = [os.path.join(logs, d) for d in os.listdir(logs)]
        newest = max((d for d in dirs if os.path.isdir(d)), key=os.path.getctime)
        if os.path.getctime(newest) < started - 5:
            return None
        for name in os.listdir(newest):
            if name.endswith("_r3dlog.txt"):
                with open(os.path.join(newest, name), encoding="utf-8", errors="ignore") as f:
                    for _ in range(30):
                        line = f.readline()
                        if "Command Line:" in line:
                            return line
    except (OSError, ValueError):
        pass
    return None


class NonPlay:
    def __init__(self):
        self._cache = {}   # (pid, 이름) -> True(다시보기, 관전) / False(플레이)

    def check(self, pid, name_lower, exe_path):
        """True: 플레이 아님, False: 플레이, None: 아직 모름(다음에 다시)."""
        pattern = NON_PLAY_ARGS.get(name_lower)
        if pattern is None:
            return False
        key = (pid, name_lower)
        if key in self._cache:
            return self._cache[key]
        try:
            proc = psutil.Process(pid)
            started = proc.create_time()
        except psutil.Error:
            return False
        try:
            args = " ".join(proc.cmdline())
        except psutil.Error:
            args = ""
        if not args and exe_path:
            args = _riot_log_cmdline(exe_path, started) or ""
        if not args:
            if time.time() - started < DECIDE_SECONDS:
                return None
            self._cache[key] = False
            return False
        self._cache[key] = bool(pattern.search(args))
        return self._cache[key]

    def forget(self, alive_keys):
        for k in [k for k in self._cache if k not in alive_keys]:
            del self._cache[k]
