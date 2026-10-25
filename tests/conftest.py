from pathlib import Path
import wave

import pytest

from proofcast.config import Settings
from proofcast.pipeline import GenerationRequest, generate_bundle
from proofcast.providers import LocalSpeechProvider


@pytest.fixture
def local_bundle(tmp_path: Path, monkeypatch):
    # Replace only OS synthesis; the real pipeline, WAV/PNG files and manifest remain.
    def write_wave(self, script, destination):
        with wave.open(str(destination), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(22050)
            handle.writeframes(b"\x00\x00" * 2205)

    monkeypatch.setattr(LocalSpeechProvider, "_generate_with_say", write_wave)
    return generate_bundle(
        GenerationRequest(
            title="Independent verification", script="Check the source.", engine="say"
        ),
        Settings(output_dir=tmp_path),
    )
