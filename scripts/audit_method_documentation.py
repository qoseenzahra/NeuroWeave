"""Report exact registered coverage; never equate environment readiness with completeness."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'bakend'))
from app.capability_registry import CapabilityRegistry


def report():
    methods=CapabilityRegistry(ROOT/'skills').all_methods()
    executable=[m for m in methods if m.execution_mode=='runner']
    missing=[dict(skill_id=m.skill_id,capability=m.capability,method_id=m.method_id,runner_id=m.runner_id,
                  parameters=[p.id for p in m.parameters if not p.description.strip()])
             for m in executable if any(not p.description.strip() for p in m.parameters)]
    command_coverage=[]
    for path in sorted((ROOT/'skills').glob('*/commands/*.json')):
        c=json.loads(path.read_text(encoding='utf-8'))['command_contract']
        command_coverage.append(dict(command=c['command'],version=c['version'],total_options=c['total_options'],
                                     exposed_options=len(c['options']),omitted_options=c['omitted_options']))
    return dict(skill_overviews=len(list((ROOT/'skills').glob('*/OVERVIEW.md'))),registered_methods=len(methods),
        runner_methods=len(executable),registered_parameters=sum(len(m.parameters) for m in executable),
        undocumented_parameters=sum(len(item['parameters']) for item in missing),
        methods_needing_parameter_documentation=missing,command_coverage=command_coverage,
        scope='Counts cover registered contracts, not every command/parameter in installed software. Runtime and real-data validation are separate.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
    payload=report()
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in payload.items() if k not in {'methods_needing_parameter_documentation','command_coverage'}},ensure_ascii=False))
