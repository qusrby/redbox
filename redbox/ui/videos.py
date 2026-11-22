"""영상: 녹화한 영상을 목록 표(기본) 또는 날짜별 카드 격자로 보여 준다.
카드는 게임 그림, 업로드 상태 배지, 길이를 보여 주고, 누르면 영상(없으면 유튜브)을 연다."""
import datetime
import os

from PyQt6.QtCore import QObject, QRect, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from .. import config, thumbs
from ..uploader.store import file_key
from ..i18n import tr
from . import icons
from .art import cover
from .style import C
from .widgets import (GAUGE, SUBICON, SUBTEXT, ElideLabel, IconButton, fmt_elapsed, tabular, SearchBox, SmoothWheel, Tabs, fmt_day, fmt_len, fmt_time, label, open_target,
                      rec_len, rec_time, table)

GAP = 18
CARD_MIN_W = 250
TEXT_H = 92                              # 카드 아래 글자 칸(파일 이름 두 줄 + 게임 이름 + 상태)
THUMB_RATIO = 9 / 16                     # 카드 그림(영상 썸네일) 비율
LIST_ART_W, LIST_ART_H = 110, 62        # 영상 썸네일(16:9, 길이 배지 포함). 없으면 게임 그림
ART_GAP = 14                             # 썸네일과 파일 이름 사이
ROW_H = 74
LIST_PORTRAIT = (14, 21)                 # 목록 둘째 줄 게임 이름 앞의 세로 표지(2:3)
CARD_PORTRAIT = (36, 54)                 # 카드 글자 칸 왼쪽의 세로 표지


def uploading_rec(store):
    """지금 올리고 있는 기록(저장소의 그 dict). 없으면 None."""
    info = store.data.get("in_progress")
    return store.data["recordings"].get(info.get("key")) if info else None


def upload_progress(svc, cur):
    """지금 올리는 기록의 진행률(0~1). 첫 조각을 올리기 전이면 0."""
    pr = svc.uploader.progress
    return pr[1] if pr and cur is not None and pr[0] == cur.get("name") else 0.0


def two_lines(fm, text, w):
    """글자를 w 너비에 두 줄까지 나눈다(넘치면 둘째 줄 끝을 줄임표로). 공백에서 끊고, 공백이 없으면 글자 단위로."""
    if fm.horizontalAdvance(text) <= w:
        return [text]
    words, first = text.split(" "), ""
    for i in range(len(words), 0, -1):
        cand = " ".join(words[:i])
        if fm.horizontalAdvance(cand) <= w:
            first, rest = cand, " ".join(words[i:])
            break
    else:
        n = len(text)
        while n > 1 and fm.horizontalAdvance(text[:n]) > w:
            n -= 1
        first, rest = text[:n], text[n:]
    return [first, fm.elidedText(rest, Qt.TextElideMode.ElideRight, int(w))]


def record_title(r):
    """영상 제목으로 보일 이름: 녹화본 파일 이름(확장자 빼고, 게임 이름과 시각이 들어 있다). 없으면 게임 이름."""
    return os.path.splitext(r.get("name") or os.path.basename(r.get("path") or ""))[0] or r.get("game", "")


def fmt_clock(sec):
    """썸네일 배지용 짧은 길이: 1:08:40, 42:12."""
    sec = int(sec)
    h, m, s = sec // 3600, sec // 60 % 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def has_original(r):
    """원본 파일이 PC 에 있는지. 정리됐거나 삭제된 기록은 파일을 확인하지 않는다(1초마다 수백 개를 확인하지 않게)."""
    if r.get("cleaned_up") or r.get("status") in ("auto_deleted", "missing"):
        return False
    return os.path.exists(r.get("path", ""))


