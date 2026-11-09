# توقيعُ المالك لتفويضات GATE-01 — دليلُ التشغيل

> الفجوة: `GATE01-AUTHORIZATION-ORIGIN-UNENFORCED-01` · قرارُ المالك: 2026-11-09 —
> «أغلِقها بتوقيع المالك المنفصل».
>
> المُتحقِّق: `scripts/ci/gate01_owner_signature_guard.py` (مكتبة + CLI)، يستدعيه
> `scripts/ci/gate01_frozen_path_guard.py` في وظيفة `gate01-physical-effect-freeze`.
> المُساعِد: `scripts/gates/prepare_gate01_authorization.py`. السياسة: كتلة
> `owner_signature` في `docs/architecture/gate01_policy.json`.

## ١. لماذا التوقيع — وما الذي لا يُثبِته

كلُّ PR يفتحها الوكيل مؤلَّفةٌ بحساب GitHub `kafaat` نفسِه (حساب المالك). فلا مؤلّفُ
الـPR ولا اعتمادٌ من ذلك الحساب يُميّز المالكَ من الوكيل، وحقلٌ مثل `approved_by: owner`
أو `ruling_source` نصٌّ يكتبه الوكيل. وأثبت فحصٌ تجريبيّ أنّ فحصَ «اكتمال الحقول» يقبل
`ruling_source` مُلفَّقاً وبصماتٍ كلُّها أصفار ما دامت الحقول حاضرة.

التوقيعُ يحلّ **سؤالَ المنشأ** وحده: «صاحبُ مفتاح المالك وقّع هذه البايتات بعينها».

- **التوقيعُ يُثبِت منشأَ القرار؛ والمراجعةُ المستقلّة وظيفةٌ أخرى.** التوقيعُ لا يعني أنّ
  أحداً غيرَ المالك راجع الرقعة، ولا أنّ الرقعة صحيحة. صحّتُها تقيسها اختباراتها
  وطفراتها، والمراجعةُ المستقلّة تأتي من هويّةٍ ثانية.
- **GitHub يمنع مؤلّفَ الـPR من اعتماد طلبه.** وبما أنّ المؤلّفَ عادةً `@kafaat`، فاعتمادُ
  `@kafaat` على PR الوكيل غيرُ ممكنٍ أصلاً، ولو أمكن لما ميّز المالكَ من الوكيل.
- **قاعدةُ CODEOWNERS التي تُسمّي `@kafaat @haithmgarallah-ye` تقبل أيَّهما** — فهي لا
  تفرض هيثم بالاسم. حين يكون المؤلّفُ `@kafaat` يقع الاعتمادُ عمليّاً على
  `@haithmgarallah-ye`، لكنّ ذلك نتيجةُ قاعدة «المؤلّف لا يعتمد» لا نصٌّ في CODEOWNERS.
  وكلُّ ذلك خاملٌ ما لم يُفعَّل `Require review from Code Owners` في قاعدةٍ نافذة على `main`.

## ٢. المفتاحُ الخاصّ لا يدخل المستودع ولا بيئةَ الوكيل — أبداً

- يُولَّد المفتاح **على جهاز المالك** (ويُفضَّل جهازٌ غير متّصل، أو مفتاحُ عتاد
  `sk-ssh-ed25519@openssh.com`).
- **لا يُلتزَم المفتاحُ الخاصّ، ولا يُلصَق في محادثة، ولا يُعطى لأيّ وكيل أو جلسة Claude.**
  أيُّ توقيعٍ أنتجه وكيلٌ ليس توقيعَ مالك بالتعريف.
- الملفُّ الملتزَم `docs/architecture/gates/owner_allowed_signers` **لا يحمل أيَّ مفتاح**
  اليوم (قالبٌ مُعلَّق). فالحارسُ يطبع `owner signing key not configured` ويعامل كلَّ
  تفويضٍ معاملةَ `UNVERIFIED` — أي يفشل مغلقاً.
