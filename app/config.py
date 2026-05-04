import os
import sys
import yaml
from pathlib import Path

MANIFEST_PATH = os.environ.get(
    "MANIFEST_PATH", "/opt/app/etc/default/model_manifest.yaml"
)


def load_manifest() -> dict:
    path = Path(MANIFEST_PATH)
    if not path.exists():
        print(f"FATAL: Manifest not found at {MANIFEST_PATH}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r") as f:
        return yaml.safe_load(f)


def resolve_profile(manifest: dict) -> tuple[str, dict]:
    profile = os.environ.get("PROFILE", "balanced").strip().lower()
    valid_profiles = list(manifest["profiles"].keys())

    if profile not in valid_profiles:
        print(
            f"FATAL: PROFILE='{profile}' is not valid.\n"
            f"Valid profiles: {', '.join(valid_profiles)}\n"
            f"Usage: docker run -e PROFILE=<profile> model-server:latest",
            file=sys.stderr,
        )
        sys.exit(1)

    return profile, manifest["profiles"][profile]
