#!/usr/bin/env python3
"""Inventory and freeze unversioned business routes.

New business endpoints should use /v1 unless explicitly classified as health,
metrics, internal S2S, GraphQL facade, or legacy_unversioned in the generated
allowlist. This avoids breaking existing clients while preventing drift.
"""
from __future__ import annotations
import ast, csv, json, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
INV=ROOT/'api_versioning_inventory.generated.json'
CSV=ROOT/'api_versioning_inventory.csv'
ALLOW=ROOT/'api_versioning_legacy_allowlist.generated.json'
METHODS={'get','post','put','patch','delete','options','head'}
INFRA_PREFIXES=('/health','/healthz','/readyz','/metrics','/contract','/capabilities','/')


def _service_for(path: Path)->str:
    parts=path.relative_to(ROOT).parts
    if parts[0]=='services': return parts[1]
    if parts[0]=='bots': return f'bots/{parts[1]}'
    return parts[0]


def _routes(path: Path):
    try: tree=ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    except SyntaxError: return []
    rows=[]
    for node in ast.walk(tree):
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)): continue
        for dec in node.decorator_list:
            if isinstance(dec,ast.Call) and isinstance(dec.func,ast.Attribute) and dec.func.attr in METHODS:
                if dec.args and isinstance(dec.args[0],ast.Constant) and isinstance(dec.args[0].value,str):
                    rows.append({'service':_service_for(path),'file':path.relative_to(ROOT).as_posix(),'line':getattr(node,'lineno',0),'method':dec.func.attr.upper(),'path':dec.args[0].value,'handler':node.name})
    return rows


def _classify(path: str)->str:
    if path.startswith('/v1/') or path == '/v1': return 'versioned'
    if path.startswith('/internal/'): return 'internal_s2s'
    if path == '/graphql': return 'graphql_facade'
    if path.startswith('/health') or path in {'/readyz','/metrics','/contract','/capabilities','/'}: return 'infra'
    return 'legacy_unversioned_business'


def collect():
    paths=list(ROOT.glob('services/**/*.py'))+list(ROOT.glob('bots/**/*.py'))
    rows=[]
    for p in sorted(paths):
        if '__pycache__' in p.parts or '.venv' in p.parts: continue
        rows.extend(_routes(p))
    for r in rows: r['classification']=_classify(r['path'])
    return rows


def write(rows):
    INV.write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    with CSV.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['service','file','line','method','path','handler','classification']); w.writeheader(); w.writerows(rows)
    legacy=sorted({f"{r['method']} {r['path']}" for r in rows if r['classification']=='legacy_unversioned_business'})
    ALLOW.write_text(json.dumps({'legacy_unversioned_business_routes':legacy},indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


def main():
    check='--check' in sys.argv
    rows=collect()
    before=INV.read_text(encoding='utf-8') if INV.exists() else None
    before_csv=CSV.read_text(encoding='utf-8') if CSV.exists() else None
    before_allow=ALLOW.read_text(encoding='utf-8') if ALLOW.exists() else None
    write(rows)
    if check and before is not None:
        if before!=INV.read_text(encoding='utf-8') or before_csv!=CSV.read_text(encoding='utf-8') or before_allow!=ALLOW.read_text(encoding='utf-8'):
            raise SystemExit('api versioning inventory drift; rerun scripts/ci/api_versioning_policy_guard.py and review unversioned allowlist')
        print('api_versioning_policy_check_ok')
    else:
        counts={}
        for r in rows: counts[r['classification']]=counts.get(r['classification'],0)+1
        print('api_versioning_inventory_written',counts)
    return 0
if __name__=='__main__': raise SystemExit(main())
