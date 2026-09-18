# تحقّقٌ مقيس من المقابلات الخارجيّة لنسيج القرار — 2026-09-16

> **موضوعه:** الدعاوى التي تُسنِدها `docs/architecture/DECISION_FABRIC_SOURCE_COMPARISON_20260916.md`
> (PR #1011، الرأس `a19543ef64b623c01986161fd7186315df1025cb`) إلى أربعة مشاريع خارج هذا
> المستودع: LinkMind · OM1 · OpenAgentFlow · WGAI. تلك الوثيقة تذكر المستودعات **بالاسم بلا SHA**،
> فدعاواها كانت غير قابلة للقياس من داخل الشجرة. هذه الوثيقة تُثبِّت الـSHA الأربعة وتقيس كلَّ دعوى
> ضدّ الشيفرة عند ذلك الـSHA، وتُسجِّل ما لم يُقَس.
>
> **ما هي وما ليست:** سجلُّ قياسٍ ساكن. لا تُغيِّر عقداً ولا راية ولا حارساً، ولا تُدخِل شيفرةً
> خارجيّة. وهي مستقلّة عن #1011: تصلح مرجعاً سواء دُمِج أو لا، وإن دُمِج فالمقصود أن تُنقَل
> كتلةُ التثبيت (§٧) إلى الوثيقة الأصل في شريحةٍ لاحقة.

## ١ — المنهج والحدود

- استنساخٌ للقراءة فقط بعمق ١ (`git clone --depth 1`) عبر وكيل الجلسة؛ لا تنفيذَ لأيٍّ من المشاريع
  ولا بناء. كلُّ سطرٍ مُستشهَدٍ به قُرِئ من الملفّ لا من README وحده حيث أمكن.
- **عمق ١ يعني:** لا دعوى تاريخيّة (متى أُضيفت خاصّيّة، أو كيف تطوّرت). الأحكام على **الحالة**
  عند الـSHA المثبَّت فقط.
- المقياس: هل الشيفرةُ عند الـSHA تفعل ما تنسبه إليها وثيقةُ #1011؟ لا: هل المشروعُ جيّد.
- الأحكام ثلاثة: **مؤكَّد** (الشيفرة تفعل ما نُسِب إليها) · **مؤكَّد بحدود** (تفعله في نطاقٍ أضيق
  ممّا توحي به الصياغة) · **غير مقيس** (لم أجد ما يُثبِته أو ينفيه في الشجرة).

## ٢ — الـSHA المثبَّتة

| المشروع | المستودع | SHA | تاريخ آخر التزام | اللغة الفعليّة |
|---|---|---|---|---|
| LinkMind | `landingbj/LinkMind` | `dc40c029d44abdb5056fe91aa4735c839749cbaa` | 2026-09-16 17:34 +08:00 | Java (Maven) |
| OM1 | `OpenMind/OM1` | `84e00a1672d17d012c24ae6b300365594265bd37` | 2026-09-15 13:02 −07:00 | **Go** (`go.mod:1-3`) |
| OpenAgentFlow | `OpenAgentFlow/OpenAgentFlow` | `397e57ca0668e97669e850b277ed1878e580e7b4` | 2026-08-02 21:03 +03:00 | JavaScript (مترجم) → Python (هدف) |
| WGAI | `dromara/wgai` | `dbf8988b9167b09a7724ab49d39a14a3065d2b58` | 2026-09-08 10:29 +08:00 | Java (Spring Boot / JeecgBoot) |

آخرُ التزامٍ في LinkMind يحمل تاريخَ يوم القياس نفسه — أي أنّ الهدف يتحرّك يوميّاً، وأيُّ
دعوى بلا SHA عنه تصف كوناً قد لا يكون قائماً غداً.

## ٣ — LinkMind: «توجيه/failover مركزيّ خلف تعبيرات مسار مُعدَّة» — **مؤكَّد**

| ما تدّعيه #1011 | الشاهد عند `dc40c029` | الحكم |
|---|---|---|
| «centralizes model routing/failover behind configured route expressions» | التعبير في الإعداد: `lagi-web/src/main/resources/lagi.yml:92` → `route: best((landing&qwen),(kimi|chatgpt))`؛ نحوُه في `lagi.yml:326-333` (`A|B` polling · `A,B` failover · `A&B` parallel · `%` wildcard) | مؤكَّد |
| التعبيرات تُحلَّل وتُنفَّذ لا تُوصَف فقط | المحلّل `lagi-core/src/main/java/ai/router/utils/RouteExprParser.java:37-38,83-84` يُنتج `FailOverRoute`؛ مستهلكه `ai/router/utils/RouterParser.java:74`؛ التنفيذُ التسلسليّ في `ai/router/FailOverRoute.java:29-46` (يجرّب كلَّ مسار حتّى أوّل نتيجة غير `null`) | مؤكَّد |
| «middleware pattern» | `README.md:5` («enterprise-grade multimodal AI middleware») و`README.md:90` («configured centrally in `lagi.yml`») | مؤكَّد |

**ما لم تذكره #1011 ولا يُغيّر حكمها:** الـfailover على **ثلاث طبقات** لا طبقة واحدة —
تعبيرُ المسار (أعلاه) · قائمةُ الخلفيّات مع تجميد المحوّل الفاشل بحسب رمز الخطأ
(`ai/llm/service/LlmRouteService.java:52-70`، `FreezingService.freezingAdapterByErrorCode`) ·
حوضُ المفاتيح (`ai/llm/adapter/impl/ProxyLlmAdapter.java:193-196`، `key_route: failover`).
كلُّها توجيهٌ بين **مزوّدين** متكافئين وظيفيّاً. فتوصيفُ #1011 لِما ترفضه — provider routing لا
authority routing — دقيق: لا طبقةَ في LinkMind تميّز مصدرَ سلطةٍ من مصدر سياق.

## ٤ — OM1: «مدخلات/أفعال وحدويّة حول HAL» — **مؤكَّد مع تصحيحَين**

| ما تدّعيه #1011 | الشاهد عند `84e00a16` | الحكم |
|---|---|---|
| «modular inputs/actions» | تسجيلٌ بالمصنع: `internal/inputs/sensor.go:59` (`func Register`) · `internal/actions/action.go:47` (`func Register`)؛ الإضافاتُ تحت `plugins/inputs/` و`plugins/actions/` (`docs/developing/7_project_structure.md:10-35`) | مؤكَّد |
| «HAL integration pattern» | `README.md:192`: **HAL يُفترَض أنّ الروبوت يوفّره** («If your robot hardware does not yet provide a suitable HAL … will be needed for you to create one»)؛ `README.md:194`: OM1 يتّصل به «via USB, serial, ROS2, CycloneDDS, Zenoh, or websockets»؛ `docs/developing/2_architecture.md:70-81` | مؤكَّد — OM1 **فوق** الـHAL لا هو |
| «No sensor driver should write a recommendation or execution command directly» (Finding 6 كقاعدة SAHOOL) | OM1 نفسه يلتزمها: `docs/developing/2_architecture.md:83` — Raw Sensors → Captioning → Fuser → LLM → HAL → Actions؛ لا مسارَ من `plugins/inputs` إلى `executeActions` | مؤكَّد بوصفه نمطاً |

**تصحيح ١ — اللغة والنقل:** OM1 عند هذا الـSHA **Go** لا Python (`go.mod:1-3`، `go 1.25.0`).
Zenoh في الشيفرة فعلاً (`go.mod:8` `eclipse-zenoh/zenoh-go v1.9.0`؛
`plugins/actions/unitree/go2/autonomy/move.go` يَنشر `cmd_vel` عبر Zenoh؛ `internal/zenoh/`).
أمّا ROS2 فلا `rclpy`/`rclgo` في أيّ ملفّ Go؛ التكاملُ معه عبر جسر Zenoh/CDR
(`docs/developing/zenoh-bridge.md`، `docs/developing/ros2-humble.md`، `plugins/actions/navigation/cdr.go`).
فدعوى «HAL via ROS2/Zenoh» صحيحةٌ توثيقاً، وفي الشيفرة Zenoh وحده.

**تصحيح ٢ — السببُ المقيس لـFinding 6، وهو ما أغفلته #1011:** حلقةُ OM1 الأساسيّة
(`internal/runtime/runtime.go:443-452` نبضةٌ بتردّد `hertz` أو عند إشارة المدخلات) تستدعي
النموذجَ اللغويّ (`runtime.go:506` `current.cortexLLM.Call`) ثمّ تُمرِّر **نداءات أدواته** مباشرةً
إلى المُنفِّذ (`runtime.go:530` و`:546` `executeActions(ctx, current, toolCalls)`). أي أنّ
**النموذجَ اللغويّ هو طبقةُ القرار التي تختار الفعل** — وهذا بعينه ما ترفضه Finding 1 في #1011
(«generated language as explanation/advisory only») وما يحرسه في SAHOOL
`scripts/ci/decision_candidate_boundary_gate.py`. فحصرُ نمط OM1 عند حدّ الجهاز
(driver → device adapter → canonical observation → quality/calibration → canonical field state → decision)
**ضرورةٌ مقيسة لا احتياط**: نقلُ الحلقة كاملةً ينقل LLM إلى مسار التنفيذ. الوثيقةُ أصابت الحكم
وأغفلت سببه؛ §٧ تُقترِح الجملة.

## ٥ — OpenAgentFlow: «مواصفة تصريحيّة + تحقّق دلاليّ يمسك تدفّقاً غير صالح قبل التنفيذ» — **مؤكَّد بحدود**

| ما تدّعيه #1011 | الشاهد عند `397e57ca` | الحكم |
|---|---|---|
| «declarative workflow specification» | DSL `.oaf` ← `spec/SPEC.md:10-16` (Human-readable · Runtime-independent · Statically verifiable · Compilable إلى IR) | مؤكَّد |
| «semantic validation pattern» / «validated workflow/IR» | ثلاثُ مراحل `spec/SEMANTICS.md:17-23` (رموز · مراجع · رسم)؛ التنفيذُ `compiler/validator.js:7,140,417`؛ الوصولُ من `start` وإلى `end` `validator.js:480-494`؛ دورةٌ بلا شرط خروج `validator.js:591` | مؤكَّد |
| «catches invalid state flow before execution» | صحيحٌ لبنية **الرسم** وقتَ الترجمة. أمّا **قِيَمُ** الحالة وقتَ التشغيل: `@min/@max` تُصدَر إلى IR **بلا فحصٍ تشغيليّ** — `todo.md:10-12` «Partially Implemented … TODO: Generate runtime boundary validation checks» | مؤكَّد بحدود |

**حدودٌ أخرى مقيسة:** هدفُ التشغيل الوحيد LangGraph — `compiler/validator.js:377-379` يرفض غيره
بخطأ «Unsupported runtime»؛ المواصفة `0.1.0-draft` (`spec/SPEC.md:3-4`). فالنمطُ المفيد
لـSAHOOL — كما قالت #1011 — هو **التحقّق البنيويّ قبل التنفيذ**، لا حارسُ قِيَمٍ تشغيليّ؛ وحذرُها
(«declarative only where it reduces duplicated state-transition logic») متناسبٌ مع هذا الحدّ.

## ٦ — WGAI: «نشر محلّيّ، تكامل نماذج/فيديو/مراقبة» — **مؤكَّد جزئيّاً**

| ما تدّعيه #1011 | الشاهد عند `dbf8988b` | الحكم |
|---|---|---|
| «local deployment» | `README_EN.md:28` «Supports autonomous offline deployment»؛ الاستدلالُ داخل JVM عبر ONNX Runtime — `wgai-module-system/wgai-system-biz/src/main/java/org/jeecg/modules/tab/AIModel/OnnxModelCacheService.java:3-5`؛ RapidOCR `pom.xml:102-103` | مؤكَّد |
| «video» | `README_EN.md:29` «edge video analysis (16-64 channels real-time)»؛ `README.md:28` (实时视频分析预警) | مؤكَّد |
| «monitoring» | `README_EN.md:98` «Backend Monitoring (CPU/JVM/Redis)» — مراقبةُ **نظام** لا ميدان؛ والإنذارُ البصريّ (预警) في سطر الفيديو أعلاه | مؤكَّد بحدود — الكلمةُ تحتمل الاثنين |
| Finding 8: النمطُ «offline-first» لا «no external APIs» | متّسقٌ مع المقيس: «Third-party API Config» `README_EN.md:98` · حوارُ ChatGPT `README_EN.md:29` · مساعداتُ Aliyun OSS/SMS `wgai-boot-base-core/src/main/java/org/jeecg/common/util/oss/OssBootUtil.java`، `…/util/DySmsHelper.java` — فهو offline-**capable** لا offline-**only** | مؤكَّد |

**غير مقيس:** مسارُ ChatGPT المُعلَن — لا `openai` ولا `api.openai.com` ولا `chat/completions`
في أيّ `*.java`/`*.yml` بالشجرة؛ إمّا في الواجهة الأماميّة (خارج هذا المستودع) أو عبر
«Third-party API Config» وقتَ التشغيل. لا أحكم عليه.

**سياقٌ يُفيد القارئ:** المشروع اشتقاقٌ من JeecgBoot (`pom.xml:3-4`
`org.jeecgframework.boot`)، أي لوحةُ low-code إداريّة بوحدات AI؛ «النمطُ» فيه تشغيليٌّ
(training/inference منفصلان، `README_EN.md:28`) أكثر منه معماريّاً.

## ٧ — الحكم الكلّيّ وما يلزم #1011

**لا دعوى خارجيّة مكذوبة.** اثنتان مؤكَّدتان بالكامل (LinkMind · OM1)، وواحدة مؤكَّدة
**ضمن نطاقها المُعلَن** (OpenAgentFlow — حكمُ §٥ «مؤكَّد بحدود»: تحقّقٌ بنيويّ وقتَ الترجمة
وهدفٌ وحيد)، وواحدة (WGAI) مؤكَّدة في جوهرها وملتبسة في كلمة. الاستنتاجاتُ المعماريّة
الثمانية في #1011 تبقى قائمةً على ما قِيس — بل قياسُ OM1 يقوّي Finding 1 وFinding 6 أكثر ممّا
ادّعته الوثيقة نفسها.

**فجوةٌ مسجَّلة:** `EXTERNAL-REFERENCE-WITHOUT-SHA-01` — وثيقةُ #1011 تُسنِد أحكاماً معماريّة
إلى مستودعات خارجيّة بالاسم بلا SHA، فلا يمكن لقارئٍ لاحق أن يُعيد قياسها. تُغلَق بنقل الكتلتين
أدناه إلى الوثيقة الأصل.

### الكتلة المقترَحة لقسم «External source references» في #1011

```markdown
- LinkMind: `landingbj/LinkMind` @ `dc40c029d44abdb5056fe91aa4735c839749cbaa` (2026-09-16) —
  route expressions `lagi-web/src/main/resources/lagi.yml:92,326-333`;
  parser `lagi-core/src/main/java/ai/router/utils/RouteExprParser.java:37-38,83-84`;
  sequential failover `lagi-core/src/main/java/ai/router/FailOverRoute.java:29-46`.
- OpenAgentFlow: `OpenAgentFlow/OpenAgentFlow` @ `397e57ca0668e97669e850b277ed1878e580e7b4` (2026-08-02) —
  IR `spec/SPEC.md:16`; three-phase validator `spec/SEMANTICS.md:17-23`; graph checks
  `compiler/validator.js:417,480-494,591`. Compile-time structural only: `@min/@max` runtime
  bounds are TODO (`todo.md:10-12`); sole runtime target LangGraph (`validator.js:377-379`).
- OM1: `OpenMind/OM1` @ `84e00a1672d17d012c24ae6b300365594265bd37` (2026-09-15), Go —
  input/action registries `internal/inputs/sensor.go:59`, `internal/actions/action.go:47`;
  HAL is assumed to be vendor-provided (`README.md:192-194`); Zenoh in code, ROS2 via bridge docs.
- WGAI: `dromara/wgai` @ `dbf8988b9167b09a7724ab49d39a14a3065d2b58` (2026-09-08) —
  offline deployment `README_EN.md:28`; in-JVM ONNX inference
  `wgai-module-system/wgai-system-biz/src/main/java/org/jeecg/modules/tab/AIModel/OnnxModelCacheService.java:3-5`;
  third-party API config `README_EN.md:98` (offline-capable, not offline-only).
```

### الجملة المقترَحة لـFinding 6

```markdown
Measured reason (OM1 @ 84e00a16): OM1's core loop hands the LLM's tool calls straight to the
action executor (`internal/runtime/runtime.go:506` → `:530`/`:546`), i.e. generated language
*is* the action-selecting authority there. That is exactly what Finding 1 rejects for SAHOOL,
so confining the OM1 pattern to the device boundary is a measured necessity, not caution.
```

## ٨ — إعادة القياس (جنائيّة: عند الـSHA المثبَّت لا عند رأس الفرع)

القاعدة: **تعذُّرُ جلب الـSHA المثبَّت = تعذُّرُ التحقّق**، لا «استعمل أحدث نسخة». السكربت
يفشل فوراً إن لم يُجلَب الـSHA أو لم يطابقه `HEAD` بعد الفصل، ولا يقرأ ملفّاً قبل ذلك.

**نطاقُه المُعلَن:** يُعيد قياسَ **المراسي الحاسمة** لكلّ حكم (سطرُ المسار وقواعدُ التعبير في
LinkMind · ترتيبُ `cortexLLM.Call` قبل `executeActions` في OM1 · رسالةُ «Unsupported runtime»
في OpenAgentFlow · غيابُ استدعاء OpenAI في WGAI)، لا كلَّ ملفٍّ استُشهد به في §٣–§٦. ملفّاتُ
المحلّل والمستهلك المذكورة في §٣ (`RouteExprParser.java` · مواضعُ الاستهلاك) تُقرأ يدويّاً عند
الـSHA نفسه؛ فرقمُ خروجٍ صفر يعني «المراسي قائمة»، لا «كلُّ سطرٍ في هذه الوثيقة أُعيد قياسُه».

```bash
#!/usr/bin/env bash
set -euo pipefail
EXT="${EXT:-/tmp/ext}"
declare -A PIN=(
  [landingbj/linkmind]=dc40c029d44abdb5056fe91aa4735c839749cbaa
  [OpenAgentFlow/openagentflow]=397e57ca0668e97669e850b277ed1878e580e7b4
  [OpenMind/om1]=84e00a1672d17d012c24ae6b300365594265bd37
  [dromara/wgai]=dbf8988b9167b09a7724ab49d39a14a3065d2b58
)
for r in "${!PIN[@]}"; do
  d="$EXT/$r"; sha="${PIN[$r]}"
  # عزلٌ صريح: دليلٌ قائمٌ من قياسٍ سابق قد يحمل ملفّاتٍ غيرَ متتبَّعة، و`checkout`
  # لا يمسحها — فتُقرأ شجرةٌ مخلوطة بدل المصدر المثبَّت. نبدأ من فارغٍ دائماً.
  rm -rf "$d"
  mkdir -p "$d"
  git -C "$d" init -q
  git -C "$d" remote add origin "https://github.com/$r"
  # جلبُ الـSHA بعينه (لا الفرع). فشلُه = التحقّق غير متاح — لا ارتداد إلى default branch.
  GIT_LFS_SKIP_SMUDGE=1 git -C "$d" fetch -q --depth 1 origin "$sha" \
    || { echo "VERIFICATION UNAVAILABLE: cannot fetch pinned $sha for $r" >&2; exit 2; }
  git -C "$d" checkout -q --detach FETCH_HEAD
  head="$(git -C "$d" rev-parse HEAD)"
  [ "$head" = "$sha" ] || { echo "HEAD $head != pinned $sha for $r" >&2; exit 3; }
  echo "pinned OK: $r @ $sha"
done

# LinkMind — دعوى §٣ شقّان: **تعبيرُ مسارٍ مُعَدٌّ فعلاً** (`lagi.yml:92`) و**نحوٌ يُعرِّفه**
# (`:326-333`). فحصُ النحو وحده لا يكفي: نسخةٌ تُبقي التوثيق وتنزع الإعدادَ تمرّ خضراء
# والدعوى نصفُها ساقط. فالسطران يُقاسان معاً.
lm_route="$(sed -n 92p "$EXT/landingbj/linkmind/lagi-web/src/main/resources/lagi.yml")"
grep -qF 'route: best((landing&qwen),(kimi|chatgpt))' <<<"$lm_route" \
  || { echo "LinkMind claim contradicted: configured route expression absent from lagi.yml:92" >&2; exit 7; }
printf 'lagi.yml:92 %s\n' "$lm_route"
lm_slice="$(sed -n 326,333p "$EXT/landingbj/linkmind/lagi-web/src/main/resources/lagi.yml")"
for tok in 'A|B' 'A,B' 'A&B'; do
  grep -qF "$tok" <<<"$lm_slice" \
    || { echo "LinkMind claim contradicted: '$tok' absent from lagi.yml:326-333" >&2; exit 7; }
done
printf '%s\n' "$lm_slice"
# OM1 — الدعوى في §٤ ليست «الرمزان موجودان» بل **الترتيب**: نداءُ النموذج يسبق المُنفِّذ
# في الحلقة نفسها. فيُقاس أوّلُ سطرِ `cortexLLM.Call` وآخرُ سطرِ `executeActions` المُستدعى
# (لا التعريف ولا التعليق) ويُشترَط أن يسبق الأوّلُ الثاني — وإلّا فالسلسلةُ المُدّعاة زالت.
# الأرقامُ المطلقة: السطرُ n في الشريحة = 499+n في الملفّ (:506 و:530/:546 في §٤).
om1_slice="$(sed -n 500,550p "$EXT/OpenMind/om1/internal/runtime/runtime.go")"
# الاستخراجُ خارج `errexit` عمداً: تحت `pipefail` يُنهي `grep` الخالي من تطابقٍ السكربتَ
# بـ1 عند الإسناد، فلا يُبلَغ فحصُ الخلوّ أدناه ويعود «الرمز مفقود» برمزِ خروجٍ غيرِ
# الموثَّق. مقيسٌ على مراجعة Copilot ٤ في #1012: كان يخرج 1 والموثَّق 5.
set +e
om1_call="$(printf '%s\n' "$om1_slice" | grep -n -F 'cortexLLM.Call' | head -1 | cut -d: -f1)"
om1_exec="$(printf '%s\n' "$om1_slice" | grep -nE '(^|[^a-zA-Z])rt\.executeActions\(' | tail -1 | cut -d: -f1)"
set -e
[ -n "$om1_call" ] && [ -n "$om1_exec" ] \
  || { echo "OM1 chain broken: call=$om1_call exec=$om1_exec in runtime.go:500-550" >&2; exit 5; }
[ "$om1_call" -lt "$om1_exec" ] \
  || { echo "OM1 order broken: LLM call at $((499+om1_call)) does not precede executor at $((499+om1_exec))" >&2; exit 5; }
echo "OM1 chain OK: cortexLLM.Call@$((499+om1_call)) → rt.executeActions@$((499+om1_exec))"
# OpenAgentFlow — هدفُ التشغيل الوحيد. الدعوى في §٥ أنّ غيرَ langgraph مرفوض، فالرمزان
# واجبان في الشريحة لا مطبوعَين فحسب.
oaf_slice="$(sed -n 375,380p "$EXT/OpenAgentFlow/openagentflow/compiler/validator.js")"
for tok in 'Unsupported runtime' 'langgraph'; do
  grep -qF "$tok" <<<"$oaf_slice" \
    || { echo "OpenAgentFlow claim contradicted: '$tok' absent from validator.js:375-380" >&2; exit 8; }
done
printf '%s\n' "$oaf_slice"
# WGAI — «لا تطابق» (grep status 1) قيمةٌ مقيسة؛ أمّا status ≥ 2 (ملفٌّ لا يُقرأ، صلاحيّات…)
# فتعذُّرُ قياسٍ لا صفرٌ — يُحفَظ status ولا يُبتلَع بـ`|| true`.
set +e
# والبحثُ غيرُ حسّاسٍ للحالة: `OpenAI` أو `OPENAI` كانا يُعدّان صفراً فيصير «غيرُ مقيس»
# استنتاجاً من مسحٍ لم يَرَ ما يبحث عنه (مراجعة Copilot ٥ على #1012).
wgai_matches="$(grep -rniE 'openai|chat/completions' --include='*.java' --include='*.yml' --include='*.yaml' "$EXT/dromara/wgai")"
wgai_status=$?
set -e
[ "$wgai_status" -le 1 ] || { echo "VERIFICATION UNAVAILABLE: grep exited $wgai_status scanning wgai" >&2; exit 6; }
wgai_hits=0
[ -z "$wgai_matches" ] || wgai_hits="$(printf '%s\n' "$wgai_matches" | wc -l)"
echo "wgai external-LLM tokens in java/yml/yaml: $wgai_hits   # يُتوقَّع 0"
```

الأسطرُ المستشهَدُ بها في §٣–§٦ صحيحةٌ **عند هذه الـSHA وحدها**؛ للاستشهاد بـ«الحالة
الراهنة» أعد القياس على SHA جديد وثبِّته في §٢ بدل استبدال الأرقام في مكانها.
