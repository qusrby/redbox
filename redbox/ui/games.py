"""게임: 스팀 게임(자동 녹화), 직접 추가한 게임, 녹화 기록만 있는 게임. 게임마다 녹화 여부와 업로드 규칙."""
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QMenu, QScrollArea, QVBoxLayout, QWidget

from .. import artwork, config
from ..detect.catalog import source_name
from ..paths import start_file
from ..i18n import tr
from ..recorder import naming
from . import icons
from .dialogs import AddGameDialog, RulesDialog
from .style import C
from .widgets import Check, ElideLabel, IconButton, SearchBox, SmoothWheel, Tabs, button, label

ART_W, ART_H = 120, 56
ROW_H = 74            # 영상 목록과 같은 줄 높이
LEFT = 15             # 머리 글자와 그림의 왼쪽 여백(영상 목록과 같게)
ART_GAP = 20          # 그림과 게임 이름 사이(영상 목록과 같게)
RULE_W, UPRULE_W, BTN_W, MORE_W = 84, 200, 34, 34
SCROLLBAR_W = 16


class GameRow(QWidget):
    """게임 한 줄: 그림 | 이름과 출처 | 녹화 여부 | 업로드 규칙 | 규칙 변경 | 더 보기(직접 추가한 게임). 오버 = 줄 전체 밝게."""

    def __init__(self, page, name, kind, key):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFixedHeight(ROW_H)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(LEFT, 0, 16, 0)
        lay.setSpacing(16)
        art = QLabel()
        art.setFixedSize(ART_W, ART_H)
        pm = page.art.game_thumb(name, ART_W * 2, ART_H * 2).copy()    # 같이 쓰는 그림을 바꾸지 않게 복사본에
        pm.setDevicePixelRatio(2.0)
        art.setPixmap(pm)
        lay.addWidget(art)
        lay.addSpacing(ART_GAP - 16)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addStretch(1)
        sub = page.platform(kind, key)          # 이름 아래에는 플랫폼만(설치 여부는 오른쪽 칸에)
        for t, obj in ((name, "gamename"), (sub, "rowdesc")):
            text.addWidget(ElideLabel(t, obj))     # 긴 이름은 끝을 줄여 다른 칸을 밀어내지 않게
        text.addStretch(1)
        lay.addLayout(text, 1)
        if key:
            box = QWidget()
            box.setFixedWidth(RULE_W)
            bl = QHBoxLayout(box)
            bl.setContentsMargins(0, 0, 0, 0)
            check = Check()
            check.setChecked(page.rule_of(key) != "never")
            check.toggled.connect(lambda on, k=key: page.set_rule(k, "auto" if on else "never"))
            bl.addWidget(check)
            bl.addStretch(1)
            lay.addWidget(box)
        else:
            none = label(tr("games.not_installed"), "rowdesc")
            none.setFixedWidth(RULE_W)
            lay.addWidget(none)
        summary, custom = page.rule_summary(name)
        up = label(summary, "uprule_custom" if custom else "rowdesc", wrap=True)
        up.setFixedWidth(UPRULE_W)
        lay.addWidget(up)
        # 맨 오른쪽은 늘 업로드 규칙 수정 버튼, 그 왼쪽은 직접 추가한 게임의 '⋯'(없으면 같은 폭의 빈 칸)
        if kind == "custom":
            more = IconButton("more", tr("games.more"), size=MORE_W)
            more.clicked.connect(lambda: page.custom_menu(name, key, more))
            lay.addWidget(more)
        else:                      # 빈 칸도 위젯으로 둬야 줄 간격이 같게 붙어 칸 위치가 맞는다
            blank = QWidget()
            blank.setFixedWidth(MORE_W)
            lay.addWidget(blank)
        b = button("", lambda: page.edit_rules(name), icon_name="edit")   # 테두리 있는 정사각 버튼, 아이콘만
        b.setObjectName("iconbtn")
        b.setFixedWidth(BTN_W)
        b.setToolTip(tr("btn.uprule"))
        lay.addWidget(b)

    def paintEvent(self, _e):
        p = QPainter(self)
        if self.underMouse():
            p.fillRect(self.rect(), QColor(C["row_hover"]))
        p.fillRect(0, self.height() - 1, self.width(), 1, QColor(C["border"]))   # 줄 구분선(영상 목록과 같게)
        p.end()

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


