"""Produce a public, method-level readiness inventory without patient data or secrets."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'bakend'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--runtime-env',type=Path);args=parser.parse_args()
    if args.runtime_env:
        from dotenv import dotenv_values
        from app.execution.slurm_worker import RUNTIME_ENV_ALLOWLIST
        values=dotenv_values(args.runtime_env)
        for key in RUNTIME_ENV_ALLOWLIST:
            if values.get(key) is not None:os.environ[key]=values[key]
    from app.capability_registry import CapabilityRegistry
    from app.execution.runner_registry import RunnerRegistry
    registry=CapabilityRegistry(ROOT/'skills');runners=RunnerRegistry()
    runtime={entry['runner_id']:entry for entry in runners.public_catalog()}
    records=[]
    for capability in registry.capabilities():
        for method in registry.selectable_methods_for(capability):
            state=runtime.get(method.runner_id)
            status='planning' if method.execution_mode!='runner' else 'ready' if state and state.get('available') else 'missing_runtime'
            reason='需要完成具体流程、数据或外部系统条件；可组合对应已就绪方法。' if status=='planning' else state['reason'] if state else '执行器未注册'
            records.append(dict(capability=capability,skill=method.skill_id,method_id=method.method_id,label=method.label,runner_id=method.runner_id,status=status,reason=reason))
    skills=[]
    for directory in sorted((ROOT/'skills').iterdir()):
        if not (directory/'SKILL.md').is_file():continue
        capability='skill.'+re.sub('[^a-z0-9]+','-',directory.name.lower()).strip('-')
        own=[m for m in records if m['capability']==capability]
        skills.append(dict(skill=directory.name,**dict(Counter(m['status'] for m in own))))
    summary=dict(skills=len(skills),skills_with_ready_methods=sum(s.get('ready',0)>0 for s in skills),
                 registered_runners=len(runtime),ready_runners=sum(bool(s.get('available')) for s in runtime.values()),
                 selectable_methods=len(records),**dict(Counter(m['status'] for m in records)))
    result=dict(generated_at=datetime.now(timezone.utc).isoformat(),summary=summary,registry=registry.stats(),skills=skills,
                missing_runners=[dict(runner_id=s['runner_id'],reason=s['reason']) for s in runtime.values() if not s.get('available')],methods=records)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False));print(json.dumps(result['missing_runners'],ensure_ascii=False))


if __name__=='__main__':main()
