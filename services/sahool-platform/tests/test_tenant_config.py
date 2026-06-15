"""اختبارات تكوين المستأجِر (api.tenant_config) — منطق نقيّ بحت.

يغطّي مُحلِّل الدمج `merge_tenant_config`: الافتراضات عند غياب التخصيص، التركيب
الجزئيّ (overlay) لمفتاح فرعيّ واحد دون مساس بالبقيّة، تجاهل المفاتيح المجهولة،
والصمود أمام المُدخل المُشوَّه (تدهور رشيق ⇒ افتراضات آمنة، لا استثناء).
لا حاجة لقاعدة أو شبكة — كلّ شيء offline. مسار القاعدة (GET endpoint) يُغطّى
بتكامل CI لا هنا.
"""

from api.tenant_config import DEFAULTS, merge_tenant_config


def test_none_returns_defaults_distinct_copy():
    """None ⇒ نسخة مطابقة عميقاً للافتراضات، لكنّها كائن مستقلّ (لا طفرة للأصل)."""
    result = merge_tenant_config(None)
    assert result == DEFAULTS
    # كائن مختلف على المستويين العلويّ والمتداخل (نسخة عميقة لا مرجع مشترك).
    assert result is not DEFAULTS
    assert result["branding"] is not DEFAULTS["branding"]
    # الطفرة في الناتج لا تلوّث الافتراضات العالميّة.
    result["branding"]["primary_color"] = "#000"
    assert DEFAULTS["branding"]["primary_color"] == "#2e7d32"


def test_partial_override_only_that_subkey():
    """تخصيص جزئيّ للون فقط ⇒ يُغيّره ويُبقي بقيّة branding على الافتراضات."""
    result = merge_tenant_config({"branding": {"primary_color": "#111"}})
    assert result["branding"]["primary_color"] == "#111"
    # المفاتيح الفرعيّة الأخرى لـbranding سليمة على افتراضاتها.
    assert result["branding"]["logo_url"] == DEFAULTS["branding"]["logo_url"]
    assert result["branding"]["name_ar"] == DEFAULTS["branding"]["name_ar"]
    # المفاتيح العلويّة الأخرى لم تُمَسّ.
    assert result["units"] == DEFAULTS["units"]
    assert result["language"] == DEFAULTS["language"]
    assert result["crops"] == DEFAULTS["crops"]


def test_simple_top_keys_override():
    """مفاتيح بسيطة (language/crops) تُستبدَل قيمتها كاملةً."""
    result = merge_tenant_config({"language": "en", "crops": ["wheat", "coffee"]})
    assert result["language"] == "en"
    assert result["crops"] == ["wheat", "coffee"]
    # branding/units تبقى على الافتراضات.
    assert result["branding"] == DEFAULTS["branding"]
    assert result["units"] == DEFAULTS["units"]


def test_unknown_keys_ignored():
    """المفاتيح المجهولة — علويّة وفرعيّة — تُتجاهَل بأمان دون تسرّب للناتج."""
    result = merge_tenant_config(
        {
            "evil": "x",  # مفتاح علويّ مجهول
            "branding": {"primary_color": "#abc", "hacker": "y"},  # فرعيّ مجهول
        }
    )
    assert "evil" not in result
    assert "hacker" not in result["branding"]
    assert result["branding"]["primary_color"] == "#abc"
    # شكل الناتج محصور في المفاتيح المعروفة فقط.
    assert set(result.keys()) == set(DEFAULTS.keys())


def test_malformed_input_returns_safe_defaults():
    """مُدخل مُشوَّه ⇒ افتراضات آمنة دون استثناء (دالّة نقيّة دفاعيّة)."""
    # نوع غير قاموسيّ بالكامل.
    assert merge_tenant_config("x") == DEFAULTS
    assert merge_tenant_config(5) == DEFAULTS
    assert merge_tenant_config([1, 2]) == DEFAULTS
    # قاموس متداخل بنوع مُشوَّه (units=5) ⇒ يُبقي افتراضات units سليمة.
    result = merge_tenant_config({"units": 5})
    assert result["units"] == DEFAULTS["units"]
    assert result == DEFAULTS
