#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(dirname -- "$script_dir")

PROJECT_ROOT="$project_root" python3 - <<'PY'
import json
import os
import shlex

root = os.environ["PROJECT_ROOT"]
python_path = os.path.join(root, ".venv", "bin", "python")

print("# The commands below are examples only. This script does not execute them.")
for schedule, name, operation in (
    ("0 10 * * 1-5", "fasad-send-new", "send-new"),
    ("15 * * * *", "fasad-sync-replies", "sync-replies"),
):
    argv = json.dumps(
        [python_path, "main.py", "--env-file", ".env", operation],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    print(
        "openclaw automations create "
        f"{shlex.quote(schedule)} --name {shlex.quote(name)} "
        f"--command-argv {shlex.quote(argv)} "
        f"--command-cwd {shlex.quote(root)} "
        "--tz Europe/Moscow --no-deliver"
    )
PY
