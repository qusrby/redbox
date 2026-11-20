"""화면에 쓰는 선 아이콘. 24x24 칸에 그린 SVG 를 원하는 색과 크기로 그린다."""
from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from .style import C

_LINE = 'fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="square" stroke-linejoin="miter"'   # 각진 끝과 모서리

PATHS = {
    "video": '<rect x="3" y="5" width="18" height="14" {L}/><path d="M10 9v6l5-3z" fill="{c}"/>',
    # 대시보드: 상태를 보는 화면이라 모니터 안 맥박 선
    "dashboard": '<rect x="3" y="4.5" width="18" height="15" {L}/><path d="M6 12.5h3l2-4 2.5 7 2-3H18" {L}/>',
    # 게임: 각진 패드 몸체 + 십자 버튼 + 네모 버튼 두 개
    "games": '<path d="M3 7.5h18v9h-5.5l-2-2h-3l-2 2H3z" {L}/><path d="M7.5 9.5v4M5.5 11.5h4" {L}/>'
             '<rect x="14.6" y="9.1" width="1.9" height="1.9" fill="{c}"/>'
             '<rect x="17.1" y="11.6" width="1.9" height="1.9" fill="{c}"/>',
    "settings": '<path d="M4 7h9M18 7h2M4 17h2M11 17h9" {L}/><rect x="13" y="4.5" width="5" height="5" {L}/>'
                '<rect x="6" y="14.5" width="5" height="5" {L}/>',
    "search": '<circle cx="10.8" cy="10.8" r="6.3" {L}/><path d="M15.6 15.6l4.6 4.6" {L}/>',
    "grid": '<rect x="4" y="4" width="6.5" height="6.5" {L}/><rect x="13.5" y="4" width="6.5" height="6.5" {L}/>'
            '<rect x="4" y="13.5" width="6.5" height="6.5" {L}/><rect x="13.5" y="13.5" width="6.5" height="6.5" {L}/>',
    "list": '<path d="M9 6.5h11M9 12h11M9 17.5h11" {L}/><path d="M4.5 6.5h.01M4.5 12h.01M4.5 17.5h.01" '
            'fill="none" stroke="{c}" stroke-width="2.6" stroke-linecap="round"/>',
    "play": '<path d="M8 5.5v13l10.5-6.5z" fill="{c}"/>',
    "folder": '<path d="M3.5 7.5V18a1 1 0 0 0 1 1h15a1 1 0 0 0 1-1V9.5a1 1 0 0 0-1-1h-8l-2-2.5h-5a1 1 0 0 0-1 1z" {L}/>',
    "external": '<path d="M14 4h6v6M20 4l-8.5 8.5M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" {L}/>',
    "copy": '<rect x="8.5" y="8.5" width="11.5" height="11.5" rx="1" {L}/>'
            '<path d="M15.5 8.5V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v9.5a1 1 0 0 0 1 1h3.5" {L}/>',
    "warning": '<path d="M12 4l9 15.5H3z" {L}/><path d="M12 10v4" {L}/><circle cx="12" cy="16.8" r="1" fill="{c}"/>',
    "upload": '<path d="M12 15.5V4.5M7.5 9L12 4.5 16.5 9" {L}/><path d="M4.5 15v4.5h15V15" {L}/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5" {L}/>',
    "more": '<circle cx="6" cy="12" r="1.6" fill="{c}"/><circle cx="12" cy="12" r="1.6" fill="{c}"/>'
            '<circle cx="18" cy="12" r="1.6" fill="{c}"/>',
    "youtube": '<rect x="2.5" y="5.5" width="19" height="13" rx="3.5" fill="{c}"/><path d="M10 9v6l5.2-3z" fill="{bg}"/>',
    "plus": '<path d="M12 5v14M5 12h14" {L}/>',
    "image": '<rect x="3.5" y="5" width="17" height="14" {L}/><path d="M3.5 16l5-5 4 4 2.5-2.5 5.5 5.5" {L}/>'
             '<circle cx="15.5" cy="9.5" r="1.5" fill="{c}"/>',
    "alert": '<path d="M12 4.5v10" fill="none" stroke="{c}" stroke-width="2.6" stroke-linecap="square"/>'
             '<rect x="10.6" y="17.4" width="2.8" height="2.8" fill="{c}"/>',
    "edit": '<path d="M4.5 19.5h4l10-10-4-4-10 10z" {L}/><path d="M13 7l4 4" {L}/>',
    "trash": '<path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 12.5h9l1-12.5" {L}/>',
    "rules": '<path d="M5 4.5h14v15H5z" {L}/><path d="M8.5 9h7M8.5 12.5h7M8.5 16h4" {L}/>',
}


def _svg(name, color, bg=None):
    bg = bg or C["surface2"]          # 유튜브 표시 안 삼각형처럼 뚫린 부분의 색
    body = PATHS[name].replace("{L}", _LINE).replace("{c}", color).replace("{bg}", bg)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>'


def pixmap(name, color, size=18, bg=None):
    """화면 배율에 맞춰 선명하게 그린 아이콘 그림."""
    ratio = 2.0
    app = QGuiApplication.instance()
    if app is not None and app.primaryScreen() is not None:
        ratio = max(2.0, app.primaryScreen().devicePixelRatio())
    px = int(size * ratio)
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(_svg(name, color, bg).encode())).render(p, QRectF(0, 0, px, px))
    p.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name, color, size=18, on_color=None, disabled_color=None):
    """on_color: 눌린(선택) 상태 색, disabled_color: 꺼진 상태 색."""
    ic = QIcon()
    ic.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal, QIcon.State.Off)
    ic.addPixmap(pixmap(name, on_color or color, size), QIcon.Mode.Normal, QIcon.State.On)
    if disabled_color:
        ic.addPixmap(pixmap(name, disabled_color, size), QIcon.Mode.Disabled, QIcon.State.Off)
    return ic


_cache = {}


def paint(p, name, rect, color, bg=None):
    """QPainter 위에 그린다(카드 안 배지 등). 그린 그림은 기억해 두고 다시 쓴다(그릴 때마다 SVG 를 읽지 않게)."""
    rect = QRectF(rect)
    key = (name, color, bg, int(rect.width()))
    pm = _cache.get(key)
    if pm is None:
        pm = _cache[key] = pixmap(name, color, int(rect.width()), bg)
    p.drawPixmap(rect.toRect(), pm)
