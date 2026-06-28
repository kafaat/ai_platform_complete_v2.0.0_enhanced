"""حزمة routers/ لخدمة auth — وحدات ``APIRouter`` مفكَّكة من ``main.py``.

كلّ وحدة تُصدّر ``router = APIRouter()`` بمساراتها (بلا prefix — المسارات محفوظة
كما هي). تُسجَّل تلقائيّاً عبر ``router_registry.register_routers(app)`` المُستدعى
في نهاية ``main.py``. التبعيّات المشتركة (مساعِدات JWT، مسبح DB، النماذج،
الاعتماديّات) تبقى في ``main`` ويُشار إليها عبر ``import main`` + ``main.X``.
"""
