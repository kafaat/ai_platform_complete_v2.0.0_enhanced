// SAHOOL — features/lab_sampling/presentation/sample_create_screen.dart
// تسجيل عيّنة في الحقل: النوع (تربة/ماء)، موقع GPS بدقّته، العمق، تاريخ الجمع،
// المصدر والرمز. يعمل دون اتّصال عبر صندوق الإرسال ويقول بصدق ما حدث.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/connectivity_status.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

import '../data/lab_sampling_api.dart';
import 'gps_reader.dart';
import 'protocol_screen.dart';
import 'sample_create_cubit.dart';

/// نتيجة الشاشة لمن فتحها.
enum SampleCreateResult { sent, queued }

/// دقّة GPS أسوأ من هذا تستحقّ تنبيهاً (نقطة العيّنة تُرسَم على الخريطة).
const double kGpsAccuracyWarnM = 20;

class SampleCreateScreen extends StatelessWidget {
  const SampleCreateScreen({
    super.key,
    required this.fieldId,
    this.fieldName,
    this.areaHa,
    this.api,
    this.outbox,
    this.isOnline,
    this.gpsReader,
    this.today,
  });

  final String fieldId;
  final String? fieldName;
  final double? areaHa;
  final LabSamplingApi? api;
  final OfflineOutbox? outbox;
  final bool Function()? isOnline;
  final GpsReader? gpsReader;
  final DateTime? today;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) => SampleCreateCubit(
      api ?? LabSamplingApi.instance,
      outbox: outbox,
      isOnline: isOnline ?? () => ConnectivityStatus.instance.isOnline,
      fieldLabel: fieldName,
    ),
    child: _SampleForm(
      fieldId: fieldId,
      areaHa: areaHa,
      api: api,
      gpsReader: gpsReader ?? readDeviceGps,
      today: today,
    ),
  );
}

class _SampleForm extends StatefulWidget {
  const _SampleForm({
    required this.fieldId,
    required this.gpsReader,
    this.areaHa,
    this.api,
    this.today,
  });

  final String fieldId;
  final double? areaHa;
  final LabSamplingApi? api;
  final GpsReader gpsReader;
  final DateTime? today;

  @override
  State<_SampleForm> createState() => _SampleFormState();
}

class _SampleFormState extends State<_SampleForm> {
  final _lat = TextEditingController();
  final _lon = TextEditingController();
  final _from = TextEditingController();
  final _to = TextEditingController();
  final _source = TextEditingController();
  final _barcode = TextEditingController();
  String _kind = 'soil';
  double? _accuracy;
  bool _gpsBusy = false;
  String? _gpsError;
  late DateTime _sampledOn;

  /// عمق مقترح من بروتوكول الخادم (null ⇒ لا اقتراح).
  (int, int)? _suggestedDepth;

  @override
  void initState() {
    super.initState();
    final now = widget.today ?? DateTime.now();
    _sampledOn = DateTime(now.year, now.month, now.day);
    _loadDepthHint();
  }

  Future<void> _loadDepthHint() async {
    try {
      final p = await (widget.api ?? LabSamplingApi.instance).getProtocol(
        areaHa: widget.areaHa,
      );
      final depth = p['depth'];
      final r = parseDepthRangeCm(
        depth is Map ? depth['depth_ar']?.toString() : null,
      );
      if (mounted) setState(() => _suggestedDepth = r);
    } catch (_) {
      // الإرشاد اختياريّ؛ دون اتّصال يبقى الإدخال يدويّاً.
    }
  }

