#!/usr/bin/env python3
"""Build a versioned frontend before activation; retain and restore its previous image."""
from pathlib import Path
import argparse
import datetime as dt
import json
import re
import subprocess
import time
import urllib.request

PRODUCTION = Path("/home/hipeson/LocalFlow")
RELEASES = Path("/home/hipeson/.cache/neuroweave/releases")
BACKUPS = Path("/home/hipeson/.cache/neuroweave/frontend-backups")


def require(condition,message):
    if not condition:
        raise RuntimeError(message)


def command(argv,*,cwd=PRODUCTION):
    return subprocess.check_output(argv,cwd=cwd,text=True,timeout=180).strip()


def switch(image):
    require(re.fullmatch(r"sha256:[0-9a-f]{64}",image),"Expected an immutable Docker image ID.")
    command(["docker","tag",image,"localflow-frontend:latest"])
    command(["docker","compose","up","-d","--no-build","--no-deps","--wait","--wait-timeout","120","frontend"])
    command(["docker","compose","exec","-T","gateway","nginx","-s","reload"])


def health(revision=None):
    last_error = None
    for _ in range(15):
        try:
            with urllib.request.urlopen("http://192.10.84.6:3000/",timeout=5) as response:
                require(response.status == 200,"Frontend health failed.")
            with urllib.request.urlopen("http://192.10.84.6:3000/api/health?include_runtime=false",timeout=5) as response:
                payload = json.load(response)
                require(payload.get("status") == "ok","API health failed.")
                if revision:
                    require(payload.get("release",{}).get("backend_revision") == revision,"Backend revision differs.")
            return
        except Exception as error:
            last_error = error
            time.sleep(1)
    raise RuntimeError("Release health check failed") from last_error


def deploy(source,revision,build_only,activate_only):
    require(re.fullmatch("[0-9a-f]{40}",revision),"Expected a full Git revision.")
    require(source == RELEASES / revision and source.resolve() == source,"Unexpected source directory.")
    require((source / "revision.txt").read_text().strip() == revision,"Release marker mismatch.")
    BACKUPS.mkdir(parents=True,exist_ok=True,mode=0o700)
    require(BACKUPS.resolve() == BACKUPS,"Backup directory is redirected.")
    backup = BACKUPS / (revision+"-"+dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    backup.mkdir(mode=0o700)
    tag = "localflow-frontend:"+revision
    if not activate_only:
        print(json.dumps({"phase":"building","log":str(backup/"build.log")}),flush=True)
        with (backup / "build.log").open("w") as stream:
            result = subprocess.run(["docker","build","--build-arg","NEUROWEAVE_REVISION="+revision,
                "-f","frontend/Dockerfile","-t",tag,"."],cwd=source,stdout=stream,stderr=subprocess.STDOUT,timeout=1800)
        require(result.returncode == 0,"Build failed; see retained build.log. Running frontend is unchanged.")
    image = command(["docker","image","inspect",tag,"--format","{{.Id}}"])
    label = command(["docker","image","inspect",tag,"--format",'{{index .Config.Labels "org.opencontainers.image.revision"}}'])
    require(label == revision,"Built image revision label differs.")
    if build_only:
        print(json.dumps({"phase":"built","revision":revision,"image":image}),flush=True)
        return
    previous = command(["docker","inspect","--format","{{.Image}}","localflow-frontend-1"])
    manifest = {"revision":revision,"previous_image":previous,"image":image}
    (backup / "rollback.json").write_text(json.dumps(manifest,indent=2))
    # The matching backend must be ready before exposing new client contracts.
    health(revision)
    print(json.dumps({"phase":"activating","backup":str(backup)}),flush=True)
    try:
        switch(image)
        health(revision)
        require(command(["docker","inspect","--format","{{.Image}}","localflow-frontend-1"]) == image,"Wrong running image.")
    except Exception:
        switch(previous)
        health()
        raise
    (backup / "verified.json").write_text(json.dumps(manifest,indent=2))
    print(json.dumps({"phase":"verified",**manifest,"backup":str(backup)}),flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path)
    parser.add_argument("--revision")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--build-only",action="store_true")
    group.add_argument("--activate-only",action="store_true")
    parser.add_argument("--rollback",type=Path)
    args = parser.parse_args()
    if args.rollback:
        require(args.rollback.parent == BACKUPS and args.rollback.resolve() == args.rollback,"Invalid rollback directory.")
        manifest = json.loads((args.rollback / "rollback.json").read_text())
        switch(manifest["previous_image"])
        health()
        print("Previous frontend image restored.")
    else:
        require(args.source is not None and args.revision is not None,"--source and --revision required.")
        deploy(args.source,args.revision,args.build_only,args.activate_only)


if __name__ == "__main__":
    main()
