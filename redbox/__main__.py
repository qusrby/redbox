"""명령줄 진입점.

  python -m redbox scan                  설치된 게임 목록을 모아 보여 준다
  python -m redbox shadow [--seconds N]  녹화 없이 감지 판정만 로그에 남긴다
  python -m redbox run                   게임을 감지해 OBS 로 녹화하고 유튜브에 올린다(데이터 폴더에 stop 파일을 만들면 끝남)
  python -m redbox auth [--key 키 파일]  유튜브 로그인(구글 클라우드에서 받은 client_secret.json)
  python -m redbox ui [--hidden]          화면 앱(트레이). 명령 없이 실행해도 화면 앱
"""
import argparse
import sys

from . import APP_NAME, VERSION, config, paths


def _out(text):
    if sys.stdout is None:      # 창 없이(pythonw) 실행하면 표준 출력이 없다
        return
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))


def cmd_scan(_args):
    from .detect import Catalog
    cfg = config.load()
    cat = Catalog(cfg["detection"])
    _out(f"{APP_NAME} {VERSION}  데이터 폴더: {paths.data_dir()}")
    from .detect.catalog import source_name
    for kind, n in cat.counts.items():
        _out(f"  {source_name(kind):16s} {n}")
    for kind, e in cat.errors.items():
        _out(f"  [오류] {kind}: {e}")
    _out("")
    for d, e in sorted(cat.dirs, key=lambda t: (t[1].source, t[1].name.lower())):
        _out(f"  [{source_name(e.source)}] {e.name}  ({e.exe or e.dir})")


def cmd_shadow(args):
    from .shadow import Shadow
    s = Shadow(config.load())
    _out(f"그림자 실행 로그: {s.log_path}")
    s.run(args.seconds)


def cmd_run(_args):
    from .service import Service, single_instance
    lock = single_instance()
    if lock is None:
        _out("이미 실행 중")
        return
    Service(config.load()).run()


def cmd_auth(args):
    from .uploader import youtube
    if args.key:
        youtube.import_secret(args.key)
        _out("키 파일 등록 완료")
    try:
        youtube.credentials(interactive=True)
    except youtube.AuthNeeded as e:
        _out(str(e))
        sys.exit(1)
    _out("유튜브 로그인 완료")


def cmd_ui(args):
    from .ui.app import main as ui_main
    sys.exit(ui_main(show=not args.hidden, restart=args.restart))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="redbox")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("scan")
    sub.add_parser("run")
    ui = sub.add_parser("ui")
    ui.add_argument("--hidden", action="store_true")
    ui.add_argument("--restart", action="store_true")   # 다시 실행: 이전 창이 끝날 때까지 잠깐 기다린다
    au = sub.add_parser("auth")
    au.add_argument("--key", default=None)
    sh = sub.add_parser("shadow")
    sh.add_argument("--seconds", type=float, default=None)
    args = ap.parse_args(argv)
    if not args.cmd:
        args = ap.parse_args(["ui"])
    {"scan": cmd_scan, "shadow": cmd_shadow, "run": cmd_run, "auth": cmd_auth, "ui": cmd_ui}[args.cmd](args)


if __name__ == "__main__":
    main()
