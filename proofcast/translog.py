"""A local, append-only transparency log of manifest SHA-256 digests.

Each entry is the SHA-256 of one saved manifest file. Leaf i of the Merkle
tree is SHA-256(0x00 || digest_i), as RFC 6962 hashes leaf data. Appends only
add lines; a signed tree head commits to the first tree_size entries. Changing,
removing or reordering an earlier entry changes every later root, so it cannot
pass a consistency check against a tree head signed before the change.

The log is one text file with one lowercase hex digest per line. Proofs are
computed from all entries on each request, which is O(n) hashing per proof.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import re

from proofcast import merkle

ENTRIES = "manifest-digests.txt"
INCLUSION_FORMAT = "proofcast-inclusion-proof"
CONSISTENCY_FORMAT = "proofcast-consistency-proof"
_LINE = re.compile(rb"[0-9a-f]{64}\n")

try:  # POSIX advisory locking; ProofCast's local speech engines are macOS/Linux only.
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


class LogError(ValueError):
    """The log is damaged or a request is outside the tree."""


class TransparencyLog:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.path = self.directory / ENTRIES

    @contextmanager
    def _locked(self, exclusive: bool):
        if exclusive:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        elif not self.directory.is_dir():
            raise LogError(f"no transparency log at {self.directory}")
        fd = os.open(self.directory / ".lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
        finally:
            os.close(fd)  # Closing releases the lock.

    def _read(self) -> list[bytes]:
        try:
            data = self.path.read_bytes()
        except FileNotFoundError:
            return []
        if len(data) % 65:
            raise LogError("log file is damaged: it does not end on a complete entry")
        digests = []
        for start in range(0, len(data), 65):
            line = data[start:start + 65]
            if not _LINE.fullmatch(line):
                raise LogError(f"log file is damaged at entry {start // 65}")
            digests.append(bytes.fromhex(line[:64].decode()))
        return digests

    def digests(self) -> list[bytes]:
        with self._locked(exclusive=False):
            return self._read()

    def append(self, digest: bytes) -> dict:
        """Add a manifest digest once; a repeat returns the existing index."""
        if not isinstance(digest, bytes) or len(digest) != merkle.HASH_SIZE:
            raise LogError("a log entry is a 32-byte SHA-256 digest")
        with self._locked(exclusive=True):
            digests = self._read()
            if digest in digests:
                return {"index": digests.index(digest), "tree_size": len(digests), "duplicate": True}
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
            try:
                os.write(fd, digest.hex().encode() + b"\n")
                os.fsync(fd)
            finally:
                os.close(fd)
            return {"index": len(digests), "tree_size": len(digests) + 1, "duplicate": False}

    @staticmethod
    def _size(digests: list[bytes], tree_size: int | None) -> int:
        size = len(digests) if tree_size is None else tree_size
        if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= len(digests):
            raise LogError(f"tree size must be between 0 and {len(digests)}")
        return size

    def root(self, tree_size: int | None = None) -> tuple[int, bytes]:
        digests = self.digests()
        size = self._size(digests, tree_size)
        return size, merkle.root([merkle.leaf_hash(d) for d in digests[:size]])

    def inclusion_proof(self, digest: bytes, tree_size: int | None = None) -> dict:
        digests = self.digests()
        size = self._size(digests, tree_size)
        if digest not in digests[:size]:
            raise LogError("this manifest digest is not in the log at that tree size")
        index = digests.index(digest)
        path = merkle.inclusion_proof([merkle.leaf_hash(d) for d in digests[:size]], index)
        return {"format": INCLUSION_FORMAT, "version": 1, "manifest_sha256": digest.hex(),
                "leaf_index": index, "tree_size": size, "inclusion_path": [h.hex() for h in path]}

    def consistency_proof(self, first_size: int, second_size: int | None = None) -> dict:
        digests = self.digests()
        second = self._size(digests, second_size)
        if isinstance(first_size, bool) or not isinstance(first_size, int) or not 0 < first_size <= second:
            raise LogError(f"the earlier size must be between 1 and {second}")
        path = merkle.consistency_proof([merkle.leaf_hash(d) for d in digests[:second]], first_size)
        return {"format": CONSISTENCY_FORMAT, "version": 1, "first_size": first_size,
                "second_size": second, "consistency_path": [h.hex() for h in path]}


def _hashes(values: object) -> list[bytes]:
    if not isinstance(values, list) or len(values) > 64:
        raise ValueError("a proof is a list of at most 64 hashes")
    hashes = []
    for value in values:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("proof hashes are 64 lowercase hex characters")
        hashes.append(bytes.fromhex(value))
    return hashes


def _count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2 ** 64:
        raise ValueError("expected an unsigned 64-bit integer")
    return value


def inclusion_issues(proof: object, manifest_digest: bytes, head: dict) -> list[str]:
    """Check an inclusion proof against an already-verified tree head."""
    try:
        if not isinstance(proof, dict) or set(proof) != {"format", "version", "manifest_sha256", "leaf_index",
                                                          "tree_size", "inclusion_path"} \
                or proof["format"] != INCLUSION_FORMAT or proof["version"] != 1:
            raise ValueError("unsupported proof")
        path, index, size = _hashes(proof["inclusion_path"]), _count(proof["leaf_index"]), _count(proof["tree_size"])
    except (ValueError, TypeError):
        return ["invalid_proof"]
    issues = []
    if proof["manifest_sha256"] != manifest_digest.hex():
        issues.append("proof_is_for_another_manifest")
    if size != head["tree_size"]:
        issues.append("proof_tree_size_differs_from_tree_head")
    if not merkle.verify_inclusion(merkle.leaf_hash(manifest_digest), index, size, path, bytes.fromhex(head["root_hash"])):
        issues.append("inclusion_proof_failed")
    return issues


def consistency_issues(proof: object, old_head: dict, new_head: dict) -> list[str]:
    """Check that new_head extends old_head; both heads already verified."""
    try:
        if not isinstance(proof, dict) or set(proof) != {"format", "version", "first_size", "second_size",
                                                          "consistency_path"} \
                or proof["format"] != CONSISTENCY_FORMAT or proof["version"] != 1:
            raise ValueError("unsupported proof")
        path, first, second = _hashes(proof["consistency_path"]), _count(proof["first_size"]), _count(proof["second_size"])
    except (ValueError, TypeError):
        return ["invalid_proof"]
    if (first, second) != (old_head["tree_size"], new_head["tree_size"]):
        return ["proof_sizes_differ_from_tree_heads"]
    if not merkle.verify_consistency(first, second, bytes.fromhex(old_head["root_hash"]),
                                     bytes.fromhex(new_head["root_hash"]), path):
        return ["consistency_proof_failed"]
    return []
