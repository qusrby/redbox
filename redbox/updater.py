"""새 버전 알림: 깃허브 Releases 의 최신 버전을 하루 한 번 확인한다. 알려 주기만 하고 설치는 하지 않는다."""
import json
import re
import threading
import time
import urllib.request

from . import APP_NAME, VERSION

REPO = "qusrby/redbox"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
CHECK_EVERY = 24 * 3600


def parse(text):
    """'v1.2.3' -> (1, 2, 3). 숫자가 없으면 (0,)."""
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:3]) or (0,)


def latest(timeout=10):
    """최신 릴리스 (버전 문자열, 페이지 주소). 못 읽으면 None(저장소가 비공개거나 인터넷이 끊긴 경우 등)."""
    req = urllib.request.Request(API, headers={"User-Agent": f"{APP_NAME}/{VERSION}",
                                               "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
    except Exception:
        return None
    tag = d.get("tag_name") or ""
    if not tag or d.get("draft") or d.get("prerelease"):
        return None
    return tag.lstrip("vV"), d.get("html_url") or f"https://github.com/{REPO}/releases/latest"


class UpdateChecker:
    def __init__(self, cfg):
        self.cfg = cfg
        self.new = None          # (버전, 주소) 지금보다 새 버전이 있으면
        self._last = 0.0

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="updates").start()

    def _loop(self):
        time.sleep(20)           # 켜자마자 인터넷을 쓰지 않게 잠깐 기다린다
        while True:
            if self.cfg.get("check_updates", True) and time.time() - self._last > CHECK_EVERY:
                self._last = time.time()
                r = latest()
                if r and parse(r[0]) > parse(VERSION):
                    self.new = r
            time.sleep(600)
