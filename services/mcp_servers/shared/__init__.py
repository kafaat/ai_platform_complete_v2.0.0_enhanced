# SAHOOL v9.0
#
# الحاويةُ تدمج حزمتَي ``shared`` في ``/app/shared/`` واحدة (``services/mcp_servers/Dockerfile``:
# ``COPY shared/`` ثمّ ``COPY services/mcp_servers/shared/``)، فخوادم MCP تستورد
# ``shared.oauth_middleware`` **و** ``shared.security.*`` معاً. وفي شجرة التطوير تُحَلّ
# ``shared`` إلى هذا المجلّد وحده حين يسبق ``services/mcp_servers`` على ``sys.path`` — فيغيب
# ``shared.security`` ويصير الخادمُ «غير قابل للاستيراد» فيُتخطّى اختبارُه صامتاً. نُطابِق الدمجَ
# بإلحاق مجلّد ``shared`` الجذريّ بمسار الحزمة **إن وُجد**؛ وفي الحاوية لا يوجد (المسارُ المحسوب
# ``/shared`` خارج ``/app``) فيبقى الدمجُ هناك من ``COPY`` كما هو.
# (JWT-DECODE-OUTSIDE-SHARED-SECURITY-01 — الفكرةُ من نسخة العمل المُنقَذة 9657f93a.)
import os as _os

_ROOT_SHARED = _os.path.normpath(
    _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "..", "shared")
)
if _os.path.isdir(_ROOT_SHARED) and _ROOT_SHARED not in __path__:
    __path__.append(_ROOT_SHARED)
