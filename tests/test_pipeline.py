from pathlib import Path
import wave

from proofcast.config import Settings
from proofcast.pipeline import GenerationRequest, generate_bundle, local_path_from_asset
from proofcast.providers import LocalSpeechProvider


def _write_test_wave(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(22050)
        handle.writeframes(b"\x00\x00" * 2205)


def test_end_to_end_local_bundle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        LocalSpeechProvider,
        "_generate_with_say",
        lambda self, script, path: _write_test_wave(path),
    )
    result = generate_bundle(
        GenerationRequest(
            title="A tiny lesson",
            script="Verify requests through a second channel before taking action.",
            engine="say",
        ),
        Settings(output_dir=tmp_path, max_script_chars=300),
    )
    assert result.verified is True
    assert result.storage_mode == "local-only"
    assert len(result.assets) == 2
    assert result.manifest_path.exists()
    assert {asset.media_type for asset in result.assets} == {"audio/wav", "image/png"}
    assert all(local_path_from_asset(asset).exists() for asset in result.assets)


def test_generation_exposes_manifest_and_local_byte_results(local_bundle):
    from proofcast.pipeline import result_as_dict

    report = result_as_dict(local_bundle)
    assert report["verified"] is True
    assert report["verification"]["manifest_verified"] is True
    assert report["verification"]["assets_verified"] is True
    assert report["verification"]["remote_assets_checked"] is False
    assert len(report["verification"]["assets"]) == 2


def test_generation_does_not_claim_verified_for_wrong_media_dimensions(
    tmp_path, monkeypatch
):
    from PIL import Image
    from proofcast.providers import AccessibleCoverProvider

    monkeypatch.setattr(
        LocalSpeechProvider,
        "_generate_with_say",
        lambda self, script, path: _write_test_wave(path),
    )
    monkeypatch.setattr(
        AccessibleCoverProvider,
        "_render",
        lambda self, title, prompt: Image.new("RGB", (640, 720)),
    )
    result = generate_bundle(
        GenerationRequest(
            title="Wrong dimensions", script="Check the source.", engine="say"
        ),
        Settings(output_dir=tmp_path),
    )
    assert result.verified is False
