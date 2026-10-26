// SAHOOL — features/fields/presentation/workspace/soil_section.dart
// تبويب «التربة»: نوع التربة وكيمياؤها من تفاصيل الحقل (FieldDetail داخل مساحة
// الموسم: soil_ph/soil_ec/soil_om/soil_n/p/k) وفحوص المختبر المسجّلة. الغائب
// «غير مقيس»، ورابط أخذ العيّنات يفتح ميزة المختبر.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../common/cross_feature_routes.dart';
import '../common/field_labels.dart';
import '../common/load_cubit.dart';
import 'workspace_deps.dart';
import 'workspace_widgets.dart';

/// قيمة رقميّة مع وحدة، أو «غير مقيس».
String _v(Object? raw, {String unit = '', int decimals = 1}) {
  final n = wNum(raw);
  if (n == null) return kNotMeasured;
  final s = fmtNumber(n, decimals: decimals);
  return unit.isEmpty ? s : '$s $unit';
}

class WSoilSection extends StatelessWidget {
  const WSoilSection({super.key, required this.fieldId, required this.field});

  final String fieldId;

  /// الحقل كما وصل للشاشة (احتياط حين لا تحمل مساحة الموسم تفاصيله).
  final Map<String, dynamic> field;

  @override
  Widget build(
    BuildContext context,
  ) => BlocBuilder<SeasonWorkspaceCubit, LoadState<Map<String, dynamic>>>(
    builder: (context, ws) {
      final cubit = context.read<SeasonWorkspaceCubit>();
      return RefreshIndicator(
        onRefresh: cubit.refresh,
        child: ListView(
          padding: const EdgeInsets.all(SahoolSpacing.page),
          children: [
            WSectionCard(
              title: 'خصائص التربة',
              icon: Icons.landscape_outlined,
              child: LoadStateView<Map<String, dynamic>>(
                state: ws,
                onRetry: cubit.load,
                builder: (context, d) {
                  final f = {...field, ...wMap(d['field'])};
                  return Column(
                    children: [
                      WInfoRow(
                        'نوع التربة',
                        wText(
                          f['soil_type_ar'] ?? f['soil_type'],
                          kNotMeasured,
                        ),
                      ),
                      WInfoRow('درجة الحموضة (pH)', _v(f['soil_ph'])),
                      WInfoRow(
                        'الملوحة (EC)',
                        _v(f['soil_ec'], unit: 'dS/m', decimals: 2),
                      ),
                      WInfoRow(
                        'المادّة العضويّة',
                        wNum(f['soil_om']) == null
                            ? kNotMeasured
                            : fmtPct(wNum(f['soil_om']), decimals: 1),
                      ),
                      WInfoRow('النيتروجين (N)', _v(f['soil_n'], unit: 'ppm')),
                      WInfoRow('الفوسفور (P)', _v(f['soil_p'], unit: 'ppm')),
                      WInfoRow('البوتاسيوم (K)', _v(f['soil_k'], unit: 'ppm')),
                      WInfoRow(
                        'ملوحة ماء الريّ',
                        _v(f['water_ec'], unit: 'dS/m', decimals: 2),
                      ),
                    ],
                  );
                },
              ),
            ),
            WSectionCard(
              title: 'فحوص المختبر',
              icon: Icons.science_outlined,
              child: LoadStateView<Map<String, dynamic>>(
                state: ws,
                onRetry: cubit.load,
                builder: (context, d) {
                  final tests = wList(d['soil_tests']);
                  if (tests.isEmpty) {
                    return Text(
                      'لا فحوص تربة مسجّلة لهذا الحقل بعد.',
                      style: context.textStyles.bodyMedium,
                    );
                  }
                  return Column(
                    children: [
                      for (final t in tests)
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Text(wText(t['lab_name'], 'مختبر غير محدّد')),
                          subtitle: Text(
                            [
                              'أُخذت ${fmtDay(t['sampled_on'])}',
                              if (wNum(wMap(t['result'])['ph']) != null)
                                'pH ${_v(wMap(t['result'])['ph'])}',
                              if (wNum(wMap(t['result'])['ec_ds_m']) != null)
                                'EC ${_v(wMap(t['result'])['ec_ds_m'], decimals: 2)}',
                            ].join(' · '),
                          ),
                          trailing: wText(t['status'], '').isEmpty
                              ? null
                              : StatusChip(
                                  label: t['status'] == 'published'
                                      ? 'منشور'
                                      : wText(t['status']),
                                  tone: t['status'] == 'published'
                                      ? StatusTone.success
                                      : StatusTone.neutral,
                                ),
                        ),
                    ],
                  );
                },
              ),
            ),
            SecondaryButton(
              icon: Icons.colorize_outlined,
              label: 'أخذ عيّنة تربة',
              onPressed: () => openFeatureRoute<void>(
                context,
                CrossFeatureRoutes.labSampling,
                query: {'field_id': fieldId},
              ),
            ),
          ],
        ),
      );
    },
  );
}
