#!/usr/bin/env bash
set -euo pipefail

# Read-only morning preflight. Does not fetch, refreeze, enroll, or run strategies.
SOURCE_REPO=/opt/yatl/app
PY="$SOURCE_REPO/.venv/bin/python"
[[ -x "$PY" ]] || { echo "VPS_PREFLIGHT_BLOCKED=MISSING_EXISTING_PYTHON" >&2; exit 2; }

"$PY" - <<'PY'
import json, os, pathlib, pwd, shutil, subprocess

def memory():
    values = {}
    try:
        for line in pathlib.Path('/proc/meminfo').read_text().splitlines():
            key, rest = line.split(':', 1)
            if key in {'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'}:
                values[key] = int(rest.split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        return {'status': 'UNAVAILABLE'}
    return values

def git_head(path):
    command = ['git', '-C', path, 'rev-parse', 'HEAD']
    if os.geteuid() == 0:
        command = ['runuser', '-u', 'yatl', '--', *command]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        value = result.stdout.strip()
        if result.returncode == 0 and len(value) == 40:
            return value
    except (OSError, subprocess.TimeoutExpired):
        pass
    return 'UNAVAILABLE_OR_OWNERSHIP_BLOCKED'

research = pathlib.Path('/var/lib/yatl/research')
disk = shutil.disk_usage(research if research.exists() else '/var/lib')
runtime = research / 'mcf-prod-001-runtime-input'
index = runtime / 'runtime-data/index-55c8c476cd5043a652c09f060e2a58b6b1dd9cfd9bffef33e3d8ff7a3a6092c3.json'
distributed = pathlib.Path('/opt/yatl/mcf-distributed')
users = {}
for name in ('yatl', 'yatl-node'):
    try:
        pwd.getpwnam(name)
        users[name] = True
    except KeyError:
        users[name] = False

print(json.dumps({
    'status': 'VPS_PREFLIGHT_COMPLETE_NO_PERFORMANCE',
    'app_git_sha': git_head('/opt/yatl/app'),
    'distributed_git_sha': git_head(str(distributed)) if distributed.exists() else 'NOT_PREPARED',
    'cpu_logical_count': os.cpu_count(),
    'memory_bytes': memory(),
    'research_disk_free_bytes': disk.free,
    'accepted_runtime_index_present': index.is_file(),
    'binding_evidence_root_present': (research / 'mcf-prod-001-binding').is_dir(),
    'setfacl_available': shutil.which('setfacl') is not None,
    'users': users,
    'full_6852_execution_started_by_this_command': False,
    'p10_accessed': False,
}, sort_keys=True, indent=2))
PY
