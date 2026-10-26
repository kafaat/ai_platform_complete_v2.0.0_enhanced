// SAHOOL — features/inventory/presentation/inventory_sheets.dart
// أوراق الكتابة في المخزون: عنصر جديد، وإدخال مخزون (دفعة). كلّ ورقة:
//   • مفتاح Idempotency-Key واحد لعمر الورقة، يُعاد في كلّ محاولة حفظ؛
//   • تحقّق سطريّ داخل الورقة (لا SnackBar يُرسَم تحتها فلا يُرى)؛
//   • الأرقام العربيّة-الهنديّة تُقبَل (AppNumberField + parseLocalizedNum)؛
//   • زرّ الحفظ يُقفَل أثناء الإرسال (لا كتابة مكرّرة).
// إدخال المخزون عمل ميدانيّ: إن انقطعت الشبكة يُودَع في صندوق الإرسال دون اتّصال
// بنفس المفتاح — وإن لم يكن الصندوق متاحاً يُقال ذلك صراحةً بدل ادّعاء الحفظ.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/inventory/data/inventory_api.dart';
import 'package:sahool_app/features/inventory/data/inventory_models.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

/// نتيجة ورقة كتابة: حُفظت على الخادم، أو أُودعت للإرسال لاحقاً.
enum InventoryWriteResult { saved, queued }

/// رسالة ما بعد الإغلاق (تُعرَض في الشاشة الأمّ، لا تحت الورقة).
String inventoryResultMessage(InventoryWriteResult r, String savedText) =>
    r == InventoryWriteResult.saved
    ? savedText
    : 'لا اتّصال: حُفظت العمليّة على الجهاز وستُرسَل عند عودة الشبكة.';

const String kFixFieldsMessage = 'راجع الحقول المعلَّمة باللون الأحمر.';

// ── عنصر جديد ─────────────────────────────────────────────────────────

class AddInventoryItemSheet extends StatefulWidget {
  const AddInventoryItemSheet({super.key, required this.api});
  final InventoryApi api;

  @override
  State<AddInventoryItemSheet> createState() => _AddInventoryItemSheetState();
}

class _AddInventoryItemSheetState extends State<AddInventoryItemSheet> {
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _unit = TextEditingController();
  final _reorder = TextEditingController();
  final _notes = TextEditingController();
  final IdempotencyKey _key = IdempotencyKey.generate();
  String _category = 'fertilizer';
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _unit.dispose();
    _reorder.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_submitting) return;
    if (!(_form.currentState?.validate() ?? false)) {
      setState(() => _error = kFixFieldsMessage);
      return;
    }
    final reorder = parseLocalizedNum(_reorder.text);
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await widget.api.createInventoryItem({
        'category': _category,
        'name': _name.text.trim(),
        if (_unit.text.trim().isNotEmpty) 'unit': _unit.text.trim(),
        if (reorder != null) 'reorder_level': reorder,
        if (_notes.text.trim().isNotEmpty) 'notes': _notes.text.trim(),
      }, idempotencyKey: _key);
      if (!mounted) return;
      Navigator.of(context).pop(InventoryWriteResult.saved);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _submitting = false;
        _error = ApiException.from(e).messageAr;
      });
    }
  }

  @override
  Widget build(BuildContext context) => Form(
    key: _form,
    child: AppSheet(
      title: 'عنصر مخزون جديد',
      submitLabel: 'حفظ العنصر',
      submitting: _submitting,
      onSubmit: _submit,
      errorText: _error,
      children: [
        AppDropdown<String>(
          label: 'الفئة',
          items: kInventoryCategories,
          value: _category,
          onChanged: (v) => setState(() => _category = v ?? 'other'),
        ),
        AppTextField(
          label: 'الاسم',
          controller: _name,
          textInputAction: TextInputAction.next,
          validator: (v) => (v ?? '').trim().isEmpty ? 'الاسم مطلوب' : null,
        ),
        AppTextField(
          label: 'الوحدة',
          hint: 'كجم، لتر، كيس…',
          controller: _unit,
          textInputAction: TextInputAction.next,
        ),
        AppNumberField(
          label: 'حدّ إعادة الطلب',
          controller: _reorder,
          min: 0,
          helper: 'ينبّهك حين تنزل الكمّيّة إليه أو أقلّ',
        ),
        AppTextField(
          label: 'ملاحظات (اختياري)',
          controller: _notes,
          maxLines: 2,
        ),
      ],
    ),
  );
}

// ── إدخال مخزون (دفعة جديدة) ────────────────────────────────────────

class StockInSheet extends StatefulWidget {
  const StockInSheet({
    super.key,
    required this.api,
    required this.item,
    this.outbox,
    this.today,
  });

  final InventoryApi api;
  final InventoryItem item;

  /// الافتراضيّ [OfflineOutbox.instance] (يُحقَن في الاختبارات).
  final OfflineOutbox? outbox;
  final DateTime? today;

  @override
  State<StockInSheet> createState() => _StockInSheetState();
}

