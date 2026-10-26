// SAHOOL — features/profile/presentation/profile_cubit.dart
// هويّة المستخدم: تُعرض فوراً من الجلسة المحفوظة (حقيقيّة، من ردّ الدخول) ثمّ
// تُحدَّث من GET /api/v1/me. فشل التحديث لا يُخفي بيانات الجلسة ولا يُلبسها ثوب
// «محدَّث»: يُعرض سببه بجانبها.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/profile/data/profile_api.dart';

class ProfileIdentity {
  const ProfileIdentity({this.name, this.role, this.tenantId, this.userId});

  final String? name;
  final String? role;
  final String? tenantId;
  final String? userId;

  /// من ملفّ الجلسة (ردّ /auth/login: full_name، role، tenant_id، user_id).
  factory ProfileIdentity.fromSession(Map<String, dynamic>? p) =>
      ProfileIdentity(
        name: _str(p?['full_name']) ?? _str(p?['name_ar']),
        role: _str(p?['role']),
        tenantId: _str(p?['tenant_id']),
        userId: _str(p?['user_id']),
      );

  /// من GET /api/v1/me (name_ar، role، tenant_id، user_id). الاسم الغائب من
  /// الخادم يُكمَّل من الجلسة لا يُخترع.
  factory ProfileIdentity.fromMe(Map<String, dynamic> me, ProfileIdentity s) =>
      ProfileIdentity(
        name: _str(me['name_ar']) ?? s.name,
        role: _str(me['role']) ?? s.role,
        tenantId: _str(me['tenant_id']) ?? s.tenantId,
        userId: _str(me['user_id']) ?? s.userId,
      );

  static String? _str(Object? v) {
    final s = v?.toString().trim();
    return (s == null || s.isEmpty) ? null : s;
  }
}

class ProfileState {
  const ProfileState({
    required this.identity,
    this.refreshing = false,
    this.verified = false,
    this.error,
  });

  final ProfileIdentity identity;
  final bool refreshing;

  /// true ⇒ آخر قراءة من الخادم نجحت.
  final bool verified;

  /// سبب فشل آخر تحديث من الخادم (إن وُجد).
  final ApiException? error;
}

class ProfileCubit extends Cubit<ProfileState> {
  ProfileCubit(this._api, {Map<String, dynamic>? session})
    : super(ProfileState(identity: ProfileIdentity.fromSession(session)));

  final ProfileApi _api;

  Future<void> refresh() async {
    if (state.refreshing) return;
    emit(
      ProfileState(
        identity: state.identity,
        refreshing: true,
        verified: state.verified,
      ),
    );
    try {
      final me = await _api.getMe();
      if (isClosed) return;
      emit(
        ProfileState(
          identity: ProfileIdentity.fromMe(me, state.identity),
          verified: true,
        ),
      );
    } catch (e) {
      if (isClosed) return;
      emit(ProfileState(identity: state.identity, error: ApiException.from(e)));
    }
  }
}
