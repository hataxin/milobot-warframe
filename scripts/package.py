"""Build a reviewable plugin ZIP using an explicit source-file allowlist."""

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = (
    "plugin.py",
    "__init__.py",
    "_manifest.json",
    "README.md",
    "NOTICE.md",
    "CHANGELOG.md",
    "ASSET-SOURCES.md",
    "LICENSE",
    "VALIDATION.md",
    "requirements.txt",
    "requirements.lock.txt",
    "pyproject.toml",
    "uv.lock",
)
ASSET_FILES = (
    "bg-candidates.png",
    "bg-cycles.png",
    "bg-table.png",
    "motif.png",
    "ribbon.png",
    "topic.png",
    "triangle.png",
    "MiSans-Regular.ttf",
    "MiSans-Demibold.ttf",
    "MiSans-NOTICE.txt",
)


def main() -> None:
    """Package code, tests, lockfiles and documentation, never user data or caches."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    destination = parser.parse_args().output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = [ROOT / name for name in ROOT_FILES]
    files.extend(ROOT / "assets" / name for name in ASSET_FILES)
    for folder in ("milo_core", "tests", "scripts"):
        files.extend(sorted((ROOT / folder).glob("*.py")))
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, "milobot_warframe/" + path.relative_to(ROOT).as_posix())
    with ZipFile(destination) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("milobot_warframe/_manifest.json"))
        assert manifest["id"] == "local.milobot-warframe"
    print(f"Packaged {len(files)} files: {destination} ({destination.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
