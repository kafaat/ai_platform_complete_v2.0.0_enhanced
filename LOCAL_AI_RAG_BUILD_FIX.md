# إصلاح فشل بناء local-ai-rag (pip exit code 1)

## السبب الجذري
`requirements.txt` كان يعلن `sentence-transformers>=3.0.0` — حزمة ضخمة تجلب
PyTorch (مئات الميغابايت). لكنّها **غير مستخدَمة في الكود إطلاقاً**:
- التضمينات (embeddings) تُحسب عبر **Ollama** (`OllamaEmbeddings`, نموذج
  `nomic-embed-text`) — لا عبر sentence-transformers.
- لا `import sentence_transformers` في أيّ ملفّ.

تبعيّة ميّتة كانت تُفشل البناء (نفاد ذاكرة / timeout على المرآة / تعارض إصدار)
بلا أيّ فائدة.

## الإصلاح المُطبَّق
حذفتُ `sentence-transformers` من requirements.txt. الكود ما زال يُترجم (تحقّقت
— لا اعتماد عليه). البناء سيخفّ مئات الميغابايت.

## ⚠ سبب ثانٍ محتمل: المرآة الصينيّة
الـDockerfile يستخدم مرآة tsinghua الصينيّة افتراضيّاً:
```
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
```
قد تكون **بطيئة أو محجوبة من اليمن** → timeout. لو استمرّ الفشل بعد حذف
sentence-transformers، تجاوز المرآة لـPyPI الرسمي:

### الأمر الصحيح للبناء (مع تجاوز المرآة)
```powershell
docker compose -f docker-compose.v9.yml --env-file .env build `
  --build-arg PIP_INDEX_URL=https://pypi.org/simple `
  --build-arg PIP_TRUSTED_HOST=pypi.org

docker compose -f docker-compose.v9.yml --env-file .env up -d
```

أو لخدمة واحدة فقط (أسرع للاختبار):
```powershell
docker compose -f docker-compose.v9.yml build sahool-local-ai-rag `
  --build-arg PIP_INDEX_URL=https://pypi.org/simple
```

## ملاحظة على أمرك الأصلي
أمرك كان:
```
docker compose docker-compose.v9.yml --env-file up -d --build
```
الصياغة الصحيحة:
```powershell
docker compose -f docker-compose.v9.yml --env-file .env up -d --build
```
(نقص `-f` قبل اسم الملفّ، و`.env` بعد `--env-file`)

## لرؤية الخطأ الكامل لو تكرّر
البناء يقطع رسالة pip. لرؤية السبب الدقيق:
```powershell
docker compose -f docker-compose.v9.yml build sahool-local-ai-rag --progress=plain --no-cache
```
`--progress=plain` يُظهر كلّ مخرجات pip (السطر الذي فشل فعلاً).

## ملاحظة صدق
حذفُ sentence-transformers مؤكّد آمن (غير مستخدَم — تحقّقت بالبحث في الكود).
لكنّي **لا أرى الخطأ الكامل** (رسالتك مقطوعة)، فقد يكون هناك سبب إضافي (المرآة،
الذاكرة، تعارض إصدار آخر). لو استمرّ الفشل، شغّل `--progress=plain` وأرسل لي
آخر 20 سطراً من مخرجات pip — سأشخّص السبب الدقيق بلا تخمين.
