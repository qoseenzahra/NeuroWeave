"""Build compact Skill entry documents without rewriting upstream/audited manuals.

SKILL.md is a provenance-preserving reference; OVERVIEW.md is the context entry.
Method contracts stay in existing manifests and are served on demand by SkillCatalog.
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
    methods = CapabilityRegistry(ROOT/'skills').all_methods()
    outputs = {}
    for skill in loader.load_all():
        owned = [m for m in methods if m.skill_id == skill.name]
        count = sum(m.execution_mode == 'runner' for m in owned)
        description = skill.summary_zh or skill.description
        content = (f'# {skill.display_name}\n\n{description[:900]}\n\n'
            f'## 方法目录\n\n已登记 {len(owned)} 个方法定义，其中 {count} 个具有 Runner 契约。'
            '这不代表当前环境全部可用，也不代表覆盖软件的全部命令参数。\n\n'
            '使用 list_skill_methods 按用途或命令名分页查找；选定后使用 read_skill_method '
            '读取实际输入、输出、参数及生效条件。每次只读取相关方法。\n\n'
            '## 使用边界\n\n只调用登记的现有软件、库或脚本；原文示例不是可直接执行的授权。'
            '输入可以来自数据集、已有文件或明确的上游输出。已有结果不应重复生成。'
            '具体环境、输入与条件参数须通过检查，运行由用户确认后的 Runner 完成。\n\n'
            '## 详细参考\n\n[原始 Skill 说明](SKILL.md) 保留完整背景与来源。'
            '需要背景或示例时用 read_skill_reference 分页读取，不将全文默认加入上下文。\n')
        outputs[skill.path/'OVERVIEW.md'] = content
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
