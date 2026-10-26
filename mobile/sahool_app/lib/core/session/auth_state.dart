// SAHOOL — lib/core/session/auth_state.dart
// إشعار تغيّر حالة الدخول. AuthGate يستمع إليه فيعيد البناء (دخول ⇒ الغلاف،
// خروج/انتهاء ⇒ شاشة الدخول) بدل أن تدفع الشاشات AuthGate جديداً فوق القديم
// (كان القديم يُتلف بعد بناء الجديد فيغلق WebSocket الجلسة الجديدة).
import 'package:flutter/foundation.dart';

enum AuthChange { signedIn, signedOut, expired }

class AuthState extends ChangeNotifier {
  AuthState();
  static final AuthState instance = AuthState();

  AuthChange? _last;
  AuthChange? get last => _last;

  void signedIn() => _emit(AuthChange.signedIn);
  void signedOut() => _emit(AuthChange.signedOut);
  void expired() => _emit(AuthChange.expired);

  void _emit(AuthChange change) {
    _last = change;
    notifyListeners();
  }
}
