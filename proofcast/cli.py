"""Command-line interface for a local, no-account smoke test."""

from __future__ import annotations

import argparse

from proofcast.config import Settings
from proofcast.pipeline import GenerationRequest, generate_bundle, result_as_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a provenance-first audio brief")
    parser.add_argument("--title", required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("--voice", default="Samantha")
    parser.add_argument("--rate", type=int, default=175)
    parser.add_argument("--engine", choices=("auto", "say", "espeak-ng"), default="auto")
    parser.add_argument(
        "--allow-b2",
        action="store_true",
        help="Allow B2 only if B2_ENABLED=1 and all B2 settings are present",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
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
            voice=args.voice,
            rate=args.rate,
            engine=args.engine,
        ),
        settings,
    )
    print(result_as_json(result))


if __name__ == "__main__":
    main()

