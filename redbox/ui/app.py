"""화면 앱: 트레이 아이콘과 메인 창. 감지, 녹화, 업로드는 별도 스레드의 서비스가 맡는다."""
import os
import subprocess
import sys
import threading
import time

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .. import APP_NAME, config, i18n, startup
from ..updater import UpdateChecker
from ..i18n import tr
from ..service import Service
from .style import QSS, app_font, app_icon
from .taskbar import Taskbar
from .setup import SetupWindow
from .window import MainWindow, RestartDialog


class App:
    def __init__(self, show=True):
        try:   # 작업표시줄에서 파이썬이 아니라 이 앱으로 묶이고 앱 아이콘이 보이게(창을 만들기 전에 정해야 한다)
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_NAME)
        except (AttributeError, OSError):
            pass
        self.qt = QApplication.instance() or QApplication(sys.argv)
        self.qt.setWindowIcon(app_icon())
        self.qt.setQuitOnLastWindowClosed(False)
        self.qt.setStyle("Fusion")
        self.qt.setFont(app_font())
        self.qt.setStyleSheet(QSS)
        self.cfg = config.load()
        i18n.set_language(self.cfg.get("language"))
        self.svc = Service(self.cfg)
        try:   # 첫 실행 안내를 마친 뒤에만, 개발용 데이터 폴더(REDBOX_HOME)로 띄운 것은 건드리지 않는다
            if (self.cfg.get("setup_done") and not os.environ.get("REDBOX_HOME")
                    and startup.apply(self.cfg.get("start_with_windows", True))):
                self.svc.log("윈도우 시작 시 실행 설정을 맞춤: " + ("등록" if self.cfg.get("start_with_windows", True) else "해제"))
        except OSError as e:
            self.svc.log(f"[오류] 윈도우 시작 시 실행 설정 실패: {e}")
        self.thread = threading.Thread(target=self.svc.run, daemon=True, name="service")
        self.svc.updates = UpdateChecker(self.cfg)
        self._told_version = None
        self.window = None
        self.setup = None
        self.tray = QSystemTrayIcon(app_icon(), self.qt)
        self.tray.activated.connect(self._tray_clicked)
        self.tray.messageClicked.connect(self._open_release)
        self._recording = None
        self.taskbar = Taskbar()
        self._overlay = None        # 작업표시줄 단추에 마지막으로 붙인 녹화 표시(창이 숨으면 None)
        self._overlay_tries = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        if self.cfg.get("setup_done"):
            self._start(show)
        else:                # 처음 설치: 안내를 마쳐야 감지와 녹화를 시작한다
            self.setup = SetupWindow(self.cfg, on_done=lambda: self._start(True), on_quit=self.quit)
            self.setup.show()

    def _start(self, show):
        self.setup = None
        self._build()
        self.tray.show()
        self.timer.start(1000)
        self.thread.start()
        self.svc.updates.start()
        if show:
            self.window.present()

    def _build(self):
        """창과 트레이 메뉴."""
        self.window = MainWindow(self.svc, self._language_changed)
        menu = QMenu()
        menu.addAction(tr("tray.open"), self.show)
        menu.addSeparator()
        menu.addAction(tr("tray.quit"), self.quit)
        self.menu = menu
        self.tray.setContextMenu(menu)

    def _language_changed(self):
        """언어는 다시 실행해야 적용된다. 지금 다시 실행할지 묻는다."""
        if RestartDialog(self.window).exec():
            self.restart()

    def restart(self):
        """서비스를 정상적으로 멈추고(녹화 중이면 마무리), 새 프로세스를 띄운 뒤 끝낸다.
        새 프로세스는 --restart 로 이 프로세스가 끝날 때까지 잠깐 기다린다."""
        cmd = startup.command().replace(" --hidden", "") + " --restart"
        self.svc.stop_event.set()
        self.thread.join(timeout=15)
        subprocess.Popen(cmd, creationflags=0x00000008 | 0x00000200, close_fds=True)   # DETACHED, NEW_PROCESS_GROUP
        self.tray.hide()
        self.qt.quit()

    def _tray_clicked(self, reason):
        if self.window is None:
            return
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show()

    def show(self):
        self.window.present()
        self.window.raise_()
        self.window.activateWindow()

    def _open_release(self):
        new = self.svc.updates.new
        if new:
            from .widgets import open_target
            open_target(new[1])

    def _tick(self):
        new = self.svc.updates.new
        if new and new[0] != self._told_version:      # 새 버전은 트레이 알림으로 한 번만
            self._told_version = new[0]
            self.tray.showMessage(APP_NAME, tr("update.tray").format(v=new[0]), app_icon(), 8000)
        rec = self.svc.recorder.session
        recording = bool(rec)
        if recording != self._recording:
            self._recording = recording
            self.tray.setIcon(app_icon(recording))
        self._update_overlay(recording)
        tip = f"{APP_NAME}: " + (f"{tr('state.recording')} {rec.game}" if rec else
                                 tr("state.paused") if self.svc.paused else tr("state.idle"))
        self.tray.setToolTip(tip)

    def _update_overlay(self, recording):
        """작업표시줄 단추의 빨간 점. 창이 숨었다 다시 뜨면 단추가 새로 생기므로, 뜬 뒤 몇 초 동안은 다시 붙인다."""
        w = self.window
        if w is None or not w.isVisible():
            self._overlay, self._overlay_tries = None, 0
            return
        if recording != self._overlay:
            self._overlay_tries = 0
        if self._overlay_tries >= 3:
            return
        if self.taskbar.set_recording(int(w.winId()), recording, tr("state.recording")):
            self._overlay = recording
            self._overlay_tries += 1

    def quit(self):
        self.svc.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=15)
        self.tray.hide()
        self.qt.quit()

    def exec(self):
        return self.qt.exec()


def _install_error_log():
    """PyQt6 는 화면 코드(슬롯, 이벤트 처리)에서 처리 안 된 예외가 나면 앱을 통째로 끈다.
    sys.excepthook 을 바꿔 두면 끄지 않고 이 함수를 부르므로, 오류를 기록하고 계속 돈다.
    파이썬 밖(Qt 내부)에서 죽는 경우를 위해 faulthandler 기록도 남긴다."""
    import datetime
    import faulthandler
    import os
    import traceback

    from .. import paths
    err_path = os.path.join(paths.log_dir(), "ui_error.log")

    def hook(etype, value, tb):
        try:
            with open(err_path, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] "
                        + "".join(traceback.format_exception(etype, value, tb)) + "\n")
        except OSError:
            pass

    sys.excepthook = hook
    try:
        main._fault = open(os.path.join(paths.log_dir(), "crash.log"), "a", encoding="utf-8")
        faulthandler.enable(main._fault)
    except OSError:
        pass


def main(show=True, restart=False):
    from ..service import single_instance
    lock = single_instance()
    tries = 60 if restart else 0          # 다시 실행이면 이전 창이 끝날 때까지 최대 30초 기다린다
    while lock is None and tries:
        time.sleep(0.5)
        tries -= 1
        lock = single_instance()
    if lock is None:
        return 0
    _install_error_log()
    return App(show).exec()
