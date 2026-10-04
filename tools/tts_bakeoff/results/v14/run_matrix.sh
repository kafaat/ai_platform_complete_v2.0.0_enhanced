set -u
S=/tmp/claude-0/-home-user-ai-platform-complete-v2-0-0-enhanced/f31fb6e3-fb2d-56ad-95cb-c3ae66c91adb/scratchpad
F=$S/final_v14; rm -rf $F; mkdir -p $F
cd $S/tts_bakeoff && rm -rf __pycache__
# 0. fixture from final code
T=$(mktemp -d)
python3 -c "
import sys; sys.path.insert(0,'.')
from pathlib import Path
import selftest
rc,r=selftest.run('ok', Path('$T'), coord=('--sandbox','bwrap'))
print(rc, r.get('performance_comparable'), r['_run_dir'])
assert r.get('performance_comparable') is True
import shutil; shutil.copy(Path(r['_run_dir'])/'result.json', 'fixtures/comparable_result.json')
" > $F/fixture.txt 2>&1; echo "fixture rc=$?" >> $F/rc.txt
step() { name=$1; shift; ( time timeout 1800 "$@" ) > $F/$name.txt 2>&1; echo "$name rc=$?" >> $F/rc.txt; }
step normal_harness python3 selftest.py
step normal_semantic python3 semantic_selftest.py
step normal_gate python3 gate_selftest.py
step pidns_harness unshare -p -f -- python3 selftest.py
step pidns_semantic unshare -p -f -- python3 semantic_selftest.py
step restricted_harness sh restricted_host_sim.sh python3 selftest.py
step restricted_semantic sh restricted_host_sim.sh python3 semantic_selftest.py
step restricted_gate sh restricted_host_sim.sh python3 gate_selftest.py
step sigign_semantic python3 -c "import signal,subprocess,sys; signal.signal(signal.SIGCHLD, signal.SIG_IGN); sys.exit(subprocess.call([sys.executable,'semantic_selftest.py']))"
cd $S && step mutations python3 mut_v14.py tts_bakeoff
cat $F/rc.txt
