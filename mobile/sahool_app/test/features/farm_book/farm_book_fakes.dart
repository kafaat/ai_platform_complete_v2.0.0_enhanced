// خادم مزيّف لدفتر المزرعة فوق ApiClient الحقيقيّ (FakeAdapter): يردّ بأشكال
// simple_farm_book.py الحقيقيّة ويسجّل كلّ طلب مع معاملات الاستعلام.
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/farm_book/data/farm_book_api.dart';
import 'package:sahool_app/features/farm_book/presentation/farm_book_screen.dart';
import 'package:sahool_app/features/farms/data/farms_api.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';

import '../../core/fake_http.dart';

class Seen {
  Seen(RequestOptions o)
    : method = o.method,
      path = o.path,
      query = Map<String, dynamic>.from(o.queryParameters),
      headers = Map<String, dynamic>.from(o.headers),
      data = o.data;
  final String method;
  final String path;
  final Map<String, dynamic> query;
  final Map<String, dynamic> headers;
  final Object? data;

  Map<String, dynamic> get body => (data! as Map).cast<String, dynamic>();
}

Map<String, dynamic> entryJson({
  required String id,
  String type = 'expense',
  String method = 'cash',
  String category = 'seed',
  num amount = 1500,
  String currency = 'YER',
  String on = '2026-10-05',
  String? partyId,
  String? partyName,
  String? reverses,
  String? fieldId,
}) => {
  'entry_id': id,
  'tenant_id': '00000000-0000-0000-0000-000000000001',
  'client_operation_id': 'op-$id',
  'entry_type': type,
  'direction': type == 'income' ? 'inflow' : 'outflow',
  'payment_method': method,
  'category': category,
  'amount': amount,
  'currency': currency,
  'occurred_on': on,
  'farm_id': 'farm1',
  'field_id': fieldId,
  'season_id': null,
  'party_id': partyId,
  'party_name': partyName,
  'settles_entry_id': null,
  'settled_entry_type': null,
  'reverses_entry_id': reverses,
  'quantity': null,
  'unit': null,
  'description': null,
  'receipt_document_id': null,
  'source': 'manual_mobile',
  'sync_status': 'synced',
  'created_at': '${on}T08:00:00+00:00',
};

Map<String, dynamic> summaryJson({
  num expenses = 0,
  num income = 0,
  num net = 0,
  num cash = 0,
  num payable = 0,
  num receivable = 0,
  int count = 0,
  Map<String, num> expenseBreakdown = const {},
}) => {
  'status': 'ok',
  'currency': 'YER',
  'entries_count': count,
  'total_expenses': expenses,
  'total_income': income,
  'net': net,
  'cash_balance_effect': cash,
  'total_payable': payable,
  'total_receivable': receivable,
  'expense_breakdown': expenseBreakdown,
  'income_breakdown': <String, num>{},
  'per_hectare': null,
};

class FakeFarmBookServer {
  FakeFarmBookServer({
    List<Map<String, dynamic>>? entries,
    Map<String, dynamic>? monthlySummary,
    Map<String, dynamic>? balancesSummary,
    List<Map<String, dynamic>>? parties,
  }) : entries = entries ?? [],
       monthlySummary = monthlySummary ?? summaryJson(),
       balancesSummary = balancesSummary ?? summaryJson(),
       parties =
           parties ??
           [
             {
               'party_id': 'party_a',
               'party_type': 'supplier',
               'name': 'مورد البذور',
               'phone': null,
               'notes': null,
               'created_at': '2026-10-01T00:00:00+00:00',
             },
           ];

  final List<Map<String, dynamic>> entries;
  Map<String, dynamic> monthlySummary;
  Map<String, dynamic> balancesSummary;
  final List<Map<String, dynamic>> parties;
  final List<Seen> seen = [];

  /// يُستبدَل ردّ POST /entries (مثلاً 409/422).
  FakeReply Function(Map<String, dynamic> body)? onCreateEntry;

  /// ردّ مخصّص لأيّ طلب (null ⇒ السلوك الافتراضيّ).
  FakeReply? Function(RequestOptions o)? intercept;

  List<Seen> calls(String method, String path) =>
      seen.where((s) => s.method == method && s.path == path).toList();

  late final FakeAdapter adapter = FakeAdapter((o) async {
    seen.add(Seen(o));
    final forced = intercept?.call(o);
    if (forced != null) return forced;
    final p = o.path;
    if (p == '/api/v1/farms') {
      return const FakeReply(200, [
        {'farm_id': 'farm1', 'name': 'مزرعة الوادي', 'currency': 'YER'},
      ]);
    }
    if (p == '/api/v1/fields') {
      return const FakeReply(200, [
        {'field_id': 'f1', 'farm_id': 'farm1', 'name_ar': 'الحقل الشمالي'},
        {'field_id': 'f9', 'farm_id': 'other', 'name_ar': 'حقل مزرعة أخرى'},
      ]);
    }
    if (p == '/api/v1/farm-book/parties' && o.method == 'GET') {
      return FakeReply(200, {'items': parties, 'count': parties.length});
    }
    if (p == '/api/v1/farm-book/parties' && o.method == 'POST') {
      final b = (o.data as Map).cast<String, dynamic>();
      final row = {
        ...b,
        'phone': b['phone'],
        'notes': b['notes'],
        'created_at': '2026-10-26T00:00:00+00:00',
      };
      return FakeReply(201, row);
    }
    if (p == '/api/v1/farm-book/entries' && o.method == 'GET') {
      return FakeReply(200, {'items': entries, 'count': entries.length});
    }
    if (p == '/api/v1/farm-book/entries' && o.method == 'POST') {
      final b = (o.data as Map).cast<String, dynamic>();
      final custom = onCreateEntry;
      if (custom != null) return custom(b);
      return FakeReply(201, {
        'entry_id': 'fbe_new',
        'client_operation_id': b['client_operation_id'],
        'persisted': true,
        'replayed': false,
        'sync_status': 'synced',
      });
    }
    if (p == '/api/v1/farm-book/monthly') {
      return FakeReply(200, {
        'month': o.queryParameters['month'],
        'summary': monthlySummary,
      });
    }
    if (p == '/api/v1/farm-book/balances') {
      return FakeReply(200, {
        'as_of': o.queryParameters['as_of'],
        'summary': balancesSummary,
      });
    }
    return const FakeReply(404, {'detail': 'not_found'});
  });

  late final ApiClient client = testClient(
    adapter,
    MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
  );

  Widget app(AppRole role, {FarmBookFileSharer? sharer}) => MaterialApp(
    theme: AppTheme.light,
    locale: const Locale('ar'),
    supportedLocales: const [Locale('ar'), Locale('en')],
    localizationsDelegates: GlobalMaterialLocalizations.delegates,
    home: FarmBookScreen(
      role: role,
      api: FarmBookApi(client),
      farmsApi: FarmsApi(client),
      fieldsApi: FieldsApi(client),
      sharer: sharer ?? (_) async {},
      now: () => DateTime(2026, 10, 26, 9),
    ),
  );
}
