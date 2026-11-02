"""Merkle tree hashing, inclusion proofs and consistency proofs.

Follows RFC 6962 section 2.1 and RFC 9162 section 2.1 with SHA-256:
a leaf hash is SHA-256(0x00 || data) and an interior node hash is
SHA-256(0x01 || left || right). The prefixes keep a leaf from ever hashing
like an interior node (a second-preimage defence). The tree over n leaves
splits at k, the largest power of two smaller than n.

https://www.rfc-editor.org/rfc/rfc6962#section-2.1
https://www.rfc-editor.org/rfc/rfc9162#section-2.1
"""

from __future__ import annotations

from collections.abc import Sequence
import hashlib

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"
HASH_SIZE = 32
EMPTY_ROOT = hashlib.sha256(b"").digest()


def leaf_hash(data: bytes) -> bytes:
    return hashlib.sha256(LEAF_PREFIX + data).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(NODE_PREFIX + left + right).digest()


def _split(size: int) -> int:
    """The largest power of two strictly smaller than size (size >= 2)."""
    return 1 << ((size - 1).bit_length() - 1)


def _root(hashes: Sequence[bytes], start: int, end: int) -> bytes:
    if end - start == 1:
        return hashes[start]
    k = _split(end - start)
    return node_hash(_root(hashes, start, start + k), _root(hashes, start + k, end))


def root(leaf_hashes: Sequence[bytes]) -> bytes:
    """MTH(D[n]) from the leaf hashes; the empty tree hashes to SHA-256('')."""
    return _root(leaf_hashes, 0, len(leaf_hashes)) if leaf_hashes else EMPTY_ROOT


def _path(hashes: Sequence[bytes], index: int, start: int, end: int) -> list[bytes]:
    if end - start == 1:
        return []
    k = _split(end - start)
    if index < k:
        return _path(hashes, index, start, start + k) + [_root(hashes, start + k, end)]
    return _path(hashes, index - k, start + k, end) + [_root(hashes, start, start + k)]


def inclusion_proof(leaf_hashes: Sequence[bytes], index: int) -> list[bytes]:
    """PATH(m, D[n]) from RFC 9162 section 2.1.3.1, ordered leaf to root."""
    if not 0 <= index < len(leaf_hashes):
        raise ValueError("leaf index must be inside the tree")
    return _path(leaf_hashes, index, 0, len(leaf_hashes))


def _subproof(hashes: Sequence[bytes], first: int, start: int, end: int, complete: bool) -> list[bytes]:
    size = end - start
    if first == size:
        return [] if complete else [_root(hashes, start, end)]
    k = _split(size)
    if first <= k:
        return _subproof(hashes, first, start, start + k, complete) + [_root(hashes, start + k, end)]
    return _subproof(hashes, first - k, start + k, end, False) + [_root(hashes, start, start + k)]


def consistency_proof(leaf_hashes: Sequence[bytes], first: int) -> list[bytes]:
    """PROOF(m, D[n]) from RFC 9162 section 2.1.4.1; empty when m equals n."""
    if not 0 < first <= len(leaf_hashes):
        raise ValueError("the earlier tree size must be between 1 and the current size")
    if first == len(leaf_hashes):
        return []
    return _subproof(leaf_hashes, first, 0, len(leaf_hashes), True)


def _valid_hashes(*values) -> bool:
    return all(isinstance(value, bytes) and len(value) == HASH_SIZE for value in values)


def verify_inclusion(leaf: bytes, index: int, size: int, proof: Sequence[bytes], root_hash: bytes) -> bool:
    """RFC 9162 section 2.1.3.2: does proof place leaf (a leaf hash) at index?"""
    if not _valid_hashes(leaf, root_hash, *proof) or not 0 <= index < size:
        return False
    fn, sn, r = index, size - 1, leaf
    for p in proof:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            r = node_hash(p, r)
            if not fn & 1:
                while fn and not fn & 1:
                    fn >>= 1
                    sn >>= 1
        else:
            r = node_hash(r, p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r == root_hash


def verify_consistency(first: int, second: int, first_root: bytes, second_root: bytes,
                       proof: Sequence[bytes]) -> bool:
    """RFC 9162 section 2.1.4.2: is the tree of size second an extension of first?

    The RFC defines proofs for 0 < first < second. Equal sizes need an empty
    proof and equal roots. A proof from the empty tree would show nothing, so
    it is refused, as the transparency-dev reference implementation does.
    """
    if not _valid_hashes(first_root, second_root, *proof) or not 0 < first <= second:
        return False
    if first == second:
        return not proof and first_root == second_root
    if not proof:
        return False
    path = list(proof)
    if first & (first - 1) == 0:  # An exact power of two: the old root is a node of the new tree.
        path.insert(0, first_root)
    fn, sn = first - 1, second - 1
    while fn & 1:
        fn >>= 1
        sn >>= 1
    fr = sr = path[0]
    for c in path[1:]:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            fr = node_hash(c, fr)
            sr = node_hash(c, sr)
            if not fn & 1:
                while fn and not fn & 1:
                    fn >>= 1
                    sn >>= 1
        else:
            sr = node_hash(sr, c)
        fn >>= 1
        sn >>= 1
    return fr == first_root and sr == second_root and sn == 0
