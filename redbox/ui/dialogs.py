"""대화 상자: 언어 변경 후 다시 실행, 게임별 업로드 규칙, 게임 추가. 대화 상자 안 설명은 대화체로 쓴다."""
import os

from PyQt6.QtCore import QFileInfo, QSize, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QDialog, QFileDialog, QFileIconProvider, QFrame, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)

from .. import config
from ..paths import start_file
from ..i18n import tr
from . import icons
from .style import C
from .widgets import (Check, ElideLabel, KeepControl, SearchBox, SmoothWheel, button, hline, label, open_target,
                      setting_row, spin, units)


class _Dialog(QDialog):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)   # 기본 제목 표시줄 없음
        self.setObjectName("dialog")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(24, 22, 24, 20)
        self.lay.setSpacing(14)
        self.lay.addWidget(label(title, "h2"))
        self._shade = None

    # 대화 상자가 떠 있는 동안 뒤 창을 어둡게 덮어 구분되게 한다
    def showEvent(self, e):
        super().showEvent(e)
        host = self.parentWidget().window() if self.parentWidget() else None
        if host is not None and host.isVisible() and self._shade is None:
            self._shade = QWidget(host)
            self._shade.setStyleSheet("background: rgba(0, 0, 0, 150);")
            self._shade.setGeometry(host.rect())
            self._shade.show()
            self._shade.raise_()
            g = self.frameGeometry()       # 창 가운데에
            g.moveCenter(host.frameGeometry().center())
            self.move(g.topLeft())

    def hideEvent(self, e):
        if self._shade is not None:
            self._shade.hide()
            self._shade.deleteLater()
            self._shade = None
        super().hideEvent(e)

    def buttons(self, *items):
        """items: (문구, 함수, 주 버튼 여부)"""
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)
        for text, fn, primary in items:
            row.addWidget(button(text, fn, primary))
        self.lay.addSpacing(4)
        self.lay.addLayout(row)


class RestartDialog(_Dialog):
    def __init__(self, parent):
        super().__init__(parent, tr("restart.title"))
        self.setMinimumWidth(400)
        self.lay.addWidget(label(tr("restart.text"), "dlgtext", wrap=True))
        self.buttons((tr("restart.later"), self.reject, False), (tr("restart.now"), self.accept, True))


class StopRecordingDialog(_Dialog):
    """대시보드의 녹화 중지: 멈추면 그 게임을 다시 실행할 때까지 자동 녹화하지 않는다는 것을 알리고 묻는다."""

    def __init__(self, parent, game):
        super().__init__(parent, tr("stop.title"))
        self.setMinimumWidth(420)
        self.lay.addWidget(label(tr("stop.text").format(game=game), "dlgtext", wrap=True))
        self.buttons((tr("stop.cancel"), self.reject, False), (tr("stop.ok"), self.accept, True))


class RulesDialog(_Dialog):
    """게임 하나의 업로드 규칙(업로드 최소 길이, 자동 삭제 길이, 업로드 뒤 녹화본 삭제 시점)."""
    FIELDS = (("min_minutes", "set.min", 0, 600, 1), ("auto_delete_minutes", "set.autodel", 0, 60, 1),
              ("keep_minutes", "set.keep", 0, 0, 2))

    def __init__(self, parent, cfg, game):
        super().__init__(parent, tr("rules.title").format(g=game))
        self.cfg, self.game = cfg, game
        self.setMinimumWidth(720)
        self.lay.addWidget(label(tr("rules.note"), "dlgtext", wrap=True))
        over = self._current()
        unit = units()
        self.rows = {}
        grid = QFrame()
        grid.setObjectName("card")
        v = QVBoxLayout(grid)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        for i, (key, text, lo, hi, u) in enumerate(self.FIELDS):
            base = cfg["upload"].get(key, 0)
            custom = key in over
            if key == "keep_minutes":
                sp = KeepControl(over.get(key, base))
            else:
                sp = spin(over.get(key, base), lo, hi,
                          {"min_minutes": tr("unit.min_ge"), "auto_delete_minutes": tr("unit.min_le")}.get(key, unit[u]),
                          tr("unit.off") if key == "auto_delete_minutes" else None)
            sp.setEnabled(custom)
            ck = Check(tr("rules.use_default"))
            ck.setChecked(not custom)
            ck.toggled.connect(lambda on, s=sp, b=base: (s.setEnabled(not on), s.setValue(int(b)) if on else None))
            ctl = QWidget()
            cl = QHBoxLayout(ctl)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(14)
            cl.addWidget(sp)
            cl.addWidget(ck)        # '기본값' 체크는 줄마다 오른쪽 끝에 맞춘다
            if i:
                v.addWidget(hline())
            v.addWidget(setting_row(tr(text), "", ctl))
            self.rows[key] = (ck, sp)
        self.lay.addWidget(grid)
        self.buttons((tr("rules.reset"), self._reset, False), (tr("btn.cancel"), self.reject, False),
                     (tr("btn.save"), self._save, True))

    def _key(self):
        return next((k for k in self.cfg["upload"].get("game_overrides", {}) if k.lower() == self.game.lower()),
                    self.game)

    def _current(self):
        return dict(self.cfg["upload"].get("game_overrides", {}).get(self._key(), {}))

    def _reset(self):
        for ck, _sp in self.rows.values():
            ck.setChecked(True)

    def _save(self):
        new = {key: sp.value() for key, (ck, sp) in self.rows.items() if not ck.isChecked()}
        overs = self.cfg["upload"].setdefault("game_overrides", {})
        overs.pop(self._key(), None)
        if new:
            overs[self.game] = new
        config.save(self.cfg)
        self.accept()


