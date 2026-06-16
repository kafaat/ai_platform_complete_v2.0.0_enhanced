// SAHOOL — lib/utils/ids.dart
// منطق نقيّ (بلا اعتماد على Flutter) لتوليد المعرّفات — مصدر واحد للحقيقة
// (على نمط lib/utils/jwt.dart). يستخدمه ApiService وWebSocketService معاً، كي
// لا تنحرف صيغ منسوخة وتُختبر مباشرةً (test/ids_test.dart يستورد هذا الكود).
import 'dart:math';

// مولّد عشوائيّ وحيد على مستوى الوحدة. نستخدم Random.secure() لأنّ المعرّفات
// تُستعمل في الترابط (X-Request-ID) ومنع التكرار (operation_id)؛ العشوائيّة
// القويّة تُقلّل خطر التصادم/التخمين دون أيّ اعتماد خارجيّ.
final Random _rand = Random.secure();

/// يولّد معرّف طلب بصيغة UUIDv7 (RFC 9562): طابع زمنيّ Unix بالمللي‑ثانية
/// (48 بت، big-endian) + 4 بت إصدار `0x7` + 2 بت variant `0b10` + 74 بت عشوائيّة.
/// النتيجة قابلة للترتيب زمنيّاً (k-sortable) وشبه‑فريدة حتى تحت التزامن — تحلّ
/// محلّ المعرّف المبنيّ على المللي‑ثانية وحدها (كان عرضةً للتصادم تحت التزامن).
/// الصيغة القانونيّة: `xxxxxxxx-xxxx-7xxx-yxxx-xxxxxxxxxxxx` (hex صغير، y ∈ {8,9,a,b}).
String generateRequestId() {
  // 16 بايتاً، كلّ قيمة في النطاق [0..255].
  final bytes = List<int>.filled(16, 0);

  // 48 بت طابع زمنيّ Unix بالمللي‑ثانية، big-endian، في البايتات [0..5].
  final ms = DateTime.now().millisecondsSinceEpoch;
  bytes[0] = (ms >> 40) & 0xFF;
  bytes[1] = (ms >> 32) & 0xFF;
  bytes[2] = (ms >> 24) & 0xFF;
  bytes[3] = (ms >> 16) & 0xFF;
  bytes[4] = (ms >> 8) & 0xFF;
  bytes[5] = ms & 0xFF;

  // بقيّة البايتات عشوائيّة (74 بت فعّالة بعد ضبط بتات الإصدار/الـvariant).
  for (var i = 6; i < 16; i++) {
    bytes[i] = _rand.nextInt(256);
  }

  // 4 بت الإصدار = 0x7 في النصف الأعلى من البايت 6.
  bytes[6] = (bytes[6] & 0x0F) | 0x70;
  // 2 بت الـvariant = 0b10 في البتّين الأعليين من البايت 8.
  bytes[8] = (bytes[8] & 0x3F) | 0x80;

  return _formatUuid(bytes);
}

/// يولّد معرّف عمليّة websocket بالصيغة `op_<hex-microseconds>_<6hex-random>`.
/// يُبقي الصيغة التاريخيّة كما هي (resilience_test يتحقّق من ^op_[0-9a-f]+_[0-9a-f]{6}$)
/// كي لا ينكسر أيّ شيء في الخلفيّة المعتمِدة عليها — هنا نمركزها فقط.
String generateOperationId() {
  final ts = DateTime.now().microsecondsSinceEpoch.toRadixString(16);
  final rnd = _rand.nextInt(0xFFFFFF).toRadixString(16).padLeft(6, '0');
  return 'op_${ts}_$rnd';
}

// ── أدوات داخليّة ────────────────────────────────────────────────────────

const _hexDigits = '0123456789abcdef';

String _hexByte(int b) =>
    '${_hexDigits[(b >> 4) & 0xF]}${_hexDigits[b & 0xF]}';

/// يُنسّق 16 بايتاً إلى الصيغة القانونيّة 8-4-4-4-12 (hex صغير مع شُرَط).
String _formatUuid(List<int> b) {
  final sb = StringBuffer();
  for (var i = 0; i < 16; i++) {
    if (i == 4 || i == 6 || i == 8 || i == 10) sb.write('-');
    sb.write(_hexByte(b[i]));
  }
  return sb.toString();
}
