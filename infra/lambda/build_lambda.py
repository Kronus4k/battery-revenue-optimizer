"""
build_lambda.py - build the Lambda deployment zip, reproducibly.

Output: build/lambda/battery-optimizer-ingest.zip (build/ is git-ignored).
Terraform tracks the zip by its sha256 (source_code_hash), so the zip must be
byte-identical when nothing changed. Otherwise every plan would show a
spurious code update. Therefore:
  - dependencies: Linux x86_64 / CPython 3.12 wheels only (the Lambda runtime),
    exact pins, --no-deps (nothing unpinned sneaks in), --no-compile (no .pyc)
  - our code: CRLF -> LF, so Windows checkouts and Linux CI give the same bytes
  - zip: sorted entries, fixed timestamp, fixed permissions
  - left out: bin/ (console-script launchers pip generates for the BUILD
    machine, e.g. Windows .exe files; useless in Lambda), their lines in
    dist-info RECORD files (the .exe hashes change on every build), and
    __pycache__/

Usage (cmd, repo root, .venv active):
    python infra\\lambda\\build_lambda.py
"""
import base64
import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = Path(__file__).with_name("requirements-lambda.txt")
SOURCES = ["lambda_function.py", "ingest.py", "ingest_svk.py"]   # our code, zip root

OUT_DIR = ROOT / "build" / "lambda"
STAGE = OUT_DIR / "package"
ZIP_PATH = OUT_DIR / "battery-optimizer-ingest.zip"

FIXED_TIME = (1980, 1, 1, 0, 0, 0)     # earliest time the zip format allows
SKIP_TOP_LEVEL = {"bin"}


def install_dependencies():
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet",
         "--no-deps", "--no-compile", "--only-binary=:all:",
         "--platform", "manylinux2014_x86_64", "--implementation", "cp",
         "--python-version", "3.12",
         "--target", str(STAGE), "-r", str(REQUIREMENTS)],
        check=True,
    )


def copy_sources():
    for name in SOURCES:
        text = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
        (STAGE / name).write_bytes(text)


def write_zip():
    files = sorted(
        p for p in STAGE.rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts
        and p.relative_to(STAGE).parts[0] not in SKIP_TOP_LEVEL
    )
    ZIP_PATH.unlink(missing_ok=True)
    with zipfile.ZipFile(ZIP_PATH, "w") as zf:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(STAGE).as_posix(), FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16           # rw-r--r--
            zf.writestr(info, entry_bytes(path), compresslevel=9)
    return len(files)


def entry_bytes(path):
    """File content for the zip. A dist-info RECORD lists the bin/ launchers
    with their hashes; the Windows .exe launchers differ on every build, so
    those lines are dropped (bin/ is not shipped, so RECORD stays accurate)."""
    data = path.read_bytes()
    if path.name == "RECORD" and path.parent.name.endswith(".dist-info"):
        lines = data.splitlines(keepends=True)
        data = b"".join(l for l in lines if not l.startswith(b"../../bin/"))
    return data


def main():
    install_dependencies()
    copy_sources()
    count = write_zip()
    digest = hashlib.sha256(ZIP_PATH.read_bytes()).digest()
    print(f"built {ZIP_PATH.relative_to(ROOT)}: {count} files, "
          f"{ZIP_PATH.stat().st_size:,} bytes")
    # Same encoding as Terraform's filebase64sha256(), for comparing with the plan.
    print(f"filebase64sha256 = {base64.b64encode(digest).decode()}")


if __name__ == "__main__":
    main()
