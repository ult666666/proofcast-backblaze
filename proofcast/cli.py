"""Generate local briefs or inspect an existing bundle without network access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from proofcast.config import Settings
from proofcast.pipeline import GenerationRequest, generate_bundle, result_as_json
from proofcast.verification import verify_bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate or independently verify a local audio brief"
    )
    parser.add_argument(
        "--verify",
        type=Path,
        metavar="MANIFEST",
        help="Read-only manifest and local media verification; no generation or network",
    )
    parser.add_argument(
        "--asset-dir",
        type=Path,
        metavar="DIRECTORY",
        help="Local media directory for --verify (default: manifest directory)",
    )
    parser.add_argument("--title")
    parser.add_argument("--script")
    parser.add_argument("--voice")
    parser.add_argument("--rate", type=int)
    parser.add_argument("--engine", choices=("auto", "say", "espeak-ng"))
    parser.add_argument(
        "--allow-b2",
        action="store_true",
        help="Allow B2 generation only if B2_ENABLED=1 and all B2 settings are present",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.verify is not None:
        if (
            any(
                value is not None
                for value in (
                    args.title,
                    args.script,
                    args.voice,
                    args.rate,
                    args.engine,
                )
            )
            or args.allow_b2
        ):
            parser.error(
                "--verify cannot be combined with generation options or --allow-b2"
            )
        report = verify_bundle(args.verify, asset_dir=args.asset_dir)
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return 0 if report.verified else 1
    if args.asset_dir is not None:
        parser.error("--asset-dir requires --verify")
    if args.title is None or args.script is None:
        parser.error("generation requires both --title and --script")
    try:
        settings = Settings.from_env()
        if settings.b2_enabled and not args.allow_b2:
            settings = Settings(
                output_dir=settings.output_dir,
                max_script_chars=settings.max_script_chars,
            )
        result = generate_bundle(
            GenerationRequest(
                title=args.title,
                script=args.script,
                voice=args.voice if args.voice is not None else "Samantha",
                rate=args.rate if args.rate is not None else 175,
                engine=args.engine if args.engine is not None else "auto",
            ),
            settings,
        )
    except (RuntimeError, ValueError) as error:
        # Invalid input or a missing speech engine: one line, not a traceback.
        parser.exit(2, f"{parser.prog}: error: {error}\n")
    print(result_as_json(result))
    return 0 if result.verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
