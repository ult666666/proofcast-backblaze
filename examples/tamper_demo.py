"""Sign and log a generated bundle, then show that each kind of tampering is caught.

    python examples/tamper_demo.py output/YOUR-RUN-ID-manifest.json

Works on copies in a temporary directory; the original bundle is never changed.
Every step runs the real `python -m proofcast.provenance` CLI. The log also gets
a few synthetic neighbour entries (SHA-256 of fixed labels) so that proofs have
real paths. Exit 0 means every check behaved as expected.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # Run from a checkout without installing the package.

from proofcast.translog import TransparencyLog  # noqa: E402


def cli(*args, expect):
    result = subprocess.run([sys.executable, "-m", "proofcast.provenance", *map(str, args)],
                            cwd=ROOT, capture_output=True, text=True, timeout=60)
    if result.returncode != expect:
        raise SystemExit(f"unexpected exit {result.returncode} for {args[0]}: {result.stdout}{result.stderr}")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def synthetic(log, label):
    TransparencyLog(log).append(hashlib.sha256(f"synthetic neighbour entry {label}".encode()).digest())


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    source = Path(sys.argv[1]).resolve()
    run = json.loads(source.read_text())["run"]
    names = [source.name] + [step["step_id"] + suffix for step, suffix in zip(run["steps"], ("-narration.wav", "-cover.png"))]
    checks = []

    def check(name, report, issue):
        found = issue in json.dumps(report)
        checks.append({"tamper": name, "caught": found, "issue": issue})

    with tempfile.TemporaryDirectory(prefix="proofcast-tamper-demo-") as temporary:
        work = Path(temporary)
        bundle, keys, log = work / "bundle", work / "keys", work / "log"
        bundle.mkdir()
        keys.mkdir(mode=0o700)
        for name in names:
            shutil.copyfile(source.parent / name, bundle / name)
        manifest = bundle / source.name
        cli("keygen", "--private-key", keys / "publisher.pem", "--public-key", keys / "publisher.pub.pem", expect=0)
        cli("keygen", "--private-key", keys / "log.pem", "--public-key", keys / "log.pub.pem", expect=0)
        cli("keygen", "--private-key", keys / "other.pem", "--public-key", keys / "other.pub.pem", expect=0)
        cli("sign", manifest, "--private-key", keys / "publisher.pem", expect=0)
        assert cli("verify", manifest, "--public-key", keys / "publisher.pub.pem", expect=0)["verified"]

        for label in ("a", "b"):
            synthetic(log, label)
        cli("log-append", log, manifest, expect=0)
        for label in ("c", "d"):
            synthetic(log, label)
        cli("log-head", log, "--private-key", keys / "log.pem", "--out", work / "head-5.json", expect=0)
        (work / "inclusion.json").write_text(json.dumps(cli("log-prove", log, manifest, expect=0)))
        trust = ("--public-key", keys / "log.pub.pem")
        assert cli("log-verify", "--tree-head", work / "head-5.json", *trust, "--inclusion", work / "inclusion.json",
                   "--manifest", manifest, "--log", log, expect=0)["verified"]
        for label in ("e", "f"):
            synthetic(log, label)
        cli("log-head", log, "--private-key", keys / "log.pem", "--out", work / "head-7.json", expect=0)
        (work / "consistency.json").write_text(json.dumps(cli("log-consistency", log, "--first", 5, expect=0)))
        assert cli("log-verify", "--tree-head", work / "head-7.json", *trust, "--consistency", work / "consistency.json",
                   "--old-tree-head", work / "head-5.json", expect=0)["verified"]

        def fresh_copy(name):
            target = work / name
            shutil.copytree(bundle, target)
            return target / source.name

        changed = fresh_copy("asset-changed")
        cover = changed.parent / names[2]
        cover.write_bytes(cover.read_bytes() + b"changed after signing")
        check("one byte appended to the cover image", cli("verify", changed, "--public-key", keys / "publisher.pub.pem", expect=1), "digest_mismatch")

        changed = fresh_copy("manifest-changed")
        text = changed.read_text()
        changed.write_text(text.replace('"status":"completed"', '"status":"completed" ', 1) if '"status":"completed"' in text else text + " ")
        check("one byte added to the manifest", cli("verify", changed, "--public-key", keys / "publisher.pub.pem", expect=1), "bad_signature")

        check("signature checked against a different trusted key",
              cli("verify", manifest, "--public-key", keys / "other.pub.pem", expect=1), "untrusted_key")

        proof = json.loads((work / "inclusion.json").read_text())
        proof["inclusion_path"][0] = format(int(proof["inclusion_path"][0], 16) ^ 1, "064x")
        (work / "inclusion-changed.json").write_text(json.dumps(proof))
        check("one bit flipped in the inclusion proof",
              cli("log-verify", "--tree-head", work / "head-5.json", *trust, "--inclusion", work / "inclusion-changed.json",
                  "--manifest", manifest, expect=1), "inclusion_proof_failed")

        head = json.loads((work / "head-5.json").read_text())
        head["root_hash"] = hashlib.sha256(b"a different root").hexdigest()
        (work / "head-changed.json").write_text(json.dumps(head))
        check("root hash replaced in a signed tree head",
              cli("log-verify", "--tree-head", work / "head-changed.json", *trust, expect=1), "bad_signature")

        entries = log / "manifest-digests.txt"
        lines = entries.read_text().splitlines(keepends=True)
        lines[1] = hashlib.sha256(b"rewritten history").hexdigest() + "\n"
        entries.write_text("".join(lines))
        cli("log-head", log, "--private-key", keys / "log.pem", "--out", work / "head-7-rewritten.json", expect=0)
        (work / "consistency-rewritten.json").write_text(json.dumps(cli("log-consistency", log, "--first", 5, expect=0)))
        check("earlier log entry rewritten, then a new head signed",
              cli("log-verify", "--tree-head", work / "head-7-rewritten.json", *trust, "--consistency",
                  work / "consistency-rewritten.json", "--old-tree-head", work / "head-5.json", expect=1),
              "consistency_proof_failed")
        check("auditor recomputes the root of the rewritten log",
              cli("log-verify", "--tree-head", work / "head-5.json", *trust, "--log", log, expect=1),
              "log_differs_from_tree_head")

    print(json.dumps({"bundle_signed_and_logged": True, "inclusion_and_consistency_verified": True,
                      "tamper_checks": checks}, indent=2))
    return 0 if all(item["caught"] for item in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
