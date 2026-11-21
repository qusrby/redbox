"""첫 실행 안내: 언어, OBS 연결, 영상 폴더, 유튜브(건너뛰기 가능), 마무리.
설정 파일이 없을 때(처음 설치) 메인 창보다 먼저 뜨고, 끝나야 감지와 녹화가 시작된다.
설명이 필요한 곳은 합니다체 문장으로, 버튼과 이름은 명사형으로 쓴다."""
import os
import threading

from PyQt6.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, config, i18n, startup
from ..i18n import tr
from ..recorder import obs as obsmod
from ..uploader import youtube
from . import frame, icons
from .style import C, app_icon, logo_pixmap
from .widgets import Check, Combo, Dot, button, hline, label, open_target, setting_row

DOCS_YOUTUBE = "https://github.com/qusrby/redbox/blob/main/docs/youtube-key.md"
CONSOLE = (   # (문구 키, 구글 클라우드 콘솔 주소)
    ("setup.yt.s1", "https://console.cloud.google.com/projectcreate"),
    ("setup.yt.s2", "https://console.cloud.google.com/apis/library/youtube.googleapis.com"),
    ("setup.yt.s3", "https://console.cloud.google.com/auth/overview"),
    ("setup.yt.s4", "https://console.cloud.google.com/auth/clients/create"),
)
STEPS = ("setup.step.lang", "setup.step.obs", "setup.step.folder", "setup.step.youtube", "setup.step.finish")
LANG, OBS, FOLDER, YOUTUBE, FINISH = range(5)


class StepItem(QWidget):
    """왼쪽 단계 목록 한 줄: 네모 번호 + 이름. 지금 단계는 파란 테두리, 지난 단계는 파란 칸에 체크."""

    def __init__(self, n, text):
        super().__init__()
        self.n, self.state = n, "todo"
        self.setFixedHeight(40)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(46, 0, 8, 0)
        self.text = QLabel(text)
        lay.addWidget(self.text)

    def set_state(self, state):
        if state != self.state:
            self.state = state
            color = C["text"] if state == "now" else C["text2"] if state == "done" else C["muted"]
            weight = 700 if state == "now" else 500
            self.text.setStyleSheet(f"color: {color}; font-weight: {weight};")
            self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        box = 24
        x, y = 12, (self.height() - box) // 2
        if self.state == "now":
            p.fillRect(0, 0, 3, self.height(), QColor(C["accent"]))
            p.fillRect(3, 0, self.width() - 3, self.height(), QColor(C["surface3"]))
        if self.state == "done":
            p.fillRect(x, y, box, box, QColor(C["accent"]))
            icons.paint(p, "check", QRectF(x + 4, y + 4, 16, 16), C["on_accent"])
        else:
            color = QColor(C["accent"] if self.state == "now" else C["border2"])
            p.setPen(color)
            p.drawRect(x, y, box - 1, box - 1)
            p.setPen(QColor(C["accent"] if self.state == "now" else C["muted"]))
            p.drawText(x, y, box, box, Qt.AlignmentFlag.AlignCenter, str(self.n))
        p.end()


def status_row(name):
    """OBS 단계의 상태 한 줄: 이름 | 색 네모 + 값 | 오른쪽 버튼 자리."""
    row = QWidget()
    row.setObjectName("settingrow")
    row.setMinimumHeight(58)
    lay = QHBoxLayout(row)
    lay.setContentsMargins(20, 8, 20, 8)
    lay.setSpacing(12)
    nm = label(name, "rowtitle")
    nm.setFixedWidth(150)
    lay.addWidget(nm)
    dot = Dot(18, 10)
    lay.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
    val = label("", "rowtitle")
    lay.addWidget(val, 1)
    slot = QHBoxLayout()
    slot.setSpacing(8)
    lay.addLayout(slot)
    row.dot, row.val, row.slot = dot, val, slot
    return row


def set_status(row, text, color):
    if row.val.text() != text:
        row.val.setText(text)
    row.dot.set_color(color)


