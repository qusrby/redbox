"""화면 색과 스타일, 앱 아이콘(그려서 만든다)."""
from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

# 스팀처럼 어두운 화면 한 가지. 순수한 검정 바탕에 흰 글자는 대비가 너무 세서 눈이 아프다.
# 바탕은 짙은 회색, 글자는 살짝 낮춘 흰색.
C = {
    "bg": "#18191c", "surface": "#1f2024", "surface2": "#26282c", "surface3": "#2e3035", "border": "#2f3136",
    "border2": "#3f4248", "row_hover": "#25272b", "check_border": "#5d6169", "scroll": "#4b4f57",
    "text": "#e2e4e8", "text2": "#aeb2ba", "muted": "#878c95", "ok": "#4fb886",
    "accent": "#5c97de", "accent_hover": "#78aae6", "accent_bg": "#1f2a38", "on_accent": "#101114",
    "neg": "#f07373", "warn": "#e2b54f", "neg_bg": "#2c1c1f", "neg_border": "#55292e", "rec": "#e5484d",
}

FONT = "'Pretendard', 'Malgun Gothic', 'Segoe UI', sans-serif"


QSS = f"""
* {{ font-family: {FONT}; font-size: 14px; font-weight: 500; color: {C['text']}; }}
QWidget#root, QDialog {{ background: {C['bg']}; }}
QLabel#h1 {{ font-size: 20px; font-weight: 800; }}
QLabel#h2 {{ font-size: 15px; font-weight: 700; }}
QLabel#muted {{ color: {C['muted']}; }}
QLabel#err {{ color: {C['neg']}; }}
QWidget#sidebar {{ background: {C['surface']}; border-right: 1px solid {C['border']}; }}
QLabel#brand {{ font-size: 20px; font-weight: 800; }}
QPushButton#nav {{ background: transparent; border: none; border-left: 3px solid transparent; text-align: left;
                   padding: 10px 12px; color: {C['text2']}; font-size: 14px; font-weight: 600; }}
QPushButton#nav:hover {{ color: {C['text']}; background: {C['surface2']}; }}
QPushButton#nav:pressed {{ background: {C['bg']}; }}
QPushButton#nav:checked {{ color: {C['text']}; background: {C['surface3']}; border-left: 3px solid {C['accent']};
                           font-weight: 700; }}
QLabel#pagetitle {{ font-size: 22px; font-weight: 700; }}
QLabel#pagesub {{ color: {C['muted']}; font-size: 13px; padding-top: 4px; }}
QFrame#statepanel {{ background: {C['surface2']}; border: 1px solid {C['border']}; }}
QLabel#statebig {{ font-size: 14px; font-weight: 800; }}
QLabel#statetime {{ font-size: 13px; font-weight: 700; color: {C['rec']}; }}
QLabel#statesub {{ font-size: 12px; color: {C['text2']}; }}
QLabel#srowname {{ font-size: 12px; color: {C['muted']}; }}
QLabel#srowval {{ font-size: 12px; font-weight: 600; }}
QFrame#hero {{ background: {C['surface']}; }}
QLabel#herostate {{ font-size: 13px; font-weight: 800; }}
QLabel#herobig {{ font-size: 26px; font-weight: 700; }}
QLabel#herometa {{ font-size: 13px; color: {C['text2']}; }}
QLabel#herotime {{ color: #ffffff; background: {C['rec']}; padding: 4px 12px; }}
QFrame#tile {{ background: {C['surface']}; border: 1px solid {C['border']}; }}
QLabel#tilename {{ font-size: 12px; color: {C['muted']}; font-weight: 700; }}
QLabel#tilevalue {{ font-size: 16px; font-weight: 700; }}
QLabel#tilenote {{ font-size: 12px; color: {C['text2']}; }}
QPushButton#link {{ background: transparent; border: none; color: {C['text2']}; padding: 4px 0; font-weight: 600; }}
QPushButton#link:hover {{ color: {C['accent']}; }}
QFrame#banner {{ background: {C['neg_bg']}; border: 1px solid {C['neg_border']}; }}
QLabel#bannertitle {{ font-weight: 800; color: {C['neg']}; }}
QLabel#bannerdesc {{ color: {C['text2']}; }}
QPushButton#tab {{ background: transparent; border: none; border-bottom: 2px solid transparent; padding: 7px 4px;
                   margin-right: 14px; color: {C['muted']}; font-weight: 600; }}
QPushButton#tab:hover {{ color: {C['text']}; border-bottom: 2px solid {C['border2']}; }}
QPushButton#tab:checked {{ color: {C['text']}; border-bottom: 2px solid {C['accent']}; font-weight: 700; }}
QLineEdit#search {{ padding: 0 8px; }}
QLabel#dayhead {{ font-size: 16px; font-weight: 800; }}
QLabel#daysub {{ color: {C['muted']}; font-size: 12px; padding-bottom: 2px; }}
QLabel#emptytitle {{ font-size: 17px; font-weight: 800; }}
QLabel#gamename {{ font-size: 14px; font-weight: 700; }}
QLabel#uprule_custom {{ color: {C['accent']}; font-size: 12px; }}
QLabel#addgroup {{ color: {C['muted']}; font-size: 12px; font-weight: 700; padding: 14px 10px 6px 10px; }}
QLabel#colhead {{ color: {C['muted']}; font-size: 12px; font-weight: 700; }}
QWidget#listhead {{ border-bottom: 1px solid {C['border']}; }}
QLabel#toast {{ background: {C['surface3']}; border: 1px solid {C['border2']}; padding: 10px 18px; color: {C['text']}; }}
QLabel#dlgtext {{ color: {C['text2']}; font-size: 14px; }}
QToolTip {{ background: {C['surface3']}; color: {C['text']}; border: 1px solid {C['border2']}; padding: 6px 8px; }}
QComboBox {{ combobox-popup: 0; }}
QComboBox QAbstractItemView {{ background: {C['surface2']}; border: 1px solid {C['border2']}; outline: none; padding: 4px; }}
QComboBox QAbstractItemView::item {{ padding: 7px 10px; min-height: 18px; }}
QComboBox QAbstractItemView::item:hover {{ background: {C['surface3']}; }}
QComboBox QAbstractItemView::item:selected {{ background: {C['accent_bg']}; color: {C['accent']}; }}
QWidget#statusbar {{ background: {C['surface']}; border-top: 1px solid {C['border']}; }}
QLabel#status {{ color: {C['muted']}; font-size: 12px; }}
QDialog#dialog {{ background: {C['bg']}; border: 1px solid {C['border2']}; }}
QFrame#numbox {{ background: {C['surface2']}; border: 1px solid {C['border2']}; }}
QFrame#numbox[focus="true"] {{ border-color: {C['accent']}; }}
QFrame#numbox:disabled {{ background: {C['bg']}; border-color: {C['border']}; }}
QSpinBox#numspin {{ background: transparent; border: none; padding: 0; }}
QSpinBox#numspin:disabled {{ color: {C['muted']}; }}
QLabel#numunit {{ color: {C['text2']}; }}
QLabel#numunit:disabled {{ color: {C['muted']}; }}
QFrame#hline {{ background: {C['border']}; border: none; }}
QLabel#rowtitle {{ font-weight: 600; }}
QLabel#rowdesc {{ color: {C['muted']}; font-size: 12px; }}
QLabel#setupdesc {{ color: {C['text2']}; font-size: 14px; }}
QLabel#setupnote {{ color: {C['warn']}; font-size: 13px; }}
QLabel#steptitle {{ color: {C['muted']}; font-size: 12px; font-weight: 700; }}
QLabel#stepvalue {{ font-size: 17px; font-weight: 800; }}
QLabel#stepnote {{ color: {C['text2']}; font-size: 12px; }}
QLabel#arrow {{ color: {C['muted']}; font-size: 22px; font-weight: 700; }}
QFrame#card {{ background: {C['surface']}; border: 1px solid {C['border']}; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {C['muted']}; padding: 10px 18px; border: none;
               border-bottom: 2px solid transparent; font-weight: 600; }}
QTabBar::tab:selected {{ color: {C['text']}; border-bottom: 2px solid {C['accent']}; }}
QTabBar::tab:hover {{ color: {C['text']}; }}
QPushButton {{ background: {C['surface2']}; border: 1px solid {C['border2']}; padding: 0 14px; }}
QPushButton:hover {{ border-color: {C['accent']}; color: {C['accent']}; }}
QPushButton:pressed {{ background: {C['bg']}; border-color: {C['accent']}; color: {C['accent']}; }}
QPushButton:disabled {{ color: {C['muted']}; border-color: {C['border']}; }}
QPushButton#primary {{ background: {C['accent']}; border-color: {C['accent']}; color: {C['on_accent']}; font-weight: 700; }}
QPushButton#primary:hover {{ background: {C['accent_hover']}; color: {C['on_accent']}; }}
QPushButton#primary:pressed {{ background: {C['accent']}; border-color: {C['text']}; color: {C['on_accent']}; }}
QPushButton#primary:disabled {{ background: {C['surface2']}; border-color: {C['border2']}; color: {C['text2']}; font-weight: 600; }}
QTableWidget QPushButton {{ padding: 2px 10px; }}
QPushButton#iconbtn {{ padding: 0; }}
QPushButton#seg {{ padding: 0 12px; background: {C['surface2']}; border: 1px solid {C['border2']}; color: {C['text2']}; }}
QPushButton#seg:hover {{ background: {C['surface3']}; border-color: {C['border2']}; color: {C['text']}; }}
QPushButton#seg:checked {{ background: {C['accent']}; border-color: {C['accent']}; color: {C['on_accent']}; font-weight: 700; }}
QPushButton#seg:checked:hover {{ background: {C['accent_hover']}; border-color: {C['accent_hover']}; color: {C['on_accent']}; }}
QPushButton#seg:disabled {{ color: {C['muted']}; background: {C['bg']}; border-color: {C['border']}; }}
QPushButton#seg:checked:disabled {{ color: {C['text2']}; background: {C['border2']}; border-color: {C['border2']}; font-weight: 700; }}
QLineEdit, QSpinBox {{ background: {C['surface2']}; border: 1px solid {C['border2']}; padding: 6px 8px; }}
QLineEdit:focus, QSpinBox:focus {{ border-color: {C['accent']}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {C['border2']}; background: {C['surface2']}; }}
QCheckBox::indicator:checked {{ background: {C['accent']}; border-color: {C['accent']}; }}
QTableWidget {{ background: transparent; border: none; gridline-color: transparent; }}
QTableWidget::item {{ padding: 4px 12px; border-bottom: 1px solid {C['border']}; }}
QHeaderView {{ background: transparent; border: none; }}
QHeaderView::section {{ background: transparent; color: {C['muted']}; border: none; border-bottom: 1px solid {C['border']};
                        padding: 6px 15px; font-size: 12px; font-weight: 700; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 16px; margin: 4px 0; }}
QTableView QScrollBar:vertical {{ margin-top: 40px; }}
QScrollBar::handle:vertical {{ background: {C['scroll']}; margin: 0 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {C['accent']}; }}
QScrollBar[empty="true"]::handle:vertical {{ background: transparent; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QMenu {{ background: {C['surface2']}; border: 1px solid {C['border2']}; padding: 4px 0; }}
QMenu::item {{ padding: 8px 24px 8px 12px; }}
QMenu::item:selected {{ background: {C['surface3']}; color: {C['text']}; }}
QMenu::item:disabled {{ color: {C['muted']}; }}
QMenu::icon {{ padding-left: 12px; }}
QMenu::separator {{ height: 1px; background: {C['border2']}; margin: 4px 0; }}
"""


