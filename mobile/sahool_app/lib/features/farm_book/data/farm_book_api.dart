// SAHOOL — features/farm_book/data/farm_book_api.dart
// نقاط «دفتر المزرعة» البسيط (api/routers/simple_farm_book.py). يملكه وكيل الميزة.
//
// الصلاحيّات كما يفرضها الخادم (core/authorization.py):
//   • الأطراف والقيود — قراءة: ACTIVITY_VIEW، كتابة: ACTIVITY_EXECUTE
//     (المالك/المدير/العامل يكتبون؛ المهندس يقرأ فقط).
//   • التقرير الشهريّ والأرصدة والتصدير: ANALYTICS_VIEW (المالك/المدير/المهندس).
//
// منع التكرار: الخادم يعتمد `client_operation_id` في جسم القيد (مع بصمة الطلب)،
// لا ترويسة Idempotency-Key. نرسل الاثنين بالقيمة نفسها: الترويسة تسمح لـApiClient
// بإعادة المحاولة على 502/503/504، والحقل يجعل الإعادة «replayed» لا قيداً ثانياً.
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';

import 'farm_book_models.dart';

/// ملفّ مُصدَّر من الخادم (CSV/PDF) كما وصل، بلا إعادة توليد محلّيّة.
class FarmBookExport {
  const FarmBookExport({
    required this.bytes,
    required this.filename,
    required this.mimeType,
  });
  final Uint8List bytes;
  final String filename;
  final String mimeType;
}

class FarmBookApi {
  FarmBookApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final FarmBookApi instance = FarmBookApi();
  final ApiClient _client;

  static const _base = '/api/v1/farm-book';

  /// GET /parties — [partyType] supplier|customer يُرجع معه «both» أيضاً.
  Future<List<FarmBookParty>> listParties({String? partyType}) async {
    final data = await _client.get(
      '$_base/parties',
      query: {if (partyType != null) 'party_type': partyType},
    );
    return asWrappedJsonList(data, const [
      'items',
    ]).map(FarmBookParty.fromJson).toList();
  }

  /// POST /parties (201). [body] يطابق PartyIn: party_type, name, phone?, notes?,
  /// party_id? — نمرّر party_id ثابتاً للنيّة فتصير الإعادة ON CONFLICT DO NOTHING.
  Future<FarmBookParty> createParty(
    Map<String, dynamic> body, {
    required IdempotencyKey idempotencyKey,
  }) async => FarmBookParty.fromJson(
    asJsonMap(
      await _client.post(
        '$_base/parties',
        data: body,
        idempotencyKey: idempotencyKey,
      ),
    ),
  );

  /// GET /entries — مرتّبة occurred_on تنازليّاً، بحدّ 2000 من الخادم.
  /// [from]/[to] بصيغة YYYY-MM-DD وكلاهما شامل.
  Future<List<FarmBookEntry>> listEntries({
    String? farmId,
    String? fieldId,
    String? seasonId,
    String? from,
    String? to,
  }) async {
    final data = await _client.get(
      '$_base/entries',
      query: {
        if (farmId != null) 'farm_id': farmId,
        if (fieldId != null) 'field_id': fieldId,
        if (seasonId != null) 'season_id': seasonId,
        if (from != null) 'from': from,
        if (to != null) 'to': to,
      },
    );
    return asWrappedJsonList(data, const [
      'items',
    ]).map(FarmBookEntry.fromJson).toList();
  }

  /// POST /entries (201). [body] يطابق SimpleEntryIn ويحمل
  /// `client_operation_id` = قيمة [idempotencyKey] (يُفرَض هنا).
  Future<FarmBookWriteReceipt> createEntry(
    Map<String, dynamic> body, {
    required IdempotencyKey idempotencyKey,
  }) async {
    final payload = {...body, 'client_operation_id': idempotencyKey.value};
    return FarmBookWriteReceipt.fromJson(
      asJsonMap(
        await _client.post(
          '$_base/entries',
          data: payload,
          idempotencyKey: idempotencyKey,
        ),
      ),
    );
  }

