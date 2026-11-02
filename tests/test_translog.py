"""The local transparency log, signed tree heads and the provenance CLI."""

import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofcast import merkle, signing
from proofcast.translog import LogError, TransparencyLog, consistency_issues, inclusion_issues

ROOT = Path(__file__).resolve().parents[1]


def digest(label):
    return hashlib.sha256(f"synthetic entry {label}".encode()).digest()


def test_append_is_ordered_idempotent_and_matches_the_merkle_root(tmp_path):
    log = TransparencyLog(tmp_path / "log")
    (tmp_path / "log").mkdir()
    assert log.root() == (0, merkle.EMPTY_ROOT)
    results = [log.append(digest(i)) for i in range(5)]
    assert [r["index"] for r in results] == list(range(5))
    assert log.append(digest(2)) == {"index": 2, "tree_size": 5, "duplicate": True}
    assert log.root() == (5, merkle.root([merkle.leaf_hash(digest(i)) for i in range(5)]))
    assert log.root(3)[1] == merkle.root([merkle.leaf_hash(digest(i)) for i in range(3)])
    assert (tmp_path / "log" / "manifest-digests.txt").read_text() == "".join(digest(i).hex() + "\n" for i in range(5))
    for bad in [b"short", "0" * 64, digest(1)[:31]]:
        with pytest.raises(LogError):
            log.append(bad)
    for size in [-1, 6, True]:
        with pytest.raises(LogError):
            log.root(size)
    with pytest.raises(LogError):
        TransparencyLog(tmp_path / "missing").root()


@pytest.mark.parametrize("damage", [b"zz" * 32 + b"\n", b"A" * 64 + b"\n", b"0" * 64, b"0" * 63 + b"\n\n"])
def test_a_damaged_log_is_refused(tmp_path, damage):
    log = TransparencyLog(tmp_path)
    log.append(digest(0))
    with open(log.path, "ab") as handle:
        handle.write(damage)
    with pytest.raises(LogError, match="damaged"):
        log.root()
    with pytest.raises(LogError, match="damaged"):
        log.append(digest(1))


def test_proofs_verify_against_signed_heads_at_every_size(tmp_path):
    key = Ed25519PrivateKey.generate()
    log = TransparencyLog(tmp_path)
    heads = {}
    for i in range(20):
        log.append(digest(i))
        size, root = log.root()
        heads[size] = signing.sign_tree_head(size, root, key, 1_000 + size)
    for size, head in heads.items():
        for i in range(size):
            proof = log.inclusion_proof(digest(i), size)
            assert inclusion_issues(proof, digest(i), head) == []
            assert inclusion_issues(proof, digest(i + 1), head) == ["proof_is_for_another_manifest", "inclusion_proof_failed"]
            if size < 20:
                # The size alone is not authenticated by the hashes; the signed head binds it.
                assert "proof_tree_size_differs_from_tree_head" in inclusion_issues(proof, digest(i), heads[size + 1])
        for first in range(1, size + 1):
            proof = log.consistency_proof(first, size)
            assert consistency_issues(proof, heads[first], head) == []
            if first < size:  # Checked against a head of another size, the proof is refused.
                assert consistency_issues(proof, heads[first], heads[size - 1]) == ["proof_sizes_differ_from_tree_heads"]
    proof = log.inclusion_proof(digest(5), 20)
    proof["inclusion_path"][0] = proof["inclusion_path"][0][::-1]
    assert inclusion_issues(proof, digest(5), heads[20]) == ["inclusion_proof_failed"]
    for broken in [{**proof, "extra": 1}, {**proof, "leaf_index": -1}, {**proof, "inclusion_path": ["xyz"]}, "text"]:
        assert inclusion_issues(broken, digest(5), heads[20]) == ["invalid_proof"]
    with pytest.raises(LogError):
        log.inclusion_proof(digest(99))
    with pytest.raises(LogError):
        log.inclusion_proof(digest(19), 19)  # Entry 19 is outside the first 19 entries.
    for first, second in [(0, 5), (6, 5), (1, 21)]:
        with pytest.raises(LogError):
            log.consistency_proof(first, second)


def test_rewriting_an_earlier_entry_breaks_consistency_with_an_old_head(tmp_path):
    key = Ed25519PrivateKey.generate()
    log = TransparencyLog(tmp_path)
    for i in range(8):
        log.append(digest(i))
    old = signing.sign_tree_head(*log.root(), key, 1)
    lines = log.path.read_text().splitlines(keepends=True)
    lines[2] = digest("rewritten").hex() + "\n"
    log.path.write_text("".join(lines))
    log.append(digest(8))
    new = signing.sign_tree_head(*log.root(), key, 2)  # An operator can sign any history...
    assert signing.tree_head_issues(new, key.public_key()) == []
    proof = log.consistency_proof(8, 9)  # ...but cannot prove it extends the old head.
    assert consistency_issues(proof, old, new) == ["consistency_proof_failed"]


