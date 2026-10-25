"""Genblaze orchestration for ProofCast's audio and visual bundle."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from genblaze_core import Modality, Pipeline
from genblaze_core.models.asset import Asset

from proofcast.config import Settings
from proofcast.providers import AccessibleCoverProvider, LocalSpeechProvider
from proofcast.storage import build_sink
from proofcast.verification import BundleVerification, verify_bundle


@dataclass(frozen=True)
class GenerationRequest:
    title: str
    script: str
    voice: str = "Samantha"
    rate: int = 175
    engine: str = "auto"

    def validate(self, max_chars: int) -> None:
        if not self.title.strip():
            raise ValueError("Title is required")
        if len(self.title.strip()) > 90:
            raise ValueError("Title must be 90 characters or fewer")
        if not self.script.strip():
            raise ValueError("Script is required")
        if len(self.script) > max_chars:
            raise ValueError(f"Script must be {max_chars} characters or fewer")


@dataclass(frozen=True)
class GenerationResult:
    run_id: str
    manifest_path: Path
    canonical_hash: str
    verified: bool
    assets: tuple[Asset, ...]
    storage_mode: str
    providers_and_models: tuple[str, ...]
    verification: BundleVerification


def generate_bundle(
    request: GenerationRequest,
    settings: Settings | None = None,
) -> GenerationResult:
    settings = settings or Settings.from_env()
    settings.validate()
    request.validate(settings.max_script_chars)
    settings.output_dir.mkdir(parents=True, exist_ok=True)

    speech = LocalSpeechProvider(
        settings.output_dir,
        engine=request.engine,
        voice=request.voice,
        rate=request.rate,
        max_chars=settings.max_script_chars,
    )
    cover = AccessibleCoverProvider(settings.output_dir)
    sink = build_sink(settings)

    pipeline = Pipeline(
        "proofcast-accessibility-bundle",
        project_id="proofcast",
        max_concurrency=1,
        preflight=False,
    )
    pipeline.step(
        speech,
        model=speech.model_name,
        prompt=request.script.strip(),
        modality=Modality.AUDIO,
        voice=request.voice,
        rate=request.rate,
    )
    pipeline.step(
        cover,
        model=cover.model_name,
        prompt=request.script.strip(),
        modality=Modality.IMAGE,
        title=request.title.strip(),
    )
    result = pipeline.run(sink=sink, timeout=90, raise_on_failure=True)
    manifest_path = settings.output_dir / f"{result.run.run_id}-manifest.json"
    manifest_path.write_text(result.manifest.to_canonical_json(), encoding="utf-8")
    verification = verify_bundle(manifest_path)

    assets = tuple(asset for step in result.run.steps for asset in step.assets)
    providers_and_models = tuple(
        f"{step.provider} / {step.model}" for step in result.run.steps
    )
    return GenerationResult(
        run_id=result.run.run_id,
        manifest_path=manifest_path,
        canonical_hash=result.manifest.canonical_hash,
        verified=verification.verified,
        assets=assets,
        storage_mode=settings.storage_mode,
        providers_and_models=providers_and_models,
        verification=verification,
    )


def local_path_from_asset(asset: Asset) -> Path | None:
    parsed = urlparse(asset.url)
    if parsed.scheme != "file":
        return None
    return Path(unquote(parsed.path))


def result_as_dict(result: GenerationResult) -> dict[str, object]:
    return {
        "run_id": result.run_id,
        "manifest_path": str(result.manifest_path),
        "canonical_hash": result.canonical_hash,
        "verified": result.verified,
        "verification": result.verification.to_dict(),
        "storage_mode": result.storage_mode,
        "providers_and_models": list(result.providers_and_models),
        "assets": [asset.model_dump(mode="json") for asset in result.assets],
    }


def result_as_json(result: GenerationResult) -> str:
    return json.dumps(result_as_dict(result), indent=2, sort_keys=True)
