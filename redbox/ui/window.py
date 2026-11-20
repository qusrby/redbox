"""메인 창: 왼쪽 메뉴(대시보드, 영상, 게임, 설정), 오른쪽 화면 제목과 본문.
녹화를 막는 문제가 있으면 대시보드 밖 화면에서도 본문 위에 알림 띠가 뜬다."""
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from .. import APP_NAME
from ..i18n import tr
from . import frame, icons
from .art import Art
from .dashboard import DashboardPage
from .dialogs import RestartDialog, RulesDialog  # noqa: F401  (app.py 가 여기서 가져다 쓴다)
from .games import GamesPage
from .settings import SettingsPage
from .style import C, app_icon, logo_pixmap
from .videos import VideosPage
from .widgets import Toast, label


# -- 상태 -----------------------------------------------------------------------------------------
def health(svc):
    """앱, OBS Studio, OBS 연결, 유튜브 상태.
    돌려주는 값: (줄 목록 [(이름, 값, 색, 한 줄 값)], 녹화를 막는 문제 (제목, 해결 방법) 또는 None)."""
    rec, now = svc.recorder, time.time()
    ok, bad, dim = C["ok"], C["neg"], C["muted"]
    rows, problem = [], None
    err = svc.last_error if svc.last_error and now - svc.last_error[0] < 60 else None
    if svc.last_tick and now - svc.last_tick > 15:
        rows.append((tr("step.app"), tr("step.app.stuck"), bad, ""))
        problem = (tr("step.app.stuck"), tr("step.app.stuck.note"))
    elif err:
        rows.append((tr("step.app"), tr("step.app.error"), bad, err[1][:60]))
        problem = (tr("step.app.error"), err[1][:160])
    else:
        rows.append((tr("step.app"), tr("step.app.ok"), ok, ""))
    obs_on = bool(svc.obs_pid)
    if obs_on:
        rows.append((tr("step.obs"), tr("step.obs.on"), ok, ""))
    else:
        rows.append((tr("step.obs"), tr("step.obs.off"), bad, ""))
        problem = problem or (tr("banner.obs.off"), tr("banner.obs.off.desc"))
    if not obs_on:
        rows.append((tr("step.conn"), tr("step.none"), dim, ""))
    elif rec.connected:
        rows.append((tr("step.conn"), tr("step.conn.ok"), ok, ""))
    else:
        rows.append((tr("step.conn"), tr("step.conn.down"), bad, tr("step.conn.down.note")))
        problem = problem or (tr("banner.conn"), tr("banner.conn.desc"))
    up, cfg = svc.uploader, svc.cfg["upload"]
    today = tr("up.today.n").format(n=svc.store.uploads_today(), m=cfg["daily_limit"])
    if not cfg.get("enabled"):
        rows.append((tr("step.youtube"), tr("up.off"), dim, ""))
    elif up.auth_problem:
        rows.append((tr("step.youtube"), tr("up.auth"), bad, today))
        problem = problem or (tr("banner.auth"), tr("banner.auth.desc"))
    elif up.progress:
        rows.append((tr("step.youtube"), f"{tr('up.busy')} {int(up.progress[1] * 100)}%", C["accent"], today))
    else:
        rows.append((tr("step.youtube"), tr("up.idle"), ok, today))
    return rows, problem


def _set(w, text=None, css=None):
    """바뀔 때만 고친다(매초 스타일을 다시 입히면 화면 전체 스타일 계산이 다시 돌아 움직임이 끊긴다)."""
    if text is not None and w.text() != text:
        w.setText(text)
    if css is not None and w.styleSheet() != css:
        w.setStyleSheet(css)


class Banner(QFrame):
    """녹화를 막는 문제가 있을 때만 본문 위에 뜨는 알림 띠."""

    def __init__(self):
        super().__init__()
        self.setObjectName("banner")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 10, 14, 10)
        h.setSpacing(12)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("warning", C["neg"], 20))
        h.addWidget(ic, 0, Qt.AlignmentFlag.AlignVCenter)
        self.title = label("", "bannertitle")
        self.desc = label("", "bannerdesc", wrap=True)
        h.addWidget(self.title)
        h.addWidget(self.desc, 1)

    def set(self, problem):
        if problem:
            _set(self.title, problem[0])
            _set(self.desc, problem[1])


