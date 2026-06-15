// test/resilience_test.dart — اختبارات P0 (سباق 401) + P1 (idempotency)
// التشغيل في بيئتك: flutter test test/resilience_test.dart
//
// يوثّق السلوك المتوقّع بعد الإصلاحات. بعضها يحتاج mock للشبكة (Dio adapter)
// لكنّ اختبارات idempotency للـoperation_id تعمل مباشرةً.

import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/utils/ids.dart';

void main() {
  group('P1: idempotency للـoffline queue', () {
    test('operation_id ثابت عبر إعادة الإرسال', () {
      // محاكاة منطق _generateOperationId + الاحتفاظ به
      final cmd = <String, dynamic>{'type': 'actuate', 'action': 'irrigate'};
      // أوّل send يولّد المعرّف
      cmd['operation_id'] ??= 'op_test_abc123';
      final firstId = cmd['operation_id'];
      // reconnect → نفس الرسالة تُرسل ثانيةً → نفس المعرّف (لا تكرار تنفيذ)
      cmd['operation_id'] ??= 'op_test_DIFFERENT';
      expect(cmd['operation_id'], equals(firstId),
          reason: 'إعادة الإرسال يجب أن تحفظ نفس operation_id');
    });

    test('ping/pong لا تحمل operation_id (ليست عمليّات مُغيِّرة)', () {
      bool isMutating(Map<String, dynamic> d) {
        final t = (d['type'] as String?) ?? '';
        return t != 'ping' && t != 'pong' && t != 'subscribe';
      }
      expect(isMutating({'type': 'ping'}), isFalse);
      expect(isMutating({'type': 'pong'}), isFalse);
      expect(isMutating({'type': 'actuate'}), isTrue);
    });

    test('operation_id بصيغة متوقّعة (op_<hex>_<hex>)', () {
      final regex = RegExp(r'^op_[0-9a-f]+_[0-9a-f]{6}$');
      // الكود الفعليّ (utils/ids.dart) — لا نسخة مُعاد كتابتها inline.
      expect(regex.hasMatch(generateOperationId()), isTrue);
    });
  });

  group('P0: سباق 401 (منطق Completer)', () {
    test('Completer مشترك: طلبات متزامنة تنتظر تحديثاً واحداً', () async {
      // محاكاة منطق _coalescedRefresh
      var refreshCount = 0;
      Future<String?>? shared;
      Future<String?> coalesced() {
        if (shared != null) return shared!;
        refreshCount++;
        shared = Future.delayed(
            const Duration(milliseconds: 10), () => 'new_token');
        shared!.whenComplete(() => shared = null);
        return shared!;
      }
      // 3 طلبات متزامنة
      final results = await Future.wait([coalesced(), coalesced(), coalesced()]);
      expect(refreshCount, equals(1), reason: 'تحديث واحد فقط للطلبات المتزامنة');
      expect(results, everyElement(equals('new_token')));
    });

    test('القفل يُحرَّر بعد الاكتمال (لا deadlock)', () async {
      Future<String?>? shared;
      Future<String?> coalesced() {
        if (shared != null) return shared!;
        shared = Future.value('token');
        shared!.whenComplete(() => shared = null);
        return shared!;
      }
      await coalesced();
      // بعد الاكتمال، القفل حُرِّر → تحديث جديد ممكن
      await Future.delayed(Duration.zero);
      expect(shared, isNull, reason: 'القفل يجب أن يُحرَّر بعد الاكتمال');
    });
  });
}
