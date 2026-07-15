# Verified rules and zero-spend entry plan

Verified from primary sources on **July 14, 2026**. Recheck the official pages immediately before joining or submitting because terms can change.

## Strict-fit verdict

This is a credible no-interview, no-purchase project competition:

- The official rules say no purchase or payment is necessary to enter or win.
- The rules contain no interview, live pitch, demo day, finalist presentation, or travel requirement.
- Judging is based on the submitted app, repository, description, video, and the four published criteria. Judges may choose not to test the app.
- A potential winner must later complete identity/qualification verification and any required affidavit or tax forms. That is administrative prize verification, not an employment interview.

It is not guaranteed money. It is a judged competition with 779 participants shown on the rules page when last checked.

## Dates

- Registration/submission: June 22, 2026 at 10:00 a.m. ET through **August 3, 2026 at 5:00 p.m. ET**.
- Judging: August 5 at 10:00 a.m. ET through August 11 at 5:00 p.m. ET.
- Winners announced: on or around August 12 at 2:00 p.m. ET.

Official source: [Devpost official rules, sections 1–4](https://backblaze-generative-media.devpost.com/rules).

## Prizes

- Grand Prize: **$7,000 USD**, one winner.
- Second Place: **$2,000 USD**, one winner.
- Third Place: **$1,000 USD**, one winner.
- Feedback Prize: one hour of Backblaze mentorship/architecture guidance, ten winners; no cash value is stated.

The rules allow one overall prize plus one feedback prize. Payment is subject to winner verification, required forms, tax reporting, and possible bank/currency fees.

Official source: [Devpost official rules, section 8](https://backblaze-generative-media.devpost.com/rules).

## Eligibility

The competition is open to individuals who are at least the age of majority where they live, teams of eligible individuals, and qualifying organizations. It excludes places where participation or prize receipt is prohibited, including the specific locations listed in the rules, and excludes sponsor/administrator employees, judges, certain affiliates, and conflicts of interest.

Based on the information currently available, an adult individual in Pennsylvania appears geographically eligible. Final eligibility is the entrant's legal representation and must be confirmed on the live entry screen. Do not make claims about employer, household, sponsor, judge, or affiliate conflicts without the entrant checking them.

Official source: [Devpost official rules, section 3](https://backblaze-generative-media.devpost.com/rules).

## Exact project requirements

The entry must:

1. Be a working generative AI media application using **both Backblaze B2 Cloud Storage and Genblaze**.
2. Solve a real user problem and show a production path, including reliable generation, durable storage, clear workflow, and usable experience.
3. Install and run consistently on its intended platform and behave as shown/described.
4. Be new, or—if pre-existing—add B2 and Genblaze after the competition opened and clearly explain the significant update.
5. Use third-party SDKs, APIs, and data only under valid permissions/licenses.

ProofCast was created during the submission period and meets the local software portion. It does not fully satisfy the competition until the live app actually uploads generated assets and the manifest to a real B2 bucket.

Official sources: [rules, project requirements](https://backblaze-generative-media.devpost.com/rules) and [Backblaze challenge announcement](https://www.backblaze.com/blog/backblaze-generative-media-hackathon-build-with-b2-genblaze-and-gmi-cloud/).

## Exact submission requirements

The Devpost entry must include:

- a working app URL judges can access and evaluate;
- a public or private GitHub repository with all source, assets, setup instructions, and README;
- access for GitHub user `b2genblaze` if the repository is private;
- a text description of features, functionality, B2 use, Genblaze use, and a clear list of AI providers/models;
- a functioning demo video under three minutes, hosted and publicly visible on YouTube, Vimeo, or Youku;
- no unauthorized trademarks, copyrighted music, or other third-party material in the video;
- free, unrestricted project access for sponsor/administrator/judges until judging ends;
- English submission materials or an English translation.

Optional: file useful Genblaze feedback as a GitHub issue to be considered for the feedback prize.

Official source: [Devpost official rules, submission requirements](https://backblaze-generative-media.devpost.com/rules).

## How ProofCast uses the required stack

### Genblaze

- Two real media-generation steps, each implemented against Genblaze's `SyncProvider` contract.
- `Pipeline` execution with explicit models, modalities, parameters, timeout, no paid-provider retries, and failure propagation.
- SHA-256 on every asset and `manifest.verify()` after each run.
- Canonical manifest saved locally and, in B2 mode, passed to Genblaze's object-storage sink.
- Provider swap path: local speech can later be replaced by a higher-quality connector without changing storage/provenance.

### Backblaze B2

- Genblaze `S3StorageBackend.for_backblaze(...)` integration.
- Content-addressable key strategy for deduplication.
- Dedicated prefix for generated assets and manifests.
- Public, credential-free judge URLs from a dedicated public demo bucket.
- Scoped application key and explicit cloud-write gate.
- Lifecycle policy remains console-managed; the app does not mutate bucket-wide lifecycle settings.

Official technical sources: [Genblaze developer guide](https://www.backblaze.com/docs/cloud-storage-genblaze-developer-guide), [Backblaze S3-compatible app keys](https://www.backblaze.com/docs/cloud-storage-s3-compatible-app-keys), and [B2 integration setup](https://www.backblaze.com/docs/en/cloud-storage-get-started-with-a-backblaze-integration).

## Zero-spend plan

1. Finish and verify everything locally first. This is complete for the current scaffold.
2. Let the account owner inspect the live Backblaze signup page. Stop if a card, deposit, paid plan, or billing authorization is required.
3. Use a dedicated public bucket and scoped key; do not connect a paid generation API.
4. Deploy the eSpeak NG build on a free app host only if the host requires no payment method.
5. Generate one short, original demo script. The current output is roughly 0.25 MB for audio plus 0.03 MB for the cover.
6. Keep the entire demo bucket below 50 MB, far below Backblaze's currently published first-10-GB-free allowance.
7. Check the B2 usage/billing dashboard before and after the live smoke test; set any available caps/alerts to zero or the lowest value.
8. Record one demo video, reuse the same generated assets, and avoid repeated cloud runs.
9. Submit on Devpost. No bid, application fee, interview, or paid promotion is needed.

Backblaze's current pricing page says the first 10 GB of storage is always free and lists free API calls for pay-as-you-go customers, with a stated exception for Class D over the daily free allocation. That pricing is external state, so the account owner must verify it again at signup. Official source: [Backblaze B2 pricing](https://www.backblaze.com/cloud-storage/pricing).

## Judging strategy

The four criteria are equally weighted, so the entry should make each visible in the first 90 seconds:

- **Real-world utility:** one short script becomes accessible audio plus a ready-to-share visual.
- **Production readiness:** input limits, explicit errors, cross-platform local TTS, Docker/Streamlit setup, secret isolation, and automated tests.
- **B2 storage/data orchestration:** show the content-addressed audio, cover, and manifest in the bucket, then open their durable URLs.
- **Genblaze use:** show both pipeline steps, provider/model records, the canonical hash, and successful verification.

Avoid positioning ProofCast as a polished enterprise product. Present it honestly as a working, cost-controlled reference application with a clear provider-swap path.

## Disqualifier checklist before submission

- Confirm age-of-majority and location eligibility.
- Confirm no entrant conflict with sponsor, administrator, judges, or affiliates.
- Use only original script, cover, screenshots, and narration; no copyrighted music.
- Ensure the public app actually works in a fresh browser.
- Ensure B2 URLs remain available without credentials through the end of judging.
- List eSpeak NG, Pillow, Genblaze, and all other material dependencies/licences.
- Remove secrets, personal data, and generated user content from Git history.
- Do not claim a live B2 integration until the real upload and retrieval test passes.
- Keep the video under three minutes; the rules say judges need not watch beyond three minutes.
