"""설정: 일반, 녹화, 유튜브 업로드, 정보. 바꾸면 바로 저장한다."""
import os
import threading

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from .. import APP_NAME, VERSION, config, paths, startup
from ..i18n import tr
from ..uploader import youtube
from .widgets import (Check, Combo, KeepControl, SmoothWheel, button, open_target, section, setting_row, spin,
                      units)


class SettingsPage(QScrollArea):
    auth_done = pyqtSignal(str)

    def __init__(self, svc, on_language_change):
        super().__init__()
        self.svc, self.cfg = svc, svc.cfg
        self.on_language_change = on_language_change
        self.auth_done.connect(self._auth_finished)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._smooth = SmoothWheel(self)
        inner = QWidget()
        inner.setObjectName("root")
        outer = QHBoxLayout(inner)
        outer.setContentsMargins(32, 0, 32, 0)
        holder = QWidget()
        outer.addWidget(holder, 1)
        self.setWidget(inner)
        v = QVBoxLayout(holder)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(28)
        rec, up = self.cfg["recording"], self.cfg["upload"]
        u_count, _u_min, u_day = units()

        # 일반
        lang = Combo([("auto", tr("set.lang.auto")), ("ko", "한국어"), ("en", "English")],
                     self.cfg.get("language", "auto"), width=180)
        lang.currentIndexChanged.connect(lambda _i: self._set_lang(lang.value()))
        boot = Check()
        boot.setChecked(bool(self.cfg.get("start_with_windows", True)))
        boot.toggled.connect(self._set_startup)
        upd = Check()
        upd.setChecked(bool(self.cfg.get("check_updates", True)))
        upd.toggled.connect(self._set_updates)
        v.addLayout(section(tr("set.general"), [
            setting_row(tr("set.language"), "", lang),
            setting_row(tr("set.startup"), "", boot),
            setting_row(tr("set.updates"), "", upd)]))

        # 녹화
        self.folder_row = setting_row(tr("set.folder"), rec["video_root"],
                                      button(tr("set.change"), self._pick_folder, icon_name="folder"))
        autodel = spin(up.get("auto_delete_minutes"), 0, 60, tr("unit.min_le"), tr("unit.off"))
        autodel.valueChanged.connect(lambda val: self._set_up("auto_delete_minutes", val))
        v.addLayout(section(tr("set.recording"), [
            self.folder_row, setting_row(tr("set.autodel"), tr("set.autodel.desc"), autodel)]))

        # 오디오
        obs = self.cfg["obs"]
        mic = Check()
        mic.setChecked(bool(obs.get("mic")))
        mic.toggled.connect(lambda on: self._set_obs("mic", bool(on)))
        target = Combo([("game", tr("set.audio.game")), ("all", tr("set.audio.all"))], obs.get("audio") or "game",
                       width=180)
        target.currentIndexChanged.connect(lambda _i: self._set_obs("audio", target.value()))
        v.addLayout(section(tr("set.audio"), [
            setting_row(tr("set.mic"), tr("set.mic.desc"), mic),
            setting_row(tr("set.audio.target"), "", target)]))

        # 유튜브 업로드
        self.auth_btn = button(tr("set.signin.key"), self._sign_in, icon_name="youtube")
        self.auth_row = setting_row(tr("set.account"), " ", self.auth_btn)
        self.auth_state = self.auth_row.findChild(QLabel, "rowdesc")
        en = Check()
        en.setChecked(bool(up.get("enabled")))
        en.toggled.connect(lambda val: self._set_up("enabled", val))
        rows = [self.auth_row, setting_row(tr("set.upload.on"), tr("set.upload.on.desc"), en)]
        for key, text, lo, hi, unit in (("daily_limit", "set.daily", 1, config.UPLOAD_DAILY_MAX, u_count),
                                        ("min_minutes", "set.min", 0, 600, tr("unit.min_ge"))):
            sp = spin(up.get(key), lo, hi, unit)
            sp.valueChanged.connect(lambda val, k=key: self._set_up(k, val))
            rows.append(setting_row(tr(text), tr(text + ".desc"), sp))
        keep = KeepControl(up.get("keep_days"), u_day)
        keep.valueChanged.connect(lambda val: self._set_up("keep_days", val))
        rows.append(setting_row(tr("set.keep"), tr("set.keep.desc"), keep))
        v.addLayout(section(tr("set.upload"), rows))

        # 정보
        folders = QWidget()
        fl = QHBoxLayout(folders)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(8)
        fl.addWidget(button(tr("set.open.logs"), lambda: open_target(paths.log_dir())))
        fl.addWidget(button(tr("set.open.data"), lambda: open_target(paths.data_dir())))
        self.update_btn = button(tr("update.download"), self._open_update, primary=True)
        self.update_btn.hide()
        fl.addWidget(self.update_btn)
        self.about_row = setting_row(f"{APP_NAME} {VERSION}", tr("app.tagline"), folders)
        self.about_desc = self.about_row.findChild(QLabel, "rowdesc")
        v.addLayout(section(tr("set.about"), [self.about_row]))
        v.addStretch(1)

    # -- 저장 -------------------------------------------------------------------------------------
    def _saved(self):
        config.save(self.cfg)

    def _set_up(self, key, val):
        self.cfg["upload"][key] = val
        self._saved()
        if key == "enabled" and val:
            self.svc.uploader.nudge()

    def _set_obs(self, key, val):
        """오디오 설정은 다음 녹화부터 적용(녹화를 시작할 때 맞춘다)."""
        self.cfg["obs"][key] = val
        self._saved()

    def _set_updates(self, on):
        self.cfg["check_updates"] = bool(on)
        self._saved()

    def _open_update(self):
        new = getattr(getattr(self.svc, "updates", None), "new", None)
        if new:
            open_target(new[1])

    def _set_startup(self, on):
        self.cfg["start_with_windows"] = bool(on)
        self._saved()
        try:
            startup.apply(bool(on))
        except OSError as e:
            self.svc.log(f"[오류] 윈도우 시작 시 실행 설정 실패: {e}")

    def _set_lang(self, val):
        if val == self.cfg.get("language", "auto"):
            return
        self.cfg["language"] = val
        self._saved()
        self.on_language_change()

    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, tr("set.folder"), self.cfg["recording"]["video_root"])
        if d:
            self.cfg["recording"]["video_root"] = os.path.normpath(d)
            desc = self.folder_row.findChild(QLabel, "rowdesc")
            if desc:
                desc.setText(self.cfg["recording"]["video_root"])
            self._saved()

    # -- 유튜브 로그인 ---------------------------------------------------------------------------------
    def _signed_in(self):
        return os.path.exists(youtube.token_file()) and not self.svc.uploader.auth_problem

    def _sign_in(self):
        """로그인 안 됨: 키 파일을 고르고 브라우저로 로그인. 로그인 됨: 브라우저로 다시 로그인(계정 바꾸기)."""
        force = self._signed_in()
        if not force and not youtube.has_secret():
            f, _ = QFileDialog.getOpenFileName(self, tr("set.account"), "", "JSON (*.json)")
            if not f:
                return
            youtube.import_secret(f)
        self._busy = True
        self.auth_btn.setEnabled(False)
        self.auth_btn.setText(tr("set.signin.busy"))
        self.auth_state.setText(tr("set.signin.wait"))

        def work():
            try:
                youtube.credentials(interactive=True, force=force)
                self.auth_done.emit("")
            except Exception as e:
                self.auth_done.emit(str(e))
        threading.Thread(target=work, daemon=True).start()

    def _auth_finished(self, err):
        self._busy = False
        self.auth_btn.setEnabled(True)
        self._channel = None
        if not err:
            self.svc.uploader.auth_problem = None
            self.svc.uploader.nudge()
            self._load_channel()
        self._auth_error = err
        self.refresh()

    def _load_channel(self):
        """채널 이름은 뒤에서 한 번 알아 온다(유튜브에 묻는 일이라)."""
        def work():
            self._channel = youtube.channel_name()
        threading.Thread(target=work, daemon=True).start()

    def refresh(self):
        new = getattr(getattr(self.svc, "updates", None), "new", None)
        want = tr("update.new").format(v=new[0]) if new else tr("app.tagline")
        if self.about_desc.text() != want:
            self.about_desc.setText(want)
        if self.update_btn.isHidden() == bool(new):
            self.update_btn.setVisible(bool(new))
        if getattr(self, "_busy", False):
            return
        ok = self._signed_in()
        if ok and getattr(self, "_channel", None) is None and not getattr(self, "_channel_asked", False):
            self._channel_asked = True
            self._load_channel()
        err = getattr(self, "_auth_error", "")
        if ok:
            ch = getattr(self, "_channel", None)
            state = tr("set.signin.ok") + (f": {ch}" if ch else "")
        else:
            state = err or tr("set.signin.no")
        if self.auth_state.text() != state:
            self.auth_state.setText(state)
        want = tr("set.signin.again") if ok else tr("set.signin.key")
        if self.auth_btn.text() != want:
            self.auth_btn.setText(want)
