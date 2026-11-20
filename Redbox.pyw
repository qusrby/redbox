# Redbox 실행 파일(콘솔 창 없이). 어느 폴더에서 실행해도 패키지를 찾도록 이 파일의 폴더를 경로에 넣는다.
#   pythonw Redbox.pyw            화면 앱
#   pythonw Redbox.pyw --hidden   트레이로만 시작(윈도우 시작 때)
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from redbox.__main__ import main  # noqa: E402

main(["ui"] + [a for a in sys.argv[1:] if a in ("--hidden", "--restart")])
