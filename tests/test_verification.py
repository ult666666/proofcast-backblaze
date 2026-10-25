import hashlib
import json
import shutil
import socket

import pytest
from genblaze_core.models.manifest import Manifest


def inspect(manifest_path, **kwargs):
    from proofcast.verification import verify_bundle

    return verify_bundle(manifest_path, **kwargs)


def media(result, suffix):
    return next(result.manifest_path.parent.glob("*" + suffix))


def rewrite(result, change, *, rehash=False):
    data = json.loads(result.manifest_path.read_text())
    change(data)
    if rehash:
        manifest = Manifest.model_validate(data)
        manifest.compute_hash()
        data = manifest.model_dump(mode="json")
    result.manifest_path.write_text(json.dumps(data))


def test_valid_bundle_checks_actual_local_media(local_bundle):
    report = inspect(local_bundle.manifest_path)
    assert report.verified
    assert report.manifest_verified
    assert report.assets_verified
    assert len(report.assets) == 2
    assert report.issues == ()
    assert report.to_dict()["remote_assets_checked"] is False
    assert all(asset.verified for asset in report.assets)


def test_same_size_tampering_fails_even_when_manifest_hash_is_valid(local_bundle):
    audio = media(local_bundle, "-narration.wav")
    data = audio.read_bytes()
    audio.write_bytes(data[:-2] + b"\x01\x00")
    assert Manifest.model_validate_json(local_bundle.manifest_path.read_text()).verify()
    report = inspect(local_bundle.manifest_path)
    assert not report.verified
    assert report.manifest_verified
    assert not report.assets_verified
    assert "digest_mismatch" in report.assets[0].issues


def test_missing_media_is_an_explicit_failure(local_bundle):
    media(local_bundle, "-cover.png").unlink()
    report = inspect(local_bundle.manifest_path)
    assert not report.verified
    assert "missing_file" in report.assets[1].issues


def test_changed_prompt_fails_manifest_integrity(local_bundle):
    rewrite(
        local_bundle, lambda d: d["run"]["steps"][0].update(prompt="Changed source.")
    )
    report = inspect(local_bundle.manifest_path)
    assert not report.verified
    assert not report.manifest_verified
    assert "manifest_hash_mismatch" in report.issues


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("size_bytes", 1, "size_mismatch"),
        ("width", 640, "media_metadata_mismatch"),
        ("media_type", "image/jpeg", "bundle_contract_mismatch"),
    ],
)
def test_rehashed_image_metadata_must_still_match_bytes(
    local_bundle, field, value, code
):
    rewrite(
        local_bundle,
        lambda d: d["run"]["steps"][1]["assets"][0].update({field: value}),
        rehash=True,
    )
    report = inspect(local_bundle.manifest_path)
    assert report.manifest_verified
    assert not report.verified
    assert code in report.issues or code in report.assets[1].issues


def test_rehashed_wave_metadata_must_match_real_header(local_bundle):
    rewrite(
        local_bundle,
        lambda d: d["run"]["steps"][0]["assets"][0]["audio"].update(sample_rate=48000),
        rehash=True,
    )
    report = inspect(local_bundle.manifest_path)
    assert report.manifest_verified
    assert not report.verified
    assert "media_metadata_mismatch" in report.assets[0].issues


def test_recorded_failed_status_cannot_be_reported_as_verified(local_bundle):
    rewrite(local_bundle, lambda d: d["run"].update(status="failed"))
    report = inspect(local_bundle.manifest_path)
    assert report.manifest_verified
    assert not report.verified
    assert "bundle_contract_mismatch" in report.issues


def test_wrong_step_role_is_rejected_even_after_rehash(local_bundle):
    rewrite(
        local_bundle,
        lambda d: d["run"]["steps"][0].update(provider="other-provider"),
        rehash=True,
    )
    report = inspect(local_bundle.manifest_path)
    assert report.manifest_verified
    assert not report.verified
    assert "bundle_contract_mismatch" in report.issues