- الاختباراتُ تُولِّد مفاتيحَ **رمِيّةً مؤقّتة** في مجلّدٍ مؤقّت عند كلّ تشغيل، ولا يُلتزَم
  منها شيء. لا تُلتزِم أيَّ مفتاحٍ يمكن أن يُظَنّ مفتاحَ المالك.

## ٣. الصيغة — ولماذا هذه

**ظرفُ DSSE فوق نقلِ `ssh-keygen -Y`.** بحثنا في الشجرة عن مُساعِدات DSSE/PAE أو مُتحقِّقِ
Ed25519 قابلٍ لإعادة الاستعمال فلم نجد: إشاراتُ DSSE الموجودة تخصّ حزم Sigstore التي
تتحقّق منها أدواتٌ خارجيّة داخل workflow الشهادة، ولا مُساعِدَ في `scripts/lab/`. ووظيفةُ
GATE-01 لا تُثبِّت أيَّ حزمة Python، فإدخالُ مكتبة تشفير تبعيّةٌ جديدة على مسارٍ حاجب.
لذلك:

- **ما يُوقَّع** هو ترميزُ DSSE المسبق `PAE(payloadType, payload)` =
  `"DSSEv1" SP LEN(type) SP type SP LEN(body) SP body`، حيث `payload` = JSON قانونيّ
  (مفاتيح مرتّبة، بلا فراغات، ASCII، وسطرٌ جديد أخير).
- **أداةُ التوقيع والتحقّق** `ssh-keygen -Y sign` / `ssh-keygen -Y verify` (OpenSSH، موجودة
  على مُشغِّلات GitHub ubuntu) مع ملفّ `allowed_signers` ونطاقٍ ثابت
  **`sahool-gate01-authorization-v1`**. لا تشفيرَ مكتوباً يدويّاً في المستودع.
- **الملفُّ الملتزَم** ظرفُ DSSE:
  `docs/architecture/gates/authorizations/<decision_id>.dsse.json` =
  `{"payloadType": "application/vnd.sahool.gate01-authorization+json;version=1", "payload": base64(JSON), "signatures": [{"keyid": <signer>, "sig": base64(<توقيع SSHSIG المُدرَّع>)}]}`.

### الحقول الموقَّعة (كلُّها إلزاميّة، ولا حقلَ مجهول)

| المجموعة | الحقول |
|---|---|
| الهويّة `identity` | `repository` (owner/name) · `repository_id` (**رقميّ**) · `pr_number` · `signer` (الـprincipal في `allowed_signers`) · `signer_role` = `owner` |
| الموضوع `subject` | `base_sha` (merge-base مع الأساس) · `head_sha` (الالتزام المُختبَر) · `tree_sha` (شجرتُه) · `scope`: لكلّ مسارٍ `path` + `change` (add/modify/delete/rename، و`from_path` للإعادة) + `before_sha256` + `after_sha256` |
| الدليل `evidence` | `manifest_path` + `manifest_sha256` لبيان الأدلّة المقبول |
| الصلاحيّة | `decision_id` فريد (`GATE01-AUTH-YYYY-MM-DD-NNN`) · `action` · `validity.not_before` · `validity.expires_at` (≤ `max_validity_days`) · `nonce` |
| الاستعمال `use` | `max_uses` = 1 · `single_use` = true |

`action` واحدٌ من: `state_transition` (CLOSED→OPEN) · `bounded_change` (تفويضٌ مقيَّد
لمسارٍ مجمَّد) · `policy_change` (إضعافُ كتلة `owner_signature`) · `trust_root_change`
(تدويرُ مفتاح المالك بعد تثبيته).

### ما يتحقّق منه الحارس

1. جذرُ الثقة يُقرأ من **فرع الأساس** (`origin/main`) لا من الـPR — فمفتاحٌ يُضاف في الـPR
   نفسِها لا يُوثَق به.