  /// GET /monthly?month=YYYY-MM — ملخّص يحسبه الخادم (القيد وعكسه يتصافيان،
  /// والعكس الواقع في شهر غير شهر الأصل يُحتسَب سالباً في شهره).
  Future<FarmBookMonthly> monthly({
    required String month,
    String? farmId,
    String? fieldId,
    String? seasonId,
  }) async {
    final data = await _client.get(
      '$_base/monthly',
      query: {
        'month': month,
        if (farmId != null) 'farm_id': farmId,
        if (fieldId != null) 'field_id': fieldId,
        if (seasonId != null) 'season_id': seasonId,
      },
    );
    return FarmBookMonthly.fromJson(asJsonMap(data));
  }

  /// GET /balances — ما علينا/ما لنا تراكميّاً حتى [asOf] (YYYY-MM-DD).
  Future<FarmBookBalances> balances({
    String? farmId,
    String? fieldId,
    String? seasonId,
    String? asOf,
  }) async {
    final data = await _client.get(
      '$_base/balances',
      query: {
        if (farmId != null) 'farm_id': farmId,
        if (fieldId != null) 'field_id': fieldId,
        if (seasonId != null) 'season_id': seasonId,
        if (asOf != null) 'as_of': asOf,
      },
    );
    return FarmBookBalances.fromJson(asJsonMap(data));
  }

  /// GET /export?month=YYYY-MM&format=csv|pdf — بايتات الملفّ كما يولّدها الخادم.
  Future<FarmBookExport> export({
    required String month,
    required String format,
    String? farmId,
    String? fieldId,
    String? seasonId,
  }) async {
    if (format != 'csv' && format != 'pdf') {
      throw ArgumentError.value(format, 'format', 'csv|pdf');
    }
    try {
      final r = await _client.dio.get<List<int>>(
        '$_base/export',
        queryParameters: {
          'month': month,
          'format': format,
          if (farmId != null) 'farm_id': farmId,
          if (fieldId != null) 'field_id': fieldId,
          if (seasonId != null) 'season_id': seasonId,
        },
        options: Options(
          responseType: ResponseType.bytes,
          receiveTimeout: const Duration(seconds: 60),
        ),
      );
      final bytes = Uint8List.fromList(r.data ?? const <int>[]);
      final mime =
          r.headers.value(Headers.contentTypeHeader) ??
          (format == 'pdf' ? 'application/pdf' : 'text/csv');
      return FarmBookExport(
        bytes: bytes,
        filename:
            filenameFromDisposition(r.headers.value('content-disposition')) ??
            'farm_book_$month.$format',
        mimeType: mime.split(';').first.trim(),
      );
    } on DioException catch (e) {
      throw ApiException.fromDio(_decodeErrorBody(e));
    }
  }

  /// اسم الملفّ من Content-Disposition، بلا مسارات.
  static String? filenameFromDisposition(String? cd) {
    if (cd == null) return null;
    final m = RegExp(r'filename="?([^";]+)"?').firstMatch(cd);
    final name = m?.group(1)?.trim();
    if (name == null ||
        name.isEmpty ||
        name.contains('/') ||
        name.contains(r'\') ||
        name.startsWith('.')) {
      return null;
    }
    return name;
  }

  /// استجابة الخطأ تصل بايتات (responseType=bytes)؛ نفكّها JSON كي يقرأ
  /// ApiException حقل `detail` (مثل reportlab_not_installed).
  static DioException _decodeErrorBody(DioException e) {
    final res = e.response;
    final data = res?.data;
    if (res == null || data is! List<int>) return e;
    final Object? decoded;
    try {
      decoded = jsonDecode(utf8.decode(data, allowMalformed: true));
    } on FormatException {
      return e;
    }
    return e.copyWith(
      response: Response<dynamic>(
        requestOptions: res.requestOptions,
        statusCode: res.statusCode,
        headers: res.headers,
        data: decoded,
      ),
    );
  }
}
