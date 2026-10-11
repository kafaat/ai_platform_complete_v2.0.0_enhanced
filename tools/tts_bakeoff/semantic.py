"""مرجعٌ دلاليّ مستقلّ: هل **اجتاز** النصُّ (خاماً أو بعد محوّل) فحوصَ الحقائق المعلنة لجملته؟

لا يُثبت «حفظ المعنى» كاملاً — يُثبت أنّ ما أُعلن من حقائق موجودٌ ومربوطٌ كما أُعلن، ويُسجّل ما لم
تُغطِّه أيُّ حقيقة (``coverage``) كي يُرى حدُّه لا يُفترض.

المحلّلُ مكتوبٌ مستقلّاً عن أيّ محوّلٍ يُختبر — لا يستعمل ``parse.py`` في arabic-tts-frontend ولا
``num2words``. والحقائقُ في ``semantic_facts.json`` مكتوبةٌ يدويّاً من الجملة الأصليّة.

ما يُفحص لكلّ جملة (كلُّ ما أُعلن لها):
  • **الكمّيّات بالترتيب:** القيمةُ العشريّة (Decimal، فـ2.5 = 2.50)، والوحدة، والمقام (``لكل لتر``)،
    والحدّ (``أقل من`` · ``أكثر من`` · ``قبل مرور`` · ``خلال`` · ``كل`` · ``من``/``إلى``/``حتى``)،
    و**المُسنَد إليه** (``رطوبة التربة ٢٢٪`` لا ``نقطة الذبول ٢٢٪``). وأيُّ كمّيّةٍ زائدة تُفشل.
  • **الأفعال وقطبيّتها:** كلُّ ظهورٍ لصيغ الفعل المعلنة يجب أن يحمل القطبيّة المعلنة — فـ«ولا تزد عليها…
    زد عليها» تُفشل لأنّ الأمرَ يناقض النهي.
  • **النفي:** الأداةُ مع فعلها، وأيُّ نفيٍ غيرِ معلن (``ليست`` · ``غير`` · ``لا``…) يُفشل.
  • **الشرط:** أداتُه موجودة، والكمّيّاتُ المعلنة داخله تقع بعدها **في الجملة نفسها** (لا يعبر حدَّ جملة
    ``.`` ``؟`` ``!`` ``؛``)، و**موضوعُه** المعلن أوّلُ ما يلي الأداة (لا يسبقه إلّا
    فعلُ الكون: كان/كانت…)، ولا نفيَ بينهما غيرَ معلن. حدٌّ مقصود: «إذا تجاوزت سرعةُ الرياح…» يُرفض أيضاً —
    إنذارٌ كاذبٌ يُراجَع، لا قبولٌ خاطئ.
  • **المحتوى بالترتيب:** عباراتٌ يجب أن تظهر بترتيبها (المحصول، المكان، الموسم، اتّجاه التغيّر…).
  جملةٌ بلا حقائقَ معلنة **لا تجتاز** — لا يُقبل ما لم يُفحص.

حدودُه صراحةً: يفحص **النصّ** قبل التوليد لا الصوت، ولا يرى النحو. المسموعُ يحكم عليه المراجعون.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent

_DIAC = re.compile(r"[ً-ْٰـ]")
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")


def normalize(text: str) -> str:
    """يُوحّد الهمزات والياء والأرقام، ويفصل الترقيم — إلّا النقطةَ والفاصلةَ **بين رقمين** (2.5 تبقى عدداً)."""
    text = _DIAC.sub("", text).translate(_DIGITS).lower()
    text = re.sub("[إأآ]", "ا", text).replace("ى", "ي").replace("٪", " % ").replace("%", " % ")
    text = re.sub(r"([،؛:])", r" \1 ", text)
    return re.sub(r"[.,](?!\d)|(?<!\d)[.,]", lambda m: f" {m.group()} ", text)


def _n(word: str) -> str:
    return normalize(word).strip()


UNITS = {
    0: ["صفر"],
    1: ["واحد", "واحدة", "احد", "احدى"],
    2: ["اثنان", "اثنين", "اثنتان", "اثنتين", "اثنا", "اثنتا"],
    3: ["ثلاث", "ثلاثة"],
    4: ["اربع", "اربعة"],
    5: ["خمس", "خمسة"],
    6: ["ست", "ستة"],
    7: ["سبع", "سبعة"],
    8: ["ثمان", "ثماني", "ثمانية"],
    9: ["تسع", "تسعة"],
    10: ["عشر", "عشرة"],
}
TENS = {20: "عشر", 30: "ثلاث", 40: "اربع", 50: "خمس", 60: "ست", 70: "سبع", 80: "ثمان", 90: "تسع"}
WORD_VALUE: dict[str, int] = {}


def _add(word: str, value: int) -> None:
    for form in {word, word[:-1] + "ه" if word.endswith("ة") else word}:
        WORD_VALUE[_n(form)] = value


for v, words in UNITS.items():
    for w in words:
        _add(w, v)
for v, stem in TENS.items():
    _add(stem + "ون", v)
    _add(stem + "ين", v)
for w in ("مئة", "مائة"):
    _add(w, 100)
    for v in range(3, 10):  # ثلاثمئة … تسعمئة
        _add(UNITS[v][0] + w, v * 100)
for w in ("مئتان", "مئتين", "مائتان", "مائتين"):
    _add(w, 200)
for w in ("الفان", "الفين"):
    _add(w, 2000)
MULT = {_n(w) for w in ("ألف", "ألفا", "آلاف")}  # تضرب ما قبلها في ألف (أو تعني ألفاً وحدها)
ORDINALS = {}
for v, stems in {
    1: ["اول", "اولى"],
    2: ["ثاني", "ثانية"],
    3: ["ثالث", "ثالثة"],
    4: ["رابع", "رابعة"],
    5: ["خامس", "خامسة"],
    6: ["سادس", "سادسة"],
    7: ["سابع", "سابعة"],
    8: ["ثامن", "ثامنة"],
    9: ["تاسع", "تاسعة"],
    10: ["عاشر", "عاشرة"],
}.items():
    for w in stems:
        for form in {w, w[:-1] + "ه" if w.endswith("ة") else w}:
            ORDINALS["ال" + _n(form)] = v

UNIT_WORDS = {
    "ml": ["مل", "مليلتر", "مليلترات", "مليلترا"],
    "L": ["لتر", "لترات", "لترا"],
    "kg": ["كيلوجرام", "كيلوجرامات", "كيلوجراما", "كجم"],
    "ha": ["هكتار"],
    "day": ["يوم", "ايام", "يوما"],
    "hour": ["ساعة", "ساعات"],
    "week": ["اسبوع", "اسابيع", "اسبوعا"],
    "km": ["كيلومتر", "كيلومترات", "كيلومترا"],
    "pct": ["%", "بالمئة", "بالمائة"],
    "degC": ["درجة", "درجات"],
    "dS": ["ديسيسيمنز", "دسيسيمنز"],
    "m": ["متر"],
}
DUAL_WORDS = {
    "ml": ["مليلتران", "مليلترين"],
    "L": ["لتران", "لترين"],
    "day": ["يومان", "يومين"],
    "hour": ["ساعتان", "ساعتين"],
    "week": ["اسبوعان", "اسبوعين"],
    "kg": ["كيلوجرامان", "كيلوجرامين"],
}
UNIT_OF, DUALS = {}, {}
for table, target in ((UNIT_WORDS, UNIT_OF), (DUAL_WORDS, DUALS)):
    for u, ws in table.items():
        for w in ws:
            for form in {w, w[:-1] + "ه" if w.endswith("ة") else w}:
                target[_n(form)] = u
CLOCK = {_n("الساعة"), _n("الساعه")}
NEGATIONS = {
    _n(w)
    for w in (
        "لا",
        "ألا",
        "ألّا",
        "لم",
        "لن",
        "ليس",
        "ليست",
        "ليسوا",
        "لست",
        "لسنا",
        "غير",
        "عدم",
        "بدون",
        "دون",
        # أدواتُ نفيٍ إنجليزيّة لاختبار ASR الإنجليزيّ الحقيقيّ (PocketSphinx) — لا تمسّ النصَّ العربيّ
        "no",
        "not",
        "never",
        "don't",
        "dont",
        "cannot",
        "nor",
        "without",
    )
}
STOP = {
    _n(w)
    for w in (
        "في",
        "من",
        "على",
        "إلى",
        "حتى",
        "مع",
        "و",
        "ثم",
        "أو",
        "عند",
        "هذا",
        "هذه",
        "ذلك",
        "تلك",
        "التي",
        "الذي",
        "أن",
        "عن",
        "إذا",
        "كانت",
        "كان",
        "يوم",
        "وقت",
        "لكل",
        "كل",
        "قبل",
        "بعد",
        "خلال",
        "،",
        ",",
        ".",
        "؛",
        ":",
    )
}
PREFIXES = ("و", "ف", "ب", "ل", "ك")
SENTENCE_END = {".", "؟", "?", "!", "؛"}
COPULAS = {_n(w) for w in ("كان", "كانت", "يكون", "تكون", "كانوا")}
# الأطولُ أوّلاً: «أكثر من» قبل «من»
BOUND_PHRASES = [
    tuple(_n(w) for w in p)
    for p in (
        ("أقل", "من"),
        ("أكثر", "من"),
        ("لا", "تتجاوز"),
        ("لا", "يتجاوز"),
        ("على", "الأقل"),
        ("قبل", "مرور"),
        ("بعد", "مرور"),
        ("خلال",),
        ("كل",),
        ("من",),
        ("إلى",),
        ("حتى",),
    )
]


def _unit(tok: str) -> str | None:
    if tok in UNIT_OF:
        return UNIT_OF[tok]
    for p in ("لل", "ل", "بال", "ال"):
        if tok.startswith(p) and tok[len(p) :] in UNIT_OF:
            return UNIT_OF[tok[len(p) :]]
    return None


def _num_token(word: str):
    """قيمةُ رمزٍ عدديّ (أرقام أو كلمة عدد، مع «و» العطف وحدها) — ``None`` إن لم يكن عدداً."""
    core = word[1:] if word.startswith("و") and len(word) > 1 else word
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?", core):
        return Decimal(core.replace(",", ""))
    if core in WORD_VALUE:
        return Decimal(WORD_VALUE[core])
    if core in MULT:
        return "MULT"
    return None


def _read_number(toks: list[str], i: int) -> tuple[list, int]:
    """يقرأ متتاليةَ رموزٍ عدديّة متّصلة؛ «و» المنفصلة تُتخطّى إن تلاها عدد (num2words يكتب «مائة و عشرون»)."""
    parts = []
    while i < len(toks):
        if toks[i] == "و" and parts and i + 1 < len(toks) and _num_token(toks[i + 1]) is not None:
            i += 1
            continue
        n = _num_token(toks[i])
        if n is None:
            break
        parts.append(n)
        i += 1
        if (
            i < len(toks)
            and toks[i] in WORD_VALUE
            and WORD_VALUE[toks[i]] == 10
            and parts[-1] != "MULT"
            and parts[-1] < 10
        ):  # أحد عشر … تسعة عشر
            parts[-1] += 10
            i += 1
    return parts, i


def _compose(parts: list) -> Decimal:
    """مئة وعشرون = 100 + 20 · ثمانية وثلاثون = 8 + 30 · ثلاث مئة = 3 × 100 · ثلاثة آلاف = 3 × 1000."""
    total, cur = Decimal(0), Decimal(0)
    for p in parts:
        if p == "MULT":
            total, cur = total + (cur or 1) * 1000, Decimal(0)
        elif p == 100 and 0 < cur < 10:
            cur *= 100
        else:
            cur += p
    return total + cur


def parse_quantities(text: str) -> list[dict]:
    """يستخرج الكمّيّات بالترتيب: القيمة، الوحدة، المقام، الحدّ — من أرقامٍ أو كلماتٍ عربيّة أو ترتيبيّة."""
    toks = normalize(text).split()
    out, i = [], 0
    while i < len(toks):
        word, start, value, unit = toks[i], i, None, None
        core = word[1:] if word.startswith("و") else word
        if core in DUALS:
            value, unit, i = Decimal(2), DUALS[core], i + 1
        elif word in ORDINALS:
            value, i = Decimal(ORDINALS[word]), i + 1
            unit = "clock" if start and toks[start - 1] in CLOCK else "ordinal"
        elif _num_token(word) is not None:
            parts, i = _read_number(toks, i)
            value = _compose(parts)
            if i < len(toks) and toks[i] in ("فاصلة", "فاصله"):
                frac, i = _read_number(toks, i + 1)
                if frac:
                    digits = (
                        "".join(str(int(d)) for d in frac)
                        if len(frac) > 1 and all(d != "MULT" and d < 10 for d in frac)
                        else str(int(_compose(frac)))
                    )
                    value = Decimal(f"{int(value)}.{digits}")
        if value is None:
            i += 1
            continue
        if i < len(toks) and toks[i] == "ونصف":
            value, i = value + Decimal("0.5"), i + 1
        if unit is None and toks[i : i + 2] in (["في", "المئة"], ["في", "المائة"]):
            unit, i = "pct", i + 2
        elif unit is None and i < len(toks) and (u := _unit(toks[i])):
            unit, i = u, i + 1
            if unit == "degC" and i < len(toks) and toks[i] in ("مئوية", "مئويه"):
                i += 1
            if i < len(toks) and toks[i] == "ونصف":
                value, i = value + Decimal("0.5"), i + 1
        anchor = start
        if unit is None and start and toks[start - 1] in CLOCK:
            unit, anchor = "clock", start - 1
        elif unit == "clock":
            anchor = start - 1
        out.append(
            {
                "value": value,
                "unit": unit,
                "per": _per_unit(toks, i),
                "bound": _bound_before(toks, anchor),
                "span": " ".join(toks[anchor:i]),
                "start": anchor,
                "end": i,
            }
        )
    return out


def _per_unit(toks: list[str], i: int) -> str | None:
    """مقامُ الكمّيّة في نافذةٍ قصيرة بعدها: «لكل X» · «في كل X» · «للX» · «في الX». يتوقّف عند ترقيمٍ أو عدد."""
    window = toks[i : i + 6]
    for j, w in enumerate(window):
        if w in ("،", ",", ".", "؛") or _num_token(w) is not None:
            return None
        if w == "لكل" or (w == "كل" and j > 0 and window[j - 1] == "في"):
            for nxt in window[j + 1 : j + 3]:
                if u := _unit(nxt):
                    return u
        if (
            (w.startswith("لل") or (w.startswith("ل") and not w.startswith("لكل")))
            and (u := _unit(w))
            and w not in UNIT_OF
        ):
            return u
        if (
            w == "في"
            and j + 1 < len(window)
            and window[j + 1].startswith("ال")
            and (u := _unit(window[j + 1]))
        ):
            return u
    return None


def _bound_before(toks: list[str], start: int) -> str | None:
    """العلاقةُ قبل الكمّيّة مباشرة: «بأقل من» تُطابق «أقل من» (الباء والواو السابقتان لا تغيّران الحدّ)."""
    for phrase in BOUND_PHRASES:
        k = len(phrase)
        got = list(toks[max(0, start - k) : start])
        if len(got) != k:
            continue
        if got[0] != phrase[0] and got[0][:1] in ("ب", "و", "ف") and got[0][1:] == phrase[0]:
            got[0] = got[0][1:]
        if tuple(got) == phrase:
            return " ".join(phrase)
    return None


def parse_negations(text: str) -> list[str]:
    """كلُّ أداة نفيٍ مع الفعل الذي يليها: «ولا تزد» → «لا تزد»."""
    toks = normalize(text).split()
    out = []
    for k in range(len(toks) - 1):
        t = toks[k]
        t = t[1:] if t[:1] in ("و", "ف") and t[1:] in NEGATIONS else t
        if t in NEGATIONS:
            out.append(f"{t} {toks[k + 1]}")
    return out


def _strip(tok: str) -> str:
    return tok[1:] if tok[:1] in ("و", "ف") and len(tok) > 2 else tok


def _find(toks: list[str], phrase: str, start: int = 0) -> list[tuple[int, int]]:
    """مواضعُ العبارة (بعد التوحيد) في الرموز. الرمزُ الأوّل يحتمل سابقةً (و/ف/ب/ل/ك)، و«لل» عن «ال»."""
    words = _n(phrase).split()
    hits = []
    for i in range(start, len(toks) - len(words) + 1):
        first = toks[i]
        ok_first = (
            first == words[0]
            or (first[:1] in PREFIXES and first[1:] == words[0])
            or (words[0].startswith("ال") and first == "لل" + words[0][2:])
        )
        if ok_first and toks[i + 1 : i + len(words)] == words[1:]:
            hits.append((i, i + len(words)))
    return hits


def _negated_before(toks: list[str], k: int) -> bool:
    return k > 0 and _strip(toks[k - 1]) in NEGATIONS or (k > 0 and toks[k - 1] in NEGATIONS)


def _action_hits(toks: list[str], forms: list[str]) -> list[tuple[int, str]]:
    wanted = {_n(f) for f in forms}
    return [
        (k, "neg" if _negated_before(toks, k) else "pos")
        for k, t in enumerate(toks)
        if t in wanted or _strip(t) in wanted
    ]


def has_facts(facts: dict) -> bool:
    return any(
        facts.get(k)
        for k in ("quantities", "negations", "actions", "conditions", "content", "words")
    )


def check(text: str, facts: dict) -> list[str]:
    """أخطاءٌ في فحوص الحقائق المعلنة لـ``text`` — قائمةٌ فارغة = **اجتاز الفحوص المعلنة** (لا «المعنى محفوظ»)."""
    if not has_facts(facts):
        return ["لا حقائقَ معلنة لهذه الجملة — لا تجتاز ما لم يُفحص"]
    errors = []
    toks = normalize(text).split()
    got = parse_quantities(text)
    want = facts.get("quantities", [])
    for k, exp in enumerate(want):
        if k >= len(got):
            errors.append(f"كمّيّةٌ مفقودة: {exp}")
            continue
        g = got[k]
        for field in ("value", "unit", "per", "bound"):
            expected = Decimal(exp["value"]) if field == "value" else exp.get(field)
            if field == "bound" and expected:
                expected = " ".join(_n(w) for w in expected.split())
            if g[field] != expected:
                errors.append(
                    f"الكمّيّة {k + 1} «{g['span']}»: {field}={g[field]} والمتوقَّع {expected}"
                )
        if exp.get("subject"):
            side = exp.get("subject_side", "before")
            rivals = {
                e["subject"]
                for e in want
                if e.get("subject") and e.get("subject_side", "before") == side
            }
            hits = [(a, b, r) for r in rivals for a, b in _find(toks, r)]
            if side == "before":
                near = max(
                    (h for h in hits if h[1] <= g["start"]), default=None, key=lambda h: h[1]
                )
            else:
                near = min(
                    (h for h in hits if g["end"] <= h[0] <= g["end"] + 4),
                    default=None,
                    key=lambda h: h[0],
                )
            if near is None or near[2] != exp["subject"]:
                errors.append(
                    f"الكمّيّة {k + 1} «{g['span']}» مُسندةٌ إلى «{near[2] if near else '—'}» "
                    f"والمعلن «{exp['subject']}»"
                )
    for extra in got[len(want) :]:
        errors.append(f"كمّيّةٌ زائدة «{extra['span']}» = {extra['value']} — قراءةٌ مجزّأة أو رقمٌ دخيل")
    negs = parse_negations(text)
    expected_negs = [" ".join(_n(w) for w in e.split()) for e in facts.get("negations", [])]
    for e in expected_negs:
        if e not in negs:
            errors.append(f"نفيٌ مفقود أو تغيّر فعلُه: «{e}» (الموجود {negs})")
    for g in negs:
        if g not in expected_negs:
            errors.append(f"نفيٌ غيرُ معلن «{g}» — قد يقلب المعنى أو نطاقَ الشرط")
    for act in facts.get("actions", []):
        hits = _action_hits(toks, act["forms"])
        if not hits:
            errors.append(f"الفعل {act['forms'][0]!r} مفقود")
        for k, polarity in hits:
            if polarity != act["polarity"]:
                errors.append(
                    f"«{toks[k]}» بقطبيّة {polarity} تناقض المعلن {act['polarity']} — "
                    f"{'أمرٌ يناقض النهي' if polarity == 'pos' else 'نهيٌ يناقض الأمر'}"
                )
    for cond in facts.get("conditions", []):
        markers = _find(toks, cond["marker"])
        if not markers:
            errors.append(f"أداةُ الشرط «{cond['marker']}» مفقودة — صار الحكمُ مطلقاً")
            continue
        m = markers[0][1]
        for qi in cond.get("quantities", []):
            if qi - 1 >= len(got) or got[qi - 1]["start"] < m:
                errors.append(f"الكمّيّة {qi} ليست داخل الشرط «{cond['marker']}»")
                continue
            between = toks[m : got[qi - 1]["start"]]
            if SENTENCE_END & set(between):
                errors.append(
                    f"الكمّيّة {qi} في جملةٍ مستقلّة عن الشرط «{cond['marker']}» — لا تُربط به عبر حدّ الجملة"
                )
                continue
            if cond.get("subject"):
                hits = _find(between, cond["subject"])
                lead = [t for t in between[: hits[0][0]] if t not in COPULAS] if hits else None
                if not hits:
                    errors.append(
                        f"موضوعُ الشرط «{cond['subject']}» ليس بين «{cond['marker']}» والكمّيّة {qi} — "
                        f"الشرطُ صار عن شيءٍ آخر"
                    )
                elif lead:
                    errors.append(
                        f"موضوعُ الشرط «{cond['marker']}» صار «{' '.join(lead)}» لا «{cond['subject']}» — "
                        f"لا يُقبل بين الأداة والموضوع إلّا فعلُ الكون"
                    )
            inside = [
                toks[j]
                for j in range(m, got[qi - 1]["start"])
                if _strip(toks[j]) in NEGATIONS or toks[j] in NEGATIONS
            ]
            if inside and not cond.get("negated"):
                errors.append(
                    f"نفيٌ داخل الشرط «{cond['marker']}» قبل الكمّيّة {qi}: {inside} — نطاقُ الشرط انقلب"
                )
    pos = 0
    for phrase in facts.get("content", []) + facts.get("words", []):
        hits = _find(toks, phrase, pos)
        if not hits:
            where = "مفقودة" if not _find(toks, phrase) else "في غير موضعها (تغيّر الترتيب)"
            errors.append(f"عبارةُ محتوى «{phrase}» {where}")
            continue
        pos = hits[0][1]
    return errors


def verdict(text: str, facts: dict) -> dict:
    """الحكمُ على مستوى النصّ بثلاث درجات — المحتوى غيرُ المغطّى **لا يُخفى** تحت الاجتياز:
    ``FAILED_DECLARED_CHECKS`` · ``REVIEW_UNCOVERED_CONTENT`` (اجتاز المعلن وبقي محتوى لم يُفحص) ·
    ``PASSED_DECLARED_CHECKS``."""
    errors, uncovered = check(text, facts), coverage(text, facts)
    status = (
        "FAILED_DECLARED_CHECKS"
        if errors
        else "REVIEW_UNCOVERED_CONTENT"
        if uncovered
        else "PASSED_DECLARED_CHECKS"
    )
    return {"status": status, "errors": errors, "uncovered_content": uncovered}


def quantity_mapping(source: str, converted: str) -> list[dict]:
    """يربط كلَّ كمّيّةٍ في النصّ المصدر بنظيرتها في النصّ المحوَّل **بالترتيب** — مستلهَمٌ من
    ``normalize_with_mapping`` في WeTextProcessing (ربطُ الجزء الأصليّ بالمحوَّل)، لكنّه مستقلٌّ عن أيّ محوّل:
    يُعيد تحليلَ الطرفين بهذا المحلّل ويقارن القيمة والوحدة والمقام والحدّ لكلّ زوج، فيرى المراجعُ
    «2.5 مل» ← «اثنان فاصلة خمسة مل» جنباً إلى جنب. زوجٌ بلا نظيرٍ يُسجَّل ``None`` في الطرف الناقص."""
    a, b = parse_quantities(source), parse_quantities(converted)
    rows = []
    for k in range(max(len(a), len(b))):
        x, y = (a[k] if k < len(a) else None), (b[k] if k < len(b) else None)
        same = {
            f: (x is not None and y is not None and x[f] == y[f])
            for f in ("value", "unit", "per", "bound")
        }
        rows.append(
            {
                "source": x and x["span"],
                "converted": y and y["span"],
                "source_value": x and str(x["value"]),
                "converted_value": y and str(y["value"]),
                **{f"same_{f}": v for f, v in same.items()},
                "all_same": all(same.values()),
            }
        )
    return rows


def coverage(text: str, facts: dict) -> list[str]:
    """الرموزُ التي لم تُغطِّها أيُّ حقيقةٍ معلنة (بعد حذف أدوات الربط) — تُسجَّل ليُرى حدُّ الفحص."""
    toks = normalize(text).split()
    covered: set[int] = set()
    for q in parse_quantities(text):
        covered.update(range(q["start"], q["end"]))
        if q["bound"]:
            covered.update(range(q["start"] - len(q["bound"].split()), q["start"]))
    for k, t in enumerate(toks):
        if _unit(t) or t in NEGATIONS or _strip(t) in NEGATIONS:
            covered.add(k)
    phrases = [e["subject"] for e in facts.get("quantities", []) if e.get("subject")]
    phrases += (
        facts.get("content", [])
        + facts.get("words", [])
        + [c["marker"] for c in facts.get("conditions", [])]
    )
    phrases += [c["subject"] for c in facts.get("conditions", []) if c.get("subject")]
    phrases += [n.split(maxsplit=1)[-1] for n in facts.get("negations", [])]
    for ph in phrases:
        for a, b in _find(toks, ph):
            covered.update(range(a, b))
    for act in facts.get("actions", []):
        covered.update(k for k, _ in _action_hits(toks, act["forms"]))
    return [
        t
        for k, t in enumerate(toks)
        if k not in covered and t not in STOP and _strip(t) not in STOP
    ]


def load_facts(path: Path = HERE / "semantic_facts.json") -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["sentences"]
