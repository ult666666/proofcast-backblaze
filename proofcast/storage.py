"""Backblaze B2 sink construction, isolated behind the explicit cloud gate."""

from __future__ import annotations

from genblaze_core import KeyStrategy, ObjectStorageSink
from genblaze_s3 import S3StorageBackend

from proofcast.config import Settings


def build_sink(settings: Settings) -> ObjectStorageSink | None:
    """Return a B2 sink only when B2_ENABLED=1 and all values validate."""
    settings.validate()
    if not settings.b2_enabled:
        return None
    backend = S3StorageBackend.for_backblaze(
        bucket=settings.b2_bucket,
        region=settings.b2_region,
        key_id=settings.b2_key_id,
        app_key=settings.b2_app_key,
        public_url_base=settings.b2_public_url_base,
        preflight=True,
        auto_lifecycle=False,
    )
    return ObjectStorageSink(
        backend,
        prefix=settings.b2_prefix,
        key_strategy=KeyStrategy.CONTENT_ADDRESSABLE,
    )