class GamesPage(QWidget):
    def __init__(self, svc, art):
        super().__init__()
        self.svc, self.cfg, self.art = svc, svc.cfg, art
        self.filter, self.query = "all", ""
        self._sig = None
        v = QVBoxLayout(self)
        v.setContentsMargins(32, 0, 32, 0)
        v.setSpacing(16)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.tabs = Tabs([("all", tr("games.filter.all")), ("steam", tr("games.filter.steam")),
                          ("custom", tr("games.filter.custom"))], "all")
        self.tabs.changed.connect(self._set_filter)
        bar.addWidget(self.tabs, 1)
        self.search = SearchBox(tr("games.search"))
        self.search.textChanged.connect(self._set_query)
        bar.addWidget(self.search)
        bar.addWidget(button(tr("games.add"), self.add_game, primary=True, icon_name="plus"))
        v.addLayout(bar)

        head = QWidget()
        head.setObjectName("listhead")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(LEFT, 0, 16 + SCROLLBAR_W, 0)    # 아래 목록의 스크롤 막대 자리만큼
        hl.setSpacing(16)
        hl.addWidget(label(tr("col.game"), "colhead"), 1)    # 영상 목록처럼 칸 왼쪽 끝(그림 시작점)에 맞춘다
        for text, w in ((tr("col.rule"), RULE_W), (tr("col.uprule"), UPRULE_W)):
            lb = label(text, "colhead")
            lb.setFixedWidth(w)
            hl.addWidget(lb)
        hl.addSpacing(BTN_W + 16 + MORE_W + 16)
        head.setFixedHeight(36)
        listbox = QVBoxLayout()    # 머리줄 바로 아래에서 목록이 시작(영상 목록과 같게)
        listbox.setSpacing(0)
        listbox.addWidget(head)
        v.addLayout(listbox, 1)

        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.area._smooth = SmoothWheel(self.area)
        self.list = QWidget()
        self.list.setObjectName("root")
        self.rows = QVBoxLayout(self.list)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(0)
        self.area.setWidget(self.list)
        listbox.addWidget(self.area, 1)
        self.fill()

    def platform(self, kind, key):
        """게임 이름 아래 플랫폼 이름. 직접 추가한 게임은 설치한 런처(Riot 등)를 알면 그 이름."""
        if kind == "steam":
            return "Steam"
        k = os.path.normcase(os.path.normpath(key or ""))
        for _d, e in self.svc.detector.catalog.dirs:
            d = os.path.normcase(os.path.normpath(e.dir)) if e.dir else ""
            if d and (k == d or k.startswith(d + os.sep)):
                return source_name(e.source)
        return tr("games.kind.custom")

    # -- 녹화 여부 ----------------------------------------------------------------------------------
    def rule_of(self, key):
        det = self.cfg["detection"]
        return "never" if key.lower() in [str(x).lower() for x in det.get("never_record", [])] else "auto"

    def set_rule(self, key, rule):
        det = self.cfg["detection"]
        k = key.lower()
        det["never_record"] = [x for x in det.get("never_record", []) if str(x).lower() != k]
        if rule == "never":
            det["never_record"].append(key)
        config.save(self.cfg)

    # -- 업로드 규칙 ---------------------------------------------------------------------------------
    def _override(self, game):
        return next((v for k, v in self.cfg["upload"].get("game_overrides", {}).items() if k.lower() == game.lower()), {})

    def rule_summary(self, game):
        """(문구, 게임별 규칙이 있는지)"""
        over = self._override(game)
        if not over:
            return tr("uprule.default"), False
        parts = []
        if "min_minutes" in over:
            parts.append(tr("uprule.min").format(v=over["min_minutes"]))
        if "auto_delete_minutes" in over:
            parts.append(tr("uprule.del").format(v=over["auto_delete_minutes"]))
        if "keep_days" in over:
            parts.append(tr("uprule.keep").format(v=over["keep_days"]) if over["keep_days"] else tr("uprule.keep0"))
        return ", ".join(parts), True

    def edit_rules(self, game):
        if RulesDialog(self.window(), self.cfg, game).exec():
            self.fill()

    # -- 직접 추가 -----------------------------------------------------------------------------------
    def add_game(self):
        AddGameDialog(self.window(), self.svc, self._added).exec()

    def _added(self):
        self.svc.detector._names.clear()
        self.art.recollect()
        self.fill()

    def custom_menu(self, name, path, anchor):
        m = QMenu(self)
        m.addAction(icons.icon("image", C["text2"], 16), tr("games.set_image"), lambda: self._set_image(name, path))
        m.addAction(icons.icon("folder", C["text2"], 16), tr("games.open_folder"),
                    lambda: start_file(path if os.path.isdir(path) else os.path.dirname(path)))
        m.addSeparator()
        m.addAction(icons.icon("trash", C["text2"], 16), tr("games.remove"), lambda: self._remove(path))
        m.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _set_image(self, name, path):
        f, _ = QFileDialog.getOpenFileName(self, tr("games.set_image"), "", "Image (*.jpg *.jpeg *.png *.webp)")
        if f:
            artwork.set_custom_image(name, path, f)
            self.art.updated.emit()        # 대시보드, 영상 목록, 카드까지 새 그림으로 다시 그린다

    def _remove(self, path):
        det = self.cfg["detection"]
        det["custom_games"] = [g for g in det.get("custom_games", []) if str(g.get("path", "")).lower() != path.lower()]
        config.save(self.cfg)
        self.svc.detector._names.clear()
        self.fill()

    # -- 목록 -------------------------------------------------------------------------------------
    def _set_filter(self, val):
        self.filter = val
        self.fill()

    def _set_query(self, text):
        self.query = text.strip().lower()
        self.fill()

    def game_list(self):
        """[(게임 이름, 종류 steam/custom, 규칙 키(설치 폴더나 실행 파일), 지금 설치 안 된 스팀 게임이면 None)].
        녹화 기록만 있는 게임도 스팀 게임으로 본다(스팀 전용 앱).
        이름은 녹화 폴더에 쓰는 이름(업로드 규칙도 이 이름 기준)."""
        match_root = self.cfg["extras"].get("match_folder_names", "")
        seen = {}
        for g in self.cfg["detection"].get("custom_games", []):
            if g.get("name") and g.get("path"):
                seen.setdefault(g["name"].lower(), (g["name"], "custom", g["path"]))
        for _d, e in self.svc.detector.catalog.dirs:
            if e.source == "steam" and e.name:
                name = naming.folder_name(e.name, match_root)
                seen.setdefault(name.lower(), (name, "steam", e.dir))
        for r in self.svc.store.data["recordings"].values():
            g = r.get("game")
            if g and g.lower() not in seen:
                seen[g.lower()] = (g, "steam", None)
        # 녹화 여부를 정할 수 있는 게임(설치된 스팀 게임, 직접 추가한 게임)을 위로, 그 안에서는 이름 순
        return sorted(seen.values(), key=lambda t: (t[2] is None, t[0].lower()))

    def fill(self, force=False):
        """바뀐 게 있을 때만 다시 만든다. 비교는 가볍게(게임 목록 자체를 만드는 데 시간이 든다)."""
        det, up = self.cfg["detection"], self.cfg["upload"]
        sig = (self.filter, self.query, self.svc.detector.catalog_at, len(self.svc.store.data["recordings"]),
               repr(det.get("never_record")), repr(det.get("custom_games")), repr(up.get("game_overrides")))
        if sig == self._sig and not force:
            return
        self._sig = sig
        games = self.game_list()
        while self.rows.count():
            it = self.rows.takeAt(0)
            w = it.widget()
            if w:
                w.hide()               # 지울 때까지 화면에 남지 않게
                w.setParent(None)
                w.deleteLater()
        counts = {"all": len(games)}
        for kind in ("steam", "custom"):
            counts[kind] = sum(1 for g in games if g[1] == kind)
        self.tabs.set_counts(counts)
        for name, kind, key in games:
            if self.query and self.query not in name.lower():
                continue
            if self.filter != "all" and kind != self.filter:
                continue
            self.rows.addWidget(GameRow(self, name, kind, key))
        self.rows.addStretch(1)