def delete_date(r, up):
    """올리고 유튜브 처리까지 끝난 녹화본이 PC 에서 지워질 날(datetime.date). 지우지 않거나 모르면 None."""
    if up is None or r.get("status") != "uploaded" or not r.get("processing_ok"):
        return None
    if not up.up.get("delete_after_upload", True):
        return None
    try:
        at = datetime.datetime.fromisoformat((r.get("uploaded_at") or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if at.tzinfo:
        at = at.astimezone().replace(tzinfo=None)
    _mn, _dl, keep = up.rules_for(r.get("game"))
    when = at + datetime.timedelta(hours=keep)
    return when.date() if when > datetime.datetime.now() else None


def record_state(r, busy=False, progress=0.0, up=None, exists=None):
    """(문구, 색, 아이콘, 둘째 줄) 영상 하나의 상태. 업로드 단계와 녹화본 파일을 한 칸에 보인다.
    둘째 줄은 업로드가 끝났는데 녹화본이 아직 PC 에 남아 있을 때만(지울 예정이면 삭제 예정, 아니면 저장).
    busy 는 지금 올리고 있는 기록, up(업로더)을 주면 보관 기간 중인지 본다, exists 를 주면 파일을 다시 확인하지 않는다."""
    st = r.get("status")
    have = has_original(r) if exists is None else exists
    if st == "waiting":
        if busy:
            return f"{tr('up.st.busy')} {int(progress * 100)}%", C["accent"], "upload", None   # 파랑
        if not have:
            return tr("orig.missing"), C["neg"], None, None
        return tr("up.st.waiting"), C["text2"], None, None
    if st == "uploaded":
        if not r.get("processing_ok") and not r.get("cleaned_up"):
            return tr("up.st.processing"), C["accent"], "youtube", None
        sub = (tr("orig.until") if delete_date(r, up) else tr("orig.kept")) if have else None
        return tr("up.st.done"), C["ok"], "youtube", sub                                   # 초록
    if st == "excluded":
        if not have:
            return tr("orig.missing"), C["muted"], None, None
        return tr("up.st.skipped"), C["warn"], None, None                                  # 노랑
    if st == "auto_deleted":
        return tr("orig.user" if r.get("reason") == "user_deleted" else "orig.deleted"), C["neg"], None, None
    if st == "missing":
        return tr("orig.missing"), C["muted"], None, None
    return tr("step.none"), C["muted"], None, None


class RuleBar(QWidget):
    """바뀐 길이 규칙 경고와 확인 버튼(누르면 사유를 보여 주고 적용할지 묻는 대화 상자).
    목록 줄은 게임 이름 아래 줄에(name, left 를 준다), 카드는 그림 아래 끝에 띠로 붙는다.
    버튼 밖을 누르면 아래(줄, 카드)로 넘겨 평소처럼 영상이 열린다."""
    H = 26

    def __init__(self, svc, key, act, card=False, name=None, left=0):
        super().__init__()
        self.svc, self.key, self.card, self.act = svc, key, card, act
        h = QHBoxLayout()
        h.setSpacing(6)
        if card:
            self.setLayout(h)
            h.setContentsMargins(10, 0, 8, 0)
        else:                              # 표: 위에 게임 이름(칸 글자 대신), 아래에 경고와 버튼
            v = QVBoxLayout(self)
            v.setContentsMargins(left, 0, 12, 0)
            v.setSpacing(5)
            v.addStretch(1)
            v.addWidget(ElideLabel(name or "", "rulename"))
            v.addLayout(h)
            v.addStretch(1)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("warning", C["warn"], 14))
        h.addWidget(ic)
        text = ElideLabel(tr(f"rule.{act}"), "rulewarn")      # 좁으면 문구가 먼저 줄어든다(버튼은 그대로)
        text.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)   # 자리가 있으면 글자 길이만큼
        h.addWidget(text, 1 if card else 0)
        h.addSpacing(10)
        b = QPushButton(tr("rule.check"))
        b.setObjectName("rulebtn")
        b.setFixedHeight(self.H)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(self._open)
        h.addWidget(b)
        if not card:
            h.addStretch(1)
        self.setMouseTracking(True)

    def _open(self):
        from .dialogs import RuleDialog
        w = self.window()
        if RuleDialog(w, self.svc, self.key, self.act).exec() and hasattr(w, "refresh"):
            QTimer.singleShot(0, w.refresh)

    def paintEvent(self, _e):
        if self.card:
            p = QPainter(self)
            p.fillRect(self.rect(), QColor(0, 0, 0, 200))
            p.end()


