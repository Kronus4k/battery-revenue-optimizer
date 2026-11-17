"""
Guard against names from the LOST AWS account coming back (migration Phase 4, T1).

The old bucket, Lambda and IAM user no longer exist. Any code, config or doc
that still names them would either fail or, worse, quietly point at a bucket
someone else could own. This test scans every TRACKED file (git ls-files, so
it also runs in CI) and fails with the exact file:line of each hit.

The only file allowed to contain the patterns is this test itself.
"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Old names: anywhere in the repo.
OLD_NAMES = re.compile(
    r"project-battery-optimizer-lake|battery-ingest|airflow-local-invoker|read-raw-zone"
)
# Static AWS keys: Airflow now assumes a role, so these files must not mention them.
KEY_VARS = re.compile(r"AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY")
NO_KEY_FILES = {"docker-compose.yml", ".env.example"}

ALLOWED = ("tests/test_no_old_names.py",)


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [f for f in out.splitlines() if not f.startswith(ALLOWED)]


def hits(pattern, files):
    found = []
    for name in files:
        path = ROOT / name
        if not path.is_file():
            continue                      # deleted in the working tree
        text = path.read_bytes().decode("utf-8", errors="ignore")
        for no, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                found.append(f"{name}:{no}: {line.strip()[:100]}")
    return found


def test_no_old_account_names_in_tracked_files():
    found = hits(OLD_NAMES, tracked_files())
    assert not found, "old names still present:\n" + "\n".join(found)


def test_no_static_aws_key_variables_in_compose_or_env_example():
    files = [f for f in tracked_files() if f in NO_KEY_FILES]
    assert files, "docker-compose.yml / .env.example not found"
    found = hits(KEY_VARS, files)
    assert not found, "static key variables still present:\n" + "\n".join(found)
