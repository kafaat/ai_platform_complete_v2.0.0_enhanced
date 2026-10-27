// UI-M3: المفتاح مربوط بالحمولة — نفس المحتوى ⇒ نفس المفتاح، أيّ تعديل ⇒ مفتاح جديد.
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';

void main() {
  test('same payload keeps the key regardless of map key order', () {
    final k = PayloadIdempotencyKey();
    final first = k.forPayload({
      'name': 'أ',
      'geometry': {
        'type': 'Polygon',
        'coordinates': [1, 2],
      },
    });
    final again = k.forPayload({
      'geometry': {
        'coordinates': [1, 2],
        'type': 'Polygon',
      },
      'name': 'أ',
    });
    expect(again.value, first.value);
    expect(k.current.value, first.value);
  });

  test('an edited payload mints a new key, and it then stays stable', () {
    final k = PayloadIdempotencyKey();
    final a = k.forPayload({
      'crops': ['wheat'],
    });
    final b = k.forPayload({
      'crops': ['maize'],
    });
    expect(b.value, isNot(a.value));
    expect(
      k.forPayload({
        'crops': ['maize'],
      }).value,
      b.value,
    );
    // العودة إلى الحمولة الأولى نيّةٌ جديدة أيضاً (لا يُعاد مفتاحٌ قديم).
    expect(
      k.forPayload({
        'crops': ['wheat'],
      }).value,
      isNot(a.value),
    );
  });
}
