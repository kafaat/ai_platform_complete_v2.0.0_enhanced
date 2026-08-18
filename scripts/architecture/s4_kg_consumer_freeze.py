#!/usr/bin/env python3
"""Generate/verify S4 Knowledge Graph runtime consumer freeze.

The freeze records production consumers of the canonical knowledge-graph service and
asserts that no sahool-platform store implementation/import remains.  It is a migration
surface, not a new source of truth.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/architecture/s4_kg_consumer_freeze.json'
LEGACY=ROOT/'services/sahool-platform/core/knowledge_graph/sqlite_graph.py'

def collect():
    consumers=[]
    for p in sorted((ROOT/'services').rglob('*.py')):
        rel=p.relative_to(ROOT).as_posix()
        if '/tests/' in rel or p.name.startswith('test_') or rel.startswith('services/knowledge-graph/'):
            continue
        t=p.read_text(encoding='utf-8',errors='ignore')
        modes=[]
        if 'KNOWLEDGE_GRAPH_URL' in t and '/v1/edges' in t: modes.append('rest_edges')
        if '"knowledge-graph"' in t and ('query_kg_annotations' in t or 'query_edges' in t): modes.append('service_registry')
        if modes: consumers.append({'evidence':rel,'modes':sorted(set(modes))})
    payload=json.dumps(consumers,ensure_ascii=False,separators=(',',':'),sort_keys=True).encode()
    return consumers, hashlib.sha256(payload).hexdigest()

def document():
    consumers,fp=collect()
    return {'schema':'sahool.s4-kg-consumer-freeze/v1','canonical_owner':'knowledge-graph',
            'legacy_platform_store_absent':not LEGACY.exists(),'consumer_count':len(consumers),
            'consumers':consumers,'consumer_fingerprint_sha256':fp,
            'closure_rule':'live subject-bound REST/GraphQL parity PASS + legacy platform store path absent'}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--write',action='store_true'); ap.add_argument('--check',action='store_true'); a=ap.parse_args()
    d=document()
    if a.write:
        OUT.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print('s4_kg_consumer_freeze_written'); return 0
    if a.check:
        if not OUT.exists() or json.loads(OUT.read_text())!=d:
            print('s4_kg_consumer_freeze_drift'); return 1
        if not d['legacy_platform_store_absent'] or not d['consumers']:
            print('s4_kg_consumer_freeze_invalid'); return 1
        print(f"s4_kg_consumer_freeze_ok consumers={d['consumer_count']} fingerprint={d['consumer_fingerprint_sha256']}"); return 0
    print(json.dumps(d,ensure_ascii=False,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
