"""유튜브 연결. 사용자가 자기 구글 클라우드 프로젝트에서 받은 OAuth 키(client_secret.json)로 로그인한다.
키와 토큰은 데이터 폴더의 youtube\\ 에 둔다."""
import os
import shutil

from .. import paths

SCOPES = ["https://www.googleapis.com/auth/youtube"]   # 업로드, 조회, 재생목록, 삭제


class AuthNeeded(RuntimeError):
    """키가 없거나 로그인이 풀려서 사람이 다시 로그인해야 하는 상태."""


def auth_dir():
    d = os.path.join(paths.data_dir(), "youtube")
    os.makedirs(d, exist_ok=True)
    return d


def secret_file():
    return os.path.join(auth_dir(), "client_secret.json")


def token_file():
    return os.path.join(auth_dir(), "token.json")


def import_secret(src):
    """사용자가 받은 키 파일을 데이터 폴더로 복사한다."""
    shutil.copyfile(src, secret_file())


def has_secret():
    return os.path.exists(secret_file())


def _save(creds):
    tmp = token_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    os.replace(tmp, token_file())


def credentials(interactive=False, force=False):
    """저장된 토큰을 쓰고, 만료됐으면 갱신한다. interactive=True 일 때만 브라우저로 로그인한다.
    force=True 면 저장된 토큰을 쓰지 않고 브라우저로 다시 로그인한다(다른 계정으로 바꿀 때). 성공해야 토큰을 바꾼다."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if os.path.exists(token_file()) and not force:
        creds = Credentials.from_authorized_user_file(token_file(), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save(creds)
            return creds
        except RefreshError:
            if not interactive:
                raise AuthNeeded("유튜브 로그인 만료. 다시 로그인 필요")
    if not interactive:
        raise AuthNeeded("유튜브 로그인 필요")
    if not has_secret():
        raise AuthNeeded("구글 클라우드 키 파일(client_secret.json) 필요")
    flow = InstalledAppFlow.from_client_secrets_file(secret_file(), SCOPES)
    try:          # 브라우저 창을 그냥 닫으면 끝없이 기다리지 않게 5분에서 멈춘다
        creds = flow.run_local_server(port=0, open_browser=True, timeout_seconds=300)
    except Exception as e:
        raise AuthNeeded("유튜브 로그인 취소 또는 시간 초과") from e
    _save(creds)
    return creds


def channel_name():
    """로그인한 계정의 유튜브 채널 이름. 실패하면 None."""
    try:
        r = service().channels().list(part="snippet", mine=True).execute()
        return r["items"][0]["snippet"]["title"]
    except Exception:
        return None


def channel_id():
    """로그인한 계정의 유튜브 채널 ID(UC...). 실패하면 None."""
    try:
        r = service().channels().list(part="id", mine=True).execute()
        return r["items"][0]["id"]
    except Exception:
        return None


def studio_url(cid=None):
    """유튜브 스튜디오 채널 콘텐츠(동영상) 화면. 채널 ID 를 모르면 지금 로그인한 채널로 가는 주소."""
    return f"https://studio.youtube.com/channel/{cid or 'UC'}/videos/upload"


def service(interactive=False):
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=credentials(interactive), cache_discovery=False)


def signature():
    """토큰 파일이 바뀌었는지 알아보는 값(다른 곳에서 다시 로그인하면 연결을 새로 만든다)."""
    try:
        st = os.stat(token_file())
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


# -- API 호출 -----------------------------------------------------------------------------------
def upload(svc, path, title, privacy, description="", tags=None, category="20", progress=None):
    from googleapiclient.http import MediaFileUpload
    body = {
        "snippet": {"title": title[:100], "description": description, "tags": tags or [], "categoryId": str(category)},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(path, chunksize=8 * 1024 * 1024, resumable=True)
    req = svc.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status and progress:
            progress(status.progress())
    return resp["id"]


def find_playlist(svc, title):
    token = None
    while True:
        r = svc.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=token).execute()
        for it in r.get("items", []):
            if it["snippet"]["title"] == title:
                return it["id"]
        token = r.get("nextPageToken")
        if not token:
            return None


def create_playlist(svc, title):
    r = svc.playlists().insert(part="snippet,status",
                               body={"snippet": {"title": title}, "status": {"privacyStatus": "private"}}).execute()
    return r["id"]


def add_to_playlist(svc, playlist_id, video_id):
    svc.playlistItems().insert(part="snippet", body={"snippet": {
        "playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()


def channel_titles(svc):
    """채널에 올라간 영상 {제목: (video_id, 올린 시각)}. 실패하면 None."""
    try:
        ch = svc.channels().list(part="contentDetails", mine=True).execute()
        pl = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        out, token = {}, None
        while True:
            r = svc.playlistItems().list(part="snippet", playlistId=pl, maxResults=50, pageToken=token).execute()
            for it in r.get("items", []):
                sn = it["snippet"]
                out[sn["title"]] = (sn["resourceId"]["videoId"], sn.get("publishedAt"))
            token = r.get("nextPageToken")
            if not token:
                return out
    except Exception:
        return None


def processed_ok(svc, video_ids):
    """유튜브 처리(processingStatus)가 끝난 video_id 집합."""
    ok = set()
    ids = list(video_ids)
    for i in range(0, len(ids), 50):
        r = svc.videos().list(part="processingDetails", id=",".join(ids[i:i + 50])).execute()
        for it in r.get("items", []):
            if it.get("processingDetails", {}).get("processingStatus") == "succeeded":
                ok.add(it["id"])
    return ok


def delete(svc, video_id):
    svc.videos().delete(id=video_id).execute()
