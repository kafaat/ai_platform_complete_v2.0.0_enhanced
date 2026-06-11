"""اختبارات توجيه التنبيهات إلى القنوات (api.alert_delivery) — منطق صرف offline.

يغطّي: تفعيل/تعطيل كلّ قناة، أرضيّة الخطورة (SMS/واتساب 'critical' فقط)، ترشيح
نوع الحدث، صياغة الرسالة العربيّة لكلّ قناة، وعلَم deliverable عند غياب العنوان،
والمُرسِل الوهميّ (stub) + حقن مُرسِل بديل. لا حاجة لقاعدة أو شبكة.
"""

from api.alert_delivery import (
    DEFAULT_SEVERITY_FLOOR,
    AlertInput,
    ChannelMessage,
    NotificationPrefs,
    deliver,
    plan_delivery,
    select_channels,
    stub_sender,
)


def _alert(alert_type="disease_risk", severity="critical", **kw):
    return AlertInput(alert_type=alert_type, severity=severity, **kw)


def _channels(prefs, alert):
    return {m.channel for m in select_channels(prefs, alert)}


# ─── تفعيل/تعطيل القنوات ──────────────────────────────────────────
class TestChannelToggles:
    def test_all_disabled_selects_nothing(self):
        prefs = NotificationPrefs()  # كلّ القنوات مُعطَّلة افتراضيّاً
        assert select_channels(prefs, _alert()) == []

    def test_email_only_when_enabled(self):
        prefs = NotificationPrefs(email_enabled=True, email_address="a@b.ye")
        assert _channels(prefs, _alert(severity="info")) == {"email"}

    def test_push_only_when_enabled(self):
        prefs = NotificationPrefs(push_enabled=True, push_token="tok")
        assert _channels(prefs, _alert(severity="info")) == {"push"}

    def test_sms_only_when_enabled(self):
        prefs = NotificationPrefs(sms_enabled=True, sms_number="+9677")
        assert _channels(prefs, _alert(severity="critical")) == {"sms"}

    def test_whatsapp_only_when_enabled(self):
        prefs = NotificationPrefs(whatsapp_enabled=True, whatsapp_number="+9677")
        assert _channels(prefs, _alert(severity="critical")) == {"whatsapp"}

    def test_multiple_channels_selected_together(self):
        prefs = NotificationPrefs(
            email_enabled=True,
            email_address="a@b.ye",
            sms_enabled=True,
            sms_number="+9677",
            push_enabled=True,
            push_token="tok",
            whatsapp_enabled=True,
            whatsapp_number="+9678",
        )
        assert _channels(prefs, _alert(severity="critical")) == {
            "email",
            "sms",
            "push",
            "whatsapp",
        }

    def test_disabled_channel_excluded_even_with_address(self):
        # العنوان مضبوط لكن القناة مُعطَّلة ⇒ لا تُختار.
        prefs = NotificationPrefs(email_enabled=False, email_address="a@b.ye")
        assert _channels(prefs, _alert()) == set()


# ─── أرضيّة الخطورة (severity floor) ──────────────────────────────
class TestSeverityFloor:
    def _all_on(self, **kw):
        return NotificationPrefs(
            email_enabled=True,
            email_address="a@b.ye",
            push_enabled=True,
            push_token="tok",
            sms_enabled=True,
            sms_number="+9677",
            whatsapp_enabled=True,
            whatsapp_number="+9678",
            **kw,
        )

    def test_info_only_email_and_push(self):
        # info دون أرضيّة SMS/واتساب (critical) ⇒ بريد/Push فقط.
        assert _channels(self._all_on(), _alert(severity="info")) == {
            "email",
            "push",
        }

    def test_warning_still_excludes_sms_and_whatsapp(self):
        # warning < critical ⇒ SMS/واتساب لا يزالان مُستبعَدين.
        assert _channels(self._all_on(), _alert(severity="warning")) == {
            "email",
            "push",
        }

    def test_critical_reaches_all_channels(self):
        assert _channels(self._all_on(), _alert(severity="critical")) == {
            "email",
            "push",
            "sms",
            "whatsapp",
        }

    def test_sms_floor_is_critical(self):
        assert DEFAULT_SEVERITY_FLOOR["sms"] == "critical"
        assert DEFAULT_SEVERITY_FLOOR["whatsapp"] == "critical"
        assert DEFAULT_SEVERITY_FLOOR["email"] == "info"
        assert DEFAULT_SEVERITY_FLOOR["push"] == "info"

    def test_user_min_severity_raises_floor(self):
        # المستخدم يرفع الأرضيّة العامّة إلى warning ⇒ يُسقِط info عن كلّ القنوات.
        prefs = self._all_on(min_severity="warning")
        assert _channels(prefs, _alert(severity="info")) == set()
        assert _channels(prefs, _alert(severity="warning")) == {"email", "push"}

    def test_user_min_severity_never_lowers_channel_floor(self):
        # min_severity=info لا يخفّض أرضيّة SMS (تبقى critical).
        prefs = self._all_on(min_severity="info")
        assert "sms" not in _channels(prefs, _alert(severity="warning"))

    def test_unknown_severity_treated_as_lowest(self):
        # خطورة غير معروفة لا تتجاوز أيّ أرضيّة فوق info.
        assert _channels(self._all_on(), _alert(severity="bogus")) == {
            "email",
            "push",
        }


