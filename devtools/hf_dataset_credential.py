"""Check existing runner credentials for access to the official PLE dataset."""

import os
from pathlib import Path
import sys

import httpx
from huggingface_hub import HfApi, set_client_factory
from huggingface_hub.errors import HfHubHTTPError


DATASET = "google/physical-engineerings-last-exam"
ENDPOINT = "https://huggingface.co"


def access_status(token: str) -> str:
    if not token:
        return "absent"
    try:
        HfApi(endpoint=ENDPOINT).auth_check(DATASET, repo_type="dataset", token=token)
    except HfHubHTTPError as exc:
        if getattr(exc.response, "status_code", None) in {401, 403}:
            return "rejected"
        return "unavailable"
    except Exception:
        return "unavailable"
    return "verified"


def main() -> None:
    set_client_factory(lambda: httpx.Client(timeout=10.0))
    secret_status = access_status(os.environ.pop("PLE_HF_CONFIGURED_TOKEN", "").strip())
    try:
        oidc_token = Path(sys.argv[1]).read_text().strip()
    except FileNotFoundError:
        oidc_status = "absent"
    except (OSError, UnicodeError):
        oidc_status = "unavailable"
    else:
        oidc_status = access_status(oidc_token)

    if secret_status == "verified":
        source, state = "secret", "verified"
    elif oidc_status == "verified":
        source, state = "oidc", "verified"
    elif "unavailable" in {secret_status, oidc_status}:
        source, state = "none", "unavailable"
    elif "rejected" in {secret_status, oidc_status}:
        source, state = "none", "rejected"
    else:
        source, state = "none", "absent"
    print(f"source={source}\nstate={state}")


if __name__ == "__main__":
    main()