_fonts_loaded = False


def load_fonts():
    """앱에 넣어 둔 Pretendard(Medium, SemiBold, Bold, ExtraBold)를 등록한다. 글꼴을 설치하지 않은 PC 에서도 같은 모양이 되게."""
    global _fonts_loaded
    if _fonts_loaded:
        return
    _fonts_loaded = True
    import glob
    from PyQt6.QtGui import QFontDatabase
    from .. import paths
    for f in glob.glob(paths.resource("redbox", "assets", "fonts", "*.otf")):
        QFontDatabase.addApplicationFont(f)


def app_font():
    """Pretendard Medium + 강한 힌팅. Regular 굵기에 기본 힌팅이면 작은 글자에서 '드' 같은 글자의 가로획이 사라진다."""
    load_fonts()
    f = QFont("Pretendard", 10)
    f.setWeight(QFont.Weight.Medium)
    f.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


LOGO = ('<rect width="24" height="24" fill="{r}"/>'      # 각진 빨간 타일 위 선으로 그린 상자
        '<path d="M12 4.5l7 3.8v7.4l-7 3.8-7-3.8V8.3z" fill="none" stroke="#fff" stroke-width="1.9" stroke-linejoin="miter"/>'
        '<path d="M5 8.3l7 3.8 7-3.8M12 12.1v7.4" fill="none" stroke="#fff" stroke-width="1.9"/>')
REC_DOT = "#ff2a2a"     # 트레이 녹화 표시(OBS 처럼 왼쪽 아래 빨간 점)


def logo_pixmap(size, recording=False):
    """로고 그림 한 장(size 픽셀). recording 이면 왼쪽 아래에 빨간 점, 타일과 섞이지 않게 둘레를 투명하게 판다."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">' + LOGO.replace("{r}", C["rec"]) + "</svg>"
    QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(0, 0, size, size))
    if recording:
        d, gap = size * 0.34, size * 0.07
        r = QRectF(0, size - d, d, d)
        p.setPen(Qt.PenStyle.NoPen)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.setBrush(QColor(0, 0, 0))
        p.drawEllipse(r.adjusted(-gap, -gap, gap, gap))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setBrush(QColor(REC_DOT))
        p.drawEllipse(r)
    p.end()
    return pm


def app_icon(recording=False, size=None):
    """창, 작업표시줄, 트레이용 아이콘. 크기별로 따로 그려 작게 줄어도 흐려지지 않게 한다."""
    icon = QIcon()
    for s in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(logo_pixmap(s, recording))
    return icon
