"""حزمة راوترات supervisor-agent (سقالة التفكيك).

كلّ وحدة هنا تُصدّر ``router = APIRouter()`` وتُضمَّن تلقائيّاً عبر
``router_registry.register_routers(app)`` (بلا prefix — المسارات تبقى كما هي).
تُملأ بنقل مُعالِجات ``main.py`` (نمط تفكيك المنصّة المحفوظ-السلوك).
"""
