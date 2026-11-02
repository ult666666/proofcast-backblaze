# Verify, sign and log a bundle

A ProofCast bundle is three files: the narration WAV, the cover PNG, and a Genblaze manifest that
records the providers, models, prompt and parameters, plus the SHA-256 and size of each file.
You can run three checks on a bundle:

- [verify](#verify-a-saved-bundle) that the files still match the manifest;
- [sign](#sign-a-bundle) the manifest with Ed25519, to show which key approved it;
- [log](#add-a-bundle-to-the-transparency-log) the manifest's hash in an append-only Merkle log,
  so that a later change to the history can be detected.

[What each check proves](#what-each-check-proves) and the [limits](#limits) are at the end. Run
every command from the repository root.

## Verify a saved bundle

`--verify` rereads the saved manifest and media. It checks the canonical hash, the completed
two-step ProofCast contract, each file's SHA-256 and byte count, the PNG's dimensions and decoded
pixels (single frame), and the PCM WAV metadata. Generation runs the same checks before it
reports `verified: true`. Genblaze's own manifest check does not reread media bytes.

```bash
.venv/bin/python -m proofcast.cli --verify output/YOUR-RUN-ID-manifest.json
# If the manifest and media are stored separately:
.venv/bin/python -m proofcast.cli --verify saved-manifest.json --asset-dir output
```

Exit 0 means the manifest and both local files passed, 1 means verification failed, and 2 means
invalid CLI arguments. The JSON report has separate `manifest_verified` and `assets_verified`
results and names each issue, such as `digest_mismatch`, `missing_file`, `size_mismatch` or
`media_metadata_mismatch`. Reports contain no prompt or recorded URL.

Verification never generates media, loads B2 settings or fetches a URL. It reads only the two
step-ID filenames in the manifest's directory (or `--asset-dir`), so a complete bundle can be
moved as a unit without following the original absolute file URLs. Linked or non-regular files,
manifests over 1 MiB and media files over 32 MiB are refused. The verifier accepts the schema 1.5
manifests that this pinned Genblaze version writes.

`remote_assets_checked` is always `false`. Even when a manifest records B2 HTTPS URLs,
verification checks the retained local files and says nothing about an upload or the bytes
served remotely.

To see a clean verification and a rejected tampered copy, without changing the original files:

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

## Sign a bundle

The manifest's hashes show that the files have not changed since the manifest was written, but
anyone who can edit the files can also write a matching manifest. An Ed25519 signature adds
origin: only the holder of the private key can produce it.

Create a key pair once, outside the repository. The private key file is created with mode 0600
and is never overwritten, and `.gitignore` also excludes `*.pem` and `keys/`. A missing
directory, such as `~/.config/proofcast/` on a first run, is created with mode 0700.

```bash
.venv/bin/python -m proofcast.provenance keygen \
  --private-key ~/.config/proofcast/signing-key.pem \
  --public-key ~/.config/proofcast/signing-key.pub.pem
```

Sign a generated bundle, then verify it against the public key, or against `--fingerprint`, the
SHA-256 of the raw public key. Signing refuses a bundle that does not verify. Verification checks
the signature and then the full bundle, so any change to the manifest or to either media file
fails.

```bash
.venv/bin/python -m proofcast.provenance sign output/YOUR-RUN-ID-manifest.json \
  --private-key ~/.config/proofcast/signing-key.pem
.venv/bin/python -m proofcast.provenance verify output/YOUR-RUN-ID-manifest.json \
  --public-key ~/.config/proofcast/signing-key.pub.pem
```

The signature file `YOUR-RUN-ID-manifest.sig.json` holds the algorithm, the key fingerprint, the
public key, the manifest's SHA-256, and the signature over `"ProofCast manifest signature v1\0"`
followed by the manifest bytes. The embedded key is used only after it matches the key or
fingerprint you trust.

## Add a bundle to the transparency log

A transparency log adds history. Once a manifest's hash is in the log and a signed tree head
covers it, the log cannot later drop or change that entry without the change being detectable.

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

## How the log works

- Leaf `i` is `SHA-256(0x00 || SHA-256(manifest_i))` and an interior node is
  `SHA-256(0x01 || left || right)`, as in [RFC 6962 §2.1](https://www.rfc-editor.org/rfc/rfc6962#section-2.1)
  and [RFC 9162 §2.1](https://www.rfc-editor.org/rfc/rfc9162#section-2.1). The different prefixes
  stop a leaf from being passed off as an interior node.
- Proofs follow the RFC 9162 algorithms. An inclusion proof is the sibling hashes from a leaf to
  the root, and a consistency proof shows that a tree of size `m` is the first `m` leaves of a
  tree of size `n`. Both are verified without the rest of the log.
- A tree head signs the bytes of RFC 6962's `TreeHeadSignature` (version, type, millisecond
  timestamp, tree size and root) with Ed25519. Proof hashes alone do not pin the tree size; the
  signed head does, and `log-verify` rejects a proof whose size differs from the head's.
- The log is one file, `manifest-digests.txt`, with one hex digest per line. Appends take a file
  lock, and each entry appears once.

The Merkle code is checked against the 196 published inclusion and consistency probes from
[transparency-dev/merkle](https://github.com/transparency-dev/merkle), vendored with their
license in [`tests/vectors/`](../tests/vectors/transparency-dev-merkle/). It is also checked
against the reference root hashes for trees of 0 to 8 leaves and against an independent
implementation of the RFC definitions. Every inclusion and consistency proof for trees of up to
64 leaves is generated and verified. For trees of up to 40 leaves, flipping a bit in a leaf, root
or proof hash, changing the leaf index, or truncating, extending or reversing a proof makes
verification fail. One published probe is rejected on purpose: it passes 12-byte placeholder
roots, and ProofCast accepts only 32-byte SHA-256 values. Ed25519 signing is checked against
reference test vectors.

## Try every tamper case

[`examples/tamper_demo.py`](../examples/tamper_demo.py) works on copies of a bundle, so the
originals do not change:

```bash
.venv/bin/python examples/tamper_demo.py output/YOUR-RUN-ID-manifest.json
```

It signs and logs the bundle and verifies inclusion and consistency. Then it checks that each of
these changes is caught:

| Change | Caught as |
| --- | --- |
| One byte appended to the cover image | `digest_mismatch` |
| One byte added to the manifest | `bad_signature` |
| The signature checked against a different trusted key | `untrusted_key` |
| One bit flipped in the inclusion proof | `inclusion_proof_failed` |
| The root hash replaced in a signed tree head | `bad_signature` |
| An earlier log entry rewritten, then a new head signed | `consistency_proof_failed` |
| An auditor recomputes the root of that rewritten log | `log_differs_from_tree_head` |

CI runs the same command on a bundle generated with eSpeak NG.

## What each check proves

- **Verification** shows local consistency: the files match the hashes and sizes in the
  manifest. It does not show authorship, or that the stated prompt produced the media.
- **A signature** shows that the holder of the trusted private key signed these manifest bytes.
  It does not show who holds the key, when the media was made (the manifest and tree-head times
  are the signer's own claims), that the recorded prompt produced the media, or anything about
  copies served from B2.
- **The log** shows that every head you hold describes one append-only history. It does not stop
  an operator from showing different histories to different people. Detecting that needs
  independent witnesses that compare signed heads, which this local log does not have.

## Limits

- The private key is stored unencrypted, protected only by file permissions.
- There is no key rotation, revocation or timestamping authority. If a signing key leaks, stop
  using it and tell verifiers to distrust its fingerprint.
- The log is a single local file with no replication.
- Each proof rereads and hashes the whole log, which is O(n). One inclusion proof over 100,000
  leaf hashes took 0.05 to 0.07 seconds in three runs (Python 3.13.17, a shared 4-vCPU Linux
  container), measured with:

```bash
python -c "import hashlib, time; from proofcast import merkle; h = [merkle.leaf_hash(hashlib.sha256(str(i).encode()).digest()) for i in range(100_000)]; t = time.perf_counter(); merkle.inclusion_proof(h, 50_000); print(f'{time.perf_counter() - t:.2f} s')"
```
