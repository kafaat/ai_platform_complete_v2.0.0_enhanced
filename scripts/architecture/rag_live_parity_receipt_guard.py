#!/usr/bin/env python3
"""Validate a live RAG parity receipt. Read-only; never promotes authority."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
STATE=ROOT/'docs/architecture/rag_authority_convergence.json'
CONTRACT=ROOT/'docs/architecture/rag_embedding_contract.json'
def findings(receipt:dict, subject_sha:str)->list[str]:
 s=json.loads(STATE.read_text(encoding='utf-8')); p=s.get('parity_acceptance') or {}; out=[]
 if receipt.get('schema')!=p.get('receipt_schema'): out.append('receipt schema mismatch')
 if receipt.get('subject_sha')!=subject_sha: out.append('receipt subject SHA mismatch')
 if receipt.get('embedding_contract_sha256')!=hashlib.sha256(CONTRACT.read_bytes()).hexdigest(): out.append('embedding contract digest mismatch')
 if receipt.get('embedding_provider')!='ollama' or receipt.get('embedding_model')!='nomic-embed-text': out.append('embedding identity mismatch')
 if receipt.get('collection')!='sahool_agri_kb': out.append('collection mismatch')
 if receipt.get('read_only') is not True or receipt.get('authority_promotion') is not False: out.append('receipt must be read-only/non-promoting')
 if int(receipt.get('query_count',0))<int(p.get('min_queries',5)): out.append('insufficient parity queries')
 if float(receipt.get('min_jaccard',0))<float(p.get('min_jaccard',0.6)): out.append('minimum jaccard below threshold')
 if float(receipt.get('mean_jaccard',0))<float(p.get('min_mean_jaccard',0.8)): out.append('mean jaccard below threshold')
 try: datetime.fromisoformat(str(receipt.get('observed_at')).replace('Z','+00:00'))
 except Exception: out.append('invalid observed_at')
 if not isinstance(receipt.get('vector_size'),int) or receipt.get('vector_size',0)<=0: out.append('invalid live vector size')
 return out
def main()->int:
 ap=argparse.ArgumentParser(); ap.add_argument('--receipt',required=True); ap.add_argument('--subject-sha',required=True); a=ap.parse_args()
 if len(a.subject_sha)!=40: print('rag_live_parity_receipt_fail invalid subject sha'); return 1
 r=json.loads(Path(a.receipt).read_text(encoding='utf-8')); f=findings(r,a.subject_sha.lower())
 if f:
  [print('rag_live_parity_receipt_fail',x) for x in f]; return 1
 print(f"rag_live_parity_receipt_ok queries={r['query_count']} min={r['min_jaccard']} mean={r['mean_jaccard']} vector_size={r['vector_size']}"); return 0
if __name__=='__main__': raise SystemExit(main())
