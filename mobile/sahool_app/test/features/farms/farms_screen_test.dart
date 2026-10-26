// المزارع: الإنشاء للمالك فقط (كان أيّ دور غير viewer — المدير يصطدم بـ403)،
// عدد الحقول من GET /api/v1/fields، ومفتاح Idempotency ثابت عبر إعادة الإرسال.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/features/farms/data/farms_api.dart';
import 'package:sahool_app/features/farms/presentation/farm_permissions.dart';
import 'package:sahool_app/features/farms/presentation/farms_screen.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';

import '../../core/fake_http.dart';
import '../fields/harness.dart';

Backend backend({List<Map<String, dynamic>>? farms, int createStatus = 201}) {
  final list =
      farms ??
      [
        {
          'farm_id': 'frm_1',
          'name': 'مزرعة الوادي',
          'region': 'إب',
          'area_ha': 12.5,
        },
        {
          'farm_id': 'frm_2',
          'name': 'مزرعة الجبل',
          'region': null,
          'area_ha': null,
        },
      ];
  return Backend({
    '/api/v1/farms': (o) {
      if (o.method == 'POST') {
        return FakeReply(createStatus, {'farm_id': 'frm_3', 'name': 'جديدة'});
      }
      return ok(list);
    },
    '/api/v1/fields': (_) => ok([
      {'field_id': 'a', 'farm_id': 'frm_1', 'name_ar': 'أ'},
      {'field_id': 'b', 'farm_id': 'frm_1', 'name_ar': 'ب'},
      {'field_id': 'c', 'farm_id': '', 'name_ar': 'ج'},
    ]),
  });
}

Widget screen(Backend b, AppRole role) => host(
  FarmsScreen(
    key: UniqueKey(),
    api: FarmsApi(b.client),
    fieldsApi: FieldsApi(b.client),
    role: () => role,
  ),
);

void main() {
  test('only the owner may create a farm (web permissions.ts create:farm)', () {
    expect(canCreateFarm(AppRole.owner), isTrue);
    for (final r in [
      AppRole.manager,
      AppRole.agronomist,
      AppRole.worker,
      AppRole.viewer,
    ]) {
      expect(canCreateFarm(r), isFalse, reason: r.name);
    }
  });

  testWidgets('manager sees farms but no create button', (t) async {
    await t.pumpWidget(screen(backend(), AppRole.manager));
    await t.pumpAndSettle();
    expect(find.text('مزرعة الوادي'), findsOneWidget);
    expect(find.byKey(const ValueKey('create_farm_fab')), findsNothing);
  });

  testWidgets(
    'owner sees the create button; empty list invites only the owner',
    (t) async {
      await t.pumpWidget(screen(backend(), AppRole.owner));
      await t.pumpAndSettle();
      expect(find.byKey(const ValueKey('create_farm_fab')), findsOneWidget);

      await t.pumpWidget(screen(backend(farms: []), AppRole.worker));
      await t.pumpAndSettle();
      expect(find.text('إنشاء المزارع متاح لمالك الحساب فقط.'), findsOneWidget);
      expect(find.text('إنشاء مزرعة'), findsNothing);
    },
  );

  testWidgets('fields count per farm comes from the fields list; area missing '
      'is "غير مقيس"', (t) async {
    await t.pumpWidget(screen(backend(), AppRole.viewer));
    await t.pumpAndSettle();
    expect(find.textContaining('حقلان'), findsOneWidget);
    expect(find.textContaining('لا حقول بعد'), findsOneWidget);
    expect(find.textContaining('12.5 هـ'), findsOneWidget);
    expect(find.textContaining('غير مقيس'), findsOneWidget);
  });

  testWidgets('create: validation inline, Arabic digits, same idempotency key '
      'on retry after a 503', (t) async {
    final b = backend(createStatus: 503);
    await t.pumpWidget(screen(b, AppRole.owner));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const ValueKey('create_farm_fab')));
    await t.pumpAndSettle();

    await t.tap(find.text('إنشاء المزرعة'));
    await t.pumpAndSettle();
    expect(find.text('اسم المزرعة مطلوب'), findsOneWidget);
    expect(b.seen.where((o) => o.method == 'POST'), isEmpty);

    await t.enterText(
      find.byKey(const ValueKey('farm_name')).last,
      'مزرعة السهل',
    );
    await t.enterText(find.byKey(const ValueKey('farm_area')).last, '٢٫٥');
    await t.tap(find.text('إنشاء المزرعة'));
    await t.pumpAndSettle();
    expect(find.textContaining('الخدمة غير متاحة'), findsOneWidget);

    await t.tap(find.text('إنشاء المزرعة'));
    await t.pumpAndSettle();
    final posts = b.seen.where((o) => o.method == 'POST').toList();
    expect(posts.length, greaterThanOrEqualTo(2));
    final keys = posts.map((o) => o.headers[kIdempotencyHeader]).toSet();
    expect(keys.length, 1, reason: 'نيّة واحدة ⇒ مفتاح واحد');
    expect(keys.single, isNotNull);
    expect((posts.first.data as Map)['area_ha'], 2.5);
    expect((posts.first.data as Map)['name'], 'مزرعة السهل');
  });
}
