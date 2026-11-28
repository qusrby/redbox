"""OBS Studio 연결(obs-websocket 5). 캡처 소스 찾기와 만들기, 녹화 시작과 정지."""
import json
import os

import obsws_python as obsws

OBS_WS_CONFIG = os.path.join(os.environ.get("APPDATA", ""), "obs-studio", "plugin_config", "obs-websocket", "config.json")

CAPTURE_KIND = "game_capture"
AUDIO_KIND = "wasapi_process_output_capture"
DESKTOP_KIND = "wasapi_output_capture"
MIC_KIND = "wasapi_input_capture"


def window_value(title, cls, exe):
    """OBS 창 지정 문자열 '제목:클래스:실행파일'. 구분자와 겹치는 문자는 OBS 규칙대로 바꾼다."""
    def enc(s):
        return (s or "").replace("#", "#22").replace(":", "#3A")
    return f"{enc(title)}:{enc(cls)}:{enc(exe)}"


def websocket_settings():
    """OBS 가 저장해 둔 웹소켓 설정(포트, 비밀번호). 없으면 None."""
    try:
        d = json.load(open(OBS_WS_CONFIG, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {"enabled": bool(d.get("server_enabled")), "port": int(d.get("server_port") or 4455),
            "password": d.get("server_password", "") if d.get("auth_required") else ""}


def open_client(cfg_obs):
    """OBS 웹소켓 연결 하나. 설정에 비밀번호가 없으면 OBS 가 저장해 둔 값을 쓴다."""
    port, password = cfg_obs.get("port") or 4455, cfg_obs.get("password") or ""
    if not password:
        ws = websocket_settings()
        if ws:
            port, password = ws["port"], ws["password"]
    return obsws.ReqClient(host=cfg_obs.get("host") or "localhost", port=port, password=password, timeout=5)


class Obs:
    def __init__(self, cfg_obs):
        self.cfg = cfg_obs
        self.client = None
        self.capture = None      # 쓸 캡처 소스 이름
        self.audio = None
        self.scene = None        # 앱 전용 장면을 쓰면 그 이름(녹화할 때 그 장면으로 바꾼다)
        self._prev_scene = None
        self._restore_mute = {}  # 녹화 동안 바꾼 음소거 {소스: 원래 상태}. 녹화가 끝나면 되돌린다
        self.seeded = False      # 오디오 설정을 OBS 의 지금 상태로 처음 정했으면 True(앱이 설정을 저장한다)

    def connect(self):
        self.client = open_client(self.cfg)
        self.setup()
        try:                                   # 지난 녹화에서 못 치운 자막 소스(앱, PC 가 꺼짐)
            from .subtitle import remove_leftovers
            if not self.recording():
                remove_leftovers(self.client)
        except Exception:
            pass

    def disconnect(self):
        try:
            if self.client:
                self.client.disconnect()
        except Exception:
            pass
        self.client = None

    def setup(self):
        """캡처 소스를 정한다. 설정에 이미 쓰던 소스 이름이 있으면 그대로 쓰고(장면은 건드리지 않음),
        없으면 앱 전용 장면과 소스를 만든다."""
        inputs = {i["inputName"]: i["inputKind"] for i in self.client.get_input_list().inputs}
        own_cap, own_aud = self.cfg.get("capture_source"), self.cfg.get("audio_source")
        if own_cap and inputs.get(own_cap) == CAPTURE_KIND:
            self.capture = own_cap
            self.audio = own_aud if own_aud and inputs.get(own_aud) == AUDIO_KIND else None
            self.scene = None
            self._seed_audio()
            return
        scene = self.cfg.get("scene") or "Redbox"
        cap, aud = f"{scene} Game", f"{scene} Audio"
        scenes = [s["sceneName"] for s in self.client.get_scene_list().scenes]
        if scene not in scenes:
            self.client.create_scene(scene)
        if cap not in inputs:
            self.client.create_input(scene, cap, CAPTURE_KIND, {"capture_mode": "window", "window": ""}, True)
        if aud not in inputs:
            self.client.create_input(scene, aud, AUDIO_KIND, {"window": ""}, True)
        self.capture, self.audio, self.scene = cap, aud, scene
        self._seed_audio()

    # -- 오디오 -------------------------------------------------------------------------------------
    def _specials(self):
        """OBS 전체에 걸린 오디오(설정 > 오디오의 데스크톱 오디오, 마이크): ([데스크톱], [마이크])."""
        try:
            sp = self.client.get_special_inputs()
        except Exception:
            return [], []
        desk = [getattr(sp, k, None) for k in ("desktop1", "desktop2")]
        mic = [getattr(sp, k, None) for k in ("mic1", "mic2", "mic3", "mic4")]
        return [x for x in desk if x], [x for x in mic if x]

    def _muted(self, name):
        try:
            return bool(self.client.get_input_mute(name).input_muted)
        except Exception:
            return None

    def _seed_audio(self):
        """처음 연결할 때 오디오 설정이 비어 있으면 OBS 의 지금 상태를 그대로 옮겨 적는다(업데이트로 녹음 내용이 바뀌지 않게)."""
        if self.cfg.get("mic") is not None and self.cfg.get("audio") in ("game", "all"):
            return
        desk, mic = self._specials()
        if self.cfg.get("mic") is None:
            self.cfg["mic"] = any(self._muted(m) is False for m in mic)
        if self.cfg.get("audio") not in ("game", "all"):
            self.cfg["audio"] = "all" if any(self._muted(d) is False for d in desk) else "game"
        self.seeded = True

    def _set_mute(self, name, muted):
        cur = self._muted(name)
        if cur is None or cur == muted:
            return
        self._restore_mute.setdefault(name, cur)
        self.client.set_input_mute(name, muted)

    def _ensure_input(self, name, kind):
        names = {i["inputName"] for i in self.client.get_input_list().inputs}
        if name not in names:
            self.client.create_input(self.scene, name, kind, {"device_id": "default"}, True)

    def apply_audio(self):
        """녹화 직전: 설정대로 소리를 맞춘다(게임 소리만 / PC 전체 소리, 마이크 켬 / 끔).
        앱 전용 장면이면 장면 안의 소스로, 쓰던 소스를 쓰면 OBS 전체 오디오의 음소거로 맞춘다."""
        self._restore_mute = {}
        mic_on, all_audio = bool(self.cfg.get("mic")), self.cfg.get("audio") == "all"
        desk, mic = self._specials()
        try:
            if self.scene:
                d_name, m_name = f"{self.scene} Desktop", f"{self.scene} Mic"
                self._ensure_input(d_name, DESKTOP_KIND)
                self._ensure_input(m_name, MIC_KIND)
                self.client.set_input_mute(d_name, not all_audio)
                self.client.set_input_mute(m_name, not mic_on)
                if self.audio:
                    self.client.set_input_mute(self.audio, all_audio)   # 전체 소리에 게임 소리가 이미 들어 있다
                for n in desk + mic:                                    # 장면 밖 전체 오디오는 겹치지 않게 끈다
                    self._set_mute(n, True)
            else:
                for n in desk:
                    self._set_mute(n, not all_audio)
                for n in mic:
                    self._set_mute(n, not mic_on)
                if self.audio:
                    self._set_mute(self.audio, all_audio)
        except Exception:
            pass

    def restore_audio(self):
        for name, muted in self._restore_mute.items():
            try:
                self.client.set_input_mute(name, muted)
            except Exception:
                pass
        self._restore_mute = {}

    def set_target(self, value):
        self.client.set_input_settings(self.capture, {"capture_mode": "window", "window": value}, True)
        if self.audio:
            self.client.set_input_settings(self.audio, {"window": value}, True)

    def record_scene(self):
        """녹화될 장면: 앱 전용 장면을 쓰면 그 장면, 아니면 지금 방송 화면 장면."""
        return self.scene or self.client.get_scene_list().current_program_scene_name

    def recording(self):
        return bool(self.client.get_record_status().output_active)

    def record_dir(self):
        return self.client.get_record_directory().record_directory

    def start(self, folder):
        if self.scene:
            cur = self.client.get_scene_list().current_program_scene_name
            if cur != self.scene:
                self._prev_scene = cur
                self.client.set_current_program_scene(self.scene)
        self.client.set_record_directory(folder)
        self.apply_audio()
        self.client.start_record()

    def stop(self):
        """녹화를 멈추고 결과 파일 경로를 돌려준다."""
        res = self.client.stop_record()
        self.restore_audio()
        if self._prev_scene:
            try:
                self.client.set_current_program_scene(self._prev_scene)
            except Exception:
                pass
            self._prev_scene = None
        return getattr(res, "output_path", None)

    def screenshot(self, width, height):
        """캡처 소스의 지금 화면(jpg 바이트). 비율을 지키며 width x height 안에 맞춘다."""
        import base64
        if not self.capture:
            return None
        r = self.client.get_source_screenshot(self.capture, "jpg", width, height, 80)
        return base64.b64decode(r.image_data.split(",", 1)[1])

    def set_record_dir(self, folder):
        self.client.set_record_directory(folder)


# -- 첫 실행 안내용: OBS 설치, 실행, 웹소켓 확인 --------------------------------------------------------
OBS_DOWNLOAD = "https://obsproject.com/download"
OBS_NAMES = ("obs64.exe", "obs32.exe", "obs.exe")


def find_obs():
    """OBS Studio 실행 파일 경로. 설치돼 있지 않으면 None."""
    cands = []
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\OBS Studio", 0, winreg.KEY_READ | view) as k:
                        cands.append(os.path.join(winreg.QueryValueEx(k, "")[0], "bin", "64bit", "obs64.exe"))
                except OSError:
                    pass
    except ImportError:
        pass
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base:
            cands.append(os.path.join(base, "obs-studio", "bin", "64bit", "obs64.exe"))
    return next((c for c in cands if os.path.isfile(c)), None)


def obs_running():
    import psutil
    for p in psutil.process_iter(["name"]):
        if (p.info.get("name") or "").lower() in OBS_NAMES:
            return True
    return False


# -- 비정상 종료 확인 창 --------------------------------------------------------------------------
# OBS 는 켜질 때 .sentinel 폴더에 run_* 표시를 만들고 정상 종료 때 지운다. 켜질 때 지난번 표시가 남아 있으면
# (PC 가 갑자기 꺼짐 등) '비정상 종료가 감지됨' 창을 띄우고, 누르기 전까지 웹소켓을 열지 않는다.
OBS_SENTINEL = os.path.join(os.environ.get("APPDATA", ""), "obs-studio", ".sentinel")


def crash_marks():
    try:
        return [os.path.join(OBS_SENTINEL, f) for f in os.listdir(OBS_SENTINEL) if f.startswith("run_")]
    except OSError:
        return []


def clear_crash_marks():
    """남은 run_* 표시를 지운다. OBS 가 꺼져 있을 때만 부른다(켜져 있으면 자기 표시까지 지워짐)."""
    n = 0
    for p in crash_marks():
        try:
            os.remove(p)
            n += 1
        except OSError:
            pass
    return n


def obs_process():
    """실행 중인 OBS (pid, 켜진 시각, 실행 파일). 없으면 None."""
    import psutil
    for p in psutil.process_iter(["name", "pid", "create_time", "exe"]):
        if (p.info.get("name") or "").lower() in OBS_NAMES:
            return p.info["pid"], p.info.get("create_time") or 0, p.info.get("exe")
    return None


def launch_obs(exe):
    """OBS 를 트레이로 켠다. OBS 는 자기 폴더에서 실행해야 설정과 플러그인을 찾는다."""
    import subprocess
    subprocess.Popen([exe, "--minimize-to-tray"], cwd=os.path.dirname(exe),
                     creationflags=0x00000008 | 0x00000200, close_fds=True)   # DETACHED, NEW_PROCESS_GROUP


def enable_websocket():
    """OBS 웹소켓 서버를 켜고 비밀번호를 정한다. 이미 켜져 있으면 그대로 둔다.
    OBS 가 켜져 있을 때 쓰면 OBS 가 끝날 때 자기 값으로 덮어쓰므로, OBS 가 꺼져 있을 때만 부른다."""
    import secrets
    try:
        with open(OBS_WS_CONFIG, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    if d.get("server_enabled"):
        return websocket_settings()
    d["server_enabled"] = True
    d["first_load"] = False          # 처음 켤 때 OBS 가 비밀번호를 새로 만들지 않게
    d.setdefault("alerts_enabled", False)
    d["server_port"] = int(d.get("server_port") or 4455)
    d["auth_required"] = True
    if not d.get("server_password"):
        d["server_password"] = secrets.token_urlsafe(12)
    os.makedirs(os.path.dirname(OBS_WS_CONFIG), exist_ok=True)
    tmp = OBS_WS_CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=4)
    os.replace(tmp, OBS_WS_CONFIG)
    return websocket_settings()


def test_connection(timeout=3):
    """OBS 웹소켓에 붙어 볼 수 있으면 OBS 버전 문자열, 안 되면 None."""
    ws = websocket_settings()
    if not ws or not ws["enabled"]:
        return None
    try:
        c = obsws.ReqClient(host="localhost", port=ws["port"], password=ws["password"], timeout=timeout)
    except Exception:
        return None
    try:
        return c.get_version().obs_version
    except Exception:
        return None
    finally:
        try:
            c.disconnect()
        except Exception:
            pass
