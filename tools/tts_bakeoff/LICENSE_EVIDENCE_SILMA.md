# SILMA TTS v1 — مادةُ إثبات الأصل والترخيص (مقتطفاتٌ من المصدر الأوّل)

**جُمعت:** 2026-10-05. **الغرض:** شرطُ إغلاق `TTS-SILMA-WEIGHTS-LINEAGE-UNVERIFIED-01` يطلب حفظَ المقتطف
**خارج الدماغ**؛ هذا موضعُه. الفجوةُ تبقى **open** (انظر «ما لا يحسمه» أدناه).

## المصادر المقروءة مباشرةً

| المصدر | المعرّف | كيف قُرئ |
|---|---|---|
| مستودع الكود `github.com/SILMA-AI/silma-tts` | commit `96ec4beedb0766fcbddbf8b49b696c4049574ed6` (2026-08-23T10:00:43+02:00) | `git clone` ثمّ قراءة `README.md` |
| حزمة PyPI `silma-tts==1.0.5` (sdist) | sha256 `ba3f4e4eee594402613416b1ebe2f13b5c6647400ddb9183b405b7d2b6b20dfd` | تنزيل `silma_tts-1.0.5.tar.gz` وقراءة `README.md` و`PKG-INFO` |
| بطاقة النموذج `huggingface.co/silma-ai/silma-tts` | commit `226dd7a65cadf51f9a6dbe3953fc89003b3844d5` | **لم تُقرأ هنا** (Hugging Face محجوبٌ في بيئة الإعداد)؛ قرأها المالك محلّيّاً ولصق نصّها في الجلسة — نصٌّ منقول لا مقيس |

## المقتطفات حرفيّاً

`README.md` عند `96ec4bee`، السطر 9 (ومثلُه حرفيّاً عدا «Arabic/English» في README الحزمة السطر 9 و`PKG-INFO` السطر 49):

