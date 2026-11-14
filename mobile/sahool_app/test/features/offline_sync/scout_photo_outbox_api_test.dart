// صورة المشاهدة المؤجَّلة (v260): يعيد الصندوق إرسال بايتات نسخة الجهاز المنطَّقة
// بالمستأجِر، لا JSON، ويرفض قبل الشبكة ملفّاً تغيّر أو عمليّةً لا تطابق حقلها.
// ApiClient و OfflineSyncApi حقيقيّان بمحوّل HTTP مزيّف.
import 'dart:typed_data';

import 'package:crypto/crypto.dart' as crypto;
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/offline_sync/data/offline_sync_api.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';
import 'package:sahool_app/features/scouting/data/scouting_api.dart';

import '../../core/fake_http.dart';
import '../scouting/scouting_fakes.dart';

void main() {
  const pin = '019a3350-1983-719d-91e4-111111111111';
  const field = 'f1';
  const key = '019a3350-1983-719d-91e4-222222222222';
  late MemoryPhotoStore photos;
  late Uint8List savedBytes;
  late String sha;

  OutboxOp ticket({String? expectedSha, String? requestedField}) => OutboxOp(
    kind: kObservationPhotoKind,
    method: 'POST',
    path: scoutingPhotoPath(field, pin),
    fieldId: requestedField ?? field,
    body: {'field_id': field, 'pin_id': pin, 'sha256': expectedSha ?? sha},
    idempotencyKey: key,
  );

  OfflineSyncApi apiWith(FakeAdapter adapter) => OfflineSyncApi(
    testClient(
      adapter,
      MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
    ),
    photos,
  );

  setUp(() async {
    photos = MemoryPhotoStore();
    await photos.keep(pin, jpegPhoto());
    savedBytes = await photos.read((await photos.find(pin))!);
    sha = crypto.sha256.convert(savedBytes).toString();
  });

  test('replays the exact photo bytes and digest, not a JSON placeholder', () async {
    final adapter = FakeAdapter(
      (o) async => FakeReply(200, {
        'evidence_id': 'evidence-1',
        'field_id': field,
        'pin_id': pin,
        'sha256': sha,
        'persisted': true,
        'verification_state': 'bytes_verified',
        'review_state': 'unreviewed',
      }),
    );
    final response = await apiWith(adapter).sendOp(ticket());
    expect(response['sha256'], sha);
    expect(adapter.requests, hasLength(1));
    expect(adapter.requests.single.data, orderedEquals(savedBytes));
    expect(adapter.requests.single.headers['X-Content-SHA256'], sha);
    expect(adapter.requests.single.headers[kIdempotencyHeader], key);
    expect(adapter.requests.single.path, scoutingPhotoPath(field, pin));
  });

  test('a modified photo is rejected before any network upload', () async {
    final adapter = FakeAdapter((o) async => const FakeReply(200, {}));
    final ex = apiWith(
      adapter,
    ).sendOp(ticket(expectedSha: List.filled(64, '0').join()));
    await expectLater(
      ex,
      throwsA(
        isA<ApiException>().having((e) => e.kind, 'kind', ApiErrorKind.validation),
      ),
    );
    expect(adapter.requests, isEmpty);
  });

  test('a ticket for another field is rejected without sending', () async {
    final adapter = FakeAdapter((o) async => const FakeReply(200, {}));
    await expectLater(
      apiWith(adapter).sendOp(ticket(requestedField: 'other-field')),
      throwsA(isA<ApiException>()),
    );
    expect(adapter.requests, isEmpty);
  });

  test('an unrelated 2xx receipt is retriable, never a sent receipt', () async {
    final adapter = FakeAdapter(
      (o) async => FakeReply(200, {
        'evidence_id': 'e1',
        'field_id': field,
        'pin_id': 'other-pin',
        'sha256': sha,
        'persisted': true,
        'verification_state': 'bytes_verified',
        'review_state': 'unreviewed',
      }),
    );
    await expectLater(
      apiWith(adapter).sendOp(ticket()),
      throwsA(
        isA<ApiException>().having((e) => e.kind, 'kind', ApiErrorKind.unavailable),
      ),
    );
  });

  test('missing local bytes cannot be silently confirmed', () async {
    photos.byPin.clear();
    final adapter = FakeAdapter((o) async => const FakeReply(200, {}));
    await expectLater(
      apiWith(adapter).sendOp(ticket()),
      throwsA(
        isA<ApiException>().having((e) => e.kind, 'kind', ApiErrorKind.validation),
      ),
    );
    expect(adapter.requests, isEmpty);
  });

  test('the rejected ticket is classified as rejected (422), the bad receipt as retry', () {
    expect(
      classifyOutboxFailure(
        const ApiException(
          kind: ApiErrorKind.validation,
          statusCode: 422,
          messageAr: 'x',
        ),
      ).kind,
      OutboxOutcomeKind.rejected,
    );
    expect(
      classifyOutboxFailure(
        const ApiException(
          kind: ApiErrorKind.unavailable,
          statusCode: 503,
          messageAr: 'x',
        ),
      ).kind,
      OutboxOutcomeKind.retryLater,
    );
  });
}
