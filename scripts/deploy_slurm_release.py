#!/usr/bin/env python3
"""Deploy a reviewed NeuroWeave archive as hipeson on mgr; never touches Docker.

The unpacked source must be /home/hipeson/.cache/neuroweave/releases/<revision>
and contain revision.txt with that exact 40-character Git revision. Example:
python3 deploy_slurm_release.py --source PATH --revision COMMIT [--enable-slurm]
Failures retain backups and stop the sequence; no automatic rollback is attempted.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile

PRODUCTION = Path('/home/hipeson/LocalFlow')
RELEASES = Path('/home/hipeson/.cache/neuroweave/releases')
BACKUPS = Path('/home/hipeson/.cache/neuroweave/deploy')
WORKERS = Path('/opt/neuroweave/worker')
DATABASE = PRODUCTION / 'runtime/localflow.db'
ENV_FILE = PRODUCTION / 'deploy/native-backend.env'
PYTHON = Path('/opt/neuroweave/envs/scientific-py311/bin/python')
OUTPUTS = Path('/home/data/neuroweave/runs/hipeson')
SERVICE = 'localflow-backend.service'
CORE_FILES = (
    'bakend/app/main.py', 'bakend/app/local_store.py',
    'bakend/app/execution/slurm_backend.py', 'bakend/app/execution/slurm_worker.py',
    'bakend/resources/neuroclaw_skill_summaries.json', 'bakend/requirements.txt',
    'skills/capability.tree.json', 'frontend/package.json', 'compose.yaml',
)
EXCLUDED_DIRS = {
    '.git', '.conda', '.venv', 'venv', 'env', 'envs', 'node_modules',
    '__pycache__', '.cache', 'cache', '.pytest_cache', '.mypy_cache', '.ruff_cache',
    '.next', '.vinext', '.wrangler', 'dist', 'build', 'runtime', 'outputs',
    'datasets', 'secrets', 'secret', '.secrets', 'credentials', '.ssh', '.aws',
    '.azure', '.kube', '.codex',
}
EXCLUDED_SUFFIXES = {'.db', '.sqlite', '.sqlite3', '.pem', '.key', '.p12', '.pfx',
                     '.pyc', '.pyo', '.log', '.tsbuildinfo'}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def no_symlinks(path, anchor):
    require(path == anchor or anchor in path.parents, 'Path escapes its allowed directory.')
    cursor = path
    while True:
        require(not cursor.is_symlink(), 'Symlinks are not permitted in deployment paths.')
        if cursor == anchor:
            break
        cursor = cursor.parent


def private_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    require(not path.is_symlink() and path.is_dir(), 'Invalid private backup directory.')
    require(path.stat().st_uid == os.geteuid(), 'Backup directory belongs to another account.')
    os.chmod(path, 0o700)


def public_path(relative):
    lower = [part.lower() for part in relative.parts]
    if any(part in EXCLUDED_DIRS for part in lower[:-1]):
        return False
    name = lower[-1]
    # Public Git examples are deployable; live environment files are never copied.
    if ('.env' in name and not name.endswith('.example')) or name in {'revision.txt', 'credentials.json', 'credentials.yml',
                                'credentials.yaml', 'secrets.json', 'secrets.yml',
                                'secrets.yaml', 'id_rsa', 'id_ed25519'}:
        return False
    if name.endswith(('-wal', '-shm', '.db-journal')):
        return False
    return Path(name).suffix not in EXCLUDED_SUFFIXES


def source_files(source):
    result = {}
    for folder, directories, names in os.walk(source, followlinks=False):
        parent = Path(folder)
        retained = []
        for name in sorted(directories):
            if name.lower() not in EXCLUDED_DIRS:
                require(not (parent / name).is_symlink(), 'Source contains a directory symlink.')
                retained.append(name)
        directories[:] = retained
        for name in sorted(names):
            path = parent / name
            relative = path.relative_to(source)
            if not public_path(relative):
                continue
            require(not path.is_symlink() and stat.S_ISREG(path.stat().st_mode),
                    'Source contains a non-regular public file.')
            data = path.read_bytes()
            mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
            result[relative.as_posix()] = (data, mode)
    require(all(name in result and result[name][0] for name in CORE_FILES),
            'Source is incomplete: a required NeuroWeave source file is missing/empty.')
    return result


def env_value(text, name):
    matches = re.findall(r'^\s*' + re.escape(name) + r'\s*=\s*(.*?)\s*$', text, re.M)
    require(len(matches) == 1, 'Expected one explicit ' + name + ' in the existing environment file.')
    parsed = shlex.split(matches[0], comments=True, posix=True)
    require(len(parsed) == 1, 'Unsupported environment value syntax for ' + name + '.')
    return parsed[0]


def updated_env(text, revision, enabled):
    values = {
        'LOCALFLOW_SKILL_PYTHON': str(PYTHON),
        'LOCALFLOW_DIPY_PYTHON': str(PYTHON),
        'LOCALFLOW_SLURM_ENABLED': 'true' if enabled else 'false',
        'LOCALFLOW_SLURM_WORKER_ROOT': str(WORKERS / revision),
        'LOCALFLOW_SLURM_PYTHON': str(PYTHON),
        'LOCALFLOW_SLURM_OUTPUT_ROOT': str(OUTPUTS),
    }
    seen = set()
    output = []
    for line in text.splitlines(keepends=True):
        matched = re.match(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=', line)
        key = matched.group(1) if matched else None
        if key in values:
            require(key not in seen, 'Duplicate runtime setting requires manual review: ' + key)
            seen.add(key)
            output.append(key + '=' + values[key] + '\n')
        else:
            output.append(line)
    if output and not output[-1].endswith('\n'):
        output[-1] += '\n'
    output.extend(key + '=' + value + '\n' for key, value in values.items() if key not in seen)
    return ''.join(output)


def idle_database():
    require(DATABASE.is_file() and DATABASE.resolve() == DATABASE,
            'Existing production database is missing or redirected; refusing to create a database.')
    connection = sqlite3.connect(DATABASE.as_uri() + '?mode=ro', uri=True, timeout=15)
    try:
        connection.execute('PRAGMA query_only=ON')
        rows = connection.execute(
            "SELECT status, COUNT(*) FROM runs WHERE status IN "
            "('queued', 'running', 'cancel_requested') GROUP BY status"
        ).fetchall()
        require(not rows, 'Production has active runs; deployment refused.')
    finally:
        connection.close()


def atomic_write(path, data, mode):
    fd, temporary = tempfile.mkstemp(prefix='.neuroweave-deploy-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def command(argv):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, timeout=90)
    # Do not print captured service output: logs can contain application secrets.
    require(result.returncode == 0,
            'Command failed (exit {}): {}'.format(result.returncode, shlex.join(argv)))
    return result.stdout.strip()


def worker_files(files):
    return {name: content for name, content in files.items()
            if name.startswith(('bakend/app/', 'bakend/resources/', 'skills/', 'models/'))}


def publish_worker(revision, files):
    require(WORKERS.is_dir() and WORKERS.resolve() == WORKERS,
            'Shared worker parent directory must already exist without symlink redirection.')
    target = WORKERS / revision
    no_symlinks(target, WORKERS)
    expected = worker_files(files)
    if target.exists():
        require(target.is_dir(), 'Existing worker version is not a directory.')
        actual = {}
        for directory, directories, names in os.walk(target, followlinks=False):
            parent = Path(directory)
            directories[:] = [name for name in directories if name != '__pycache__']
            require(all(not (parent / name).is_symlink() for name in directories),
                    'Existing worker contains directory symlinks.')
            for name in names:
                if Path(name).suffix in {'.pyc', '.pyo'}:
                    continue
                path = parent / name
                require(path.is_file() and not path.is_symlink(), 'Existing worker contains non-regular files.')
                actual[path.relative_to(target).as_posix()] = path.read_bytes()
        require(set(actual) == set(expected), 'Existing worker file list differs; it will not be overwritten.')
        require(all(actual[name] == data for name, (data, _) in expected.items()),
                'Existing worker bytes differ; it will not be overwritten.')
        return len(expected), False
    staging = Path(tempfile.mkdtemp(prefix='.' + revision + '-', dir=str(WORKERS)))
    # Keep a failed/incomplete staging directory for inspection; never delete a release.
    for name, (data, mode) in expected.items():
        path = staging / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        atomic_write(path, data, mode)
    for directory, _, _ in os.walk(staging):
        os.chmod(directory, 0o755)
    require(not target.exists(), 'Worker target appeared during staging; refusing to overwrite.')
    os.rename(staging, target)
    return len(expected), True


def production_changes(files):
    changes = {}
    for name, (after, mode) in files.items():
        path = PRODUCTION / name
        no_symlinks(path, PRODUCTION)
        require(not path.exists() or path.is_file(), 'A production source-file path is a directory.')
        before = path.read_bytes() if path.exists() else None
        before_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
        if before != after or before_mode != mode:
            changes[name] = {'before': before, 'after': after,
                             'before_mode': before_mode, 'after_mode': mode}
    return changes


def backup_changes(revision, changes, before_env, after_env):
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    backup = BACKUPS / (revision + '-' + stamp)
    backup.mkdir(mode=0o700)
    records = []
    for name, change in changes.items():
        original = change['before']
        if original is not None:
            saved = backup / 'files' / name
            saved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic_write(saved, original, 0o600)
        records.append({'path': name, 'existed': original is not None,
                        'before_sha256': sha(original) if original is not None else None,
                        'after_sha256': sha(change['after']),
                        'before_mode': change['before_mode'], 'after_mode': change['after_mode']})
    atomic_write(backup / 'native-backend.env', before_env, 0o600)
    manifest = {'revision': revision, 'production': str(PRODUCTION), 'files': records,
                'environment': {'path': str(ENV_FILE), 'before_sha256': sha(before_env),
                                'after_sha256': sha(after_env), 'backup_mode': '0600'},
                'database': 'Existing production SQLite was checked read-only and is never copied/reset.',
                'rollback': 'Stop the user backend only after confirming no active runs. Review hashes, '
                            'restore saved original files and environment, then start the backend. '
                            'New files listed with existed=false require explicit review before removal.'}
    atomic_write(backup / 'manifest.json', (json.dumps(manifest, indent=2) + '\n').encode(), 0o600)
    print('Backup: ' + str(backup), flush=True)
    return backup


def validate_context(source, revision):
    import pwd
    require(socket.gethostname().split('.')[0] == 'mgr', 'Run on mgr only.')
    require(os.geteuid() != 0 and pwd.getpwuid(os.geteuid()).pw_name == 'hipeson',
            'Run as hipeson, without sudo.')
    expected = RELEASES / revision
    require(source.is_absolute() and source == expected and source.resolve() == expected,
            '--source must be the exact release directory /home/hipeson/.cache/neuroweave/releases/<revision>.')
    require(source.is_dir(), 'Source directory does not exist.')
    marker = source / 'revision.txt'
    require(marker.is_file() and not marker.is_symlink() and marker.read_text().strip() == revision,
            'Missing or mismatched revision.txt in the trusted source archive.')
    require(PRODUCTION.is_dir() and PRODUCTION.resolve() == PRODUCTION,
            'Production directory is missing or redirected.')
    no_symlinks(ENV_FILE, PRODUCTION)
    require(ENV_FILE.is_file(), 'Existing native-backend.env is required and will never be created from an example.')
    require(PYTHON.is_file() and os.access(PYTHON, os.X_OK), 'Shared scientific Python is unavailable.')
    require(OUTPUTS.is_dir() and os.access(OUTPUTS, os.W_OK | os.X_OK),
            'Shared Slurm output directory must already exist and be writable.')
    require(BACKUPS.parent.resolve() == BACKUPS.parent, 'Backup parent path is redirected.')


def deploy(source, revision, enable_slurm):
    validate_context(source, revision)
    private_dir(BACKUPS)
    import fcntl
    lock_fd = os.open(BACKUPS / '.deployment.lock', os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(lock_fd, 'w') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        before_env = ENV_FILE.read_bytes()
        env_text = before_env.decode('utf-8')
        require(env_value(env_text, 'LOCALFLOW_DATABASE_PATH') == str(DATABASE),
                'Existing environment does not select the expected production database.')
        idle_database()
        files = source_files(source)
        changes = production_changes(files)
        after_env = updated_env(env_text, revision, enable_slurm).encode('utf-8')
        backup = backup_changes(revision, changes, before_env, after_env)
        worker_count, worker_created = publish_worker(revision, files)
        print('Reviewed public files: {}; changed production files: {}; worker files: {} ({}).'.format(
            len(files), len(changes), worker_count, 'created' if worker_created else 'verified'), flush=True)
        # Check both before and after stopping: no code or environment is copied if a new run raced the stop.
        idle_database()
        command(['systemctl', '--user', 'stop', SERVICE])
        try:
            state = command(['systemctl', '--user', 'show', SERVICE, '--property=ActiveState', '--value'])
            require(state == 'inactive', 'Backend did not reach inactive state; deployment stopped.')
            idle_database()
            require(ENV_FILE.read_bytes() == before_env, 'Environment changed during deployment planning.')
            for name, change in changes.items():
                path = PRODUCTION / name
                no_symlinks(path, PRODUCTION)
                current = path.read_bytes() if path.exists() else None
                require(current == change['before'], 'Production files changed during deployment planning.')
            for name, change in changes.items():
                path = PRODUCTION / name
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                atomic_write(path, change['after'], change['after_mode'])
            atomic_write(ENV_FILE, after_env, 0o600)
            command(['systemctl', '--user', 'daemon-reload'])
            command(['systemctl', '--user', 'start', SERVICE])
            command(['systemctl', '--user', 'is-active', '--quiet', SERVICE])
        except Exception:
            print('Deployment stopped. Backups retained at ' + str(backup) +
                  '. Backend may be stopped or partially updated; no automatic rollback was attempted.',
                  file=sys.stderr, flush=True)
            raise
        print('Deployment finished. Slurm enabled: {}. Database and server-only files were preserved.'.format(
            'true' if enable_slurm else 'false'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--enable-slurm', action='store_true',
                        help='Explicitly enable Slurm; disabled by default.')
    args = parser.parse_args()
    require(re.fullmatch(r'[0-9a-f]{40}', args.revision), '--revision must be a lowercase 40-character Git SHA.')
    deploy(args.source, args.revision, args.enable_slurm)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, sqlite3.Error, subprocess.TimeoutExpired) as error:
        # Exceptions contain operational descriptions only; never emit environment contents.
        print('ERROR: ' + str(error), file=sys.stderr)
        sys.exit(1)
