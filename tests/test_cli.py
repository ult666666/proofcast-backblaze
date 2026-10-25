import json
import os
import subprocess
import sys


def run_cli(*args, **env):
    return subprocess.run(
        [sys.executable, "-m", "proofcast.cli", *map(str, args)],
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, **env},
    )


def test_inspection_cli_checks_saved_files_without_cloud_configuration(local_bundle):
    before = {
        file.name: file.read_bytes()
        for file in local_bundle.manifest_path.parent.iterdir()
    }
    result = run_cli(
        "--verify",
        local_bundle.manifest_path,
        B2_ENABLED="1",
        PROOFCAST_MAX_SCRIPT_CHARS="not-an-integer",
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["verified"] is True
    assert report["manifest_verified"] is True
    assert report["assets_verified"] is True
    assert report["remote_assets_checked"] is False
    after = {
        file.name: file.read_bytes()
        for file in local_bundle.manifest_path.parent.iterdir()
    }
    assert before == after


def test_inspection_cli_returns_nonzero_for_tampered_bytes(local_bundle):
    audio = next(local_bundle.manifest_path.parent.glob("*-narration.wav"))
    data = audio.read_bytes()
    audio.write_bytes(data[:-2] + b"\x01\x00")
    result = run_cli("--verify", local_bundle.manifest_path)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["verified"] is False
    assert report["manifest_verified"] is True
    assert "digest_mismatch" in report["assets"][0]["issues"]
    assert not result.stderr


def test_inspection_cli_reports_missing_manifest_without_traceback(tmp_path):
    result = run_cli("--verify", tmp_path / "missing.json")
    assert result.returncode == 1
    assert json.loads(result.stdout)["issues"] == ["missing_file"]
    assert not result.stderr


def test_verify_flags_cannot_implicitly_generate_or_enable_cloud(local_bundle):
    for flags in [
        ("--title", "Unwanted generation"),
        ("--allow-b2",),
        ("--engine", "say"),
    ]:
        result = run_cli("--verify", local_bundle.manifest_path, *flags)
        assert result.returncode == 2
        assert not result.stdout


def test_asset_directory_requires_verification_mode(tmp_path):
    result = run_cli(
        "--asset-dir", tmp_path, "--title", "A lesson", "--script", "Safe text."
    )
    assert result.returncode == 2
    assert not result.stdout


def test_generation_requires_both_original_text_inputs():
    for flags in [(), ("--title", "Only title"), ("--script", "Only script")]:
        result = run_cli(*flags)
        assert result.returncode == 2
        assert not result.stdout
