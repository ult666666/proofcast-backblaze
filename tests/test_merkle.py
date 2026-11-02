"""RFC 6962 / RFC 9162 Merkle hashing against published vectors and an oracle."""

import base64
import hashlib
import json
from pathlib import Path
import random

import pytest

from proofcast import merkle

VECTORS = Path(__file__).parent / "vectors" / "transparency-dev-merkle"
# testonly/constants.go in transparency-dev/merkle at c39fbf35 (see the vectors README).
LEAF_INPUTS = ["", "00", "10", "2021", "3031", "40414243", "5051525354555657", "606162636465666768696a6b6c6d6e6f"]
ROOTS = [
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d",
    "fac54203e7cc696cf0dfcb42c92a1d9dbaf70ad9e621f4bd8d98662f00e3c125",
    "aeb6bcfe274b70a14fb067a5e5578264db0fa9b51af5e0ba159158f329e06e77",
    "d37ee418976dd95753c1c73862b9398fa2a2cf9b4ff0fdfe8b30cd95209614b7",
    "4e3bbb1f7b478dcfe71fb631631519a3bca12c9aefca1612bfce4c13a86264d4",
    "76e67dadbcdf1e10e1b74ddc608abd2f98dfb16fbce75277b5232a127f2087ef",
    "ddb89be403809e325750d3d263cd78929c2942b7942a34b77e122c9594a74c8c",
    "5dc9da79a70659a9ad559cb701ded9a2ab9d823aad2f4960cfe370eff4604328",
]
LEVEL_ONE = ["fac54203e7cc696cf0dfcb42c92a1d9dbaf70ad9e621f4bd8d98662f00e3c125",
             "5f083f0a1a33ca076a95279832580db3e0ef4584bdff1f54c8a360f50de3031e",
             "0ebc5d3437fbe2db158b9f126a1d118e308181031d0a949f8dededebc558ef6a",
             "ca854ea128ed050b41b35ffc1b87b8eb2bde461e9e3b5596ece6b9d5975a0ae0"]
# This one consistency probe uses 12-byte placeholder roots with equal sizes.
# The reference accepts it without checking the roots; ProofCast requires every
# hash to be 32 bytes, so it rejects it on purpose.
STRICTER = {"consistency/additional/sizes-are-equal-one-and-proof-is-empty.json"}


def probes(kind):
    return json.loads((VECTORS / f"{kind}.json").read_text())


def b64(value):
    return base64.b64decode(value) if value else b""


def test_reference_roots_for_every_prefix_and_level_one_nodes():
    hashes = [merkle.leaf_hash(bytes.fromhex(item)) for item in LEAF_INPUTS]
    assert [merkle.root(hashes[:size]).hex() for size in range(9)] == ROOTS
    assert [merkle.node_hash(hashes[i], hashes[i + 1]).hex() for i in range(0, 8, 2)] == LEVEL_ONE
    assert merkle.leaf_hash(b"") != hashlib.sha256(b"").digest()  # The 0x00 prefix is applied.


@pytest.mark.parametrize("probe", probes("inclusion"), ids=lambda probe: probe["file"])
def test_published_inclusion_probes(probe):
    result = merkle.verify_inclusion(b64(probe.get("leafHash")), probe["leafIdx"], probe["treeSize"],
                                     [b64(item) for item in probe.get("proof") or []], b64(probe.get("root")))
    assert result is (not probe["wantErr"])


@pytest.mark.parametrize("probe", probes("consistency"), ids=lambda probe: probe["file"])
def test_published_consistency_probes(probe):
    result = merkle.verify_consistency(probe["size1"], probe["size2"], b64(probe.get("root1")),
                                       b64(probe.get("root2")), [b64(item) for item in probe.get("proof") or []])
    assert result is (False if probe["file"] in STRICTER else not probe["wantErr"])


def test_vector_files_are_complete():
    assert (len(probes("inclusion")), len(probes("consistency"))) == (98, 98)
    assert sum(not probe["wantErr"] for probe in probes("inclusion") + probes("consistency")) == 12


# An independent oracle: the RFC 6962 definitions over list slices, sharing no
# code with proofcast.merkle.
def _k(n):
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def mth(data):
    if not data:
        return hashlib.sha256(b"").digest()
    if len(data) == 1:
        return hashlib.sha256(b"\x00" + data[0]).digest()
    k = _k(len(data))
    return hashlib.sha256(b"\x01" + mth(data[:k]) + mth(data[k:])).digest()


def path(m, data):
    if len(data) == 1:
        return []
    k = _k(len(data))
    return path(m, data[:k]) + [mth(data[k:])] if m < k else path(m - k, data[k:]) + [mth(data[:k])]


def subproof(m, data, complete):
    if m == len(data):
        return [] if complete else [mth(data)]
    k = _k(len(data))
    if m <= k:
        return subproof(m, data[:k], complete) + [mth(data[k:])]
    return subproof(m - k, data[k:], False) + [mth(data[:k])]


def tree(size, seed):
    rng = random.Random(seed)
    data = [rng.randbytes(rng.randint(0, 40)) for _ in range(size)]
    return data, [merkle.leaf_hash(item) for item in data]


def test_every_proof_up_to_64_leaves_matches_the_oracle_and_verifies():
    data, hashes = tree(64, 9162)
    for n in range(1, 65):
        root = merkle.root(hashes[:n])
        assert root == mth(data[:n])
        for m in range(n):
            proof = merkle.inclusion_proof(hashes[:n], m)
            assert proof == path(m, data[:n])
            assert merkle.verify_inclusion(hashes[m], m, n, proof, root)
        for m in range(1, n + 1):
            proof = merkle.consistency_proof(hashes[:n], m)
            assert proof == (subproof(m, data[:n], True) if m < n else [])
            assert merkle.verify_consistency(m, n, mth(data[:m]), root, proof)


