"""정전이나 강제 종료에도 깨지지 않게 파일을 쓰고 읽는다.

새 내용을 임시 파일에 써서 디스크까지 내린(fsync) 뒤 바꿔 끼우고, 바로 전 파일은 .bak 으로 남긴다.
읽을 때 본 파일이 없거나 깨졌으면 .bak 을 읽는다.
"""
import json
import os


def write_text(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    if os.path.exists(path):
        try:
            os.replace(path, path + ".bak")
        except OSError:
            pass                      # 백업을 못 남겨도 새 내용 저장은 한다
    os.replace(tmp, path)


def write_json(path, data, indent=1):
    write_text(path, json.dumps(data, ensure_ascii=False, indent=indent))


def read_json(path):
    """본 파일, 안 되면 .bak. 둘 다 없으면 FileNotFoundError, 남은 것이 깨졌으면 ValueError."""
    err = None
    for p in (path, path + ".bak"):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError as e:
            err = err or e
        except ValueError as e:
            err = e
    raise err


def exists(path):
    return os.path.exists(path) or os.path.exists(path + ".bak")
