from __future__ import annotations
import copy, importlib.util
from datetime import date
from pathlib import Path
import pytest
pytestmark=pytest.mark.unit
ROOT=Path(__file__).resolve().parents[1]; PATH=ROOT/'scripts/architecture/rag_authority_convergence_guard.py'
def mod(name='ragconv'):
 s=importlib.util.spec_from_file_location(name,PATH); assert s and s.loader; m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

def test_s3_live_tree_is_safe_expand_shadow(): assert mod().findings(today=date(2026,8,16))==[]
def test_s3_embedding_and_ingest_parity_are_now_structurally_closed():
 m=mod('parity'); state=m.load(); reqs=state['cutover_requirements']; assert reqs['embedding_contract_parity'] is True; assert reqs['canonical_ingest_parity'] is True; assert not any('embedding parity claimed' in x or 'canonical ingest parity claimed' in x for x in m.findings(state,today=date(2026,8,16)))
def test_s3_cannot_cutover_before_all_requirements():
 m=mod('cut'); state=m.load(); state['stage']='cutover'; state['authority_state']='CUTOVER_CAPABLE'; assert any('without all cutover requirements' in x for x in m.findings(state,today=date(2026,8,16)))
def test_s3_direct_qdrant_exception_must_be_owned_and_dated():
 m=mod('exc'); state=m.load(); state['direct_qdrant_exception']['owner']=''; assert any('missing owner' in x for x in m.findings(state,today=date(2026,8,16)))
def test_s3_exception_expiry_fails_closed():
 m=mod('exp'); state=m.load(); assert any('expired' in x for x in m.findings(state,today=date(2026,10,1)))
def test_s3_shadow_defaults_off():
 m=mod('off'); state=m.load(); assert state['shadow']['enabled_by_default'] is False
