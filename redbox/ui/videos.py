"""영상: 녹화한 영상을 목록 표(기본) 또는 날짜별 카드 격자로 보여 준다.
카드는 게임 그림, 업로드 상태 배지, 길이를 보여 주고, 누르면 영상(없으면 유튜브)을 연다."""
import datetime
import os

from PyQt6.QtCore import QObject, QRect, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QHBoxLayout, QMenu, QScrollArea, QStackedWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from .. import config
from ..i18n import tr
from . import icons
from .art import CARD_H, CARD_W
from .style import C
from .widgets import (IconButton, SearchBox, SmoothWheel, Tabs, fmt_day, fmt_len, fmt_time, label, open_target,
                      rec_len, rec_time, table)

GAP = 18
CARD_MIN_W = 250
TEXT_H = 58
LIST_ART_W, LIST_ART_H = 120, 56        # 스팀 대표 그림 비율(460x215)
ART_GAP = 14                             # 그림과 게임 이름 사이
ROW_H = LIST_ART_H + 18


def upload_state(r):
    """(문구, 색, 아이콘) 업로드 진행."""
    st = r.get("status")
    if st == "uploaded":
        return tr("up.st.done"), C["ok"], "youtube"          # 초록
    if st == "waiting":
        return tr("up.st.waiting"), C["accent"], "upload"
    if st in ("excluded", "auto_deleted"):
        return tr("up.st.skipped"), C["warn"], None          # 노랑
    return tr("step.none"), C["muted"], None


def has_original(r):
    """원본 파일이 PC 에 있는지. 정리됐거나 삭제된 기록은 파일을 확인하지 않는다(1초마다 수백 개를 확인하지 않게)."""
    if r.get("cleaned_up") or r.get("status") in ("auto_deleted", "missing"):
        return False
    return os.path.exists(r.get("path", ""))


def original_state(r, exists=None):
    """(문구, 색) 원본 파일이 지금 PC 에 있는지."""
    if has_original(r) if exists is None else exists:
        return tr("orig.kept"), C["accent"]
    st = r.get("status")
    if st == "uploaded":
        return tr("orig.cleaned"), C["muted"]
    if st == "auto_deleted":
        return tr("orig.deleted"), C["neg"]                  # 빨강(정리됨은 회색 그대로)
    return tr("orig.missing"), C["neg"] if st == "waiting" else C["muted"]


def record_menu(parent, r, pos):
    """카드와 목록 줄의 오른쪽 클릭 메뉴."""
    path, url = r.get("path", ""), r.get("url")
    exists = os.path.isfile(path)
    m = QMenu(parent)
    a = m.addAction(icons.icon("play", C["text2"], 16), tr("act.play"), lambda: os.startfile(path))
    a.setEnabled(exists)
    a = m.addAction(icons.icon("folder", C["text2"], 16), tr("act.folder"),
                    lambda: open_target(path if exists else os.path.dirname(path)))
    a.setEnabled(exists or os.path.isdir(os.path.dirname(path)))
    m.addSeparator()
    a = m.addAction(icons.icon("external", C["text2"], 16), tr("act.youtube"), lambda: open_target(url))
    a.setEnabled(bool(url))
    a = m.addAction(icons.icon("copy", C["text2"], 16), tr("act.copy"),
                    lambda: QGuiApplication.clipboard().setText(url or ""))
    a.setEnabled(bool(url))
    m.exec(pos)


def open_record(r, parent=None):
    """누르면: 원본이 있으면 재생, 없으면 유튜브. 둘 다 없으면 왜 없는지 알려 준다."""
    path = r.get("path", "")
    if os.path.isfile(path):
        os.startfile(path)
    elif r.get("url"):
        open_target(r["url"])
    elif parent is not None:          # 열 수 없는 영상: 왜 없는지 짧은 토스트로
        st = r.get("status")
        key = {"auto_deleted": "noopen.deleted", "excluded": "noopen.excluded"}.get(st, "noopen.missing")
        toast = getattr(parent.window(), "toast", None)
        if toast:
            toast.show_message(tr(key))


