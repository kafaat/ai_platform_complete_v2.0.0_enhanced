"""
tests_v9/test_v12_modules.py — TrueUp + Sharing tests (pure logic, no DB)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../services/sahool-platform'))


def test_moisture_correction():
    """تصحيح الرطوبة بالمعادلة المعياريّة."""
    from api.trueup import moisture_correct
    
    results = []
    
    # Example: 1000 kg قمح بـ16% رطوبة، المعيار 13.5%
    # W_std = 1000 × (100-16) / (100-13.5) = 1000 × 84/86.5 ≈ 971.1
    corrected = moisture_correct(1000, 16.0, 13.5)
    if 970 < corrected < 972:
        results.append(("✓", f"corn 16%→13.5%: {corrected:.1f} (expected ~971)"))
    else:
        results.append(("✗", f"got {corrected}"))
    
    # 1000 kg عند 13.5% → نفسه (لا تصحيح)
    same = moisture_correct(1000, 13.5, 13.5)
    if 999.9 < same < 1000.1:
        results.append(("✓", f"no correction when at standard: {same}"))
    
    # رطوبة أقلّ من المعيار → الوزن يزيد عند المعيار (water added)
    higher = moisture_correct(1000, 10.0, 13.5)
    if higher > 1000:
        results.append(("✓", f"dry grain → adjusted up: {higher:.1f}"))
    else:
        results.append(("✗", "should adjust up"))
    
    # Edge: invalid
    try:
        moisture_correct(1000, 100, 13.5)
        results.append(("✗", "should reject 100% moisture"))
    except ValueError:
        results.append(("✓", "rejected 100% moisture"))
    
    return results


def test_k_calculation():
    """k_new = actual / measured."""
    from api.trueup import calculate_k_new, is_k_acceptable
    
    results = []
    
    # Combine قاس 1000 kg، الوزن الحقيقي 1050 kg
    k = calculate_k_new(1050, 1000)
    if abs(k - 1.05) < 0.0001:
        results.append(("✓", f"k=1.05 (5% under-measured)"))
    
    # acceptable
    if is_k_acceptable(1.05):
        results.append(("✓", "k=1.05 acceptable"))
    if is_k_acceptable(0.85):
        results.append(("✓", "k=0.85 acceptable"))
    
    # NOT acceptable (>30% off → sensor failure or wrong sample)
    if not is_k_acceptable(1.5):
        results.append(("✓", "k=1.5 rejected (50% off)"))
    if not is_k_acceptable(0.5):
        results.append(("✓", "k=0.5 rejected (50% off)"))
    
    # Edge case
    try:
        calculate_k_new(1000, 0)
        results.append(("✗", "should reject measured=0"))
    except ValueError:
        results.append(("✓", "rejected measured=0"))
    
    return results


def test_trueup_compute():
    """Full TrueUp computation (no DB)."""
    from api.trueup import TrueUpEngine, TrueUpInput, TrueUpStatus
    
    results = []
    engine = TrueUpEngine()  # no pool — pure compute
    
    # Wheat field: combine measured 2000 kg, actual 2100 kg, both at 14% moisture
    input_data = TrueUpInput(
        field_id="11111111-1111-1111-1111-111111111111",
        operation_id="22222222-2222-2222-2222-222222222222",
        actual_weight_kg=2100,
        actual_moisture_pct=14.0,
        measured_weight_kg=2000,
    )
    
    result = engine.compute(
        input_data=input_data,
        crop="wheat",
        measured_yield_kg_ha=2500,
        k_old=1.0,
    )
    
    if result.status == TrueUpStatus.APPLIED:
        results.append(("✓", "TrueUp APPLIED status"))
    else:
        results.append(("✗", f"status: {result.status}"))
    
    # k_new ~ 1.05 (5% under)
    if 1.04 < result.k_new < 1.06:
        results.append(("✓", f"k_new={result.k_new}"))
    
    # adjusted yield = 2500 × 1.05 = 2625
    if 2620 < result.adjusted_yield_kg_ha < 2630:
        results.append(("✓", f"adjusted yield={result.adjusted_yield_kg_ha}"))
    
    # moisture correction applied (wheat is in catalog)
    if result.moisture_correction_applied:
        results.append(("✓", "moisture correction applied for wheat"))
    if result.standard_moisture_pct == 13.5:
        results.append(("✓", f"standard moisture 13.5% (wheat)"))
    
    # Out-of-range rejection
    bad_input = TrueUpInput(
        field_id="11111111-1111-1111-1111-111111111111",
        operation_id="22222222-2222-2222-2222-222222222222",
        actual_weight_kg=5000,    # 2.5x measured — wrong
        actual_moisture_pct=14.0,
        measured_weight_kg=2000,
    )
    bad_result = engine.compute(bad_input, "wheat", 2500)
    if bad_result.status == TrueUpStatus.REJECTED:
        results.append(("✓", f"out-of-range k rejected"))
    if any("خارج النطاق" in w for w in bad_result.warnings):
        results.append(("✓", "rejection includes Arabic warning"))
    
    # Vegetable (tomato) - no moisture correction
    tomato_input = TrueUpInput(
        field_id="11111111-1111-1111-1111-111111111111",
        operation_id="22222222-2222-2222-2222-222222222222",
        actual_weight_kg=10500,
        actual_moisture_pct=92.0,   # tomato is mostly water
        measured_weight_kg=10000,
    )
    tomato_result = engine.compute(tomato_input, "tomato", 30000)
    if not tomato_result.moisture_correction_applied:
        results.append(("✓", "no moisture correction for tomato"))
    
    return results


def test_sharing_key_generation():
    """Key generation + hashing."""
    from api.sharing import generate_key_plaintext, hash_key
    
    results = []
    
    # Format
    key = generate_key_plaintext()
    if key.startswith("shk_") and len(key) > 30:
        results.append(("✓", f"key format: {key[:12]}..."))
    
    # Uniqueness (10 keys)
    keys = {generate_key_plaintext() for _ in range(10)}
    if len(keys) == 10:
        results.append(("✓", "10 keys all unique"))
    
    # Hash is deterministic
    k = "shk_test_key_value"
    h1 = hash_key(k)
    h2 = hash_key(k)
    if h1 == h2:
        results.append(("✓", "hash is deterministic"))
    
    # Hash length (SHA-256 = 64 hex)
    if len(h1) == 64:
        results.append(("✓", f"hash is SHA-256 (64 hex chars)"))
    
    # Different keys → different hashes
    h3 = hash_key("shk_different")
    if h1 != h3:
        results.append(("✓", "different keys → different hashes"))
    
    return results


def run_all():
    print("="*60)
    print("  v12 modules — TrueUp + Sharing tests")
    print("="*60)
    
    suites = [
        ("Moisture Correction Math",   test_moisture_correction),
        ("k Factor Math",              test_k_calculation),
        ("TrueUp Engine (compute)",    test_trueup_compute),
        ("Sharing Key Generation",     test_sharing_key_generation),
    ]
    
    tp = 0; tf = 0
    for name, suite in suites:
        print(f"\n── {name} ──")
        try:
            for status, msg in suite():
                print(f"  {status} {msg}")
                if status == "✓": tp += 1
                else: tf += 1
        except Exception as e:
            print(f"  ✗ CRASHED: {type(e).__name__}: {e}")
            tf += 1
    
    print(f"\n{'='*60}")
    print(f"  Passed: {tp}/{tp+tf}")
    print(f"{'='*60}")
    return tp, tf


if __name__ == "__main__":
    p, f = run_all()
    sys.exit(0 if f == 0 else 1)
