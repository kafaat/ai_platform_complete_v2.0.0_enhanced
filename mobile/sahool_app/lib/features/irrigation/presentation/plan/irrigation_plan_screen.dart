// SAHOOL — features/irrigation/presentation/plan/irrigation_plan_screen.dart
// خطّة ريّ افتراضيّة (POST /api/v1/irrigation-plan): يدخل المستخدم ET₀ وKc والمطر
// اليوميّ وعدد الأيّام، فيُعيد الخادم جدولاً بنموذج FAO-56. لا قيم مسبقة الملء:
// الويب يملأ ET₀=6 وKc=1.0 افتراضاً، وهنا تُطلب صراحةً كي لا تُقدَّم أرقام لم
// يُدخلها أحد كأنّها بيانات الحقل. النتيجة موسومة «غير معايَرة» كما يقول الخادم.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_api.dart';

sealed class IrrigationPlanState {
  const IrrigationPlanState();
}

class PlanIdle extends IrrigationPlanState {
  const PlanIdle();
}

class PlanComputing extends IrrigationPlanState {
  const PlanComputing();
}

class PlanReady extends IrrigationPlanState {
  const PlanReady(this.result);
  final Map<String, dynamic> result;
}

class PlanFailed extends IrrigationPlanState {
  const PlanFailed(this.error);
  final ApiException error;
}

class IrrigationPlanCubit extends Cubit<IrrigationPlanState> {
  IrrigationPlanCubit(this._api) : super(const PlanIdle());
  final IrrigationApi _api;

  Future<void> compute(Map<String, dynamic> body, IdempotencyKey key) async {
    if (state is PlanComputing) return;
    emit(const PlanComputing());
    try {
      final res = await _api.computeIrrigationPlan(body, idempotencyKey: key);
      if (res['plan'] is! Map) {
        throw const FormatException('استجابة الخطّة بلا كائن plan.');
      }
      if (!isClosed) emit(PlanReady(res));
    } catch (e) {
      if (!isClosed) emit(PlanFailed(ApiException.from(e)));
    }
  }
}

/// تحقّق نموذج الخطّة؛ يُرجع (جسم الطلب، خطأ).
({Map<String, dynamic>? body, String? error}) buildPlanRequest({
  required String days,
  required String et0,
  required String kc,
  required String rain,
  String? texture,
  String rootDepth = '',
  String policy = 'water_saving',
}) {
  final d = parseLocalizedInt(days);
  final e = parseLocalizedNum(et0);
  final k = parseLocalizedNum(kc);
  final r = parseLocalizedNum(rain);
  final rootText = rootDepth.trim();
  final root = parseLocalizedNum(rootText);
  if (d == null || d < 1 || d > 14) {
    return (body: null, error: 'عدد الأيّام بين 1 و14');
  }
  if (e == null || e <= 0 || e > 20) {
    return (body: null, error: 'ET₀ اليوميّ بين 0 و20 مم');
  }
  if (k == null || k <= 0 || k > 2) return (body: null, error: 'Kc بين 0 و2');
  if (r == null || r < 0 || r > 300) {
    return (
      body: null,
      error: 'أدخل المطر اليوميّ المتوقَّع (0 إن لم يُتوقَّع مطر)',
    );
  }
  if (rootText.isNotEmpty && (root == null || root <= 0 || root > 5)) {
    return (body: null, error: 'عمق الجذور بين 0 و5 م أو اتركه فارغاً');
  }
  return (
    body: {
      'forecast': [
        for (var i = 0; i < d; i++) {'et0_mm': e, 'kc': k, 'rain_mm': r},
      ],
      'soil_texture': ?texture,
      'root_depth_m': ?root,
      'policy': policy,
    },
    error: null,
  );
}

const Map<String, String> kTexturesAr = {
  'sand': 'رمليّة',
  'sandy_loam': 'طميّة رمليّة',
  'loam': 'طميّة',
  'silt_loam': 'طميّة غرينيّة',
  'clay_loam': 'طميّة طينيّة',
  'clay': 'طينيّة',
};

