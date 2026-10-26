// SAHOOL — features/fields/presentation/field_create_wizard.dart
// معالج إنشاء حقل في أربع خطوات: المعلومات الأساسيّة ← حدّ الحقل ← المحصول
// والموسم ← المراجعة والحفظ. ثمّ مساحة عمل الحقل الجديد.
//
// ما تغيّر عن المعالج السابق (خمس خطوات + ثلاث بعد الحفظ):
//   • الرسم في lib/features/maps/draw/: أوضاع مضلّع/مستطيل/محور بلا خلط
//     هندسات، تراجع وإعادة، سحب/إدراج/حذف رؤوس بمقابض ≥48dp، التقاط بحدود
//     الحقول المجاورة، والمساحة بصيغة الخادم نفسها (كانت تزيد 0.224٪).
//   • تحقّق حاجب قبل الحفظ: التقاطع الذاتيّ (كان يُرسَل فيُصلحه الخادم بصمت
//     بمساحة مختلفة)، عدد الرؤوس، حدود المساحة، خارج اليمن/إحداثيّات مقلوبة،
//     وتحذير التداخل مع حقولك.
//   • الحفظ بمفتاح منع تكرار ثابت (إعادة المحاولة بعد انقطاع كانت تنتهي بـ409
//     «اسم مكرّر»)، مع farm_id، ومعاملات المحور، ونوع الريّ في طلب الإنشاء نفسه.
//   • زرّ الرجوع في النظام يعود خطوةً ولا يُضيّع المُدخَل؛ والخروج بمدخلات غير
//     محفوظة يطلب تأكيداً.
//   • بعد الإنشاء تُبطَل ذاكرة الاستجابات ويُبلَّغ المستمعون (قائمة الحقول).
//   • خطوة تقدير الإنتاجيّة تظهر فقط إن ردّ الخادم تقديراً رقميّاً.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/state_views.dart' show apiErrorMessage;
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/farms/data/farms_api.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/maps/draw/boundary_step.dart';
import 'package:sahool_app/features/maps/draw/boundary_validation.dart';
import 'package:sahool_app/features/maps/draw/draw_controller.dart';
import 'package:sahool_app/features/maps/draw/field_create_api.dart';
import 'package:sahool_app/features/maps/draw/field_create_errors.dart'
    show FixStep;
import 'package:sahool_app/features/maps/draw/field_save_cubit.dart';

/// اسم مسار مساحة العمل البديل (يربطه fields_routes).
const String _workspaceRouteName = 'field_workspace';

class FieldCreateWizard extends StatefulWidget {
  const FieldCreateWizard({
    super.key,
    this.initialFarmId,
    this.farmsApi,
    this.fieldsApi,
    this.createApi,
    this.showBasemap = true,
    this.readPosition,
    this.canCreate,
  });

  /// مزرعة مختارة مسبقاً (وإلّا تُقرأ `farm_id` من وسائط المسار إن وُجدت).
  final String? initialFarmId;
  final FarmsApi? farmsApi;
  final FieldsApi? fieldsApi;
  final FieldCreateApi? createApi;

  /// false في الاختبارات (لا بلاطات شبكيّة).
  final bool showBasemap;
  final PositionReader? readPosition;

  /// يتجاوز فحص الدور من الجلسة (للاختبارات).
  final bool? canCreate;

  @override
  State<FieldCreateWizard> createState() => _FieldCreateWizardState();
}

class _FieldCreateWizardState extends State<FieldCreateWizard> {
  static const _titles = [
    'المعلومات الأساسيّة',
    'حدّ الحقل',
    'المحصول والموسم',
    'المراجعة والحفظ',
  ];

  // وسط المرتفعات الزراعيّة اليمنيّة بتكبير الدولة: نقطة بدء محايدة يقرّب منها
  // المزارع أو يضيف موقعه؛ لا ندّعي أنّها موقع حقله.
  static const _yemenCenter = LatLng(15.3, 44.2);

