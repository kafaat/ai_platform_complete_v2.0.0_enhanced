# SAHOOL Cookbook — حزمة التوصية بالنماذج الزراعيّة

**Hardware-aware agricultural model recommender for Arabic contexts.**

---

## الفكرة

تكتشف الحزمة عتاد الجهاز المحلّي (GPU/CPU/RAM) تلقائيّاً، ثم توصي بأفضل نموذج ذكاء اصطناعي وتكميم يناسب البيئة — دون اتصال بالإنترنت.

---

## التثبيت

```bash
# ضمن المستودع مباشرةً (لا حاجة لتثبيت منفصل)
cd ai_platform_complete_v2.0.0_enhanced
```

---

## الاستخدام السريع (Python)

```python
from sahool_ai.cookbook import detect_platform, recommend_model, deploy_ollama

# 1. اكتشاف العتاد
profile = detect_platform()
print(profile)
# {'backend': 'cpu_x86', 'total_ram_gb': 15.9, 'available_ram_gb': 8.2,
#  'cpu_cores': 8, 'cpu_name': 'Intel Core i7-...'}

# 2. التوصية بنموذج لغوي
rec = recommend_model(profile, task_type="llm")
print(rec)
# {'model': 'qwen2.5-7b-gguf', 'quantization': 'Q4_K_M',
#  'estimated_vram_gb': 4.79, 'confidence': 0.72}

# 3. نشر النموذج عبر Ollama
result = deploy_ollama(rec["model"], rec["quantization"])
print(result["ok"])  # True
```

### نموذج ONNX

```python
from sahool_ai.cookbook import recommend_model, deploy_onnx, detect_platform

profile = detect_platform()
rec = recommend_model(profile, task_type="onnx")
# {'model': 'sahool-crop-forecast-v1', 'quantization': None, ...}

deploy_onnx("/opt/models/sahool-crop-forecast-v1.onnx", port=8080)
```

### تقدير الذاكرة يدويّاً

```python
from sahool_ai.cookbook import estimate_vram_gb

# كم تحتاج 7B بـ Q4_K_M وسياق 4096 رمز؟
gb = estimate_vram_gb(7.0, "Q4_K_M", context_length=4096)
print(f"{gb:.2f} GB")  # 4.79 GB
```

### درجة التوافق

```python
from sahool_ai.cookbook import fit_score

profile = {
    "backend": "cpu_x86",
    "total_ram_gb": 16.0,
    "available_ram_gb": 12.0,
    "cpu_cores": 8,
    "cpu_name": "...",
}
model = {"params_b": 7.0, "min_ram_gb": 6, "name": "qwen2.5-7b-gguf"}
score = fit_score(profile, model, quant="Q4_K_M")
print(f"درجة التوافق: {score}/100")
```

---

## Quick Start (English)

```python
from sahool_ai.cookbook import detect_platform, recommend_model

profile = detect_platform()  # auto-detect GPU/CPU/RAM
rec = recommend_model(profile, task_type="llm")
print(rec["model"], rec["quantization"])
```

---

## الكتالوج

يحوي `model_catalog.yaml` أكثر من 20 نموذجاً:

| النوع | الأمثلة |
|-------|---------|
| LLM | jais-13b, acegpt-7b, qwen2.5-7b, phi-3.5-mini |
| Embedding | bge-m3, jina-v3, e5-mistral-7b, arabic-bert |
| ONNX | sahool-crop-forecast, sahool-pest-detection, … |

---

## التشغيل بدون شبكة

كل المكوّنات تعمل offline:
- اكتشاف العتاد من `/proc/meminfo` و `/proc/cpuinfo`
- الكتالوج ملف YAML محلّي
- النشر عبر أدوات محليّة (Ollama / vLLM / ONNX Runtime)

---

## الاختبارات

```bash
python3 -m pytest tests_v9/test_cookbook.py -q
```