def test_bundle_can_be_moved_without_following_original_absolute_paths(
    local_bundle, tmp_path
):
    relocated = tmp_path / "moved"
    relocated.mkdir()
    for original in list(tmp_path.iterdir()):
        if original.is_file():
            shutil.move(str(original), relocated)
    assert inspect(relocated / local_bundle.manifest_path.name).verified


def test_explicit_asset_directory_supports_separately_stored_manifest(
    local_bundle, tmp_path
):
    elsewhere = tmp_path / "manifests"
    elsewhere.mkdir()
    manifest_path = elsewhere / "bundle.json"
    shutil.copyfile(local_bundle.manifest_path, manifest_path)
    assert inspect(manifest_path, asset_dir=tmp_path).verified
    assert not inspect(manifest_path).verified


def test_https_transport_is_never_fetched_or_claimed_verified(
    local_bundle, monkeypatch
):
    rewrite(
        local_bundle,
        lambda d: [
            a.update(url="https://example.invalid/" + a["sha256"])
            for s in d["run"]["steps"]
            for a in s["assets"]
        ],
    )

    def no_network(*args, **kwargs):
        pytest.fail("Offline verification attempted network access")

    monkeypatch.setattr(socket, "socket", no_network)
    report = inspect(local_bundle.manifest_path)
    assert report.verified
    assert report.to_dict()["remote_assets_checked"] is False


def test_symlink_asset_is_refused(local_bundle, tmp_path):
    audio = media(local_bundle, "-narration.wav")
    target = tmp_path / "outside.wav"
    audio.rename(target)
    audio.symlink_to(target)
    report = inspect(local_bundle.manifest_path)
    assert not report.verified
    assert "unsafe_file" in report.assets[0].issues


def test_file_url_cannot_select_an_unrelated_local_file(local_bundle):
    rewrite(
        local_bundle,
        lambda d: d["run"]["steps"][0]["assets"][0].update(url="file:///etc/passwd"),
    )
    report = inspect(local_bundle.manifest_path)
    assert not report.verified
    assert "bundle_contract_mismatch" in report.issues


@pytest.mark.parametrize(
    "payload",
    [
        b"{",
        b"null",
        b'{"canonical_hash":"x","canonical_hash":"y"}',
        b'{"run":NaN}',
        b"\xff",
    ],
)
def test_malformed_manifest_is_bounded_and_refused(tmp_path, payload):
    manifest_path = tmp_path / "bad.json"
    manifest_path.write_bytes(payload)
    report = inspect(manifest_path)
    assert not report.verified
    assert "invalid_manifest" in report.issues
    assert len(json.dumps(report.to_dict())) < 3000


def test_manifest_file_size_is_bounded_before_parsing(tmp_path):
    manifest_path = tmp_path / "huge.json"
    with manifest_path.open("wb") as handle:
        handle.truncate(2 * 1024 * 1024)
    report = inspect(manifest_path)
    assert not report.verified
    assert "unsafe_file" in report.issues


def test_rehashed_non_media_bytes_are_rejected(local_bundle):
    cover = media(local_bundle, "-cover.png")
    cover.write_bytes(b"This is not a PNG.")
    rewrite(
        local_bundle,
        lambda d: d["run"]["steps"][1]["assets"][0].update(
            sha256=hashlib.sha256(cover.read_bytes()).hexdigest(),
            size_bytes=cover.stat().st_size,
        ),
        rehash=True,
    )
    report = inspect(local_bundle.manifest_path)
    assert not report.verified
    assert "invalid_media" in report.assets[1].issues


@pytest.mark.parametrize(
    ("index", "field", "value"),
    [
        (0, "model", "unrelated-speech-model"),
        (1, "model", "unrelated-image-model"),
    ],
)
def test_rehashed_provider_model_inconsistency_is_rejected(
    local_bundle, index, field, value
):
    rewrite(
        local_bundle,
        lambda d: d["run"]["steps"][index].update({field: value}),
        rehash=True,
    )
    report = inspect(local_bundle.manifest_path)
    assert report.manifest_verified
    assert not report.verified
    assert "bundle_contract_mismatch" in report.issues
