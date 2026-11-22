; Redbox 설치 파일(Inno Setup 6). packaging/build.py 가 버전과 폴더를 넘겨 준다.
; 관리자 권한 없이 사용자 폴더(%LOCALAPPDATA%\Programs\Redbox)에 설치한다.
; 설정과 기록(%APPDATA%\Redbox)은 지우지 않는다(다시 설치해도 이어서 쓰도록).

#ifndef AppVersion
  #define AppVersion "1.0.4"
#endif
#ifndef SetupVersion
  #define SetupVersion AppVersion
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\Redbox"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

[Setup]
AppId={{6F1E8D2A-4C3B-4E7A-9B1D-2A5C7E9F0B13}
AppName=Redbox
AppVersion={#AppVersion}
AppVerName=Redbox {#AppVersion}
AppPublisher=qusrby
AppPublisherURL=https://github.com/qusrby/redbox
AppSupportURL=https://github.com/qusrby/redbox/issues
AppUpdatesURL=https://github.com/qusrby/redbox/releases
DefaultDirName={localappdata}\Programs\Redbox
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=Redbox-Setup-{#SetupVersion}
SetupIconFile=redbox.ico
UninstallDisplayIcon={app}\Redbox.exe
UninstallDisplayName=Redbox
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
RestartApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; 업데이트할 때 이전 버전의 라이브러리 파일이 섞이지 않게 비운다
Type: filesandordirs; Name: "{app}\*"

[Icons]
Name: "{autoprograms}\Redbox"; Filename: "{app}\Redbox.exe"
Name: "{autodesktop}\Redbox"; Filename: "{app}\Redbox.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Redbox.exe"; Description: "{cm:LaunchProgram,Redbox}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im Redbox.exe"; Flags: runhidden; RunOnceId: "StopRedbox"

[Registry]
; 앱이 직접 등록하는 윈도우 시작 항목을 제거할 때 지운다
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Redbox"; Flags: uninsdeletevalue
