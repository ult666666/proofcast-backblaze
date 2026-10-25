# ProofCast

ProofCast turns a short lesson or safety briefing into two generated media assets:

- a local text-to-speech WAV narration;
- a high-contrast 1280×720 visual cover.

Genblaze orchestrates both steps, records the provider/model/prompt/parameters, hashes every asset, and creates a verifiable canonical manifest. When deliberately enabled, a content-addressable Genblaze sink stores the media and manifest in Backblaze B2. The default mode is local-only and makes no cloud writes.

This is a submission scaffold for the official [Backblaze Generative Media Hackathon](https://backblaze-generative-media.devpost.com/). It is not yet submitted or deployed.

## Why it is useful

Small education, nonprofit, security-awareness, and internal-training teams often need an audio version and a visual card for the same short lesson. They also need to know which model and prompt produced each asset. ProofCast makes the pair in one click and keeps the provenance record attached to the workflow rather than in a separate spreadsheet.

## Architecture

1. `LocalSpeechProvider` uses Apple Speech on macOS or eSpeak NG on Linux to generate WAV narration with no API key or paid inference.
2. `AccessibleCoverProvider` generates a deterministic, readable PNG cover from the same prompt.
3. A two-step Genblaze `Pipeline` produces a SHA-256-verifiable manifest.
4. In local mode, media and the canonical manifest remain in `output/`.
5. With `B2_ENABLED=1`, `ObjectStorageSink` and `S3StorageBackend.for_backblaze(...)` upload media and provenance to a public B2 demo bucket using content-addressable keys.

The app caps scripts at 1,200 characters, disables provider retries, allows only one generation per click, and never enables B2 implicitly. Those controls keep both compute and storage use small.

## Providers and models

| Step | Provider | Model/engine | Cost per run |
|---|---|---|---:|
| Narration on macOS | `proofcast-local-speech` | Apple Speech voice selected by the user | $0 |
| Narration on Linux/deployment | `proofcast-local-speech` | `espeak-ng-en-us` | $0 |
| Cover generation | `proofcast-accessible-cover` | `proofcast-accessible-cover-v1` | $0 |

The public demo should use eSpeak NG so it runs on a normal Linux host without a generation-provider account. The application can later swap in any Genblaze speech or image connector without changing the B2/provenance layer.

## Local quick start

Requirements: Python 3.11+, plus either the built-in macOS `say` command or `espeak-ng` on Linux.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest
.venv/bin/python -m proofcast.cli \
  --title "Three ways to spot a phishing message" \
  --script "Pause before opening unexpected links. Check the sender address. Verify urgent requests through a second channel."
```

Start the app:

```bash
.venv/bin/streamlit run app.py
```

No account, card, provider credit, or network call is needed for local generation.

## Verify a saved local bundle

`--verify` independently rereads the saved manifest and media. It checks the canonical hash,
the completed two-step ProofCast contract, each file's SHA-256 and byte count, and actual
single-frame PNG dimensions and decoded pixels / PCM WAV metadata. Generation now runs these same checks before reporting
`verified: true`; Genblaze's manifest-only check does not reread media bytes.

```bash
.venv/bin/python -m proofcast.cli --verify output/YOUR-RUN-ID-manifest.json
# If the manifest and media are stored separately:
.venv/bin/python -m proofcast.cli --verify saved-manifest.json --asset-dir output
```

Exit **0** means the manifest and both local files passed; **1** means verification failed;
**2** means invalid CLI arguments. JSON includes separate `manifest_verified` and
`assets_verified` results and explicit issues such as `digest_mismatch`, `missing_file`,
`size_mismatch` or `media_metadata_mismatch`. Reports contain no prompt or recorded URL.

Inspection never generates media, loads B2 settings or fetches a URL. It reads only the two
step-ID filenames in the manifest directory (or `--asset-dir`), so a complete bundle can be
moved together without following the original absolute file URLs. Linked/nonregular files,
manifests over 1 MiB and media files over 32 MiB are refused. The verifier accepts the schema
1.5 manifests emitted by this pinned Genblaze version.

Try a complete local generation → clean verification → tamper detection, leaving the original
files intact:

```bash
mkdir -p output
.venv/bin/python -m proofcast.cli \
  --title "Check before clicking" \
  --script "Verify unexpected requests through a second channel." > output/latest-run.json

.venv/bin/python - <<'PYDEMO'
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

run = json.loads(Path("output/latest-run.json").read_text())
manifest = Path(run["manifest_path"])
subprocess.run([sys.executable, "-m", "proofcast.cli", "--verify", str(manifest)], check=True)
with tempfile.TemporaryDirectory(prefix="proofcast-tamper-") as temporary:
    folder = Path(temporary).resolve()
    shutil.copyfile(manifest, folder / manifest.name)
    for asset in run["verification"]["assets"]:
        name = asset["filename"]
        shutil.copyfile(manifest.parent / name, folder / name)
    cover = next(folder.glob("*-cover.png"))
    cover.write_bytes(cover.read_bytes() + b"changed after generation")
    result = subprocess.run(
        [sys.executable, "-m", "proofcast.cli", "--verify", str(folder / manifest.name)],
        capture_output=True, text=True, check=False,
    )
    report = json.loads(result.stdout)
    assert result.returncode == 1 and report["manifest_verified"] is True
    assert "digest_mismatch" in report["assets"][1]["issues"]
    print("Tampered copy rejected; original media preserved.")
PYDEMO
```

A passing report establishes **local consistency**, not authorship or proof that the stated
prompt produced the media. Hashes are not signatures. `remote_assets_checked` is always
`false`: even when a manifest records B2 HTTPS URLs, verification checks the retained local
files and makes no claim about an upload or the bytes served remotely.

## Backblaze B2 mode

Do not put real credentials in the repository. Copy `.env.example` into a secure local secret store or configure the same values in the deployment platform.

```bash
export B2_ENABLED=1
export B2_BUCKET="your-public-demo-bucket"
export B2_REGION="us-west-004"
export B2_KEY_ID="your-scoped-key-id"
export B2_APP_KEY="your-scoped-application-key"
export B2_PUBLIC_URL_BASE="https://f004.backblazeb2.com/file/your-public-demo-bucket"
export B2_PREFIX="proofcast"

# Cloud writes still require a second, explicit CLI switch.
.venv/bin/python -m proofcast.cli \
  --allow-b2 \
  --title "Three ways to spot a phishing message" \
  --script "Pause before opening unexpected links. Check the sender address. Verify urgent requests through a second channel."
```

The Streamlit app uses B2 when `B2_ENABLED=1`; deployment secrets must never be exposed to the browser. The demo bucket should contain only original, non-sensitive sample content because the provenance manifest includes the generation prompt.

## B2 design choices

- `KeyStrategy.CONTENT_ADDRESSABLE` deduplicates identical media.
- `auto_lifecycle=False` avoids changing bucket-wide policy behind the user's back.
- `preflight=True` fails before generation if the key, region, or bucket is wrong.
- A public URL base gives judges credential-free asset access.
- A bucket-scoped key limits the blast radius.
- Cloud mode requires all five B2 values and an explicit `B2_ENABLED=1` gate.

Backblaze documents that the first 10 GB of B2 storage is free. Keep the demo far below that amount, check the B2 usage screen before and after testing, and stop if signup or deployment asks for a payment method. The code itself cannot guarantee that an external service will never change its signup or billing policy.

## Verification performed

As of July 14, 2026:

- seven automated tests pass on macOS and Linux without contacting a provider;
- the full local pipeline generated a WAV, PNG, and canonical manifest;
- `manifest.verify()` returned `True`;
- both media steps recorded `cost_usd = 0.0` and `network_calls = 0`;
- no Backblaze account was created;
- no B2 upload, deployment, Devpost submission, or paid API call was made.

The B2 path is implemented but intentionally untested against a live account. Follow [ACCOUNT_BOUND_STEPS.md](ACCOUNT_BOUND_STEPS.md) only after the account owner approves the current Backblaze signup/billing screen.

## Submission materials

- [Official rules and entry strategy](RULES_AND_ENTRY_PLAN.md)
- [Account-bound remaining steps](ACCOUNT_BOUND_STEPS.md)
- [Devpost-ready copy and demo script](SUBMISSION.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

## Security and privacy

- Never enter sensitive, regulated, or private text. Genblaze provenance records prompts.
- Use a dedicated public demo bucket, not an existing production bucket.
- Use a bucket-scoped application key with only the capabilities needed for upload/read/list.
- Rotate the key immediately if it appears in logs or screenshots.
- Do not commit `.env`, deployment secrets, generated assets, or user text.

## License

Project code is MIT licensed. Third-party dependencies remain under their own licenses.
