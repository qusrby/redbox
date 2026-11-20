"""게임 폴더 이름 정하기. 상표 기호를 빼고, 원하면 이미 있는 폴더 이름에 맞춘다
(같은 게임이 'DARK SOULS™ III' 와 'DARK SOULS III' 처럼 두 폴더로 갈라지지 않게)."""
import os
import re

from rapidfuzz import fuzz

from .files import safe_name

_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}
_MARKS = re.compile(r"[™®©]")
MATCH_SCORE = 85


def clean_title(name):
    return re.sub(r"\s+", " ", _MARKS.sub("", name or "")).strip()


def sequel_keys(name):
    """제목의 시리즈 번호(숫자, 로마 숫자). 번호가 다른 작품끼리는 맞추지 않는다(Hades 와 Hades II 등)."""
    full = clean_title(name)
    keys = set()
    for s in {full, full.split(":")[0].strip()}:
        for tok in s.split():
            t = tok.strip(".,'\"")
            if re.fullmatch(r"\d{1,2}", t):
                keys.add(int(t))
            elif re.fullmatch(r"[IVX]{1,5}", t, re.I) and t.upper() in _ROMAN:
                keys.add(_ROMAN[t.upper()])
        m = re.search(r"(\d{1,2}|[IVX]{1,5})$", s, re.I)
        if m:
            t = m.group(1)
            v = int(t) if t.isdigit() else _ROMAN.get(t.upper())
            if v is not None:
                keys.add(v)
    return keys


def best_match(label, folders):
    """(가장 비슷한 폴더 이름, 점수 0~100)"""
    label = clean_title(label)
    lk = sequel_keys(label)
    nl = re.sub(r"[^a-z0-9]", "", label.lower())
    if len(nl) < 3:
        return None, 0
    best, best_score = None, 0
    for f in folders:
        fc = clean_title(f)
        fk = sequel_keys(fc)
        if (lk or fk) and not (lk & fk):
            continue
        nf = re.sub(r"[^a-z0-9]", "", fc.lower())
        if len(nf) < 3:
            continue
        score = 100 if nl == nf else fuzz.ratio(nl, nf)
        if nl != nf and (nl in nf or nf in nl):
            short, long_ = sorted([nl, nf], key=len)
            if len(short) / len(long_) >= 0.85:
                score = max(score, 92)
        if score > best_score:
            best, best_score = f, score
    return best, best_score


def folder_name(game, match_root=""):
    """녹화를 넣을 게임 폴더 이름."""
    title = clean_title(game)
    if match_root and os.path.isdir(match_root):
        folders = [d for d in os.listdir(match_root) if os.path.isdir(os.path.join(match_root, d))]
        m, score = best_match(title, folders)
        if m and score >= MATCH_SCORE:
            return m
    return safe_name(title)
