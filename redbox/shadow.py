"""그림자 실행: 녹화는 하지 않고 감지 판정만 로그에 남긴다.
새 감지를 실제 녹화에 쓰기 전에, 며칠 동안 평소처럼 게임을 하며 판정이 맞는지 확인하는 용도.
다른 판정 방식과 비교하고 싶으면 Shadow 를 상속해 compare() 와 extra() 를 채운다."""
import datetime
import os
import time

from . import paths
from .detect import Detector, win32

POLL_SECONDS = 2


class Shadow:
    def __init__(self, cfg, log_path=None):
        self.det = Detector(cfg)
        self.log_path = log_path or os.path.join(paths.log_dir(), "shadow.log")
        self.state = {}       # pid -> 마지막으로 남긴 판정
        self.stats = {"start": 0, "diff": 0}

    def log(self, msg):
        line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def header(self):
        c = self.det.catalog
        counts = ", ".join(f"{k} {v}" for k, v in c.counts.items())
        self.log("=" * 60)
        self.log(f"그림자 실행 시작. 모은 목록: {counts}")
        for k, e in c.errors.items():
            self.log(f"  [목록 오류] {k}: {e}")

    def compare(self, decision):
        """다른 방식의 판정(True/False) 또는 None(비교 안 함)."""
        return None

    def extra(self, seen, procs):
        """새 방식이 판정하지 않은 프로세스를 더 볼 때 쓴다."""

    def tick(self):
        decisions = self.det.evaluate(time.time())
        seen = set()
        for pid, d in decisions.items():
            seen.add(pid)
            other = self.compare(d)
            key = (d.key(), other)
            if self.state.get(pid) == key:
                continue
            self.state[pid] = key
            verdict = "녹화" if d.record else "보류"
            name = f" '{d.name}'" if d.name else ""
            cmp = ""
            if other is not None and d.record != other:
                cmp = f"  [차이] 비교 방식은 {'녹화' if other else '안 함'}"
                self.stats["diff"] += 1
            if d.record:
                self.stats["start"] += 1
            self.log(f"{verdict}: {d.exe}{name} (pid {pid}) - {d.reason}{cmp}")
        procs = win32.list_processes()
        self.extra(seen, procs)
        alive = {pid for pid, _ in procs}
        for pid in [p for p in self.state if p not in seen and p not in alive]:
            prev = self.state.pop(pid)
            if isinstance(prev, tuple) and prev[0][0]:
                self.log(f"끝남: pid {pid}")

    def run(self, seconds=None):
        win32.set_dpi_aware()
        self.header()
        end = time.time() + seconds if seconds else None
        stop_flag = os.path.join(paths.data_dir(), "shadow.stop")   # 이 파일을 만들면 끝난다
        if os.path.exists(stop_flag):
            os.remove(stop_flag)
        try:
            while (end is None or time.time() < end) and not os.path.exists(stop_flag):
                self.tick()
                time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            pass
        self.log(f"그림자 실행 끝. 녹화 판정 {self.stats['start']}번, 비교 방식과 차이 {self.stats['diff']}번")