# -- 목록 표 ---------------------------------------------------------------------------------------
class RecordTable(QObject):
    """녹화 목록 표: 게임(작은 게임 그림), 녹화 시각, 길이, 업로드, 원본. 누르면 열기(카드와 같게), 오른쪽 클릭 메뉴.
    마우스를 올리면 그림 위에 재생(원본 없으면 유튜브) 표시와 테두리.
    녹화 화면과 대시보드(최근 영상)가 같이 쓴다."""

    def __init__(self, parent, art):
        super().__init__(parent)
        self.parent_widget, self.art = parent, art
        self.rows, self.icons = [], {}
        fm = parent.fontMetrics()

        def widest(keys, head):
            return max([fm.horizontalAdvance(tr(k)) for k in keys] + [fm.horizontalAdvance(tr(head))]) + 44
        t = self.table = table([tr("col.game"), tr("col.when"), tr("col.length"), tr("col.upload"), tr("col.original")], 0,
                               {1: fm.horizontalAdvance("2026-00-00 00:00") + 48, 2: fm.horizontalAdvance(fmt_len(36000 + 3599)) + 44,
                                3: widest(("up.st.waiting", "up.st.done", "up.st.skipped"), "col.upload"),
                                4: widest(("orig.kept", "orig.cleaned", "orig.deleted", "orig.missing"), "col.original")})
        t.setIconSize(QSize(LIST_ART_W + ART_GAP, LIST_ART_H))      # 게임 칸 앞의 작은 게임 그림(+ 여백)
        t.verticalHeader().setDefaultSectionSize(ROW_H)
        t.cellClicked.connect(lambda r, _c: self._rec(r) and open_record(self._rec(r), self.parent_widget))
        t.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        t._hover.overlay = self._overlay
        t.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        t.customContextMenuRequested.connect(self._menu)

    def _overlay(self, p, rect, row):
        """오버한 줄의 그림: 살짝 어둡게 + 가운데 재생(또는 유튜브) 표시 + 파란 테두리. 카드 보기와 같은 모양."""
        r = self._rec(row)
        if not r:
            return
        art = QRectF(rect.left(), rect.top() + (rect.height() - LIST_ART_H) / 2, LIST_ART_W, LIST_ART_H)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(art, QColor(0, 0, 0, 45))
        d = 26
        box = QRectF(art.center().x() - d / 2, art.center().y() - d / 2, d, d)
        p.fillRect(box, QColor(255, 255, 255, 235))
        playable = os.path.isfile(r.get("path", ""))
        name = "play" if playable else "external" if r.get("url") else "alert"
        icons.paint(p, name, box.adjusted(5 + (1 if playable else 0), 5, -5, -5), "#101114")
        p.setPen(QPen(QColor(C["accent"]), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(art.adjusted(1, 1, -1, -1))
        p.restore()

    def _rec(self, row):
        return self.rows[row] if 0 <= row < len(self.rows) else None

    def _menu(self, pos):
        r = self._rec(self.table.rowAt(pos.y()))
        if r:
            record_menu(self.parent_widget, r, self.table.viewport().mapToGlobal(pos))

    def _icon(self, game):
        key = (game or "").lower()
        if key not in self.icons:
            art = self.art.game_thumb(game, LIST_ART_W * 2, LIST_ART_H * 2)
            pm = QPixmap((LIST_ART_W + ART_GAP) * 2, LIST_ART_H * 2)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.drawPixmap(QRect(0, 0, LIST_ART_W * 2, LIST_ART_H * 2), art)   # 크기를 정해 그린다(그림의 배율과 상관없이)
            p.end()
            pm.setDevicePixelRatio(2.0)
            self.icons[key] = QIcon(pm)
        return self.icons[key]

    def fill(self, recs):
        t = self.table
        t.setRowCount(0)
        t.setRowCount(len(recs))
        self.rows = recs
        for i, r in enumerate(recs):
            up_txt, up_col, _ic = upload_state(r)
            og_txt, og_col = original_state(r)
            vals = [(r.get("game", ""), C["text"]), (fmt_time(rec_time(r)), C["text2"]),
                    (fmt_len(rec_len(r)), C["text2"]), (up_txt, up_col), (og_txt, og_col)]
            for c, (val, color) in enumerate(vals):
                it = QTableWidgetItem(str(val))
                it.setForeground(QColor(color))
                if c == 0:
                    it.setIcon(self._icon(r.get("game", "")))
                t.setItem(i, c, it)


# -- 카드 -----------------------------------------------------------------------------------------
class Card(QWidget):
    """녹화 하나. live 면 지금 녹화 중인 카드(빨간 테두리, 경과 시간)."""

    def __init__(self, art, key, rec=None, live=None):
        super().__init__()
        self.art, self.key, self.rec, self.live = art, key, rec, live
        self.orig = original_state(rec) if rec else None      # 그릴 때마다 파일을 확인하지 않게 만들 때 한 번
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setCursor(Qt.CursorShape.PointingHandCursor if rec else Qt.CursorShape.ArrowCursor)
        self._scaled = None

    def game(self):
        return (self.rec or {}).get("game") if self.rec else self.live.game

    def _image(self, w, h):
        if self._scaled is None or self._scaled.width() != int(w * self.devicePixelRatioF()):
            pm = self.art.record_image(self.game())
            ratio = self.devicePixelRatioF()
            s = pm.scaled(int(w * ratio), int(h * ratio), Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            s.setDevicePixelRatio(ratio)
            self._scaled = s
        return self._scaled

    @staticmethod
    def _chip(p, x, y, text, fg, bg, icon_name=None, icon_color=None, right=False):
        """작은 배지. right=True 면 x 가 오른쪽 끝."""
        fm = p.fontMetrics()
        iw = 16 if icon_name else 0
        w = fm.horizontalAdvance(text) + 14 + (iw + 5 if icon_name else 0)
        h = 22
        if right:
            x -= w
        p.fillRect(QRectF(x, y, w, h), bg)
        tx = x + 7
        if icon_name:
            icons.paint(p, icon_name, QRectF(tx, y + (h - iw) / 2, iw, iw), icon_color or fg, "#ffffff")
            tx += iw + 5
        p.setPen(fg)
        p.drawText(QRectF(tx, y, w, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w = self.width()
        th = round(w * CARD_H / CARD_W)
        hover = self.underMouse() and self.rec is not None
        p.drawPixmap(0, 0, self._image(w, th))
        small = QFont(self.font())
        small.setPixelSize(12)
        small.setWeight(QFont.Weight.DemiBold)
        p.setFont(small)
        dark = QColor(0, 0, 0, 190)
        if self.live:
            elapsed = datetime.datetime.now().timestamp() - self.live.start
            self._chip(p, 10, 10, tr("state.recording"), QColor("#ffffff"), QColor(C["rec"]))
            self._chip(p, w - 10, th - 32, fmt_len(elapsed), QColor("#ffffff"), dark, right=True)
            p.setPen(QPen(QColor(C["rec"]), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(1, 1, w - 2, th - 2))
        else:
            r = self.rec
            text, color, ic = upload_state(r)
            if ic == "youtube":
                self._chip(p, 10, 10, text, QColor("#ffffff"), dark, "youtube", "#ff4e45")
            elif ic == "upload":
                self._chip(p, 10, 10, text, QColor(C["accent"]), dark, "upload", C["accent"])
            else:
                self._chip(p, 10, 10, text, QColor(C["text2"]), dark)
            n = rec_len(r)
            if n:
                self._chip(p, w - 10, th - 32, fmt_len(n), QColor("#ffffff"), dark, right=True)
            if hover:
                p.fillRect(QRectF(0, 0, w, th), QColor(0, 0, 0, 70))
                d = 48
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 255, 255, 235))
                p.drawRect(QRectF((w - d) / 2, (th - d) / 2, d, d))
                icons.paint(p, "play" if os.path.isfile(r.get("path", "")) else "external" if r.get("url") else "alert",
                            QRectF((w - 24) / 2 + (2 if os.path.isfile(r.get("path", "")) else 0), (th - 24) / 2, 24, 24),
                            "#101114")
                p.setPen(QPen(QColor(C["accent"]), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(QRectF(1, 1, w - 2, th - 2))
        # 아래 글자: 게임 이름 / 시각과 원본 상태
        title = QFont(self.font())
        title.setPixelSize(14)
        title.setWeight(QFont.Weight.Bold)
        p.setFont(title)
        p.setPen(QColor(C["text"]))
        fm = QFontMetrics(title)
        p.drawText(QRectF(0, th + 8, w, 22), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   fm.elidedText(self.game() or "", Qt.TextElideMode.ElideRight, w))
        meta = QFont(self.font())
        meta.setPixelSize(12)
        p.setFont(meta)
        if self.live:
            left = tr("card.started").format(t=datetime.datetime.fromtimestamp(self.live.start).strftime("%H:%M"))
            right, rcolor = tr("orig.recording"), C["rec"]
        else:
            left = fmt_time(rec_time(self.rec))           # 녹화 시각(날짜까지). 길이와 헷갈리지 않게
            right, rcolor = self.orig
        p.setPen(QColor(C["muted"]))
        p.drawText(QRectF(0, th + 32, w, 18), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, left)
        p.setPen(QColor(rcolor))
        p.drawText(QRectF(0, th + 32, w, 18), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, right)
        p.end()

    def mouseReleaseEvent(self, e):
        if self.rec and e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            open_record(self.rec, self)
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e):
        if self.rec:
            record_menu(self, self.rec, e.globalPos())

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


class DayHead(QWidget):
    def __init__(self, title, sub):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(label(title, "dayhead"), 0, Qt.AlignmentFlag.AlignBottom)
        lay.addWidget(label(sub, "daysub"), 0, Qt.AlignmentFlag.AlignBottom)
        lay.addStretch(1)


class Grid(QWidget):
    """날짜 제목과 카드를 창 너비에 맞춰 줄 세운다(창을 넓히면 한 줄의 카드 수가 늘어남)."""

    def __init__(self):
        super().__init__()
        self.items = []          # [("head", 위젯) | ("card", 위젯)]

    def set_items(self, items):
        for _k, w in self.items:
            w.hide()
            w.deleteLater()
        self.items = items
        for _k, w in items:
            w.setParent(self)
            w.show()
        self.relayout()

    def relayout(self):
        w = max(self.width(), CARD_MIN_W)
        cols = max(1, (w + GAP) // (CARD_MIN_W + GAP))
        cw = (w - GAP * (cols - 1)) / cols
        ch = round(cw * CARD_H / CARD_W) + TEXT_H
        y, col = 0, 0
        for kind, wid in self.items:
            if kind == "head":
                if col:
                    y += ch + GAP
                    col = 0
                y += 8 if y else 0
                wid.setGeometry(0, y, int(w), 30)
                y += 30 + 12
            else:
                wid.setGeometry(round(col * (cw + GAP)), y, int(cw), ch)
                col += 1
                if col == cols:
                    col = 0
                    y += ch + GAP
        if col:
            y += ch + GAP
        self.setMinimumHeight(y + 8)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.relayout()


class Empty(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        ic = label("")
        ic.setPixmap(icons.pixmap("video", C["muted"], 44))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ic)
        lay.addSpacing(6)
        self.title = label("", "emptytitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.desc = label("", "muted")
        self.desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.title)
        lay.addWidget(self.desc)
        lay.addStretch(2)

    def set(self, title, desc):
        self.title.setText(title)
        self.desc.setText(desc)


# -- 영상 화면 ------------------------------------------------------------------------------------
class VideosPage(QWidget):
    count_changed = pyqtSignal(int)

    def __init__(self, svc, art):
        super().__init__()
        self.svc = svc
        self.cfg = svc.cfg
        self.filter = "all"
        self.query = ""
        self.view = self.cfg.setdefault("ui", {}).get("recordings_view", "list")
        self.art = art
        self._sig = None
        self.cards = {}
        self.live_card = None

        v = QVBoxLayout(self)
        v.setContentsMargins(32, 0, 32, 0)
        v.setSpacing(16)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.tabs = Tabs([("all", tr("lib.filter.all")), ("kept", tr("lib.filter.kept")),
                          ("waiting", tr("lib.filter.waiting")), ("skipped", tr("lib.filter.skipped"))], self.filter)
        self.tabs.changed.connect(self._set_filter)
        bar.addWidget(self.tabs, 1)
        self.search = SearchBox(tr("lib.search"))
        self.search.textChanged.connect(self._set_query)
        bar.addWidget(self.search)
        bar.addSpacing(4)
        self.grid_btn = IconButton("grid", tr("lib.view.grid"), checkable=True)
        self.list_btn = IconButton("list", tr("lib.view.list"), checkable=True)
        self.grid_btn.clicked.connect(lambda: self._set_view("grid"))
        self.list_btn.clicked.connect(lambda: self._set_view("list"))
        bar.addWidget(self.grid_btn)
        bar.addWidget(self.list_btn)
        v.addLayout(bar)

        self.stack = QStackedWidget()
        self.grid = Grid()
        self.grid_area = QScrollArea()
        self.grid_area.setWidgetResizable(True)
        self.grid_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grid_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        holder = QWidget()
        holder.setObjectName("root")
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 14, 24)
        hl.addWidget(self.grid)
        hl.addStretch(1)
        self.grid_area.setWidget(holder)
        self.grid_area._smooth = SmoothWheel(self.grid_area)
        self.stack.addWidget(self.grid_area)

        self.list = RecordTable(self, self.art)
        self.table = self.list.table
        tw = QWidget()
        tl = QVBoxLayout(tw)
        tl.setContentsMargins(0, 0, 0, 24)
        tl.addWidget(self.table)
        self.stack.addWidget(tw)
        self.empty = Empty()
        self.stack.addWidget(self.empty)
        v.addWidget(self.stack, 1)
        self._apply_view_buttons()

        self.tick = QTimer(self)              # 녹화 중 카드의 경과 시간
        self.tick.timeout.connect(lambda: self.live_card and self.live_card.update())
        self.tick.start(1000)

    # -- 조작 -------------------------------------------------------------------------------------
    def _set_filter(self, val):
        self.filter = val
        self._sig = None
        self.refresh()

    def _set_query(self, text):
        self.query = text.strip().lower()
        self._sig = None
        self.refresh()

    def _set_view(self, view):
        self.view = view
        self.cfg.setdefault("ui", {})["recordings_view"] = view
        config.save(self.cfg)
        self._apply_view_buttons()
        self._sig = None
        self.refresh()

    def _apply_view_buttons(self):
        self.grid_btn.setChecked(self.view == "grid")
        self.list_btn.setChecked(self.view == "list")

    # -- 갱신 -------------------------------------------------------------------------------------
    @staticmethod
    def _kind(r):
        st = r.get("status")
        if st == "uploaded" and has_original(r):
            return "kept"
        if st == "waiting":
            return "waiting"
        if st in ("excluded", "auto_deleted", "missing"):
            return "skipped"
        return ""

    def refresh(self):
        if self.grid_area._smooth.anim.running() or self.table._smooth.anim.running():
            return                      # 스크롤 중에는 다시 그리지 않는다(움직임이 끊기지 않게)
        store = self.svc.store
        with store.lock:
            allrecs = list(store.data["recordings"].items())
        allrecs.sort(key=lambda kv: kv[1].get("added_at", ""), reverse=True)
        live = self.svc.recorder.session
        counts = {"all": len(allrecs), "kept": 0, "waiting": 0, "skipped": 0}
        shown = []
        for k, r in allrecs:
            kind = self._kind(r)
            if kind:
                counts[kind] += 1
            if self.filter != "all" and kind != self.filter:
                continue
            if self.query and self.query not in (r.get("game") or "").lower():
                continue
            shown.append((k, r))
        show_live = live is not None and self.filter == "all" and (
            not self.query or self.query in (live.game or "").lower())
        sig = (self.filter, self.query, self.view, id(live) if show_live else None,
               [(k, r.get("status"), r.get("cleaned_up"), has_original(r)) for k, r in shown])
        if sig == self._sig:
            return
        self._sig = sig
        self.tabs.set_counts(counts)
        self.count_changed.emit(len(allrecs))
        if not shown and not show_live:
            if not allrecs:
                self.empty.set(tr("empty.title"), tr("empty.desc"))
            else:
                self.empty.set(tr("lib.empty"), tr("lib.empty.desc"))
            self.stack.setCurrentWidget(self.empty)
            self.cards, self.live_card = {}, None
            self.grid.set_items([])
            return
        if self.view == "list":
            self._fill_table([r for _k, r in shown])
            self.stack.setCurrentIndex(1)
            self.cards, self.live_card = {}, None
            self.grid.set_items([])
        else:
            self._fill_grid(shown, live if show_live else None)
            self.stack.setCurrentIndex(0)

    def _fill_grid(self, shown, live):
        items, self.cards, self.live_card = [], {}, None
        today = datetime.date.today()
        groups = []
        for k, r in shown:
            dt = rec_time(r)
            day = dt.date() if dt else None
            if not groups or groups[-1][0] != day:
                groups.append((day, []))
            groups[-1][1].append((k, r))
        if live and (not groups or groups[0][0] != today):
            groups.insert(0, (today, []))
        for day, recs in groups:
            total = sum(rec_len(r) for _k, r in recs)
            n = len(recs) + (1 if live and day == today else 0)
            one = ".one" if n == 1 else ""
            sub = (tr("lib.daysub" + one).format(n=n, t=fmt_len(total)) if total
                   else tr("lib.daysub" + (".one.n" if one else ".n")).format(n=n))
            items.append(("head", DayHead(fmt_day(day, today) if day else tr("day.unknown"), sub)))
            if live and day == today:
                self.live_card = Card(self.art, "", live=live)
                items.append(("card", self.live_card))
            for k, r in recs:
                c = Card(self.art, k, rec=r)
                self.cards[k] = c
                items.append(("card", c))
        self.grid.set_items(items)

    def _fill_table(self, recs):
        self.list.fill(recs)
