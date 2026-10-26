// SAHOOL — features/weather/presentation/weather_screen.dart
// طقس الحقل: الآن، تنبيهات الطقس، نوافذ العمليّات (الرشّ/الريّ أوّلاً)، توقّعات
// 7 أيّام، توصية الريّ، خطر الأمراض، الإجهاد الحراريّ وإجهاد المحصول. مرآة سلوك
// الويب WeatherAdvicePage.tsx وFieldWorkspaceWeatherPanel.tsx — بلا حساب طقس في
// العميل: كلّ قرار من الخادم.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';

import '../data/weather_api.dart';
import '../data/weather_models.dart';
import 'weather_cubit.dart';
import 'weather_format.dart';

typedef FieldsLoader = Future<List<Map<String, dynamic>>> Function();

/// بلا [fieldId]: اختيار الحقل. معه: طقس الحقل.
class WeatherScreen extends StatelessWidget {
  const WeatherScreen({super.key, this.fieldId, this.api, this.loadFields});
  final String? fieldId;
  final WeatherApi? api;

  /// للاختبار؛ الافتراضيّ FieldsApi.listFields.
  final FieldsLoader? loadFields;

  @override
  Widget build(BuildContext context) {
    final id = fieldId;
    if (id == null || id.isEmpty) {
      return _FieldPicker(
        api: api,
        loader: loadFields ?? FieldsApi.instance.listFields,
      );
    }
    return BlocProvider(
      create: (_) => WeatherCubit(api ?? WeatherApi.instance, id)..load(),
      child: const _FieldWeatherView(),
    );
  }
}

// ── اختيار الحقل ───────────────────────────────────────────────────

@immutable
class _FieldsState {
  const _FieldsState({this.fields, this.error});
  final List<Map<String, dynamic>>? fields;
  final ApiException? error;
}

class _FieldsCubit extends Cubit<_FieldsState> {
  _FieldsCubit(this._loader) : super(const _FieldsState());
  final FieldsLoader _loader;

  Future<void> load() async {
    emit(const _FieldsState());
    try {
      final f = await _loader();
      if (!isClosed) emit(_FieldsState(fields: f));
    } catch (e) {
      if (!isClosed) emit(_FieldsState(error: ApiException.from(e)));
    }
  }
}

class _FieldPicker extends StatelessWidget {
  const _FieldPicker({required this.api, required this.loader});
  final WeatherApi? api;
  final FieldsLoader loader;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) => _FieldsCubit(loader)..load(),
    child: Builder(
      builder: (context) {
        final cubit = context.read<_FieldsCubit>();
        return AppScaffold(
          title: 'الطقس',
          onRefresh: cubit.load,
          body: BlocBuilder<_FieldsCubit, _FieldsState>(
            builder: (context, s) {
              if (s.error != null) {
                return ErrorState(error: s.error!, onRetry: cubit.load);
              }
              final fields = s.fields;
              if (fields == null) {
                return const LoadingState(message: 'جارٍ تحميل الحقول…');
              }
              if (fields.isEmpty) {
                return const EmptyState(
                  icon: Icons.layers_clear_outlined,
                  title: 'لا حقول',
                  message: 'أضف حقلاً بموقعه ليظهر طقسه هنا.',
                );
              }
              return ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                children: [
                  const ListSectionHeader('اختر الحقل'),
                  for (final f in fields) _fieldTile(context, f),
                ],
              );
            },
          ),
        );
      },
    ),
  );

  Widget _fieldTile(BuildContext context, Map<String, dynamic> f) {
    final id = f['field_id']?.toString() ?? '';
    final name = (f['name_ar'] ?? f['name'] ?? id).toString();
    final hasCoords = f['lat'] is num && f['lon'] is num;
    final crop = f['crop']?.toString();
    return AppListTile(
      icon: hasCoords ? Icons.cloud_outlined : Icons.cloud_off_outlined,
      title: name,
      subtitle: [
        if (crop != null && crop.isNotEmpty) crop,
        if (!hasCoords) kNoFieldWeather,
      ].join(' · '),
      onTap: id.isEmpty
          ? null
          : () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => WeatherScreen(fieldId: id, api: api),
              ),
            ),
    );
  }
}

// ── طقس الحقل ──────────────────────────────────────────────────────

class _FieldWeatherView extends StatelessWidget {
  const _FieldWeatherView();

