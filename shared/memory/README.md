# SAHOOL Farm Memory — دليل الاستخدام

## English Guide

### Overview

The Farm Memory package (`shared/memory`) provides a tenant-isolated, versioned, encryptable knowledge store for SAHOOL farms.

### Quick Start

```python
from shared.memory import FarmMemory, ConversationTurn, export_to_encrypted_tarball, import_from_encrypted_tarball

# Create a memory store for farm "farm-001"
mem = FarmMemory("farm-001")

# Add a conversation turn
turn = ConversationTurn(
    farm_id="farm-001",
    user_query="What should I plant this season?",
    ai_response="Based on your soil type and climate zone, wheat is recommended.",
    topic="crop_selection",
)
mem.add_conversation(turn)

# Add preferences
mem.add_preference("preferred_crop", "wheat")
mem.add_preference("soil_type", "loam")

# Search
results = mem.search("wheat planting", k=5)

# Export encrypted
export_to_encrypted_tarball("farm-001", "/tmp/farm001.enc", password="secure-password", memory=mem)

# Import encrypted
mem2 = FarmMemory("farm-001")
import_from_encrypted_tarball("/tmp/farm001.enc", "farm-001", "secure-password", mem2)
```

### Encryption Guide

**Algorithm:** AES-256-GCM authenticated encryption.

**Key Derivation:** PBKDF2-HMAC-SHA256 with 200,000 iterations and a 16-byte random salt.

**File Format (.enc):**
```
[16 bytes: PBKDF2 salt]
[12 bytes: AES-GCM nonce]
[N bytes: ciphertext + 16-byte GCM authentication tag]
```

**Security notes:**
- Each export uses a fresh random salt and nonce.
- The GCM tag provides both confidentiality and authenticity (tampering is detected).
- Passwords are never stored — keep your password safe.
- Recommended password length: 20+ characters.

### Schema Migration Guide

When upgrading from schema v1 to v2:

| Change | v1 | v2 |
|--------|----|----|
| Field rename | `query` | `user_query` |
| New field | (absent) | `satisfaction_score: null` |

Migration is automatic on import. To manually migrate:

```python
from shared.memory import migrate_schema

old_data = {"schema_version": "v1", "conversations": [{"query": "hello"}], ...}
new_data = migrate_schema(old_data, from_version="v1", to_version="v2")
# new_data["conversations"][0] now has "user_query": "hello", "satisfaction_score": null
```

### Tenant Isolation

Each `FarmMemory` instance is locked to a single `farm_id`. Cross-tenant access raises `ValueError`. Data is stored under separate namespaces: `<store_dir>/<farm_id>/memory.json`.

### Export Formats

| Format | Function | Notes |
|--------|----------|-------|
| JSON | `export_to_json` | Always available |
| Encrypted | `export_to_encrypted_tarball` | AES-256-GCM; always available |
| Parquet | `export_to_parquet` | Requires `pip install pyarrow` |
| Qdrant snapshot | `export_to_qdrant_snapshot` | Falls back to JSON if qdrant_client absent |

---

## الدليل العربي

### نظرة عامة

حزمة ذاكرة المزرعة (`shared/memory`) توفّر مخزناً معزولاً للمستأجرين، مُعتمداً على الإصدارات، وقابلاً للتشفير لمعرفة مزارع SAHOOL.

### دليل التشفير

**الخوارزمية:** AES-256-GCM تشفير مصادق عليه.

**اشتقاق المفتاح:** PBKDF2-HMAC-SHA256 مع 200,000 تكرار وملح عشوائي من 16 بايت.

**تنسيق الملف (.enc):**
```
[16 بايت: ملح PBKDF2]
[12 بايت: nonce لـ AES-GCM]
[N بايت: نص مشفّر + وسم مصادقة GCM بحجم 16 بايت]
```

**ملاحظات أمنية:**
- يستخدم كل تصدير ملحاً وnonce عشوائيَّين جديدَين.
- وسم GCM يضمن السرية والأصالة معاً (يكتشف أي تلاعب).
- كلمات المرور لا تُخزَّن أبداً — احتفظ بكلمة مرورك في أمان.
- الطول الموصى به لكلمة المرور: 20+ حرفاً.

### دليل ترحيل المخطط

عند الترقية من المخطط v1 إلى v2:

| التغيير | v1 | v2 |
|---------|----|----|
| إعادة تسمية الحقل | `query` | `user_query` |
| حقل جديد | (غائب) | `satisfaction_score: null` |

الترحيل يتم تلقائياً عند الاستيراد.

### عزل المستأجرين

كل مثيل `FarmMemory` مرتبط بـ `farm_id` واحد. أي وصول عبر المستأجرين يُطلق `ValueError`. البيانات مخزّنة في مساحات أسماء منفصلة: `<store_dir>/<farm_id>/memory.json`.

### المهارات المتاحة

| المهارة | الاسم |
|---------|-------|
| مستشار المحاصيل | `crop_advisor` |
| الري | `irrigation` |
| تشخيص الآفات | `pest_diagnosis` |

```python
from shared.memory import load_skill, list_skills

print(list_skills())  # ['crop_advisor', 'irrigation', 'pest_diagnosis']
skill = load_skill("pest_diagnosis")
print(skill["pitfalls"])  # قائمة المخاطر
```
