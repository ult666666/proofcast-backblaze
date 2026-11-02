"""Sign, verify and log ProofCast manifests. Local files only; no network access.

Exit 0 means success or a passing verification, 1 a failed verification or a
bundle that does not verify, 2 invalid arguments or unusable files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from proofcast.signing import (
    SigningError,
    generate_keypair,
    load_private_key,
    load_public_key,
    manifest_signature_issues,
    parse_fingerprint,
    sign_manifest,
    sign_tree_head,
    tree_head_issues,
)
from proofcast.translog import LogError, TransparencyLog, consistency_issues, inclusion_issues
from proofcast.verification import MAX_MANIFEST_BYTES, _FileRefused, _read_file, verify_bundle

MAX_DOCUMENT_BYTES = 64 * 1024
SIGNATURE_SCOPE = (
    "A valid signature shows that the holder of the trusted key signed these exact "
    "manifest bytes, which pin each asset's SHA-256. It does not identify the "
    "holder, date the media, or prove the recorded prompt produced it."
)


def _manifest(path: Path) -> bytes:
    try:
        return _read_file(Path(path).absolute(), MAX_MANIFEST_BYTES)[0]
    except _FileRefused as error:
        raise SigningError(f"cannot read manifest ({error.code}): {path}") from None


def _document(path: Path) -> object:
    """Strict, bounded JSON: no duplicate keys, NaN or Infinity."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("non-finite number")
    try:
        data = _read_file(Path(path).absolute(), MAX_DOCUMENT_BYTES)[0]
        return json.loads(data.decode("utf-8"), object_pairs_hook=unique, parse_constant=constant)
    except _FileRefused as error:
        raise SigningError(f"cannot read {path} ({error.code})") from None
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise SigningError(f"{path} is not valid JSON") from None


def _trusted(args):
    return load_public_key(args.public_key) if args.public_key else parse_fingerprint(args.fingerprint)


def _signature_path(manifest: Path) -> Path:
    name = manifest.name[:-len(".json")] if manifest.name.endswith(".json") else manifest.name
    return manifest.with_name(name + ".sig.json")


def _write_new(path: Path, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)


def _print(document: dict) -> None:
    print(json.dumps(document, indent=2, sort_keys=True))


def _bundle_or_refuse(args, manifest: Path) -> bool:
    report = verify_bundle(manifest, asset_dir=args.asset_dir)
    if not report.verified:
        _print({"refused": "the bundle does not verify", "bundle": report.to_dict()})
    return report.verified


def keygen(args) -> int:
    key_fingerprint = generate_keypair(args.private_key, args.public_key)
    _print({"key_fingerprint": key_fingerprint, "private_key": str(args.private_key),
            "public_key": str(args.public_key),
            "notice": "The private key file is mode 0600 and unencrypted. Keep it out of source control and backups you share."})
    return 0