class _StockInSheetState extends State<StockInSheet> {
  final _form = GlobalKey<FormState>();
  final _qty = TextEditingController();
  final _unit = TextEditingController();
  final _code = TextEditingController();
  final _supplier = TextEditingController();
  final _notes = TextEditingController();
  final IdempotencyKey _key = IdempotencyKey.generate();
  late DateTime _received;
  DateTime? _expiry;
  bool _submitting = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final t = widget.today ?? DateTime.now();
    _received = DateTime(t.year, t.month, t.day);
    _unit.text = widget.item.unit;
  }

  @override
  void dispose() {
    _qty.dispose();
    _unit.dispose();
    _code.dispose();
    _supplier.dispose();
    _notes.dispose();
    super.dispose();
  }

  String get _path => '/api/v1/inventory/items/${widget.item.id}/batches';

  Future<void> _submit() async {
    if (_submitting) return;
    if (!(_form.currentState?.validate() ?? false)) {
      setState(() => _error = kFixFieldsMessage);
      return;
    }
    final body = <String, dynamic>{
      'quantity': parseLocalizedNum(_qty.text),
      if (_unit.text.trim().isNotEmpty) 'unit': _unit.text.trim(),
      if (_code.text.trim().isNotEmpty) 'batch_code': _code.text.trim(),
      if (_expiry != null) 'expiry_date': isoCalendarDate(_expiry!),
      'received_at': isoCalendarDate(_received),
      if (_supplier.text.trim().isNotEmpty) 'supplier': _supplier.text.trim(),
      if (_notes.text.trim().isNotEmpty) 'notes': _notes.text.trim(),
    };
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await widget.api.addInventoryBatch(
        widget.item.id,
        body,
        idempotencyKey: _key,
      );
      if (!mounted) return;
      Navigator.of(context).pop(InventoryWriteResult.saved);
    } catch (e) {
      final err = ApiException.from(e);
      if (err.isConnectivity) {
        final receipt = await (widget.outbox ?? OfflineOutbox.instance).enqueue(
          OutboxOp(
            kind: 'inventory_batch_add',
            method: 'POST',
            path: _path,
            body: body,
            idempotencyKey: _key.value,
            labelAr: 'إدخال مخزون: ${widget.item.name}',
          ),
        );
        if (!mounted) return;
        if (receipt.queued) {
          Navigator.of(context).pop(InventoryWriteResult.queued);
          return;
        }
        setState(() {
          _submitting = false;
          _error =
              '${err.messageAr}\nلم تُحفَظ الدفعة: الحفظ دون اتّصال غير '
              'متاح بعد على هذا الجهاز. أعِد المحاولة حين تعود الشبكة.';
        });
        return;
      }
      if (!mounted) return;
      setState(() {
        _submitting = false;
        _error = err.messageAr;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final today = widget.today ?? DateTime.now();
    return Form(
      key: _form,
      child: AppSheet(
        title: 'إدخال مخزون — ${widget.item.name}',
        submitLabel: 'حفظ الدفعة',
        submitting: _submitting,
        onSubmit: _submit,
        errorText: _error,
        children: [
          _QuantityField(controller: _qty),
          AppTextField(
            label: 'الوحدة',
            controller: _unit,
            helper: 'وحدة العنصر افتراضيّاً',
          ),
          OpsDateField(
            label: 'تاريخ الاستلام',
            value: _received,
            firstDate: DateTime(today.year - 5),
            lastDate: DateTime(today.year, today.month, today.day),
            onChanged: (d) => setState(
              () =>
                  _received = d ?? DateTime(today.year, today.month, today.day),
            ),
          ),
          OpsDateField(
            label: 'تاريخ انتهاء الصلاحيّة (اختياري)',
            value: _expiry,
            firstDate: DateTime(today.year - 1),
            lastDate: DateTime(today.year + 10),
            onChanged: (d) => setState(() => _expiry = d),
          ),
          AppTextField(label: 'رمز الدفعة (اختياري)', controller: _code),
          AppTextField(label: 'المورّد (اختياري)', controller: _supplier),
          AppTextField(
            label: 'السبب / ملاحظات (اختياري)',
            hint: 'شراء، تحويل من مخزن آخر…',
            controller: _notes,
            maxLines: 2,
          ),
        ],
      ),
    );
  }
}

/// كمّيّة إلزاميّة > 0. AppNumberField يقبل الصفر (min شامل) ودفعة بصفر بلا
/// معنى، فهذا الحقل يكرّر سلوكه (لوحة أرقام + تحويل ٠-٩ و«٫») بتحقّق أشدّ.
class _QuantityField extends StatelessWidget {
  const _QuantityField({required this.controller});
  final TextEditingController controller;

  static String? validate(String? raw) {
    final text = raw?.trim() ?? '';
    if (text.isEmpty) return 'الكمّيّة مطلوبة';
    final v = parseLocalizedNum(text);
    if (v == null) return 'أدخل رقماً صحيحاً';
    if (v <= 0) return 'الكمّيّة يجب أن تكون أكبر من صفر';
    return null;
  }

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: SahoolSpacing.md),
    child: TextFormField(
      controller: controller,
      validator: validate,
      autovalidateMode: AutovalidateMode.onUserInteraction,
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
      inputFormatters: const [LocalizedDigitsFormatter()],
      decoration: const InputDecoration(labelText: 'الكمّيّة المستلمة'),
    ),
  );
}
