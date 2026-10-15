from pathlib import Path
import shutil,subprocess,tempfile,json
src=Path(__file__).resolve().parents[1];evidence=src/'verification/patch_0.4.1';evidence.mkdir(parents=True,exist_ok=True)
mutations=[
 ('reset_check','sahool_qa/waterbal.py','problem = meter_sequence_problem(meter_records(s, a, b))','problem = None'),
 ('well_coverage','sahool_qa/waterbal.py','    inventory = inventory_for(store, fw.field, rules)','    return None, None\n    inventory = inventory_for(store, fw.field, rules)'),
 ('flow_rounding','sahool_qa/generators/water.py','"flow_m3_h": dv / dh','"flow_m3_h": dv / round(dh, 2)'),
 ('zero_flow','sahool_qa/generators/water.py','            if q == 0:','            if False:'),
 ('mass_conservation','sahool_qa/waterbal.py','eta = min(eta_potential, max(0.0, taw - dr + rain[d] + inet))','eta = eta_potential'),
 ('kc_lineage','sahool_qa/generators/water.py','return [ref for s in case["fw"].of("kc").values()','return [ref for s in []'),
]
results=[]
for name,file,old,new in mutations:
 with tempfile.TemporaryDirectory() as td:
  dst=Path(td)/'qa';shutil.copytree(src,dst,ignore=shutil.ignore_patterns('__pycache__','demo_out','verification'))
  f=dst/file;s=f.read_text();assert old in s,(name,old);f.write_text(s.replace(old,new,1))
  p=subprocess.run(['python','-m','unittest','discover','-s','tests','-p','test_water_041.py','-v'],cwd=dst,text=True,capture_output=True)
  log=p.stdout+p.stderr;(evidence/(name+'.log')).write_text(log)
  results.append({'mutation':name,'exit_code':p.returncode,'caught':p.returncode!=0,'summary':log.strip().splitlines()[-1]})
(evidence/'mutations.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
assert all(r['caught'] for r in results)
