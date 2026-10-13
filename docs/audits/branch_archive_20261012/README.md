# جرد الفروع وأرشيفها — 2026-10-12 (توثيق فقط)

المستودع `kafaat/ai_platform_complete_v2.0.0_enhanced`، والقياس على `main@29c09d0b`.
هذه الوثيقة **لا تحذف شيئاً ولا تأذن بحذف**. لم يُحذف فرع، ولم يُدمج PR، ولم يُنشر شيء، ولم يُمسّ Railway (قراءة فقط).
الحذف يحتاج موافقة مستقلّة من المالك، ثمّ إعادة فحص فوريّة قبل كلّ دفعة (القسم ٨).

| الملفّ | المحتوى |
|---|---|
| `branches_20261012.md` | الفروع الـ594 كلّها: الـSHA الكامل، قاعدة الدمج مع main، التقدّم، تاريخ آخر commit، سجلّ الـPR، الصنف، نوع التكامل، ملفّات المصدر والتعارضات، مرجع الاستعادة، القرار ودليله (صيغة أمر الاستعادة في رأس الملفّ) |
| `deletion_manifest_20261012.md` | قائمة الحذف النهائيّة: SAFE / REVIEW / HOLD لكلّ فرع، مع الدليل وأمر الاستعادة |

## ١. مطابقة الجرد

الإجماليّ **594** فرعاً (`git ls-remote` في 2026-10-12):

| الصنف | العدد |
|---|---|
| SAFE_TO_DELETE (قبل إعادة الفحص) | 387 |
| REQUIRES_INTEGRATION_REVIEW | 141 |
| NEEDS_REVIEW | 44 |
| ACTIVE_DEPENDENCY | 17 |
| PRESERVED_NO_CONTENT_LEFT | 5 |
| **المجموع** | **594** |

### الفروع الـ146 المحفوظة للتحليل المنفصل

هي 124 فرعاً بلا PR، و22 فرعاً أُغلق الـPR الخاصّ بها دون دمج. كان التفصيل السابق يعدّ 143 منها فقط؛ الفرق 3 فروع لم تُذكر في سطر التفصيل وإن كانت داخل الجرد:

| النوع (مقيس بدمج تجريبيّ في `main@29c09d0b`) | العدد |
|---|---|
| `source_conflicts` (تعارض في ملفّات مصدر) | 109 |
| `clean_unique` (دمج نظيف ويضيف محتوى) | 23 |
| `generated_only_conflicts` (التعارض في المولَّد فقط) | 6 |
| `brain_or_generated_only` (الفرق في الدماغ أو المولَّد فقط) — **وهي الثلاثة الغائبة** | 3 |
| `PRESERVED_NO_CONTENT_LEFT` (الدمج لا يغيّر شيئاً في main) | 5 |
| **المجموع** | **146** |

- الثلاثة الغائبة من التفصيل السابق: `brain-close-deferred-gaps` · `claude/brain-ledger-bundle-b` · `claude/brain-session-close`.
- الخمسة بلا محتوى متبقٍّ: `claude/wip-slice-c` · `claude/wip-v25-3-10` · `claude/wip-v25-c` · `copilot/check-merge-status-workflow` · `fix/edge-model-artifact-digest-rebased`.

إذن 141 + 5 = 146، و387 + 141 + 44 + 17 + 5 = 594. بقيت الفروع الـ146 كلّها على حالها وقرارها HOLD.

## ٢. قائمة الحذف النهائيّة

| القرار | العدد | المعنى |
|---|---|---|
| **SAFE** | **380** | مرشَّح للحذف إن وافق المالك، بعد إعادة الفحص الفوريّة |
| REVIEW | 51 | لا يُحذف قبل قراءة بشريّة |
| HOLD | 163 | لا يُحذف |
| **المجموع** | **594** | |

### كيف صار 387 = 380 + 7

اسم كلٍّ من هذه الفروع السبعة مذكور في ملفّ حيّ في `main`، فنُقلت إلى REVIEW رغم تكافؤ محتواها:

