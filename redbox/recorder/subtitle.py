"""녹화에 자막 얹기: 바깥 프로그램이 내놓는 통합 자막 파일을 읽어, 녹화하는 동안 OBS 장면에 그림과 글을 얹는다.

레드박스는 게임 창만 캡처하므로 다른 프로그램이 화면에 띄운 창은 녹화에 들어가지 않는다. 그래서 얹을 것을 파일로 받아
녹화하는 쪽이 직접 장면에 얹는다. 레드박스는 무엇을 보여 줄지 정하지 않고, 통합 자막 파일이 적은 대로 얹고 치우기만 한다.

통합 자막 파일(UTF-8 JSON, 글을 내놓는 쪽이 지키는 약속은 docs/subtitle.md):
    {"layers": [
        {"image": "지금 생각.png"},                                  그림: 게임 화면 전체에 겹친다
        {"text_file": "메모.txt", "anchor": "bottom-left", ...},     글 파일
        {"text": "1장", "anchor": "top"}                             글을 직접
    ]}
- layers 는 아래부터 차례로 겹친다(앞의 것이 아래). 개수 제한 없음. 경로는 통합 자막 파일이 있는 폴더 기준.
- 글 칸: anchor(자리), width(화면 폭 대비 최대 폭), size(화면 높이 대비 글자 크기), opacity(바탕 불투명도).
- 파일이 없거나 비었거나 layers 가 비면 아무것도 얹지 않는다. 깨진 JSON 이면 직전 상태를 둔다.

OBS 에는 칸마다 소스를 얹는다. 그림은 그림 소스를 게임 캡처와 같은 자리, 같은 크기로(그림 속 자리가 게임 화면과 맞게).
글은 반투명 검은 바탕(색 소스) 위에 흰 글(FreeType 글 소스. GDI+ 글 소스는 OTF 글꼴을 못 쓴다)."""
import json
import os
import threading
import time

PREFIX = "Redbox Layer"
OLD_NAMES = ("Redbox Subtitle", "Redbox Subtitle Box", "Redbox Overlay Image")   # 앞선 판에서 쓰던 이름
POLL_SECONDS = 0.5
FIT_SECONDS = 1.0
TEXT_DEFAULTS = {"anchor": "bottom", "width": 0.7, "size": 0.04, "opacity": 0.6}
ANCHORS = ("bottom", "top", "left", "right", "top-left", "top-right", "bottom-left", "bottom-right")


# -- 통합 자막 파일 읽기 -------------------------------------------------------------------------------
def _style(d):
    """글 칸의 모양 값(자리, 폭, 크기, 불투명도). 틀린 값은 기본값, 범위 밖은 끝값."""
    out = dict(TEXT_DEFAULTS)
    a = str(d.get("anchor") or "").lower().replace("_", "-").replace(" ", "-")
    a = {"topleft": "top-left", "topright": "top-right", "bottomleft": "bottom-left", "bottomright": "bottom-right"}.get(a, a)
    if a in ANCHORS:
        out["anchor"] = a
    for k, lo, hi in (("width", 0.1, 1.0), ("size", 0.01, 0.2), ("opacity", 0.0, 1.0)):
        try:
            out[k] = min(hi, max(lo, float(d[k])))
        except (KeyError, TypeError, ValueError):
            pass
    return out


def parse_manifest(raw, base_dir):
    """통합 자막 파일 내용 -> 칸 목록. 깨졌으면 None(직전 상태를 둔다). 비었으면 [].
    칸: {"kind": "image", "path"} 또는 {"kind": "text", "text" | "path", 모양 값}."""
    s = (raw or "").lstrip("\ufeff").strip()
    if not s:
        return []
    try:
        d = json.loads(s)
    except ValueError:
        return None
    if not isinstance(d, dict) or not isinstance(d.get("layers", []), list):
        return None

    def path(p):
        p = os.path.expandvars(str(p))
        return os.path.normpath(p if os.path.isabs(p) else os.path.join(base_dir, p))

    out = []
    for item in d.get("layers", []):
        if not isinstance(item, dict):
            continue
        if item.get("image"):
            out.append({"kind": "image", "path": path(item["image"])})
        elif item.get("text_file"):
            out.append(dict(_style(item), kind="text", path=path(item["text_file"])))
        elif "text" in item:
            out.append(dict(_style(item), kind="text", text=str(item.get("text") or "")))
    return out


def _clean_text(s):
    return (s or "").replace("\r\n", "\n").replace("\r", "\n").strip("\n")


def _stat(path):
    try:
        st = os.stat(path)
        return st.st_mtime_ns, st.st_size
    except OSError:
        return None


