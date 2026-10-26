// SAHOOL — features/advisor/data/chat_history_store.dart
// سجلّ محادثة المستشار: صندوق Hive مشفّر (AES-256) لكلّ (مستأجر، مستخدم)، ومفتاحه
// في التخزين الآمن (Keychain/Keystore) لا على القرص بجانب البيانات.
//
// لماذا: كان السجلّ صندوقاً واحداً `chat_history` بنصّ صريح مشترك بين كلّ مستخدمي
// الجهاز، فيرى المستخدم التالي محادثة سابقه. الآن:
// - اسم الصندوق مشتقّ من المستأجر والمستخدم (بصمة لا المعرّفات نفسها).
// - المفتاح يُولَّد عند أوّل فتح ويُحذَف مع الصندوق عند الخروج ([endSession]).
// - إن تعذّر المفتاح الآمن أو هويّة المستخدم: سجلّ في الذاكرة فقط — لا نكتب نصّاً
//   صريحاً أبداً.
// - الصندوق القديم غير المنطَّق (`chat_history`، يفتحه main.dart) يُفرَّغ عند أوّل
//   فتح: لا يمكن نسبته إلى مستخدم، فلا يُعرَض لأحد.
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:hive/hive.dart';
import 'package:sahool_app/core/session/session_scope.dart';

import 'advisor_models.dart';

/// الصندوق القديم بنصّ صريح المشترك بين المستخدمين (يُفتح في main.dart).
const String kLegacyAdvisorChatBox = 'chat_history';

/// أقصى عدد رسائل محفوظة لكلّ مستخدم (الأقدم يُحذَف أوّلاً).
const int kAdvisorHistoryCap = 200;

/// سجلّ محادثة مستخدم واحد.
abstract class AdvisorChatHistory {
  /// true ⇒ محفوظ مشفّراً على الجهاز؛ false ⇒ في الذاكرة فقط (يضيع عند الإغلاق).
  bool get persistent;
  Future<List<ChatEntry>> load();
  Future<void> append(ChatEntry entry);
  Future<void> clear();
}

/// سجلّ في الذاكرة — حين لا هويّة مستخدم أو تعذّر التشفير، وفي الاختبارات.
class MemoryChatHistory implements AdvisorChatHistory {
  MemoryChatHistory([List<ChatEntry>? seed]) : _items = [...?seed];
  final List<ChatEntry> _items;

  @override
  bool get persistent => false;

  @override
  Future<List<ChatEntry>> load() async => List.unmodifiable(_items);

  @override
  Future<void> append(ChatEntry entry) async {
    _items.add(entry);
    if (_items.length > kAdvisorHistoryCap) _items.removeAt(0);
  }

  @override
  Future<void> clear() async => _items.clear();
}

class _HiveChatHistory implements AdvisorChatHistory {
  _HiveChatHistory(this._box);
  final Box<dynamic> _box;

  @override
  bool get persistent => true;

  @override
  Future<List<ChatEntry>> load() async =>
      _box.values.map(ChatEntry.fromMap).whereType<ChatEntry>().toList();

  @override
  Future<void> append(ChatEntry entry) async {
    await _box.add(entry.toMap());
    while (_box.length > kAdvisorHistoryCap) {
      await _box.deleteAt(0);
    }
  }

  @override
  Future<void> clear() => _box.clear();
}

/// مخزن مفاتيح التشفير. الإنتاج: flutter_secure_storage.
abstract class ChatKeyVault {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);
}

class SecureChatKeyVault implements ChatKeyVault {
  const SecureChatKeyVault();
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  @override
  Future<String?> read(String key) => _storage.read(key: key);
  @override
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);
  @override
  Future<void> delete(String key) => _storage.delete(key: key);
}

class MemoryChatKeyVault implements ChatKeyVault {
  final Map<String, String> values = {};
  @override
  Future<String?> read(String key) async => values[key];
  @override
  Future<void> write(String key, String value) async => values[key] = value;
  @override
  Future<void> delete(String key) async => values.remove(key);
}

class AdvisorChatStore {
  AdvisorChatStore({ChatKeyVault? vault, HiveInterface? hive})
    : _vault = vault ?? const SecureChatKeyVault(),
      _hive = hive ?? Hive;

