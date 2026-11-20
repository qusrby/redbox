"""PC 에 설치된 게임 목록 모으기: 윈도우 게임 목록(GameConfigStore)과 런처 설치 정보.
손으로 관리하는 고정 목록은 두지 않는다. 앱 시작 때와 주기적으로 다시 모은다."""
import glob
import json
import os
import re
import winreg

from . import win32

HKCU, HKLM = winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE


class Entry:
    """설치된 게임 하나. dir 은 설치 폴더(이 안에서 실행되면 이 게임), exe 는 알려진 실행 파일(있으면)."""
    __slots__ = ("name", "dir", "exe", "source", "appid", "icon")

    def __init__(self, name, dir="", exe="", source="", appid="", icon=""):
        self.name, self.dir, self.exe, self.source, self.appid = name, dir, exe, source, appid
        self.icon = icon        # 아이콘이 든 파일(.exe 또는 .ico). 그림이 없을 때 쓴다

    def __repr__(self):
        return f"Entry({self.source}: {self.name} | {self.exe or self.dir})"


def _subkeys(root, path):
    try:
        with winreg.OpenKey(root, path) as k:
            i = 0
            while True:
                try:
                    yield winreg.EnumKey(k, i)
                except OSError:
                    return
                i += 1
    except OSError:
        return


def _values(root, path):
    out = {}
    try:
        with winreg.OpenKey(root, path) as k:
            i = 0
            while True:
                try:
                    name, val, _t = winreg.EnumValue(k, i)
                except OSError:
                    break
                out[name] = val
                i += 1
    except OSError:
        pass
    return out


def _value(root, path, name):
    return _values(root, path).get(name)


# --- 윈도우 게임 목록 ------------------------------------------------------------------------
def windows_game_list():
    """GameConfigStore: 윈도우(게임 바, 게임 모드)가 게임으로 알아본 실행 파일들. 실행할 때마다 늘어난다."""
    base = r"System\GameConfigStore\Children"
    out = []
    for sub in _subkeys(HKCU, base):
        path = _value(HKCU, base + "\\" + sub, "MatchedExeFullPath")
        if path:
            out.append(Entry("", exe=path, source="windows"))
    return out


# --- 런처 ----------------------------------------------------------------------------------
_STEAM_SKIP = re.compile(r"steamworks common redistributables|proton|steam linux runtime|wallpaper engine", re.I)


def steam_root():
    return (_value(HKCU, r"Software\Valve\Steam", "SteamPath") or r"C:\Program Files (x86)\Steam").replace("/", "\\")


def steam_art(appid):
    """스팀이 라이브러리 화면용으로 받아 둔 게임 그림. {"header": 460x215, "hero": 1920x620 배경, "logo": 투명 로고,
    "icon": 32x32}. 스팀 버전에 따라 appid 폴더 바로 아래 또는 그 아래 해시 이름 폴더에 있다(언어 꼬리 _koreana 등)."""
    out = {}
    if not appid:
        return out
    cache = os.path.join(steam_root(), "appcache", "librarycache")
    files = glob.glob(os.path.join(cache, str(appid), "**", "*.*"), recursive=True)
    files += glob.glob(os.path.join(cache, f"{appid}_*.jpg"))
    for p in files:
        n = os.path.basename(p).lower()
        if "blur" in n:
            continue
        if re.match(r"(library_)?header", n) or n.startswith(f"{appid}_header"):
            out.setdefault("header", p)
        elif re.match(r"library_hero", n) or n.startswith(f"{appid}_library_hero"):
            out.setdefault("hero", p)
        elif n.startswith("logo"):
            out.setdefault("logo", p)
        elif re.fullmatch(r"[0-9a-f]{40}\.jpg", n):
            out.setdefault("icon", p)
    return out