  static const _crops = {
    'wheat': 'قمح',
    'barley': 'شعير',
    'sorghum': 'ذرة رفيعة',
    'maize': 'ذرة شاميّة',
    'coffee': 'بنّ',
    'qat': 'قات',
    'vegetables': 'خضروات',
    'fruits': 'فواكه',
    'alfalfa': 'برسيم',
    'other': 'أخرى',
  };
  static const _waterSources = {
    'well': 'بئر',
    'spring': 'نبع',
    'rain': 'أمطار',
    'canal': 'قناة',
    'tanker': 'صهريج',
    'network': 'شبكة',
  };
  static const _irrigationTypes = {
    'drip': 'تنقيط',
    'pivot': 'محوريّ',
    'flood': 'غمر',
    'sprinkler': 'رشّ',
    'rainfed': 'بعليّ (مطريّ)',
    'subsurface': 'تحت سطحيّ',
  };
  static const _soilTypes = {
    'sandy': 'رمليّة',
    'clay': 'طينيّة',
    'loam': 'طميّيّة',
    'silt': 'غرينيّة',
    'rocky': 'صخريّة',
  };
  static const _noFarm = '';

  late final FarmsApi _farmsApi = widget.farmsApi ?? FarmsApi.instance;
  late final FieldsApi _fieldsApi = widget.fieldsApi ?? FieldsApi.instance;
  late final FieldSaveCubit _save = FieldSaveCubit(
    createApi: widget.createApi,
    fieldsApi: _fieldsApi,
  );

  final _draw = DrawController();
  final _name = TextEditingController();
  int _step = 0;

  String _farmId = _noFarm;
  bool _farmArgRead = false;
  List<Map<String, dynamic>>? _farms;
  Object? _farmsError;
  bool _farmsLoading = true;

  bool _existingLoaded = false;
  Object? _existingError;
  LatLng? _existingCenter;

  String? _crop;
  String? _waterSource;
  String? _irrigationType;
  String? _soilType;
  DateTime? _sowingDate;

