// SAHOOL — lib/core/network/in_flight.dart
// دمج الطلبات المتطابقة المتزامنة: نداءان بنفس المفتاح أثناء طلبٍ جارٍ ينتظران
// نفس الـFuture بدل إرسال طلبين. لا يخزّن النتيجة بعد اكتمالها (ذاك دور
// ResponseCache)؛ فقط يمنع الطلبات المكرَّرة في اللحظة نفسها (مثل عدّة شاشات
// تطلب لوحة المعلومات عند الإقلاع).
class InFlight<T> {
  final Map<String, Future<T>> _pending = {};

  Future<T> run(String key, Future<T> Function() body) {
    final existing = _pending[key];
    if (existing != null) return existing;
    final future = body();
    _pending[key] = future;
    future.whenComplete(() => _pending.remove(key)).ignore();
    return future;
  }

  int get pendingCount => _pending.length;
}
