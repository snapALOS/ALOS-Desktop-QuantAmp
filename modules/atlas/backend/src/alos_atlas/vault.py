"""Encrypted local archive helpers for AlosAtlas."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _vault_key(passphrase: str | None = None) -> str:
    key = passphrase or os.environ.get("REXNEXUS_VAULT_KEY")
    if not key:
        raise ValueError("encrypted archive operations require a passphrase or REXNEXUS_VAULT_KEY")
    if len(key) < 12:
        raise ValueError("vault passphrase must be at least 12 characters")
    return key


def _openssl_available() -> None:
    completed = subprocess.run(
        ["openssl", "version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=5,
    )
    if completed.returncode != 0:
        raise RuntimeError("openssl is required for encrypted AlosAtlas archives")


def encrypt_file(input_path: Path, output_path: Path, passphrase: str | None = None) -> Path:
    _openssl_available()
    key = _vault_key(passphrase)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            "openssl",
            "enc",
            "-aes-256-cbc",
            "-salt",
            "-pbkdf2",
            "-iter",
            "200000",
            "-in",
            str(input_path),
            "-out",
            str(output_path),
            "-pass",
            f"pass:{key}",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"encrypted archive export failed: {completed.stderr.strip()}")
    return output_path


def decrypt_file(input_path: Path, output_path: Path, passphrase: str | None = None) -> Path:
    _openssl_available()
    key = _vault_key(passphrase)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            "openssl",
            "enc",
            "-d",
            "-aes-256-cbc",
            "-pbkdf2",
            "-iter",
            "200000",
            "-in",
            str(input_path),
            "-out",
            str(output_path),
            "-pass",
            f"pass:{key}",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        raise RuntimeError("encrypted archive import failed")
    return output_path

