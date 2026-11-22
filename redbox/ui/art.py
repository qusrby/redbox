"""카드와 목록에 쓰는 게임 그림. 그림은 artwork 가 플랫폼(Steam, Xbox, Epic, Ubisoft, Riot)에서 모아 보관한다.
그림이 아이콘뿐이면 색 바탕 위에 아이콘, 아무것도 없으면 머리글자 타일."""
import hashlib
import os
import re
import threading

from PyQt6.QtCore import QObject, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPixmap

from .. import artwork

CARD_W, CARD_H = 920, 430        # 스팀 대표 그림(460x215) 비율. 제목이 잘리지 않게


def cover(pm, w, h):
    """그림을 w x h 칸에 꽉 차게(넘치는 쪽은 가운데 기준으로 잘라) 맞춘다."""
    if pm is None or pm.isNull():
        return None
    s = pm.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    return s.copy((s.width() - w) // 2, (s.height() - h) // 2, w, h)


def _hue(name):
    return int(hashlib.md5(name.lower().encode("utf-8")).hexdigest()[:4], 16) % 360


def _tile(name, w, h):
    pm = QPixmap(w, h)
    p = QPainter(pm)
    g = QLinearGradient(0, 0, w, h)
    hue = 213 + _hue(name or "?") % 13 - 6     # 테마 파란색(#2a7de1) 계열. 이름마다 색조만 조금씩 달리
    g.setColorAt(0, QColor.fromHsl(hue, 170, 112))
    g.setColorAt(1, QColor.fromHsl(hue, 150, 40))
    p.fillRect(0, 0, w, h, g)
    p.end()
    return pm


def placeholder(name, w=CARD_W, h=CARD_H, icon=None):
    """그림이 없는 게임: 이름에서 정한 색 바탕 + 아이콘(있으면) 또는 이름(작으면 머리글자)."""
    pm = _tile(name, w, h)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    if icon is not None and not icon.isNull():
        s = int(h * 0.62)
        ic = icon.scaled(s, s, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap((w - ic.width()) // 2, (h - ic.height()) // 2, ic)
        p.end()
        return pm
    f = QFont("Pretendard")
    f.setWeight(QFont.Weight.Bold)
    if h < 160:          # 작은 그림은 이름 대신 머리글자(AC, CU)를 크게
        words = [x for x in re.split(r"[\s:\-]+", name or "?") if x and x[0].isalnum()]
        words = [x for x in words if x[0].isupper() or x[0].isdigit()] or words   # of, the 같은 작은 낱말 빼기
        text = "".join(x[0] for x in words[:2]).upper() or "?"
        f.setPixelSize(int(h * 0.42))
    else:
        text = name or ""
        f.setPixelSize(max(12, int(h * 0.11)))
    p.setFont(f)
    p.setPen(QColor(255, 255, 255, 215))
    p.drawText(QRectF(w * 0.08, 0, w * 0.84, h), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)
    p.end()
    return pm


class Art(QObject):
    """게임 이름 -> 그림. 만든 그림은 기억해 둔다. 앱이 켜지면 뒤에서 플랫폼 그림을 모으고, 새로 생기면 updated."""
    updated = pyqtSignal()

    def __init__(self, catalog_fn, custom_fn=lambda: [], recorded_fn=lambda: [], log=None):
        super().__init__()
        self.catalog_fn, self.custom_fn, self.recorded_fn, self.log = catalog_fn, custom_fn, recorded_fn, log
        self._index = artwork.load_index()
        self._card, self._small = {}, {}
        self.updated.connect(self.reload)
        self.recollect()

    def recollect(self):
        """그림을 다시 모은다(앱 시작, 게임을 직접 추가했을 때). 뒤에서 돌고, 바뀌면 updated."""
        threading.Thread(target=self._collect, daemon=True, name="artwork").start()

    def _collect(self):
        try:
            if artwork.collect(self.catalog_fn(), list(self.custom_fn()), list(self.recorded_fn()), self.log):
                self.updated.emit()
        except Exception as e:          # 그림을 못 모아도 앱은 그대로
            if self.log:
                self.log(f"[오류] 게임 그림 모으기: {e}")

    def reload(self):
        self._index = artwork.load_index()
        self._card.clear()
        self._small.clear()

    def game_files(self, game):
        return artwork.stored(artwork.lookup(self._index, game))

    def _icon(self, files):
        """아이콘: 보관한 .ico/.png, 없으면 실행 파일에서 뽑아(256px) icon.png 로 보관해 둔다(게임을 지워도 남게)."""
        if files.get("icon"):
            return QPixmap(files["icon"])
        src = files.get("iconsrc")
        if src and os.path.isfile(src):
            from PyQt6.QtCore import QFileInfo, QSize
            from PyQt6.QtWidgets import QFileIconProvider
            pm = QFileIconProvider().icon(QFileInfo(src)).pixmap(QSize(256, 256))
            if not pm.isNull():
                path = os.path.join(files["_dir"], "icon.png")
                if pm.save(path, "PNG"):
                    files["icon"] = path
                return pm
        return None

    def game_card(self, game):
        """16:9 게임 그림. 플랫폼 그림을 그대로(합성 없이) 칸에 맞춰 자른다:
        제목이 박힌 대표 그림(header) > 배경(hero) > 아이콘 타일 > 없으면 None."""
        key = artwork.norm(game)
        if key in self._card:
            return self._card[key]
        files, pm = self.game_files(game), None
        src = files.get("header") or files.get("hero")
        if src:
            pm = cover(QPixmap(src), CARD_W, CARD_H)
        if pm is None and (files.get("icon") or files.get("iconsrc")):
            pm = placeholder(game, CARD_W, CARD_H, self._icon(files))
        self._card[key] = pm
        return pm

    def game_thumb(self, game, w, h):
        """목록의 작은 그림: 머리 그림 > 배경 > 아이콘 타일 > 머리글자 타일."""
        key = (artwork.norm(game), w, h)
        if key not in self._small:
            files = self.game_files(game)
            src = files.get("header") or files.get("hero")
            pm = cover(QPixmap(src), w, h) if src else None
            self._small[key] = pm if pm is not None else placeholder(game, w, h, self._icon(files))
        return self._small[key]

    def game_portrait(self, game, w, h):
        """세로 표지(스팀 600x900): 영상 목록과 카드에서 게임을 알아보게. 없으면 아이콘 타일, 머리글자 타일."""
        key = ("portrait", artwork.norm(game), w, h)
        if key not in self._small:
            files = self.game_files(game)
            pm = cover(QPixmap(files["portrait"]), w, h) if files.get("portrait") else None
            self._small[key] = pm if pm is not None else placeholder(game, w, h, self._icon(files))
        return self._small[key]

    def record_image(self, game):
        """녹화 카드 그림: 게임 그림, 없으면 기본 타일."""
        pm = self.game_card(game)
        if pm is None:
            gk = "\0" + artwork.norm(game)
            if gk not in self._card:
                self._card[gk] = placeholder(game)
            pm = self._card[gk]
        return pm