def test_concurrent_appends_keep_every_entry_once(tmp_path):
    def append(i):
        return TransparencyLog(tmp_path).append(digest(i % 40))["index"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(append, range(120)))
    entries = TransparencyLog(tmp_path).digests()
    assert len(entries) == 40 and set(entries) == {digest(i) for i in range(40)}


def run(*args):
    result = subprocess.run([sys.executable, "-m", "proofcast.provenance", *map(str, args)],
                            cwd=ROOT, capture_output=True, text=True, timeout=60)
    return result.returncode, (json.loads(result.stdout) if result.stdout.strip() else None), result.stderr


def test_cli_signs_verifies_logs_and_proves(local_bundle, tmp_path):
    manifest, keys, log = local_bundle.manifest_path, tmp_path / "keys", tmp_path / "log"
    keys.mkdir()
    code, out, _ = run("keygen", "--private-key", keys / "k.pem", "--public-key", keys / "k.pub.pem")
    assert code == 0 and len(out["key_fingerprint"]) == 64
    assert run("keygen", "--private-key", keys / "k.pem", "--public-key", keys / "x.pem")[0] == 2
    code, out, _ = run("sign", manifest, "--private-key", keys / "k.pem")
    assert code == 0 and Path(out["signature_path"]).name == manifest.name.replace(".json", ".sig.json")
    assert run("sign", manifest, "--private-key", keys / "k.pem")[0] == 2  # Never overwrites a signature.
    code, out, _ = run("verify", manifest, "--public-key", keys / "k.pub.pem")
    assert code == 0 and out["verified"] and out["signature_verified"] and out["bundle"]["verified"]
    assert run("verify", manifest, "--fingerprint", out["key_fingerprint"])[0] == 0
    assert run("verify", manifest)[0] == 2  # A trusted key or fingerprint is required.

    code, out, _ = run("log-append", log, manifest)
    assert code == 0 and (out["index"], out["tree_size"], out["duplicate"]) == (0, 1, False)
    assert run("log-append", log, manifest)[1]["duplicate"] is True
    code, head, _ = run("log-head", log, "--private-key", keys / "k.pem", "--out", tmp_path / "head.json")
    assert code == 0 and head["tree_size"] == 1
    code, proof, _ = run("log-prove", log, manifest)
    (tmp_path / "proof.json").write_text(json.dumps(proof))
    code, out, _ = run("log-verify", "--tree-head", tmp_path / "head.json", "--public-key", keys / "k.pub.pem",
                       "--inclusion", tmp_path / "proof.json", "--manifest", manifest, "--log", log)
    assert code == 0 and out["verified"] and out["tree_size"] == 1
    assert run("log-consistency", log, "--first", "2")[0] == 2
    assert run("log-prove", log, manifest, "--tree-size", "5")[0] == 2

    shutil.copyfile(manifest, tmp_path / "copy.json")
    cover = next(manifest.parent.glob("*-cover.png"))
    cover.write_bytes(cover.read_bytes() + b"changed")
    code, out, _ = run("verify", manifest, "--public-key", keys / "k.pub.pem")
    assert code == 1 and out["signature_verified"] and not out["bundle"]["verified"]
    assert run("sign", manifest, "--private-key", keys / "k.pem", "--signature", tmp_path / "s.json")[0] == 1  # Refused.
    assert run("log-append", log, manifest)[0] == 1
    manifest.write_bytes(manifest.read_bytes() + b"\n")
    code, out, _ = run("verify", manifest, "--public-key", keys / "k.pub.pem")
    assert code == 1 and "bad_signature" in out["signature_issues"]


def test_tamper_demo_catches_every_change_on_a_real_bundle(local_bundle):
    before = {path.name: path.read_bytes() for path in local_bundle.manifest_path.parent.iterdir()}
    result = subprocess.run([sys.executable, str(ROOT / "examples" / "tamper_demo.py"), str(local_bundle.manifest_path)],
                            capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["bundle_signed_and_logged"] and report["inclusion_and_consistency_verified"]
    assert len(report["tamper_checks"]) == 7 and all(item["caught"] for item in report["tamper_checks"])
    assert {path.name: path.read_bytes() for path in local_bundle.manifest_path.parent.iterdir()} == before
