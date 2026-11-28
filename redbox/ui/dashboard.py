"""대시보드: 지금 녹화 상태(크게), 앱, OBS Studio, OBS 연결, 유튜브 상태, 최근 영상 몇 개."""
import datetime
import threading
import time

from PyQt6.QtCore import QEvent, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ..i18n import tr
from ..recorder import obs as obsmod
from ..uploader import youtube
from . import icons
from .art import cover
from .style import C
from .videos import RecordTable, ROW_H, upload_progress, uploading_rec
from .widgets import Dot, ElideLabel, button, fmt_elapsed, fmt_time, label, open_target, rec_time, tabular

HEAD_H = 36            # 표 머리줄 높이


def _set(w, text=None, css=None):
    """바뀔 때만 고친다(매초 다시 입히면 스타일 계산이 다시 돈다)."""
    if text is not None and w.text() != text:
        w.setText(text)
    if css is not None and w.styleSheet() != css:
        w.setStyleSheet(css)


class Hero(QFrame):
    """지금 상태 칸. 녹화 중이면 그 게임의 스팀 배경 그림을 깔고 빨간 표시."""

    SHADE = ((0, 195), (0.45, 95), (1, 0))         # 왼쪽부터 덮는 바탕색의 진하기(위치, 알파)

    def __init__(self, art):
        super().__init__()
        self.setObjectName("hero")
        self.art = art
        self.setFixedHeight(176)
        self.game = None
        self._bg = None
        # 왼쪽 위: 상태, 오른쪽 위: 녹화 시간 / 가운데: 게임 이름 / 왼쪽 아래: 시작 시각, 오른쪽 아래: OBS Studio 실행
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 22, 22, 20)
        v.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.dot = Dot(16, 10)
        top.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self.state = label("", "herostate")
        top.addWidget(self.state)
        top.addStretch(1)
        self.timer = label("", "herotime")
        f = tabular(self.timer.font())            # 글꼴은 여기서(스타일 시트로 주면 고정폭 숫자 설정이 빠진다)
        f.setPixelSize(20)
        f.setWeight(QFont.Weight.Bold)
        self.timer.setFont(f)
        top.addWidget(self.timer, 0, Qt.AlignmentFlag.AlignVCenter)
        v.addLayout(top)
        v.addStretch(1)
        self.big = label("", "herobig")
        v.addWidget(self.big)
        bottom = QHBoxLayout()
        self.meta = label("", "herometa")
        bottom.addWidget(self.meta, 1, Qt.AlignmentFlag.AlignBottom)
        self.action = button("", primary=True)        # OBS Studio 가 꺼져 있을 때만
        self.action.hide()
        bottom.addWidget(self.action, 0, Qt.AlignmentFlag.AlignBottom)
        self.stop = button(tr("dash.stop"), icon_name="stop")   # 녹화 중일 때만
        self.stop.hide()
        bottom.addWidget(self.stop, 0, Qt.AlignmentFlag.AlignBottom)
        v.addLayout(bottom)

    def set_game(self, game):
        if game != self.game:
            self.game = game
            self._bg = None
            self.update()

    def _background(self):
        if self._bg is not None and self._bg.size() == self.size():
            return self._bg
        files = self.art.game_files(self.game) if self.game else {}
        src = QPixmap(files["hero"]) if files.get("hero") else None
        pm = cover(src, self.width(), self.height()) if src is not None and not src.isNull() else None
        self._bg = pm if pm is not None else QPixmap()
        return self._bg

    def paintEvent(self, _e):
        p = QPainter(self)
        r = QRectF(self.rect())
        bg = self._background() if self.game else None
        if bg is not None and not bg.isNull():
            p.drawPixmap(0, 0, bg)
            g = QLinearGradient(0, 0, self.width(), 0)       # 글자가 읽히게 왼쪽을 바탕색으로 덮는다
            base = QColor(C["bg"])
            for pos, alpha in self.SHADE:
                c = QColor(base)
                c.setAlpha(alpha)
                g.setColorAt(pos, c)
            p.fillRect(r, g)
        else:
            p.fillRect(r, QColor(C["surface"]))
        p.setPen(QColor(C["rec"] if self.game else C["border"]))
        p.drawRect(r.adjusted(0.5, 0.5, -0.5, -0.5))
        p.end()


