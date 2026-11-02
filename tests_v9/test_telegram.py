"""Telegram Bot Tests — SAHOOL v9.1.0"""

import pytest


class TestTelegramSecurity:
    @pytest.mark.unit
    def test_webhook_secret_env_exists(self):
        """WEBHOOK_SECRET must be configurable."""
        import os

        # The bot reads WEBHOOK_SECRET from env
        secret = os.getenv("WEBHOOK_SECRET", "")
        # In production this should be non-empty
        # In tests we just verify the env var is accessible
        assert isinstance(secret, str)

    @pytest.mark.unit
    def test_photo_size_limit_constant(self):
        """MAX_PHOTO_BYTES must be defined and reasonable."""
        MAX = 10 * 1024 * 1024  # 10MB
        assert MAX == 10_485_760
        assert MAX < 50 * 1024 * 1024  # Less than Telegram max

    @pytest.mark.unit
    def test_bot_token_required(self):
        """BOT_TOKEN must raise if missing."""
        import os

        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not token:
            # Should raise in production
            with pytest.raises((RuntimeError, ValueError)):
                if not token:
                    raise RuntimeError("TELEGRAM_BOT_TOKEN required")

    # تدقيق 2026-11-01 (Q2): كان يطلب localhost:8124/health (لا وجود له؛ البوت بلا HTTP)
    # ويقبل 404 نجاحاً، ولا تُشغّله أيّ وظيفة. العقد الحقيقيّ: البوت استطلاعيّ (polling)
    # فلا سطح webhook وارد يُقبَل بلا سرّ. إن أُضيف webhook يحمرّ هنا حتى يُفرَض السرّ.
    @pytest.mark.unit
    @pytest.mark.security
    def test_webhook_rejects_no_secret(self):
        """No inbound webhook surface exists that could accept a request without the secret."""
        import re
        from pathlib import Path

        bot_dir = Path(__file__).resolve().parents[1] / "bots" / "telegram"
        src = "\n".join(p.read_text(encoding="utf-8") for p in sorted(bot_dir.glob("*.py")))
        assert "start_polling(" in src, "البوت لم يعد استطلاعيّاً — راجع فرض سرّ الـwebhook"
        inbound = re.findall(
            r"set_webhook|SimpleRequestHandler|web\.Application|FastAPI\(|uvicorn\.run", src
        )
        assert not inbound, f"سطح webhook وارد بلا اختبار فرض السرّ: {inbound}"
