"""영상 파일 다루기: 길이 읽기, 사용 중 확인, 안전한 삭제."""
import datetime
import os
import re
import stat

_DURATION_TAG = re.compile(r"(\d+)m(\d+)s")
_TIMESTAMP = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2})")


def duration_seconds(path):
    """재생 시간(초). 파일 이름의 길이 표시(12m34s) > 파일 이름의 시작 시각과 수정 시각 차이 > mp4 헤더."""
    name = os.path.basename(path)
    m = _DURATION_TAG.search(name)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = _TIMESTAMP.search(name)
    if m:
        try:
            start = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H-%M-%S")
            elapsed = os.path.getmtime(path) - start.timestamp()
            if elapsed > 0:
                return elapsed
        except (ValueError, OSError):
            pass
    try:
        return _mvhd_duration(path)
    except OSError:
        return None


def _mvhd_duration(path):
    """mp4 의 moov/mvhd 상자에서 길이를 읽는다(조각난 mp4 는 대개 0)."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        end = f.tell()

        def walk(start, stop):
            pos = start
            while pos < stop:
                f.seek(pos)
                head = f.read(8)
                if len(head) < 8:
                    return None
                size, kind = int.from_bytes(head[:4], "big"), head[4:8]
                body = pos + 8
                if size == 1:
                    size = int.from_bytes(f.read(8), "big")
                    body += 8
                box_end = pos + size if size > 0 else stop
                if kind == b"moov":
                    r = walk(body, box_end)
                    if r is not None:
                        return r
                elif kind == b"mvhd":
                    f.seek(body)
                    ver = f.read(1)[0]
                    f.seek(body + (12 if ver == 0 else 20))
                    scale = int.from_bytes(f.read(4), "big")
                    dur = int.from_bytes(f.read(4 if ver == 0 else 8), "big")
                    return dur / scale if scale else None
                if size <= 0:
                    break
                pos = box_end
            return None

        return walk(0, end)


def in_use(path):
    """다른 프로그램이 열어 둔 파일(녹화 중, 동기화 중)인지. 자기 이름으로 바꿔 보면 열려 있을 때만 막힌다."""
    try:
        os.rename(path, path)
        return False
    except FileNotFoundError:
        return False
    except OSError:
        return True


def force_remove(path):
    try:
        if not os.access(path, os.W_OK):
            os.chmod(path, stat.S_IWRITE)
    except OSError:
        pass
    os.remove(path)
