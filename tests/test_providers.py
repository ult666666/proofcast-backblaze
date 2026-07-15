from pathlib import Path
import wave

from genblaze_core import Modality, Pipeline

from proofcast.providers import AccessibleCoverProvider, LocalSpeechProvider


def test_cover_provider_creates_hashable_png(tmp_path: Path) -> None:
    provider = AccessibleCoverProvider(tmp_path)
    result = (
        Pipeline("cover-test", preflight=False)
        .step(
            provider,
            model=provider.model_name,
            prompt="A safe training lesson",
            modality=Modality.IMAGE,
            title="Safety in sixty seconds",
        )
        .run(raise_on_failure=True)
    )
    asset = result.run.steps[0].assets[0]
    assert asset.media_type == "image/png"
    assert asset.sha256 and len(asset.sha256) == 64
    assert result.manifest.verify()


def _write_test_wave(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(22050)
        handle.writeframes(b"\x00\x00" * 2205)


def test_speech_provider_uses_local_engine_and_verifies(tmp_path: Path, monkeypatch) -> None:
    provider = LocalSpeechProvider(tmp_path, engine="say", voice="Samantha")
    monkeypatch.setattr(provider, "_generate_with_say", lambda script, path: _write_test_wave(path))
    result = (
        Pipeline("speech-test", preflight=False)
        .step(
            provider,
            model=provider.model_name,
            prompt="This is a short local narration test.",
            modality=Modality.AUDIO,
        )
        .run(raise_on_failure=True)
    )
    asset = result.run.steps[0].assets[0]
    assert asset.media_type == "audio/wav"
    assert asset.metadata["network_calls"] == 0
    assert result.run.steps[0].cost_usd == 0.0
    assert result.manifest.verify()
