# Verification runbook

## Local tests

```bash
.venv/bin/python -m pytest
```

Expected: seven tests pass with no warning or failure.

## Local no-account smoke test

```bash
env -u B2_ENABLED -u B2_KEY_ID -u B2_APP_KEY \
  .venv/bin/python -m proofcast.cli \
  --title "Three ways to spot a phishing message" \
  --script "Pause before opening unexpected links. Check the sender address. Verify urgent requests through a second channel."
```

Expected:

- `storage_mode` is `local-only`;
- `verified` is `true`;
- one `audio/wav` and one `image/png` exist under `output/`;
- both assets report `network_calls: 0`;
- no B2 request is possible because `build_sink()` returned `None`.

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
