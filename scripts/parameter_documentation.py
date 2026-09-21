"""Recover existing argparse help without importing or executing scientific scripts.

Missing semantic documentation remains explicitly missing. No name-based model
guessing, and no change to scientific parameter defaults or invocation behavior.
"""
import ast
from pathlib import Path


def literal_text(node):
    if isinstance(node,ast.Constant) and isinstance(node.value,str):return node.value
    if isinstance(node,ast.JoinedStr):
        # Preserve prose; dynamic values are already represented by typed choices.
        return ''.join(part.value if isinstance(part,ast.Constant) and isinstance(part.value,str)
                       else '[参见原脚本动态取值]' for part in node.values)
    return ''


def enrich(spec,root):
    sources=[spec['script'],*spec.get('required_files',[])]
    if spec.get('original_entrypoint'):sources.insert(0,spec['original_entrypoint'])
    helps={}
    for filename in dict.fromkeys(sources):
        path=Path(root)/filename
        if path.suffix!='.py' or not path.is_file():continue
        tree=ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Attribute) or node.func.attr!='add_argument':continue
            text=next((literal_text(k.value) for k in node.keywords if k.arg=='help'),'')
            if not text:continue
            for arg in node.args:
                flag=literal_text(arg)
                if flag.startswith('-'):helps.setdefault(flag,(text,filename,node.lineno))
    for p in spec['parameters']:
        reference=helps.get(p.get('flag','--'+p['id'].replace('_','-')))
        if reference and not p.get('description'):
            p['description']=reference[0]
            p['usage']=f'参数说明直接来自 {reference[1]}:{reference[2]}。平台仅转发已登记选项；默认值和取值限制见本方法定义。'