def rule_bars_wanted(svc, r):
    """이 기록에 바뀐 규칙 경고를 붙일지: ('upload'|'exclude'|'delete') 또는 None."""
    try:
        return svc.uploader.rule_change(r)
    except Exception:
        return None


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
        self.busy_row, self.pct = -1, None       # 올리고 있는 줄, 마지막으로 쓴 진행률(%)
        fm = parent.fontMetrics()

        def widest(keys, head):
            return max([fm.horizontalAdvance(tr(k)) for k in keys] + [fm.horizontalAdvance(tr(head))]) + 44
        t = self.table = table([tr("col.video"), tr("col.when"), tr("col.status")], 0,
                               {1: fm.horizontalAdvance("2026-00-00 00:00") + 48,
                                2: max(widest(("up.st.waiting", "up.st.done", "up.st.processing", "up.st.skipped", "orig.deleted",
                                               "orig.user", "orig.missing", "orig.kept", "orig.until"), "col.status"),
                                       fm.horizontalAdvance(tr("up.st.busy") + " 100%") + 44)})
        t.setIconSize(QSize(LIST_ART_W + ART_GAP, LIST_ART_H))      # 칸 앞의 영상 썸네일(+ 여백)
        t.verticalHeader().setDefaultSectionSize(ROW_H)
        self.title_font = QFont(parent.font())
        self.title_font.setPixelSize(13)
        self.title_font.setWeight(QFont.Weight.Bold)
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

    def _icon(self, game, thumb, length):
        """줄 앞 그림: 영상 썸네일(없으면 게임 그림)과 오른쪽 아래 길이 배지."""
        key = ((game or "").lower(), thumb, length)
        if key not in self.icons:
            k = 2
            pm = QPixmap((LIST_ART_W + ART_GAP) * k, LIST_ART_H * k)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            shot = cover(QPixmap(thumb), LIST_ART_W * k, LIST_ART_H * k) if thumb else None
            if shot is None:
                shot = self.art.game_thumb(game, LIST_ART_W * k, LIST_ART_H * k)
            p.drawPixmap(QRect(0, 0, LIST_ART_W * k, LIST_ART_H * k), shot)   # 크기를 정해 그린다(그림의 배율과 상관없이)
            if length:
                f = QFont(self.parent_widget.font())
                f.setPixelSize(11 * k)
                f.setWeight(QFont.Weight.DemiBold)
                p.setFont(tabular(f))
                w = p.fontMetrics().horizontalAdvance(length) + 10 * k
                h = 17 * k
                box = QRectF(LIST_ART_W * k - 4 * k - w, LIST_ART_H * k - 4 * k - h, w, h)
                p.fillRect(box, QColor(0, 0, 0, 200))
                p.setPen(QColor("#ffffff"))
                p.drawText(box, Qt.AlignmentFlag.AlignCenter, length)
            p.end()
            pm.setDevicePixelRatio(k)
            self.icons[key] = QIcon(pm)
        return self.icons[key]

    def _portrait(self, game):
        key = ("portrait", (game or "").lower())
        if key not in self.icons:
            w, h = LIST_PORTRAIT
            pm = self.art.game_portrait(game, w * 2, h * 2).copy()
            pm.setDevicePixelRatio(2)
            self.icons[key] = pm
        return self.icons[key]

    def fill(self, recs):
        t = self.table
        t.setRowCount(0)
        t.setRowCount(len(recs))
        self.rows = recs
        svc = self.parent_widget.svc
        cur = uploading_rec(svc.store)
        self.busy_row, self.pct = -1, None
        for i, r in enumerate(recs):
            if r is cur:
                self.busy_row = i
            st_txt, st_col, _ic, st_sub = record_state(r, r is cur, upload_progress(svc, cur), svc.uploader)
            game = r.get("game", "")
            vals = [(record_title(r), C["text"]), (fmt_time(rec_time(r)), C["text2"]), (st_txt, st_col)]
            for c, (val, color) in enumerate(vals):
                it = QTableWidgetItem(str(val))
                it.setForeground(QColor(color))
                if c == 0:             # 썸네일(길이 배지) / 파일 이름 / 세로 표지와 게임 이름
                    n = rec_len(r)
                    it.setIcon(self._icon(game, thumbs.find(r.get("path")), fmt_clock(n) if n else ""))
                    it.setFont(self.title_font)
                    it.setData(SUBTEXT, game)
                    it.setData(SUBICON, self._portrait(game))
                if c == 2 and st_sub:
                    it.setData(SUBTEXT, st_sub)
                t.setItem(i, c, it)
            act = rule_bars_wanted(svc, r)
            if act:
                t.item(i, 0).setForeground(QColor(0, 0, 0, 0))        # 이름은 경고 위에 다시 쓴다
                t.setCellWidget(i, 0, RuleBar(svc, file_key(r.get("path", "")), act,
                                              name=record_title(r), left=self._text_left(i)))
        self.update_progress()

    def _text_left(self, row):
        """게임 칸에서 글자가 시작하는 x(그림 뒤). 경고 줄을 게임 이름과 같은 자리에 맞춘다."""
        from PyQt6.QtWidgets import QStyle, QStyleOptionViewItem
        t = self.table
        idx = t.model().index(row, 0)
        opt = QStyleOptionViewItem()
        t.itemDelegate().initStyleOption(opt, idx)
        opt.rect = t.visualRect(idx)
        opt.widget = t
        r = t.style().subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, t)
        return max(0, r.left() - opt.rect.left() - 9)      # 9: 칸 글자가 실제로 그려지는 자리와 맞춤(Fusion 글자 여백)

    def update_progress(self):
        """올리고 있는 줄의 글자와 게이지만 고친다(표 전체를 다시 채우지 않고 1초마다)."""
        it = self.table.item(self.busy_row, 2) if self.busy_row >= 0 else None
        if it is None:
            return
        svc = self.parent_widget.svc
        p = upload_progress(svc, uploading_rec(svc.store))
        pct = int(p * 100)
        if pct != self.pct:
            self.pct = pct
            it.setText(f"{tr('up.st.busy')} {pct}%")
            it.setData(GAUGE, p)