const Map<String, String> kPoliciesAr = {
  'water_saving': 'توفير الماء',
  'yield_max': 'أقصى إنتاج',
};

class IrrigationPlanScreen extends StatelessWidget {
  const IrrigationPlanScreen({super.key, this.api});
  final IrrigationApi? api;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) => IrrigationPlanCubit(api ?? IrrigationApi.instance),
    child: const _PlanView(),
  );
}

class _PlanView extends StatefulWidget {
  const _PlanView();
  @override
  State<_PlanView> createState() => _PlanViewState();
}

class _PlanViewState extends State<_PlanView> {
  final _days = TextEditingController(text: '7');
  final _et0 = TextEditingController();
  final _kc = TextEditingController();
  final _rain = TextEditingController();
  final _root = TextEditingController();
  String? _texture;
  String _policy = 'water_saving';
  String? _error;
  IdempotencyKey _key = IdempotencyKey.generate();
  Map<String, dynamic>? _lastBody;

  @override
  void dispose() {
    for (final c in [_days, _et0, _kc, _rain, _root]) {
      c.dispose();
    }
    super.dispose();
  }

  void _submit() {
    final req = buildPlanRequest(
      days: _days.text,
      et0: _et0.text,
      kc: _kc.text,
      rain: _rain.text,
      texture: _texture,
      rootDepth: _root.text,
      policy: _policy,
    );
    if (req.error != null) {
      setState(() => _error = req.error);
      return;
    }
    // مدخلات جديدة ⇒ نيّة جديدة؛ نفس المدخلات ⇒ نفس المفتاح.
    if (_lastBody != null && _lastBody.toString() != req.body.toString()) {
      _key = IdempotencyKey.generate();
    }
    _lastBody = req.body;
    setState(() => _error = null);
    context.read<IrrigationPlanCubit>().compute(req.body!, _key);
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'خطّة ريّ افتراضيّة',
      body: BlocBuilder<IrrigationPlanCubit, IrrigationPlanState>(
        builder: (context, s) => ListView(
          padding: const EdgeInsetsDirectional.fromSTEB(
            SahoolSpacing.page,
            SahoolSpacing.sm,
            SahoolSpacing.page,
            SahoolSpacing.xl,
          ),
          children: [
            Text(
              'حساب بمدخلاتك أنت (نموذج FAO-56)، لا بيانات الحقل المقيسة — للتخطيط لا للتشغيل.',
              style: context.textStyles.bodyMedium,
            ),
            AppNumberField(
              label: 'عدد الأيّام',
              controller: _days,
              decimal: false,
              unit: 'يوم',
            ),
            AppNumberField(
              label: 'ET₀ اليوميّ',
              controller: _et0,
              unit: 'مم/يوم',
            ),
            AppNumberField(label: 'معامل المحصول Kc', controller: _kc),
            AppNumberField(
              label: 'المطر اليوميّ المتوقَّع',
              controller: _rain,
              unit: 'مم/يوم',
            ),
            AppDropdown<String>(
              label: 'نسيج التربة (اختياريّ)',
              items: kTexturesAr,
              value: _texture,
              onChanged: (v) => setState(() => _texture = v),
            ),
            AppNumberField(
              label: 'عمق الجذور (اختياريّ)',
              controller: _root,
              unit: 'م',
            ),
            AppDropdown<String>(
              label: 'السياسة',
              items: kPoliciesAr,
              value: _policy,
              onChanged: (v) => setState(() => _policy = v ?? 'water_saving'),
            ),
            if (_error != null) ...[
              const SizedBox(height: SahoolSpacing.md),
              Text(
                _error!,
                style: context.textStyles.bodyMedium?.copyWith(
                  color: context.tokens.danger,
                ),
              ),
            ],
            const SizedBox(height: SahoolSpacing.lg),
            PrimaryButton(
              label: 'احسب الخطّة',
              icon: Icons.calculate_rounded,
              loading: s is PlanComputing,
              onPressed: _submit,
            ),
            const SizedBox(height: SahoolSpacing.lg),
            switch (s) {
              PlanIdle() || PlanComputing() => const SizedBox.shrink(),
              PlanFailed(:final error) => SizedBox(
                height: 280,
                child: ErrorState(error: error),
              ),
              PlanReady(:final result) => _PlanResult(result),
            },
          ],
        ),
      ),
    );
  }
}