def _read(path):
    """글 파일 내용. 없으면 "", 바꿔치기 순간이라 못 읽으면 None."""
    for _ in range(3):
        try:
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                return f.read()
        except FileNotFoundError:
            return ""
        except OSError:
            time.sleep(0.05)
    return None


# -- 글 배치 -------------------------------------------------------------------------------------------
def font_choice():
    """OBS 가 쓸 수 있는 글꼴: 윈도우 글꼴 폴더에 Pretendard 가 있으면 그것, 없으면 맑은 고딕. (이름, 굵기, 파일).
    OBS 의 FreeType 글 소스는 사용자 한 명에게만 설치된 글꼴(LOCALAPPDATA)을 찾지 못한다."""
    d = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for name, face, style in (("Pretendard-SemiBold.otf", "Pretendard", "SemiBold"), ("malgunbd.ttf", "Malgun Gothic", "Bold")):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return face, style, p
    return "Arial", "Bold", None


def _wrap(text, font, width):
    """글을 width 픽셀 안에 줄바꿈한다. 원래 줄바꿈은 지키고, 띄어쓰기에서 끊되 너무 긴 낱말은 글자 단위로."""
    out = []
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            cand = f"{line} {word}" if line else word
            if font.getlength(cand) <= width:
                line = cand
                continue
            if line:
                out.append(line)
                line = ""
            while font.getlength(word) > width and len(word) > 1:
                n = len(word)
                while n > 1 and font.getlength(word[:n]) > width:
                    n -= 1
                out.append(word[:n])
                word = word[n:]
            line = word
        out.append(line)
    return out


