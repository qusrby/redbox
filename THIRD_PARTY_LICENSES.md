# 함께 배포하는 구성 요소의 라이선스

Redbox 는 GPL v3 로 배포합니다(`LICENSE`). 설치 파일에는 아래 구성 요소가 함께 들어 있습니다.

| 구성 요소 | 라이선스 | 주소 |
|---|---|---|
| PyQt6 | GPL v3 | https://www.riverbankcomputing.com/software/pyqt/ |
| Qt 6 (PyQt6-Qt6) | LGPL v3 | https://www.qt.io/ |
| obsws-python | GPL v3 | https://github.com/aatikturk/obsws-python |
| psutil | BSD 3-Clause | https://github.com/giampaolo/psutil |
| RapidFuzz | MIT | https://github.com/rapidfuzz/RapidFuzz |
| google-api-python-client | Apache 2.0 | https://github.com/googleapis/google-api-python-client |
| google-auth, google-auth-oauthlib, google-auth-httplib2 | Apache 2.0 | https://github.com/googleapis/google-auth-library-python |
| httplib2 | MIT | https://github.com/httplib2/httplib2 |
| requests-oauthlib | ISC | https://github.com/requests/requests-oauthlib |
| websocket-client | Apache 2.0 | https://github.com/websocket-client/websocket-client |
| Python | PSF License | https://www.python.org/ |
| Pretendard 글꼴 | SIL Open Font License 1.1 (`redbox/assets/fonts/OFL.txt`) | https://github.com/orioncactus/pretendard |

exe 는 PyInstaller 로 묶었습니다. PyInstaller 부트로더는 GPL v2 이상에 묶은 프로그램 배포를 허용하는 예외 조항이 붙어 있습니다.
