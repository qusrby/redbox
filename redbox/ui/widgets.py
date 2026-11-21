"""여러 화면이 같이 쓰는 작은 부품: 글자, 부드러운 스크롤, 표, 버튼 묶음, 체크, 토글, 드롭다운, 설정 줄."""
import datetime
import os
import re
import subprocess

from PyQt6.QtCore import QElapsedTimer, QEvent, QObject, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QAbstractButton, QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QFrame,
                             QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListView, QPushButton, QSpinBox,
                             QTableWidget, QVBoxLayout, QWidget)

from ..i18n import lang, tr
from . import icons
from .style import C

ROW_H = 40
GAUGE = Qt.ItemDataRole.UserRole + 1     # 표 칸의 진행률(0~1). 있으면 글자 아래에 게이지를 그린다
CONTROL_H = 34        # 버튼, 드롭다운, 숫자 칸, 검색 칸, 버튼 묶음의 높이(어디서나 같게)
SETTING_ROW_H = 66    # 설정 한 줄의 높이(설명이 있든 없든 같게)


class Dot(QWidget):
    """상태 점(동그라미). 색만 바뀔 때 다시 그린다."""

    def __init__(self, size=8):
        super().__init__()
        self.setFixedSize(size, size)
        self._color = None

    def set_color(self, color):
        if color != self._color:
            self._color = color
            self.update()

    def paintEvent(self, _e):
        if not self._color:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self._color))
        p.drawEllipse(QRectF(self.rect()))
        p.end()


# -- 글자 모양 -------------------------------------------------------------------------------------
def fmt_len(sec):
    """길이: 1분 25초, 2시간 1분 2초(영어 1m 25s, 2h 1m 2s). 0 인 단위는 빼되 초만 있으면 초."""
    sec = int(sec or 0)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    parts = [tr("time.h").format(v=h) if h else "", tr("time.m").format(v=m) if m else "",
             tr("time.s").format(v=s) if s or not (h or m) else ""]
    return " ".join(p for p in parts if p)


def fmt_uptime(sec):
    """가동 시간: 하루가 넘으면 '3일 9시간', 아니면 '1:02:05'."""
    sec = int(sec or 0)
    d, rem = divmod(sec, 86400)
    if d:
        return tr("time.dh").format(d=d, h=rem // 3600)
    return fmt_len(sec)


def rec_len(r):
    """기록의 길이(초). 없으면 파일 이름의 길이 표시(12m34s)에서 읽는다."""
    if r.get("duration"):
        return r["duration"]
    m = re.search(r"(\d+)m(\d+)s", r.get("name") or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else 0


def rec_time(r):
    try:
        return datetime.datetime.fromisoformat(r.get("added_at") or "")
    except (TypeError, ValueError):
        return None


def fmt_time(dt, with_date=True):
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M") if with_date else dt.strftime("%H:%M")


_WD_KO = "월화수목금토일"


def fmt_day(d, today=None):
    """날짜 묶음 제목: 오늘, 어제, 11월 15일 토요일(올해가 아니면 연도까지)."""
    today = today or datetime.date.today()
    if d == today:
        return tr("day.today")
    if d == today - datetime.timedelta(days=1):
        return tr("day.yesterday")
    if lang() == "ko":
        s = f"{d.month}월 {d.day}일 {_WD_KO[d.weekday()]}요일"
        return s if d.year == today.year else f"{d.year}년 {s}"
    s = d.strftime("%A, %B ") + str(d.day)
    return s if d.year == today.year else f"{s}, {d.year}"


def open_target(target):
    """파일이면 탐색기에서 선택, 폴더면 열기, 주소면 브라우저."""
    if not target:
        return
    if target.startswith("http"):
        os.startfile(target)
    elif os.path.isfile(target):
        subprocess.Popen(f'explorer /select,"{target}"')
    elif os.path.isdir(target):
        os.startfile(target)


def label(text, name=None, wrap=False):
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(wrap)
    return lb


class ElideLabel(QLabel):
    """칸보다 긴 글자는 끝을 '…'로 줄여 보여 준다(전체는 풍선 도움말)."""

    def __init__(self, text, name=None):
        super().__init__(text)
        if name:
            self.setObjectName(name)
        self.setToolTip(text)
        self.setMinimumWidth(1)
        from PyQt6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setFont(self.font())
        p.setPen(self.palette().color(self.foregroundRole()))
        text = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, self.width())
        p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), text)
        p.end()


