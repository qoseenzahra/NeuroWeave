"""Build compact Skill entry documents without rewriting upstream/audited manuals.

SKILL.md is a provenance-preserving reference; OVERVIEW.md is the context entry.
Method contracts live in the independent methods directory and are served on demand by SkillCatalog.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'bakend'))
from app.skill_loader import SkillLoader
from app.capability_registry import CapabilityRegistry


def build():
    loader = SkillLoader(ROOT/'skills', ROOT/'bakend/resources/neuroclaw_skill_summaries.json')
    registry = CapabilityRegistry(ROOT/'skills').definitions
    registry.load()
    outputs = {}
    for skill in loader.load_all():
        structure=registry.skills[skill.name]
        methods={r['method_ref'] for r in structure['method_refs']}
        pipelines={r['pipeline_ref'] for r in structure['pipeline_refs']}
        rules='\n'.join('- '+rule for rule in structure['selection_rules'])
        guidance='\n\n'.join('## '+title+'\n\n'+'\n'.join('- '+item for item in structure.get(key, [])) for title,key in [('适用情况','applicability'),('限制','limitations')])
        content=(f'# {skill.display_name}\n\n{structure["description"]}\n\n'
            f'## 统筹目录\n\n{len(methods)} 个独立方法，{len(pipelines)} 个组合流程，'
            f'{len(structure["planning_capabilities"])} 个尚未接入的规划能力。\n\n'
            'Skill 负责选择、解释方法与复用已有输入。执行契约唯一保存在 methods/；'
            '组合连接保存在 pipelines/；本 Skill 的方法角色见 skill.json 的 method_refs。\n\n'
            '先 list_skill_methods（kind=method/pipeline/capability）定位，再 read_skill_method '
            '或 read_skill_pipeline 按需查看参数和端口，不将全部方法手册塞入上下文。\n\n'
            f'## 选择规则\n\n{rules}\n\n{guidance}\n\n'
            '只调用登记的现有软件、库或原始脚本；环境可用不代表已完成真实数据验证。'
            '实际运行须检查输入、节点、参数，并通过用户确认后的 Runner。\n\n'
            '## 背景参考\n\n[SKILL.md](SKILL.md) 保留原始背景；'
            'read_skill_reference 分页读取。原文示例不自动取得执行权限。\n')
        if not (skill.path/'SKILL.md').is_file():
            content=content[:content.index('## 背景参考')].rstrip()+'\n'
        outputs[skill.path/'OVERVIEW.md']=content
    return outputs


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    outputs = build()
    for path, content in outputs.items():
        if args.check:
            if not path.is_file() or path.read_text(encoding='utf-8') != content:
                raise SystemExit('Stale Skill overview: '+str(path))
        else:
            path.write_text(content, encoding='utf-8')
    print(f'{len(outputs)} layered Skill overviews verified' if args.check else f'{len(outputs)} layered Skill overviews generated')
