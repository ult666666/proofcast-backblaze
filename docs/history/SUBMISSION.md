# Devpost submission packet — draft, not yet submitted

Replace every bracketed placeholder and remove this line before submission.

## Project name

ProofCast

## Tagline

One short lesson, two accessible media assets, and a provenance record you can verify.

## Short description

ProofCast turns a short educational or safety script into local AI narration and a high-contrast visual cover. Genblaze orchestrates both generation steps, hashes every output, and creates a verifiable provenance manifest. Backblaze B2 stores the audio, cover, and manifest with content-addressable keys and durable public URLs.

## Inspiration

Small education, nonprofit, and internal-training teams regularly publish the same idea in several formats. A lesson may need audio for accessibility, a visual card for distribution, and a record of how the media was generated. Those steps are usually split across tools, and the provenance record is easy to lose. ProofCast makes the media bundle and evidence together.

## What it does

1. The user enters an original title and a short, non-sensitive lesson script.
2. A local text-to-speech model creates WAV narration without a paid generation API.
3. A second local provider creates a readable 1280×720 visual cover from the same prompt.
4. Genblaze records both providers, models, prompts, parameters, and output hashes in one canonical manifest.
5. ProofCast verifies the manifest after every run.
6. Backblaze B2 stores the two assets and provenance under content-addressable keys so identical outputs are deduplicated and judges get durable URLs.

## How we built it

- Python 3.11+
- Streamlit user interface
- Genblaze `Pipeline`, `SyncProvider`, `ObjectStorageSink`, canonical manifests, and SHA-256 verification
- Backblaze B2 through `genblaze-s3` and `S3StorageBackend.for_backblaze(...)`
- eSpeak NG for free local Linux text-to-speech; Apple Speech is supported for local macOS development
- Pillow for the accessible visual cover
- Pytest for end-to-end, provider, manifest, and cloud-safety tests

The application defaults to local-only mode. Cloud writes require a complete B2 configuration plus an explicit `B2_ENABLED=1` gate. The CLI adds a second `--allow-b2` gate. Scripts are capped at 1,200 characters, provider retries are disabled, and content-addressable storage avoids duplicate objects.

## AI providers and models used

- `proofcast-local-speech` / `espeak-ng-en-us` in the public Linux app.
- `proofcast-accessible-cover` / `proofcast-accessible-cover-v1` for the high-contrast visual card.
- Optional local macOS development path: `proofcast-local-speech` / `apple-speech-[selected voice]`.

No paid model API is required for the submitted workflow.

## How ProofCast uses Genblaze

Genblaze is the orchestration and evidence layer, not a wrapper around one API call. Two independent providers implement the Genblaze provider contract and execute as an explicit multi-step pipeline. Genblaze captures the model and parameters for each step, includes both media artifacts in one run, generates the canonical provenance manifest, verifies SHA-256 integrity, and sends the media/manifest to the storage sink. A higher-fidelity speech or image provider can replace a local provider without rewriting storage or provenance.

## How ProofCast uses Backblaze B2

Generated WAV, PNG, and provenance are stored in a dedicated B2 bucket through Genblaze's S3-compatible backend. The app uses content-addressable object keys for deduplication, a dedicated prefix for organization, a bucket-scoped key for least privilege, and a public URL base so judges can retrieve the demo artifacts without credentials. The app deliberately leaves bucket-wide lifecycle settings under console control instead of silently changing them.

## Challenges we ran into

The main challenge was making an app that is both easy to judge and safe to run for free. We separated local generation from cloud persistence, added two independent cloud-write gates, capped script size, removed paid-provider retries, and required a dedicated public demo bucket. We also made every output hashable before upload so manifest verification works in local and B2 modes.

## Accomplishments we are proud of

- A real two-asset media workflow without a paid inference provider.
- A verified canonical manifest for every run.
- Content-addressable B2 storage rather than opaque random filenames.
- Cross-platform local speech support.
- One-command local smoke test and automated regression coverage.
- A public-demo design that does not expose B2 secrets to the browser.

## What we learned

Provenance is most useful when it is part of the media pipeline from the beginning. Adding a sidecar record later is fragile. Genblaze makes the provider/model/prompt lineage a native output of the run, while B2 makes the resulting evidence durable and independently accessible.

## What's next

- Add multilingual eSpeak NG voices and pronunciation controls.
- Add an optional human approval checkpoint before B2 persistence.
- Add signed manifests and retention policies for regulated training workflows.
- Add a higher-quality local speech connector while preserving the same Genblaze/B2 interface.
- Add accessible caption exports and a lightweight media library view.

## Links

- Working app: `[PUBLIC_APP_URL]`
- Repository: https://github.com/ult666666/proofcast-backblaze
- Demo video: `[PUBLIC_VIDEO_URL]`
- Sample audio: `[PUBLIC_B2_AUDIO_URL]`
- Sample cover: `[PUBLIC_B2_COVER_URL]`
- Provenance manifest: `[PUBLIC_B2_MANIFEST_URL]`
- Optional Genblaze feedback issue: `[ISSUE_URL_OR_REMOVE]`

## Demo video script (target 2:20)

**0:00–0:15 — Problem**  
“A short training lesson often needs an audio version, a shareable visual, and proof of how both were generated. ProofCast produces the whole evidence-backed bundle in one workflow.”

**0:15–0:35 — Input and safety**  
Show the public app. Point out the 1,200-character limit, non-sensitive-content confirmation, local model, and B2 status.

**0:35–1:00 — Generate**  
Enter the original phishing-awareness sample and click Generate. Show the narration player and cover. Play two or three seconds of audio.

**1:00–1:25 — Genblaze evidence**  
Show the two provider/model records, canonical hash, and `Verified provenance: True`. Download and briefly open the manifest.

**1:25–1:50 — B2**  
Open the audio and cover B2 URLs in a private window. Show the corresponding content-addressed objects and stored run manifest in the bucket.

**1:50–2:10 — Production path**  
Show the repository's provider, storage, explicit cloud gate, tests, Dockerfile, and cross-platform eSpeak/Apple Speech path.

**2:10–2:20 — Close**  
“ProofCast makes accessible media and its provenance together—locally generated, durably stored, and independently verifiable.”

## Final truth check before pasting

- `[ ]` Public app works in a private browser.
- `[ ]` Actual live run used eSpeak NG, not an unlisted model.
- `[ ]` All three B2 URLs open without credentials.
- `[ ]` Manifest verifies after the live B2 run.
- `[ ]` Repository is public or `b2genblaze` has access.
- `[ ]` Video is publicly visible and under three minutes.
- `[ ]` No trademark, copyrighted music, secret, or private text appears.
- `[ ]` Every bracketed placeholder has been replaced or removed.