def hline():
    f = QFrame()
    f.setObjectName("hline")
    f.setFixedHeight(1)
    return f


# -- 스크롤 ---------------------------------------------------------------------------------------
class Tween(QObject):
    """값을 화면 주사율(144Hz 등)에 맞춰 부드럽게 옮긴다. 끝으로 갈수록 느려지는 곡선(OutCubic).
    Qt 기본 애니메이션은 60프레임으로 고정이라 고주사율 모니터에서 끊겨 보여서 직접 돌린다."""

    def __init__(self, parent, setter, duration=240):
        super().__init__(parent)
        self.setter, self.duration = setter, duration
        self.a = self.b = 0.0
        self.clock = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._step)

    @staticmethod
    def frame_ms():
        screen = QGuiApplication.primaryScreen()
        hz = screen.refreshRate() if screen is not None else 60
        return max(4, int(1000 / (hz if hz and hz > 1 else 60)))

    def running(self):
        return self.timer.isActive()

    def start(self, a, b):
        self.a, self.b = float(a), float(b)
        self.clock.start()
        self.timer.start(self.frame_ms())
        self._step()

    def _step(self):
        t = min(1.0, self.clock.elapsed() / self.duration)
        e = 1 - (1 - t) ** 3
        self.setter(self.a + (self.b - self.a) * e)
        if t >= 1.0:
            self.timer.stop()


class SmoothWheel(QObject):
    """마우스 휠 스크롤을 부드럽게: 한 칸씩 끊어 넘기지 않고 짧게 미끄러지듯 움직인다."""
    STEP = 110

    def __init__(self, area):
        super().__init__(area)
        self.bar = area.verticalScrollBar()
        self.anim = Tween(self, lambda v: self.bar.setValue(round(v)), 260)
        self.goal = None
        area.viewport().installEventFilter(self)
        self.bar.rangeChanged.connect(self._range)     # 넘칠 내용이 없으면 손잡이를 숨긴다(자리는 그대로)
        self._range(self.bar.minimum(), self.bar.maximum())

    def _range(self, lo, hi):
        empty = hi <= lo
        if self.bar.property("empty") != empty:
            self.bar.setProperty("empty", empty)
            self.bar.style().unpolish(self.bar)
            self.bar.style().polish(self.bar)
            self.bar.update()

    def eventFilter(self, _obj, ev):
        if ev.type() != QEvent.Type.Wheel or ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return False
        dy = ev.angleDelta().y()
        if not dy:
            return False
        base = self.goal if self.anim.running() and self.goal is not None else self.bar.value()
        self.goal = max(self.bar.minimum(), min(self.bar.maximum(), int(base - dy / 120 * self.STEP)))
        self.anim.start(self.bar.value(), self.goal)
        return True


