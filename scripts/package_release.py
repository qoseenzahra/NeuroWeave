#!/usr/bin/env python3
"""Package committed public source with a revision marker and SHA-256 manifest."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import subprocess
import tarfile


def package(output: Path):
    root = Path(__file__).resolve().parents[1]
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root)
    # Ignore untracked scratch, but never label modified tracked files as a release.
    if git("diff", "HEAD", "--name-only").strip():
        raise RuntimeError("Commit reviewed changes before packaging")
    revision = git("rev-parse", "HEAD").decode().strip()
    output.mkdir(parents=True, exist_ok=True)
    target = output / (revision + ".tar.gz")
    if target.exists():
        raise FileExistsError(target)
    source = git("archive", "--format=tar", "HEAD")
    with tarfile.open(fileobj=io.BytesIO(source)) as archive, tarfile.open(target, "w:gz") as release:
        for member in archive:
            if not (member.isfile() or member.isdir()):
                raise RuntimeError("Release contains a link or unsupported file")
            release.addfile(member, archive.extractfile(member) if member.isfile() else None)
        marker = (revision + "\n").encode()
        info = tarfile.TarInfo("revision.txt")
        info.size, info.mode = len(marker), 0o644
        release.addfile(info, io.BytesIO(marker))
    manifest = {"revision": revision, "archive": target.name,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    target.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    package(parser.parse_args().output)
