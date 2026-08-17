from __future__ import annotations
import importlib.util
from pathlib import Path
import pytest
pytestmark=pytest.mark.unit
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'scripts/architecture/rag_live_parity_probe.py'
def mod():
 s=importlib.util.spec_from_file_location('ragprobe',P); assert s and s.loader; m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

def test_live_probe_is_read_only_and_dimension_bound(monkeypatch):
 m=mod()
 monkeypatch.setattr(m,'_get',lambda *_a,**_k:{'result':{'config':{'params':{'vectors':{'size':3}}}}})
 def post(url,payload,headers=None):
  if '/api/embeddings' in url:return {'embedding':[1,2,3]}
  if '/points/search' in url:return {'result':[{'payload':{'page_content':'same text'}}]}
  return {'annotations':[{'text':'same text'}]}
 monkeypatch.setattr(m,'_post',post)
 r=m.run_probe(tenant_id='t1',queries=['water'],final_k=5,qdrant_url='http://q',collection='c',ollama_url='http://o',model='m',retrieval_url='http://r',subject_sha='a'*40,contract_sha256='b'*64)
 assert r['min_jaccard']==1.0 and r['read_only'] is True and r['authority_promotion'] is False

def test_live_probe_rejects_vector_dimension_mismatch(monkeypatch):
 m=mod(); monkeypatch.setattr(m,'_get',lambda *_a,**_k:{'result':{'config':{'params':{'vectors':{'size':4}}}}}); monkeypatch.setattr(m,'_post',lambda *_a,**_k:{'embedding':[1,2,3]})
 with pytest.raises(ValueError,match='dimension mismatch'):
  m.run_probe(tenant_id='t',queries=['q'],final_k=5,qdrant_url='q',collection='c',ollama_url='o',model='m',retrieval_url='r',subject_sha='a'*40,contract_sha256='b'*64)
