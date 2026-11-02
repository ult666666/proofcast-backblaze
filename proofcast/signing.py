"""Ed25519 signatures over saved manifests and transparency-log tree heads.

A valid manifest signature shows that whoever holds one private key signed
these exact manifest bytes, and the manifest pins each asset's SHA-256. It does
not show who holds the key, when the media was made, or that the recorded
prompt produced it. Trust comes only from a public key or fingerprint that the
verifier already has; the key embedded in a signature file is never trusted on
its own.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# Domain separation: a manifest signature can never be replayed as a tree head
# signature, whose RFC 6962 encoding starts with the bytes 0x00 0x01.
MANIFEST_CONTEXT = b"ProofCast manifest signature v1\x00"
SIGNATURE_FORMAT = "proofcast-manifest-signature"
TREE_HEAD_FORMAT = "proofcast-tree-head"
ALGORITHM = "Ed25519"
MAX_KEY_FILE_BYTES = 4096
_HEX64 = re.compile(r"[0-9a-f]{64}")


class SigningError(ValueError):
    """A key, signature file or tree head is unusable."""


def raw_public_key(public_key: Ed25519PublicKey) -> bytes:
    return public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def fingerprint(public_key: Ed25519PublicKey) -> str:
    """Lowercase hex SHA-256 of the raw 32-byte public key."""
    return hashlib.sha256(raw_public_key(public_key)).hexdigest()


def _write_new(path: Path, data: bytes, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, mode)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, mode)  # The umask can only remove bits; set the exact mode.
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def generate_keypair(private_path: Path, public_path: Path) -> str:
    """Write a new key pair; never overwrite. Returns the public key fingerprint.

    The private key is unencrypted PKCS #8 PEM with mode 0600; the public key is
    SubjectPublicKeyInfo PEM with mode 0644.
    """
    private_path, public_path = Path(private_path), Path(public_path)
    for path in (private_path, public_path):
        if os.path.lexists(path):
            raise SigningError(f"refusing to overwrite existing file: {path}")
    key = Ed25519PrivateKey.generate()
    _write_new(private_path, key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()), 0o600)
    _write_new(public_path, key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo), 0o644)
    return fingerprint(key.public_key())


def _read_key_file(path: Path) -> bytes:
    path = Path(path)
    try:
        details = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        raise SigningError(f"key file not found: {path}") from None
    if not stat.S_ISREG(details.st_mode) or details.st_size > MAX_KEY_FILE_BYTES:
        raise SigningError("a key file must be a small regular file, not a link")
    return path.read_bytes()


def load_private_key(path: Path) -> Ed25519PrivateKey:
    """Load an unencrypted Ed25519 PKCS #8 PEM key that only its owner can read."""
    data = _read_key_file(path)
    if os.name == "posix" and os.stat(path).st_mode & 0o077:
        raise SigningError("private key file must not be accessible by group or others; run chmod 600")
    try:
        key = serialization.load_pem_private_key(data, password=None)
    except (ValueError, TypeError, UnsupportedAlgorithm):
        raise SigningError("not an unencrypted PEM private key") from None
    if not isinstance(key, Ed25519PrivateKey):
        raise SigningError("the private key is not an Ed25519 key")
    return key


def load_public_key(path: Path) -> Ed25519PublicKey:
    try:
        key = serialization.load_pem_public_key(_read_key_file(path))
    except (ValueError, UnsupportedAlgorithm):
        raise SigningError("not a PEM public key") from None
    if not isinstance(key, Ed25519PublicKey):
        raise SigningError("the public key is not an Ed25519 key")
    return key


def parse_fingerprint(text: str) -> str:
    if not isinstance(text, str) or not _HEX64.fullmatch(text):
        raise SigningError("a fingerprint is 64 lowercase hexadecimal characters")
    return text


def _b64(value: object, size: int) -> bytes:
    if not isinstance(value, str):
        raise ValueError("expected base64 text")
    try:
        decoded = base64.b64decode(value, validate=True)
    except binascii.Error:
        raise ValueError("invalid base64") from None
    if len(decoded) != size or base64.b64encode(decoded).decode() != value:
        raise ValueError("unexpected encoded length")
    return decoded


def _signer(document: dict, trusted: Ed25519PublicKey | str) -> Ed25519PublicKey | None:
    """The embedded public key, only if it is the trusted key; otherwise None."""
    embedded = Ed25519PublicKey.from_public_bytes(_b64(document["public_key"], 32))
    if hashlib.sha256(raw_public_key(embedded)).hexdigest() != document["key_fingerprint"]:
        raise ValueError("fingerprint does not match the embedded key")
    if isinstance(trusted, Ed25519PublicKey):
        return embedded if raw_public_key(embedded) == raw_public_key(trusted) else None
    return embedded if document["key_fingerprint"] == trusted else None


