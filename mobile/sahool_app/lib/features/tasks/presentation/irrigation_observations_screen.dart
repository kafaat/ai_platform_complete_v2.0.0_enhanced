import 'package:flutter/material.dart';
import 'package:sahool_app/core/session/auth_state.dart';
import 'package:sahool_app/services/auth_service.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_record.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';
import '../data/irrigation_observations_api.dart';

/// Adds evidence only. It never completes a task or writes the water ledger.
class IrrigationObservationsScreen extends StatefulWidget {
  const IrrigationObservationsScreen({
    super.key, required this.taskId, required this.fieldId,
    required this.canEdit, this.api, this.outbox, this.ownerReader, this.authState,
  });
  final String taskId;
  final String fieldId;
  final bool canEdit;
  final IrrigationObservationsApi? api;
  final OfflineOutbox? outbox;
  final OutboxOwner? Function()? ownerReader;
  final AuthState? authState;

  @override
  State<IrrigationObservationsScreen> createState() =>
      _IrrigationObservationsScreenState();
}

class _IrrigationObservationsScreenState
    extends State<IrrigationObservationsScreen> {
  late final _api = widget.api ?? IrrigationObservationsApi();
  final _values = <String, TextEditingController>{
    for (final key in ['meter_start_m3', 'meter_end_m3', 'flow_m3_h',
      'duration_minutes', 'interruptions_minutes', 'volume_m3',
      'irrigated_area_ha', 'notes']) key: TextEditingController(),
  };
  List<Map<String, dynamic>> _executions = [];
  List<Map<String, dynamic>> _history = [];
  String? _execution;
  String _source = 'farmer_task';
  String _outcome = 'unknown';
  String _method = 'unknown';
  DateTime _occurred = DateTime.now();
  bool _loading = true;
  bool _saving = false;
  bool _queued = false;
  String? _readError;
  String? _writeError;
  IrrigationObservation? _pending;
  late final OutboxOwner? _originOwner;
  bool _sessionChanged = false;
  OutboxOwner? _currentOwner() => widget.ownerReader != null
      ? widget.ownerReader!()
      : OutboxOwner.fromAccessToken(AuthService.instance.token);
  bool get _sameSession => !_sessionChanged && _originOwner != null &&
      _originOwner == _currentOwner();

  void _onAuthChanged() {
    if (!mounted) return;
    setState(() {
      _sessionChanged = true;
      _history = [];
      _executions = [];
      _execution = null;
      _readError = null;
      _pending = null;
      _queued = false;
      for (final controller in _values.values) { controller.clear(); }
      _writeError = 'تغيّرت الجلسة. افتح المهمّة من حسابك الحالي قبل تسجيل إفادة.';
    });
  }

  @override
  void initState() {
    super.initState();
    _originOwner = _currentOwner();
    (widget.authState ?? AuthState.instance).addListener(_onAuthChanged);
    _load();
  }

  @override
  void dispose() {
    (widget.authState ?? AuthState.instance).removeListener(_onAuthChanged);
    for (final controller in _values.values) { controller.dispose(); }
    super.dispose();
  }

  Future<void> _load() async {
    if (!_sameSession) {
      setState(() { _loading = false; _readError = 'الجلسة لا تطابق صاحب هذه الشاشة.'; });
      return;
    }
    setState(() { _loading = true; _readError = null; });
    try {
      final history = await _api.history(widget.taskId);
      if (!mounted || !_sameSession) return;
      final executions = await _api.executions(widget.fieldId);
      if (!mounted || !_sameSession) return;
      setState(() { _history = history; _executions = executions; });
    } catch (e) {
      if (mounted && _sameSession) setState(() => _readError = ApiException.from(e).messageAr);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _pickTime() async {
    final day = await showDatePicker(context: context,
      initialDate: _occurred, firstDate: DateTime(2000), lastDate: DateTime.now());
    if (!mounted || !_sameSession || day == null) return;
    final time = await showTimePicker(context: context,
      initialTime: TimeOfDay.fromDateTime(_occurred));
    if (!mounted || !_sameSession || time == null) return;
    setState(() => _occurred = DateTime(day.year, day.month, day.day,
      time.hour, time.minute));
  }

  Future<void> _save() async {
    if (_saving || _queued || !widget.canEdit) return;
    if (!_sameSession) {
      setState(() => _writeError = 'تغيّرت الجلسة؛ لم تُرسل هذه الإفادة بحساب آخر.');
      return;
    }
    if (_pending == null) {
      final body = <String, dynamic>{
        'observation_id': IdempotencyKey.generate().value,
        'execution_id': _execution,
        'source': _source, 'outcome': _outcome,
        'occurred_at': _occurred.toUtc().toIso8601String(),
        'quantity_method': _method, 'interruptions_minutes': 0,
        'volume_m3': null,
      };
      final keys = [
        if (_method == 'meter') ...['meter_start_m3', 'meter_end_m3'],
        if (_method == 'estimated_flow') ...[
          'flow_m3_h', 'duration_minutes', 'interruptions_minutes'],
        if (_method == 'declared_volume') 'volume_m3',
        if (_outcome == 'irrigated') 'irrigated_area_ha',
      ];
      for (final key in keys) {
        final text = _values[key]!.text.trim();
        if (text.isEmpty) continue;
        final value = double.tryParse(text);
        if (value == null || !value.isFinite) {
          setState(() => _writeError = 'أدخل أرقاماً صالحة؛ لا تقبل NaN أو Infinity.');
          return;
        }
        body[key] = value;
      }
      final note = _values['notes']!.text.trim();
      if (note.isNotEmpty) body['notes'] = note;
      final error = validateIrrigationObservation(body);
      if (error != null) { setState(() => _writeError = error); return; }
      _pending = IrrigationObservation(body);
    }
    setState(() { _saving = true; _writeError = null; });
    try {
      // Persist first. The owner-bound outbox owns retry and the immutable UUID.
      final receipt = await (widget.outbox ?? OfflineOutbox.instance).enqueue(
        _pending!.toOutbox(widget.taskId, widget.fieldId),
      );
      if (!mounted || !_sameSession) return;
      setState(() {
        _queued = receipt.queued;
        if (!_queued) _writeError = 'تعذّر تأكيد الحفظ المحلي. أعد محاولة حفظ الإفادة نفسها.';
      });
    } catch (_) {
      if (mounted && _sameSession) setState(() => _writeError =
        'تعذّر تأكيد الحفظ. احتفظنا بالإفادة نفسها لإعادة المحاولة.');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _number(String key, String label) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
    child: TextField(controller: _values[key],
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
      decoration: InputDecoration(labelText: label)),
  );

  Widget _select(String label, String value, Map<String, String> choices,
      void Function(String) change) => DropdownButtonFormField<String>(
    value: value, decoration: InputDecoration(labelText: label),
    items: choices.entries.map((e) => DropdownMenuItem(
      value: e.key, child: Text(e.value))).toList(),
    onChanged: (v) { if (v != null) setState(() => change(v)); },
  );

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('إفادات الريّ للمهمّة')),
    body: ListView(padding: const EdgeInsets.all(16), children: [
      const Text('هذه إفادة ميدانية. لا تُنجز المهمّة ولا تؤكد كمية الماء في الدفتر تلقائياً.'),
      if (_loading) const LinearProgressIndicator(),
      if (_readError != null) Text(_readError!),
      TextButton(onPressed: _loading ? null : _load,
        child: const Text('تحديث سجل الإفادات والتنفيذات')),
      for (final item in _history) ListTile(
        title: Text({'irrigated': 'أفاد بحدوث ريّ', 'not_irrigated': 'لم يحدث ريّ',
          'unknown': 'النتيجة غير معروفة'}[item['outcome']] ?? 'إفادة ريّ'),
        subtitle: Text('${item['occurred_at'] ?? 'وقت غير معروف'}\n'
          'الحجم: ${(item['computed'] is Map ? item['computed']['volume_m3'] : item['volume_m3']) ?? 'غير معروف'} م³\n'
          '${item['notes'] ?? ''}'),
      ),
      if (!_loading && _readError == null && _history.isEmpty)
        const Text('لا إفادات مؤكدة على الخادم حتى الآن.'),
      if (_queued) const Card(child: Padding(padding: EdgeInsets.all(12),
        child: Text('حُفظت الإفادة محلياً للمزامنة. تابع حالة الإرسال في صفحة المزامنة؛ '
          'لا تعني هذه الرسالة تأكيد الخادم. حدّث السجل للتحقق.'))),
      if (widget.canEdit && !_queued) ...[
        const Divider(),
        AbsorbPointer(absorbing: _pending != null || _saving || !_sameSession,
          child: Column(children: [
            if (_executions.isEmpty) const Text(
              'لا يوجد تنفيذ ريّ متاح للاختيار. يلزم ربط الإفادة بتنفيذ قائم؛ لا يُنشأ تنفيذ تلقائياً.'),
            DropdownButtonFormField<String>(value: _execution,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'تنفيذ الريّ'),
              items: _executions.where((e) => e['execution_id'] != null).map((e) =>
                DropdownMenuItem<String>(value: e['execution_id'].toString(),
                  child: Text('${e['execution_id']} — ${e['state'] ?? ''}',
                    overflow: TextOverflow.ellipsis))).toList(),
              onChanged: (v) => setState(() => _execution = v)),
            _select('مصدر الإفادة', _source, const {
              'farmer_task': 'إفادة المزارع', 'field_inspection': 'كشف ميداني'},
              (v) => _source = v),
            _select('هل حدث ريّ؟', _outcome, const {
              'irrigated': 'نعم', 'not_irrigated': 'لا', 'unknown': 'غير معروف'},
              (v) { _outcome = v; if (v != 'irrigated') _method = 'unknown'; }),
            if (_outcome == 'irrigated') _select('طريقة تحديد الكمية', _method, const {
              'unknown': 'غير معروفة', 'meter': 'عداد ماء',
              'estimated_flow': 'تقدير من التدفق والمدة', 'declared_volume': 'حجم مصرّح به'},
              (v) => _method = v),
            if (_method == 'meter') ...[
              _number('meter_start_m3', 'قراءة العداد في البداية (م³)'),
              _number('meter_end_m3', 'قراءة العداد في النهاية (م³)')],
            if (_method == 'estimated_flow') ...[
              _number('flow_m3_h', 'التدفق التقديري (م³/ساعة)'),
              _number('duration_minutes', 'المدة الكلية (دقيقة)'),
              _number('interruptions_minutes', 'الانقطاعات ضمن المدة (دقيقة)')],
            if (_method == 'declared_volume') _number('volume_m3', 'الحجم المصرّح به (م³)'),
            if (_outcome == 'irrigated')
              _number('irrigated_area_ha', 'المساحة المروية (هكتار، اختياري)'),
            TextButton(onPressed: _pickTime,
              child: Text('وقت المشاهدة المحلي: $_occurred')),
            TextField(controller: _values['notes'], maxLength: 2000,
              decoration: const InputDecoration(labelText: 'ملاحظات')),
          ])),
        if (_writeError != null) Text(_writeError!),
        if (_pending != null && !_queued) const Text(
          'ثُبّتت بيانات هذه المحاولة. إعادة الحفظ تستخدم الإفادة نفسها ولا تنشئ مفتاحاً جديداً.'),
        FilledButton(onPressed: _saving || _loading || !_sameSession ? null : _save,
          child: Text(_saving ? 'جارٍ الحفظ المحلي…' :
            _pending == null ? 'حفظ الإفادة للمزامنة' : 'إعادة حفظ الإفادة نفسها')),
      ],
    ]),
  );
}