def steam():
    root = steam_root()
    vdf = os.path.join(root.replace("/", "\\"), "steamapps", "libraryfolders.vdf")
    libs = [os.path.join(root, "steamapps")]
    try:
        text = open(vdf, encoding="utf-8", errors="ignore").read()
        libs += [os.path.join(m.replace("\\\\", "\\"), "steamapps") for m in re.findall(r'"path"\s*"([^"]+)"', text)]
    except OSError:
        pass
    out, seen = [], set()
    for lib in libs:
        key = os.path.normcase(os.path.abspath(lib))
        if key in seen or not os.path.isdir(lib):
            continue
        seen.add(key)
        for acf in glob.glob(os.path.join(lib, "appmanifest_*.acf")):
            try:
                t = open(acf, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            name = re.search(r'"name"\s*"([^"]*)"', t)
            inst = re.search(r'"installdir"\s*"([^"]*)"', t)
            appid = re.search(r'"appid"\s*"(\d+)"', t)
            if not (name and inst) or _STEAM_SKIP.search(name.group(1)):
                continue
            out.append(Entry(name.group(1), dir=os.path.join(lib, "common", inst.group(1)), source="steam",
                             appid=appid.group(1) if appid else ""))
    return out


def epic():
    out = []
    for item in glob.glob(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests\*.item"):
        try:
            d = json.load(open(item, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        cats = [str(c).lower() for c in d.get("AppCategories", [])]
        if "games" not in cats:      # 언리얼 엔진, 플러그인 등은 빼고 게임만
            continue
        loc = d.get("InstallLocation", "")
        exe = d.get("LaunchExecutable", "")
        out.append(Entry(d.get("DisplayName", ""), dir=loc, exe=os.path.join(loc, exe) if exe else "", source="epic"))
    return out


def gog():
    base = r"SOFTWARE\WOW6432Node\GOG.com\Games"
    out = []
    for sub in _subkeys(HKLM, base):
        v = _values(HKLM, base + "\\" + sub)
        if v.get("path"):
            out.append(Entry(v.get("gameName", ""), dir=v["path"], exe=v.get("exe", ""), source="gog", appid=sub))
    return out


def ubisoft():
    base = r"SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs"
    out = []
    for sub in _subkeys(HKLM, base):
        d = _value(HKLM, base + "\\" + sub, "InstallDir")
        if d:
            d = d.replace("/", "\\").rstrip("\\")
            out.append(Entry(os.path.basename(d), dir=d, source="ubisoft"))
    return out


_UNINSTALL = [(HKLM, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
              (HKLM, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
              (HKCU, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")]
_PUBLISHERS = {"ea": re.compile(r"electronic arts", re.I),
               "battlenet": re.compile(r"blizzard", re.I),
               "riot": re.compile(r"riot games", re.I)}
_LAUNCHER_APPS = re.compile(r"^(ea app|ea desktop|origin|battle\.net|riot client|riot vanguard)$", re.I)


def uninstall_entries(kind):
    """설치된 프로그램 목록에서 게시자로 EA, 블리자드, 라이엇 게임을 찾는다(런처 자신은 뺀다)."""
    pub = _PUBLISHERS[kind]
    out = []
    for root, base in _UNINSTALL:
        for sub in _subkeys(root, base):
            v = _values(root, base + "\\" + sub)
            name = (v.get("DisplayName") or "").strip()
            loc = (v.get("InstallLocation") or "").strip().strip('"')
            if not name or not loc or not pub.search(v.get("Publisher") or ""):
                continue
            if _LAUNCHER_APPS.match(name):
                continue
            icon = re.sub(r",-?\d+$", "", (v.get("DisplayIcon") or "").strip()).strip('"')
            out.append(Entry(name, dir=loc, source=kind, icon=icon if os.path.isfile(icon) else ""))
    return out


_RIOT_NAMES = {"league_of_legends": "League of Legends", "valorant": "VALORANT",
               "bacon": "Legends of Runeterra", "teamfighttactics": "Teamfight Tactics", "lion": "2XKO"}


def riot():
    """라이엇 클라이언트 메타데이터(정식 서버 .live 만)와 설치된 프로그램 목록. 같은 폴더는 한 번만."""
    out, seen = [], set()
    for yaml in glob.glob(r"C:\ProgramData\Riot Games\Metadata\*.live\*.live.product_settings.yaml"):
        try:
            t = open(yaml, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        m = re.search(r'product_install_full_path:\s*"?([^"\r\n]+)"?', t)
        if not m:
            continue
        product = os.path.basename(os.path.dirname(yaml)).split(".")[0]
        d = os.path.normpath(m.group(1).strip())
        if d.lower() in seen:
            continue
        seen.add(d.lower())
        out.append(Entry(_RIOT_NAMES.get(product, product.replace("_", " ").title()), dir=d, source="riot"))
    for e in uninstall_entries("riot"):
        d = os.path.normpath(e.dir)
        if not any(win32.is_under(d.lower() + "\\", s) or d.lower() == s for s in seen):
            seen.add(d.lower())
            e.dir = d
            out.append(e)
    return out


def xbox():
    out = []
    for drive in win32.fixed_drives():
        root = os.path.join(drive, "XboxGames")
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            d = os.path.join(root, name)
            if os.path.isdir(d) and name.lower() != "gameSave".lower():
                out.append(Entry(name, dir=d, source="xbox"))
    return out


# 화면과 로그에 쓰는 정식 이름
SOURCE_NAMES = {"windows": "Windows", "steam": "Steam", "epic": "Epic Games", "gog": "GOG", "ubisoft": "Ubisoft Connect",
                "ea": "EA app", "battlenet": "Battle.net", "riot": "Riot", "xbox": "Xbox"}


def source_name(kind):
    return SOURCE_NAMES.get(kind, kind)


LAUNCHERS = {"steam": steam, "epic": epic, "gog": gog, "ubisoft": ubisoft,
             "ea": lambda: uninstall_entries("ea"), "battlenet": lambda: uninstall_entries("battlenet"),
             "riot": riot, "xbox": xbox}


class Catalog:
    """모은 결과. 실행 경로를 넣으면 어느 목록에 있는지, 게임 이름이 무엇인지 알려 준다."""

    def __init__(self, det_cfg):
        self.windows_exes = set()
        self.windows_paths = {}  # 소문자 경로 -> 원래 대소문자 경로(화면 표시용)
        self.exact = {}          # 실행 파일 경로(소문자) -> Entry (에픽, GOG 처럼 실행 파일까지 아는 것)
        self.dirs = []           # (설치 폴더 소문자, Entry) 긴 경로 먼저
        self.counts = {}
        self.errors = {}
        if det_cfg.get("windows_game_list", True):
            self._add("windows", windows_game_list)
        for kind, fn in LAUNCHERS.items():
            if det_cfg.get("launchers", {}).get(kind, True):
                self._add(kind, fn)
        self.dirs.sort(key=lambda t: len(t[0]), reverse=True)

    def _add(self, kind, fn):
        try:
            entries = fn()
        except Exception as e:     # 런처 하나가 이상해도 나머지는 모은다
            self.errors[kind] = str(e)
            entries = []
        self.counts[kind] = len(entries)
        for e in entries:
            if kind == "windows":
                self.windows_exes.add(e.exe.lower())
                self.windows_paths[e.exe.lower()] = e.exe
                continue
            if e.exe:
                self.exact[e.exe.lower()] = e
            if e.dir and os.path.isdir(e.dir):
                self.dirs.append((os.path.normpath(e.dir).lower(), e))

    def in_windows_list(self, path_lower):
        return path_lower in self.windows_exes

    def launcher_entry(self, path_lower):
        """(Entry, 실행 파일까지 일치하는지)"""
        if path_lower in self.exact:
            return self.exact[path_lower], True
        for d, e in self.dirs:
            if win32.is_under(path_lower, d):
                return e, False
        return None, False
