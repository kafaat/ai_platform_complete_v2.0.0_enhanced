// منطق نموذج الموسم: التحقّق يطابق ما يرفضه الخادم، التواريخ بأسماء الأشهر
// العربيّة، جسم PATCH بالحقول المتغيّرة فقط، وانتقالات الحالة مرآة season_lifecycle.
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/features/crop_season/data/season_models.dart';
import 'package:sahool_app/features/crop_season/presentation/phenology_cards.dart';
import 'package:sahool_app/features/crop_season/presentation/season_form_logic.dart';

Season season({
  String status = 'active',
  String? sowing = '2026-03-05',
  String? end,
  double? target,
  int? version,
}) => Season.fromJson({
  'season_id': 'ssn_1',
  'field_id': 'f1',
  'crops': ['wheat', 'common_bean'],
  'status': status,
  'cultivar': 'بكّور',
  'sowing_date': sowing,
  'season_end': end,
  'target_yield_kg_ha': target,
  'row_version': version,
  'stages': [],
});

void main() {
  group('validateSeasonForm', () {
    test('crop and planting date are required', () {
      final e = validateSeasonForm(const SeasonFormInput());
      expect(e[SeasonFormField.crop], 'اختر المحصول');
      expect(e[SeasonFormField.sowing], 'حدّد تاريخ الزراعة');
    });

    test('expected harvest before planting is rejected (server 422)', () {
      final e = validateSeasonForm(
        SeasonFormInput(
          crop: 'wheat',
          sowingDate: DateTime(2026, 3, 5),
          seasonEnd: DateTime(2026, 3, 4),
        ),
      );
      expect(e[SeasonFormField.end], 'تاريخ الحصاد المتوقّع قبل تاريخ الزراعة');
    });

    test('harvest on the planting day is allowed', () {
      final e = validateSeasonForm(
        SeasonFormInput(
          crop: 'wheat',
          sowingDate: DateTime(2026, 3, 5),
          seasonEnd: DateTime(2026, 3, 5),
        ),
      );
      expect(e, isEmpty);
    });

    test(
      'target yield accepts Arabic-Indic digits and rejects junk/negatives',
      () {
        SeasonFormInput withYield(String y) => SeasonFormInput(
          crop: 'wheat',
          sowingDate: DateTime(2026, 3, 5),
          targetYieldText: y,
        );
        expect(validateSeasonForm(withYield('٤٢٠٠٫٥')), isEmpty);
        expect(
          validateSeasonForm(withYield('abc'))[SeasonFormField.targetYield],
          'أدخل رقماً صحيحاً',
        );
        expect(
          validateSeasonForm(withYield('-1'))[SeasonFormField.targetYield],
          'لا تكون الإنتاجيّة سالبة',
        );
        expect(
          buildCreateBody(withYield('٤٢٠٠٫٥'))['target_yield_kg_ha'],
          4200.5,
        );
      },
    );

    test('cultivar over 100 chars mirrors the server max_length', () {
      final e = validateSeasonForm(
        SeasonFormInput(
          crop: 'wheat',
          sowingDate: DateTime(2026, 3, 5),
          cultivar: 'x' * 101,
        ),
      );
      expect(e[SeasonFormField.cultivar], isNotNull);
    });

    test('edit: clearing a saved date is refused (PATCH cannot clear it)', () {
      final e = validateSeasonForm(
        SeasonFormInput(crop: 'wheat', sowingDate: DateTime(2026, 3, 5)),
        original: season(end: '2026-07-01'),
      );
      expect(e[SeasonFormField.end], 'لا يمكن مسح تاريخ الحصاد بعد حفظه');
    });
  });

  group('request bodies', () {
    test('create sends crop_id and ISO days', () {
      final b = buildCreateBody(
        SeasonFormInput(
          crop: 'wheat',
          cultivar: ' بكّور ',
          irrigationType: 'drip',
          sowingDate: DateTime(2026, 3, 5),
          seasonEnd: DateTime(2026, 7, 1),
        ),
      );
      expect(b, {
        'crops': ['wheat'],
        'cultivar': 'بكّور',
        'irrigation_type': 'drip',
        'sowing_date': '2026-03-05',
        'season_end': '2026-07-01',
      });
    });

    test('patch carries only changed fields and keeps intercrops', () {
      final o = season(target: 4000, version: 3);
      final unchanged = buildPatchBody(
        SeasonFormInput(
          crop: 'wheat',
          cultivar: 'بكّور',
          sowingDate: DateTime(2026, 3, 5),
          targetYieldText: '4000',
        ),
        o,
      );
      expect(unchanged, isEmpty);
      final b = buildPatchBody(
        SeasonFormInput(
          crop: 'barley',
          cultivar: 'بكّور',
          sowingDate: DateTime(2026, 3, 5),
          seasonEnd: DateTime(2026, 7, 1),
          targetYieldText: '4000',
        ),
        o,
      );
      expect(b, {
        'crops': ['barley', 'common_bean'],
        'season_end': '2026-07-01',
        'base_version': 3,
      });
    });
  });

  group('dates are shown with Arabic month names', () {
    test('server ISO day renders as day + Arabic month + year', () {
      expect(fmtIsoDate('2026-03-05'), '5 مارس 2026');
      expect(
        fmtDayRange('2026-03-05', '2026-04-20'),
        '5 مارس 2026 – 20 أبريل 2026',
      );
      expect(fmtIsoDate(null), '—');
    });

    test('ISO day round-trips without a timezone shift', () {
      final d = parseIsoDay('2026-12-31')!;
      expect(isoDay(d), '2026-12-31');
      expect(fmtDate(d), '31 ديسمبر 2026');
    });
  });

  group('season status transitions mirror season_lifecycle.py', () {
    test('planned → active/closed, active → closed, closed is final', () {
      expect(SeasonStatus.planned.allowedTargets, {
        SeasonStatus.active,
        SeasonStatus.closed,
      });
      expect(SeasonStatus.active.allowedTargets, {SeasonStatus.closed});
      expect(SeasonStatus.closed.allowedTargets, isEmpty);
      expect(
        SeasonStatus.active.canTransitionTo(SeasonStatus.planned),
        isFalse,
      );
      expect(SeasonStatus.parse('archived'), isNull);
    });
  });

  group('seasonWriteError', () {
    test('409 shows the server message_ar, not the generic conflict text', () {
      const e = ApiException(
        kind: ApiErrorKind.conflict,
        statusCode: 409,
        messageAr: 'تعارض: السجلّ موجود مسبقاً.',
        detail: {'message_ar': 'يوجد موسم نشط لهذا الحقل بالفعل'},
      );
      expect(seasonWriteError(e), 'يوجد موسم نشط لهذا الحقل بالفعل');
    });

    test('422 custom stage errors are joined', () {
      const e = ApiException(
        kind: ApiErrorKind.validation,
        statusCode: 422,
        messageAr: 'x',
        detail: {
          'code': 'invalid_custom_stages',
          'errors_ar': ['أ', 'ب'],
        },
      );
      expect(seasonWriteError(e), 'أ\nب');
    });

    test('503 keeps the contract wording', () {
      const e = ApiException(
        kind: ApiErrorKind.unavailable,
        statusCode: 503,
        messageAr:
            'الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة على الخادم).',
        detail: {'message_ar': 'تفاصيل داخليّة'},
      );
      expect(
        seasonWriteError(e),
        'الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة على الخادم).',
      );
    });
  });
}