class SetupWindow(QWidget):
    obs_tested = pyqtSignal(str)
    auth_done = pyqtSignal(str)
    channel_found = pyqtSignal(str)

    def __init__(self, cfg, on_done, on_quit):
        super().__init__()
        self.cfg, self.on_done, self.on_quit = cfg, on_done, on_quit
        self.index = 0
        self.reached = 0
        self.channel = None
        self.auth_error = ""
        self.busy = False
        self._testing = False
        self._obs_version = None
        self._ws_note = False
        self.obs_tested.connect(self._obs_result)
        self.auth_done.connect(self._auth_finished)
        self.channel_found.connect(self._channel_found)
        self.setObjectName("root")
        self.setWindowFlags(Qt.WindowType.Window)
        frame.refresh(int(self.winId()))
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(960, 640)
        self.setMinimumSize(880, 600)
        self.outer = QHBoxLayout(self)
        self.outer.setContentsMargins(0, 0, 0, 0)
        self.outer.setSpacing(0)
        self.body = None
        self._build()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1500)

    # -- 화면 만들기(언어를 바꾸면 통째로 다시 만든다) ---------------------------------------------------
    def _build(self):
        if self.body is not None:
            self.body.hide()
            self.body.setParent(None)
            self.body.deleteLater()
        self.body = QWidget()
        self.outer.addWidget(self.body)
        h = QHBoxLayout(self.body)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

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
        self.items = []
        for i, key in enumerate(STEPS):
            it = StepItem(i + 1, tr(key))
            self.items.append(it)
            sl.addWidget(it)
        sl.addStretch(1)
        h.addWidget(side)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        head = QWidget()
        head.setFixedHeight(68)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(40, 0, 0, 0)
        self.title = label("", "pagetitle")
        hl.addWidget(self.title, 0, Qt.AlignmentFlag.AlignVCenter)
        hl.addStretch(1)
        for kind, fn in (("min", self.showMinimized), ("close", self.close)):
            b = frame.WinButton(kind)
            b.clicked.connect(fn)
            hl.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        self.drag_widgets.append(head)
        right.addWidget(head)

        self.stack = QStackedWidget()
        for make in (self._page_lang, self._page_obs, self._page_folder, self._page_youtube, self._page_finish):
            self.stack.addWidget(self._page(make()))
        right.addWidget(self.stack, 1)

        right.addWidget(hline())
        foot = QWidget()
        foot.setFixedHeight(68)
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(40, 0, 40, 0)
        fl.setSpacing(8)
        self.back_btn = button(tr("setup.back"), lambda: self._go(self.index - 1))
        fl.addWidget(self.back_btn)
        fl.addStretch(1)
        self.skip_btn = button(tr("setup.skip"), lambda: self._go(self.index + 1))
        fl.addWidget(self.skip_btn)
        self.next_btn = button(tr("setup.next"), self._next, primary=True)
        self.next_btn.setMinimumWidth(110)
        fl.addWidget(self.next_btn)
        right.addWidget(foot)
        h.addLayout(right, 1)
        self._go(self.index)

    def _page(self, content):
        """본문 한 장: 위 설명 + 내용. 너비는 읽기 좋게 640까지."""
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(40, 4, 40, 24)
        inner = QWidget()
        inner.setMaximumWidth(640)
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(18)
        desc, body = content
        if desc:
            v.addWidget(label(desc, "setupdesc", wrap=True))
        if body is not None:
            v.addWidget(body)
        v.addStretch(1)
        lay.addWidget(inner, 1)
        lay.addStretch(0)
        return w

    @staticmethod
    def _card(rows):
        box = QFrame()
        box.setObjectName("card")
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        for i, r in enumerate(rows):
            if i:
                v.addWidget(hline())
            v.addWidget(r)
        return box

    def _page_lang(self):
        cur = self.cfg.get("language", "auto")
        lang = Combo([("auto", tr("set.lang.auto")), ("ko", "한국어"), ("en", "English")], cur, width=200)
        lang.currentIndexChanged.connect(lambda _i: self._set_lang(lang.value()))
        return tr("setup.lang.desc").format(app=APP_NAME), self._card([setting_row(tr("set.language"), "", lang)])

    def _page_obs(self):
        self.r_install = status_row("OBS Studio")
        self.r_ws = status_row(tr("setup.obs.ws"))
        self.r_conn = status_row(tr("setup.obs.conn"))
        self.dl_btn = button(tr("setup.obs.download"), lambda: open_target(obsmod.OBS_DOWNLOAD), icon_name="external")
        self.r_install.slot.addWidget(self.dl_btn)
        self.run_btn = button(tr("setup.obs.run"), self._run_obs, icon_name="play")
        self.r_conn.slot.addWidget(self.run_btn)
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        v.addWidget(self._card([self.r_install, self.r_ws, self.r_conn]))
        self.obs_note = label("", "setupnote", wrap=True)
        v.addWidget(self.obs_note)
        return tr("setup.obs.desc").format(app=APP_NAME), box

    def _page_folder(self):
        self.folder_row = setting_row(tr("set.folder"), self.cfg["recording"]["video_root"],
                                      button(tr("set.change"), self._pick_folder, icon_name="folder"))
        return tr("setup.folder.desc"), self._card([self.folder_row])

    def _page_youtube(self):
        rows = []
        for i, (key, url) in enumerate(CONSOLE):
            rows.append(setting_row(f"{i + 1}. {tr(key)}", tr(key + ".desc"),
                                    button(tr("setup.open"), lambda _c=False, u=url: open_target(u),
                                           icon_name="external")))
        self.auth_btn = button(tr("set.signin.key"), self._sign_in, primary=True, icon_name="youtube")
        self.auth_row = setting_row(f"{len(CONSOLE) + 1}. {tr('setup.yt.s5')}", " ", self.auth_btn)
        self.auth_state = self.auth_row.findChild(QLabel, "rowdesc")
        rows.append(self.auth_row)
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        v.addWidget(self._card(rows))
        guide = button(tr("setup.yt.guide"), lambda: open_target(DOCS_YOUTUBE))
        guide.setObjectName("link")
        guide.setIcon(icons.icon("external", C["text2"], 16))
        row = QHBoxLayout()
        row.addWidget(guide)
        row.addStretch(1)
        v.addLayout(row)
        return tr("setup.yt.desc"), box

    def _page_finish(self):
        boot = Check()
        boot.setChecked(bool(self.cfg.get("start_with_windows", True)))
        boot.toggled.connect(lambda on: self.cfg.__setitem__("start_with_windows", bool(on)))
        return tr("setup.finish.desc").format(app=APP_NAME), self._card([setting_row(tr("set.startup"), "", boot)])

    # -- 이동 -------------------------------------------------------------------------------------
    def _go(self, i):
        i = max(0, min(i, len(STEPS) - 1))
        self.index = i
        self.reached = max(self.reached, i)
        self.stack.setCurrentIndex(i)
        self.title.setText(tr(STEPS[i] + ".title"))
        for n, it in enumerate(self.items):
            it.set_state("now" if n == i else "done" if n < i else "todo")
        self.back_btn.setVisible(i > 0)
        self.skip_btn.setVisible(i == YOUTUBE and not self._signed_in())
        self.next_btn.setText(tr("setup.start") if i == FINISH else tr("setup.next"))
        self._tick()

    def _next(self):
        if self.index == FINISH:
            self._finish()
        else:
            self._go(self.index + 1)

    def _finish(self):
        self.cfg["setup_done"] = True
        config.save(self.cfg)
        try:
            startup.apply(bool(self.cfg.get("start_with_windows", True)))
        except OSError:
            pass
        self.timer.stop()
        self._done = True
        self.hide()
        self.on_done()
        self.deleteLater()

    def _set_lang(self, val):
        if val == self.cfg.get("language", "auto"):
            return
        self.cfg["language"] = val
        config.save(self.cfg)
        i18n.set_language(val)
        QTimer.singleShot(0, self._build)      # 콤보 상자 신호 안에서 자신을 지우지 않게 다음 차례에

    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, tr("set.folder"), self.cfg["recording"]["video_root"])
        if d:
            self.cfg["recording"]["video_root"] = os.path.normpath(d)
            config.save(self.cfg)
            desc = self.folder_row.findChild(QLabel, "rowdesc")
            if desc:
                desc.setText(self.cfg["recording"]["video_root"])

    # -- OBS --------------------------------------------------------------------------------------
    def _tick(self):
        if self.index == OBS:
            self._check_obs()
        elif self.index == YOUTUBE:
            self._refresh_auth()

    def _check_obs(self):
        ok, bad, dim = C["ok"], C["neg"], C["muted"]
        exe = obsmod.find_obs()
        running = obsmod.obs_running()
        ws = obsmod.websocket_settings()
        note = ""
        if not exe and not running:
            set_status(self.r_install, tr("setup.obs.notinstalled"), bad)
            set_status(self.r_ws, tr("step.none"), dim)
            set_status(self.r_conn, tr("step.none"), dim)
            note = tr("setup.obs.install.note")
        else:
            set_status(self.r_install, tr("setup.obs.installed"), ok)
            if not (ws and ws["enabled"]):
                if running:
                    set_status(self.r_ws, tr("setup.obs.ws.off"), bad)
                    set_status(self.r_conn, tr("step.none"), dim)
                    note = tr("setup.obs.ws.close")
                else:
                    try:
                        ws = obsmod.enable_websocket()
                    except OSError:
                        ws = None
            if ws and ws["enabled"]:
                set_status(self.r_ws, tr("setup.obs.ws.on"), ok)
            if not running:
                set_status(self.r_conn, tr("setup.obs.off"), bad if ws and ws["enabled"] else dim)
                self._obs_version = None
            elif ws and ws["enabled"]:
                if self._obs_version:
                    set_status(self.r_conn, tr("setup.obs.connected").format(v=self._obs_version), ok)
                else:
                    set_status(self.r_conn, tr("setup.obs.connecting"), C["accent"])
                    self._test_obs()
        self.dl_btn.setVisible(not exe and not running)
        self.run_btn.setVisible(bool(exe) and not running)
        if self.obs_note.text() != note:
            self.obs_note.setText(note)
        self.obs_note.setVisible(bool(note))

    def _test_obs(self):
        if self._testing:
            return
        self._testing = True

        def work():
            v = obsmod.test_connection()
            self.obs_tested.emit(v or "")
        threading.Thread(target=work, daemon=True).start()

    def _obs_result(self, version):
        self._testing = False
        self._obs_version = version or None
        if self.index == OBS:
            if version:
                set_status(self.r_conn, tr("setup.obs.connected").format(v=version), C["ok"])
            else:
                set_status(self.r_conn, tr("setup.obs.failed"), C["neg"])

    def _run_obs(self):
        exe = obsmod.find_obs()
        if exe:
            try:
                obsmod.launch_obs(exe)
            except OSError:
                pass
            set_status(self.r_conn, tr("setup.obs.connecting"), C["accent"])

    # -- 유튜브 -----------------------------------------------------------------------------------
    def _signed_in(self):
        return os.path.exists(youtube.token_file())

    def _sign_in(self):
        force = self._signed_in()
        if not force and not youtube.has_secret():
            f, _ = QFileDialog.getOpenFileName(self, tr("set.account"), "", "JSON (*.json)")
            if not f:
                return
            youtube.import_secret(f)
        self.busy = True
        self.auth_btn.setEnabled(False)
        self.auth_btn.setText(tr("set.signin.busy"))
        self.auth_state.setText(tr("set.signin.wait"))

        def work():
            try:
                youtube.credentials(interactive=True, force=force)
                self.auth_done.emit("")
            except Exception as e:
                self.auth_done.emit(str(e) or tr("set.signin.no"))
        threading.Thread(target=work, daemon=True).start()

    def _auth_finished(self, err):
        self.busy = False
        self.auth_btn.setEnabled(True)
        self.auth_error = err
        if not err:
            self.cfg["upload"]["enabled"] = True     # 로그인했으면 업로드를 켠다(설정에서 끌 수 있음)
            config.save(self.cfg)

            def work():
                self.channel_found.emit(youtube.channel_name() or "")
            threading.Thread(target=work, daemon=True).start()
        self._refresh_auth()
        self.skip_btn.setVisible(self.index == YOUTUBE and not self._signed_in())

    def _channel_found(self, name):
        self.channel = name or None
        self._refresh_auth()

    def _refresh_auth(self):
        if self.busy:
            return
        ok = self._signed_in()
        if ok:
            state = tr("set.signin.ok") + (f": {self.channel}" if self.channel else "")
        else:
            state = self.auth_error or tr("set.signin.no")
        if self.auth_state.text() != state:
            self.auth_state.setText(state)
        want = tr("set.signin.again") if ok else tr("set.signin.key")
        if self.auth_btn.text() != want:
            self.auth_btn.setText(want)

    # -- 창 ---------------------------------------------------------------------------------------
    def is_drag_area(self, pos):
        for w in getattr(self, "drag_widgets", []):
            if w.rect().contains(w.mapFrom(self, pos)):
                return True
        return False

    def showEvent(self, e):
        super().showEvent(e)
        frame.square_corners(int(self.winId()))

    def nativeEvent(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            r = frame.handle(int(message), self)
            if r is not None:
                return True, r
        return False, 0

    def closeEvent(self, ev):
        """안내를 끝내기 전에 닫으면 앱을 끝낸다(다음에 켜면 안내가 다시 뜬다)."""
        if getattr(self, "_done", False):
            ev.accept()
            return
        self.timer.stop()
        ev.accept()
        self.on_quit()
