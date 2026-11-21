"""업로드 상태 저장소(데이터 폴더의 uploads.json). 녹화 엔진과 업로드 스레드가 함께 쓰므로 잠금을 건다.

녹화 하나의 기록(recordings[키]):
  name, path, game, duration, added_at, status, video_id, url, uploaded_at, processing_ok, cleaned_up, reason
status: waiting(대기) / uploaded(올라감) / excluded(짧아서 제외) / auto_deleted(짧아서 삭제) / missing(파일 없음)
"""
import datetime
import os
import threading

from .. import paths, safefile


def file_key(path):
    return os.path.normcase(os.path.abspath(path))


def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def today():
    return datetime.date.today().isoformat()


class Store:
    def __init__(self, path=None):
        self.path = path or os.path.join(paths.data_dir(), "uploads.json")
        self.lock = threading.RLock()
        self.data = self._load()

    def _load(self):
        try:
            d = safefile.read_json(self.path)
        except (OSError, ValueError):
            d = {}
        for k, v in (("recordings", {}), ("uploads", {"date": "", "count": 0}), ("playlists", {})):
            d.setdefault(k, v)
        return d

    def save(self):
        with self.lock:
            safefile.write_json(self.path, self.data, indent=1)

    # -- 녹화 ----------------------------------------------------------------------------------
    def add_recording(self, path, game, duration):
        """녹화 엔진이 녹화를 끝낼 때 부른다. 이미 있으면 그대로 둔다."""
        key = file_key(path)
        with self.lock:
            if key in self.data["recordings"]:
                return False
            self.data["recordings"][key] = {
                "name": os.path.basename(path), "path": path, "game": game,
                "duration": round(float(duration), 1), "added_at": now_iso(), "status": "waiting",
            }
            self.save()
            return True

    def get(self, key):
        return self.data["recordings"].get(key)

    def update(self, key, **fields):
        with self.lock:
            rec = self.data["recordings"].setdefault(key, {})
            rec.update(fields)
            self.save()

    def remove(self, key):
        with self.lock:
            self.data["recordings"].pop(key, None)
            self.save()

    def waiting(self):
        with self.lock:
            items = [(k, dict(v)) for k, v in self.data["recordings"].items() if v.get("status") == "waiting"]
        prio = self.data.get("priority")
        items.sort(key=lambda kv: (kv[0] != prio, kv[1].get("added_at", "")))
        return items

    def uploaded_not_cleaned(self):
        with self.lock:
            return [(k, dict(v)) for k, v in self.data["recordings"].items()
                    if v.get("video_id") and not v.get("cleaned_up")]

    # -- 하루 업로드 개수 --------------------------------------------------------------------------
    def uploads_today(self):
        up = self.data["uploads"]
        return up.get("count", 0) if up.get("date") == today() else 0

    def bump_uploads(self):
        with self.lock:
            up = self.data["uploads"]
            if up.get("date") != today():
                up["date"], up["count"] = today(), 0
            up["count"] += 1
            self.save()

    # -- 그 밖 ---------------------------------------------------------------------------------
    def set(self, key, value):
        with self.lock:
            if value is None:
                self.data.pop(key, None)
            else:
                self.data[key] = value
            self.save()
