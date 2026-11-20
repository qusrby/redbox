"""게임 그림 모으기.

- 스팀 게임: 스팀이 라이브러리 화면용으로 PC 에 받아 둔 그림(대표 그림 header, 배경 hero)
- 지금 설치 안 된 스팀 게임(녹화 기록만 있는 것): 스팀 상점 검색으로 게임 번호를 찾아, PC 캐시나 스팀 그림 서버에서
- 직접 추가한 게임: 사용자가 고른 그림, 없으면 게임 실행 파일의 아이콘
찾은 그림은 데이터 폴더 art 에 복사해 두므로, 게임이나 스팀을 지워도 계속 보인다."""
import glob
import hashlib
import json
import os
import re
import shutil
import time
import urllib.parse
import urllib.request

from . import paths
from .detect.catalog import steam_art

KINDS = ("hero", "header", "icon", "iconsrc")
STORE_SEARCH = "https://store.steampowered.com/api/storesearch/?"
STEAM_CDN = "https://cdn.akamai.steamstatic.com/steam/apps/{}/{}"
RETRY_MISS_DAYS = 7
RIOT_META = r"C:\ProgramData\Riot Games\Metadata"
_EDITION = re.compile(r"(?: (?:ultimate|deluxe|gold|complete|definitive|standard|digital|goty|game of the year|"
                      r"enhanced|special|premium|collector s))* edition$| goty$")


def norm(name):
    """비교용 이름: 상표 기호와 문장 부호를 빼고 소문자로(Tom Clancy’s The Division® 2 = tom clancy s the division 2)."""
    s = (name or "").lower().replace("’", "'")
    s = re.sub(r"[™®©]", "", s)
    s = re.sub(r"[^0-9a-z가-힣]+", " ", s)
    return s.strip()


def base(name):
    """판 이름을 뗀 이름(control ultimate edition = control)."""
    return _EDITION.sub("", norm(name)).strip()


def lookup(index, name):
    return index.get(norm(name)) or index.get(base(name))


def art_dir(key=None):
    d = os.path.join(paths.data_dir(), "art")
    return os.path.join(d, key) if key else d


def custom_key(path):
    return "custom_" + hashlib.md5(str(path).lower().rstrip("\\/").encode("utf-8")).hexdigest()[:12]


def load_index():
    try:
        with open(os.path.join(art_dir(), "games.json"), encoding="utf-8") as f:
            return dict(json.load(f))
    except (OSError, ValueError):
        return {}


def save_index(index):
    os.makedirs(art_dir(), exist_ok=True)
    path = os.path.join(art_dir(), "games.json")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(path + ".tmp", path)


def stored(key):
    """보관해 둔 그림 {"header": 경로, ..., "_dir": 폴더}."""
    d, out = art_dir(key), {}
    if not key or not os.path.isdir(d):
        return out
    out["_dir"] = d
    for f in os.listdir(d):
        kind = os.path.splitext(f)[0]
        if kind == "iconsrc":            # 아이콘을 뽑을 실행 파일 경로(화면 쪽에서 뽑아 icon.png 로 저장)
            try:
                out[kind] = open(os.path.join(d, f), encoding="utf-8").read().strip()
            except OSError:
                pass
        elif kind in KINDS:
            out[kind] = os.path.join(d, f)
    return out


def set_custom_image(game, path, image):
    """직접 추가한 게임의 그림을 사용자가 고른 파일로(대표 그림 자리)."""
    key = custom_key(path)
    d = art_dir(key)
    os.makedirs(d, exist_ok=True)
    for f in glob.glob(os.path.join(d, "header.*")):
        os.remove(f)
    shutil.copyfile(image, os.path.join(d, "header" + os.path.splitext(image)[1].lower()))
    index = load_index()
    index[norm(game)] = key
    save_index(index)


# -- 후보: (키, [이름들], {종류: 파일 경로}) --------------------------------------------------------------
def _steam(catalog):
    for _d, e in catalog.dirs:
        if e.source == "steam" and e.appid:
            files = {k: v for k, v in steam_art(e.appid).items() if k in ("header", "hero")}
            if files:
                yield f"steam_{e.appid}", [e.name], files


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Redbox"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def steam_search(name):
    """스팀 상점에서 이름이 같은 게임의 번호. 없으면 None(판 이름은 떼고 비교)."""
    try:
        items = json.loads(_get(STORE_SEARCH + urllib.parse.urlencode({"term": name, "l": "english", "cc": "US"})))
    except (OSError, ValueError):
        return None
    for it in items.get("items") or []:
        if norm(it.get("name")) in (norm(name), base(name)) or base(it.get("name")) == base(name):
            return str(it.get("id"))
    return None


def _misses():
    try:
        with open(os.path.join(art_dir(), "misses.json"), encoding="utf-8") as f:
            return dict(json.load(f))
    except (OSError, ValueError):
        return {}


