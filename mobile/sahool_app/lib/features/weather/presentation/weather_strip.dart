// SAHOOL — features/weather/presentation/weather_strip.dart
// شريط طقس مضغوط — ودجة عامّة تضمّنها ميزات أخرى (اللوحة، بطاقة الحقل):
//
//   import 'package:sahool_app/features/weather/presentation/weather_strip.dart';
//   WeatherStrip(fieldId: id)
//
// يعرض الآن: الحالة + الحرارة + الرطوبة + الرياح + المطر، وعظمى/صغرى اليوم.
// الضغط يفتح شاشة طقس الحقل. حالات صادقة: تحميل / لا إحداثيّات / خطأ.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';

import '../data/weather_api.dart';
import '../data/weather_models.dart';
import '../weather_paths.dart';
import 'weather_cubit.dart';
import 'weather_format.dart';

@immutable
class WeatherStripState {
  const WeatherStripState({this.current, this.today, this.error, this.noData});
  final CurrentWeather? current;
  final ForecastDay? today;
  final ApiException? error;

  /// سبب «لا بيانات طقس» إن وُجد.
  final String? noData;
  bool get loading => current == null && error == null && noData == null;
}

class WeatherStripCubit extends Cubit<WeatherStripState> {
  WeatherStripCubit(this._api, this.fieldId) : super(const WeatherStripState());
  final WeatherApi _api;
  final String fieldId;

  Future<void> load() async {
    emit(const WeatherStripState());
    try {
      final loc = await _api.getFieldLocation(fieldId);
      if (!loc.hasCoordinates) {
        if (!isClosed) {
          emit(const WeatherStripState(noData: kNoCoordinatesReason));
        }
        return;
      }
      final results = await Future.wait<Object?>([
        _api.current(loc.lat!, loc.lon!),
        // اليوم فقط؛ فشلُه لا يُسقط القراءة الحاليّة.
        _api
            .forecast(loc.lat!, loc.lon!, days: 1)
            .then<WeatherForecast?>((f) => f)
            .catchError((Object _) => null),
      ]);
      final cur = results[0]! as CurrentWeather;
      final fc = results[1] as WeatherForecast?;
      if (isClosed) return;
      if (!cur.hasAnyReading) {
        emit(
          const WeatherStripState(
            noData: 'خدمة الطقس لم تُرجع قراءات لموقع الحقل.',
          ),
        );
        return;
      }
      emit(
        WeatherStripState(
          current: cur,
          today: (fc?.days.isNotEmpty ?? false) ? fc!.days.first : null,
        ),
      );
    } catch (e) {
      if (!isClosed) emit(WeatherStripState(error: ApiException.from(e)));
    }
  }
}

class WeatherStrip extends StatelessWidget {
  const WeatherStrip({super.key, required this.fieldId, this.api, this.onTap});
  final String fieldId;
  final WeatherApi? api;

  /// الافتراضيّ: يفتح شاشة طقس الحقل.
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) =>
        WeatherStripCubit(api ?? WeatherApi.instance, fieldId)..load(),
    child: _StripView(
      onTap:
          onTap ?? () => context.openRoute<void>(WeatherPaths.field(fieldId)),
    ),
  );
}

class _StripView extends StatelessWidget {
  const _StripView({required this.onTap});
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            minHeight: SahoolSizes.minTouchTarget,
          ),
          child: Padding(
            padding: const EdgeInsets.all(SahoolSpacing.md),
            child: BlocBuilder<WeatherStripCubit, WeatherStripState>(
              builder: (context, s) {
                if (s.loading) {
                  return Row(
                    children: [
                      const SizedBox.square(
                        dimension: SahoolSizes.iconSm,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                      const SizedBox(width: SahoolSpacing.sm),
                      Text(
                        'جارٍ تحميل الطقس…',
                        style: context.textStyles.bodyMedium,
                      ),
                    ],
                  );
                }
                if (s.noData != null || s.error != null) {
                  final retry =
                      s.error != null &&
                      s.error!.kind != ApiErrorKind.forbidden &&
                      s.error!.kind != ApiErrorKind.notFound;
                  return Row(
                    children: [
                      Icon(Icons.cloud_off_outlined, color: t.muted),
                      const SizedBox(width: SahoolSpacing.sm),
                      Expanded(
                        child: Text(
                          s.noData != null
                              ? kNoFieldWeather
                              : 'تعذّر جلب الطقس: ${weatherErrorText(s.error!)}',
                          style: context.textStyles.bodyMedium?.copyWith(
                            color: t.muted,
                          ),
                        ),
                      ),
                      if (retry)
                        IconButton(
                          tooltip: 'إعادة المحاولة',
                          icon: const Icon(Icons.refresh_rounded),
                          onPressed: context.read<WeatherStripCubit>().load,
                        ),
                    ],
                  );
                }
                final c = s.current!;
                final today = s.today;
                return Semantics(
                  button: true,
                  label: 'طقس الحقل الآن',
                  child: Wrap(
                    spacing: SahoolSpacing.md,
                    runSpacing: SahoolSpacing.xs,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      _Item(Icons.cloud_outlined, weatherCodeAr(c.weatherCode)),
                      _Item(
                        Icons.thermostat_outlined,
                        fmtTempC(c.temperatureC),
                      ),
                      if (today != null)
                        _Item(
                          Icons.swap_vert_rounded,
                          '${fmtTempC(today.tempMaxC)} / ${fmtTempC(today.tempMinC)}',
                        ),
                      _Item(Icons.water_drop_outlined, fmtPct(c.humidityPct)),
                      _Item(Icons.air_rounded, fmtKmh(c.windKmh)),
                      _Item(Icons.umbrella_outlined, fmtMm(c.precipitationMm)),
                    ],
                  ),
                );
              },
            ),
          ),
        ),
      ),
    );
  }
}

class _Item extends StatelessWidget {
  const _Item(this.icon, this.text);
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Icon(icon, size: SahoolSizes.iconSm, color: context.tokens.muted),
      const SizedBox(width: SahoolSpacing.xs),
      Text(text, style: context.textStyles.bodyMedium),
    ],
  );
}