  @override
  Widget build(BuildContext context) {
    final cubit = context.read<WeatherCubit>();
    return BlocBuilder<WeatherCubit, WeatherState>(
      builder: (context, s) {
        final loc = s.location;
        final title = loc.data?.nameAr == null
            ? 'طقس الحقل'
            : 'طقس ${loc.data!.nameAr}';
        Widget body;
        if (loc.isLoading) {
          body = const LoadingState(message: 'جارٍ تحميل طقس الحقل…');
        } else if (loc.status == SectionStatus.failed) {
          body = ErrorState(
            title: 'تعذّر تحميل الحقل',
            error: loc.error!,
            onRetry: cubit.load,
          );
        } else if (s.noCoordinates) {
          body = const EmptyState(
            icon: Icons.cloud_off_outlined,
            title: kNoFieldWeather,
            message: kNoCoordinatesReason,
          );
        } else {
          body = _sections(context, s);
        }
        return AppScaffold(title: title, onRefresh: cubit.load, body: body);
      },
    );
  }

  Widget _sections(BuildContext context, WeatherState s) {
    const gap = SizedBox(height: SahoolSpacing.md);
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(SahoolSpacing.md),
      children: [
        _CurrentCard(section: s.current),
        gap,
        _WeatherAlertsCard(section: s.alerts),
        gap,
        _WindowsCard(section: s.windows),
        gap,
        _ForecastCard(section: s.forecast),
        gap,
        _IrrigationCard(section: s.irrigation),
        gap,
        _DiseaseCard(section: s.disease),
        gap,
        _ThermalCard(section: s.thermal),
        gap,
        _CropStressCard(section: s.cropStress),
        if (s.loadedAt != null)
          Padding(
            padding: const EdgeInsets.only(top: SahoolSpacing.md),
            child: Text(
              'آخر تحميل: ${fmtDateTime(s.loadedAt)}',
              textAlign: TextAlign.center,
              style: context.textStyles.bodySmall?.copyWith(
                color: context.tokens.muted,
              ),
            ),
          ),
        const SizedBox(height: SahoolSpacing.xl),
      ],
    );
  }
}

/// غلاف قسم: بطاقة بعنوان + حالة (تحميل/فشل/غير متاح) أو المحتوى.
class _SectionShell<T> extends StatelessWidget {
  const _SectionShell({
    required this.title,
    required this.icon,
    required this.section,
    required this.builder,
  });
  final String title;
  final IconData icon;
  final Section<T> section;
  final Widget Function(BuildContext, T) builder;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    Widget child;
    switch (section.status) {
      case SectionStatus.loading:
        child = const Padding(
          padding: EdgeInsets.symmetric(vertical: SahoolSpacing.sm),
          child: LinearProgressIndicator(),
        );
      case SectionStatus.failed:
        child = Row(
          children: [
            Icon(ErrorState.iconFor(section.error!), color: t.danger),
            const SizedBox(width: SahoolSpacing.sm),
            Expanded(
              child: Text(
                weatherErrorText(section.error!),
                style: context.textStyles.bodyMedium,
              ),
            ),
          ],
        );
      case SectionStatus.unavailable:
        child = Text(
          section.reasonAr!,
          style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
        );
      case SectionStatus.ready:
        child = builder(context, section.data as T);
    }
    return SectionCard(title: title, icon: icon, child: child);
  }
}

class _CurrentCard extends StatelessWidget {
  const _CurrentCard({required this.section});
  final Section<CurrentWeather> section;