def _envelope(private_key: Ed25519PrivateKey, fields: dict, message: bytes) -> dict:
    public_key = private_key.public_key()
    return {
        **fields,
        "algorithm": ALGORITHM,
        "key_fingerprint": fingerprint(public_key),
        "public_key": base64.b64encode(raw_public_key(public_key)).decode(),
        "signature": base64.b64encode(private_key.sign(message)).decode(),
    }


def sign_manifest(manifest_bytes: bytes, private_key: Ed25519PrivateKey) -> dict:
    """Sign MANIFEST_CONTEXT + the exact manifest file bytes."""
    return _envelope(private_key, {
        "format": SIGNATURE_FORMAT,
        "version": 1,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }, MANIFEST_CONTEXT + manifest_bytes)


_SIGNATURE_KEYS = {"format", "version", "algorithm", "key_fingerprint", "public_key", "manifest_sha256", "signature"}


def manifest_signature_issues(manifest_bytes: bytes, envelope: object, trusted: Ed25519PublicKey | str) -> list[str]:
    """Empty when envelope is a valid signature by the trusted key over these bytes."""
    try:
        if (not isinstance(envelope, dict) or set(envelope) != _SIGNATURE_KEYS
                or envelope["format"] != SIGNATURE_FORMAT or envelope["version"] != 1
                or envelope["algorithm"] != ALGORITHM
                or not _HEX64.fullmatch(str(envelope["manifest_sha256"]))
                or not _HEX64.fullmatch(str(envelope["key_fingerprint"]))):
            raise ValueError("unsupported signature file")
        signature = _b64(envelope["signature"], 64)
        signer = _signer(envelope, trusted)
    except (ValueError, TypeError, KeyError):
        return ["invalid_signature_file"]
    if signer is None:
        return ["untrusted_key"]
    issues = []
    if hashlib.sha256(manifest_bytes).hexdigest() != envelope["manifest_sha256"]:
        issues.append("manifest_digest_mismatch")
    try:
        signer.verify(signature, MANIFEST_CONTEXT + manifest_bytes)
    except InvalidSignature:
        issues.append("bad_signature")
    return issues


def tree_head_message(timestamp_ms: int, tree_size: int, root_hash: bytes) -> bytes:
    """RFC 6962 section 3.5 TreeHeadSignature: version v1 (0), signature type
    tree_hash (1), uint64 timestamp in milliseconds, uint64 tree size, root."""
    return struct.pack(">BBQQ", 0, 1, timestamp_ms, tree_size) + root_hash


def sign_tree_head(tree_size: int, root_hash: bytes, private_key: Ed25519PrivateKey, timestamp_ms: int) -> dict:
    return _envelope(private_key, {
        "format": TREE_HEAD_FORMAT,
        "version": 1,
        "tree_size": tree_size,
        "root_hash": root_hash.hex(),
        "timestamp": timestamp_ms,
    }, tree_head_message(timestamp_ms, tree_size, root_hash))


_HEAD_KEYS = {"format", "version", "algorithm", "key_fingerprint", "public_key", "tree_size", "root_hash", "timestamp", "signature"}


def tree_head_issues(head: object, trusted: Ed25519PublicKey | str) -> list[str]:
    """Empty when head is a well-formed tree head signed by the trusted key."""
    try:
        if (not isinstance(head, dict) or set(head) != _HEAD_KEYS or head["format"] != TREE_HEAD_FORMAT
                or head["version"] != 1 or head["algorithm"] != ALGORITHM
                or not _HEX64.fullmatch(str(head["root_hash"])) or not _HEX64.fullmatch(str(head["key_fingerprint"]))):
            raise ValueError("unsupported tree head")
        for name in ("tree_size", "timestamp"):
            if isinstance(head[name], bool) or not isinstance(head[name], int) or not 0 <= head[name] < 2 ** 64:
                raise ValueError("tree size and timestamp are unsigned 64-bit integers")
        signature = _b64(head["signature"], 64)
        signer = _signer(head, trusted)
    except (ValueError, TypeError, KeyError):
        return ["invalid_tree_head"]
    if signer is None:
        return ["untrusted_key"]
    try:
        signer.verify(signature, tree_head_message(head["timestamp"], head["tree_size"], bytes.fromhex(head["root_hash"])))
    except InvalidSignature:
        return ["bad_signature"]
    return []


def dumps(document: dict) -> str:
    return json.dumps(document, indent=2, sort_keys=True) + "\n"
