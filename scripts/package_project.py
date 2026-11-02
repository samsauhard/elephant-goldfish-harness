"""Build an explicit source-only zip; local config, traces, and credentials are excluded."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent
FILES = ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", ".gitignore", "config.example.json")
FOLDERS = ("harness_lab", "tests", "examples", "docs", "scripts", "benchmarks", "vendor")


def main():
    paths = [ROOT / name for name in FILES]
    for folder in FOLDERS:
        paths.extend(path for path in (ROOT / folder).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts
                     and path.suffix not in (".pyc", ".pyo"))
    output = ROOT / "dist" / "elephant-goldfish-harness.zip"
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            archive.write(path, arcname=path.relative_to(ROOT).as_posix())
    print(str(output))
    print(str(len(paths)) + " source files; config.local.json and runs/ excluded")


if __name__ == "__main__":
    main()
