// SAHOOL — features/fields/presentation/workspace/monitoring_section.dart
// تبويب «المراقبة»: مؤشّرات الأقمار للحقل (بطاقات + مبدّل المؤشّر + رسم زمنيّ)
// من لوحة ميزة الأقمار نفسها. طبقة الخريطة ملك ميزة الخرائط.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/satellite/presentation/field_indicators_cubit.dart';
import 'package:sahool_app/features/satellite/presentation/field_indicators_panel.dart';

import '../common/cross_feature_routes.dart';
import 'workspace_deps.dart';

class WMonitoringSection extends StatelessWidget {
  const WMonitoringSection({super.key, required this.fieldId});
  final String fieldId;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (ctx) => FieldIndicatorsCubit(ctx.read<WorkspaceDeps>().satellite)
      ..loadCatalog()
      ..selectField(fieldId),
    child: Builder(
      builder: (context) => RefreshIndicator(
        onRefresh: context.read<FieldIndicatorsCubit>().refresh,
        child: ListView(
          padding: const EdgeInsets.all(SahoolSpacing.page),
          children: [
            const FieldIndicatorsPanel(),
            const SizedBox(height: SahoolSpacing.md),
            SecondaryButton(
              icon: Icons.satellite_alt_outlined,
              label: 'شاشة الأقمار الكاملة',
              onPressed: () => openFeatureRoute<void>(
                context,
                CrossFeatureRoutes.satellite,
                query: {'field_id': fieldId},
              ),
            ),
          ],
        ),
      ),
    ),
  );
}