class _PlanResult extends StatelessWidget {
  const _PlanResult(this.result);
  final Map<String, dynamic> result;

  @override
  Widget build(BuildContext context) {
    final plan = Map<String, dynamic>.from(result['plan'] as Map);
    final quality = result['quality'] is Map
        ? Map<String, dynamic>.from(result['quality'] as Map)
        : const {};
    final soil = result['soil'] is Map
        ? Map<String, dynamic>.from(result['soil'] as Map)
        : const {};
    num? n(Object? v) => v is num ? v : null;
    final days = plan['days'] is List
        ? (plan['days'] as List).whereType<Map>().toList()
        : const <Map>[];
    final stress = plan['stress_days'] is List
        ? (plan['stress_days'] as List).length
        : null;
    final notes = <String>[
      ...?(plan['notes_ar'] as List?)?.map((e) => e.toString()),
      ...?(quality['assumptions_ar'] as List?)?.map((e) => e.toString()),
      ...?(soil['warnings_ar'] as List?)?.map((e) => e.toString()),
    ];
    return SectionCard(
      title: 'النتيجة',
      icon: Icons.insights_rounded,
      trailing: plan['calibrated'] == true
          ? null
          : const StatusChip(label: 'غير معايَرة', tone: StatusTone.warning),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Wrap(
            spacing: SahoolSpacing.sm,
            runSpacing: SahoolSpacing.sm,
            children: [
              _kv(
                context,
                'إجماليّ الريّ',
                fmtMm(n(plan['total_irrigation_mm'])),
              ),
              _kv(
                context,
                'بالحجم',
                fmtM3PerHa(n(plan['total_irrigation_m3_ha'])),
              ),
              _kv(
                context,
                'عدد الريّات',
                fmtNumber(n(plan['n_events']), decimals: 0),
              ),
              _kv(context, 'أيّام إجهاد', fmtNumber(stress, decimals: 0)),
              _kv(
                context,
                'الاستنزاف النهائيّ',
                fmtMm(n(plan['final_depletion_mm'])),
              ),
              _kv(context, 'TAW المستعمَل', fmtMm(n(result['taw_mm_used']))),
            ],
          ),
          if (days.isNotEmpty) ...[
            const SizedBox(height: SahoolSpacing.md),
            Text('الأيّام', style: context.textStyles.titleSmall),
            for (final d in days)
              Padding(
                padding: const EdgeInsetsDirectional.only(
                  top: SahoolSpacing.xs,
                ),
                child: Text(
                  'اليوم ${(n(d['day_index']) ?? 0).toInt() + 1}: ريّ ${fmtMm(n(d['irrigation_mm']))}'
                  ' · ETc ${fmtMm(n(d['etc_mm']))}'
                  '${d['stressed'] == true ? ' · إجهاد' : ''}',
                  style: context.textStyles.bodySmall,
                ),
              ),
          ],
          if (notes.isNotEmpty) ...[
            const SizedBox(height: SahoolSpacing.md),
            for (final note in notes)
              Padding(
                padding: const EdgeInsetsDirectional.only(
                  top: SahoolSpacing.xs,
                ),
                child: Text('• $note', style: context.textStyles.bodySmall),
              ),
          ],
        ],
      ),
    );
  }

  Widget _kv(BuildContext context, String k, String v) => SizedBox(
    width: 150,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(k, style: context.textStyles.labelMedium),
        Text(v, style: context.textStyles.titleMedium),
      ],
    ),
  );
}