def sign(args) -> int:
    data = _manifest(args.manifest)
    if not _bundle_or_refuse(args, args.manifest):
        return 1
    envelope = sign_manifest(data, load_private_key(args.private_key))
    output = args.signature or _signature_path(args.manifest)
    _write_new(output, json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    _print({"signature_path": str(output), "key_fingerprint": envelope["key_fingerprint"],
            "manifest_sha256": envelope["manifest_sha256"]})
    return 0


def verify(args) -> int:
    trusted = _trusted(args)
    data = _manifest(args.manifest)
    envelope = _document(args.signature or _signature_path(args.manifest))
    issues = manifest_signature_issues(data, envelope, trusted)
    bundle = verify_bundle(args.manifest, asset_dir=args.asset_dir)
    _print({"verified": not issues and bundle.verified, "signature_verified": not issues,
            "signature_issues": issues, "manifest_sha256": hashlib.sha256(data).hexdigest(),
            "key_fingerprint": envelope.get("key_fingerprint") if isinstance(envelope, dict) else None,
            "bundle": bundle.to_dict(), "scope": SIGNATURE_SCOPE})
    return 0 if not issues and bundle.verified else 1


def log_append(args) -> int:
    data = _manifest(args.manifest)
    if not _bundle_or_refuse(args, args.manifest):
        return 1
    digest = hashlib.sha256(data).digest()
    _print({**TransparencyLog(args.log).append(digest), "manifest_sha256": digest.hex()})
    return 0


def log_head(args) -> int:
    size, root = TransparencyLog(args.log).root(args.tree_size)
    head = sign_tree_head(size, root, load_private_key(args.private_key), int(time.time() * 1000))
    text = json.dumps(head, indent=2, sort_keys=True) + "\n"
    if args.out:
        _write_new(args.out, text)
    print(text, end="")
    return 0


def log_prove(args) -> int:
    digest = hashlib.sha256(_manifest(args.manifest)).digest()
    _print(TransparencyLog(args.log).inclusion_proof(digest, args.tree_size))
    return 0


def log_consistency(args) -> int:
    _print(TransparencyLog(args.log).consistency_proof(args.first, args.second))
    return 0


def log_verify(args) -> int:
    trusted = _trusted(args)
    head = _document(args.tree_head)
    report = {"tree_head_issues": tree_head_issues(head, trusted)}
    usable = not report["tree_head_issues"]
    if args.inclusion:
        if not args.manifest:
            raise SigningError("--inclusion needs --manifest")
        digest = hashlib.sha256(_manifest(args.manifest)).digest()
        proof = _document(args.inclusion)
        report["inclusion_issues"] = inclusion_issues(proof, digest, head) if usable else ["tree_head_not_verified"]
    if args.consistency:
        if not args.old_tree_head:
            raise SigningError("--consistency needs --old-tree-head")
        old = _document(args.old_tree_head)
        report["old_tree_head_issues"] = tree_head_issues(old, trusted)
        proof = _document(args.consistency)
        both = usable and not report["old_tree_head_issues"]
        report["consistency_issues"] = consistency_issues(proof, old, head) if both else ["tree_head_not_verified"]
    if args.log:
        if usable:
            size, root = TransparencyLog(args.log).root(min(head["tree_size"], len(TransparencyLog(args.log).digests())))
            report["log_issues"] = [] if (size, root.hex()) == (head["tree_size"], head["root_hash"]) else ["log_differs_from_tree_head"]
        else:
            report["log_issues"] = ["tree_head_not_verified"]
    verified = not any(report.values())
    if usable:
        report.update(tree_size=head["tree_size"], root_hash=head["root_hash"])
    _print({"verified": verified, **report})
    return 0 if verified else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="proofcast-provenance", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    def trust(command):
        group = command.add_mutually_exclusive_group(required=True)
        group.add_argument("--public-key", type=Path, help="trusted Ed25519 public key (PEM)")
        group.add_argument("--fingerprint", help="trusted key fingerprint: SHA-256 hex of the raw public key")

    command = commands.add_parser("keygen", help="create an Ed25519 key pair; never overwrites")
    command.add_argument("--private-key", type=Path, required=True)
    command.add_argument("--public-key", type=Path, required=True)
    command.set_defaults(handler=keygen)

    command = commands.add_parser("sign", help="sign a manifest whose bundle verifies")
    command.add_argument("manifest", type=Path)
    command.add_argument("--private-key", type=Path, required=True)
    command.add_argument("--signature", type=Path, help="output path (default: MANIFEST.sig.json beside it)")
    command.add_argument("--asset-dir", type=Path)
    command.set_defaults(handler=sign)

    command = commands.add_parser("verify", help="check a signature and the bundle it covers")
    command.add_argument("manifest", type=Path)
    trust(command)
    command.add_argument("--signature", type=Path)
    command.add_argument("--asset-dir", type=Path)
    command.set_defaults(handler=verify)

    command = commands.add_parser("log-append", help="append a verified manifest's SHA-256 to a log")
    command.add_argument("log", type=Path)
    command.add_argument("manifest", type=Path)
    command.add_argument("--asset-dir", type=Path)
    command.set_defaults(handler=log_append)

    command = commands.add_parser("log-head", help="sign the log's current (or an earlier) tree head")
    command.add_argument("log", type=Path)
    command.add_argument("--private-key", type=Path, required=True)
    command.add_argument("--tree-size", type=int)
    command.add_argument("--out", type=Path, help="also write the tree head to this new file")
    command.set_defaults(handler=log_head)

    command = commands.add_parser("log-prove", help="inclusion proof for a manifest")
    command.add_argument("log", type=Path)
    command.add_argument("manifest", type=Path)
    command.add_argument("--tree-size", type=int)
    command.set_defaults(handler=log_prove)

    command = commands.add_parser("log-consistency", help="consistency proof between two tree sizes")
    command.add_argument("log", type=Path)
    command.add_argument("--first", type=int, required=True)
    command.add_argument("--second", type=int)
    command.set_defaults(handler=log_consistency)

    command = commands.add_parser("log-verify", help="check a signed tree head and optional proofs, offline")
    command.add_argument("--tree-head", type=Path, required=True)
    trust(command)
    command.add_argument("--inclusion", type=Path)
    command.add_argument("--manifest", type=Path)
    command.add_argument("--consistency", type=Path)
    command.add_argument("--old-tree-head", type=Path)
    command.add_argument("--log", type=Path, help="also recompute the root from this local log")
    command.set_defaults(handler=log_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (SigningError, LogError, OSError) as error:
        parser.exit(2, f"{parser.prog}: error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
