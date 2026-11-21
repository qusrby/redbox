"""녹화본 썸네일.

녹화하는 동안 OBS 캡처 화면을 몇 분마다 한 장씩 찍어 두고, 녹화가 끝나면 그중 한 장을 골라 영상 파일과 짝지어 둔다.
영상 파일을 지운 뒤에도 목록에서 영상을 구분할 수 있게 하려는 것이다(유튜브 비공개 영상은 썸네일 주소가 막혀 있다).
"""
import hashlib
import io
import os
import shutil

from . import paths
from .uploader.store import file_key

WIDTH, HEIGHT = 640, 360
FIRST = 45            # 녹화 시작 뒤 첫 장(로딩 화면을 피하려고 조금 기다린다)
EVERY = 180           # 그 뒤 간격
PICK_AT = 0.4         # 녹화 길이의 이 지점에 가장 가까운 장을 고른다
DARK = 14             # 평균 밝기가 이보다 낮으면(검은 화면, 로딩) 버린다


def folder():
    d = os.path.join(paths.data_dir(), "thumbs")
    os.makedirs(d, exist_ok=True)
    return d


def live_folder():
    d = os.path.join(folder(), "live")
    os.makedirs(d, exist_ok=True)
    return d


def path_for(video):
    return os.path.join(folder(), hashlib.sha1(file_key(video).encode("utf-8")).hexdigest()[:24] + ".jpg")


def find(video):
    """영상의 썸네일 파일 경로. 없으면 None."""
    p = path_for(video) if video else None
    return p if p and os.path.exists(p) else None


def latest_live():
    """지금 녹화 중인 영상의 가장 최근 장면. 없으면 None."""
    try:
        shots = [f for f in os.listdir(live_folder()) if f.endswith(".jpg")]
    except OSError:
        return None
    if not shots:
        return None
    return os.path.join(live_folder(), max(shots, key=lambda f: int(f[:-4])))


def _dark(data):
    try:
        from PIL import Image, ImageStat
        im = Image.open(io.BytesIO(data)).convert("L").resize((32, 18))
        return ImageStat.Stat(im).mean[0] < DARK
    except Exception:
        return False


def _clear_live():
    shutil.rmtree(os.path.join(folder(), "live"), ignore_errors=True)


class Shooter:
    """녹화 세션 하나 동안 장면을 찍는다. 녹화 엔진이 2초마다 tick 을 부른다."""

    def __init__(self, log):
        self.log = log
        self.start = None
        self.next = None
        self.failed = False

    def begin(self, start):
        _clear_live()
        self.start, self.next, self.failed = start, start + FIRST, False

    def tick(self, obs, now):
        if self.next is None or now < self.next:
            return
        self.next = now + EVERY
        try:
            data = obs.screenshot(WIDTH, HEIGHT)
        except Exception as e:
            if not self.failed:
                self.failed = True
                self.log(f"  [썸네일] OBS 화면 찍기 실패: {e}")
            return
        if not data or _dark(data):
            self.next = now + 30          # 검은 화면이면 조금 뒤에 다시
            return
        with open(os.path.join(live_folder(), f"{int(now - self.start)}.jpg"), "wb") as f:
            f.write(data)

    def finish(self, video, duration):
        """녹화가 끝나 파일이 정해지면 한 장을 골라 영상과 짝짓는다."""
        self.next = None
        try:
            shots = [int(f[:-4]) for f in os.listdir(live_folder()) if f.endswith(".jpg")]
            if video and shots:
                t = min(shots, key=lambda s: abs(s - duration * PICK_AT))
                shutil.copyfile(os.path.join(live_folder(), f"{t}.jpg"), path_for(video))
        except OSError as e:
            self.log(f"  [썸네일] 저장 실패: {e}")
        _clear_live()

    def cancel(self):
        self.next = None
        _clear_live()
