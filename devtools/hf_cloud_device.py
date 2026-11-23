"""Start an HF CLI device login and publish only an encrypted human challenge."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit


CHALLENGE = re.compile(
    r"Ask the user to open (\S+) in a browser and enter the code "
    r"([A-Z0-9-]+)\. The code expires in ([0-9]+) seconds\."
)


def write_atomic(path: Path, data: bytes) -> None:
    pending = path.with_suffix(".tmp")
    pending.write_bytes(data)
    pending.replace(path)


def encrypt_challenge(match: re.Match, key: Path) -> bytes:
    url, code, expiry = match.groups()
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc not in {"hf.co", "huggingface.co"}
        or parsed.path != "/oauth/device"
    ):
        raise ValueError("Unrecognized Hugging Face verification address")

    payload = json.dumps({"url": url, "code": code, "expires_at": int(time.time()) + int(expiry)})
    result = subprocess.run(
        [
            "openssl", "pkeyutl", "-encrypt", "-pubin", "-inkey", str(key),
            "-pkeyopt", "rsa_padding_mode:oaep", "-pkeyopt", "rsa_oaep_md:sha256",
            "-pkeyopt", "rsa_mgf1_md:sha256",
        ],
        input=payload.encode(),
        capture_output=True,
        check=True,
    )
    return result.stdout


def authorize(hf: str, state: Path, key: Path) -> bool:
    issued = False
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    env.pop("HF_TOKEN", None)
    with subprocess.Popen(
        [hf, "auth", "login", "--force", "--no-add-to-git-credential", "--format", "agent"],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    ) as cli:
        for line in cli.stdout:
            match = CHALLENGE.search(line)
            if not issued and match:
                try:
                    ciphertext = encrypt_challenge(match, key)
                    write_atomic(state / "challenge.bin", ciphertext)
                except (ValueError, OSError, subprocess.SubprocessError):
                    cli.terminate()
                    cli.wait()
                    return False
                issued = True
        return cli.wait() == 0 and issued


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hf", required=True, help="Path to the official hf CLI executable")
    parser.add_argument("--state", required=True, type=Path, help="New private runner state directory")
    parser.add_argument("--public-key", required=True, type=Path, help="Ephemeral RSA public key in PEM format")
    args = parser.parse_args()
    os.umask(0o077)
    args.state.mkdir()

    try:
        success = authorize(args.hf, args.state, args.public_key)
    except OSError:
        success = False
    write_atomic(args.state / "status", b"authenticated\n" if success else b"failed\n")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
