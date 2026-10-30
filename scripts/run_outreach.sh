#!/usr/bin/env sh
set -eu

command_name="${1:-state-report}"
env_file="${ENV_FILE:-.env}"

case "$command_name" in
  healthcheck|dry-run|send-new|sync-replies|state-report) ;;
  *)
    printf '%s\n' 'Usage: run_outreach.sh {healthcheck|dry-run|send-new|sync-replies|state-report} [--sample]' >&2
    exit 2
    ;;
esac

sample_arg="${2:-}"
if [ -n "$sample_arg" ] && { [ "$command_name" != "dry-run" ] || [ "$sample_arg" != "--sample" ]; }; then
  printf '%s\n' '--sample is valid only with dry-run.' >&2
  exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(dirname -- "$script_dir")
python_command="$project_root/.venv/bin/python"
if [ ! -x "$python_command" ]; then
  python_command=python3
fi

cd -- "$project_root"
if [ -n "$sample_arg" ]; then
  exec "$python_command" main.py --env-file "$env_file" "$command_name" --sample
fi
exec "$python_command" main.py --env-file "$env_file" "$command_name"