# ─── ترشيح نوع الحدث (event_types) ────────────────────────────────
class TestEventTypeFilter:
    def _all_on(self, **kw):
        return NotificationPrefs(email_enabled=True, email_address="a@b.ye", **kw)

    def test_none_event_types_allows_all(self):
        prefs = self._all_on(event_types=None)
        assert _channels(prefs, _alert(alert_type="heat_stress")) == {"email"}

    def test_matching_event_type_passes(self):
        prefs = self._all_on(event_types=["disease_risk", "frost_risk"])
        assert _channels(prefs, _alert(alert_type="disease_risk")) == {"email"}

    def test_non_matching_event_type_filtered_out(self):
        prefs = self._all_on(event_types=["frost_risk"])
        assert select_channels(prefs, _alert(alert_type="disease_risk")) == []

    def test_empty_event_types_filters_everything(self):
        prefs = self._all_on(event_types=[])
        assert select_channels(prefs, _alert(alert_type="disease_risk")) == []


# ─── صياغة الرسالة العربيّة ───────────────────────────────────────
class TestRendering:
    def test_email_body_includes_severity_and_title(self):
        prefs = NotificationPrefs(email_enabled=True, email_address="a@b.ye")
        msgs = select_channels(
            prefs,
            _alert(severity="info", title_ar="رطوبة منخفضة", message_ar="اسقِ الحقل"),
        )
        body = msgs[0].body_ar
        assert "معلومة" in body
        assert "رطوبة منخفضة" in body
        assert "اسقِ الحقل" in body

    def test_sms_body_is_single_line_compact(self):
        prefs = NotificationPrefs(sms_enabled=True, sms_number="+9677")
        msgs = select_channels(
            prefs,
            _alert(severity="critical", title_ar="صقيع", message_ar="غطِّ المحصول"),
        )
        line = msgs[0].body_ar
        assert "\n" not in line
        assert "حرِج" in line
        assert "صقيع" in line

    def test_default_title_when_missing(self):
        prefs = NotificationPrefs(push_enabled=True, push_token="tok")
        msgs = select_channels(prefs, _alert(severity="warning", title_ar=None))
        assert msgs[0].title_ar  # عنوان افتراضيّ غير فارغ
        assert "تحذير" in msgs[0].title_ar


# ─── علَم deliverable + المُرسِل ──────────────────────────────────
class TestDeliverability:
    def test_enabled_without_address_is_not_deliverable(self):
        # المستخدم فعّل البريد بلا عنوان ⇒ يُختار لكن غير قابل للتسليم (صدق).
        prefs = NotificationPrefs(email_enabled=True, email_address=None)
        msgs = select_channels(prefs, _alert(severity="info"))
        assert len(msgs) == 1
        assert msgs[0].deliverable is False

    def test_blank_address_is_not_deliverable(self):
        prefs = NotificationPrefs(email_enabled=True, email_address="   ")
        msgs = select_channels(prefs, _alert(severity="info"))
        assert msgs[0].deliverable is False

    def test_valid_address_is_deliverable(self):
        prefs = NotificationPrefs(email_enabled=True, email_address="a@b.ye")
        msgs = select_channels(prefs, _alert(severity="info"))
        assert msgs[0].deliverable is True

    def test_stub_sender_reports_logged_not_sent(self):
        msg = ChannelMessage(
            channel="email",
            severity="info",
            recipient="a@b.ye",
            title_ar="t",
            body_ar="b",
        )
        channel, ok, detail = stub_sender(msg)
        assert channel == "email"
        assert ok is True
        assert "إرسال فعليّ" in detail  # لا يزعم إرسالاً حقيقيّاً

    def test_stub_sender_fails_on_missing_recipient(self):
        msg = ChannelMessage(
            channel="sms",
            severity="critical",
            recipient=None,
            title_ar="t",
            body_ar="b",
        )
        _, ok, _ = stub_sender(msg)
        assert ok is False


# ─── plan_delivery / deliver (حقن مُرسِل) ─────────────────────────
class TestDeliveryPlan:
    def test_plan_delivery_has_messages_no_results(self):
        prefs = NotificationPrefs(email_enabled=True, email_address="a@b.ye")
        plan = plan_delivery(prefs, _alert(severity="info"))
        assert len(plan.messages) == 1
        assert plan.results == []
        assert plan.deliverable_count == 1

    def test_deliver_uses_injected_sender(self):
        prefs = NotificationPrefs(
            email_enabled=True,
            email_address="a@b.ye",
            push_enabled=True,
            push_token="tok",
        )
        seen: list[str] = []

        def fake_sender(m):
            seen.append(m.channel)
            return (m.channel, True, "ok")

        plan = deliver(prefs, _alert(severity="info"), sender=fake_sender)
        assert seen == ["email", "push"]
        assert all(ok for _, ok, _ in plan.results)

    def test_deliver_default_stub_sender(self):
        prefs = NotificationPrefs(email_enabled=True, email_address="a@b.ye")
        plan = deliver(prefs, _alert(severity="info"))
        assert len(plan.results) == 1
        assert plan.results[0][0] == "email"