> **SILMA Arabic TTS v1** is a high-performance, **150M-parameter** bilingual (Arabic & English) TTS model
> developed by [SILMA AI](https://silma.ai). Built on the cutting-edge **F5-TTS diffusion architecture**, the
> model was **pretrained from scratch** using tens of thousands of hours of high-quality public and
> proprietary data. To give back to the community, SILMA TTS is released under a highly permissive license,
> making state-of-the-art speech synthesis accessible for both **research and commercial use**.

`README.md` عند `96ec4bee`، الأسطر 189-191 (و README الحزمة السطر 183، `PKG-INFO` السطر 223):

> ## License
> 1. Code: MIT License
> 2. Model Weights: Apache-2.0 License

`README.md` عند `96ec4bee`، السطر 197 (**غائبٌ** عن README حزمة 1.0.5):

> * **Get Consent:** Only clone voices with explicit, documented permission from the speaker.

## فحصٌ بنيويّ مستقلّ (من المنبع F5-TTS)

مستودع `github.com/SWivid/F5-TTS` عند `283252563dbf91be625e0c27926acfaac449186c` (2026-09-21):

| البند | المقيس | الموضع |
|---|---|---|
| رخصةُ أوزان F5 | «The pre-trained models are licensed under the CC-BY-NC license due to the training data Emilia» | `README.md:278` |
| الأوزانُ الرسميّة المنشورة | ثلاثٌ كلّها بحجم Base: `F5TTS_v1_Base` · `F5TTS_v1_Base_no_zero_init` · `F5TTS_Base` | `src/f5_tts/infer/SHARED.md:52-64` |
| حجمُ Base | `dim 1024 · depth 22 · heads 16` | `src/f5_tts/configs/F5TTS_v1_Base.yaml` |
| حجمُ SILMA | `dim 768 · depth 18 · heads 12 · tokenizer char · text_mask_padding True · pe_attn_head null` = **`F5TTS_v1_Small` حرفيّاً** | `silma_tts/config.yaml:20-36` (حزمة 1.0.5) مقابل `configs/F5TTS_v1_Small.yaml` |
| إدراجُ SILMA في المنبع | «F5-TTS Small … Apache-2.0 … Pretrained by SILMA.AI» | `SHARED.md:73-79`، أُضيف في `623c96c2` (#1279، 2026-03-16) **بيد Karim Ouda** — إعلانُ الناشر نفسه قَبِله المشرفون، لا تحقّقٌ مستقلّ |

**النتيجة:** لم يُنشر المنبعُ أوزاناً بحجم Small، وأوزانُه كلّها 1024×22 لا تُحمَّل في 768×18. فـ**التهيئةُ المباشرة من
نقطة F5 رسميّة مستبعَدةٌ بنيويّاً** — دليلٌ مستقلّ عن إعلان الناشر. ولا يستبعد الشكلُ وحده التقطيرَ أو التقليمَ من
نموذج Base؛ وذلك يعود إلى سؤال البيانات أدناه.

**ليس ذا صلة:** `scripts/convert_checkpoint.py` (الموضعُ الذي تحيل إليه ملاحظةُ «checkpoint of different structure»)
محوّلٌ إلى TensorRT-LLM (`src/f5_tts/runtime/triton_trtllm/scripts/convert_checkpoint.py`)، لا أداةَ اشتقاق أوزان. و`silma-tts`
لا يعتمد على حزمة `f5-tts` (تبعيّاتُه في `pyproject.toml` بلا `f5-tts`؛ الكودُ منسوخٌ داخل `silma_tts/model`)، فتغييراتُ
إصدارات `f5-tts` لا تمسّ المحوّل.

## ما يحسمه

- **نقطةُ التهيئة:** الناشرُ يُعلن «pretrained from scratch» على بنية F5-TTS — أي البنية (كودها MIT) لا أوزان
  F5-TTS الأساسيّة (CC-BY-NC). فالمسارُ الذي فتح الفجوة (اشتقاقُ الأوزان من نقطة F5 غير التجاريّة) **ينفيه الناشر
  كتابةً**. هذا إعلانٌ من الناشر، لا تحقّقٌ مستقلّ من الأوزان.
- **مقطعُ الحزمة المرجعيّ:** شرطُ الموافقة منشورٌ في README المستودع (السطر 197)، فقرارُ رفض `ar.ref.24k.wav`
  قائمٌ على نصٍّ مقيس.

## ما لا يحسمه (سببُ بقاء الفجوة open)

- **مصادرُ بيانات التدريب غيرُ مُفصَّلة:** «public and proprietary data» بلا قائمة. فلا يُعرف إن دخلتها مجموعاتٌ
  غيرُ تجاريّة (مثل Emilia، CC-BY-NC، بيانات F5-TTS)، ولا حكمُ رخصة الأوزان حينئذٍ — سؤالٌ قانونيّ لا تقنيّ.
- **تطابقُ README المستودع مع بطاقة النموذج عند `226dd7a6`** لم يُقَس هنا (البطاقة محجوبة)؛ الأوزانُ المثبّتة في
  `sources.example.json` من commit البطاقة لا المستودع.
- **شرطُ الإغلاق الباقي:** تأكيدٌ مكتوب من SILMA AI بمصادر بيانات التدريب (أو ورقةٌ تُفصّلها)، يُحفظ هنا.
  حتّى ذلك: **يُقاس SILMA للجودة فقط، ولا يُعتمد تجاريّاً ولا في الإنتاج.**

## للمقارنة: Habibi-TTS (المنبع نفسه، مرشّحٌ عربيّ آخر)

`github.com/SWivid/Habibi-TTS` عند `16252f67b9d54fc75670c091d7a1e9e9550bbe3d` (2026-03-30): الكود MIT؛ النماذج
Unified/SAU/UAE CC-BY-NC-SA-4.0 والمتخصّصة (ALG · EGY · IRQ · MAR · MSA) Apache-2.0 (`README.md:125-128`). وخلافاً
لـSILMA، حجمُه `v1_base_cfg = dim 1024 · depth 22 · heads 16` (`src/habibi_tts/infer/infer_gradio.py:73`) = حجمُ
`F5TTS_v1_Base` — فالحجّةُ البنيويّة أعلاه **لا تنطبق عليه**، ونقطةُ تهيئته غيرُ مقروءة (issue #2 والورقة محجوبان هنا).