class RowHover(QObject):
    """표에서 마우스가 올라간 줄 전체를 밝게(칸 하나만이 아니라). 줄을 고르는(선택) 상태는 두지 않는다."""

    def __init__(self, t):
        super().__init__(t)
        self.t = t
        self.row = -1
        t.viewport().installEventFilter(self)
        t.verticalScrollBar().valueChanged.connect(lambda _v: self._update_from_cursor())
        self.overlay = None      # (painter, 첫 칸 그림 자리, 줄) -> 오버한 줄의 그림 위에 덧그리기(영상 목록의 재생 표시)
        from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

        hover = self

        class Delegate(QStyledItemDelegate):
            def paint(self, p, opt, idx):
                if idx.row() == hover.row:
                    p.fillRect(opt.rect, QColor(C["row_hover"]))
                super().paint(p, opt, idx)
                g = idx.data(GAUGE)
                if g is not None:
                    r = QRectF(opt.rect).adjusted(12, 0, -16, 0)
                    bar = QRectF(r.left(), r.center().y() + 15, r.width(), 3)
                    p.fillRect(bar, QColor(C["border"]))
                    p.fillRect(QRectF(bar.left(), bar.top(), bar.width() * max(0.0, min(1.0, g)), bar.height()),
                               QColor(C["accent"]))
                if idx.row() == hover.row and idx.column() == 0 and hover.overlay:
                    o = QStyleOptionViewItem(opt)
                    self.initStyleOption(o, idx)
                    style = o.widget.style() if o.widget else QApplication.style()
                    r = style.subElementRect(QStyle.SubElement.SE_ItemViewItemDecoration, o, o.widget)
                    hover.overlay(p, r, idx.row())
        self.delegate = Delegate(t)
        t.setItemDelegate(self.delegate)

    def _set(self, row):
        if row != self.row:
            self.row = row
            self.t.viewport().update()

    def _update_from_cursor(self):
        from PyQt6.QtGui import QCursor
        pos = self.t.viewport().mapFromGlobal(QCursor.pos())
        self._set(self.t.rowAt(pos.y()) if self.t.viewport().rect().contains(pos) else -1)

    def eventFilter(self, _obj, ev):
        if ev.type() == QEvent.Type.MouseMove:
            self._set(self.t.rowAt(int(ev.position().y())))
        elif ev.type() == QEvent.Type.Leave:
            self._set(-1)
        return False


def table(headers, stretch_col=0, widths=None):
    """목록 표. widths: {칸 번호: 너비} 를 주면 그 칸은 내용과 상관없이 너비 고정(필터를 바꿔도 칸이 움직이지 않게)."""
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setShowGrid(False)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    t.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    t.setMouseTracking(True)
    t.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    t.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)   # 목록 길이와 상관없이 칸 위치 고정
    h = t.horizontalHeader()
    h.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    h.setSectionResizeMode(stretch_col, QHeaderView.ResizeMode.Stretch)
    for col, w in (widths or {}).items():
        h.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
        t.setColumnWidth(col, w)
    h.setHighlightSections(False)
    h.setFixedHeight(36)
    t.verticalHeader().setDefaultSectionSize(ROW_H)
    t._smooth = SmoothWheel(t)
    t._hover = RowHover(t)
    return t


# -- 버튼 -----------------------------------------------------------------------------------------
def button(text, fn=None, primary=False, icon_name=None):
    b = QPushButton(text)
    b.setFixedHeight(CONTROL_H)
    if primary:
        b.setObjectName("primary")
    if icon_name:
        b.setIcon(icons.icon(icon_name, C["on_accent"] if primary else C["text2"], 16))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if fn:
        b.clicked.connect(fn)
    return b


class IconButton(QAbstractButton):
    """아이콘만 있는 작은 버튼(보기 전환, 더 보기). 선택 = 파란 아이콘 + 밝은 바탕, 오버 = 바탕만 살짝."""

    def __init__(self, name, tip="", size=34, checkable=False):
        super().__init__()
        self.name = name
        self.setToolTip(tip)
        self.setCheckable(checkable)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self._pm = {}

    def _pix(self, color):
        if color not in self._pm:
            self._pm[color] = icons.pixmap(self.name, color, 18)
        return self._pm[color]

    def paintEvent(self, _e):
        p = QPainter(self)
        on, hover = self.isChecked(), self.underMouse()
        if self.isDown():
            p.fillRect(self.rect(), QColor(C["bg"]))
        elif on:
            p.fillRect(self.rect(), QColor(C["surface3"]))
        elif hover:
            p.fillRect(self.rect(), QColor(C["surface2"]))
        color = C["accent"] if on else C["text"] if hover else C["text2"]
        pm = self._pix(color)
        p.drawPixmap((self.width() - 18) // 2, (self.height() - 18) // 2, pm)
        p.end()

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


def segmented(options, current, on_change, stretch=True):
    """버튼 묶음(둘셋 중 하나 고르기). options: [(값, 문구)]"""
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    group = QButtonGroup(box)
    for val, text in options:
        b = QPushButton(text)
        b.setObjectName("seg")
        b.setFixedHeight(CONTROL_H)
        b.setCheckable(True)
        b.setChecked(val == current)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.ensurePolished()     # 굵은 글씨(선택)까지 들어가게 굵은 글씨 기준으로 잰다
        bold = b.font()
        bold.setBold(True)
        b.setMinimumWidth(QFontMetrics(bold).horizontalAdvance(text) + 32)
        b.clicked.connect(lambda _c, v=val: on_change(v))
        group.addButton(b)
        lay.addWidget(b)
    if stretch:
        lay.addStretch(1)
    return box


class Tabs(QWidget):
    """밑줄 탭(필터). 탭마다 개수를 함께 보여 준다. 선택 = 흰 글자 + 파란 밑줄, 오버 = 글자만 밝게."""
    changed = pyqtSignal(str)

    def __init__(self, options, current):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.group = QButtonGroup(self)
        self.buttons = {}
        for val, text in options:
            b = QPushButton(text)
            b.setObjectName("tab")
            b.setCheckable(True)
            b.setChecked(val == current)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c, v=val: self.changed.emit(v))
            b._base = text
            self.group.addButton(b)
            self.buttons[val] = b
            lay.addWidget(b)
        lay.addStretch(1)

    def set_counts(self, counts):
        for val, b in self.buttons.items():
            n = counts.get(val)
            b.setText(b._base if n is None else f"{b._base}  {n}")
            b.ensurePolished()
            bold = b.font()
            bold.setBold(True)
            b.setMinimumWidth(QFontMetrics(bold).horizontalAdvance(b.text()) + 28)


