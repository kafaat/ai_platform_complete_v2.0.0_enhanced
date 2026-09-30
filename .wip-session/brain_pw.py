"""Brain rows for the Playwright/APT retry fix (owner-pasted CI log). argv: root"""
import pathlib
import subprocess
import sys

root = pathlib.Path(sys.argv[1])
out = subprocess.check_output(["git", "-C", str(root), "log", "--format=%h %s", "-n", "30"], text=True)
hits = [l.split()[0] for l in out.splitlines() if l.split(" ", 1)[1].startswith("CI: إعادةُ تثبيت Playwright تنتظر apt اليتيم")]
assert len(hits) == 1, hits
P = hits[0]

ROWS = f"""| PLAYWRIGHT-RETRY-FAILS-ON-ORPHANED-APT-LOCK-01 | **إعادةُ تثبيت Playwright لم تكن إعادة:** بلغت المحاولةُ الأولى مهلتها (مرآةٌ بطيئة)، لكنّ `apt-get` الذي يستدعيه `--with-deps` عبر `sudo` بقي حيّاً يُكمل التنزيل ويحمل `/var/lib/dpkg/lock-frontend`، فسقطت المحاولتان الثانية والثالثة في ~٣ث لكلٍّ على القفل — والرسالةُ قالت «تجاوز مهلته ٣ مرّات». مقيسٌ من سجلّ CI نقله المالك (2026-09-30، 17:53–17:58Z، بعد دمج `b0c14b6d`): أسطرُ `Get:16–20` بعد إعلان المهلة، و`held by process 2655 (apt-get)`. | ci/frontend-e2e | `scripts/ci/resilient_playwright_install.sh` · `scripts/ci/apt_mirror_fallback.sh` (`wait_for_apt_idle`) · `tests_v9/test_resilient_playwright_install.py` | **fixed** (`{P}`، 2026-09-30): الإعادةُ تنتظر اليتيمَ بسقف `PW_TIMEOUT` وتُسمّيه، ولا تقتله (قتلُ dpkg أثناء التثبيت يُفسد حالته)؛ والرسالةُ النهائيّة تقول لكلّ محاولة مهلةً أم فشلاً برمزه. التكذيب: سكربتا main ⇒ أحمر. **حدٌّ مُعلَن:** لا يُسرِّع مرآةً بطيئة — المهلةُ الأولى تبقى ممكنة، وما تغيّر أنّ ما بعدها صار إعادةً فعلاً. |
| APT-MIRROR-SWITCH-CLAIMED-WITHOUT-SUBSTITUTION-01 | **«المرآة بُدِّلت» ولم تُبدَّل:** مُشغِّلاتُ GitHub تقرأ مرآتها من `mirror+file:/etc/apt/apt-mirrors.txt`، فلا يحمل `ubuntu.sources` اسمَ المضيف؛ و`sed -i` يُعيد صفراً بلا استبدال، فطُبِع الادّعاءُ وجلب التحديثُ التالي من `azure.archive.ubuntu.com` نفسِه (السجلّ نفسه). والاختبارُ زيّف `sed` وكتب مصدراً بمضيفٍ صريح لا يوجد على المُشغِّل — يقيس صيغةً مُتخيَّلة لا صيغةَ المُشغِّل. يمسّ `resilient_apt_install.sh` أيضاً (الدالّةُ مشتركة). | ci/apt | `scripts/ci/apt_mirror_fallback.sh` (`switch_apt_mirror`) · `tests_v9/test_resilient_playwright_install.py` | **fixed** (`{P}`، 2026-09-30): `apt-mirrors.txt` أوّلُ المصادر، والادّعاءُ مشروطٌ بوجود المضيف قبل التحرير («لم تُبدَّل» وإلّا). الاختبارُ الجديد بصيغة المُشغِّل و`sed` حقيقيّ. التكذيب: ⇒ حالتان حمراوان على main. |
"""

LOG = f"""## [2026-09-30] ci | تثبيتُ Playwright: إعادةٌ لم تكن إعادة، ومرآةٌ ادُّعي تبديلُها

من سجلّ CI نقله المالك (بعد دمج `b0c14b6d`، لا من محتواه): `PLAYWRIGHT-RETRY-FAILS-ON-ORPHANED-APT-LOCK-01` و`APT-MIRROR-SWITCH-CLAIMED-WITHOUT-SUBSTITUTION-01` fixed (`{P}`). كلاهما مقيسٌ من السجلّ نفسه لا مظنون: `apt-get` يتيمٌ يُكمل التنزيل بعد المهلة ويحمل القفل، والتحديثُ بعد «بُدِّلت» يجلب من المرآة القديمة. والدرسُ صنفٌ معروف هنا: الاختبارُ زيّف الأداةَ التي تحمل العطل (`sed`) وكتب مُدخَلاً بصيغةٍ غير صيغة المُشغِّل. لا يمسّ Railway.
"""

reg = root / "sahool-brain/gaps/registry.md"
text = reg.read_text(encoding="utf-8")
anchor = next(l for l in text.splitlines() if l.startswith("| TILER-IN-FIXED-AND-UNIFIED-HAS-NO-CONSUMER-AND-CANNOT-BUILD-01 |"))
assert text.count(anchor) == 1
for bad in ("‏", "‎"):
    assert bad not in ROWS + LOG
reg.write_text(text.replace(anchor, anchor + "\n" + ROWS.rstrip("\n"), 1), encoding="utf-8")
log = root / "sahool-brain/log.md"
lt = log.read_text(encoding="utf-8")
log.write_text((lt if lt.endswith("\n") else lt + "\n") + LOG, encoding="utf-8")
print(P)
