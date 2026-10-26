// SAHOOL — lib/core/network/response_cache.dart
// ذاكرة استجابات قصيرة العمر في الذاكرة فقط، مُنطَّقة بالمستأجِر+المستخدم في
// المفتاح (يمنع رؤية حساب لكاش حساب سابق على نفس الجهاز). تُمسَح عند الخروج
// (ApiService.clearCache ← logout). ليست تخزيناً دون اتّصال: تموت مع العمليّة.
class ResponseCache {
  ResponseCache({this.ttl = const Duration(minutes: 5), this.maxEntries = 100});

  static final ResponseCache instance = ResponseCache();

  final Duration ttl;
  final int maxEntries;
  final Map<String, (Object?, DateTime)> _entries = {};

  Object? get(String key) {
    final entry = _entries[key];
    if (entry == null) return null;
    if (DateTime.now().difference(entry.$2) > ttl) {
      _entries.remove(key);
      return null;
    }
    return entry.$1;
  }

  void set(String key, Object? value) {
    if (_entries.length >= maxEntries) _entries.remove(_entries.keys.first);
    _entries[key] = (value, DateTime.now());
  }

  void clear() => _entries.clear();
}
