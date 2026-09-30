"""Slice D brain row. argv: <root> <D_sha>."""
import pathlib, sys
root = pathlib.Path(sys.argv[1]); D = sys.argv[2]
ROW = f"""| DOCKER-BUILD-VERIFIED-ONLY-ON-MANUAL-DISPATCH-SKIP-READS-GREEN-01 | **أولويّة: حرِج (الأوّل في الترتيب بقرار المالك — آخرُ ما يمنع فشلَ بناءٍ من بلوغ Railway).** **تصحيحٌ مقيس:** فشلُ migrate-main في الإنتاج **ليس** مثالاً عليه — بُني بـrailpack لا بالـDockerfile (صنفٌ مستقلّ: اختيارُ البنّاء، يُسجَّل في دفعة الدماغ التالية). وظيفة `docker-build` لا تعمل إلّا بتشغيلٍ يدويّ، و`runtime-stack-e2e-chaos` كذلك مع شرطِ متغيّر؛ فتظهران «skipped» في كلّ PR (رأيناهما في #1112) وتُقرآن نجاحاً. ومع `checkSuites:false` لا شيء يبني ملفّات Dockerfile قبل أن يبنيها Railway في الإنتاج. وآخرُ دليلٍ للمصفوفة `status: not_verified` (2026-07-27). صنفُ «الصمت يُقرأ نجاحاً». | ci/docker | `.github/workflows/docker-build-matrix-verifier.yml:58` · `.github/workflows/sahool-production-gates.yml:195` · `certification/evidence/docker_build_matrix_full.json` | **fixed** ({D}، 2026-09-30، التصميمُ بقرار المالك): بناءٌ يُثبت صلاحَ الـDockerfile من سياقٍ نظيف، بـ`SAHOOL_GIT_SHA=${{{{ github.sha }}}}` و`SAHOOL_BUILD_ID=${{{{ github.run_id }}}}-${{{{ github.run_attempt }}}}`، **حين يتغيّر الـDockerfile أو ما ينسخه (COPY)** لا في كلّ PR؛ وأنماطُ المراقبة تشمل ملفّاتِ السياق لا الـDockerfile وحده — وإلّا فهو «التخطّي يُقرأ نجاحاً» في طبقةٍ أخرى. **والبرهانُ الحيّ:** الـPR الذي أضافه غيّر المُتحقِّق نفسَه فبنى الصورَ الثلاثَ عشرة في CI قبل الدمج. |"""
LOG = f"""## [2026-09-30] governance | بناءُ ملفّات Dockerfile التي يبنيها Railway في الـPR — «التخطّي يُقرأ نجاحاً» يُغلَق بشكلٍ يمنع تكراره

`DOCKER-BUILD-VERIFIED-ONLY-ON-MANUAL-DISPATCH-SKIP-READS-GREEN-01` fixed (`{D}`): مُخطِّطٌ يختار الـDockerfile التي يمسّ الـPR ملفَّها **أو ما تنسخه** (السياقُ مُشتقٌّ من أسطر COPY لا قائمةً تُصان)، وبناءٌ بوسائط هويّةٍ من CI، و**وظيفةُ حكمٍ تعمل دائماً** («لا شيءَ يُبنى» نتيجةٌ مُعلَنة لا تخطٍّ صامت)، و**فحصٌ مستقلّ عن المُطابِق** (Dockerfile مُعدَّلٌ لا يغيب عن الخطّة — أفسِد المطابقةَ ⇒ 4 أحمر)، و**تغييرُ المُتحقِّق يُعيد بناءَ كلّ ما يتحقّق منه**. قيسَ عرضاً: أنماطُ مراقبة Railway تطابق مصادرَ COPY للخدمات الثلاث عشرة.
"""
reg = root / "sahool-brain/gaps/registry.md"
t = reg.read_text(encoding="utf-8")
anchor = next(l for l in t.splitlines() if l.startswith("| TILER-IN-FIXED-AND-UNIFIED-HAS-NO-CONSUMER-AND-CANNOT-BUILD-01 |"))
assert t.count(anchor) == 1 and chr(0x200F) not in ROW and chr(0x200F) not in LOG
reg.write_text(t.replace(anchor, anchor + "\n" + ROW, 1), encoding="utf-8")
lg = root / "sahool-brain/log.md"; lt = lg.read_text(encoding="utf-8")
lg.write_text(lt + ("" if lt.endswith("\n") else "\n") + LOG, encoding="utf-8")
print("ok")
