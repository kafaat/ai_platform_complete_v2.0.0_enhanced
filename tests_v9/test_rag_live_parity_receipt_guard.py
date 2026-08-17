from __future__ import annotations
import hashlib, importlib.util, json
from datetime import UTC, datetime
from pathlib import Path
import pytest
pytestmark=pytest.mark.unit
ROOT=Path(__file__).resolve().parents[1]; P=ROOT/'scripts/architecture/rag_live_parity_receipt_guard.py'
def mod():
 s=importlib.util.spec_from_file_location('ragrg',P); assert s and s.loader; m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def receipt():
 return {'schema':'sahool.rag-live-parity-receipt/v1','observed_at':datetime.now(UTC).isoformat(),'subject_sha':'a'*40,'embedding_contract_sha256':hashlib.sha256((ROOT/'docs/architecture/rag_embedding_contract.json').read_bytes()).hexdigest(),'embedding_provider':'ollama','embedding_model':'nomic-embed-text','collection':'sahool_agri_kb','vector_size':768,'query_count':5,'min_jaccard':0.7,'mean_jaccard':0.85,'read_only':True,'authority_promotion':False}
def test_receipt_acceptance_contract_passes_good_bound_receipt(): assert mod().findings(receipt(),'a'*40)==[]
def test_receipt_rejects_wrong_subject(): assert 'receipt subject SHA mismatch' in mod().findings(receipt(),'b'*40)
def test_receipt_rejects_weak_overlap(): r=receipt(); r['min_jaccard']=0.2; assert any('minimum jaccard' in x for x in mod().findings(r,'a'*40))
def test_receipt_never_accepts_promoting_probe(): r=receipt(); r['authority_promotion']=True; assert any('non-promoting' in x for x in mod().findings(r,'a'*40))