| الفرع | الملفّ الذي يذكره |
|---|---|
| `certification/final-readiness-evidence` | `FINAL_PRODUCTION_READINESS_REPORT.md` و`docs/runbooks/OPERATOR_DISPATCH_BACKLOG_LIVE_EXECUTION.md` |
| `claude/code-review-34hO3` | `agent-memory/CORRECTIONS.md` و`docs/architecture/brain_deferral_baseline.json` و`docs/runbooks/OPERATOR_DISPATCH_BACKLOG_LIVE_EXECUTION.md` |
| `claude/unify-main-and-certification` | `docs/runbooks/OPERATOR_DISPATCH_BACKLOG_LIVE_EXECUTION.md` |
| `claude/verify-all-generated` | `docs/architecture/generated_chain_known_drift.json` |
| `copilot/29041154936` | `docs/runbooks/OPERATOR_DISPATCH_BACKLOG_LIVE_EXECUTION.md` |
| `feat/ds-fieldapp-skin` | `docs/UI_DESIGN_SPEC_FIELDAPP.md` |
| `permanent-compatibility-contract` | `docs/architecture/api_versioning_legacy_baseline.json` |

- **REVIEW (51)** = هذه السبعة + 44 فرعاً من NEEDS_REVIEW. منها 43 فرعاً لطلبات #504–#539 (يونيو): commits دمجها ليست أسلافاً لـmain الحاليّ لأنّ التاريخ بعدها أُعيدت كتابته، وثلاثة منها غائبة محلّيّاً، فلا يمكن إثبات التكافؤ مع main الحاليّ، وإن بقيت قابلة للاستعادة عبر `refs/pull`. والفرع الـ44 هو `develop`، لأنّ مرشّحات workflows ما زالت تسمّيه، و`docs/audits/BRANCH_TRIAGE_REVIEW_20260718.md` ينصّ على عدم حذفه.
- **HOLD (163)** = 17 ACTIVE_DEPENDENCY + 146 فرعاً محفوظاً (القسم ١).
- **ACTIVE_DEPENDENCY (17):**
  - `main`
  - `claude/project-exploration-dtjw3p` (مصدر TTS في staging، و#1122)
  - `claude/claude-md-docs-p6qqir`
  - خمسة فروع `deploy/*`، منها `deploy/sahool-staging-fa92a1f7` (مصدر platform وauth في الإنتاج) و`deploy/sahool-platform-db-ready-eb6da9df` (مصدر platform في staging)
  - رؤوس الـPR المفتوحة كلّها: #1128 · #1129 · #1130 · #1161 · #1162 · #1163 · #1165 · #1166 · #1167

### دليل كلّ قرار SAFE

يُقبل الفرع SAFE إذا تحقّقت **كلّ** الشروط التالية (العمود `decision_evidence`):

1. رأس الفرع سلف لـ`main`؛ أو أنّ الـPR الخاصّ به دُمج squash بهذا الرأس نفسه، وإعادة تطبيق الرأس على أبي commit الـsquash (`git merge-tree --write-tree X^1 tip`) تعطي شجرة الـsquash بايتاً ببايت.
2. الرأس مبلوغ من `refs/pull/<N>/head` أو من `main`، وهي مراجع لا يحذفها GitHub بحذف الفرع.
3. الرأس أب مباشر في فرع الأرشيف، وهو موجود في الـbundle (القسم ٣).
4. ليس مصدراً لأيّ خدمة على Railway، ولا تسمّيه أيّ workflow، ولا PR مفتوحاً له، ولا يذكره ملفّ حيّ.

## ٣. النسخ الاحتياطيّ والتحقّق منه

### أ) فرع الأرشيف على GitHub (دائم)

`claude/wip-branch-archive-20261012` @ `316ae7eec335412df31427a50300ab4e2e15a101`

- سلسلة commits من نوع octopus، لكلّ منها 60 أباً على الأكثر. شجرة كلّ commit هي ملفّ البيان وحده، فلا يُدمج الفرع ولا يُنشر.
- رؤوس الفروع الـ594 كلّها **آباء مباشرة** فيه. هي 593 SHA فريداً، لأنّ `fix/railway-migration-runner` و`ops/resolved-pr1023-20260918` يشتركان في الرأس `d08d3fa5`.
- التحقّق المحلّيّ: الرؤوس الـ594 كلّها ضمن `git rev-list --parents` للفرع.
- التحقّق على الخادم: مقارنة GitHub (`compare`) لعيّنة من 20 رأساً، منها 6 فروع بلا PR: 20/20 مبلوغة.

### ب) Git bundle للمرشّحين (مستقلّ عن GitHub)

- الملفّ: `candidates_20261012.bundle`، حجمه 42,306,783 بايت.
- `sha256` = `159d4e6e413ba567b7707694f9046d1495728b009a01be73c197005a5126829f`
- يغطّي المرشّحين الـ387 الأصليّين تحت `refs/backup-20261012/<branch>`، فيغطّي الـ380 الحاليّين بالضرورة.
- اختبار الاستعادة في مستودع منفصل جديد:
  ```bash
  git init --bare restore_test
  git -C restore_test fetch candidates_20261012.bundle 'refs/backup-20261012/*:refs/heads/*'
  git -C restore_test fsck --connectivity-only
  ```
- النتيجة:
  - استُعيد 387/387 مرجعاً.
  - لا مرجع مفقود، ولا اختلاف في أيّ SHA.
  - `fsck` أعاد 0.
  - التاريخ الكامل لكلّ مرجع قابل للعبور: 387/387.
- الـbundle ملفّ خارج المستودع، لأنّ حجمه لا يناسب الـgit. يُحفظ لدى المالك. النسخة الدائمة داخل GitHub هي فرع الأرشيف و`refs/pull/*`.

### ج) أوامر الاستعادة

```bash
# من GitHub (فرع الأرشيف أو refs/pull): الـSHA في العمود head_sha
git fetch origin claude/wip-branch-archive-20261012
git push origin <head_sha>:refs/heads/<branch>        # = العمود restore_command

# من الـbundle، دون الحاجة إلى GitHub
git fetch candidates_20261012.bundle 'refs/backup-20261012/<branch>:refs/heads/<branch>'
git push origin <branch>
```

## ٤. إعادة الفحص (2026-10-12، نحو 09:48Z)

| الفحص | النتيجة |
|---|---|
| SHA كلّ فرع مقابل `git ls-remote` | 595 رأساً على الخادم، منها فرع الأرشيف الجديد. لم يتغيّر أيّ SHA لأيّ مرشّح |
| الـPR المفتوحة | 10 طلبات. كلّ رؤوسها وقواعدها في HOLD |
| مصادر Railway (قراءة `describe-environment` في البيئتين) | `main` · `claude/project-exploration-dtjw3p` · `deploy/sahool-staging-fa92a1f7` · `deploy/sahool-platform-db-ready-eb6da9df`. لا شيء منها مرشّح |
| مراجع GitHub Actions | مرشّحات الفروع تسمّي `main` و`release/**` و`develop`. `develop` في REVIEW |
| مراجع الملفّات في `main` | 33 ملفّاً تذكر أسماء تشبه الفروع. 7 مرشّحين مذكورون في ملفّات حيّة، فنُقلوا إلى REVIEW (القسم ٢). الباقون مذكورون فقط في الوثيقة التاريخيّة `docs/audits/BRANCH_TRIAGE_REVIEW_20260718.md` |

**تنبيه لإعادة الفحص القادمة:** هذا المجلّد يذكر الأسماء الـ594 كلّها بطبيعته. لذا يُستثنى من فحص المراجع، كما تُستثنى `BRANCH_TRIAGE_REVIEW_20260718.md`.

## ٥. هل يحمل أيّ مرشّح تغييرات يحتاجها فرعا التكامل؟

**لا.** محتوى كلّ فرع من الـ380 مكافئ لـmain: إمّا أنّ رأسه سلف لـmain، وإمّا أنّه مكافئ للـsquash بالشجرة. ولا أحد منها مصدر لفرع التكامل A أو B. المصادر كلّها من فئة HOLD، وهي إمّا رؤوس PR مفتوحة، وإمّا من الفروع الـ146.

## ٦. توصيات التكامل

هذه مقترحات وليست قرارات؛ دمج أيّ فرع تكامل في main قرار للمالك.

**A — `claude/wip-integration-a-nodeploy`:** دمجه في main لا ينشر أيّ خدمة، لأنّه لا يمسّ أنماط المراقبة (watchPatterns) في Railway.

- #1161 `claude/wip-migrator-railway-evidence`
- #1162 `claude/wip-minio-guard-provenance`
- #1166 `claude/wip-brain-verified-transition`
- #1167 `claude/wip-gap-measure-identity`
- `claude/wip-v25b-sam2` · `claude/wip-v25b-tiler` · `claude/wip-v25b-erp` (كلّها `clean_unique`)

**B — `claude/wip-integration-b-runtime`:** دمجه في main يُطلق نشراً.

| المصدر | ما ينشره دمجه في main |
|---|---|
| #1163 `claude/wip-frontend-reference-contracts` | frontend |
| #1130 `claude/wip-ci-nginx-pull-retry` | frontend |
| #1128 `claude/wip-vegetation-rs256-v2` | vegetation |
| #1165 `claude/wip-migrator-ingest-precheck` | migrate-main (`/migrations/**`) |
| `claude/wip-1122-main-sync` (محتوى #1122) | tts. تعارضه في `docs/architecture/tenant_guc_scope_baseline.json` يحتاج حلّاً يدويّاً، ولا يتغيّر #1122 نفسه |

**خارج الفرعين الآن:**

| الفرع | السبب |
|---|---|
| `claude/wip-agent-ratchets-jwt-held` | معلَّق بقصد |
| `claude/wip-cdse-catalog-outage` | تعارض مصدر في `capabilities/registry/capabilities.json` |
| `claude/wip-voice-consult-57847492` و`claude/wip-tts-review-tests` | يتبعان #1122 |
| `claude/wip-vegetation-rs256` | حلّ محلّه #1128 (v2) |
| `claude/wip-v25b-vllm` | تعارض في `ai_evidence_runtime.py` |
| فروع `codex/*-repair-lab-*` و`codex/publish-*` و`ops/conflict-resolution-*` (`clean_unique`) | workflows لحادثة واحدة؛ دمجها يضيف workflows ميّتة |
| الفروع الـ109 ذات تعارض المصدر | تُفرز حسب المجال (العمود `source_files_changed`) قبل نقل أيّ شيء منها |

## ٧. الحالة

- **الحذف غير مأذون به.** هذه الوثيقة لا تُدمج آليّاً.
- **المرشّحون الباقون للحذف بالضبط: 380** (SAFE). ويبقى 51 فرعاً في REVIEW و163 في HOLD دون مساس.

## ٨. إجراء الحذف المقترح (بعد موافقة مستقلّة فقط)

1. دفعات من 50 فرعاً.
2. قبل كلّ دفعة: `git ls-remote` ومقارنة كلّ SHA بالعمود `head_sha`، وإعادة فحص الـPR المفتوحة، ومصادر Railway، والـworkflows، ومراجع الملفّات.
3. الحذف مشروط بأن يكون الـSHA هو نفسه، وإلّا رفضه الخادم:
   ```bash
   git push --force-with-lease=refs/heads/<branch>:<head_sha> origin :refs/heads/<branch>
   ```
4. أيّ فرع تغيّر رأسه أو ظهر له مرجع جديد يخرج من الدفعة إلى REVIEW.