_RUNTIME = ("java.exe", "javaw.exe", "python.exe", "pythonw.exe", "node.exe", "dotnet.exe")


class RuleDialog(_Dialog):
    """바뀐 길이 규칙으로 판정이 달라진 영상 하나: 왜 경고가 떴는지 보여 주고 적용할지 묻는다(취소하면 경고는 남는다)."""

    def __init__(self, parent, svc, key, act):
        super().__init__(parent, tr("rule.title"))
        self.svc, self.key, self.act = svc, key, act
        self.setMinimumWidth(520)
        up = svc.uploader
        rec = svc.store.data["recordings"].get(key) or {}
        game = rec.get("game") or ""
        mn, dl, _keep = up.rules_for(game)

        def minutes(sec):
            return tr("rule.minutes").format(n=f"{sec / 60:g}")
        from .widgets import fmt_len, fmt_time, rec_len, rec_time
        head = f"{game}  {fmt_time(rec_time(rec))}  ({fmt_len(rec_len(rec))})"
        top = QHBoxLayout()
        top.addWidget(label(head, "dlghead"), 1)
        path, url = rec.get("path", ""), rec.get("url")       # 원본이 있으면 원본, 없으면 유튜브
        if os.path.isfile(path) or url:
            local = os.path.isfile(path)
            go = QPushButton(tr("rule.open.file" if local else "rule.open.youtube"))
            go.setObjectName("link")
            go.setIcon(icons.icon("play" if local else "external", C["text2"], 14))
            go.setCursor(Qt.CursorShape.PointingHandCursor)
            go.clicked.connect(lambda: start_file(path) if os.path.isfile(path) else open_target(url))
            top.addWidget(go)
        self.lay.addLayout(top)
        old = rec.get("rule_at")
        if rec.get("status") == "excluded":
            was = tr("rule.was.exclude").format(old=minutes(old[0])) if old else tr("rule.was.exclude.unknown")
        else:
            was = tr("rule.was.upload")
        now = tr(f"rule.now.{act}").format(mn=minutes(mn), dl=minutes(dl))
        if any(k.lower() == game.lower() for k in (svc.cfg["upload"].get("game_overrides") or {})):
            now += f" ({tr('rule.game').format(g=game)})"
        for text in (was, now, tr("rule.ask")):
            self.lay.addWidget(label(text, "dlgtext", wrap=True))
        row = QHBoxLayout()
        row.setSpacing(8)
        if act != "delete":                # 판정과 상관없이 지울 수도 있게(되돌릴 수 없으니 왼쪽에 따로)
            row.addWidget(button(tr("rule.apply.delete"), self._delete), 0)
            row.itemAt(0).widget().setObjectName("danger")
        row.addStretch(1)
        row.addWidget(button(tr("rule.cancel"), self.reject))
        row.addWidget(button(tr(f"rule.apply.{act}"), self._apply, True))
        self.lay.addSpacing(4)
        self.lay.addLayout(row)

    def _delete(self):
        if self.svc.uploader.delete_original(self.key):
            self.accept()

    def _apply(self):
        self.svc.uploader.apply_rule_change(self.key)
        self.accept()


def not_a_game(path_lower, name):
    """게임 추가 후보에서 뺄 것: 자바, 파이썬 같은 실행기와 윈도우 앱 패키지 폴더 안의 보조 프로그램."""
    return (os.path.basename(path_lower) in _RUNTIME or "openjdk" in (name or "").lower()
            or "\\appdata\\local\\packages\\" in path_lower or "\\windowsapps\\" in path_lower)