# -- 카드 -----------------------------------------------------------------------------------------
class Card(QWidget):
    """녹화 하나. live 면 지금 녹화 중인 카드(빨간 테두리, 경과 시간)."""

    def __init__(self, art, key, rec=None, live=None, busy=False, svc=None):
        super().__init__()
        self.art, self.key, self.rec, self.live, self.busy = art, key, rec, live, busy
        act = rule_bars_wanted(svc, rec) if svc is not None and rec else None
        self.rule = RuleBar(svc, key, act, card=True) if act else None
        if self.rule:
            self.rule.setParent(self)
        self.progress = 0.0
        self.up = svc.uploader if svc is not None else None
        self.exists = has_original(rec) if rec else False     # 그릴 때마다 파일을 확인하지 않게 만들 때 한 번
        self.thumb = thumbs.find(rec.get("path")) if rec else None
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setCursor(Qt.CursorShape.PointingHandCursor if rec else Qt.CursorShape.ArrowCursor)
        self._scaled = None

    def game(self):
        return (self.rec or {}).get("game") if self.rec else self.live.game

    def _shot(self):
        """큰 그림으로 쓸 영상 장면 파일: 녹화 중이면 가장 최근 장면, 아니면 녹화본 썸네일. 없으면 None."""
        if self.live:
            return thumbs.latest_live()
        return self.thumb

    def _image(self, w, h):
        ratio = self.devicePixelRatioF()
        src = self._shot()
        key = (int(w * ratio), src, os.path.getmtime(src) if src and os.path.exists(src) else 0)
        if self._scaled is None or self._scaled[0] != key:
            pm = cover(QPixmap(src), int(w * ratio), int(h * ratio)) if src else None
            if pm is None:
                pm = cover(self.art.record_image(self.game()), int(w * ratio), int(h * ratio))
                src = None
            pm.setDevicePixelRatio(ratio)
            self._scaled = (key, pm)
        return self._scaled[1]

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
        th = round(w * THUMB_RATIO)
        hover = self.underMouse() and self.rec is not None
        p.drawPixmap(0, 0, self._image(w, th))
        small = QFont(self.font())
        small.setPixelSize(12)
        small.setWeight(QFont.Weight.DemiBold)
        p.setFont(tabular(small))
        dark = QColor(0, 0, 0, 190)
        if self.live:
            elapsed = datetime.datetime.now().timestamp() - self.live.start
            self._chip(p, 10, 10, tr("state.recording"), QColor("#ffffff"), QColor(C["rec"]))
            self._chip(p, w - 10, th - 32, fmt_elapsed(elapsed), QColor("#ffffff"), dark, right=True)
            p.setPen(QPen(QColor(C["rec"]), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(1, 1, w - 2, th - 2))
        else:
            r = self.rec
            n = rec_len(r)
            if n:
                bar = self.rule.height() if self.rule else 0          # 경고 띠가 있으면 그 위에
                self._chip(p, w - 10, th - 32 - bar, fmt_clock(n), QColor("#ffffff"), dark, right=True)
            if self.busy:                  # 그림 아래 끝에 업로드 게이지
                p.fillRect(QRectF(0, th - 4, w, 4), QColor(0, 0, 0, 160))
                p.fillRect(QRectF(0, th - 4, w * max(0.0, min(1.0, self.progress)), 4), QColor(C["accent"]))
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
        # 아래: 왼쪽에 세로 표지, 오른쪽에 파일 이름(두 줄까지, 녹화 중이면 게임 이름) / 게임 이름 / 상태
        pw, ph = CARD_PORTRAIT
        p.drawPixmap(QRectF(0, th + 10, pw, ph), self.art.game_portrait(self.game(), pw * 2, ph * 2), QRectF(0, 0, pw * 2, ph * 2))
        x = pw + 10
        tw = w - x
        title = QFont(self.font())
        title.setPixelSize(13)
        title.setWeight(QFont.Weight.Bold)
        p.setFont(title)
        p.setPen(QColor(C["text"]))
        fm = QFontMetrics(title)
        name = record_title(self.rec) if self.rec else (self.game() or "")
        lh = fm.lineSpacing()
        for i, line in enumerate(two_lines(fm, name, tw)):
            p.drawText(QRectF(x, th + 8 + i * lh, tw, lh), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, line)
        y = th + 8 + 2 * lh + 4
        meta = QFont(self.font())
        meta.setPixelSize(12)
        p.setFont(meta)
        mfm = QFontMetrics(meta)
        left = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        if self.live:
            second = tr("card.started").format(t=fmt_time(datetime.datetime.fromtimestamp(self.live.start)))
            state, scolor, sub = tr("orig.recording"), C["rec"], ""
        else:
            second = self.game() or ""
            state, scolor, _ic, sub = record_state(self.rec, self.busy, self.progress, self.up, self.exists)
        p.setPen(QColor(C["muted"]))
        p.drawText(QRectF(x, y, tw, 18), left, mfm.elidedText(second, Qt.TextElideMode.ElideRight, int(tw)))
        y += 18
        p.setPen(QColor(scolor))
        p.drawText(QRectF(x, y, tw, 18), left, state)
        if sub:
            sx = x + mfm.horizontalAdvance(state) + 10
            p.setPen(QColor(C["muted"]))
            p.drawText(QRectF(sx, y, max(0, w - sx), 18), left,
                       mfm.elidedText(sub, Qt.TextElideMode.ElideRight, int(max(0, w - sx))))
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

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.rule:
            th = round(self.width() * THUMB_RATIO)
            h = RuleBar.H + 10
            self.rule.setGeometry(0, th - h, self.width(), h)


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
        ch = round(cw * THUMB_RATIO) + TEXT_H
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
        self.tabs = Tabs([("all", tr("lib.filter.all")), ("waiting", tr("lib.filter.waiting")),
                          ("skipped", tr("lib.filter.skipped"))], self.filter)
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
        hl.setContentsMargins(0, 0, 14, 0)
        hl.addWidget(self.grid)
        hl.addStretch(1)
        self.grid_area.setWidget(holder)
        self.grid_area._smooth = SmoothWheel(self.grid_area)
        self.stack.addWidget(self.grid_area)

        self.list = RecordTable(self, self.art)
        self.table = self.list.table
        tw = QWidget()
        tl = QVBoxLayout(tw)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(self.table)
        self.stack.addWidget(tw)
        self.empty = Empty()
        self.stack.addWidget(self.empty)
        v.addWidget(self.stack, 1)
        self._apply_view_buttons()

        self.tick = QTimer(self)              # 녹화 중 카드의 경과 시간
        self.tick.timeout.connect(self._tick)
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
        if st == "waiting":
            return "waiting"
        if st in ("excluded", "auto_deleted", "missing"):
            return "skipped"
        return ""

    def _tick(self):
        """1초마다: 녹화 중 카드의 경과 시간, 업로드 중 영상의 진행률."""
        if self.live_card:
            self.live_card.update()
        cur = uploading_rec(self.svc.store)
        p = upload_progress(self.svc, cur)
        for c in self.cards.values():
            if c.busy and c.progress != p:
                c.progress = p
                c.update()
        self.list.update_progress()

    def refresh(self):
        if self.grid_area._smooth.anim.running() or self.table._smooth.anim.running():
            return                      # 스크롤 중에는 다시 그리지 않는다(움직임이 끊기지 않게)
        store = self.svc.store
        with store.lock:
            allrecs = list(store.data["recordings"].items())
        allrecs.sort(key=lambda kv: kv[1].get("added_at", ""), reverse=True)
        live = self.svc.recorder.session
        counts = {"all": len(allrecs), "waiting": 0, "skipped": 0}
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
        cur = uploading_rec(store)
        sig = (self.filter, self.query, self.view, id(live) if show_live else None, id(cur) if cur else None,
               self.svc.uploader.rules_signature(),
               [(k, r.get("status"), r.get("cleaned_up"), r.get("processing_ok"), has_original(r))
                for k, r in shown])
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
        cur = uploading_rec(self.svc.store)
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
                c = Card(self.art, k, rec=r, busy=r is cur, svc=self.svc)
                if c.busy:
                    c.progress = upload_progress(self.svc, cur)
                self.cards[k] = c
                items.append(("card", c))
        self.grid.set_items(items)

    def _fill_table(self, recs):
        self.list.fill(recs)
