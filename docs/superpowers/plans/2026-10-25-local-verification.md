# Local Bundle Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Independently verify the two local ProofCast media assets against a saved manifest.

**Architecture:** A focused `proofcast.verification` module parses bounded JSON and reports contract, manifest-hash and per-file checks. Generation and the existing CLI/UI consume that same report; inspection never loads B2 settings or generates media.

**Tech Stack:** Python 3.11+, Genblaze 0.3.4 models, standard-library SHA-256/WAV/JSON, Pillow PNG validation, pytest.

**Spec:** `docs/superpowers/specs/2026-10-25-local-verification-design.md`

## Global Constraints

- B2 remains opt-in, with no change to its upload gate or credentials.
- Preserve existing CLI generation flags and expose inspection through `--verify MANIFEST [--asset-dir DIRECTORY]`.
- A successful report means the supplied manifest is internally consistent and the local bytes match it.
- Inspection never creates storage, calls a speech provider, reads cloud configuration or fetches URLs.

## Review Focus

- Rehashed metadata drift must fail independently of the canonical hash.
- Missing files and altered same-size bytes must produce distinct failures.
- Relocated bundles must be readable without following arbitrary recorded file paths.
- Remote transport URLs must never trigger network access or imply upload verification.
- Malformed JSON, linked files and oversized files must fail with bounded output.

### Task 1: Saved-bundle verifier

**Files:** Create `proofcast/verification.py`, `tests/test_verification.py`.

**Interfaces:** `verify_bundle(manifest_path: Path, *, asset_dir: Path | None = None) -> BundleVerification`; report exposes `verified`, `manifest_verified`, `assets_verified`, per-file results, issue codes and `to_dict()`.

- [ ] Write real-file tests for valid bundle, byte tampering, missing files, changed manifest hash, rehashed PNG/WAV metadata drift, wrong step roles, invalid JSON, outside/linked paths and HTTPS without fetching.
- [ ] Run `.venv/bin/python -m pytest tests/test_verification.py`; expect failures because verification is missing.
- [ ] Implement bounded parsing, the two-step contract, streamed file digests and actual media checks.
- [ ] Run targeted tests and the complete suite; expect all pass.
- [ ] Commit the verifier and tests.

### Task 2: Generation, CLI/UI and runnable workflow

**Files:** Modify `proofcast/pipeline.py`, `proofcast/cli.py`, `app.py`, `README.md`, `VERIFY.md`; create `tests/test_cli.py`; extend `tests/test_pipeline.py`.

**Interfaces:** Consume Task 1 report. `GenerationResult` includes the report; CLI `--verify` emits its JSON and returns 0 only when verified, 1 on failed verification, 2 on invalid arguments. CLI inspection works even with invalid B2 environment settings.

- [ ] Write failing subprocess CLI tests for clean/tampered inspection, argument isolation and invalid B2 environment; add pipeline report assertions.
- [ ] Run targeted tests; expect missing interface/command failures.
- [ ] Integrate the report; make UI success conditional and describe local-byte verification, with remote verification false.
- [ ] Document generate → inspect → tamper → detect commands with explicit exit behavior.
- [ ] Run the complete suite, real OS-speech generation, clean verification and a tampered-copy rejection; inspect the diff and public output for secrets.
- [ ] Commit, refresh remote main, push the feature branch and open/attach a PR without merging.
