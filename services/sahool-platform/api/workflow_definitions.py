"""تعريفات سير العمل (Workflow Definitions) — سجلّ سير العمل المُعلَن كبيانات.

المشكلة المسدودة: محرّك سير العمل (core/workflow_engine.py: run_workflow) يُنفّذ خطوات
كـ**كود** (دوالّ Python داخل كلّ خدمة)، وقواعد الانتقال تُرمَّز في محرّكات نطاق متفرّقة
(مثل core/engines/soil_lab_workflow.py: SOIL_TEST_TRANSITIONS). لا يوجد **كتالوج واحد**
يُعرّف ما هي سير العمل المتاحة في المنصّة، ومراحلها، وأيّها نهائيّ. هذا الملف يحوّل
**وصف سير العمل** إلى بيانات (metadata) لا كود: كلّ سير عمل يُعلَن مرّة واحدة هنا
(المعرّف، الأسماء، المراحل، الانتقالات، المراحل النهائيّة، الوصف).

التمييز المهمّ: هذا **سجلّ تعريفات** (catalog) لا **محرّك تنفيذ**. التنفيذ يبقى في
core/workflow_engine.py (Saga: استئناف/تعليق/تعويض) ومحرّكات النطاق. هنا نُوحّد الوصف
فقط — أيّ سير عمل موجود، وما مراحله — لتقرأه طبقة الواجهة/الاستبطان دون تكرار.

نطاق هذا الإصدار (PR): يُسلّم **السجلّ + البيانات الوصفيّة** فقط. ربط التعريفات بمحرّك
التنفيذ الفعليّ (توليد WorkflowStep من تعريف، وقيادة الانتقالات منه) **متابعة لاحقة**.

أمانة البيانات: مراحل وانتقالات سير عمل فحص التربة مأخوذة حرفيّاً من
core/engines/soil_lab_workflow.py (SoilTestStatus + SOIL_TEST_TRANSITIONS). سير عمل
الصمّام مؤرَّض على حالة الصمّام open/closed (main.py) وactuator-service (open↔close).
لا نخترع مراحل لا مصدر لها في النموذج القائم.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WorkflowDefinition:
    """تعريف سير عمل واحد مُعلَن كبيانات — وحدة كتالوج واحدة (declare-a-workflow).

    - `id`: معرّف ثابت قابل للبرمجة (مثل "soil_lab_test").
    - `name_ar`: اسم معروض بالعربيّة.
    - `stages`: المراحل بترتيبها المنطقيّ (مثل ("requested", "sampled", ...)).
    - `initial`: المرحلة الابتدائيّة (أوّل عنصر في stages عادةً).
    - `terminal`: المراحل النهائيّة التي لا انتقال بعدها.
    - `transitions`: خريطة المرحلة → المراحل المسموح الانتقال إليها (تطابق محرّك النطاق).
    - `description_ar`: وصف موجز + تأريض المصدر في محرّك النطاق القائم.
    """

    id: str
    name_ar: str
    stages: tuple[str, ...]
    initial: str
    terminal: tuple[str, ...]
    transitions: dict[str, tuple[str, ...]] = field(default_factory=dict)
    description_ar: str = ""

    def as_dict(self) -> dict:
        """تشكيل JSON لطبقة الـAPI (الصفوف tuple تُسلسَل قوائمَ)."""
        return {
            "id": self.id,
            "name_ar": self.name_ar,
            "stages": list(self.stages),
            "initial": self.initial,
            "terminal": list(self.terminal),
            "transitions": {k: list(v) for k, v in self.transitions.items()},
            "description_ar": self.description_ar,
        }


# ── السجلّ المركزيّ: مصدر واحد لتعريفات سير العمل ─────────────────────
# كلّ مدخل مؤرَّض على محرّك النطاق المقابل؛ لا نخترع مراحل لا مصدر لها.
_REGISTRY: dict[str, WorkflowDefinition] = {
    # فحص التربة المخبري — مؤرَّض حرفيّاً على core/engines/soil_lab_workflow.py
    # (SoilTestStatus + SOIL_TEST_TRANSITIONS). نهائيّ: published/cancelled.
    "soil_lab_test": WorkflowDefinition(
        id="soil_lab_test",
        name_ar="فحص التربة المخبري",
        stages=(
            "requested",
            "sampled",
            "in_lab",
            "result_received",
            "approved",
            "published",
            "rejected",
            "cancelled",
        ),
        initial="requested",
        terminal=("published", "cancelled"),
        transitions={
            "requested": ("sampled", "cancelled"),
            "sampled": ("in_lab", "cancelled"),
            "in_lab": ("result_received", "cancelled"),
            "result_received": ("approved", "rejected"),
            "approved": ("published",),
            "rejected": ("in_lab", "cancelled"),
            "published": (),
            "cancelled": (),
        },
        description_ar=(
            "دورة حياة فحص التربة من الطلب إلى النشر — مؤرَّضة حرفيّاً على "
            "soil_lab_workflow.SOIL_TEST_TRANSITIONS. لا اعتماد/نشر بلا نتيجة مختبر "
            "(invariant في المحرّك). published/cancelled نهائيّتان."
        ),
    ),
    # تشغيل صمّام الريّ — مؤرَّض على حالة الصمّام open/closed (main.py)
    # وactuator-service (_INVERSE_COMMANDS: open↔close). دورة قابلة للعكس (لا نهائيّ).
    "valve_actuation": WorkflowDefinition(
        id="valve_actuation",
        name_ar="تشغيل صمّام الريّ",
        stages=("closed", "opening", "open", "closing"),
        initial="closed",
        terminal=(),
        transitions={
            "closed": ("opening",),
            "opening": ("open",),
            "open": ("closing",),
            "closing": ("closed",),
        },
        description_ar=(
            "دورة فتح/إغلاق صمّام الريّ عبر أوامر MQTT. الحالتان open/closed مؤرَّضتان "
            "على main.py (ValveStateRequest) وactuator-service (open↔close). دورة قابلة "
            "للعكس بلا حالة نهائيّة — الصمّام يُفتَح ويُغلَق متكرّراً."
        ),
    ),
    # تصعيد القرار للبشر — مؤرَّض على core/engines/human_escalation.py
    # (none/review/blocked). يُستخدم حين يحتاج القرار مراجعة/موافقة بشريّة.
    "human_escalation": WorkflowDefinition(
        id="human_escalation",
        name_ar="تصعيد القرار للمراجعة البشريّة",
        stages=("none", "review", "blocked", "approved", "rejected"),
        initial="none",
        terminal=("approved", "rejected"),
        transitions={
            "none": ("review", "blocked"),
            "review": ("approved", "rejected"),
            "blocked": ("review",),
            "approved": (),
            "rejected": (),
        },
        description_ar=(
            "مسار تصعيد قرار ذي أثر (دفع/رشّ) لمراجعة بشريّة — مؤرَّض على "
            "human_escalation (none/review/blocked). review→approved/rejected. "
            "approved/rejected نهائيّتان."
        ),
    ),
}


def list_workflows() -> list[dict]:
    """كلّ تعريفات سير العمل المُعلَنة كقوائم dict (لطبقة الـAPI)، بترتيب الإدراج."""
    return [wf.as_dict() for wf in _REGISTRY.values()]


def get_workflow(id: str) -> dict | None:
    """تعريف سير العمل بمعرّفه كـdict، أو None إن لم يكن مُعلَناً."""
    wf = _REGISTRY.get(id)
    return wf.as_dict() if wf is not None else None


def known_workflow_ids() -> list[str]:
    """معرّفات سير العمل المُعلَنة، بترتيب الإدراج."""
    return list(_REGISTRY.keys())
