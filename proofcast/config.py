"""Runtime configuration with an explicit no-cloud-by-default safety gate."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    output_dir: Path = Path("output")
    max_script_chars: int = 1200
    b2_enabled: bool = False
    b2_bucket: str | None = None
    b2_region: str | None = None
    b2_key_id: str | None = None
    b2_app_key: str | None = None
    b2_public_url_base: str | None = None
    b2_prefix: str = "proofcast"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            output_dir=Path(os.getenv("PROOFCAST_OUTPUT_DIR", "output")),
            max_script_chars=int(os.getenv("PROOFCAST_MAX_SCRIPT_CHARS", "1200")),
            b2_enabled=_enabled(os.getenv("B2_ENABLED")),
            b2_bucket=os.getenv("B2_BUCKET"),
            b2_region=os.getenv("B2_REGION"),
            b2_key_id=os.getenv("B2_KEY_ID"),
            b2_app_key=os.getenv("B2_APP_KEY"),
            b2_public_url_base=os.getenv("B2_PUBLIC_URL_BASE"),
            b2_prefix=os.getenv("B2_PREFIX", "proofcast"),
        )

    def validate(self) -> None:
        if self.max_script_chars < 100 or self.max_script_chars > 5000:
            raise ValueError("PROOFCAST_MAX_SCRIPT_CHARS must be between 100 and 5000")
        if not self.b2_enabled:
            return
        values = {
            "B2_BUCKET": self.b2_bucket,
            "B2_REGION": self.b2_region,
            "B2_KEY_ID": self.b2_key_id,
            "B2_APP_KEY": self.b2_app_key,
            "B2_PUBLIC_URL_BASE": self.b2_public_url_base,
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise ValueError(
                "B2_ENABLED=1 but required values are missing: " + ", ".join(missing)
            )
        if not str(self.b2_public_url_base).startswith("https://"):
            raise ValueError("B2_PUBLIC_URL_BASE must use HTTPS")

    @property
    def storage_mode(self) -> str:
        return "Backblaze B2" if self.b2_enabled else "local-only"