# -- 메인 창 ---------------------------------------------------------------------------------------
class MainWindow(QWidget):
    PAGES = (("nav.dashboard", "dashboard"), ("nav.videos", "video"), ("nav.games", "games"),
             ("nav.settings", "settings"))
    DASH, VIDEOS, GAMES, SETTINGS = range(4)

    def __init__(self, service, on_language_change):
        super().__init__()
        self.svc = service
        self.cfg = service.cfg
        self.setObjectName("root")
        self.setWindowFlags(Qt.WindowType.Window)
        frame.refresh(int(self.winId()))          # 윈도우 기본 제목 표시줄을 없앤다(창 끌기, 크기 조절은 윈도우가 그대로)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1180, 760)
        self.setMinimumSize(920, 600)

        body = QHBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # 왼쪽: 이름, 메뉴, 한 줄 상태
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(232)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 0, 12, 12)
        sl.setSpacing(2)
        brand = QWidget()
        brand.setFixedHeight(68)
        bl = QHBoxLayout(brand)
        bl.setContentsMargins(8, 0, 0, 0)
        bl.setSpacing(10)
        logo = QLabel()
        dpr = self.devicePixelRatioF()
        pm = logo_pixmap(round(28 * dpr))
        pm.setDevicePixelRatio(dpr)
        logo.setPixmap(pm)
        bl.addWidget(logo)
        bl.addWidget(label(APP_NAME, "brand"))
        bl.addStretch(1)
        sl.addWidget(brand)
        self.drag_widgets = [brand]
        self.nav_group = QButtonGroup(self)
        self.nav_buttons = []
        for i, (key, ic) in enumerate(self.PAGES):
            b = QPushButton(tr(key))
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setIcon(icons.icon(ic, C["text2"], 20, on_color=C["accent"]))
            pm = icons.pixmap(ic, C["text2"], 20)
            b.setIconSize(pm.size() / pm.devicePixelRatio())
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c, i=i: self._go(i))
            self.nav_group.addButton(b)
            self.nav_buttons.append(b)
            sl.addWidget(b)
        sl.addStretch(1)
        body.addWidget(side)

        # 오른쪽: 화면 제목과 창 버튼, 알림 띠, 본문
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        head = QWidget()
        head.setFixedHeight(68)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(32, 0, 0, 0)
        hl.setSpacing(12)
        self.title = label("", "pagetitle")
        hl.addWidget(self.title, 0, Qt.AlignmentFlag.AlignVCenter)
        self.subtitle = label("", "pagesub")
        hl.addWidget(self.subtitle, 0, Qt.AlignmentFlag.AlignVCenter)
        hl.addStretch(1)
        self.max_btn = None
        for kind, fn in (("min", self.showMinimized), ("max", self._toggle_max), ("close", self.close)):
            b = frame.WinButton(kind)
            b.clicked.connect(fn)
            hl.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
            if kind == "max":
                self.max_btn = b
        self.drag_widgets.append(head)
        right.addWidget(head)
        bw = QWidget()
        bwl = QVBoxLayout(bw)
        bwl.setContentsMargins(32, 0, 32, 14)
        self.banner = Banner()
        bwl.addWidget(self.banner)
        self.banner_wrap = bw
        bw.hide()
        right.addWidget(bw)
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        body.addLayout(right, 1)

        art = Art(lambda: service.detector.catalog, lambda: self.cfg["detection"].get("custom_games", []),
                  lambda: [r.get("game") for r in list(service.store.data["recordings"].values())], service.log)
        art.updated.connect(self._art_updated)
        self.dashboard = DashboardPage(service, art, lambda: self._go(self.VIDEOS))
        self.videos = VideosPage(service, art)
        self.games = GamesPage(service, art)
        self.settings = SettingsPage(service, on_language_change)
        for w in (self.dashboard, self.videos, self.games, self.settings):
            self.stack.addWidget(w)
        self.videos.count_changed.connect(lambda _n: self._update_title())
        self.toast = Toast(self)
        self._problem = None
        self._go(self.DASH)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    def _art_updated(self):
        """게임 그림을 새로 모았으면 목록과 카드를 새 그림으로 다시 그린다."""
        self.dashboard._sig = None
        self.dashboard.hero.game = None
        self.videos._sig = None
        self.videos.list.icons.clear()
        self.dashboard.recent.icons.clear()
        self.games.fill(force=True)
        self.refresh()

    def _go(self, i):
        self.stack.setCurrentIndex(i)
        self.nav_buttons[i].setChecked(True)
        if i == self.GAMES:
            self.games.fill()
        self._update_title()
        self._update_banner()

    def _update_title(self):
        i = self.stack.currentIndex()
        self.title.setText(tr(self.PAGES[i][0]))
        self.subtitle.setText("")      # 영상 수는 필터 탭에 나온다

    def _update_banner(self):
        """대시보드는 상태 칸이 문제를 크게 보여 주므로 띠를 따로 띄우지 않는다."""
        show = bool(self._problem) and self.stack.currentIndex() != self.DASH
        self.banner.set(self._problem)
        if self.banner_wrap.isVisible() != show:
            self.banner_wrap.setVisible(show)

    def is_drag_area(self, pos):
        """창 머리와 왼쪽 위 이름 칸을 잡으면 창이 움직인다(버튼 위는 제외)."""
        for w in getattr(self, "drag_widgets", []):
            if w.rect().contains(w.mapFrom(self, pos)):
                return True
        return False

    def refresh(self):
        rows, problem = health(self.svc)
        self._problem = problem
        self._update_banner()
        if self.isVisible():
            self.dashboard.refresh_status(rows, problem)
            self.dashboard.refresh()
            self.videos.refresh()
            self.settings.refresh()

    def _toggle_max(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def changeEvent(self, e):
        super().changeEvent(e)
        btn = getattr(self, "max_btn", None)    # 창을 만드는 도중에도 불린다(PyQt6 는 여기서 오류가 나면 앱을 끈다)
        if btn is not None:
            btn.set_restore(self.isMaximized())

    def showEvent(self, e):
        super().showEvent(e)
        frame.square_corners(int(self.winId()))
        self.refresh()

    def nativeEvent(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            r = frame.handle(int(message), self)
            if r is not None:
                return True, r
        return False, 0

    def closeEvent(self, ev):
        """창을 닫으면 트레이로 숨는다(녹화는 계속)."""
        ev.ignore()
        self.hide()
