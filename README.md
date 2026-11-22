# Redbox

게임 실행을 감지해 OBS Studio 로 자동 녹화하고, 유튜브 비공개 업로드 뒤 PC 에서 정리

## 기능

- 첫 실행 안내: 언어, OBS 연결(설치 확인, 웹소켓 자동 켜기, 연결 시험), 영상 폴더, 유튜브 연결(건너뛰기 가능), 윈도우 시작 시 실행. 안내를 마쳐야 녹화 시작
- 게임 감지: 스팀으로 설치한 게임은 자동 녹화(스팀 게임 폴더에서 게임 창을 띄운 프로그램)
- 직접 추가: 스팀 밖 게임은 '게임 추가'에서 골라 녹화. 후보는 최근 게임처럼 실행된 프로그램, 다른 런처(Riot, Epic Games, GOG, Ubisoft Connect, EA app, Battle.net, Xbox)에 설치된 게임, 윈도우가 게임으로 알아본 프로그램이고, 실행 파일을 직접 고를 수도 있음
- 게임별 녹화 여부(녹화, 제외)
- 다시보기, 관전처럼 직접 플레이가 아닌 실행은 녹화 제외(리그 오브 레전드)
- OBS 자동 녹화: 게임 창을 찾아 캡처 대상을 바꾸고 게임별 폴더에 녹화, 끝나면 `게임 Video 시작시각 길이.mp4` 로 이름 정리
- 창을 못 찾은 채 금방 끝난 실행은 녹화 후 영상 삭제, 사용자가 직접 켠 녹화는 건드리지 않음
- OBS 캡처 소스가 없으면 전용 장면과 소스를 만들어 씀
- 오디오: 마이크 녹음 켬, 끔과 녹음 대상(게임 소리만, PC 전체 소리). 녹화 동안만 OBS 음소거를 맞추고 끝나면 되돌림
- 유튜브 업로드(선택): 녹화가 끝나면 올리고(기본 비공개, 설정에서 일부 공개나 공개 선택) 게임 이름의 재생목록에 추가(설정에서 끄기)
- 길이 규칙: 기준보다 짧은 영상은 올리지 않음, 아주 짧은 영상은 삭제, 업로드 뒤 녹화본 삭제 시점(게임별 규칙 가능). 규칙을 바꾸면 이미 판정한 영상은 그대로 두고, 판정이 달라지는 영상에 경고와 검토 창(적용, 녹화본 삭제, 취소)
- PC 정리: 유튜브 처리가 끝난 것을 확인하고 정한 기간(기본 7일)이 지나면 녹화본 삭제
- 업로드 도중 PC 가 꺼지거나 앱이 다시 켜지면 끊긴 지점부터 이어 올리고, 유튜브 처리가 멈춘 영상은 자동으로 정리하고 다시 업로드
- 화면: 트레이 아이콘(녹화 중이면 빨간색), 대시보드, 영상, 게임, 설정
- 대시보드: 녹화 상태(녹화 중이면 게임과 경과 시간, OBS Studio 가 꺼져 있으면 실행 버튼), 앱, OBS Studio, OBS 연결, 유튜브 상태(올리는 영상과 진행률), 최근 영상, YouTube 스튜디오 바로가기
- 영상: 녹화한 영상 목록(목록 또는 카드 보기, 녹화 중 찍어 둔 장면 썸네일과 길이, 파일 이름, 게임 세로 표지, 업로드 단계와 녹화본 파일 상태를 한 칸에, 필터와 검색)
- 게임: 스팀 게임, 직접 추가한 게임, 녹화 기록이 있는 게임 목록과 게임별 녹화 여부, 업로드 규칙
- 녹화를 막는 문제(OBS Studio 꺼짐 등)는 화면 위 알림 띠로 표시
- 게임 그림: 스팀 게임은 스팀이 PC 에 받아 둔 대표 그림과 세로 표지(없으면 스팀 상점 그림), 직접 추가한 게임은 아이콘이나 사용자가 고른 그림. 보관해 두어 게임을 지워도 유지
- 한국어, 영어(윈도우 언어를 따르고 설정에서 변경)
- 윈도우를 켜면 트레이로 자동 시작(설정에서 끄기)
- 새 버전 알림: 깃허브 Releases 에 새 버전이 나오면 트레이 알림과 설정 화면으로 알림(설치는 하지 않음, 설정에서 끄기)
- 그림자 실행: 녹화 없이 감지 판정만 로그에 남겨 확인

