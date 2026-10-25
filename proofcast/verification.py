"""Read-only verification of a saved ProofCast manifest and local media bytes.

Recorded URLs are transport hints, never download instructions. Local filenames
come from validated step UUIDs, so bundles can move together without reading the
old absolute paths. Successful checks establish consistency, not authenticity.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import stat
from urllib.parse import unquote, urlparse
from uuid import UUID
import wave

from genblaze_core.exceptions import ManifestError
from genblaze_core.models.asset import Asset, AudioMetadata
from genblaze_core.models.manifest import Manifest
from genblaze_core.models.run import Run
from genblaze_core.models.step import Step
from PIL import Image, UnidentifiedImageError

MAX_MANIFEST_BYTES = 1024 * 1024
MAX_ASSET_BYTES = 32 * 1024 * 1024
SCOPE = (
    "Checks the supplied manifest's integrity and the two local media files' "
    "SHA-256, size and format metadata. No URL is fetched. Does not authenticate "
    "the author, prove the prompt produced the media, or verify remote uploads."
)


@dataclass(frozen=True)
class AssetVerification:
    filename: str
    media_type: str
    issues: tuple[str, ...]
    actual_sha256: str | None = None
    actual_size_bytes: int | None = None

    @property
    def verified(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "verified": self.verified}


@dataclass(frozen=True)
class BundleVerification:
    manifest_verified: bool = False
    issues: tuple[str, ...] = ()
    assets: tuple[AssetVerification, ...] = ()

    @property
    def assets_verified(self) -> bool:
        return len(self.assets) == 2 and all(asset.verified for asset in self.assets)

    @property
    def verified(self) -> bool:
        return self.manifest_verified and not self.issues and self.assets_verified

    def to_dict(self) -> dict[str, object]:
        return {
            "verified": self.verified,
            "manifest_verified": self.manifest_verified,
            "assets_verified": self.assets_verified,
            "issues": list(self.issues),
            "assets": [asset.to_dict() for asset in self.assets],
            "remote_assets_checked": False,
            "scope": SCOPE,
        }


class _FileRefused(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


def _unlinked_path(path: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink():
            raise _FileRefused("unsafe_file")


def _read_file(path: Path, limit: int) -> tuple[bytes, str]:
    """Read one bounded regular file, refusing links and concurrent changes."""
    try:
        _unlinked_path(path)
        initial = path.stat()
        if (
            not stat.S_ISREG(initial.st_mode)
            or initial.st_nlink != 1
            or initial.st_size > limit
        ):
            raise _FileRefused("unsafe_file")
        flags = (
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        )
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if (opened.st_dev, opened.st_ino) != (initial.st_dev, initial.st_ino):
                raise _FileRefused("unsafe_file")
            data = bytearray()
            digest = hashlib.sha256()
            while chunk := handle.read(min(1024 * 1024, limit + 1 - len(data))):
                data.extend(chunk)
                if len(data) > limit:
                    raise _FileRefused("unsafe_file")
                digest.update(chunk)
            after = os.fstat(handle.fileno())
        _unlinked_path(path)
        final = path.stat()

        def identity(s):
            return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)

        if identity(initial) != identity(after) or identity(after) != identity(final):
            raise _FileRefused("unsafe_file")
        if len(data) != after.st_size:
            raise _FileRefused("unsafe_file")
        return bytes(data), digest.hexdigest()
    except FileNotFoundError:
        raise _FileRefused("missing_file") from None
    except (OSError, ValueError):
        raise _FileRefused("unsafe_file") from None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _no_constant(value):
    raise ValueError("Non-finite JSON number")


def _known_keys(data: dict, model: type) -> None:
    if not isinstance(data, dict) or set(data) - set(model.model_fields):
        raise ValueError("Unsupported fields")


def _parse_manifest(data: bytes) -> Manifest:
    raw = json.loads(
        data.decode("utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=_no_constant,
    )
    _known_keys(raw, Manifest)
    if raw.get("schema_version") != "1.5" or "canonical_hash" not in raw:
        raise ValueError("Unsupported manifest")
    run = raw["run"]
    _known_keys(run, Run)
    if not {"run_id", "status", "project_id", "name", "steps"} <= run.keys():
        raise ValueError("Missing run contract")
    if not isinstance(run["steps"], list) or len(run["steps"]) != 2:
        raise ValueError("Expected two steps")
    for step in run["steps"]:
        _known_keys(step, Step)
        if (
            not {
                "step_id",
                "run_id",
                "step_index",
                "status",
                "provider",
                "model",
                "modality",
                "prompt",
                "assets",
            }
            <= step.keys()
        ):
            raise ValueError("Missing step contract")
        if not isinstance(step["assets"], list) or len(step["assets"]) != 1:
            raise ValueError("Expected one asset per step")
        asset = step["assets"][0]
        _known_keys(asset, Asset)
        if (
            not {"asset_id", "url", "media_type", "sha256", "size_bytes"}
            <= asset.keys()
        ):
            raise ValueError("Missing asset contract")
        if asset.get("audio") is not None:
            _known_keys(asset["audio"], AudioMetadata)
    # Strict JSON validation retains enum/date JSON support while refusing scalar coercion.
    return Manifest.model_validate_json(json.dumps(raw), strict=True)


def _uuid(value: str) -> bool:
    try:
        return str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def _transport_allowed(url: str, filename: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.query or parsed.fragment or parsed.username or parsed.password:
            return False
        if parsed.scheme == "https":
            return bool(parsed.hostname)
        local = Path(unquote(parsed.path))
        return (
            parsed.scheme == "file"
            and not parsed.netloc
            and local.is_absolute()
            and ".." not in local.parts
            and local.name == filename
        )
    except ValueError:
        return False


def _contract_ok(manifest: Manifest) -> bool:
    run = manifest.run
    if (
        run.name != "proofcast-accessibility-bundle"
        or run.project_id != "proofcast"
        or run.status != "completed"
        or not _uuid(run.run_id)
        or len(run.steps) != 2
    ):
        return False
    ids = []
    for index, (step, role) in enumerate(zip(run.steps, ("audio", "image"))):
        expected_provider = (
            "proofcast-local-speech"
            if role == "audio"
            else "proofcast-accessible-cover"
        )
        suffix = "-narration.wav" if role == "audio" else "-cover.png"
        mime = "audio/wav" if role == "audio" else "image/png"
        if (
            not _uuid(step.step_id)
            or step.run_id != run.run_id
            or step.step_index != index
            or step.status != "succeeded"
            or step.provider != expected_provider
            or step.modality != role
            or len(step.assets) != 1
            or not step.prompt
        ):
            return False
        asset = step.assets[0]
        if (
            not _uuid(asset.asset_id)
            or asset.media_type != mime
            or not isinstance(asset.size_bytes, int)
            or asset.size_bytes < 1
            or not _transport_allowed(asset.url, step.step_id + suffix)
        ):
            return False
        ids.extend((step.step_id, asset.asset_id))
    return len(set(ids)) == 4 and run.steps[0].prompt == run.steps[1].prompt


def _media_issues(data: bytes, asset: Asset, role: str) -> list[str]:
    try:
        if role == "image":
            with Image.open(BytesIO(data)) as image:
                if image.format != "PNG":
                    return ["invalid_media"]
                if image.size != (1280, 720) or image.size != (
                    asset.width,
                    asset.height,
                ):
                    return ["media_metadata_mismatch"]
                image.verify()
        else:
            with wave.open(BytesIO(data), "rb") as audio:
                metadata = asset.audio
                if (
                    metadata is None
                    or audio.getcomptype() != "NONE"
                    or audio.getsampwidth() != 2
                    or metadata.codec != "pcm_s16le"
                    or audio.getframerate() != metadata.sample_rate
                    or audio.getnchannels() != metadata.channels
                ):
                    return ["media_metadata_mismatch"]
                frames = audio.getnframes()
                if (
                    frames < 1
                    or len(audio.readframes(frames))
                    != frames * audio.getnchannels() * audio.getsampwidth()
                ):
                    return ["invalid_media"]
    except (
        OSError,
        ValueError,
        EOFError,
        wave.Error,
        UnidentifiedImageError,
        Image.DecompressionBombError,
    ):
        return ["invalid_media"]
    return []


def verify_bundle(
    manifest_path: Path, *, asset_dir: Path | None = None
) -> BundleVerification:
    """Inspect saved provenance and local media, without fetching recorded URLs.

    Files are selected only within ``asset_dir`` (default: manifest directory),
    using validated step IDs. Each asset is limited to 32 MiB and the manifest
    to 1 MiB. Reports deliberately exclude prompts and recorded URLs.
    """
    manifest_path = Path(manifest_path).absolute()
    try:
        data, _ = _read_file(manifest_path, MAX_MANIFEST_BYTES)
    except _FileRefused as error:
        return BundleVerification(issues=(error.code,))
    try:
        manifest = _parse_manifest(data)
        hash_ok = manifest.verify_hash()
    except (ValueError, TypeError, KeyError, RecursionError, ManifestError):
        return BundleVerification(issues=("invalid_manifest",))
    issues = []
    if not hash_ok:
        issues.append("manifest_hash_mismatch")
    if not manifest.verify() or not _contract_ok(manifest):
        issues.append("bundle_contract_mismatch")
    # An untrusted/invalid identity must never select a local filename.
    if not _contract_ok(manifest):
        return BundleVerification(hash_ok, tuple(issues))
    root = Path(asset_dir).absolute() if asset_dir is not None else manifest_path.parent
    reports = []
    for step, role in zip(manifest.run.steps, ("audio", "image")):
        asset = step.assets[0]
        name = step.step_id + ("-narration.wav" if role == "audio" else "-cover.png")
        try:
            media, digest = _read_file(root / name, MAX_ASSET_BYTES)
        except _FileRefused as error:
            reports.append(AssetVerification(name, asset.media_type, (error.code,)))
            continue
        failures = []
        if digest != asset.sha256:
            failures.append("digest_mismatch")
        if len(media) != asset.size_bytes:
            failures.append("size_mismatch")
        failures.extend(_media_issues(media, asset, role))
        reports.append(
            AssetVerification(
                name, asset.media_type, tuple(failures), digest, len(media)
            )
        )
    return BundleVerification(hash_ok, tuple(issues), tuple(reports))
