"""배포판 만들기: 아이콘 -> PyInstaller(폴더형 exe) -> Inno Setup 설치 파일.

  pip install -r requirements.txt -r packaging/requirements-build.txt
  python packaging/build.py            exe 와 설치 파일
  python packaging/build.py --no-setup exe 만

결과: dist/Redbox/Redbox.exe, dist/Redbox-Setup-<버전>.exe
설치 파일은 Inno Setup 6 의 ISCC.exe 가 필요하다(없으면 exe 까지만 만든다)."""
import glob
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "packaging")
DIST = os.path.join(ROOT, "dist")
WORK = os.path.join(ROOT, "build")
sys.path.insert(0, ROOT)


def find_iscc():
    cands = [os.environ.get("ISCC", "")]
    for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base:
            cands.append(os.path.join(base, "Programs", "Inno Setup 6", "ISCC.exe"))
            cands.append(os.path.join(base, "Inno Setup 6", "ISCC.exe"))
    return next((c for c in cands if c and os.path.isfile(c)), None)


def youtube_doc():
    """유튜브 API 구성 파일 하나만 넣는다(googleapiclient 전체 구성 파일은 100MB 가까이 된다)."""
    import googleapiclient
    return os.path.join(os.path.dirname(googleapiclient.__file__), "discovery_cache", "documents", "youtube.v3.json")


# 화면 앱에 쓰지 않는 Qt 파일: 소프트웨어 OpenGL, PDF, Qt 번역 파일
PRUNE = ("PyQt6/Qt6/bin/opengl32sw.dll", "PyQt6/Qt6/bin/Qt6Pdf.dll", "PyQt6/Qt6/plugins/imageformats/qpdf.dll",
         "PyQt6/Qt6/translations")


def prune(app_dir):
    docs = os.path.join(app_dir, "googleapiclient", "discovery_cache", "documents")
    for f in glob.glob(os.path.join(docs, "*.json")):      # 유튜브 것만 남긴다
        if os.path.basename(f) != "youtube.v3.json":
            os.remove(f)
    for rel in PRUNE:
        p = os.path.join(app_dir, *rel.split("/"))
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.isfile(p):
            os.remove(p)


def build_exe(icon):
    import PyInstaller.__main__
    fonts = os.path.join(ROOT, "redbox", "assets", "fonts")
    shutil.rmtree(os.path.join(DIST, "Redbox"), ignore_errors=True)
    PyInstaller.__main__.run([
        "--noconfirm", "--clean", "--windowed", "--name", "Redbox",
        "--icon", icon,
        "--add-data", f"{fonts}{os.pathsep}redbox/assets/fonts",
        "--add-data", f"{youtube_doc()}{os.pathsep}googleapiclient/discovery_cache/documents",
        "--exclude-module", "numpy",
        "--distpath", DIST, "--workpath", WORK, "--specpath", WORK,
        os.path.join(ROOT, "Redbox.pyw"),
    ])
    prune(os.path.join(DIST, "Redbox"))
    for f in ("LICENSE", "THIRD_PARTY_LICENSES.md"):
        shutil.copy(os.path.join(ROOT, f), os.path.join(DIST, "Redbox", f))
    return os.path.join(DIST, "Redbox", "Redbox.exe")


def build_setup(version):
    iscc = find_iscc()
    if not iscc:
        print("ISCC.exe 를 찾지 못해 설치 파일은 건너뜀(Inno Setup 6 설치 또는 ISCC 환경 변수)")
        return None
    for old in glob.glob(os.path.join(DIST, "Redbox-Setup-*.exe")):
        os.remove(old)
    subprocess.run([iscc, f"/DAppVersion={version}", f"/DSourceDir={os.path.join(DIST, 'Redbox')}",
                    f"/DOutputDir={DIST}", os.path.join(PKG, "redbox.iss")], check=True)
    return os.path.join(DIST, f"Redbox-Setup-{version}.exe")


def main():
    from redbox import VERSION
    from make_icon import main as make_icon
    icon = make_icon()
    exe = build_exe(icon)
    print("exe:", exe)
    if "--no-setup" not in sys.argv:
        setup = build_setup(VERSION)
        if setup:
            print("setup:", setup)


if __name__ == "__main__":
    sys.path.insert(0, PKG)
    main()
