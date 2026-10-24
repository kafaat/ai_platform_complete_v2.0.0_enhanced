import 'package:dio/dio.dart';

import 'realtime_controller.dart';

/// Uses the existing authenticated Dio client and fixed relative endpoints.
class RealtimeApi implements RealtimeSessionApi {
  RealtimeApi(this._dio, {DateTime Function()? now}) : _now = now ?? DateTime.now;
  final Dio _dio;
  final DateTime Function() _now;

  @override
  Future<RealtimeGrant> create(String fieldId) async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/api/v1/realtime/sessions',
      data: {'field_id': fieldId, 'consent': true, 'voice_consent': true},
      options: Options(sendTimeout: const Duration(seconds: 10), receiveTimeout: const Duration(seconds: 15)),
    );
    final data = response.data;
    if (data == null || data['status'] != 'ACTIVE' || data['field_id'] != fieldId ||
        data['session_id'] is! String || data['participant_token'] is! String ||
        data['url'] is! String || data['expires_at'] is! int ||
        data['token_expires_at'] is! int) {
      throw StateError('invalid_session_response');
    }
    // SessionService enforces session_ttl <= 300 and token_ttl <= 60.
    // A five-second clock tolerance matches the independent web client.
    final now = _now().millisecondsSinceEpoch ~/ 1000;
    final expiry = data['expires_at'] as int;
    final tokenExpiry = data['token_expires_at'] as int;
    final id = data['session_id'] as String;
    final token = data['participant_token'] as String;
    if (id.isEmpty || id.length > 128 || token.isEmpty || token.length > 16384 ||
        expiry <= now || expiry > now + 305 || tokenExpiry <= now ||
        tokenExpiry > now + 65 || tokenExpiry > expiry) {
      throw StateError('invalid_session_lease');
    }
    final url = Uri.parse(data['url'] as String);
    if (url.scheme != 'wss' || url.host.isEmpty || url.userInfo.isNotEmpty ||
        url.hasQuery || url.hasFragment) {
      throw StateError('invalid_media_origin');
    }
    return RealtimeGrant(
      id: id,
      fieldId: fieldId,
      url: url.toString(),
      token: token,
      expiresAt: DateTime.fromMillisecondsSinceEpoch(expiry * 1000, isUtc: true),
    );
  }

  @override
  Future<void> close(String sessionId) async {
    await _dio.delete<void>('/api/v1/realtime/sessions/${Uri.encodeComponent(sessionId)}',
      options: Options(sendTimeout: const Duration(seconds: 5), receiveTimeout: const Duration(seconds: 5)),
    );
  }
}
