#!/usr/bin/env bash
set -euo pipefail
mkdir -p test-results-smart

if command -v flutter >/dev/null 2>&1; then
  flutter pub get
  flutter analyze
  flutter test --reporter expanded
  exit $?
fi

if command -v dart >/dev/null 2>&1; then
  dart --version
else
  echo "WARN: Flutter/Dart SDK not available; running offline static guards only." | tee test-results-smart/mobile-static.log
fi

python3 - <<'PY'
from pathlib import Path
import re, sys, json
root = Path('.')
issues = []
required = [
  'pubspec.yaml', 'lib/main.dart', 'lib/services/api_service.dart',
  'lib/services/auth_service.dart', 'lib/services/websocket_service.dart',
]
for item in required:
    if not (root/item).exists():
        issues.append({'severity':'critical','file':item,'issue':'required mobile file is missing'})

pub = (root/'pubspec.yaml').read_text(encoding='utf-8')
if 'sdk: \'>=3.6.0 <4.0.0\'' not in pub and 'sdk: ">=3.6.0 <4.0.0"' not in pub:
    issues.append({'severity':'high','file':'pubspec.yaml','issue':'Dart SDK constraint is not pinned to the expected >=3.6.0 <4.0.0 range'})
if 'assets/fonts/' in pub and 'fonts:' in pub:
    issues.append({'severity':'medium','file':'pubspec.yaml','issue':'font assets are declared; clean CI may fail if font binaries are absent'})

for p in root.glob('lib/**/*.dart'):
    s = p.read_text(encoding='utf-8', errors='ignore')
    if re.search(r'print\s*\(', s):
        issues.append({'severity':'low','file':str(p),'issue':'print() found; prefer logger/debugPrint guarded by environment'})
    if 'http://' in s and 'localhost' not in s and '127.0.0.1' not in s:
        issues.append({'severity':'medium','file':str(p),'issue':'plain http URL found in app code'})
    if 'operation_id' in s or 'operationId' in s:
        pass

tests = sorted(str(p) for p in root.glob('test/**/*_test.dart'))
if len(tests) < 4:
    issues.append({'severity':'medium','file':'test/','issue':f'expected at least 4 unit tests, found {len(tests)}'})

summary = {'sdk_mode':'static-only', 'tests_found': tests, 'issues': issues, 'ok': not any(i['severity'] in ('critical','high') for i in issues)}
Path('test-results-smart/mobile-static-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
sys.exit(0 if summary['ok'] else 1)
PY