  @override
  Widget build(BuildContext context) => _SectionShell<CurrentWeather>(
    title: 'الطقس الآن',
    icon: Icons.wb_sunny_outlined,
    section: section,
    builder: (context, c) {
      final t = context.tokens;
      final tiles = [
        MetricTile(
          label: 'الحرارة',
          value: c.temperatureC,
          unit: '°م',
          decimals: 0,
          icon: Icons.thermostat_outlined,
        ),
        MetricTile(
          label: 'الرطوبة',
          value: c.humidityPct,
          unit: '٪',
          decimals: 0,
          icon: Icons.water_drop_outlined,
        ),
        MetricTile(
          label: 'الرياح',
          value: c.windKmh,
          unit: 'كم/س',
          decimals: 0,
          icon: Icons.air_rounded,
        ),
        MetricTile(
          label: 'الهطول',
          value: c.precipitationMm,
          unit: 'مم',
          icon: Icons.umbrella_outlined,
        ),
      ];
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            weatherCodeAr(c.weatherCode),
            style: context.textStyles.titleMedium,
          ),
          const SizedBox(height: SahoolSpacing.sm),
          LayoutBuilder(
            builder: (context, box) {
              final w = (box.maxWidth - SahoolSpacing.sm) / 2;
              return Wrap(
                spacing: SahoolSpacing.sm,
                runSpacing: SahoolSpacing.sm,
                children: [
                  for (final tile in tiles) SizedBox(width: w, child: tile),
                ],
              );
            },
          ),
          if (c.time != null) ...[
            const SizedBox(height: SahoolSpacing.sm),
            Text(
              'وقت القراءة: ${fmtDateTime(c.time)}',
              style: context.textStyles.bodySmall?.copyWith(color: t.muted),
            ),
          ],
          if (c.degraded) ...[
            const SizedBox(height: SahoolSpacing.xs),
            Text(
              'بعض القياسات لم يرسلها مزوّد الطقس — تُعرَض «غير مقيس».',
              style: context.textStyles.bodySmall?.copyWith(color: t.warning),
            ),
          ],
        ],
      );
    },
  );
}

class _WeatherAlertsCard extends StatelessWidget {
  const _WeatherAlertsCard({required this.section});
  final Section<List<WeatherAlert>> section;

  StatusTone _tone(String? s) => switch (s) {
    'critical' => StatusTone.danger,
    'warning' => StatusTone.warning,
    'info' => StatusTone.info,
    _ => StatusTone.neutral,
  };

  String _label(String? s) => switch (s) {
    'critical' => 'حرج',
    'warning' => 'تحذير',
    'info' => 'معلومة',
    _ => 'غير مصنّف',
  };

  @override
  Widget build(BuildContext context) => _SectionShell<List<WeatherAlert>>(
    title: 'تنبيهات الطقس',
    icon: Icons.thunderstorm_outlined,
    section: section,
    builder: (context, list) {
      if (list.isEmpty) {
        return Text(
          'لا تنبيهات طقس حاليّاً لموقع الحقل.',
          style: context.textStyles.bodyMedium?.copyWith(
            color: context.tokens.muted,
          ),
        );
      }
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final a in list)
            Padding(
              padding: const EdgeInsets.only(bottom: SahoolSpacing.sm),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(
                    spacing: SahoolSpacing.sm,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      StatusChip(
                        label: _label(a.severity),
                        tone: _tone(a.severity),
                      ),
                      Text(
                        a.titleAr ?? 'تنبيه طقس',
                        style: context.textStyles.titleSmall,
                      ),
                    ],
                  ),
                  if (a.detailAr != null)
                    Padding(
                      padding: const EdgeInsets.only(top: SahoolSpacing.xs),
                      child: Text(
                        a.detailAr!,
                        style: context.textStyles.bodyMedium,
                      ),
                    ),
                ],
              ),
            ),
        ],
      );
    },
  );
}

class _WindowsCard extends StatelessWidget {
  const _WindowsCard({required this.section});
  final Section<OperationWindows> section;

  static const _primary = ['spraying', 'irrigation'];

  @override
  Widget build(BuildContext context) => _SectionShell<OperationWindows>(
    title: 'نوافذ العمليّات (48 ساعة)',
    icon: Icons.schedule_outlined,
    section: section,
    builder: (context, w) {
      final t = context.tokens;
      final ordered = [
        for (final op in _primary)
          if (w.of(op) != null) w.of(op)!,
        for (final x in w.windows)
          if (!_primary.contains(x.operation)) x,
      ];
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (w.degraded || w.warningAr != null)
            Padding(
              padding: const EdgeInsets.only(bottom: SahoolSpacing.sm),
              child: Text(
                w.warningAr ?? 'بعض مصادر الطقس تعذّرت؛ النتيجة جزئيّة.',
                style: context.textStyles.bodySmall?.copyWith(color: t.warning),
              ),
            ),
          if (ordered.isEmpty)
            Text(
              'لم تُرجع خدمة الطقس نوافذ عمليّات لهذا الحقل.',
              style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
            ),
          for (final x in ordered) _WindowRow(window: x),
        ],
      );
    },
  );
}

