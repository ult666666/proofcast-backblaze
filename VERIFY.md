# Verification runbook

## Local tests

```bash
.venv/bin/python -m pytest
```

The suite exercises local generation, saved-bundle integrity, real-file tampering, media metadata, malformed input and CLI isolation without contacting a provider. It also checks Ed25519 signatures and the Merkle log against published test vectors (see `tests/vectors/transparency-dev-merkle/README.md`) and runs the tamper demo on a generated bundle.

## Local no-account smoke test

```bash
env -u B2_ENABLED -u B2_KEY_ID -u B2_APP_KEY \
  .venv/bin/python -m proofcast.cli \
  --title "Three ways to spot a phishing message" \
  --script "Pause before opening unexpected links. Check the sender address. Verify urgent requests through a second channel."
```

Expected:

- `storage_mode` is `local-only`;
- `verified`, `verification.manifest_verified` and `verification.assets_verified` are `true`;
- `verification.remote_assets_checked` is `false`;
- one `audio/wav` and one `image/png` exist under `output/`;
- both assets report `network_calls: 0`;
- no B2 request is possible because `build_sink()` returned `None`.

## Independent saved-bundle verification

Use the generated manifest path from the smoke-test JSON:

```bash
.venv/bin/python -m proofcast.cli --verify output/YOUR-RUN-ID-manifest.json
```

Expected: exit 0 and separate passing manifest/local asset checks. This command never invokes
speech generation, reads cloud settings or fetches URLs. A copy with a changed media byte must
exit 1 with `digest_mismatch`; a missing file must exit 1 with `missing_file`. The runnable
copy-and-tamper scenario in [docs/PROVENANCE.md](docs/PROVENANCE.md#verify-a-saved-bundle) preserves the originals.

Checks cover canonical integrity, the ProofCast two-step contract, file SHA-256/size and real
PNG/WAV metadata, including full decoding of the supported single-frame PNG cover. Passing is internal consistency, not authenticated provenance or remote
upload verification. Files must be unlinked regular files, at most 1 MiB for the manifest and
32 MiB for each asset. Moved files are selected only in the manifest directory or an explicit
`--asset-dir`; recorded absolute locations and HTTPS URLs are never followed.

## Signed provenance and transparency log

With a bundle from the smoke test:

```bash
.venv/bin/python examples/tamper_demo.py output/YOUR-RUN-ID-manifest.json
```

Expected: exit 0, `bundle_signed_and_logged` and `inclusion_and_consistency_verified` are `true`,
and all seven `tamper_checks` report `"caught": true`. The demo works on copies in a temporary
directory, so `output/` is unchanged afterwards. CI runs the same command on a bundle generated
with eSpeak NG.

To check by hand, follow [Sign a bundle](docs/PROVENANCE.md#sign-a-bundle) and [Add a bundle to the transparency log](docs/PROVENANCE.md#add-a-bundle-to-the-transparency-log). Then confirm:

- the private key file has mode `-rw-------` (`ls -l`) and is outside the repository;
- `verify` exits 0 with `signature_verified` and `bundle.verified` both `true`;
- `verify` with another key's `--public-key` exits 1 with `untrusted_key`;
- appending one byte to a media copy makes `verify` exit 1 with `digest_mismatch`, while the
  signature itself still verifies;
- `log-verify` with `--inclusion` and with `--consistency` exits 0, and exits 1 after any proof
  hash is edited.

A passing signature shows which key signed the manifest, not who holds that key or when the media
was made.

## Streamlit health check

```bash
.venv/bin/streamlit run app.py --server.headless true
```

Open `http://localhost:8501/_stcore/health`; expected body: `ok`.

## Secret and generated-file scan

```bash
git status --short
rg -n --hidden \
  -g '!/.venv/**' -g '!/output/**' -g '!.git/**' \
  '(B2_APP_KEY=.+|B2_KEY_ID=.+|applicationKey|BEGIN (RSA |OPENSSH |EC |ENCRYPTED )?PRIVATE KEY)' .
```

Review every match manually. `.env.example` must contain placeholders only. Ed25519 signing keys
are PKCS #8 files that start with `BEGIN PRIVATE KEY`; none may appear in the repository.

## Live B2 smoke test

Run only after following the account and bucket setup in [docs/history/ACCOUNT_BOUND_STEPS.md](docs/history/ACCOUNT_BOUND_STEPS.md) and confirming no payment method is required.

```bash
.venv/bin/python -m proofcast.cli \
  --allow-b2 \
  --title "Three ways to spot a phishing message" \
  --script "Pause before opening unexpected links. Check the sender address. Verify urgent requests through a second channel."
```

Then open every returned URL in a private browser and inspect B2 usage/billing. Turn `B2_ENABLED=0` immediately after the one-run test.
