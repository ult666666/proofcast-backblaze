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
