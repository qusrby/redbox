"""설정 읽기와 저장. 파일에 없는 항목은 기본값을 쓴다(새 버전에서 항목이 늘어도 그대로 동작)."""
import copy
import os

from . import APP_NAME, paths, safefile

UPLOAD_DAILY_MAX = 100   # 유튜브 API 업로드 한도: 구글 프로젝트당 하루 100개

DEFAULTS = {
    "setup_done": False,             # 첫 실행 안내를 마쳤는지(설정 파일이 이미 있던 사용자는 마친 것으로 본다)
    "language": "auto",              # auto(윈도우 언어), ko, en
    "start_with_windows": True,
    "check_updates": True,           # 깃허브에 새 버전이 있으면 알린다(설치는 하지 않음)
    "notify": True,
    "recording": {
        "video_root": "",            # 비면 동영상\Redbox
        "per_game_folder": True,
        "file_name": "{game} Video {start} {duration}",
        "discard_no_window_seconds": 30,   # 창을 한 번도 못 찾은 채 이 시간 안에 끝난 녹화는 지운다
        "subtitle_file": "",         # 녹화에 얹을 통합 자막 파일(JSON, 바깥 프로그램이 고쳐 씀. 그림과 글 칸 목록). 비면 끔
    },
    "detection": {
        "windows_game_list": True,   # 윈도우 GameConfigStore
        "launchers": {"steam": True, "epic": True, "gog": True, "ubisoft": True,
                      "ea": True, "battlenet": True, "riot": True, "xbox": True},
        "screen_detect": True,       # 녹화하지 않는 프로그램이 전체 화면 + 그래픽 모듈이면 '게임 추가' 후보로 기억
        "screen_detect_seconds": 10,
        "custom_games": [],          # 직접 추가한 게임 [{"name": 이름, "path": 실행 파일 또는 설치 폴더}]
        "always_record": [],         # 실행 파일 이름이나 전체 경로(예전 설정. 화면에서는 '게임 추가'를 쓴다)
        "never_record": [],
        "names": {},                 # 실행 파일 전체 경로(소문자) -> 사용자가 정한 게임 이름
    },
    "upload": {
        "enabled": False,
        "privacy": "private",           # private, unlisted, public
        "daily_limit": 20,              # 최대 100(유튜브 한도)
        "min_minutes": 3,               # 이보다 짧으면 올리지 않는다(파일은 남김)
        "auto_delete_minutes": 0,       # 이 길이 이하는 지운다. 0 이면 끔
        "delete_after_upload": True,    # 유튜브 처리가 끝나고 보관 기간이 지나면 PC 에서 지운다
        "keep_minutes": 7 * 24 * 60,    # 올린 뒤 원본 보관 시간(분). 0 이면 바로 지운다
        "stuck_hours": 10,              # 이 시간 넘게 유튜브 처리가 안 끝나면 지우고 다시 올린다
        "game_playlists": True,         # 게임 이름의 비공개 재생목록에 넣는다
        "title_template": "{name}",     # {name} = 파일 이름
        "description": "",
        "tags": ["gaming"],
        "category": "20",               # 유튜브 카테고리: 20 = 게임
        "poll_seconds": 30,
        "game_overrides": {},           # 게임 이름 -> {min_minutes, auto_delete_minutes, keep_minutes}
    },
    "obs": {
        "host": "localhost", "port": 4455, "password": "",   # 비밀번호가 비면 OBS 웹소켓 설정 파일에서 읽는다
        "scene": APP_NAME,                                     # 앱이 만드는 전용 장면
        "capture_source": "", "audio_source": "",              # 이미 쓰던 소스를 쓰려면 그 이름
        "mic": None,           # 마이크 녹음(True/False). None 이면 처음 연결할 때 OBS 의 지금 상태를 읽어 정한다
        "audio": None,         # 녹음 대상: "game"(게임 소리만) / "all"(PC 전체 소리). None 이면 위와 같이
    },
    "extras": {                      # 추가 기능(기본 꺼짐)
        "screenshot_folder": "",     # OBS 스크린샷을 게임 이름으로 바꿔 옮길 폴더
        "match_folder_names": "",    # 이 폴더의 하위 폴더 이름에 게임 이름을 맞춘다
    },
}


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(out.get(k), dict) and isinstance(v, dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _keep_minutes(d):
    """예전 설정의 보관 날 수(keep_days)를 분(keep_minutes)으로 옮긴다."""
    if isinstance(d, dict) and "keep_days" in d:
        days = d.pop("keep_days")
        if "keep_minutes" not in d:
            try:
                d["keep_minutes"] = max(0, round(float(days or 0) * 24 * 60))
            except (TypeError, ValueError):
                pass


def load():
    try:
        raw = safefile.read_json(paths.config_file())
        up = raw.get("upload") if isinstance(raw, dict) else None
        if isinstance(up, dict):
            _keep_minutes(up)
            for over in (up.get("game_overrides") or {}).values():
                _keep_minutes(over)
        cfg = _merge(DEFAULTS, raw)
        if "setup_done" not in raw:      # 안내가 생기기 전부터 쓰던 사용자
            cfg["setup_done"] = True
    except (FileNotFoundError, ValueError):
        cfg = copy.deepcopy(DEFAULTS)
    if not cfg["recording"]["video_root"]:
        cfg["recording"]["video_root"] = os.path.join(paths.videos_dir(), APP_NAME)
    try:
        limit = int(cfg["upload"]["daily_limit"])
    except (TypeError, ValueError):
        limit = DEFAULTS["upload"]["daily_limit"]
    cfg["upload"]["daily_limit"] = max(1, min(limit, UPLOAD_DAILY_MAX))
    return cfg


def save(cfg):
    safefile.write_json(paths.config_file(), cfg, indent=2)
