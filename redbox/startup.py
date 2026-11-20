"""윈도우 시작 시 실행(HKCU Run). 앱이 직접 관리한다: 설정이 켜져 있으면 자기 실행 명령을 등록하고, 꺼져 있으면 지운다."""
import os
import sys
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "Redbox"


def command():
    """트레이로만 켜는 명령. 묶은 exe 면 exe 자신, 아니면 pythonw 로 Redbox.pyw."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --hidden'
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pyw):
        exe = pyw
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Redbox.pyw")
    return f'"{exe}" "{script}" --hidden'


def current():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, NAME)[0]
    except OSError:
        return None


def apply(enabled):
    """설정에 맞춰 등록하거나 지운다. 바뀌었으면 True."""
    want = command() if enabled else None
    have = current()
    if want == have:
        return False
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if want:
            winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, want)
        else:
            try:
                winreg.DeleteValue(k, NAME)
            except FileNotFoundError:
                pass
    return True
