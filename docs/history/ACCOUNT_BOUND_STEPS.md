# Account-bound steps still required

No account was created, no terms were accepted, no deployment was made, no object was uploaded, and no money was spent while building this scaffold. These steps require the account owner's active session or explicit review of the live legal/billing screen.

## 1. Join the hackathon

1. Open [the official Devpost challenge](https://backblaze-generative-media.devpost.com/).
2. Sign in to the correct Devpost account.
3. Click **Join hackathon**.
4. Read the live rules and confirm eligibility/conflict statements.
5. Complete any human CAPTCHA personally; do not bypass it.

Stop if the live rules differ materially from `RULES_AND_ENTRY_PLAN.md`.

## 2. Create the B2 account without authorizing spend

1. Open Backblaze's official **Start Free** flow from the challenge or [B2 integration guide](https://www.backblaze.com/docs/en/cloud-storage-get-started-with-a-backblaze-integration).
2. Register and verify the email address.
3. Enable only **B2 Cloud Storage** and review its current terms.
4. If any screen requires a card, deposit, paid plan, billing authorization, or minimum commitment, **stop**. Do not enter payment information.
5. In the usage/billing page, confirm the first-10-GB-free allowance is active and set any available storage/transaction/egress caps or alerts to the lowest safe value.

The official challenge says no purchase is necessary and advertises 10 GB of free B2 storage, but external signup requirements can change. The safe rule is: no card and no charge authorization.

## 3. Create a dedicated public demo bucket

1. Name it uniquely, for example `proofcast-charles-dai-demo` plus a short random suffix.
2. Set bucket visibility to **public** so judges can retrieve the generated demo assets without credentials.
3. Record the exact S3 endpoint and region, such as `us-west-004`.
4. Keep this bucket free of private or user-provided data. The Genblaze manifest includes the prompt.
5. Do not enable Object Lock for the first smoke test; it can prevent cleanup.
6. Do not add bucket-wide lifecycle rules until the simple upload/retrieval path passes.

## 4. Create a least-privileged application key

In **B2 Cloud Storage → Application Keys**:

1. Create a new key restricted to the ProofCast demo bucket.
2. Select **Read and Write** for the dedicated bucket.
3. Enable **Allow List All Bucket Names** if the console offers it; Backblaze documents this as needed by S3-compatible list-bucket operations for bucket-restricted keys.
4. Do not grant account-management, key-management, or other-bucket access.
5. Copy the application key immediately; Backblaze shows the secret only once.
6. Store the key only in a local secret store or deployment secrets. Never paste it into source, Devpost, screenshots, logs, or chat.

## 5. Configure a one-run live smoke test

Set these secrets locally, replacing placeholders:

```bash
export B2_ENABLED=1
export B2_BUCKET="proofcast-charles-dai-demo-..."
export B2_REGION="..."
export B2_KEY_ID="..."
export B2_APP_KEY="..."
export B2_PUBLIC_URL_BASE="https://f...backblazeb2.com/file/proofcast-charles-dai-demo-..."
export B2_PREFIX="proofcast"
```

Then run exactly one short original script:

```bash
.venv/bin/python -m proofcast.cli \
  --allow-b2 \
  --title "Three ways to spot a phishing message" \
  --script "Pause before opening unexpected links. Check the sender address. Verify urgent requests through a second channel."
```

Verify all of these before proceeding:

- command exits successfully;
- result says `storage_mode: Backblaze B2`;
- result says `verified: true`;
- audio and cover URLs open in a private browser window with no login;
- B2 contains content-addressed media and a run manifest under the `proofcast` prefix;
- B2 usage remains far below 50 MB;
- there is no charge or pending bill.

If any check fails, turn `B2_ENABLED=0` before debugging so repeated local runs cannot upload.

## 6. Publish the repository

1. Run the secret scan in `VERIFY.md`.
2. Create a new GitHub repository only after reviewing every tracked file.
3. Keep it public for the simplest judging path, or grant the required `b2genblaze` GitHub account access if private.
4. Confirm `.env`, `output/`, and `.venv/` are not tracked.
5. Use the repository URL in Devpost.

## 7. Deploy without a payment method

Preferred simple route: Streamlit Community Cloud or another genuinely free host that can install `packages.txt` (`espeak-ng`) and store secrets server-side.

1. Connect the repository.
2. Set app entrypoint to `app.py`.
3. Add the six B2 values as protected secrets.
4. Do not select a paid compute tier or enter a card.
5. Open the deployed URL in a private browser.
6. Run the same short demo once and verify audio, image, hash, manifest download, and public B2 URLs.
7. Leave the app freely accessible through the end of the judging period.

If the free host cannot run eSpeak NG reliably, use the included Dockerfile on a no-card free service. Do not silently move to paid infrastructure.

## 8. Record the demo video

Use the script in `SUBMISSION.md` and keep the final cut around 2:20.

- Show the public app generating the two assets.
- Play two or three seconds of narration.
- Show the canonical hash and `Verified provenance: True`.
- Open the B2 audio/cover URLs and the stored manifest.
- Show the two Genblaze steps in the repository.
- Use no music, stock footage, logos, or third-party trademarks unless clearly licensed.
- Upload to YouTube, Vimeo, or Youku and make it publicly visible as the rules require.

## 9. Submit on Devpost

1. Create the project under the joined hackathon.
2. Paste the reviewed copy from `SUBMISSION.md`.
3. Add the working app URL, GitHub URL, and public video URL.
4. List both generation providers/models exactly as the live run reports them.
5. Explain B2 and Genblaze use accurately.
6. Add original screenshots.
7. Save a draft, review in a private browser, then submit before **August 3, 2026 at 5:00 p.m. ET**.
8. Capture the confirmation page and final public project URL.

## 10. Optional feedback prize

After genuine hands-on use, file one useful issue in the official [Genblaze repository](https://github.com/backblaze-labs/genblaze/issues). Do not invent feedback. Link the issue in the Devpost entry if the form allows it.

