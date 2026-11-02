# Merkle proof test vectors from transparency-dev/merkle

These files hold the inclusion and consistency proof probes published in
[transparency-dev/merkle](https://github.com/transparency-dev/merkle), the
Go implementation of RFC 6962 and RFC 9162 Merkle hashing maintained by the
transparency-dev project. They were copied from commit
`c39fbf350a405f68571bf4c42a6a518eb0a46a4b` (2026-10-12):

- `inclusion.json`: every file under `testdata/inclusion/`
- `consistency.json`: every file under `testdata/consistency/`

Each original JSON file became one array element, with its path relative to
`testdata/` added as `file`. Hashes stay base64-encoded and no value was
changed. Each probe gives a proof and `wantErr`: whether a verifier must
reject it. Most probes are deliberate corruptions of a valid proof (a flipped
bit, a wrong index or size, an extra or missing hash).

The reference root and node hashes used in `tests/test_merkle.py` come from
`testonly/constants.go` at the same commit.

The source files carry "Copyright 2017 Google LLC" and "Copyright 2019 Google
LLC" notices. Licensed under the Apache License 2.0; see `LICENSE` in this
directory.
