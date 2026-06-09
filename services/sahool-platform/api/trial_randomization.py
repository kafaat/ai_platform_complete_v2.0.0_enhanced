"""
api/trial_randomization.py — توليد عشوائي حتمي للتجارب الميدانيّة (قابل للتحقّق)

خارطة الطريق: تمهيد للبند ١١ (محرّك التجارب المقترنة).

مُستلهَم ومُكيَّف من كود مرفوع (sahool_unified_v16_fixed) — لكن **استُخرِج
المنطق النقي فقط** بعد إزالة طبقة SQLAlchemy/async/event_store التي لا تلائم
بنية سهول. الفكرة القيّمة: بدل `np.random.seed(timestamp)` الساذج، نشتقّ
البذرة من hash حتمي يتيح:
  • إعادة توليد التوزيع نفسه بالضبط (reproducibility)
  • كشف التلاعب (tamper detection) عبر seed_hash
  • تسجيل المصدر في data_lineage (provenance)

هذا يجسّد مبدأ "الصدق الإحصائي": التوزيع العشوائي ليس صندوقاً أسود — بل
قابل للتدقيق والإعادة.

⚠ هذا منطق توزيع فقط؛ التحليل الإحصائي (t-test/LSD) يأتي في البند ١١ نفسه.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from typing import Any

SeedSource = str  # "user_provided" | "hash_chain" | "uuid_v4"


@dataclass(frozen=True)
class RandomizationConfig:
    """إعداد ثابت للتوزيع الحتمي."""

    trial_id: str
    num_blocks: int
    seed_source: SeedSource = "hash_chain"
    seed_value: int | None = None  # لـuser_provided
    hash_chain_input: str | None = None  # لـhash_chain

    def to_canonical(self) -> str:
        """تمثيل قانوني (لإعادة الإنتاج + التدقيق)."""
        return json.dumps(
            {
                "trial_id": self.trial_id,
                "num_blocks": self.num_blocks,
                "seed_source": self.seed_source,
                "seed_value": self.seed_value,
                "hash_chain_input": self.hash_chain_input,
            },
            sort_keys=True,
            ensure_ascii=False,
        )


@dataclass
class BlockAssignment:
    """توزيع كتلة واحدة (معالجة شمال/جنوب) + hash للتحقّق."""

    block_number: int
    treatment_position: str  # "north" | "south"
    control_position: str
    block_seed: int
    seed_hash: str  # لكشف التلاعب

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_number": self.block_number,
            "treatment_position": self.treatment_position,
            "control_position": self.control_position,
            "block_seed": self.block_seed,
            "seed_hash": self.seed_hash,
        }


@dataclass
class RandomizationResult:
    master_seed: int
    master_seed_hash: str
    config_canonical: str
    blocks: list[BlockAssignment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "master_seed_hash": self.master_seed_hash,  # لا نكشف البذرة الخام
            "config_canonical": self.config_canonical,
            "blocks": [b.to_dict() for b in self.blocks],
        }


def _compute_master_seed(config: RandomizationConfig) -> int:
    """يشتقّ البذرة الرئيسيّة من المصدر."""
    if config.seed_source == "user_provided":
        if config.seed_value is None:
            raise ValueError("seed_value مطلوب لـuser_provided")
        return config.seed_value
    if config.seed_source == "hash_chain":
        if not config.hash_chain_input:
            raise ValueError("hash_chain_input مطلوب لـhash_chain")
        return int(hashlib.sha256(config.hash_chain_input.encode()).hexdigest(), 16)
    if config.seed_source == "uuid_v4":
        import uuid

        return uuid.uuid4().int
    raise ValueError(f"seed_source غير معروف: {config.seed_source}")


def generate_block_assignments(config: RandomizationConfig) -> RandomizationResult:
    """يولّد توزيعاً حتميّاً قابلاً للتحقّق للكتل.

    يحتاج ≥4 كتل (معيار الصحّة الإحصائيّة — SARE).
    """
    if config.num_blocks < 4:
        raise ValueError("الحدّ الأدنى ٤ كتل للصحّة الإحصائيّة (تقسيم الحقل لنصفَين غير صالح)")

    master_seed = _compute_master_seed(config)
    master_seed_hash = hashlib.sha256(str(master_seed).encode()).hexdigest()

    blocks: list[BlockAssignment] = []
    for block_number in range(1, config.num_blocks + 1):
        # بذرة كلّ كتلة مشتقّة حتميّاً من الرئيسيّة + رقم الكتلة + معرّف التجربة
        block_seed_input = f"{master_seed}:{block_number}:{config.trial_id}"
        block_seed = int(hashlib.sha256(block_seed_input.encode()).hexdigest(), 16) % (2**32)

        rng = random.Random(block_seed)
        treatment_is_north = rng.choice([True, False])

        seed_hash = hashlib.sha256(
            f"{block_seed}:{block_number}:{treatment_is_north}".encode()
        ).hexdigest()

        blocks.append(
            BlockAssignment(
                block_number=block_number,
                treatment_position="north" if treatment_is_north else "south",
                control_position="south" if treatment_is_north else "north",
                block_seed=block_seed,
                seed_hash=seed_hash,
            )
        )

    return RandomizationResult(
        master_seed=master_seed,
        master_seed_hash=master_seed_hash,
        config_canonical=config.to_canonical(),
        blocks=blocks,
    )


def verify_assignment(block: BlockAssignment) -> bool:
    """يتحقّق أنّ كتلة لم تُلاعَب (يعيد حساب الـhash)."""
    treatment_is_north = block.treatment_position == "north"
    expected = hashlib.sha256(
        f"{block.block_seed}:{block.block_number}:{treatment_is_north}".encode()
    ).hexdigest()
    return expected == block.seed_hash