  @override
  void initState() {
    super.initState();
    _farmId = widget.initialFarmId ?? _noFarm;
    // أزرار التنقّل تتبع صلاحيّة الحدّ أثناء الرسم.
    _draw.addListener(_onDrawChanged);
    _loadFarms();
    _loadExisting();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_farmArgRead) return;
    _farmArgRead = true;
    final args = ModalRoute.of(context)?.settings.arguments;
    if (widget.initialFarmId == null &&
        args is Map &&
        args['farm_id'] != null) {
      _farmId = args['farm_id'].toString();
    }
  }

  void _onDrawChanged() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _name.dispose();
    _draw.removeListener(_onDrawChanged);
    _draw.dispose();
    _save.close();
    super.dispose();
  }

  Future<void> _loadFarms() async {
    setState(() {
      _farmsLoading = true;
      _farmsError = null;
    });
    try {
      final farms = await _farmsApi.listFarms();
      if (!mounted) return;
      setState(() {
        _farms = farms;
        _farmsLoading = false;
        if (_farmId == _noFarm && farms.length == 1) {
          _farmId = (farms.first['farm_id'] ?? '').toString();
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _farmsError = e;
        _farmsLoading = false;
      });
    }
  }

  Future<void> _loadExisting() async {
    try {
      final list = await _fieldsApi.listFields();
      if (!mounted) return;
      final fields = list
          .map(ExistingField.fromSummary)
          .whereType<ExistingField>()
          .toList();
      _draw.existingFields = fields;
      setState(() {
        _existingLoaded = true;
        _existingError = null;
        if (fields.isNotEmpty) _existingCenter = fields.last.rings.first.first;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _existingLoaded = true;
        _existingError = e;
      });
    }
  }

  // ── المدخلات والتنقّل ──

  String get _trimmedName => _name.text.trim();
  String? get _nameError {
    if (_trimmedName.isEmpty) return null;
    if (_trimmedName.length > 100) return 'الاسم أطول من 100 حرف.';
    return null;
  }

  bool get _nameOk => _trimmedName.isNotEmpty && _nameError == null;

  bool get _dirty =>
      _trimmedName.isNotEmpty ||
      _draw.canUndo ||
      _crop != null ||
      _waterSource != null ||
      _irrigationType != null ||
      _soilType != null;

  bool get _boundaryOk => _draw.ring.length >= 3 && _draw.validation.canSave;

  bool get _canAdvance => switch (_step) {
    0 => _nameOk,
    1 => _boundaryOk,
    _ => true,
  };

  void _next() {
    if (_step < _titles.length - 1 && _canAdvance) setState(() => _step++);
  }

  void _back() {
    if (_step > 0) setState(() => _step--);
  }

  /// رجوع النظام: خطوة إلى الوراء؛ وفي الخطوة الأولى تأكيد قبل إسقاط المُدخَل.
  Future<void> _onSystemBack() async {
    if (_save.busy) return;
    if (_step > 0) {
      _back();
      return;
    }
    final nav = Navigator.of(context);
    if (_dirty) {
      final leave = await showConfirmDialog(
        context,
        title: 'الخروج من إضافة الحقل؟',
        message: 'لم يُحفَظ الحقل بعد، وستضيع البيانات التي أدخلتها.',
        confirmLabel: 'خروج دون حفظ',
        cancelLabel: 'متابعة الإدخال',
        destructive: true,
      );
      if (!leave || !mounted) return;
    }
    nav.pop(false);
  }

  FieldCreateDraft _draft() => FieldCreateDraft(
    name: _trimmedName,
    geometry: _draw.geometry!,
    farmId: _farmId == _noFarm ? null : _farmId,
    pivot: _draw.pivotPayload,
    crop: _crop,
    waterSource: _waterSource,
    irrigationType: _draw.isPivot ? 'pivot' : _irrigationType,
    soilType: _soilType,
    boundarySource: _draw.boundarySource,
  );

  String _ymd(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';

  Future<void> _submit() async {
    if (!_nameOk) return setState(() => _step = 0);
    if (!_boundaryOk) return setState(() => _step = 1);
    await _save.save(
      _draft(),
      seasonCrop: _crop,
      sowingDate: _sowingDate == null ? null : _ymd(_sowingDate!),
    );
  }

  void _onSaveState(BuildContext context, FieldSaveState s) {
    if (s is FieldSaveDone &&
        s.yieldEstimate == null &&
        s.seasonWarning == null) {
      _goToWorkspace(s.fieldId);
    }
  }

  void _goToWorkspace(String fieldId) {
    final nav = Navigator.of(context);
    // true ⇒ قائمة الحقول التي فتحت المعالج تعيد التحميل.
    nav.pop(true);
    if (fieldId.isEmpty) return;
    try {
      nav.pushNamed(_workspaceRouteName, arguments: fieldId);
    } catch (_) {
      // مسار غير مسجَّل في بيئة ما: الإغلاق بنجاح يكفي.
    }
  }

  // ── الواجهة ──

  @override
  Widget build(BuildContext context) {
    final allowed = widget.canCreate ?? canMutate(currentRole());
    if (!allowed) {
      return const AppScaffold(
        title: 'حقل جديد',
        body: EmptyState(
          icon: Icons.lock_outline,
          message: 'دورك للقراءة فقط؛ لا يمكنه إنشاء حقول.',
        ),
      );
    }
    return BlocProvider.value(
      value: _save,
      child: BlocConsumer<FieldSaveCubit, FieldSaveState>(
        listener: _onSaveState,
        builder: (context, s) {
          if (s is FieldSaveDone &&
              (s.yieldEstimate != null || s.seasonWarning != null)) {
            return _doneView(context, s);
          }
          return PopScope(
            canPop: false,
            onPopInvokedWithResult: (didPop, _) {
              if (!didPop) _onSystemBack();
            },
            child: Scaffold(
              appBar: AppBar(title: const Text('حقل جديد')),
              body: SafeArea(
                top: false,
                child: Column(
                  children: [
                    _progress(context),
                    Expanded(child: _body(context, s)),
                    _navBar(context, s),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _progress(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final t = context.tokens;
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(
        SahoolSpacing.lg,
        SahoolSpacing.sm,
        SahoolSpacing.lg,
        SahoolSpacing.xs,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              for (var i = 0; i < _titles.length; i++)
                Expanded(
                  child: Container(
                    height: 6,
                    margin: const EdgeInsetsDirectional.only(end: 4),
                    decoration: BoxDecoration(
                      color: i <= _step ? scheme.primary : t.line,
                      borderRadius: SahoolRadius.smAll,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: SahoolSpacing.sm),
          Text(
            'الخطوة ${_step + 1} من ${_titles.length} · ${_titles[_step]}',
            key: const ValueKey('wizard-step-title'),
            style: context.textStyles.titleMedium,
          ),
        ],
      ),
    );
  }

  Widget _body(BuildContext context, FieldSaveState s) => switch (_step) {
    0 => _basicsStep(context),
    1 => BoundaryStep(
      controller: _draw,
      initialCenter: _existingCenter ?? _yemenCenter,
      initialZoom: _existingCenter != null ? 15 : 7,
      showBasemap: widget.showBasemap,
      readPosition: widget.readPosition,
      note: _existingLoaded && _existingError != null
          ? 'تعذّر تحميل حقولك القائمة: فحص التداخل والالتقاط غير متاحين الآن.'
          : null,
    ),
    2 => _cropStep(context),
    _ => _reviewStep(context, s),
  };

  Widget _basicsStep(BuildContext context) {
    final farms = _farms;
    return ListView(
      padding: const EdgeInsets.all(SahoolSpacing.lg),
      children: [
        AppTextField(
          key: const ValueKey('field-name'),
          label: 'اسم الحقل',
          controller: _name,
          hint: 'مثال: الحقل الشرقيّ',
          errorText: _nameError,
          textInputAction: TextInputAction.done,
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: SahoolSpacing.md),
        if (_farmsLoading)
          const Padding(
            padding: EdgeInsets.all(SahoolSpacing.lg),
            child: Center(child: CircularProgressIndicator()),
          )
        else if (_farmsError != null)
          SectionCard(
            title: 'المزرعة',
            icon: Icons.agriculture_outlined,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(apiErrorMessage(_farmsError!)),
                const SizedBox(height: SahoolSpacing.sm),
                Text(
                  'يمكنك المتابعة دون ربط الحقل بمزرعة، وربطه لاحقاً.',
                  style: context.textStyles.bodyMedium?.copyWith(
                    color: context.tokens.muted,
                  ),
                ),
                const SizedBox(height: SahoolSpacing.sm),
                SecondaryButton(
                  label: 'إعادة المحاولة',
                  icon: Icons.refresh,
                  onPressed: _loadFarms,
                ),
              ],
            ),
          )
        else
          AppDropdown<String>(
            key: const ValueKey('farm-picker'),
            label: 'المزرعة',
            value: _farmId,
            items: {
              _noFarm: 'بدون مزرعة',
              for (final f in farms ?? const <Map<String, dynamic>>[])
                (f['farm_id'] ?? '').toString(): (f['name'] ?? f['farm_id'])
                    .toString(),
            },
            onChanged: (v) => setState(() => _farmId = v ?? _noFarm),
          ),
        const SizedBox(height: SahoolSpacing.sm),
        Text(
          'الاسم يجب ألّا يتكرّر داخل المزرعة نفسها.',
          style: context.textStyles.bodyMedium?.copyWith(
            color: context.tokens.muted,
          ),
        ),
      ],
    );
  }

  Widget _cropStep(BuildContext context) {
    final t = context.tokens;
    return ListView(
      padding: const EdgeInsets.all(SahoolSpacing.lg),
      children: [
        AppDropdown<String>(
          key: const ValueKey('crop-picker'),
          label: 'المحصول (اختياريّ)',
          value: _crop,
          items: _crops,
          onChanged: (v) => setState(() => _crop = v),
        ),
        if (_draw.isPivot)
          Padding(
            padding: const EdgeInsets.only(top: SahoolSpacing.md),
            child: InputDecorator(
              decoration: const InputDecoration(labelText: 'نوع الريّ'),
              child: Text(
                'محوريّ — من شكل الحدّ (دائرة المحور)',
                style: context.textStyles.bodyLarge,
              ),
            ),
          )
        else
          AppDropdown<String>(
            label: 'نوع الريّ (اختياريّ)',
            value: _irrigationType == 'pivot' ? null : _irrigationType,
            items: {
              for (final e in _irrigationTypes.entries)
                if (e.key != 'pivot') e.key: e.value,
            },
            onChanged: (v) => setState(() => _irrigationType = v),
          ),
        AppDropdown<String>(
          label: 'مصدر المياه (اختياريّ)',
          value: _waterSource,
          items: _waterSources,
          onChanged: (v) => setState(() => _waterSource = v),
        ),
        AppDropdown<String>(
          label: 'نوع التربة (اختياريّ)',
          value: _soilType,
          items: _soilTypes,
          onChanged: (v) => setState(() => _soilType = v),
        ),
        if (_crop != null) ...[
          const SizedBox(height: SahoolSpacing.md),
          AppListTile(
            icon: Icons.event_outlined,
            title: 'تاريخ البذر (اختياريّ)',
            subtitle: _sowingDate == null ? 'لم يُحدَّد' : fmtDate(_sowingDate),
            onTap: () async {
              final d = await showDatePicker(
                context: context,
                initialDate: _sowingDate ?? DateTime.now(),
                firstDate: DateTime(2015),
                lastDate: DateTime(2100),
              );
              if (d != null && mounted) setState(() => _sowingDate = d);
            },
          ),
          Text(
            'عند الحفظ يُنشأ موسم لهذا المحصول على الحقل.',
            style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
          ),
        ],
      ],
    );
  }

  Widget _row(BuildContext context, String k, String v) => Padding(
    padding: const EdgeInsets.symmetric(vertical: SahoolSpacing.xs),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 110,
          child: Text(
            k,
            style: context.textStyles.bodyMedium?.copyWith(
              color: context.tokens.muted,
            ),
          ),
        ),
        Expanded(child: Text(v, style: context.textStyles.bodyLarge)),
      ],
    ),
  );

  String _farmName() {
    if (_farmId == _noFarm) return 'بدون مزرعة';
    final f = _farms?.firstWhere(
      (f) => (f['farm_id'] ?? '').toString() == _farmId,
      orElse: () => const {},
    );
    return (f?['name'] ?? _farmId).toString();
  }

  Widget _reviewStep(BuildContext context, FieldSaveState s) {
    final t = context.tokens;
    final v = _draw.validation;
    final boundaryLabel = switch (_draw.mode) {
      DrawMode.circle =>
        'محور · نصف القطر ${fmtNumber(_draw.radiusM, decimals: 0)} م',
      DrawMode.rectangle => 'مستطيل',
      _ => switch (_draw.polygonSource) {
        'gps' => 'مضلّع من GPS',
        'import_geojson' => 'مستورَد من GeoJSON',
        'import_kml' => 'مستورَد من KML',
        _ => 'مضلّع مرسوم',
      },
    };
    final irrigation = _draw.isPivot ? 'pivot' : _irrigationType;
    return ListView(
      padding: const EdgeInsets.all(SahoolSpacing.lg),
      children: [
        SectionCard(
          title: 'ملخّص الحقل',
          icon: Icons.fact_check_outlined,
          child: Column(
            children: [
              _row(context, 'الاسم', _trimmedName),
              _row(context, 'المزرعة', _farmName()),
              _row(context, 'الحدّ', boundaryLabel),
              if (_crop != null) _row(context, 'المحصول', _crops[_crop]!),
              if (irrigation != null)
                _row(context, 'الريّ', _irrigationTypes[irrigation]!),
              if (_waterSource != null)
                _row(context, 'المياه', _waterSources[_waterSource]!),
              if (_soilType != null)
                _row(context, 'التربة', _soilTypes[_soilType]!),
              if (_crop != null && _sowingDate != null)
                _row(context, 'البذر', fmtDate(_sowingDate)),
            ],
          ),
        ),
        const SizedBox(height: SahoolSpacing.md),
        SectionCard(
          title: 'الحدّ والمساحة',
          icon: Icons.square_foot,
          child: BoundarySummary(validation: v, perimeterM: _draw.perimeter),
        ),
        if (s is FieldSaveFailed) ...[
          const SizedBox(height: SahoolSpacing.md),
          SectionCard(
            title: 'لم يُحفَظ الحقل',
            icon: Icons.error_outline,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  s.view.messageAr,
                  key: const ValueKey('save-error'),
                  style: context.textStyles.bodyLarge?.copyWith(
                    color: t.danger,
                  ),
                ),
                if (s.view.fixStep != FixStep.none) ...[
                  const SizedBox(height: SahoolSpacing.sm),
                  SecondaryButton(
                    label: s.view.fixStep == FixStep.basics
                        ? 'تعديل الاسم أو المزرعة'
                        : 'تعديل الحدّ',
                    icon: Icons.edit_outlined,
                    onPressed: () {
                      _save.acknowledgeError();
                      setState(
                        () => _step = s.view.fixStep == FixStep.basics ? 0 : 1,
                      );
                    },
                  ),
                ],
              ],
            ),
          ),
        ],
      ],
    );
  }

  Widget _navBar(BuildContext context, FieldSaveState s) {
    final busy = s is FieldSaveInProgress;
    final isLast = _step == _titles.length - 1;
    final stageLabel = s is FieldSaveInProgress
        ? switch (s.stage) {
            SaveStage.creating => 'جارٍ حفظ الحقل…',
            SaveStage.season => 'جارٍ إنشاء الموسم…',
            SaveStage.estimate => 'جارٍ طلب تقدير الإنتاجيّة…',
          }
        : null;
    String? blocker;
    if (_step == 0 && !_nameOk) blocker = 'أدخل اسماً للحقل.';
    // في خطوة الحدّ يشرح ملخّص الحدّ سبب الحجب؛ لا نكرّره هنا (مساحة الخريطة).
    return Material(
      color: Theme.of(context).colorScheme.surface,
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(SahoolSpacing.md),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (blocker != null || stageLabel != null)
              Padding(
                padding: const EdgeInsets.only(bottom: SahoolSpacing.sm),
                child: Text(
                  stageLabel ?? blocker!,
                  textAlign: TextAlign.center,
                  style: context.textStyles.bodyMedium?.copyWith(
                    color: context.tokens.muted,
                  ),
                ),
              ),
            Row(
              children: [
                if (_step > 0) ...[
                  Expanded(
                    child: SecondaryButton(
                      label: 'السابق',
                      onPressed: busy ? null : _back,
                    ),
                  ),
                  const SizedBox(width: SahoolSpacing.md),
                ],
                Expanded(
                  flex: 2,
                  child: isLast
                      ? PrimaryButton(
                          key: const ValueKey('save-field'),
                          label: s is FieldSaveFailed && s.view.retrySafe
                              ? 'إعادة المحاولة'
                              : 'حفظ الحقل',
                          icon: Icons.check,
                          loading: busy,
                          onPressed: (_nameOk && _boundaryOk) ? _submit : null,
                        )
                      : PrimaryButton(
                          key: const ValueKey('wizard-next'),
                          label: 'التالي',
                          onPressed: _canAdvance ? _next : null,
                        ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _doneView(BuildContext context, FieldSaveDone s) {
    final t = context.tokens;
    final est = s.yieldEstimate;
    final name = (s.field['name_ar'] ?? s.field['name'] ?? _trimmedName)
        .toString();
    final conf = est?['confidence'];
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _goToWorkspace(s.fieldId);
      },
      child: AppScaffold(
        title: 'تمّ إنشاء الحقل',
        showBack: false,
        body: ListView(
          padding: const EdgeInsets.all(SahoolSpacing.lg),
          children: [
            SectionCard(
              title: name,
              icon: Icons.check_circle_outline,
              child: Text(
                'المساحة المحفوظة: ${fmtArea(s.areaHa, decimals: 2)}',
                style: context.textStyles.bodyLarge,
              ),
            ),
            if (s.seasonWarning != null) ...[
              const SizedBox(height: SahoolSpacing.md),
              Text(
                s.seasonWarning!,
                style: context.textStyles.bodyLarge?.copyWith(color: t.warning),
              ),
            ],
            if (est != null) ...[
              const SizedBox(height: SahoolSpacing.md),
              SectionCard(
                title: 'تقدير الإنتاجيّة',
                icon: Icons.insights_outlined,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      fmtYieldKgHa(est['estimated_yield_kg_ha'] as num),
                      key: const ValueKey('yield-estimate'),
                      style: context.textStyles.headlineSmall,
                    ),
                    Text(
                      'تقدير استدلاليّ من الخادم، ليس قياساً'
                      '${conf != null ? ' · الثقة: $conf' : ''}'
                      '${est['requires_review'] == true ? ' · يحتاج مراجعة مهندس' : ''}',
                      style: context.textStyles.bodyMedium?.copyWith(
                        color: t.muted,
                      ),
                    ),
                    if (est['rationale_ar'] is String)
                      Padding(
                        padding: const EdgeInsets.only(top: SahoolSpacing.sm),
                        child: Text(est['rationale_ar'] as String),
                      ),
                  ],
                ),
              ),
            ],
            const SizedBox(height: SahoolSpacing.xl),
            PrimaryButton(
              key: const ValueKey('go-workspace'),
              label: 'إلى مساحة عمل الحقل',
              icon: Icons.arrow_forward,
              onPressed: () => _goToWorkspace(s.fieldId),
            ),
          ],
        ),
      ),
    );
  }
}