def _steam_by_name(recorded, index):
    """설치된 스팀 게임 목록에 없는 녹화 게임: 상점 검색으로 번호를 찾는다. 못 찾은 이름은 7일 동안 다시 묻지 않는다."""
    misses, now = _misses(), time.time()
    changed_miss = False
    for name in sorted(set(recorded)):
        n = norm(name)
        if not n or lookup(index, name) or now - misses.get(n, 0) < RETRY_MISS_DAYS * 86400:
            continue
        appid = steam_search(name)
        if not appid:
            misses[n] = now
            changed_miss = True
            continue
        files = {k: v for k, v in steam_art(appid).items() if k in ("header", "hero")}
        for kind, fn in (("header", "header.jpg"), ("hero", "library_hero.jpg")):
            files.setdefault(kind, STEAM_CDN.format(appid, fn))
        yield f"steam_{appid}", [name], files
    if changed_miss:
        os.makedirs(art_dir(), exist_ok=True)
        with open(os.path.join(art_dir(), "misses.json"), "w", encoding="utf-8") as f:
            json.dump(misses, f)


def _icon_for(path, catalog):
    """직접 추가한 게임의 아이콘 파일: 실행 파일이면 그 파일, 폴더면 런처가 둔 아이콘이나 폴더에서 가장 큰 실행 파일."""
    if path.lower().endswith(".exe"):
        return path if os.path.isfile(path) else ""
    for _d, e in catalog.dirs:
        if e.dir and os.path.normcase(e.dir.rstrip("\\/")) == os.path.normcase(path.rstrip("\\/")):
            if e.source == "riot":
                for ico in glob.glob(os.path.join(RIOT_META, "*.live", "*.live.ico")):
                    product = os.path.basename(ico).split(".")[0].replace("_", "")
                    if product in norm(e.name).replace(" ", ""):
                        return ico
            if e.icon or e.exe:
                return e.icon or e.exe
    exes = [p for depth in ("*.exe", "*/*.exe", "*/*/*.exe") for p in glob.glob(os.path.join(path, depth))
            if not re.search(r"unins|setup|crash|helper|launcher|update", os.path.basename(p), re.I)]
    return max(exes, key=os.path.getsize, default="")


def _custom(custom_games, catalog):
    for g in custom_games:
        path, name = str(g.get("path", "")), g.get("name", "")
        if not path or not name:
            continue
        key = custom_key(path)
        if os.path.isfile(os.path.join(art_dir(key), "icon.png")):
            yield key, [name], {}
            continue
        src = _icon_for(path, catalog)
        if src:
            yield key, [name], {("icon" if src.lower().endswith(".ico") else "iconsrc"): src}


# -- 모으기 ---------------------------------------------------------------------------------------
def _put(src, dst):
    try:
        if src.startswith("http"):
            if not os.path.isfile(dst):
                data = _get(src)
                if len(data) < 1000:
                    return False
                with open(dst + ".part", "wb") as f:
                    f.write(data)
                os.replace(dst + ".part", dst)
        elif dst.endswith("iconsrc.txt"):
            with open(dst, "w", encoding="utf-8") as f:
                f.write(src)
        elif not (os.path.isfile(dst) and os.path.getsize(dst) == os.path.getsize(src)):
            shutil.copyfile(src, dst)
        return True
    except (OSError, ValueError):
        return False


def collect(catalog, custom_games, recorded=(), log=None):
    """스팀 게임과 직접 추가한 게임의 그림을 보관하고 이름 -> 키 목록을 갱신한다. 바뀐 게 있으면 True."""
    index = load_index()
    changed = False
    for name, key in list(index.items()):      # 스팀과 직접 추가 말고 예전 방식의 보관본은 정리
        if not key.startswith(("steam_", "custom_")):
            index.pop(name)
            shutil.rmtree(art_dir(key), ignore_errors=True)
            changed = True
    def sources():
        yield from _steam(catalog)
        yield from _custom(custom_games, catalog)
        yield from _steam_by_name(recorded, index)     # 앞에서 index 가 채워진 뒤에 돈다

    for key, names, files in sources():
        names = list(dict.fromkeys(n for x in names for n in (norm(x), base(x)) if n))
        d = art_dir(key)
        os.makedirs(d, exist_ok=True)
        got = False
        for kind, src in files.items():
            ext = ".txt" if kind == "iconsrc" else os.path.splitext(src.split("?")[0])[1].lower()
            got = _put(src, os.path.join(d, kind + ext)) or got
        if not got and not files.get("iconsrc") and not os.listdir(d):
            continue
        new = [n for n in names if index.get(n) != key and (not index.get(n) or key.startswith("custom_"))]
        for n in new:
            index[n] = key
        if new:
            changed = True
            if log:
                log(f"게임 그림 보관: {new[0]} ({key.split('_')[0]})")
    if changed:
        save_index(index)
    return changed
