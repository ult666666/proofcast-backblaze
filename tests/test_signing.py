"""Ed25519 manifest and tree-head signatures."""

import base64
import copy
import hashlib
import os
import stat

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofcast import signing
from proofcast.signing import SigningError

# The first three lines of the Ed25519 reference test vectors, as vendored by
# pyca/cryptography: vectors/cryptography_vectors/asymmetric/Ed25519/sign.input
# (secret key, public key, message, signature).
ED25519_VECTORS = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]


@pytest.fixture
def keys(tmp_path):
    fingerprint = signing.generate_keypair(tmp_path / "key.pem", tmp_path / "key.pub.pem")
    return signing.load_private_key(tmp_path / "key.pem"), signing.load_public_key(tmp_path / "key.pub.pem"), fingerprint


@pytest.mark.parametrize(("secret", "public", "message", "signature"), ED25519_VECTORS)
def test_reference_ed25519_vectors(secret, public, message, signature):
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(secret))
    assert signing.raw_public_key(key.public_key()).hex() == public
    assert key.sign(bytes.fromhex(message)).hex() == signature


def test_key_files_are_private_exclusive_and_fingerprinted(tmp_path, keys):
    private, public, fingerprint = keys
    assert fingerprint == hashlib.sha256(signing.raw_public_key(public)).hexdigest() == signing.fingerprint(private.public_key())
    assert b"PRIVATE KEY" in (tmp_path / "key.pem").read_bytes() and b"ENCRYPTED" not in (tmp_path / "key.pem").read_bytes()
    if os.name == "posix":
        assert stat.S_IMODE((tmp_path / "key.pem").stat().st_mode) == 0o600
        assert stat.S_IMODE((tmp_path / "key.pub.pem").stat().st_mode) == 0o644
    before = (tmp_path / "key.pem").read_bytes()
    with pytest.raises(SigningError, match="overwrite"):
        signing.generate_keypair(tmp_path / "key.pem", tmp_path / "other.pub.pem")
    assert (tmp_path / "key.pem").read_bytes() == before
    assert not (tmp_path / "other.pub.pem").exists()


def test_keygen_creates_missing_directories_like_the_readme_path(tmp_path):
    # The README writes to ~/.config/proofcast/, which a first run does not have yet.
    folder = tmp_path / "home" / ".config" / "proofcast"
    fingerprint = signing.generate_keypair(folder / "signing-key.pem", folder / "signing-key.pub.pem")
    assert signing.fingerprint(signing.load_private_key(folder / "signing-key.pem").public_key()) == fingerprint
    assert signing.fingerprint(signing.load_public_key(folder / "signing-key.pub.pem")) == fingerprint
    if os.name == "posix":
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700


def test_keygen_never_leaves_a_private_key_without_its_public_key(tmp_path, monkeypatch):
    # A rerun refuses to overwrite, so an orphaned private key could not be repaired.
    real = signing._write_new

    def public_write_fails(path, data, mode):
        if path.name.endswith(".pub.pem"):
            raise OSError("synthetic failure while writing the public key")
        real(path, data, mode)

    monkeypatch.setattr(signing, "_write_new", public_write_fails)
    with pytest.raises(OSError, match="synthetic"):
        signing.generate_keypair(tmp_path / "key.pem", tmp_path / "key.pub.pem")
    assert not (tmp_path / "key.pem").exists()
    monkeypatch.undo()
    signing.generate_keypair(tmp_path / "key.pem", tmp_path / "key.pub.pem")  # The retry succeeds.


def test_public_key_errors_name_the_real_problem(tmp_path, keys):
    with pytest.raises(SigningError, match="key file not found"):
        signing.load_public_key(tmp_path / "missing.pub.pem")
    if os.name == "posix":
        (tmp_path / "link.pub.pem").symlink_to(tmp_path / "key.pub.pem")
        with pytest.raises(SigningError, match="regular file"):
            signing.load_public_key(tmp_path / "link.pub.pem")


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
def test_private_key_readable_by_others_or_linked_is_refused(tmp_path, keys):
    (tmp_path / "key.pem").chmod(0o640)
    with pytest.raises(SigningError, match="chmod 600"):
        signing.load_private_key(tmp_path / "key.pem")
    (tmp_path / "key.pem").chmod(0o600)
    (tmp_path / "link.pem").symlink_to(tmp_path / "key.pem")
    with pytest.raises(SigningError, match="regular file"):
        signing.load_private_key(tmp_path / "link.pem")
    with pytest.raises(SigningError):
        signing.load_public_key(tmp_path / "key.pem")  # A private key is not a public key file.
    (tmp_path / "rsa.pub.pem").write_bytes(b"-----BEGIN PUBLIC KEY-----\nnot a key\n-----END PUBLIC KEY-----\n")
    with pytest.raises(SigningError):
        signing.load_public_key(tmp_path / "rsa.pub.pem")


