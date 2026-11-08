"""S15 (audit 2026-11-01) — supervisor intent routing is linear in the query length.

**Fault on origin/main cc0d2e295:** ``services/supervisor-agent/router.py`` joined every keyword
pattern into ``(?<!\\w)(?:…|head.*tail|…)(?!\\w)`` and ran it with ``re.search`` on the raw,
unbounded query. ``re.search`` retries ``head.*tail`` from every ``head`` and each ``.*`` runs to the
end of the line: quadratic. Measured: 160 KB of «صحة » = 17 s, 200 KB of «what » = 8.6 s, holding a
worker of ``/v1/agent/query``.

**Fix:** the query is cut to ``MAX_ROUTED_QUERY_CHARS`` before matching, and ``head.*tail`` is
matched as one search for the leftmost ``head`` then one search for ``tail`` after it, per line.

① 200 KB adversarial inputs finish in < 0.5 s (via ``classify_intent`` and via ``_matches``
   without the length bound). ② Routing of the existing examples is unchanged (table taken from
   origin/main). ③ ``_matches`` agrees with the original regex on random keyword soups.
"""

from __future__ import annotations

import asyncio
import importlib.util
import random
import re
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "services" / "supervisor-agent" / "router.py"


@pytest.fixture(scope="module")
def router_mod():
    spec = importlib.util.spec_from_file_location("supervisor_router_s15", ROUTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _classify(mod, query):
    return asyncio.run(mod.HierarchicalRouter({}).classify_intent(query))


def _all_patterns(mod):
    r = mod.HierarchicalRouter({})
    return [p for ps in r.domain_patterns.values() for p in ps] + [
        p for d in r.sub_intent_patterns.values() for p in d.values()
    ]


def _reference_matches(pattern: str, query: str) -> bool:
    """origin/main's ``_matches`` verbatim — the oracle, safe only on short inputs."""
    alternatives = []
    for term in pattern.split("|"):
        if re.fullmatch(r"[ء-ي]+", term):
            term = "(?:ال)?" + term
        alternatives.append(term)
    return re.search(r"(?<!\w)(?:" + "|".join(alternatives) + r")(?!\w)", query) is not None


# ── ① no catastrophic backtracking ───────────────────────────────────────────

ADVERSARIAL = {
    "sahha": "صحة " * 50_000,
    "what": "what " * 40_000,
    "hala": "حالة " * 50_000,
    "before": "before " * 28_600,
    "mixed": ("صحة what قبل احتياج full " * 8_000),
    "one_line_letters": "a" * 200_000,
}


@pytest.mark.parametrize("name", sorted(ADVERSARIAL))
def test_200kb_adversarial_query_routes_in_under_half_a_second(router_mod, name):
    query = ADVERSARIAL[name]
    assert len(query.encode("utf-8")) >= 200_000 or len(query) >= 200_000
    started = time.perf_counter()
    domain, sub, confidence = _classify(router_mod, query)
    elapsed = time.perf_counter() - started
    assert elapsed < 0.5, f"{name}: {elapsed:.2f}s"
    assert domain and sub and 0 <= confidence <= 1


@pytest.mark.parametrize("name", ["sahha", "what", "mixed"])
def test_matching_itself_is_linear_without_the_length_bound(router_mod, name):
    """The bound is a second wall, not the fix: ``_matches`` alone stays linear on 200 KB."""
    query = router_mod._normalize(ADVERSARIAL[name])
    for pattern in _all_patterns(router_mod):
        started = time.perf_counter()
        router_mod._matches(router_mod._normalize(pattern), query)
        elapsed = time.perf_counter() - started
        assert elapsed < 0.5, f"{name}: {elapsed:.2f}s on {pattern[:40]!r}"


def test_query_is_bounded_before_matching(router_mod):
    assert 0 < router_mod.MAX_ROUTED_QUERY_CHARS <= 16_384
    tail_only = "x " * router_mod.MAX_ROUTED_QUERY_CHARS + "ما سعر القمح"
    assert _classify(router_mod, tail_only)[:2] == ("advisory", "general_advice")


def test_a_term_with_repeated_quantifiers_is_refused(router_mod):
    for bad in ("a.*b.*c", "(?:ab)+.*c", "a.*b+"):
        with pytest.raises(ValueError):
            router_mod._compile(bad)


# ── ② routing unchanged (expected values measured on origin/main) ─────────────

ROUTING_TABLE = [
    ("ما هو NDVI لحقلي؟", "remote_sensing", "ndvi"),
    ("ما سعر القمح في السوق؟", "market", "price_current"),
    ("لدي آفة في الحقل ماذا أفعل؟", "advisory", "pest_id"),
    ("متى أسقي المحصول؟", "crop_model", "irrigation_advice"),
    ("نموذج محاكاة الإنتاج", "crop_model", "simulate_current"),
    ("show me NDVI for my field", "remote_sensing", "ndvi"),
    ("what is the market price", "market", "price_current"),
    ("irrigation schedule for my crop", "crop_model", "irrigation_advice"),
    ("مرحبا كيف حالك", "advisory", "general_advice"),
    ("مرحبا", "advisory", "general_advice"),
    ("market price for wheat", "market", "price_current"),
    ("كم احتياج الري لحقل القمح؟", "crop_model", "irrigation_advice"),
    ("توقع محصول القمح لهذا الموسم", "crop_model", "simulate_current"),
    ("اعرض مؤشر NDVI للحقل", "remote_sensing", "ndvi"),
    ("متى أروي القمح؟", "crop_model", "irrigation_advice"),
    ("متى أَرْوِي القمح؟", "crop_model", "irrigation_advice"),
    ("متى أــروي القمح؟", "crop_model", "irrigation_advice"),
    ("ما حالة النمو في حقلي؟", "remote_sensing", "full_analysis"),
    ("ظهرت بقع صفراء على القمح", "advisory", "disease_id"),
    ("مرض مع بقع صفراء على القمح", "advisory", "disease_id"),
    ("الرياح قوية اليوم", "advisory", "general_advice"),
    ("حالة حقل متضرر بسبب الرياح", "remote_sensing", "full_analysis"),
    ("ما سعر القمح الشهر القادم؟", "market", "price_forecast"),
    ("توقع سعر القمح الشهر القادم", "market", "price_forecast"),
    ("what is the wheat price next month?", "market", "price_forecast"),
    ("ما تحليل NDVI", "remote_sensing", "ndvi"),
    ("تحليل", "advisory", "general_advice"),
    ("زراعة قمح", "advisory", "general_advice"),
    ("ري ذكي", "crop_model", "irrigation_advice"),
    ("تسميد", "crop_model", "fertilizer_advice"),
    ("حصاد", "advisory", "general_advice"),
    ("what should I do about this", "advisory", "pest_id"),
    ("full analysis of the farm satellite", "remote_sensing", "full_analysis"),
    ("compare before and after the storm", "advisory", "general_advice"),
    ("how much water need for my wheat", "advisory", "general_advice"),
    ("sell before harvest to a buyer", "market", "create_contract"),
    ("photo of a pest on the leaf", "advisory", "pest_id"),
    ("best practice to improve yield", "crop_model", "simulate_current"),
    ("صورة فضائية للحقل", "remote_sensing", "full_analysis"),
    ("كتلة حيوية عالية", "crop_model", "simulate_current"),
    ("احتياجات مائية للقمح", "crop_model", "irrigation_advice"),
    ("حاجة المياه في الصيف", "crop_model", "irrigation_advice"),
    ("هل يرتفع سعر الطماطم؟", "market", "price_forecast"),
    ("بيع المحصول قبل الحصاد", "market", "create_contract"),
    ("كيف أحسن التربة", "advisory", "general_advice"),
    ("أفضل ممارسة للتسميد", "advisory", "general_advice"),
    ("ما هذا على الورقة؟", "advisory", "general_advice"),
    ("when to fertilize wheat", "advisory", "general_advice"),
    ("متى أسمد النخيل", "advisory", "general_advice"),
    ("صحة حقلي", "remote_sensing", "full_analysis"),
    ("حالة\nحقلي", "advisory", "general_advice"),
    ("what\ndo", "advisory", "general_advice"),
]


@pytest.mark.parametrize("query,domain,sub", ROUTING_TABLE, ids=range(len(ROUTING_TABLE)))
def test_routing_of_existing_examples_is_unchanged(router_mod, query, domain, sub):
    assert _classify(router_mod, query)[:2] == (domain, sub)


# ── ③ same language as the original regex ────────────────────────────────────


def _vocabulary(mod):
    words = set()
    for pattern in _all_patterns(mod):
        for piece in re.split(r"\.\*|\||\(\?:|\)\??", pattern):
            if piece:
                words.add(piece)
    return sorted(words) + ["ال", "ي", "ة", "x", "حقلين", "?", ",", "\n", "", "  "]


def test_matches_agrees_with_the_original_regex_on_random_keyword_soups(router_mod):
    rng = random.Random(15)
    vocab = _vocabulary(router_mod)
    patterns = [router_mod._normalize(p) for p in _all_patterns(router_mod)]
    for _ in range(3000):
        tokens = [rng.choice(vocab) for _ in range(rng.randint(1, 8))]
        joiners = [rng.choice([" ", "", "\n", "-", "ال"]) for _ in tokens]
        query = router_mod._normalize("".join(t + j for t, j in zip(tokens, joiners, strict=True)))
        for pattern in patterns:
            assert router_mod._matches(pattern, query) is _reference_matches(pattern, query), (
                pattern,
                query,
            )
