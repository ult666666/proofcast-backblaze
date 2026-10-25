# Independent local bundle verification

ProofCast currently calls Genblaze's `manifest.verify()`. Genblaze 0.3.4 checks the canonical provenance hash and the presence of declared SHA-256 values; it does not read output bytes. Appending bytes to the generated WAV leaves that result true.

Add an offline verifier for a saved ProofCast manifest and its two local media files. It must validate the manifest hash and the ProofCast two-step contract, reread bytes to check SHA-256 and size, and compare PNG/WAV metadata with the manifest. Missing files, changed bytes, malformed manifests and inconsistent metadata produce explicit machine-readable failures and a nonzero CLI exit. Inspection never creates storage, calls a speech provider, reads cloud configuration or fetches URLs.

Approaches considered: only clarify the existing label (does not detect changed media); fetch all asset URLs (introduces network and credential concerns); verify the retained local bundle (chosen for a useful deterministic, no-account workflow). Use manifest-adjacent files named by the recorded step IDs, with an optional explicit asset directory for moved bundles. Validate local file URL names and reject remote schemes other than credential-free HTTPS. HTTPS transport URLs are recorded only; remote bytes and uploads are never validated.

A successful report means the supplied manifest is internally consistent and the local bytes match it. Hashes are not signatures, proof of authorship, approval or evidence that a remote upload exists. Both generation and inspection must state this scope. B2 remains opt-in, with no change to its upload gate or credentials.

Implementation stays on a fresh task-owned branch. Preserve existing CLI generation flags and expose inspection through `--verify MANIFEST [--asset-dir DIRECTORY]`. `verified` remains available, with its meaning strengthened to full local verification; expose separate manifest/media results and a scope string. Existing third-party licenses and historical verification claims remain intact.
