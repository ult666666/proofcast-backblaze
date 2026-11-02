# Store bundles in Backblaze B2

ProofCast can upload each bundle (the narration, the cover and the manifest) to a Backblaze B2
bucket. With `B2_ENABLED=1`, Genblaze's `ObjectStorageSink` and
`S3StorageBackend.for_backblaze(...)` upload them under content-addressable keys. Uploads are off
by default. The upload path is implemented but has not been run against a real bucket.

## Turn it on

Keep real credentials out of the repository. Copy `.env.example` into a secure local secret
store, or set the same values in your deployment platform.

```bash
export B2_ENABLED=1
export B2_BUCKET="your-public-demo-bucket"
export B2_REGION="us-west-004"
export B2_KEY_ID="your-scoped-key-id"
export B2_APP_KEY="your-scoped-application-key"
export B2_PUBLIC_URL_BASE="https://f004.backblazeb2.com/file/your-public-demo-bucket"
export B2_PREFIX="proofcast"

# Cloud writes also need a second, explicit CLI switch.
.venv/bin/python -m proofcast.cli \
  --allow-b2 \
  --title "Three ways to spot a phishing message" \
  --script "Pause before opening unexpected links. Check the sender address. Verify urgent requests through a second channel."
```

The Streamlit app uploads when `B2_ENABLED=1`. Never expose deployment secrets to the browser.
The bucket should hold only original, non-sensitive sample content, because the manifest includes
the generation prompt.

## Design choices

- `KeyStrategy.CONTENT_ADDRESSABLE` deduplicates identical media.
- `auto_lifecycle=False` leaves bucket-wide lifecycle policy unchanged.
- `preflight=True` fails before generation if the key, region or bucket is wrong.
- A public URL base lets anyone open the demo assets without credentials.
- A bucket-scoped key limits what a leaked key can reach.
- Cloud mode needs all five B2 values and an explicit `B2_ENABLED=1`.

## Cost

Backblaze documents that the first 10 GB of B2 storage is free. Keep the demo far below that,
check the B2 usage screen before and after testing, and stop if signup or deployment asks for a
payment method.

## Keys and secrets

- Use a dedicated public demo bucket, not an existing production bucket.
- Use a bucket-scoped application key with only the capabilities needed to upload, read and list.
- Rotate the key at once if it appears in logs or screenshots.
- Do not commit `.env` files, deployment secrets, generated assets or user text.

[VERIFY.md](../VERIFY.md#live-b2-smoke-test) describes a one-run live smoke test.