@pytest.mark.parametrize("seed", range(8))
def test_random_larger_trees_verify(seed):
    rng = random.Random(seed)
    size = rng.randint(65, 1500)
    data, hashes = tree(size, seed)
    root = merkle.root(hashes)
    assert root == mth(data)
    for index in rng.sample(range(size), 20):
        assert merkle.verify_inclusion(hashes[index], index, size, merkle.inclusion_proof(hashes, index), root)
    for first in rng.sample(range(1, size), 20):
        proof = merkle.consistency_proof(hashes, first)
        assert merkle.verify_consistency(first, size, merkle.root(hashes[:first]), root, proof)


def flipped(value, bit):
    changed = bytearray(value)
    changed[bit // 8] ^= 1 << (bit % 8)
    return bytes(changed)


def test_any_change_to_an_inclusion_proof_leaf_root_or_index_fails():
    rng = random.Random(6962)
    data, hashes = tree(40, 6962)
    for n in range(1, 41):
        root = merkle.root(hashes[:n])
        for m in range(n):
            proof = merkle.inclusion_proof(hashes[:n], m)
            leaf = hashes[m]
            assert not merkle.verify_inclusion(flipped(leaf, rng.randrange(256)), m, n, proof, root)
            assert not merkle.verify_inclusion(leaf, m, n, proof, flipped(root, rng.randrange(256)))
            for i in range(len(proof)):
                changed = proof[:i] + [flipped(proof[i], rng.randrange(256))] + proof[i + 1:]
                assert not merkle.verify_inclusion(leaf, m, n, changed, root)
            for other in {m - 1, m + 1, m ^ 1} - {m}:
                assert not merkle.verify_inclusion(leaf, other, n, proof, root)
            assert not merkle.verify_inclusion(leaf, m, n, proof + [rng.randbytes(32)], root)
            if proof:
                assert not merkle.verify_inclusion(leaf, m, n, proof[:-1], root)
            if len(proof) > 1:
                assert not merkle.verify_inclusion(leaf, m, n, proof[::-1], root)


def test_any_change_to_a_consistency_proof_or_its_roots_fails():
    rng = random.Random(9162)
    data, hashes = tree(40, 9162)
    for n in range(2, 41):
        new_root = merkle.root(hashes[:n])
        for m in range(1, n):
            old_root = merkle.root(hashes[:m])
            proof = merkle.consistency_proof(hashes[:n], m)
            assert not merkle.verify_consistency(m, n, flipped(old_root, rng.randrange(256)), new_root, proof)
            assert not merkle.verify_consistency(m, n, old_root, flipped(new_root, rng.randrange(256)), proof)
            for i in range(len(proof)):
                changed = proof[:i] + [flipped(proof[i], rng.randrange(256))] + proof[i + 1:]
                assert not merkle.verify_consistency(m, n, old_root, new_root, changed)
            assert not merkle.verify_consistency(m, n, old_root, new_root, proof + [rng.randbytes(32)])
            assert not merkle.verify_consistency(m, n, old_root, new_root, proof[:-1])
    # A rewritten earlier leaf cannot be proven consistent with the old root.
    rewritten = list(hashes)
    rewritten[3] = merkle.leaf_hash(b"rewritten")
    old_root = merkle.root(hashes[:10])
    assert not merkle.verify_consistency(10, 40, old_root, merkle.root(rewritten),
                                         merkle.consistency_proof(rewritten, 10))


def test_a_proof_alone_does_not_pin_the_tree_size():
    # The verifiers rebuild the root from the leaf and its siblings. For the
    # leftmost leaf, sizes 3 and 4 combine the same siblings in the same order,
    # so a size-3 proof also passes when told the size is 4. The same holds for
    # a consistency proof from size 1. The tree size is authenticated only
    # because a signed tree head signs it together with the root;
    # translog.inclusion_issues and consistency_issues compare proof sizes with
    # the signed heads (tests/test_translog.py).
    _, hashes = tree(4, 2)
    root3 = merkle.root(hashes[:3])
    assert merkle.verify_inclusion(hashes[0], 0, 4, merkle.inclusion_proof(hashes[:3], 0), root3)
    assert merkle.verify_consistency(1, 4, hashes[0], root3, merkle.consistency_proof(hashes[:3], 1))


def test_invalid_inputs_are_rejected():
    _, hashes = tree(5, 1)
    root = merkle.root(hashes)
    proof = merkle.inclusion_proof(hashes, 2)
    assert not merkle.verify_inclusion(hashes[2][:31], 2, 5, proof, root)
    assert not merkle.verify_inclusion(hashes[2], -1, 5, proof, root)
    assert not merkle.verify_inclusion(hashes[2], 5, 5, proof, root)
    assert not merkle.verify_consistency(0, 5, merkle.EMPTY_ROOT, root, [])  # Proof from the empty tree.
    assert not merkle.verify_consistency(5, 4, root, root, [])
    assert merkle.verify_consistency(5, 5, root, root, [])
    assert not merkle.verify_consistency(5, 5, root, root, [root])
    for bad in [-1, 5]:
        with pytest.raises(ValueError):
            merkle.inclusion_proof(hashes, bad)
    for bad in [0, 6]:
        with pytest.raises(ValueError):
            merkle.consistency_proof(hashes, bad)
    assert merkle.root([]) == merkle.EMPTY_ROOT