class _WindowRow extends StatelessWidget {
  const _WindowRow({required this.window});
  final OperationWindow window;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final w = window;
    return Padding(
      padding: const EdgeInsets.only(bottom: SahoolSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Wrap(
            spacing: SahoolSpacing.sm,
            runSpacing: SahoolSpacing.xs,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(
                operationLabelAr(w.operation),
                style: context.textStyles.titleSmall,
              ),
              StatusChip(
                label: suitabilityLabelAr(w.suitability),
                tone: suitabilityTone(w.suitability),
              ),
              if (w.recommended)
                const StatusChip(
                  label: 'موصى بها',
                  tone: StatusTone.success,
                  icon: Icons.thumb_up_alt_outlined,
                ),
            ],
          ),
          const SizedBox(height: SahoolSpacing.xs),
          Text(
            'أفضل موعد: ${fmtWindowStart(w.startAt, w.startOffsetHours)}',
            style: context.textStyles.bodyMedium,
          ),
          if (w.adviceAr != null)
            Text(w.adviceAr!, style: context.textStyles.bodyMedium),
          if (w.limitingFactors.isNotEmpty)
            Text(
              'العوائق: ${w.limitingFactors.map(limitingFactorAr).join('، ')}',
              style: context.textStyles.bodySmall?.copyWith(color: t.muted),
            ),
        ],
      ),
    );
  }
}

class _ForecastCard extends StatelessWidget {
  const _ForecastCard({required this.section});
  final Section<WeatherForecast> section;

  @override
  Widget build(BuildContext context) => _SectionShell<WeatherForecast>(
    title: 'توقّعات 7 أيّام',
    icon: Icons.calendar_view_week_outlined,
    section: section,
    builder: (context, f) => Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (var i = 0; i < f.days.length; i++) ...[
          if (i > 0) Divider(color: context.tokens.line, height: 1),
          ForecastDayRow(day: f.days[i]),
        ],
      ],
    ),
  );
}

/// صفّ يوم توقّع — عموديّ ومرن، فلا يفيض عند تكبير الخطّ (textScale 1.3).
class ForecastDayRow extends StatelessWidget {
  const ForecastDayRow({super.key, required this.day, this.now});
  final ForecastDay day;
  final DateTime? now;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: SahoolSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Wrap(
            spacing: SahoolSpacing.sm,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(
                fmtDayName(day.date, now: now),
                style: context.textStyles.titleSmall,
              ),
              Text(
                fmtDate(day.date),
                style: context.textStyles.bodySmall?.copyWith(color: t.muted),
              ),
              Text(
                weatherCodeAr(day.weatherCode),
                style: context.textStyles.bodyMedium,
              ),
            ],
          ),
          const SizedBox(height: SahoolSpacing.xs),
          Wrap(
            spacing: SahoolSpacing.md,
            runSpacing: SahoolSpacing.xs,
            children: [
              Text(
                'العظمى ${fmtTempC(day.tempMaxC)}',
                style: context.textStyles.bodyMedium,
              ),
              Text(
                'الصغرى ${fmtTempC(day.tempMinC)}',
                style: context.textStyles.bodyMedium,
              ),
              Text(
                'مطر ${fmtMm(day.precipitationMm)}',
                style: context.textStyles.bodyMedium,
              ),
              Text(
                'رياح ${fmtKmh(day.windMaxKmh)}',
                style: context.textStyles.bodyMedium,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _IrrigationCard extends StatelessWidget {
  const _IrrigationCard({required this.section});
  final Section<IrrigationAdvice> section;

  @override
  Widget build(BuildContext context) => _SectionShell<IrrigationAdvice>(
    title: 'توصية الريّ',
    icon: Icons.water_outlined,
    section: section,
    builder: (context, a) => Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Wrap(
          spacing: SahoolSpacing.sm,
          runSpacing: SahoolSpacing.xs,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            StatusChip(
              label: 'الإلحاح: ${urgencyLabelAr(a.urgency)}',
              tone: urgencyTone(a.urgency),
            ),
            Text(
              'الكمّيّة: ${fmtMm(a.recommendedMm)}',
              style: context.textStyles.titleSmall,
            ),
          ],
        ),
        if (a.timingAr != null) ...[
          const SizedBox(height: SahoolSpacing.xs),
          Text(a.timingAr!, style: context.textStyles.bodyLarge),
        ],
        if (a.rationaleAr != null) ...[
          const SizedBox(height: SahoolSpacing.xs),
          Text(
            a.rationaleAr!,
            style: context.textStyles.bodySmall?.copyWith(
              color: context.tokens.muted,
            ),
          ),
        ],
      ],
    ),
  );
}

class _DiseaseCard extends StatelessWidget {
  const _DiseaseCard({required this.section});
  final Section<DiseaseRisk> section;

