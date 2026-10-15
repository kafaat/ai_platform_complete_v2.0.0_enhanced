"""Run the offline suite and verify two independently generated demo exports."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--require-postgres', action='store_true')
    args = parser.parse_args()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    evidence = ROOT / 'verification' / 'integration'
    evidence.mkdir(parents=True, exist_ok=True)
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    with (evidence / 'tests.log').open('w', encoding='utf-8') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    report = {'tests_run': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors),
              'skipped': [{'test': str(t), 'reason': why} for t, why in result.skipped],
              'require_postgres': args.require_postgres, 'demo_verified': False}
    ok = result.wasSuccessful() and result.testsRun >= 126
    if args.require_postgres and result.skipped:
        ok = False
    if ok:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = []
            for name in ('first', 'second'):
                out = Path(tmp) / name
                run = subprocess.run([sys.executable, '-m', 'sahool_qa', 'demo', '--out', str(out)],
                                     capture_output=True, text=True, cwd=ROOT)
                (evidence / f'{name}.log').write_text(run.stdout + run.stderr, encoding='utf-8')
                if run.returncode:
                    ok = False
                    break
                outputs.append(out / 'qa')
            if len(outputs) == 2:
                manifests = [json.loads((out / 'manifest.json').read_text()) for out in outputs]
                hashes = {}
                for split in ('train', 'val', 'test'):
                    payloads = [(out / f'{split}.jsonl').read_bytes() for out in outputs]
                    ok = ok and payloads[0] == payloads[1] and bool(payloads[0])
                    hashes[split] = hashlib.sha256(payloads[0]).hexdigest()
                for manifest in manifests:
                    ok = ok and not manifest['family_errors'] and not manifest.get('case_errors')
                    ok = ok and manifest['counts']['items_total'] == 538
                report.update(demo_verified=bool(ok), demo_hashes=hashes,
                              counts=manifests[0]['counts'])
                (evidence / 'manifest.json').write_text(json.dumps(manifests[0], ensure_ascii=False, indent=2))
    report['passed'] = bool(ok)
    (evidence / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
