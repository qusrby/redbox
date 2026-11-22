"""Redbox: 게임을 감지해 OBS 로 자동 녹화하고, 유튜브에 올린 뒤 PC 에서 정리하는 앱."""

APP_NAME = "Redbox"
APP_ID = "Redbox"
VERSION = "1.0.3"         # 주.부.수정. 릴리스 태그(v1.0.3)와 설치 파일 이름에 쓴다


def _build_number():
    """저장소 전체 커밋 수. 묶은 exe 는 빌드할 때 packaging/build.py 가 쓴 _build.py, 소스 실행은 git 에서 읽는다."""
    try:
        from ._build import BUILD
        return BUILD
    except ImportError:
        pass
    try:
        import os
        import subprocess
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        out = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=root, capture_output=True, text=True,
                             timeout=5, creationflags=0x08000000)       # CREATE_NO_WINDOW
        return int(out.stdout.strip()) if out.returncode == 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


BUILD = _build_number()
FULL_VERSION = f"{VERSION}.{BUILD}" if BUILD is not None else VERSION   # 화면, 로그, 윈도우 앱 목록에 보이는 버전
