#!/usr/bin/env python3
"""Build the firmware and bundle it with the Home Assistant integration.

    scripts/build_firmware.py           build and copy the hex into the integration
    scripts/build_firmware.py --check   fail if the bundled hex is not what the source builds to

Refuses to bundle a changed firmware under the version that is already committed, since Home
Assistant would not offer it to devices that run that version.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = "nanoatmega328new"
BUILT_HEX = ROOT / ".pio" / "build" / ENV / "firmware.hex"
BUNDLED_HEX = ROOT / "custom_components" / "cc1101duino" / "firmware" / f"{ENV}.hex"
VERSION_HEADER = ROOT / "include" / "version.h"
VERSION_REGEX = re.compile(r'#define FIRMWARE_VERSION "([^"]+)"')


def version_of(path: Path) -> str:
    match = VERSION_REGEX.search(path.read_text())
    if match is None:
        sys.exit(f"No FIRMWARE_VERSION in {path}")
    return match.group(1)


def git_show(path: Path) -> str | None:
    result = subprocess.run(
        ["git", "show", f"HEAD:{path.relative_to(ROOT)}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="only check the bundled hex")
    args = parser.parse_args()

    subprocess.run([os.environ.get("PIO", "pio"), "run", "-e", ENV], cwd=ROOT, check=True)
    built = BUILT_HEX.read_text()
    bundled = BUNDLED_HEX.read_text() if BUNDLED_HEX.exists() else None

    if built == bundled:
        print(f"{BUNDLED_HEX.relative_to(ROOT)} is up to date")
        return
    if args.check:
        sys.exit(
            f"{BUNDLED_HEX.relative_to(ROOT)} does not match the firmware source, "
            "run scripts/build_firmware.py"
        )

    version = version_of(VERSION_HEADER)
    committed_hex = git_show(BUNDLED_HEX)
    committed_header = git_show(VERSION_HEADER) or ""
    committed_version = VERSION_REGEX.search(committed_header)
    if (
        committed_hex not in (None, built)
        and committed_version
        and committed_version.group(1) == version
    ):
        sys.exit(
            f"The firmware changed, bump FIRMWARE_VERSION (now {version}) in include/version.h"
        )

    BUNDLED_HEX.parent.mkdir(exist_ok=True)
    BUNDLED_HEX.write_text(built)
    print(f"Bundled firmware version {version} as {BUNDLED_HEX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