class Tile(QFrame):
    """작은 상태 칸: 이름(오른쪽에 보조 값) / 표시와 값 / 한 줄 설명(오른쪽에 시각). progress 가 있으면 아래 끝에 게이지."""

    def __init__(self):
        super().__init__()
        self.setObjectName("tile")
        self.progress = None
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.name = label("", "tilename")
        top.addWidget(self.name, 1)
        self.side = label("", "tilenote")
        top.addWidget(self.side)
        v.addLayout(top)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.dot = Dot(18, 9)
        row.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self.value = label("", "tilevalue")
        row.addWidget(self.value, 1)
        v.addLayout(row)
        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        self.note = ElideLabel("", "tilenote")        # 긴 게임 이름은 줄임표로(시각은 늘 보이게)
        bottom.addWidget(self.note, 1)
        self.when = label("", "tilenote")
        bottom.addWidget(self.when)
        v.addLayout(bottom)

    def set(self, name, value, color, note, side="", when="", progress=None):
        _set(self.name, name)
        _set(self.side, side)
        _set(self.value, value, f"color: {color if color != C['ok'] else C['text']};")
        self.dot.set_color(color)
        if self.note.text() != (note or " "):
            self.note.setText(note or " ")
            self.note.setToolTip(note or "")
        _set(self.when, when)
        if progress != self.progress:
            self.progress = progress
            self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.progress is None:
            return
        p = QPainter(self)
        bar = QRectF(1, self.height() - 4, self.width() - 2, 3)          # 칸 아래 테두리 바로 안쪽
        p.fillRect(bar, QColor(C["border"]))
        p.fillRect(QRectF(bar.left(), bar.top(), bar.width() * max(0.0, min(1.0, self.progress)), bar.height()),
                   QColor(C["accent"]))
        p.end()