def test_any_change_to_the_signed_manifest_fails(local_bundle, keys):
    private, public, fingerprint = keys
    data = local_bundle.manifest_path.read_bytes()
    envelope = signing.sign_manifest(data, private)
    assert signing.manifest_signature_issues(data, envelope, public) == []
    assert signing.manifest_signature_issues(data, envelope, fingerprint) == []
    for index in range(0, len(data), max(1, len(data) // 50)):
        changed = bytearray(data)
        changed[index] ^= 0x01
        assert "bad_signature" in signing.manifest_signature_issues(bytes(changed), envelope, public)
    for changed in [data + b" ", data[:-1], b" " + data]:
        assert signing.manifest_signature_issues(changed, envelope, public) == ["manifest_digest_mismatch", "bad_signature"]


def test_only_the_trusted_key_is_accepted(local_bundle, keys, tmp_path):
    private, public, fingerprint = keys
    data = local_bundle.manifest_path.read_bytes()
    other = Ed25519PrivateKey.generate()
    forged = signing.sign_manifest(data, other)  # Valid signature, untrusted signer.
    assert signing.manifest_signature_issues(data, forged, public) == ["untrusted_key"]
    assert signing.manifest_signature_issues(data, forged, fingerprint) == ["untrusted_key"]
    mixed = {**signing.sign_manifest(data, private), "public_key": forged["public_key"]}
    assert signing.manifest_signature_issues(data, mixed, public) == ["invalid_signature_file"]  # Fingerprint no longer matches.
    with pytest.raises(SigningError):
        signing.parse_fingerprint(fingerprint.upper())


@pytest.mark.parametrize("change", [
    lambda e: e.update(signature=base64.b64encode(bytes(64)).decode()),
    lambda e: e.update(manifest_sha256="0" * 64),
])
def test_altered_signature_values_fail(local_bundle, keys, change):
    private, public, _ = keys
    data = local_bundle.manifest_path.read_bytes()
    envelope = signing.sign_manifest(data, private)
    change(envelope)
    assert signing.manifest_signature_issues(data, envelope, public) != []


@pytest.mark.parametrize("change", [
    lambda e: e.update(extra=True), lambda e: e.pop("algorithm"), lambda e: e.update(algorithm="Ed448"),
    lambda e: e.update(version=2), lambda e: e.update(format="other"), lambda e: e.update(signature="!!"),
    lambda e: e.update(signature=e["signature"].rstrip("=")), lambda e: e.update(public_key=base64.b64encode(bytes(31)).decode()),
    lambda e: e.update(key_fingerprint="F" * 64), lambda e: e.update(manifest_sha256=123),
])
def test_malformed_signature_files_are_rejected(local_bundle, keys, change):
    private, public, _ = keys
    data = local_bundle.manifest_path.read_bytes()
    envelope = signing.sign_manifest(data, private)
    change(envelope)
    assert signing.manifest_signature_issues(data, envelope, public) == ["invalid_signature_file"]
    assert signing.manifest_signature_issues(data, "not an object", public) == ["invalid_signature_file"]


def test_tree_heads_use_the_rfc_6962_layout_and_detect_changes(keys):
    private, public, fingerprint = keys
    root = hashlib.sha256(b"synthetic root").digest()
    message = signing.tree_head_message(1_700_000_000_000, 7, root)
    assert len(message) == 50 and message[:2] == b"\x00\x01"
    assert message[2:18] == (1_700_000_000_000).to_bytes(8, "big") + (7).to_bytes(8, "big") and message[18:] == root
    head = signing.sign_tree_head(7, root, private, 1_700_000_000_000)
    assert signing.tree_head_issues(head, public) == [] == signing.tree_head_issues(head, fingerprint)
    for field, value in [("tree_size", 8), ("timestamp", 1_700_000_000_001), ("root_hash", "0" * 64)]:
        assert signing.tree_head_issues({**head, field: value}, public) == ["bad_signature"]
    for field, value in [("tree_size", True), ("tree_size", -1), ("timestamp", 2 ** 64), ("root_hash", "xyz"), ("extra", 1)]:
        assert signing.tree_head_issues({**head, field: value}, public) == ["invalid_tree_head"]
    assert signing.tree_head_issues(head, signing.fingerprint(Ed25519PrivateKey.generate().public_key())) == ["untrusted_key"]


def test_a_manifest_signature_cannot_pass_as_a_tree_head(keys):
    private, public, _ = keys
    root = hashlib.sha256(b"synthetic root").digest()
    head = signing.sign_tree_head(7, root, private, 1)
    # Sign the tree-head bytes as if they were a manifest: the context prefix differs.
    as_manifest = signing.sign_manifest(signing.tree_head_message(1, 7, root), private)
    swapped = copy.deepcopy(head)
    swapped["signature"] = as_manifest["signature"]
    assert signing.tree_head_issues(swapped, public) == ["bad_signature"]
