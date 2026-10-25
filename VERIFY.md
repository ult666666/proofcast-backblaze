# Verification runbook

## Local tests

```bash
.venv/bin/python -m pytest
```

The suite exercises local generation, saved-bundle integrity, real-file tampering, media metadata, malformed input and CLI isolation without contacting a provider.

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
copy-and-tamper scenario in [README.md](README.md#verify-a-saved-local-bundle) preserves the originals.

Checks cover canonical integrity, the ProofCast two-step contract, file SHA-256/size and real
PNG/WAV metadata, including full decoding of the supported single-frame PNG cover. Passing is internal consistency, not authenticated provenance or remote
upload verification. Files must be unlinked regular files, at most 1 MiB for the manifest and
32 MiB for each asset. Moved files are selected only in the manifest directory or an explicit
`--asset-dir`; recorded absolute locations and HTTPS URLs are never followed.

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
  '(B2_APP_KEY=.+|B2_KEY_ID=.+|applicationKey|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY)' .
```

Review every match manually. `.env.example` must contain placeholders only.

## Live B2 smoke test

Run only after following `ACCOUNT_BOUND_STEPS.md` and confirming no payment method is required.

```bash
.venv/bin/python -m proofcast.cli \
  --allow-b2 \
  --title "Three ways to spot a phishing message" \
  --script "Pause before opening unexpected links. Check the sender address. Verify urgent requests through a second channel."
```

Then open every returned URL in a private browser and inspect B2 usage/billing. Turn `B2_ENABLED=0` immediately after the one-run test.
