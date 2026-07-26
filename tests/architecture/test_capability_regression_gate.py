import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
s=importlib.util.spec_from_file_location('g',ROOT/'scripts/ci/capability_regression_gate.py');g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
def doc(**kw):
 c={'id':'WX-001','maturity':3,'evidence_level':3,'production_certified':False,'parity_classification':'parity','dependencies':['WX-002']};c.update(kw);return {'capabilities':[c]}
def test_blocks_maturity_and_evidence_regression():
 kinds={x['kind'] for x in g.compare(doc(),doc(maturity=2,evidence_level=2))};assert {'maturity_regression','evidence_level_regression'}<=kinds
def test_blocks_removal_and_dependency_edge_removal():
 assert g.compare(doc(),{'capabilities':[]})[0]['kind']=='removed'
 assert any(x['kind']=='dependency_edges_removed' for x in g.compare(doc(),doc(dependencies=[])))
def test_no_false_regression_on_improvement():
 assert g.compare(doc(),doc(maturity=4,evidence_level=4,parity_classification='leader'))==[]
