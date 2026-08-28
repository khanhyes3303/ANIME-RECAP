from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import MvpError
from .workflow import new_state
from .workspace import create_job


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_episode.py", description="Review đúng một tập anime bằng Antigravity"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start", help="Tạo job cho đúng một video")
    start.add_argument("--anime", required=True)
    start.add_argument("--season", required=True, type=int)
    start.add_argument("--episode", required=True, type=int)
    start.add_argument("--video", required=True, type=Path)
    for name in ("prepare", "validate", "tts", "render", "audit", "package"):
        command = subparsers.add_parser(name)
        command.add_argument("--run", required=True, type=Path)
    return parser


def _start(args: argparse.Namespace) -> int:
    root = Path.cwd()
    paths = create_job(root, args.anime, args.season, args.episode, args.video)
    state = new_state(
        paths.temp_dir,
        episode_dir=paths.episode_dir,
        source_video=paths.source_video,
    )
    next_action = {
        "stage": state.stage.value,
        "instruction": "Đọc Bo_nao_Antigravity/GEMINI.md rồi chạy bước prepare.",
        "run_dir": str(state.run_dir),
    }
    (state.run_dir / "next_action.json").write_text(
        json.dumps(next_action, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(state.run_dir)
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            return _start(args)
        parser.error(f"subcommand wiring is not ready: {args.command}")
    except MvpError as exc:
        parser.error(str(exc))
    return 2
