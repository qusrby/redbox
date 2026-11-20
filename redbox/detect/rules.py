"""기본 제외 목록: 전체 화면이 되거나 게임 폴더 안에 있어도 녹화하지 않을 프로그램."""
import os
import re

# 실행 파일 이름(소문자)
EXCLUDE_EXES = {
    # 브라우저
    "chrome.exe", "msedge.exe", "firefox.exe", "whale.exe", "opera.exe", "brave.exe", "vivaldi.exe",
    # 영상 플레이어
    "vlc.exe", "potplayermini.exe", "potplayermini64.exe", "mpc-hc.exe", "mpc-hc64.exe", "mpc-be64.exe",
    "wmplayer.exe", "video.ui.exe", "mpv.exe", "kmplayer.exe", "kmplayer64x.exe", "daumpotplayer.exe",
    # 만드는 도구
    "unrealeditor.exe", "ue4editor.exe", "unity.exe", "unity hub.exe", "blender.exe", "devenv.exe",
    "code.exe", "rider64.exe",
    # 런처와 클라이언트
    "steam.exe", "steamwebhelper.exe", "epicgameslauncher.exe", "epicwebhelper.exe", "battle.net.exe",
    "agent.exe", "riotclientservices.exe", "riotclientux.exe", "riotclientuxrender.exe", "leagueclient.exe",
    "leagueclientux.exe", "leagueclientuxrender.exe", "eadesktop.exe", "eabackgroundservice.exe",
    "origin.exe", "upc.exe", "ubisoftconnect.exe", "uplaywebcore.exe", "galaxyclient.exe",
    "xboxpcapp.exe", "gamebar.exe", "gamebarftserver.exe",
    # 윈도우와 상주 프로그램
    "explorer.exe", "dwm.exe", "applicationframehost.exe", "textinputhost.exe", "searchhost.exe",
    "shellexperiencehost.exe", "startmenuexperiencehost.exe", "lockapp.exe", "systemsettings.exe",
    "discord.exe", "slack.exe", "kakaotalk.exe", "teams.exe", "ms-teams.exe", "zoom.exe",
    "wallpaper32.exe", "wallpaper64.exe", "wallpaperui.exe", "lively.exe",
    # 캡처, 오버레이 도구
    "snippingtool.exe", "screenclippinghost.exe", "sharex.exe", "lightshot.exe", "greenshot.exe",
    "powertoys.exe", "powertoys.screenruler.exe", "powertoys.colorpickerui.exe", "magnify.exe", "screensketch.exe",
    "nvidia overlay.exe", "nvcontainer.exe", "radeonsoftware.exe", "amdrsserv.exe", "gamebarpresencewriter.exe",
    "steamwebhelper.exe", "medal.exe", "overwolf.exe",
    # 녹화 프로그램과 이 앱
    "obs64.exe", "obs32.exe", "obs.exe", "redbox.exe", "python.exe", "pythonw.exe",
}

# 이름 일부로 거르는 것: 설치와 제거, 크래시 보고, 안티치트, 에디터
EXCLUDE_PATTERN = re.compile(
    r"unins|setup\.exe$|installer|redist|vcredist|vc_redist|dxsetup|dotnetfx|directx|"
    r"crashpad|crashreport|crashhandler|crashsender|bugsplat|"
    r"battleye|easyanticheat|eac_|eaclaunch|vanguard|"
    r"editor\.exe$|updater|helper\.exe$|launcher\.exe$|webhelper|cefprocess|renderer\.exe$",
    re.I,
)

# 화면 판정에 쓰는 그래픽 모듈
GFX_MODULES = {"d3d9.dll", "d3d11.dll", "d3d12.dll", "vulkan-1.dll", "opengl32.dll"}


def is_system_path(path_lower):
    """윈도우에 딸린 프로그램(시스템 폴더, 마이크로소프트 앱)은 화면 판정으로 게임이 되지 않게."""
    windir = (os.environ.get("WINDIR") or r"C:\Windows").lower()
    return path_lower.startswith(windir + "\\") or r"\windowsapps\microsoft." in path_lower


def is_default_excluded(name_lower):
    return name_lower in EXCLUDE_EXES or bool(EXCLUDE_PATTERN.search(name_lower))


def in_user_list(items, name_lower, path_lower):
    """사용자 목록 항목은 실행 파일 이름, 전체 경로, 게임 설치 폴더(그 안의 실행 파일 전부)를 받는다."""
    for it in items:
        it = str(it).strip().lower().rstrip("\\/")
        if not it:
            continue
        if it == name_lower or it == path_lower or (path_lower and path_lower.startswith(it + "\\")):
            return True
    return False
