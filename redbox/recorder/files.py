"""녹화 파일 이름 정리, 안전한 이동, 스크린샷 정리."""
import datetime
import os
import re
import shutil
import time

_ILLEGAL = re.compile(r'[<>:"/\\|?*]')
DEFAULT_TEMPLATE = "{game} Video {start} {duration}"


def safe_name(name):
    """윈도우 파일, 폴더 이름에 쓸 수 없는 문자를 뺀다(콜론은 ' -' 로)."""
    name = name.replace(":", " -")
    name = _ILLEGAL.sub("", name)
    return name.strip().rstrip(" .") or "Game"


def format_duration(seconds):
    m, s = divmod(max(0, int(seconds)), 60)
    return f"{m}m{s:02d}s"


def recording_name(template, game, start_ts, duration, ext):
    start = datetime.datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H-%M-%S")
    text = (template or DEFAULT_TEMPLATE).format(game=game, start=start, duration=format_duration(duration))
    return safe_name(text) + ext


def unique_dest(dst):
    """같은 이름이 있으면 ' (2)', ' (3)' 을 붙인다. 덮어쓰지 않는다."""
    base, ext = os.path.splitext(dst)
    cand, n = dst, 1
    while os.path.exists(cand):
        n += 1
        cand = f"{base} ({n}){ext}"
    return cand


def rename_with_retry(src, dst, tries=10, wait=1.0):
    """OBS 가 파일을 잠깐 더 붙잡고 있을 수 있어 몇 번 다시 시도한다. 새 경로 또는 None."""
    dst = unique_dest(dst)
    for i in range(tries):
        try:
            os.rename(src, dst)
            return dst
        except OSError:
            if i == tries - 1:
                return None
            time.sleep(wait)


def remove_with_retry(path, tries=10, wait=1.0):
    for i in range(tries):
        try:
            os.remove(path)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            if i == tries - 1:
                return False
            time.sleep(wait)


def move_safely(src, dst):
    """같은 드라이브면 이름 변경 한 번, 다른 드라이브면 복사 후 크기 확인, 그다음 원본 삭제."""
    dst = unique_dest(dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.rename(src, dst)
        return dst
    except OSError as e:
        if getattr(e, "winerror", None) != 17:    # 다른 드라이브가 아니면 실패
            raise
    tmp = dst + ".part"
    try:
        shutil.copy2(src, tmp)
        if os.path.getsize(tmp) != os.path.getsize(src):
            raise OSError("복사본 크기가 원본과 다름")
        os.replace(tmp, dst)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise
    os.remove(src)
    return dst


def sweep_screenshots(video_root, dest_root, settle_seconds=2.0):
    """영상 폴더의 게임별 하위 폴더에 생긴 png(OBS 스크린샷)를 '게임 Screenshot 원래이름' 으로
    dest_root\\게임 으로 옮긴다. 저장 중이거나 실패한 것은 다음 호출에서 다시. [(원래 이름, 새 경로)]"""
    moved = []
    try:
        games = [d for d in os.listdir(video_root) if os.path.isdir(os.path.join(video_root, d))]
    except OSError:
        return moved
    now = time.time()
    for game in games:
        folder = os.path.join(video_root, game)
        prefix = f"{game} Screenshot "
        try:
            pngs = sorted(f for f in os.listdir(folder) if f.lower().endswith(".png"))
        except OSError:
            continue
        for name in pngs:
            src = os.path.join(folder, name)
            try:
                if now - os.path.getmtime(src) < settle_seconds:
                    continue
                new = name if name.startswith(prefix) else prefix + name
                moved.append((name, move_safely(src, os.path.join(dest_root, game, new))))
            except OSError:
                continue
    return moved
