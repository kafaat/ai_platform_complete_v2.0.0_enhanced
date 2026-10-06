#!/usr/bin/env bash
# مصفوفةُ التحقّق لـv14: تُعيد إنتاج السجلّات في هذا المجلّد على أيّ نسخة.
#
#   sudo bash tools/tts_bakeoff/results/v14/run_matrix.sh [مجلّد_الناتج]
#
# الجذرُ مشتقٌّ من موضع السكربت (لا مسارَ جلسةٍ مؤقّت)، والناتجُ في مجلّدٍ منفصل (افتراضيّاً مؤقّت) فلا تُكتب
# سجلّاتُ الحزمة فوق نفسها. يحتاج root (namespaces · cgroup v1 · bwrap)؛ وحالةُ فضاء PID والمضيف المقيَّد
# تُسجَّل BLOCKED حيث لا يسمح المضيف. الخطوة 0 تكتب ``fixtures/comparable_result.json`` من تشغيلٍ bwrap حقيقيّ.
# حالةُ ASR الحقيقيّة (pocketsphinx) تحتاج مفسّراً فيه pocketsphinx: BAKEOFF_PS_PYTHON=<venv_ps>/bin/python، وبدونه BLOCKED.
set -u
PKG=$(cd "$(dirname "$0")/../.." && pwd)
OUT=${1:-$(mktemp -d)}
mkdir -p "$OUT"
cd "$PKG" || exit 1
rm -rf __pycache__

T=$(mktemp -d)
python3 - "$T" > "$OUT/fixture.txt" 2>&1 <<'EOF'
import shutil, sys
from pathlib import Path
sys.path.insert(0, ".")
import selftest
rc, r = selftest.run("ok", Path(sys.argv[1]), coord=("--sandbox", "bwrap"))
print(rc, r.get("performance_comparable"), r["_run_dir"])
assert r.get("performance_comparable") is True
shutil.copy(Path(r["_run_dir"]) / "result.json", "fixtures/comparable_result.json")
EOF
echo "fixture rc=$?" >> "$OUT/rc.txt"

step() {
    name=$1
    shift
    { time timeout 1800 "$@"; } > "$OUT/$name.txt" 2>&1
    echo "$name rc=$?" >> "$OUT/rc.txt"
}
step normal_harness python3 selftest.py
step normal_semantic python3 semantic_selftest.py
step normal_gate python3 gate_selftest.py
step pidns_harness unshare -p -f -- python3 selftest.py
step pidns_semantic unshare -p -f -- python3 semantic_selftest.py
step restricted_harness sh restricted_host_sim.sh python3 selftest.py
step restricted_semantic sh restricted_host_sim.sh python3 semantic_selftest.py
step restricted_gate sh restricted_host_sim.sh python3 gate_selftest.py
step sigign_semantic python3 -c "import signal,subprocess,sys; signal.signal(signal.SIGCHLD, signal.SIG_IGN); sys.exit(subprocess.call([sys.executable,'semantic_selftest.py']))"
step mutations python3 mutations_v14.py .
cat "$OUT/rc.txt"
echo "السجلّات في $OUT"