class DashboardPage(QWidget):
    def __init__(self, svc, art, show_videos):
        super().__init__()
        self.svc = svc
        self._sig = None
        self.fit = 1                     # 창 높이에 들어가는 최근 영상 줄 수
        v = QVBoxLayout(self)
        v.setContentsMargins(32, 0, 32, 0)
        v.setSpacing(16)
        self.hero = Hero(art)
        v.addWidget(self.hero)
        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.tiles = [Tile() for _ in range(4)]
        self._obs_exe = obsmod.find_obs()
        self._obs_launch = 0.0           # OBS Studio 실행 버튼을 누른 시각(켜질 때까지 버튼을 잠근다)
        self.hero.action.clicked.connect(self._run_obs)
        for t in self.tiles:
            tiles.addWidget(t, 1)
        v.addLayout(tiles)
        v.addSpacing(8)
        head = QHBoxLayout()
        head.addWidget(label(tr("dash.recent"), "h2"))
        head.addStretch(1)
        studio = QPushButton(tr("dash.studio"))          # 유튜브 스튜디오의 채널 콘텐츠(올린 영상 목록)
        studio.setObjectName("link")
        studio.setIcon(icons.icon("external", C["text2"], 14))
        studio.setCursor(Qt.CursorShape.PointingHandCursor)
        studio.clicked.connect(self._open_studio)
        head.addWidget(studio)
        head.addSpacing(20)
        more = QPushButton(tr("dash.all"))
        more.setObjectName("link")
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        more.clicked.connect(show_videos)
        head.addWidget(more)
        v.addLayout(head)
        self.recent = RecordTable(self, art)
        t = self.recent.table
        t.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        t.setMinimumHeight(HEAD_H + ROW_H)
        t.installEventFilter(self)       # 표 높이가 바뀌면 들어가는 줄 수만큼 다시 채운다(스크롤 없이)
        v.addWidget(t, 1)
        self.empty = label(tr("empty.title"), "muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        v.addWidget(self.empty, 1)

    def _open_studio(self):
        """채널 ID 를 알면 바로, 모르면 뒤에서 알아낸 뒤 연다(처음 한 번만 걸린다)."""
        store = self.svc.store
        cid = store.data.get("channel_id")
        if cid:
            open_target(youtube.studio_url(cid))
            return

        def work():
            found = youtube.channel_id() if youtube.has_secret() else None
            if found:
                store.set("channel_id", found)
            open_target(youtube.studio_url(found))
        threading.Thread(target=work, daemon=True, name="studio").start()

    def _run_obs(self):
        """OBS Studio 를 켠다(첫 실행 안내와 같은 방식, 트레이로). 설치돼 있지 않으면 받는 곳을 연다."""
        self._obs_exe = obsmod.find_obs()
        if not self._obs_exe:
            open_target(obsmod.OBS_DOWNLOAD)
            return
        try:
            obsmod.launch_obs(self._obs_exe)
        except OSError as e:
            self.svc.log(f"OBS Studio 실행 실패: {e}")
            return
        self.svc.log("대시보드에서 OBS Studio 실행")
        self._obs_launch = time.time()
        if getattr(self, "_last", None):
            self.refresh_status(*self._last)

    def _stop_recording(self):
        """녹화 중지: 알림 창으로 묻고, 멈추면 그 게임을 다시 실행할 때까지 자동 녹화하지 않는다."""
        s = self.svc.recorder.session
        if not s:
            return
        from .dialogs import StopRecordingDialog
        if StopRecordingDialog(self, s.game).exec() and self.svc.recorder.session is s:
            self.svc.recorder.request_stop()
            self._stopping = s
            self.svc.log(f"대시보드에서 녹화 중지: {s.game}")
            if getattr(self, "_last", None):
                self.refresh_status(*self._last)

    def _stop_button(self, s):
        b = self.hero.stop
        if not s:
            self._stopping = None
            b.hide()
            return
        stopping = getattr(self, "_stopping", None) is s
        _set(b, tr("dash.stopping") if stopping else tr("dash.stop"))
        if b.isEnabled() == stopping:
            b.setEnabled(not stopping)
        b.show()

    def _obs_action(self):
        """녹화 중이 아니고 OBS Studio 가 꺼져 있을 때만 큰 칸에 실행 버튼. 누른 뒤 20초 동안은 켜는 중으로 잠근다."""
        b = self.hero.action
        if self.svc.obs_pid or self.svc.recorder.session:
            self._obs_launch = 0.0
            b.hide()
            return
        starting = time.time() - self._obs_launch < 20
        _set(b, tr("dash.obs.starting") if starting else tr("dash.obs.run") if self._obs_exe else tr("dash.obs.get"))
        if b.isEnabled() == starting:
            b.setEnabled(not starting)
        b.show()

    def eventFilter(self, obj, ev):
        if obj is self.recent.table and ev.type() == QEvent.Type.Resize:
            n = max(1, (obj.height() - HEAD_H - 2) // ROW_H)
            if n != self.fit:
                self.fit = n
                self._sig = None
                self.refresh()
        return False

    def refresh_status(self, rows, problem):
        """창이 1초마다 부른다. rows, problem 은 window.health() 결과."""
        self._last = (rows, problem)
        svc, s, now = self.svc, self.svc.recorder.session, time.time()
        h = self.hero
        if s:
            color, state, big = C["rec"], tr("state.recording"), s.game
            meta = tr("dash.started").format(t=fmt_time(datetime.datetime.fromtimestamp(s.start)))
            _set(h.timer, fmt_elapsed(now - s.start))
            h.timer.show()
            h.set_game(s.game)
        else:
            h.timer.hide()
            h.set_game(None)
            if problem:
                color, state, big, meta = C["neg"], tr("state.blocked"), problem[0], problem[1]
            elif svc.paused:
                color, state, big, meta = C["text2"], tr("state.paused"), tr("dash.paused.big"), ""
            elif svc.recorder.external:
                color, state, big, meta = C["text2"], tr("state.external"), tr("dash.external.big"), ""
            else:
                color, state, big, meta = C["ok"], tr("state.ready"), tr("dash.ready.big"), ""
        self._obs_action()
        self._stop_button(s)
        h.dot.set_color(color)
        _set(h.state, state, f"color: {color};")
        _set(h.big, big)
        _set(h.meta, meta)
        for i, (tile, (name, value, c, note)) in enumerate(zip(self.tiles, rows)):
            if i == 3:          # 유튜브: 오늘 올린 수는 이름 옆, 아래 줄은 지금 올리는 영상(게임 이름과 녹화 시각)
                cur = uploading_rec(svc.store) if svc.uploader.progress else None
                if cur is not None:
                    tile.set(name, value, c, cur.get("game") or cur.get("name", ""), side=note,
                             when=fmt_time(rec_time(cur)), progress=upload_progress(svc, cur))
                else:
                    tile.set(name, value, c, "", side=note)
            else:
                tile.set(name, value, c, note)

    def refresh(self):
        store = self.svc.store
        with store.lock:
            recs = sorted(store.data["recordings"].values(), key=lambda r: r.get("added_at", ""), reverse=True)[:self.fit]
        cur = uploading_rec(store)
        sig = [self.svc.uploader.rules_signature()] + [
            (r.get("path"), r.get("status"), r.get("cleaned_up"), r.get("processing_ok"), r is cur)
            for r in recs]
        if sig == self._sig:
            self.recent.update_progress()
            return
        self._sig = sig
        self.recent.fill(recs)
        self.recent.table.setVisible(bool(recs))
        self.empty.setVisible(not recs)