2. التوقيعُ صالحٌ للـprincipal المُعلَن في النطاق `sahool-gate01-authorization-v1`؛ وموقِّعٌ
   مجهول أو مفتاحٌ آخر أو نطاقٌ آخر أو بايتٌ مُبدَّل ⇒ `INVALID`.
3. الهويّة: المستودع ورقمُه (`GITHUB_REPOSITORY`/`GITHUB_REPOSITORY_ID`) ورقمُ الـPR.
4. الموضوع: `base_sha` = merge-base الحاليّ (فأيُّ rebase أو دمجٍ من الأساس بعد الموافقة
   يُبطِلها) · `head_sha` سلفٌ لرأس الـPR، وما بعده لا يمسّ إلّا ملفّاتِ التفويض والسجلَّين
   · `tree_sha` شجرةُ `head_sha` · `scope` يساوي التغيير الفعليّ `base..head` بالضبط.
5. الدليل: بايتاتُ `manifest_path` عند `head_sha` تطابق `manifest_sha256`.
6. الصلاحيّة الزمنيّة وقائمةُ الإلغاء.
7. الاستعمالُ الواحد: القرارُ المُدرَج في سجلّ الاستهلاك على الأساس مُستهلَكٌ ومرفوض،
   والـPR يجب أن تحجزه في السجلّ **مرّةً واحدة** بنفس بصمة الموضوع والظرف. والسجلّان
   (الاستهلاك والإلغاء) إلحاقيّان: حذفُ مدخلٍ أو تعديلُه أو إعادةُ ترتيبه يُحجَب.
8. للانتقال إلى OPEN: السياسةُ الجديدة يجب أن تُسمّي في `gate.ruling_source` مسارَ
   الظرف المُتحقَّق نفسِه، وأن تحمل `owner_ruling_on` مؤرَّخاً وحقولَ أدلّة المرحلة ٠
   كاملةً (`FROZEN` · `success` · بصمات sha256 غير صفريّة).

## ٤. ما يُفرَض الآن، وما يُفرَض بعد تثبيت المفتاح

| الحالة | قبل تثبيت المفتاح (اليوم) | بعد تثبيته |
|---|---|---|
| CLOSED→OPEN | **محجوب** دائماً (`owner signing key not configured`) | يمرّ فقط بظرفٍ `state_transition` مُتحقَّق |
| تفويضٌ مقيَّد بلا توقيع | إرشاديّ (لا يحجب) | إرشاديّ حتّى يقلب المالك `required_for_bounded` إلى `true`، ثمّ محجوب |
| تفويضٌ مقيَّد بتوقيعٍ حاضر | `UNVERIFIED` (إرشاديّ) | يُتحقَّق منه؛ وتوقيعٌ حاضرٌ فاسد **يحجب** |
| إضعافُ كتلة `owner_signature` | **محجوب** (لا مفتاحَ يوقّع `policy_change`) | يمرّ فقط بـ`policy_change` مُتحقَّق |
| تعديلُ `owner_allowed_signers` | التثبيتُ الأوّل يُرفَض ما لم تساوِ البصمةُ `vars.GATE01_OWNER_KEY_FINGERPRINT` | التدويرُ يتطلّب `trust_root_change` بالمفتاح القائم |

ولا تُغيَّر حالةُ البوّابة هنا: `gate.state` يبقى `CLOSED`.

## ٥. ما يفعله المالك — مرّةً واحدة

```bash
# 1) على جهاز المالك (لا في المستودع، لا في بيئة الوكيل)
ssh-keygen -t ed25519 -C "kafaat GATE-01 owner signing key" -f ~/.ssh/sahool_gate01_owner
ssh-keygen -lf ~/.ssh/sahool_gate01_owner.pub      # احفظ البصمة SHA256:...

# 2) أنشئ سطرَ جذر الثقة (المفتاحُ العامّ وحده)
printf 'kafaat-gate01-owner namespaces="sahool-gate01-authorization-v1" %s\n' \
  "$(cat ~/.ssh/sahool_gate01_owner.pub)"
```

