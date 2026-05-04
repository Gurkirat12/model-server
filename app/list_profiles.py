#!/usr/bin/env python3
import os
import sys
import yaml
from pathlib import Path

MANIFEST_PATH = os.environ.get(
    "MANIFEST_PATH", "/opt/app/etc/default/model_manifest.yaml"
)

BOLD = "\033[1m"
GREEN = "\033[32m"
RESET = "\033[0m"
DIM = "\033[2m"


def main():
    path = Path(MANIFEST_PATH)
    if not path.exists():
        print(f"ERROR: Manifest not found at {MANIFEST_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(path) as f:
        manifest = yaml.safe_load(f)

    active = os.environ.get("PROFILE", "balanced").strip().lower()
    profiles = manifest.get("profiles", {})

    model_info = manifest.get("model", {})
    print(f"\n{BOLD}Model:{RESET} {model_info.get('display_name', 'Unknown')} "
          f"({model_info.get('parameters', '?')} {model_info.get('quantization', '')})")
    print(f"{BOLD}Active Profile:{RESET} {GREEN}{active}{RESET}\n")
    print(f"{'Profile':<14} {'n_ctx':<8} {'n_batch':<10} {'max_concur':<12} {'max_tokens':<12} Description")
    print("-" * 85)

    for name, cfg in profiles.items():
        marker = f"{GREEN}*{RESET} " if name == active else "  "
        gen = cfg.get("generation", {})
        print(
            f"{marker}{name:<12} "
            f"{cfg.get('n_ctx', '-'):<8} "
            f"{cfg.get('n_batch', '-'):<10} "
            f"{cfg.get('max_concurrent_requests', '-'):<12} "
            f"{gen.get('max_tokens', '-'):<12} "
            f"{DIM}{cfg.get('description', '')}{RESET}"
        )
    print()


if __name__ == "__main__":
    main()
