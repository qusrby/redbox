"""로고(코드로 그린 상자)를 exe 와 설치 파일용 아이콘(redbox.ico)으로 만든다. 크기마다 따로 그려 작아도 또렷하게."""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def main(out=os.path.join(ROOT, "packaging", "redbox.ico")):
    from PIL import Image
    from PyQt6.QtCore import QBuffer, QIODevice
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)   # noqa: F841  (그리기에 필요)
    from redbox.ui.style import logo_pixmap

    images = []
    for s in SIZES:
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        logo_pixmap(s).save(buf, "PNG")
        images.append(Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA"))
    big = images[-1]
    big.save(out, format="ICO", sizes=[(s, s) for s in SIZES], append_images=images[:-1])
    return out


if __name__ == "__main__":
    print(main())
