"""Slice C code change: --generate may lower the bidi baseline, never raise it."""
import pathlib, sys
root = pathlib.Path(sys.argv[1])
g = root / "scripts/ci/bidi_control_char_guard.py"
s = g.read_text(encoding="utf-8")

old_gen = "def generate(path: Path = BASELINE, root: Path = ROOT) -> dict:\n    overrides, marks = scan(root)\n"
new_gen = '''class BaselineWouldGrow(RuntimeError):
    """إعادةُ التوليد كانت سترفع عدّاً مُعلَناً — الأساسُ يتقلّص ولا ينمو **بالبناء**."""

    def __init__(self, grown: dict[str, tuple[int, int]]) -> None:
        self.grown = grown
        super().__init__(
            " · ".join(f"{name}: {old}→{new}" for name, (old, new) in sorted(grown.items()))
        )


def generate(path: Path = BASELINE, root: Path = ROOT) -> dict:
    overrides, marks = scan(root)
    # «يتقلّص ولا ينمو» كان وصفاً يقرؤه الفاحصُ وحده: `--generate` كان يكتب العدَّ
    # الحاليّ أيّاً كان، فـ72→74 تمرّ بسطرٍ واحد. الآن التوليدُ يُخفِض ولا يرفع؛ وأوّلُ
    # توليدٍ (لا أساسَ بعد) وحده يكتب ما يجده. التحريرُ اليدويّ للملفّ يبقى ممكناً
    # ويظهر في المراجعة — حدٌّ مُعلَن لا يدّعي الحارسُ سدَّه.
    if path.exists():
        previous = load_baseline(path)
        grown = {
            name: (previous.get(name, 0), count)
            for name, count in marks.items()
            if count > previous.get(name, 0)
        }
        if grown:
            raise BaselineWouldGrow(grown)
'''
assert s.count(old_gen) == 1
s = s.replace(old_gen, new_gen)

old_main = "    if args.generate:\n        data = generate()\n"
new_main = '''    if args.generate:
        try:
            data = generate()
        except BaselineWouldGrow as exc:
            print("bidi_control_char_guard_failed")
            print(
                f"- إعادةُ التوليد كانت سترفع الأساس ({exc}) — الأساسُ يتقلّص ولا ينمو. "
                "احذف الزائد ثمّ أعِد التوليد: "
                "`python3 scripts/ci/bidi_control_char_guard.py --strip-added`."
            )
            return 1
'''
assert s.count(old_main) == 1
s = s.replace(old_main, new_main)
g.write_text(s, encoding="utf-8")

t = root / "tests_v9/test_bidi_control_char_guard.py"
ts = t.read_text(encoding="utf-8")
ts += '''

def _git_tree(tmp_path: Path, text: str) -> Path:
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "a.md").write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "a.md"], check=True)
    return tmp_path


def test_regenerating_the_baseline_can_lower_it_but_never_raise_it(tmp_path: Path) -> None:
    """«يتقلّص ولا ينمو» كان وصفاً: `--generate` كان يكتب 74 فوق 72 بلا اعتراض."""
    root = _git_tree(tmp_path / "tree", f"x{RLM}{RLM}")
    baseline = tmp_path / "baseline.json"
    bidi.generate(baseline, root)  # أوّلُ توليد: لا أساسَ سابق
    assert bidi.load_baseline(baseline) == {"a.md": 2}

    (root / "a.md").write_text(f"x{RLM}{RLM}{RLM}", encoding="utf-8")
    with pytest.raises(bidi.BaselineWouldGrow) as raised:
        bidi.generate(baseline, root)
    assert raised.value.grown == {"a.md": (2, 3)}
    assert bidi.load_baseline(baseline) == {"a.md": 2}, "الرفضُ لا يكتب نصفَ أساس"

    (root / "a.md").write_text(f"x{RLM}", encoding="utf-8")
    bidi.generate(baseline, root)
    assert bidi.load_baseline(baseline) == {"a.md": 1}


def test_a_file_new_to_the_baseline_cannot_be_admitted_by_regeneration(tmp_path: Path) -> None:
    """ملفٌّ بلا مدخلٍ أساسُه صفر؛ والتوليدُ لا يمنحه رخصةً."""
    root = _git_tree(tmp_path / "tree", "clean")
    baseline = tmp_path / "baseline.json"
    bidi.generate(baseline, root)
    (root / "b.md").write_text(f"y{LRM}", encoding="utf-8")
    import subprocess

    subprocess.run(["git", "-C", str(root), "add", "b.md"], check=True)
    with pytest.raises(bidi.BaselineWouldGrow):
        bidi.generate(baseline, root)
'''
t.write_text(ts, encoding="utf-8")
print("applied")
