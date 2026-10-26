// تبويب «الحقول» يبقى حيّاً في الغلاف: حين يُنشأ حقل في مكان آخر (المعالج،
// الاستيراد، مشي GPS) يُعيد تحميل القائمة بصمت عبر FieldCreatedEvents، ويُلغي
// اشتراكه عند الإغلاق.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/features/farms/data/farms_api.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/fields/presentation/common/load_cubit.dart';
import 'package:sahool_app/features/fields/presentation/fields_list_cubit.dart';
import 'package:sahool_app/features/fields/presentation/fields_screen.dart';
import 'package:sahool_app/features/maps/draw/field_created_events.dart';

import 'harness.dart';

void main() {
  var fields = <Map<String, dynamic>>[
    {'field_id': 'f1', 'name_ar': 'حقل البنّ'},
  ];
  Backend backend() => Backend({
    '/api/v1/fields': (_) => ok(fields),
    '/api/v1/farms': (_) => ok(<dynamic>[]),
  });
  setUp(
    () => fields = [
      {'field_id': 'f1', 'name_ar': 'حقل البنّ'},
    ],
  );

  test('a created-field event reloads silently; close cancels the '
      'subscription', () async {
    final events = StreamController<Object?>.broadcast();
    final b = backend();
    final cubit = FieldsListCubit(
      FieldsApi(b.client),
      FarmsApi(b.client),
      fieldCreated: events.stream,
    );
    await cubit.load();
    expect(b.to('/api/v1/fields'), hasLength(1));
    expect(events.hasListener, isTrue);

    fields = [
      ...fields,
      {'field_id': 'f2', 'name_ar': 'حقل جديد'},
    ];
    final states = <FieldsListState>[];
    final sub = cubit.stream.listen(states.add);
    events.add({'field_id': 'f2'});
    await Future<void>.delayed(const Duration(milliseconds: 50));
    expect(b.to('/api/v1/fields'), hasLength(2));
    // صامت: لا مؤشّر تحميل يستبدل القائمة الظاهرة.
    expect(states.where((s) => s.fields is LoadLoading), isEmpty);
    expect((cubit.state.fields as LoadLoaded).data, hasLength(2));

    await sub.cancel();
    await cubit.close();
    expect(events.hasListener, isFalse);
    await events.close();
  });

  testWidgets('the fields screen picks up a field created elsewhere', (
    t,
  ) async {
    final b = backend();
    await t.pumpWidget(
      host(
        FieldsScreen(
          fieldsApi: FieldsApi(b.client),
          farmsApi: FarmsApi(b.client),
          role: () => AppRole.worker,
        ),
      ),
    );
    await t.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 20)),
    );
    await t.pumpAndSettle();
    expect(find.text('حقل البنّ'), findsOneWidget);
    expect(find.text('حقل الذرة الجديد'), findsNothing);

    fields = [
      ...fields,
      {'field_id': 'f9', 'name_ar': 'حقل الذرة الجديد'},
    ];
    FieldCreatedEvents.instance.notifyCreated({'field_id': 'f9'});
    await t.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 20)),
    );
    await t.pumpAndSettle();
    expect(find.text('حقل الذرة الجديد'), findsOneWidget);
  });
}