def layout(text, style, canvas_w, canvas_h, font_path):
    """글 칸 배치: {"lines", "px", "pad", "margin", "anchor", "box": (x, y, w, h), "text_at": (x, y)}. 글이 없으면 None."""
    from PIL import ImageFont
    if not text.strip():
        return None
    px = max(10, round(style["size"] * canvas_h))
    pad = round(px * 0.55)
    margin = round(canvas_h * 0.04)
    font = ImageFont.truetype(font_path, px) if font_path else ImageFont.load_default()
    max_w = max(px * 4, style["width"] * canvas_w - 2 * pad)
    lines = _wrap(text, font, max_w)
    asc, desc = font.getmetrics()
    line_h = round((asc + desc) * 1.12)
    max_lines = max(1, int((canvas_h - 2 * margin - 2 * pad) // line_h))
    lines = lines[-max_lines:]                       # 화면보다 길면 마지막 줄들만(새 글이 아래에 붙는 경우가 많다)
    tw, th = round(max(font.getlength(x) for x in lines)), line_h * len(lines)
    out = {"lines": lines, "px": px, "pad": pad, "margin": margin, "anchor": style["anchor"]}
    out.update(place(out, tw, th, canvas_w, canvas_h))
    return out


def place(lay, tw, th, canvas_w, canvas_h):
    """글 크기(tw x th)에 여백을 더한 바탕을 자리에 놓는다: {"box": (x, y, w, h), "text_at": (x, y)}."""
    pad, margin, a = lay["pad"], lay["margin"], lay["anchor"]
    w, h = tw + 2 * pad, th + 2 * pad
    if "left" in a:
        x = margin
    elif "right" in a:
        x = canvas_w - margin - w
    else:
        x = (canvas_w - w) // 2
    if "top" in a:
        y = margin
    elif "bottom" in a:
        y = canvas_h - margin - h
    else:
        y = (canvas_h - h) // 2
    return {"box": (x, y, w, h), "text_at": (x + pad, y + pad)}


# -- OBS 에 얹는 칸 -----------------------------------------------------------------------------------
class _TextLayer:
    """글 칸 하나: 반투명 바탕 소스와 그 위 글 소스."""

    def __init__(self, ov, n, spec):
        self.ov, self.spec = ov, spec
        self.box, self.name = f"{PREFIX} {n} Box", f"{PREFIX} {n} Text"
        c = ov.client
        self.box_id = c.create_input(ov.scene, self.box, "color_source_v3", {"color": 0, "width": 2, "height": 2},
                                     False).scene_item_id
        self.text_id = c.create_input(
            ov.scene, self.name, "text_ft2_source_v2",
            {"text": "", "font": {"face": ov.face, "style": ov.style, "size": 32, "flags": 0},
             "color1": 0xFFFFFFFF, "color2": 0xFFFFFFFF, "antialiasing": True}, False).scene_item_id
        self.shown = None                   # 마지막으로 얹은 (글, 모양)
        self.mark = None

    def refresh(self, spec):
        """글 파일이 바뀌었거나 모양이 바뀌었으면 다시 얹는다."""
        self.spec = spec
        if spec.get("path"):
            mark = _stat(spec["path"])
            if mark == self.mark and self.shown is not None and self.shown[1] == self._style():
                return
            raw = _read(spec["path"])
            if raw is None:
                return
            self.mark = mark
            text = _clean_text(raw)
        else:
            text = _clean_text(spec.get("text"))
        key = (text, self._style())
        if key != self.shown:
            self.shown = key
            self._apply(text)

    def _style(self):
        return tuple(self.spec[k] for k in ("anchor", "width", "size", "opacity"))

    def _apply(self, text):
        ov, c = self.ov, self.ov.client
        lay = layout(text, self.spec, *ov.canvas, ov.font_path)
        if lay is None:
            for i in (self.box_id, self.text_id):
                c.set_scene_item_enabled(ov.scene, i, False)
            return
        before = self._size()
        c.set_input_settings(self.name, {"text": "\n".join(lay["lines"]),
                                         "font": {"face": ov.face, "style": ov.style, "size": lay["px"], "flags": 0}}, True)
        # OBS 가 실제로 그린 글 크기에 바탕을 맞춘다(줄 간격이 미리 잰 값과 조금 다름).
        # 글을 바꾼 직후에는 앞 글의 크기가 나오므로, 크기가 바뀔 때까지 잠깐(최대 0.5초) 기다린다.
        size = None
        for _ in range(17):
            size = self._size()
            if size and size != before:
                break
            time.sleep(0.03)
        if size:
            lay.update(place(lay, size[0], size[1], *ov.canvas))
        x, y, w, h = lay["box"]
        c.set_input_settings(self.box, {"color": (round(self.spec["opacity"] * 255) << 24), "width": w, "height": h}, True)
        tx, ty = lay["text_at"]
        for i, px, py in ((self.box_id, x, y), (self.text_id, tx, ty)):
            c.set_scene_item_transform(ov.scene, i, {"positionX": float(px), "positionY": float(py),
                                                     "alignment": 5, "scaleX": 1.0, "scaleY": 1.0})
            c.set_scene_item_enabled(ov.scene, i, True)

    def _size(self):
        try:
            t = self.ov.client.get_scene_item_transform(self.ov.scene, self.text_id).scene_item_transform
            w, h = round(t["sourceWidth"]), round(t["sourceHeight"])
            return (w, h) if w > 0 and h > 0 else None
        except Exception:
            return None

    def fit(self):
        pass

    def names(self):
        return (self.name, self.box)


class _ImageLayer:
    """그림 칸 하나: 투명 PNG 를 게임 캡처와 같은 자리, 같은 크기로 겹친다(그림 비율은 게임 화면과 같게)."""

    def __init__(self, ov, n, spec):
        self.ov, self.spec = ov, spec
        self.name = f"{PREFIX} {n} Image"
        self.id = ov.client.create_input(ov.scene, self.name, "image_source",
                                         {"file": spec["path"], "unload": False, "linear_alpha": False},
                                         True).scene_item_id
        self.mark = _stat(spec["path"])
        self.fitted = None
        self.fit()

    def refresh(self, spec):
        mark = _stat(spec["path"])
        if mark != self.mark:                  # 바뀌거나 생기면 OBS 가 바로 다시 읽게(스스로는 1초 남짓 늦다)
            self.mark = mark
            self.ov.client.set_input_settings(self.name, {"file": spec["path"]}, True)

    def fit(self):
        tgt = self.ov.capture_target()
        if tgt is not None and tgt != self.fitted:
            self.ov.client.set_scene_item_transform(self.ov.scene, self.id, tgt)
            self.fitted = tgt

    def names(self):
        return (self.name,)


# -- 통합 자막 ---------------------------------------------------------------------------------------
class Overlay:
    """녹화 하나 동안 통합 자막 파일을 지켜보며 칸들을 얹는다. 자기 OBS 연결과 스레드로 돌아 녹화 쪽은 건드리지 않는다.
    칸 목록(종류와 파일)이 바뀌면 다시 만들고, 글이나 그림 파일만 바뀌면 그 칸만 고친다."""

    def __init__(self, path, connect, log):
        self.path, self.connect, self.log = path, connect, log
        self.client = None
        self.scene = self.capture = self.cap_item = None
        self.layers = []
        self.shape = None                       # 지금 얹은 칸 목록의 모양(종류, 파일, 글 칸 순서)
        self._mark = "none"
        self._specs = []
        self._stop = threading.Event()
        self._thread = None
        self._next_fit = 0
        self.face, self.style, self.font_path = font_choice()

    def start(self, scene, capture=None):
        """scene 에 통합 자막 파일이 적은 칸들을 얹고 지켜보기 시작한다. 실패하면 로그만 남기고 녹화는 그대로."""
        try:
            self.client = self.connect()
            self.scene, self.capture = scene, capture
            remove_leftovers(self.client)
            v = self.client.get_video_settings()
            self.canvas = (v.base_width, v.base_height)
            try:
                self.cap_item = self.client.get_scene_item_id(scene, capture).scene_item_id if capture else None
            except Exception:
                self.cap_item = None           # 게임 캡처가 이 장면에 바로 있지 않으면 그림은 장면 전체에 맞춘다
            self._refresh()
        except Exception as e:
            self.log(f"  [자막] 얹기 실패: {e}")
            self.stop()
            return False
        self._thread = threading.Thread(target=self._run, daemon=True, name="subtitle")
        self._thread.start()
        self.log(f"  [자막] 통합 자막 파일 지켜보기: {self.path}")
        return True

    def _run(self):
        failed = False
        while not self._stop.wait(POLL_SECONDS):
            try:
                self._refresh()
                failed = False
            except Exception as e:
                if not failed:
                    self.log(f"  [자막] 고치기 실패: {e}")
                failed = True

    def _refresh(self):
        mark = _stat(self.path)
        if mark != self._mark:
            raw = _read(self.path) if mark else ""
            specs = None if raw is None else parse_manifest(raw, os.path.dirname(self.path))
            if specs is not None:              # 깨졌거나 못 읽으면 직전 상태를 둔다
                self._mark, self._specs = mark, specs
        shape = tuple((s["kind"], s.get("path"), "path" in s) for s in self._specs)
        if shape != self.shape:
            self._rebuild(shape)
        for layer, spec in zip(self.layers, self._specs):
            layer.refresh(spec)
        if time.time() >= self._next_fit:
            self._next_fit = time.time() + FIT_SECONDS
            for layer in self.layers:
                layer.fit()

    def _rebuild(self, shape):
        """칸 목록이 바뀌면 얹은 소스를 모두 치우고 아래부터 다시 얹는다(새로 만든 소스가 맨 위로 가므로 순서대로)."""
        self._remove_layers()
        self.shape = shape
        for n, spec in enumerate(self._specs, 1):
            cls = _ImageLayer if spec["kind"] == "image" else _TextLayer
            self.layers.append(cls(self, n, spec))

    def _remove_layers(self):
        names = [n for layer in self.layers for n in layer.names()]
        self.layers = []
        for n in names:
            try:
                self.client.remove_input(n)
            except Exception:
                pass

    def capture_target(self):
        """그림 칸을 놓을 자리: 게임 캡처의 배치를 그대로(바깥 틀이 있으면 그 틀과 맞춤 방식, 없으면 보이는 크기로 늘림)."""
        full = {"positionX": 0.0, "positionY": 0.0, "rotation": 0.0, "alignment": 5, "scaleX": 1.0, "scaleY": 1.0,
                "boundsType": "OBS_BOUNDS_SCALE_INNER", "boundsAlignment": 0,
                "boundsWidth": float(self.canvas[0]), "boundsHeight": float(self.canvas[1])}
        if self.cap_item is None:
            return full
        t = self.client.get_scene_item_transform(self.scene, self.cap_item).scene_item_transform
        out = {k: t[k] for k in ("positionX", "positionY", "rotation", "alignment")}
        out.update(scaleX=1.0, scaleY=1.0, boundsAlignment=t.get("boundsAlignment", 0))
        if t.get("boundsType") and t["boundsType"] != "OBS_BOUNDS_NONE" and t["boundsWidth"] >= 1:
            out.update(boundsType=t["boundsType"], boundsWidth=t["boundsWidth"], boundsHeight=t["boundsHeight"])
            return out
        w = (t["sourceWidth"] - t.get("cropLeft", 0) - t.get("cropRight", 0)) * t["scaleX"]
        h = (t["sourceHeight"] - t.get("cropTop", 0) - t.get("cropBottom", 0)) * t["scaleY"]
        if abs(w) < 1 or abs(h) < 1:
            return None                       # 게임 화면이 아직 안 잡힘: 다음에 다시
        out.update(boundsType="OBS_BOUNDS_STRETCH", boundsWidth=abs(w), boundsHeight=abs(h))
        return out

    def stop(self):
        """지켜보기를 멈추고 얹은 소스를 치운다."""
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(2)
        if self.client:
            try:
                self._remove_layers()
                remove_leftovers(self.client)
            except Exception as e:
                self.log(f"  [자막] 치우기 실패: {e}")
            try:
                self.client.disconnect()
            except Exception:
                pass
        self.client = None


def remove_leftovers(client):
    """앞선 녹화에서 남은 자막 소스(앱이 꺼지거나 PC 가 꺼져 못 치운 것)를 치운다."""
    for i in client.get_input_list().inputs:
        n = i["inputName"]
        if n.startswith(PREFIX + " ") or n in OLD_NAMES:
            client.remove_input(n)
