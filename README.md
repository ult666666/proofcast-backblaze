# ProofCast

[![Verify](https://github.com/ult666666/proofcast-backblaze/actions/workflows/verify.yml/badge.svg)](https://github.com/ult666666/proofcast-backblaze/actions/workflows/verify.yml)

ProofCast turns a short lesson or safety briefing into two generated media assets:

- a local text-to-speech WAV narration;
- a high-contrast 1280×720 visual cover.

Genblaze orchestrates both steps, records the provider/model/prompt/parameters, hashes every asset, and creates a verifiable canonical manifest. Version 0.2.0 adds origin: an Ed25519 signature over the manifest, and an append-only transparency log of manifest hashes with signed tree heads, inclusion proofs and consistency proofs. When deliberately enabled, a content-addressable Genblaze sink stores the media and manifest in Backblaze B2. The default mode is local-only and makes no cloud writes.

ProofCast was built for the [Backblaze Generative Media Hackathon](https://backblaze-generative-media.devpost.com/). Local generation and verification are tested in CI. The optional Backblaze B2 upload is implemented but has not been run against a real bucket.

## Why it is useful

Small education, nonprofit, security-awareness, and internal-training teams often need an audio version and a visual card for the same short lesson. They also need to know which model and prompt produced each asset. ProofCast makes the pair in one click and keeps the provenance record attached to the workflow rather than in a separate spreadsheet.

## Architecture

1. `LocalSpeechProvider` uses Apple Speech on macOS or eSpeak NG on Linux to generate WAV narration with no API key or paid inference.
2. `AccessibleCoverProvider` generates a deterministic, readable PNG cover from the same prompt.
3. A two-step Genblaze `Pipeline` produces a SHA-256-verifiable manifest.
4. In local mode, media and the canonical manifest remain in `output/`.
5. With `B2_ENABLED=1`, `ObjectStorageSink` and `S3StorageBackend.for_backblaze(...)` upload media and provenance to a public B2 demo bucket using content-addressable keys.
6. `proofcast.signing` signs the saved manifest bytes with Ed25519; `proofcast.provenance` is the CLI that signs, verifies and logs.
7. `proofcast.translog` keeps an append-only log of manifest SHA-256 digests. `proofcast.merkle` hashes it as an RFC 6962 / RFC 9162 Merkle tree and builds and checks the proofs.

The app caps scripts at 1,200 characters, disables provider retries, allows only one generation per click, and never enables B2 implicitly. Those controls keep both compute and storage use small.

## Providers and models

| Step | Provider | Model/engine | Cost per run |
|---|---|---|---:|
| Narration on macOS | `proofcast-local-speech` | Apple Speech voice selected by the user | $0 |
| Narration on Linux/deployment | `proofcast-local-speech` | `espeak-ng-en-us` | $0 |
| Cover generation | `proofcast-accessible-cover` | `proofcast-accessible-cover-v1` | $0 |

On Linux, ProofCast uses eSpeak NG, so it needs no generation-provider account. Any Genblaze speech or image connector could replace these providers without changing the B2 and provenance layer.

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

No account, card, provider credit, or network call is needed for local generation. If the input is invalid or no speech engine is installed, the CLI prints a one-line error and exits 2.

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
prompt produced the media. Hashes are not signatures; to show which key approved a bundle,
[sign it](#sign-and-log-a-bundle). `remote_assets_checked` is always
`false`: even when a manifest records B2 HTTPS URLs, verification checks the retained local
files and makes no claim about an upload or the bytes served remotely.

## Sign and log a bundle

The manifest's hashes show that the files have not changed since the manifest was written, but
anyone who can edit the files can also write a matching manifest. An Ed25519 signature adds
origin: only the holder of the private key can produce it. A transparency log adds history: once
a manifest's hash is in the log and a signed tree head covers it, the log cannot later drop or
change that entry without the change being detectable.

Create a key pair once, outside the repository. The private key file is created with mode 0600
and is never overwritten; `.gitignore` also excludes `*.pem` and `keys/`.

```bash
.venv/bin/python -m proofcast.provenance keygen \
  --private-key ~/.config/proofcast/signing-key.pem \
  --public-key ~/.config/proofcast/signing-key.pub.pem
```

Sign a generated bundle, then verify it against the public key (or `--fingerprint`, the SHA-256
of the raw public key). Signing refuses a bundle that does not verify. Verification checks the
signature and then the full bundle, so any change to the manifest or to either media file fails:

```bash
.venv/bin/python -m proofcast.provenance sign output/YOUR-RUN-ID-manifest.json \
  --private-key ~/.config/proofcast/signing-key.pem
.venv/bin/python -m proofcast.provenance verify output/YOUR-RUN-ID-manifest.json \
  --public-key ~/.config/proofcast/signing-key.pub.pem
```

The signature file `YOUR-RUN-ID-manifest.sig.json` holds the algorithm, the key fingerprint, the
public key, the manifest's SHA-256 and the signature over `"ProofCast manifest signature v1\0"`
plus the exact manifest bytes. The embedded key is used only after it matches the key or
fingerprint you trust.

Add the manifest to a log, sign a tree head, and prove inclusion:

```bash
.venv/bin/python -m proofcast.provenance log-append transparency-log output/YOUR-RUN-ID-manifest.json
.venv/bin/python -m proofcast.provenance log-head transparency-log \
  --private-key ~/.config/proofcast/signing-key.pem --out head.json
.venv/bin/python -m proofcast.provenance log-prove transparency-log output/YOUR-RUN-ID-manifest.json > inclusion.json
.venv/bin/python -m proofcast.provenance log-verify --tree-head head.json \
  --public-key ~/.config/proofcast/signing-key.pub.pem \
  --inclusion inclusion.json --manifest output/YOUR-RUN-ID-manifest.json
```

After more appends, sign a new head and check that it extends the old one:
`log-consistency transparency-log --first OLD_SIZE > consistency.json`, then
`log-verify --tree-head new-head.json --old-tree-head head.json --consistency consistency.json`
with the same `--public-key`. Add `--log transparency-log` to `log-verify` to recompute the root
from the entries yourself.

How it works:

- Leaf `i` is `SHA-256(0x00 || SHA-256(manifest_i))` and an interior node is
  `SHA-256(0x01 || left || right)`, as in [RFC 6962 §2.1](https://www.rfc-editor.org/rfc/rfc6962#section-2.1)
  and [RFC 9162 §2.1](https://www.rfc-editor.org/rfc/rfc9162#section-2.1). The different prefixes
  stop a leaf from being passed off as an interior node.
- Proofs follow the RFC 9162 algorithms: an inclusion proof is the sibling hashes from a leaf to
  the root, and a consistency proof shows that a tree of size `m` is the first `m` leaves of a
  tree of size `n`. Both are verified without the rest of the log.
- A tree head signs the bytes of RFC 6962's `TreeHeadSignature` (version, type, millisecond
  timestamp, tree size and root) with Ed25519. Proof hashes alone do not pin the tree size;
  the signed head does, and `log-verify` rejects a proof whose size differs from the head's.
- The log is one file, `manifest-digests.txt`, with one hex digest per line; appends take a file
  lock and each entry appears once.

Try every tamper case on copies of a bundle (the originals are not changed):

```bash
.venv/bin/python examples/tamper_demo.py output/YOUR-RUN-ID-manifest.json
```

It signs and logs the bundle, verifies inclusion and consistency, then checks that a changed
media byte (`digest_mismatch`), a changed manifest byte (`bad_signature`), a different trusted
key (`untrusted_key`), a flipped proof bit, an edited tree head, and a rewritten log entry
followed by a newly signed head (`consistency_proof_failed`) are all caught.

What a signature does and does not prove:

- **Proves:** the holder of the trusted private key signed these exact manifest bytes, and the
  media files match the hashes and sizes in that manifest.
- **Does not prove:** who holds the key, when the media was made (the manifest and tree-head
  times are the signer's own claims), that the recorded prompt produced the media, or anything
  about copies served from B2.
- **The log proves** that every head you hold describes one append-only history. It does not
  stop an operator from showing different histories to different people: detecting that needs
  independent witnesses that compare signed heads, which this local log does not have.

Limits: the private key is stored unencrypted (protected only by file permissions); there is no
key rotation, revocation or timestamping authority; the log is a single local file with no
replication; and each proof rereads the whole log and hashes it, which is O(n). Computing one
inclusion proof over 100,000 leaf hashes took 0.11 to 0.18 seconds in three runs on Python
3.12.3 in a shared 4-vCPU Linux container:

```bash
python -c "import hashlib, time; from proofcast import merkle; h = [merkle.leaf_hash(hashlib.sha256(str(i).encode()).digest()) for i in range(100_000)]; t = time.perf_counter(); merkle.inclusion_proof(h, 50_000); print(f'{time.perf_counter() - t:.2f} s')"
```

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
- A public URL base lets anyone open the demo assets without credentials.
- A bucket-scoped key limits the blast radius.
- Cloud mode requires all five B2 values and an explicit `B2_ENABLED=1` gate.

Backblaze documents that the first 10 GB of B2 storage is free. Keep the demo far below that amount, check the B2 usage screen before and after testing, and stop if signup or deployment asks for a payment method.

## Verification

CI runs the test suite and compiles the source on pull requests and pushes to `main` ([workflow](.github/workflows/verify.yml)). The suite exercises local generation, saved-bundle integrity, real-file tampering, media metadata, malformed input and CLI isolation without contacting a provider or Backblaze. Tests replace the operating system's speech call with a small WAV writer. CI then installs eSpeak NG, generates a real bundle and runs the tamper demo on it.

The Merkle code is checked against the 196 published inclusion and consistency probes from [transparency-dev/merkle](https://github.com/transparency-dev/merkle) (vendored with their license in `tests/vectors/`), the reference root hashes for trees of 0 to 8 leaves, and an independent implementation of the RFC definitions. Every inclusion and consistency proof for trees of up to 64 leaves is generated and verified. For trees of up to 40 leaves, flipping a bit in a leaf, root or proof hash, changing the leaf index, or truncating, extending or reversing a proof makes verification fail. One published probe is rejected on purpose: it passes 12-byte placeholder roots, and ProofCast accepts only 32-byte SHA-256 values. Ed25519 is checked against reference vectors. [VERIFY.md](VERIFY.md) lists the manual checks, including a one-run live B2 smoke test.

## Security and privacy

- Never enter sensitive, regulated, or private text. Genblaze provenance records prompts.
- Use a dedicated public demo bucket, not an existing production bucket.
- Use a bucket-scoped application key with only the capabilities needed for upload/read/list.
- Rotate the key immediately if it appears in logs or screenshots.
- Do not commit `.env`, deployment secrets, generated assets, user text, or signing keys. Keep the private signing key outside the repository with mode 0600; `.gitignore` and `.dockerignore` exclude `*.pem` and `keys/` as a backstop.
- If a signing key leaks, stop using it and tell verifiers to distrust its fingerprint; ProofCast has no revocation list.
- Docker builds skip `.env` files, virtual environments, caches and `output/` (see `.dockerignore`), so local keys and media stay out of the image.

## Project history

The rules summary, account checklist and submission draft written for the hackathon are kept in [`docs/history/`](docs/history/).

## License

Project code is MIT licensed. Third-party dependencies remain under their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
