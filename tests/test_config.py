from pathlib import Path

import pytest

from proofcast.config import Settings
from proofcast import storage
from proofcast.storage import build_sink


def test_local_mode_never_constructs_cloud_sink(tmp_path: Path) -> None:
    settings = Settings(output_dir=tmp_path, b2_enabled=False)
    assert build_sink(settings) is None
    assert settings.storage_mode == "local-only"


def test_enabled_b2_requires_every_value(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="required values are missing"):
        Settings(output_dir=tmp_path, b2_enabled=True).validate()


def test_public_url_must_be_https(tmp_path: Path) -> None:
    settings = Settings(
        output_dir=tmp_path,
        b2_enabled=True,
        b2_bucket="bucket",
        b2_region="us-west-004",
        b2_key_id="key",
        b2_app_key="secret",
        b2_public_url_base="http://example.test/file/bucket",
    )
    with pytest.raises(ValueError, match="must use HTTPS"):
        settings.validate()


def test_b2_sink_uses_scoped_settings_and_content_addressing(
    tmp_path: Path, monkeypatch
) -> None:
    captured: dict[str, object] = {}
    fake_backend = object()

    def fake_for_backblaze(**kwargs):
        captured["backend_kwargs"] = kwargs
        return fake_backend

    def fake_sink(backend, *, prefix, key_strategy):
        captured["sink"] = (backend, prefix, key_strategy)
        return "configured-sink"

    monkeypatch.setattr(storage.S3StorageBackend, "for_backblaze", fake_for_backblaze)
    monkeypatch.setattr(storage, "ObjectStorageSink", fake_sink)
    settings = Settings(
        output_dir=tmp_path,
        b2_enabled=True,
        b2_bucket="proofcast-demo",
        b2_region="us-west-004",
        b2_key_id="scoped-key",
        b2_app_key="one-time-secret",
        b2_public_url_base="https://f004.backblazeb2.com/file/proofcast-demo",
        b2_prefix="proofcast",
    )

    assert build_sink(settings) == "configured-sink"
    assert captured["backend_kwargs"] == {
        "bucket": "proofcast-demo",
        "region": "us-west-004",
        "key_id": "scoped-key",
        "app_key": "one-time-secret",
        "public_url_base": "https://f004.backblazeb2.com/file/proofcast-demo",
        "preflight": True,
        "auto_lifecycle": False,
    }
    backend, prefix, key_strategy = captured["sink"]
    assert backend is fake_backend
    assert prefix == "proofcast"
    assert key_strategy == storage.KeyStrategy.CONTENT_ADDRESSABLE