class SearchBox(QLineEdit):
    def __init__(self, placeholder, width=240):
        super().__init__()
        self.setObjectName("search")
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.setFixedHeight(CONTROL_H)
        self.addAction(icons.icon("search", C["muted"], 16), QLineEdit.ActionPosition.LeadingPosition)
        self.setFixedWidth(width)


# -- 체크, 토글, 드롭다운, 숫자 ------------------------------------------------------------------------
class Check(QCheckBox):
    """체크 표시가 그려지는 체크박스(네모 색만 바뀌는 기본 모양 대신)."""
    BOX = 18

    def __init__(self, text=""):
        super().__init__(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def sizeHint(self):
        fm = self.fontMetrics()
        w = self.BOX + (10 + fm.horizontalAdvance(self.text()) if self.text() else 0)
        return QSize(w + 2, max(self.BOX, fm.height()) + 4)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = (self.height() - self.BOX) / 2
        r = QRectF(0.5, y + 0.5, self.BOX - 1, self.BOX - 1)
        on = self.isChecked()
        enabled = self.isEnabled()
        if on:
            p.fillRect(r, QColor(C["accent"] if enabled else C["border2"]))
            pen = QPen(QColor(C["on_accent"]), 2.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            path = QPainterPath()
            path.moveTo(r.left() + 4, r.center().y() + 0.5)
            path.lineTo(r.left() + 7.5, r.bottom() - 4.5)
            path.lineTo(r.right() - 3.5, r.top() + 4.5)
            p.drawPath(path)
        else:
            p.fillRect(r, QColor(C["surface2"]))
            p.setPen(QPen(QColor(C["accent"] if self.underMouse() and enabled else C["check_border"] if enabled else C["border2"]), 1))
            p.drawRect(r)
        if self.text():
            p.setPen(QColor(C["text"] if enabled else C["muted"]))
            p.drawText(QRectF(self.BOX + 10, 0, self.width() - self.BOX - 10, self.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
        p.end()


class _ToastItem(QLabel):
    """토스트 한 개: 아래에서 살짝 올라오며 나타나고, 시간이 지나거나 새 토스트가 뜨면 흐려지며 사라진다."""
    SHOW_MS, HOLD_MS, HIDE_MS, QUICK_MS, RISE = 180, 2400, 240, 90, 8

    def __init__(self, parent, text, delay=0):
        super().__init__(text, parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        self.fx = QGraphicsOpacityEffect(self)
        self.fx.setOpacity(0.0)
        self.setGraphicsEffect(self.fx)
        self.adjustSize()
        self.anim = Tween(self, self._step, self.SHOW_MS)
        self.hold = QTimer(self)
        self.hold.setSingleShot(True)
        self.hold.timeout.connect(lambda: self.leave(self.HIDE_MS))
        self._dir = 1
        self._from = 1.0
        x, y = self._base()
        self.move(x, y + self.RISE)
        if delay:
            QTimer.singleShot(delay, self._appear)
        else:
            self._appear()

    def _appear(self):
        self.show()
        self.raise_()
        self.anim.start(0, 1)
        self.hold.start(self.SHOW_MS + self.HOLD_MS)

    def _base(self):
        par = self.parentWidget()
        return (par.width() - self.width()) // 2, par.height() - self.height() - 36

    def _step(self, t):
        x, y = self._base()
        if self._dir > 0:                 # 나타나기: 아래에서 올라오며 진해진다
            self.fx.setOpacity(t)
            self.move(x, int(y + self.RISE * (1 - t)))
        else:                             # 사라지기: 제자리에서 흐려진다
            self.fx.setOpacity(self._from * (1 - t))
            if t >= 1:
                self.hide()
                self.deleteLater()

    def leave(self, ms):
        if self._dir < 0:
            return
        self.hold.stop()
        self._dir, self._from = -1, self.fx.opacity()
        self.anim.duration = ms
        self.anim.start(0, 1)


class Toast(QObject):
    """창 아래 가운데의 토스트. 띄울 때마다 새로 뜨고, 떠 있던 것은 바로 흐려지며 사라진다."""

    def __init__(self, parent):
        super().__init__(parent)
        self.host = parent
        self.current = None

    def show_message(self, text):
        delay = 0
        if self.current is not None:
            try:
                if self.current.isVisible():
                    self.current.leave(_ToastItem.QUICK_MS)
                    delay = _ToastItem.QUICK_MS
            except RuntimeError:          # 이미 사라진 것
                pass
        self.current = _ToastItem(self.host, text, delay)


class Combo(QComboBox):
    """드롭다운. 오른쪽 꺾쇠를 직접 그린다(기본 모양은 그림 파일이 있어야 바꿀 수 있어서).
    마우스 휠로는 바뀌지 않는다(스크롤하다 실수로 바뀌지 않게)."""

    def wheelEvent(self, e):
        e.ignore()

    def __init__(self, options, current=None, width=None):
        super().__init__()
        self.setView(QListView())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        for val, text in options:
            self.addItem(text, val)
        i = self.findData(current)
        if i >= 0:
            self.setCurrentIndex(i)
        self.setFixedHeight(CONTROL_H)
        if width:
            self.setFixedWidth(width)
        else:
            self.ensurePolished()
            fm = self.fontMetrics()
            self.setMinimumWidth(max(fm.horizontalAdvance(t) for _v, t in options) + 52)

    def value(self):
        return self.currentData()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        enabled, hover = self.isEnabled(), self.underMouse() or self.view().isVisible()
        p.fillRect(r, QColor(C["surface2"] if enabled else C["bg"]))
        p.setPen(QPen(QColor(C["accent"] if hover and enabled else C["border2"] if enabled else C["border"]), 1))
        p.drawRect(r)
        p.setPen(QColor(C["text"] if enabled else C["muted"]))
        p.drawText(QRectF(12, 0, self.width() - 40, self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.currentText())
        pen = QPen(QColor(C["text2"] if enabled else C["muted"]), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        cx, cy = self.width() - 18, self.height() / 2
        p.drawPolyline([QPointF(cx - 4, cy - 2), QPointF(cx, cy + 2), QPointF(cx + 4, cy - 2)])
        p.end()

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


class _NoWheelSpin(QSpinBox):
    """마우스 휠로는 숫자가 바뀌지 않는다(스크롤하다 실수로 바뀌지 않게). 휠은 화면 스크롤로 넘긴다."""

    def wheelEvent(self, e):
        e.ignore()


class NumberBox(QFrame):
    """숫자 칸. 단위(개, 분 이하 등)는 입력 칸 밖의 글자라 눌러도 글자 커서가 들어가지 않는다.
    off_text 를 주면 가장 작은 값(0)일 때 단위 대신 그 글자(끔)."""
    valueChanged = pyqtSignal(int)

    def __init__(self, value, lo, hi, unit, off_text=None, width=150):
        super().__init__()
        self.setObjectName("numbox")
        self.setFixedSize(width, CONTROL_H)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 12, 0)
        lay.setSpacing(6)
        self.spin = _NoWheelSpin()
        self.spin.setObjectName("numspin")
        self.spin.setFrame(False)
        self.spin.setRange(lo, hi)
        self.spin.setValue(int(value or 0))
        self.spin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        if off_text:
            self.spin.setSpecialValueText(off_text)
        self.off_text = off_text
        self.unit = QLabel((unit or "").strip())
        self.unit.setObjectName("numunit")
        lay.addWidget(self.spin, 1)
        lay.addWidget(self.unit)
        self.spin.valueChanged.connect(self._changed)
        self.spin.installEventFilter(self)
        self._changed(self.spin.value(), emit=False)

    def _changed(self, v, emit=True):
        self.unit.setVisible(not (self.off_text and v == self.spin.minimum()))
        if emit:
            self.valueChanged.emit(v)

    def eventFilter(self, _obj, ev):
        if ev.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):     # 입력 중이면 테두리를 강조색으로
            self.setProperty("focus", ev.type() == QEvent.Type.FocusIn)
            self.style().unpolish(self)
            self.style().polish(self)
        return False

    def value(self):
        return self.spin.value()

    def setValue(self, v):
        self.spin.setValue(int(v or 0))


def spin(value, lo, hi, unit, off_text=None):
    return NumberBox(value, lo, hi, unit, off_text)


class KeepControl(QWidget):
    """원본 보관: [바로 삭제 | 기간 보관] + 날 수. 값 0 = 바로 삭제."""
    valueChanged = pyqtSignal(int)

    def __init__(self, days, unit):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.days = spin(days or 7, 1, 365, unit)
        self.seg_box = segmented([(0, tr("keep.now")), (1, tr("keep.days"))], 0 if not days else 1,
                                 self._mode, stretch=False)
        lay.addWidget(self.seg_box)
        lay.addWidget(self.days)
        self.days.setEnabled(bool(days))
        self.days.valueChanged.connect(lambda _v: self.valueChanged.emit(self.value()))

    def _mode(self, keep):
        self.days.setEnabled(bool(keep))
        self.valueChanged.emit(self.value())

    def value(self):
        return self.days.value() if self.days.isEnabled() else 0

    def setValue(self, v):
        v = int(v or 0)
        for b in self.seg_box.findChildren(QPushButton):
            b.setChecked((b.text() == tr("keep.days")) == bool(v))
        self.days.setEnabled(bool(v))
        if v:
            self.days.setValue(v)


# -- 설정 줄 --------------------------------------------------------------------------------------
def setting_row(title, desc, control):
    """설정 한 줄: 왼쪽 이름과 설명, 오른쪽 조작."""
    row = QWidget()
    row.setObjectName("settingrow")
    row.setMinimumHeight(SETTING_ROW_H)
    lay = QHBoxLayout(row)
    lay.setContentsMargins(20, 10, 20, 10)
    lay.setSpacing(16)
    left = QVBoxLayout()
    left.setSpacing(3)
    left.addWidget(label(title, "rowtitle"))
    if desc:
        left.addWidget(label(desc, "rowdesc", wrap=True))
    lay.addLayout(left, 1)
    if control is not None:
        lay.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
    return row


def section(title, rows, desc=None):
    """설정 묶음: 제목 + 테두리 칸 안의 여러 줄(줄 사이 가는 선)."""
    box = QVBoxLayout()
    box.setSpacing(10)
    head = QVBoxLayout()
    head.setSpacing(2)
    head.addWidget(label(title, "h2"))
    if desc:
        head.addWidget(label(desc, "muted", wrap=True))
    box.addLayout(head)
    frame_ = QFrame()
    frame_.setObjectName("card")
    v = QVBoxLayout(frame_)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(0)
    for i, r in enumerate(rows):
        if i:
            v.addWidget(hline())
        v.addWidget(r)
    box.addWidget(frame_)
    return box


def units():
    """숫자 칸 뒤에 붙는 단위(개, 분, 일)."""
    def u(key):
        t = tr(key).strip()
        return f" {t}" if t else ""
    return u("unit.count"), u("unit.min"), u("unit.day")