class AddGameDialog(_Dialog):
    """게임 추가: 최근 게임처럼 실행된 프로그램, 다른 런처에 설치된 게임, 윈도우가 게임으로 알아본 프로그램 중에서
    고르거나, 실행 파일을 직접 고른다. 스팀 게임은 자동으로 녹화되니 후보에 넣지 않는다."""

    def __init__(self, parent, svc, on_added):
        super().__init__(parent, tr("add.title"))
        self.svc, self.cfg, self.on_added = svc, svc.cfg, on_added
        self.setMinimumSize(720, 560)
        self.lay.addWidget(label(tr("add.note"), "dlgtext", wrap=True))
        self.search = SearchBox(tr("games.search"), width=260)
        self.search.textChanged.connect(self._fill)
        self.lay.addWidget(self.search)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.area._smooth = SmoothWheel(self.area)
        inner = QWidget()
        inner.setObjectName("root")
        self.rows = QVBoxLayout(inner)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(0)
        self.area.setWidget(inner)
        self.lay.addWidget(self.area, 1)
        self._icons = {}
        self.candidates = self._candidates()
        self._fill()
        row = QHBoxLayout()
        row.addWidget(button(tr("add.browse"), self._browse, icon_name="folder"))
        row.addStretch(1)
        row.addWidget(button(tr("add.close"), self.accept))
        self.lay.addLayout(row)

    # -- 후보 ---------------------------------------------------------------------------------------
    def _candidates(self):
        """[(묶음, 이름, 경로)]. 이미 추가했거나 스팀 게임인 것은 뺀다."""
        from ..detect import win32
        from ..detect.catalog import source_name
        det = self.svc.detector
        out, seen = [], set()

        def add(group, name, path):
            pl = path.lower().rstrip("\\/")
            if not path or pl in seen or det.custom_game(pl) or not_a_game(pl, name):
                return
            entry, _ = det.catalog.launcher_entry(pl)
            if entry and entry.source == "steam":
                return
            seen.add(pl)
            out.append((group, name, path))

        for s in sorted(det.suggestions.values(), key=lambda s: s.get("last", 0), reverse=True):
            if os.path.exists(s["path"]):
                add(tr("add.group.recent"), s.get("name") or os.path.basename(s["path"]), s["path"])
        for _d, e in sorted(det.catalog.dirs, key=lambda t: t[1].name.lower()):
            if e.source != "steam" and e.name and os.path.isdir(e.dir):
                add(tr("add.group.launcher").format(src=source_name(e.source)), e.name, e.dir)
        for low in sorted(det.catalog.windows_exes):
            exe = det.catalog.windows_paths.get(low, low)
            if os.path.isfile(exe):
                add(tr("add.group.windows"), win32.product_name(exe) or os.path.splitext(os.path.basename(exe))[0], exe)
        return out

    def _icon(self, path):
        if path not in self._icons:
            target = path
            if os.path.isdir(path):         # 폴더면 안의 가장 큰 실행 파일(라이엇은 런처가 둔 아이콘)
                from ..artwork import _icon_for
                target = _icon_for(path, self.svc.detector.catalog) or path
            if target.lower().endswith((".ico", ".png")):
                pm = QPixmap(target)
            else:          # 가장 큰 아이콘(256)을 받아 줄인다(작은 크기를 달라면 16px 를 줄 때가 있다)
                pm = QFileIconProvider().icon(QFileInfo(target)).pixmap(QSize(256, 256))
            self._icons[path] = pm
        return self._icons[path]

    def _fill(self):
        while self.rows.count():
            it = self.rows.takeAt(0)
            w = it.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        q = self.search.text().strip().lower()
        group, shown = None, 0
        for g, name, path in self.candidates:
            if q and q not in name.lower() and q not in path.lower():
                continue
            if g != group:
                group = g
                self.rows.addWidget(label(g, "addgroup"))
            self.rows.addWidget(self._row(name, path))
            shown += 1
        if not shown:
            self.rows.addWidget(label(tr("add.empty"), "muted"))
        self.rows.addStretch(1)

    def _row(self, name, path):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(12)
        ic = QLabel()
        ic.setFixedSize(32, 32)
        pm = self._icon(path)
        if not pm.isNull():
            ic.setPixmap(pm.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        h.addWidget(ic)
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(ElideLabel(name, "gamename"))
        text.addWidget(ElideLabel(path, "rowdesc"))
        h.addLayout(text, 1)
        b = button(tr("add.add"), primary=True)
        b.clicked.connect(lambda _c, n=name, p=path, btn=b: self._add(n, p, btn))
        h.addWidget(b)
        return row

    # -- 추가 ---------------------------------------------------------------------------------------
    def _add(self, name, path, btn=None):
        det = self.cfg["detection"]
        det.setdefault("custom_games", []).append({"name": name, "path": path})
        k = path.lower()
        det["never_record"] = [x for x in det.get("never_record", []) if str(x).lower() != k]
        config.save(self.cfg)
        self.svc.log(f"게임 추가: {name} ({path})")
        if btn is not None:
            btn.setText(tr("add.added"))
            btn.setEnabled(False)
        self.on_added()

    def _browse(self):
        f, _ = QFileDialog.getOpenFileName(self, tr("add.browse"), "", "Game (*.exe)")
        if not f:
            return
        from ..detect import win32
        f = os.path.normpath(f)
        self._add(win32.product_name(f) or os.path.splitext(os.path.basename(f))[0], f)
        self.accept()