  static final AdvisorChatStore instance = AdvisorChatStore();

  final ChatKeyVault _vault;
  final HiveInterface _hive;

  /// صناديق فُتحت في هذه العمليّة — تُحذَف كلّها عند انتهاء الجلسة.
  final Set<String> _opened = {};

  /// اسم صندوق (مستأجر، مستخدم): بصمتا FNV-1a بطول 64 بتّاً في اتّجاهين، فلا
  /// تظهر المعرّفات في اسم الملفّ، والتصادم غير عمليّ على جهاز واحد.
  static String boxNameFor(String tenantId, String userId) {
    final a = _fnv1a64('$tenantId\u0000$userId');
    final b = _fnv1a64('$userId\u0000$tenantId');
    return 'advisor_chat_$a$b';
  }

  static String _keyNameFor(String box) => '${box}_key';

  /// يفتح سجلّ المستخدم الحاليّ. بلا [userId] ⇒ ذاكرة فقط.
  Future<AdvisorChatHistory> openFor({
    required String? tenantId,
    required String? userId,
  }) async {
    await _wipeLegacy();
    if (userId == null || userId.isEmpty) return MemoryChatHistory();
    final name = boxNameFor(tenantId ?? '', userId);
    try {
      final cipher = HiveAesCipher(await _keyFor(name));
      Box<dynamic> box;
      try {
        box = await _hive.openBox<dynamic>(name, encryptionCipher: cipher);
      } on HiveError {
        // صندوق لا يُفكّ بالمفتاح الحاليّ (مفتاح ضائع/تالف): لا يُقرأ أبداً،
        // فيُحذَف ويُبدأ صندوق جديد بدل انهيار الشاشة.
        await _hive.deleteBoxFromDisk(name);
        box = await _hive.openBox<dynamic>(name, encryptionCipher: cipher);
      }
      _opened.add(name);
      return _HiveChatHistory(box);
    } catch (e) {
      debugPrint('advisor chat: encrypted history unavailable ($e)');
      return MemoryChatHistory();
    }
  }

  Future<List<int>> _keyFor(String box) async {
    final keyName = _keyNameFor(box);
    final saved = await _vault.read(keyName);
    if (saved != null) {
      final bytes = base64Decode(saved);
      if (bytes.length == 32) return bytes;
    }
    final fresh = _hive.generateSecureKey();
    await _vault.write(keyName, base64Encode(fresh));
    return fresh;
  }

  Future<void> _wipeLegacy() async {
    try {
      if (_hive.isBoxOpen(kLegacyAdvisorChatBox)) {
        final legacy = _hive.box<dynamic>(kLegacyAdvisorChatBox);
        if (legacy.isNotEmpty) await legacy.clear();
      }
    } catch (e) {
      debugPrint('advisor chat: legacy wipe failed ($e)');
    }
  }

  /// تنظيف الخروج (FeatureModule.onSessionEnd): يحذف صندوق المستخدم المنتهية
  /// جلسته ومفتاحه، وكلّ صندوق فُتح في هذه العمليّة، ويفرّغ الصندوق القديم.
  Future<void> endSession(SessionEnd end) async {
    final names = {..._opened};
    final user = end.userId;
    if (user != null && user.isNotEmpty) {
      names.add(boxNameFor(end.tenantId ?? '', user));
    }
    for (final name in names) {
      try {
        if (_hive.isBoxOpen(name)) {
          await _hive.box<dynamic>(name).deleteFromDisk();
        } else {
          await _hive.deleteBoxFromDisk(name);
        }
      } catch (e) {
        debugPrint('advisor chat: delete $name failed ($e)');
      }
      await _vault.delete(_keyNameFor(name));
      _opened.remove(name);
    }
    await _wipeLegacy();
  }
}

String _fnv1a64(String input) {
  // FNV-1a على 64 بتّاً بحساب صحيح 64 بتّ (Dart VM). ليست تشفيراً؛ اسم ملفّ فقط.
  var hash = 0xcbf29ce484222325;
  const prime = 0x100000001b3;
  for (final byte in utf8.encode(input)) {
    hash ^= byte;
    hash = (hash * prime) & 0xFFFFFFFFFFFFFFFF;
  }
  return hash.toUnsigned(64).toRadixString(16).padLeft(16, '0');
}