## 동작 환경

- Windows 10, 11 (64비트)
- OBS Studio 28 이상(웹소켓 서버는 첫 실행 안내에서 자동으로 켬)
- 소스로 실행할 때는 Python 3.11 이상

## 설치

1. [Releases](https://github.com/qusrby/redbox/releases/latest)에서 `Redbox-Setup-<버전>.exe` 를 내려받아 실행
2. 관리자 권한 없이 `%LOCALAPPDATA%\Programs\Redbox` 에 설치되고 시작 메뉴에 등록됨
3. 처음 켜면 첫 실행 안내가 뜸

코드 서명을 하지 않은 설치 파일이라, 처음 실행할 때 윈도우의 'Windows의 PC 보호' 화면이 뜰 수 있습니다. **추가 정보**를 누르고 **실행**을 누르면 설치됩니다.

제거는 윈도우 설정의 앱 목록에서 합니다. 설정과 녹화 기록(`%APPDATA%\Redbox`)과 영상 파일은 남습니다.

### 소스로 실행

```bash
pip install -r requirements.txt
python -m redbox
```

### 직접 빌드

```bash
pip install -r requirements.txt -r packaging/requirements-build.txt
python packaging/build.py
```

`dist/Redbox/Redbox.exe`(폴더형 exe)와 `dist/Redbox-Setup-<버전>.exe`(설치 파일)가 만들어집니다. 설치 파일에는 [Inno Setup 6](https://jrsoftware.org/isinfo.php)이 필요하고, 없으면 exe 까지만 만듭니다.

앱 안과 윈도우 앱 목록에 보이는 버전은 `주.부.수정.커밋 수`(예: `1.0.1.14`)입니다. 마지막 자리는 저장소 전체 커밋 수라, 같은 1.0.1 이라도 커밋이 더 쌓인 빌드는 숫자가 다릅니다. 릴리스 태그와 설치 파일 이름은 `1.0.1` 처럼 세 자리를 씁니다.

## 유튜브 연결

업로드는 사용자 본인의 구글 클라우드 프로젝트 키로 동작합니다. 첫 실행 안내의 유튜브 단계나 설정 화면에서 연결하고, 키 만드는 법은 [유튜브 키 만들기](docs/youtube-key.md)에 있습니다.

명령줄로 연결하려면 `python -m redbox auth --key 내려받은파일.json` 실행 후 브라우저에서 로그인하고, 설정 파일의 `upload.enabled` 를 `true` 로 바꿉니다.

## 실행

```bash
python -m redbox
python -m redbox scan
python -m redbox shadow
python -m redbox run
```

- 명령 없이 실행하면 화면 앱(트레이). 창을 닫아도 트레이에서 계속 동작하고, 트레이 메뉴의 종료로 끝냄
- `scan`: 설치된 게임 목록을 모아 보여 줌
- `shadow`: 녹화 없이 감지 판정만 로그에 남김. 데이터 폴더에 `shadow.stop` 파일을 만들면 끝남
- `run`: 게임을 감지해 OBS 로 녹화하고, 업로드를 켰으면 유튜브에 올림. 데이터 폴더에 `stop` 파일을 만들면 녹화를 정리하고 끝남
- `auth`: 유튜브 로그인
- 설정, 로그 위치: `%APPDATA%\Redbox`

## 파일 구성

| 파일 | 역할 |
|------|------|
| `redbox/config.py` | 설정 기본값, 읽기와 저장 |
| `redbox/paths.py` | 데이터 폴더, 동영상 폴더 위치 |
| `redbox/detect/catalog.py` | 윈도우 게임 목록과 런처 설치 정보 모으기 |
| `redbox/detect/detector.py` | 실행 중인 프로세스의 녹화 여부 판정 |
| `redbox/detect/rules.py` | 기본 제외 목록 |
| `redbox/detect/win32.py` | 프로세스, 창, 모듈, 파일 버전 정보 조회 |
| `redbox/detect/nonplay.py` | 다시보기, 관전 실행 거르기 |
| `redbox/recorder/obs.py` | OBS 연결, 캡처 소스 준비, 녹화 시작과 정지 |
| `redbox/recorder/session.py` | 녹화 세션: 시작, 창 다시 찾기, 정지와 파일 정리 |
| `redbox/recorder/files.py` | 파일 이름 정리, 안전한 이동, 스크린샷 정리 |
| `redbox/recorder/naming.py` | 게임 폴더 이름(상표 기호 제거, 기존 폴더 이름에 맞추기) |
| `redbox/uploader/worker.py` | 업로드 스레드: 길이 규칙, 업로드, 재생목록, 처리 확인과 PC 정리 |
| `redbox/uploader/youtube.py` | 유튜브 로그인과 API 호출 |
| `redbox/uploader/store.py` | 업로드 상태 저장(`uploads.json`) |
| `redbox/uploader/media.py` | 영상 길이, 사용 중 확인, 안전한 삭제 |
| `redbox/thumbs.py` | 녹화 중 OBS 화면을 찍어 두었다가 녹화본 썸네일로 저장 |
| `redbox/safefile.py` | 정전에도 깨지지 않는 설정과 기록 파일 저장(직전 사본 보관) |
| `redbox/startup.py` | 윈도우 시작 시 실행 등록과 해제 |
| `redbox/service.py` | 상시 실행 본체(감지, 녹화, 업로드 스레드) |
| `redbox/shadow.py` | 그림자 실행 |
| `redbox/i18n.py` | 화면 문구(한국어, 영어) |
| `redbox/ui/app.py` | 화면 앱: 트레이, 서비스 스레드 |
| `redbox/ui/window.py` | 메인 창: 왼쪽 메뉴, 한 줄 상태, 알림 띠 |
| `redbox/ui/dashboard.py` | 대시보드(녹화 상태, 연결 상태, 최근 영상) |
| `redbox/ui/videos.py` | 영상 목록(목록 표와 날짜별 카드) |
| `redbox/ui/games.py` | 게임 목록(녹화 규칙, 게임별 업로드 규칙) |
| `redbox/ui/settings.py` | 설정 |
| `redbox/ui/setup.py` | 첫 실행 안내 |
| `redbox/ui/dialogs.py` | 대화 상자(다시 실행, 게임별 업로드 규칙) |
| `redbox/ui/widgets.py` | 공통 부품(표, 탭, 토글, 드롭다운, 부드러운 스크롤) |
| `redbox/artwork.py` | 플랫폼별 게임 그림 찾기와 보관 |
| `redbox/ui/art.py` | 카드와 목록용 게임 그림, 기본 타일 |
| `redbox/ui/icons.py` | 선 아이콘 |
| `redbox/ui/style.py` | 색, 글꼴, 스타일, 앱 아이콘 |
| `redbox/ui/frame.py` | 제목 표시줄 없는 창: 창 버튼, 이동과 크기 조절 |
| `Redbox.pyw` | 콘솔 창 없이 실행하는 진입 파일 |
| `docs/youtube-key.md` | 유튜브 키 만들기 안내 |
| `redbox/updater.py` | 새 버전 확인(깃허브 Releases) |
| `redbox/assets/fonts/` | Pretendard 글꼴(OFL) |
| `packaging/build.py` | 아이콘, exe, 설치 파일 빌드 |
| `packaging/make_icon.py` | 로고로 exe 아이콘 만들기 |
| `packaging/redbox.iss` | Inno Setup 설치 파일 설정 |

## 라이선스

GPL v3(`LICENSE`). 함께 배포하는 구성 요소의 라이선스는 `THIRD_PARTY_LICENSES.md` 에 있습니다.