3. **ثبِّت البصمة خارج المستودع أوّلاً:** في إعدادات المستودع على GitHub
   (Settings → Secrets and variables → Actions → **Variables** → New repository variable)
   أنشئ المتغيّر `GATE01_OWNER_KEY_FINGERPRINT` بقيمة البصمة التي طبعها `ssh-keygen -lf`
   في الخطوة ١ حرفيّاً (`SHA256:...`). هذا الإعداد لا يملكه الوكيل: ليس في المستودع، ولا
   تكتبه أدواته — فهو المرساة الوحيدة التي تفصل المالكَ عن وكيلٍ يشاركه حسابَ GitHub.
   (GATE01-INITIAL-TRUST-ROOT-IS-TOFU-01.)
4. افتح **بنفسك** (من واجهة GitHub أو جهازك) PR تُضيف ذلك السطرَ وحده إلى
   `docs/architecture/gates/owner_allowed_signers` (أزِل لا شيء من التعليقات). الحارس يرفض
   التثبيتَ الأوّل ما لم تساوِ بصمةُ المفتاح **بالضبط** قيمةَ المتغيّر (مفتاحٌ واحد، لا غيره)،
   ويرفضه كذلك إن لم يكن المتغيّر مضبوطاً. وراجِع البصمة في الـPR بعينك أيضاً.
5. بعد دمجها: (اختياريّ، مُستحسَن) PR تقلب `owner_signature.required_for_bounded` إلى `true`
   — وهو تقويةٌ لا تحتاج توقيعاً.
6. احصل على رقم المستودع مرّةً واحدة:
   `gh api repos/kafaat/ai_platform_complete_v2.0.0_enhanced --jq .id`

## ٦. ما يُفعَل لكلّ قرار

يستطيع **أيُّ أحد** (والوكيل منهم) تنفيذ الخطوات ١ و٢ و٤ و٥؛ الخطوة ٣ للمالك وحده.

```bash
# 0) (للانتقال إلى OPEN فقط) في الـPR: state=OPEN، و
#    gate.ruling_source = "docs/architecture/gates/authorizations/<ID>.dsse.json"،
#    و gate.owner_ruling_on = تاريخ اليوم — ثمّ التزِم. هذا الالتزام هو head_sha.

# 1) ابنِ الحمولة من الأساس والرأس والفرق (يكتب <ID>.payload.json و<ID>.pae)
python3 scripts/gates/prepare_gate01_authorization.py prepare \
  --base-ref origin/main --head HEAD \
  --action state_transition \
  --decision-id GATE01-AUTH-2026-11-09-001 \
  --repository kafaat/ai_platform_complete_v2.0.0_enhanced --repository-id <REPO_ID> \
  --pr-number <PR> --signer kafaat-gate01-owner \
  --evidence-manifest <path/of/accepted/evidence/manifest> \
  --valid-days 3 --out-dir /tmp/g01auth

# 2) راجِع الحمولة: PR الصحيح؟ head_sha هو آخِر التزامٍ راجعته؟ كلّ مسارٍ في scope متوقَّع؟
cat /tmp/g01auth/GATE01-AUTH-2026-11-09-001.payload.json
git diff --stat <base_sha> <head_sha>

# 3) المالك وحده — يوقّع بايتات PAE (لا ملفّ JSON نفسه)
ssh-keygen -Y sign -f ~/.ssh/sahool_gate01_owner -n sahool-gate01-authorization-v1 \
  /tmp/g01auth/GATE01-AUTH-2026-11-09-001.pae
#   ⇒ /tmp/g01auth/GATE01-AUTH-2026-11-09-001.pae.sig

# 4) لُفَّ الحمولة والتوقيع في ظرف DSSE داخل المستودع، ثمّ احجز القرار في السجلّ
python3 scripts/gates/prepare_gate01_authorization.py envelope \
  --payload /tmp/g01auth/GATE01-AUTH-2026-11-09-001.payload.json \
  --signature /tmp/g01auth/GATE01-AUTH-2026-11-09-001.pae.sig
python3 scripts/gates/prepare_gate01_authorization.py reserve \
  --envelope docs/architecture/gates/authorizations/GATE01-AUTH-2026-11-09-001.dsse.json

# 5) تحقّق محلّيّاً، ثمّ التزِم الظرف والسجلّ وحدهما فوق head_sha
python3 scripts/ci/gate01_owner_signature_guard.py \
  docs/architecture/gates/authorizations/GATE01-AUTH-2026-11-09-001.dsse.json \
  --base-ref origin/main --pr-head HEAD \
  --repository kafaat/ai_platform_complete_v2.0.0_enhanced --repository-id <REPO_ID> --pr-number <PR>
git add docs/architecture/gates/authorizations/GATE01-AUTH-2026-11-09-001.dsse.json \
        docs/architecture/gates/consumed_authorizations.json
git commit -m "gate01: owner-signed authorization GATE01-AUTH-2026-11-09-001"
```