  @override
  void dispose() {
    for (final c in [_lat, _lon, _from, _to, _source, _barcode]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _captureGps() async {
    setState(() {
      _gpsBusy = true;
      _gpsError = null;
    });
    try {
      final fix = await widget.gpsReader();
      if (!mounted) return;
      setState(() {
        _lat.text = fix.latitude.toStringAsFixed(6);
        _lon.text = fix.longitude.toStringAsFixed(6);
        _accuracy = fix.accuracyM;
      });
    } on GpsFailure catch (e) {
      if (mounted) setState(() => _gpsError = e.messageAr);
    } catch (_) {
      if (mounted) {
        setState(
          () => _gpsError =
              'تعذّر التقاط الموقع — أعد المحاولة أو أدخل الإحداثيّات.',
        );
      }
    } finally {
      if (mounted) setState(() => _gpsBusy = false);
    }
  }

  SampleDraft _draft() => SampleDraft(
    fieldId: widget.fieldId,
    kind: _kind,
    latitudeText: _lat.text,
    longitudeText: _lon.text,
    accuracyM: _accuracy,
    depthFromText: _kind == 'soil' ? _from.text : '',
    depthToText: _kind == 'soil' ? _to.text : '',
    sampledOn: _sampledOn,
    source: _source.text,
    barcode: _barcode.text,
  );

  Future<void> _pickDate() async {
    final now = widget.today ?? DateTime.now();
    final d = await showDatePicker(
      context: context,
      initialDate: _sampledOn,
      firstDate: DateTime(now.year - 2),
      lastDate: DateTime(now.year, now.month, now.day),
      helpText: 'تاريخ الجمع',
    );
    if (d != null && mounted) setState(() => _sampledOn = d);
  }

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    return BlocConsumer<SampleCreateCubit, SampleCreateState>(
      listener: (context, state) {
        if (state is SampleSent) {
          Navigator.of(context).pop(SampleCreateResult.sent);
        } else if (state is SampleQueued) {
          Navigator.of(context).pop(SampleCreateResult.queued);
        }
      },
      builder: (context, state) {
        final errors = state is SampleEditing
            ? state.errors
            : const <String, String>{};
        final submitError = state is SampleEditing ? state.submitError : null;
        final busy = state is SampleSubmitting;
        // تعديل الإحداثيّات يدويّاً يُسقط دقّة GPS (لم تعد قراءة جهاز).
        void manualEdit(String _) {
          if (_accuracy != null) setState(() => _accuracy = null);
        }

        return AppScaffold(
          title: 'عيّنة جديدة',
          padded: true,
          actions: [
            AppIconButton(
              icon: Icons.menu_book_outlined,
              tooltip: 'إرشادات أخذ العيّنة',
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) =>
                      ProtocolScreen(areaHa: widget.areaHa, api: widget.api),
                ),
              ),
            ),
          ],
          body: ListView(
            padding: const EdgeInsetsDirectional.only(
              top: SahoolSpacing.md,
              bottom: SahoolSpacing.xl,
            ),
            children: [
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(
                    value: 'soil',
                    label: Text('تربة'),
                    icon: Icon(Icons.landscape_outlined),
                  ),
                  ButtonSegment(
                    value: 'water',
                    label: Text('ماء ريّ'),
                    icon: Icon(Icons.water_drop_outlined),
                  ),
                ],
                selected: {_kind},
                onSelectionChanged: busy
                    ? null
                    : (s) => setState(() => _kind = s.first),
              ),
              const SizedBox(height: SahoolSpacing.lg),
              PrimaryButton(
                key: const ValueKey('sample_gps'),
                label: _lat.text.isEmpty
                    ? 'التقاط موقع العيّنة (GPS)'
                    : 'إعادة التقاط الموقع',
                icon: Icons.my_location,
                loading: _gpsBusy,
                tone: ButtonTone.accent,
                onPressed: busy || _gpsBusy ? null : _captureGps,
              ),
              if (_accuracy != null)
                Padding(
                  padding: const EdgeInsetsDirectional.only(
                    top: SahoolSpacing.sm,
                  ),
                  child: Text(
                    'دقّة الموقع: ± ${fmtNumber(_accuracy, decimals: 0)} م'
                    '${_accuracy! > kGpsAccuracyWarnM ? ' — منخفضة، انتظر قليلاً في مكان مكشوف ثمّ أعد الالتقاط' : ''}',
                    style: context.textStyles.bodyMedium?.copyWith(
                      color: _accuracy! > kGpsAccuracyWarnM
                          ? t.warning
                          : t.muted,
                    ),
                  ),
                ),
              if (_gpsError != null)
                Padding(
                  padding: const EdgeInsetsDirectional.only(
                    top: SahoolSpacing.sm,
                  ),
                  child: Text(
                    _gpsError!,
                    style: context.textStyles.bodyMedium?.copyWith(
                      color: t.danger,
                    ),
                  ),
                ),
              Row(
                children: [
                  Expanded(
                    child: AppTextField(
                      key: const ValueKey('sample_lat'),
                      label: 'خط العرض',
                      controller: _lat,
                      keyboardType: const TextInputType.numberWithOptions(
                        decimal: true,
                        signed: true,
                      ),
                      inputFormatters: const [LocalizedDigitsFormatter()],
                      onChanged: manualEdit,
                    ),
                  ),
                  const SizedBox(width: SahoolSpacing.md),
                  Expanded(
                    child: AppTextField(
                      key: const ValueKey('sample_lon'),
                      label: 'خط الطول',
                      controller: _lon,
                      keyboardType: const TextInputType.numberWithOptions(
                        decimal: true,
                        signed: true,
                      ),
                      inputFormatters: const [LocalizedDigitsFormatter()],
                      onChanged: manualEdit,
                    ),
                  ),
                ],
              ),
              if (errors[SampleField.location] != null)
                _InlineError(errors[SampleField.location]!),
              if (_kind == 'soil') ...[
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: AppTextField(
                        key: const ValueKey('sample_depth_from'),
                        label: 'العمق من (سم)',
                        controller: _from,
                        keyboardType: TextInputType.number,
                        inputFormatters: const [LocalizedDigitsFormatter()],
                        errorText: errors[SampleField.depthFrom],
                      ),
                    ),
                    const SizedBox(width: SahoolSpacing.md),
                    Expanded(
                      child: AppTextField(
                        key: const ValueKey('sample_depth_to'),
                        label: 'العمق إلى (سم)',
                        controller: _to,
                        keyboardType: TextInputType.number,
                        inputFormatters: const [LocalizedDigitsFormatter()],
                        errorText: errors[SampleField.depthTo],
                      ),
                    ),
                  ],
                ),
                if (_suggestedDepth != null)
                  Padding(
                    padding: const EdgeInsetsDirectional.only(
                      top: SahoolSpacing.sm,
                    ),
                    child: Align(
                      alignment: AlignmentDirectional.centerStart,
                      child: ActionChip(
                        avatar: const Icon(
                          Icons.straighten,
                          size: SahoolSizes.iconSm,
                        ),
                        label: Text(
                          'العمق الموصى به ${_suggestedDepth!.$1}–${_suggestedDepth!.$2} سم',
                        ),
                        onPressed: busy
                            ? null
                            : () => setState(() {
                                _from.text = '${_suggestedDepth!.$1}';
                                _to.text = '${_suggestedDepth!.$2}';
                              }),
                      ),
                    ),
                  ),
              ],
              Padding(
                padding: const EdgeInsetsDirectional.only(
                  top: SahoolSpacing.md,
                ),
                child: AppListTile(
                  icon: Icons.event_outlined,
                  title: 'تاريخ الجمع',
                  subtitle: fmtDate(_sampledOn),
                  onTap: busy ? null : _pickDate,
                ),
              ),
              AppTextField(
                label: _kind == 'water'
                    ? 'مصدر الماء (بئر، قناة…)'
                    : 'ملاحظة المكان (اختياريّ)',
                controller: _source,
                errorText: errors[SampleField.source],
              ),
              AppTextField(
                label: 'رمز الكيس/الباركود (اختياريّ)',
                controller: _barcode,
                errorText: errors[SampleField.barcode],
              ),
              if (submitError != null) _InlineError(submitError),
              const SizedBox(height: SahoolSpacing.lg),
              PrimaryButton(
                key: const ValueKey('sample_submit'),
                label: 'حفظ العيّنة',
                icon: Icons.save_outlined,
                loading: busy,
                onPressed: busy
                    ? null
                    : () => context.read<SampleCreateCubit>().submit(_draft()),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _InlineError extends StatelessWidget {
  const _InlineError(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsetsDirectional.only(top: SahoolSpacing.sm),
    child: Semantics(
      liveRegion: true,
      child: Text(
        text,
        style: context.textStyles.bodyMedium?.copyWith(
          color: context.tokens.danger,
        ),
      ),
    ),
  );
}