  @override
  Widget build(BuildContext context) => _SectionShell<DiseaseRisk>(
    title: 'خطر الأمراض الفطريّة',
    icon: Icons.coronavirus_outlined,
    section: section,
    builder: (context, d) => Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: StatusChip(
            label: 'الخطر: ${riskLabelAr(d.riskLevel)}',
            tone: riskTone(d.riskLevel),
          ),
        ),
        const SizedBox(height: SahoolSpacing.xs),
        Text(
          'الحرارة ${fmtTempC(d.temperatureC)} · الرطوبة ${fmtPct(d.humidityPct)} · مطر 3 أيّام ${fmtMm(d.rainMm3d)}',
          style: context.textStyles.bodySmall?.copyWith(
            color: context.tokens.muted,
          ),
        ),
        if (d.diseasesAr.isNotEmpty) ...[
          const SizedBox(height: SahoolSpacing.xs),
          Text(
            'محتملة (احتمال لا تشخيص): ${d.diseasesAr.join('، ')}',
            style: context.textStyles.bodyMedium,
          ),
        ],
        if (d.adviceAr != null) ...[
          const SizedBox(height: SahoolSpacing.xs),
          Text(d.adviceAr!, style: context.textStyles.bodyMedium),
        ],
      ],
    ),
  );
}

class _ThermalCard extends StatelessWidget {
  const _ThermalCard({required this.section});
  final Section<ThermalStress> section;

  @override
  Widget build(BuildContext context) => _SectionShell<ThermalStress>(
    title: 'الإجهاد الحراريّ',
    icon: Icons.device_thermostat_outlined,
    section: section,
    builder: (context, th) {
      final t = context.tokens;
      if (th.insufficientContext) {
        return Text(
          'غير متاح بعد — يلزم محصول ومرحلة نموّ معروفان لهذا الحقل.',
          style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
        );
      }
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: StatusChip(
              label: 'الخطر: ${riskLabelAr(th.risk)}',
              tone: riskTone(th.risk),
            ),
          ),
          const SizedBox(height: SahoolSpacing.xs),
          Wrap(
            spacing: SahoolSpacing.md,
            runSpacing: SahoolSpacing.xs,
            children: [
              Text(
                'أعلى نهار ${fmtTempC(th.dayMaxC)}',
                style: context.textStyles.bodyMedium,
              ),
              Text(
                'أدنى ليل ${fmtTempC(th.nightMinC)}',
                style: context.textStyles.bodyMedium,
              ),
              Text(
                'أيّام حرّ: ${fmtNumber(th.heatStressDays, decimals: 0)}',
                style: context.textStyles.bodyMedium,
              ),
              Text(
                'ليالي صقيع: ${fmtNumber(th.frostNights, decimals: 0)}',
                style: context.textStyles.bodyMedium,
              ),
            ],
          ),
          if (th.limitingFactors.isNotEmpty)
            Text(
              th.limitingFactors.map(limitingFactorAr).join('، '),
              style: context.textStyles.bodySmall?.copyWith(color: t.muted),
            ),
        ],
      );
    },
  );
}

class _CropStressCard extends StatelessWidget {
  const _CropStressCard({required this.section});
  final Section<CropStress> section;

  @override
  Widget build(BuildContext context) => _SectionShell<CropStress>(
    title: 'إجهاد المحصول',
    icon: Icons.grass_outlined,
    section: section,
    builder: (context, c) {
      final t = context.tokens;
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final p in c.products)
            Padding(
              padding: const EdgeInsets.only(bottom: SahoolSpacing.xs),
              child: Wrap(
                spacing: SahoolSpacing.sm,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  Text(
                    kCropStressProductsAr[p.key] ?? p.key,
                    style: context.textStyles.bodyMedium,
                  ),
                  if (p.status == 'insufficient_context')
                    const StatusChip(label: 'سياق غير كافٍ')
                  else
                    StatusChip(
                      label: riskLabelAr(p.risk),
                      tone: riskTone(p.risk),
                    ),
                ],
              ),
            ),
          for (final k in c.failed)
            Text(
              '${kCropStressProductsAr[k] ?? k}: تعذّر جلبه من خدمة الطقس',
              style: context.textStyles.bodySmall?.copyWith(color: t.muted),
            ),
          if (c.products.isEmpty && c.failed.isEmpty)
            Text(
              kNotMeasured,
              style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
            ),
        ],
      );
    },
  );
}