**قواعدُ تُسقِط القرار إن خُولِفت:**

- أيُّ التزامٍ بعد `head_sha` يمسّ غيرَ الظرف والسجلَّين ⇒ مرفوض. أعِد من الخطوة ١.
- أيُّ rebase أو دمجٍ من `main` بعد التوقيع يُغيّر `base_sha` ⇒ مرفوض. أعِد التوقيع.
- انقضاءُ `expires_at` قبل الدمج ⇒ مرفوض. أصدِر قراراً جديداً بمعرّفٍ جديد.
- رمزُ الخروج للـCLI: `0` = VERIFIED · `1` = INVALID · `2` = UNVERIFIED.

## ٧. الإلغاء والتدوير

- **الإلغاء:** أضِف `{"decision_id", "revoked_at", "reason"}` إلى `revoked` في
  `docs/architecture/gates/revoked_authorizations.json`. يسري من الـPR نفسها، ولا يُزال أبداً.
- **تدويرُ المفتاح:** PR تُعدِّل `owner_allowed_signers` وتحمل ظرفاً
  `--action trust_root_change` موقَّعاً **بالمفتاح القائم**. بلا ذلك تُحجَب.
- **فقدُ المفتاح:** لا تجاوزَ داخل المستودع عمداً. الطريقُ قرارُ مالكٍ خارج الشجرة (تعديلُ
  الحارس نفسِه في PR يراجعها مالكُ الكود الثاني) — وهو ما يجب أن يكون صعباً.

## ٨. حدودُ الصدق

- التثبيتُ **الأوّل** للمفتاح لا يحميه توقيع؛ تحميه بصمةٌ يضعها المالكُ خارج المستودع
  (`vars.GATE01_OWNER_KEY_FINGERPRINT`) ويفرض الحارسُ مساواتَها. وحدُّ ذلك: مَن يملك صلاحيةَ
  إدارة إعدادات المستودع يستطيع تغيير المتغيّر — فالضمانُ مساوٍ لضمان حساب المالك نفسه، لا أعلى.
- المُتحقِّقُ والحارس نفسُهما كودٌ في المستودع: تعديلُهما يتطلّب مراجعةَ مالك الكود
  (`.github/CODEOWNERS`) — خاملةً ما لم يُفعَّل الإعداد — وطفراتُهما مسجَّلة في
  `docs/architecture/guard_mutation_registry.json`.
- الحجزُ الذرّيّ (`O_CREAT|O_EXCL`) يحسم التسابقَ على آلةٍ واحدة؛ وبين PRين متوازيتين
  يحسمه git: مدخلان يُلحَقان بآخر المصفوفة نفسها يتعارضان نصّيّاً، والثانية بعد تحديثها
  ترى القرارَ مُستهلَكاً على الأساس فتُرفَض.
- الساعة: `now` = ساعةُ المُشغِّل (أو `--now` في الاختبارات)، لا وقتُ الالتزام الذي يكتبه
  المؤلّف.
