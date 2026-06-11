// SAHOOL — lib/screens/inventory_screen.dart
// المخزون: عناصر + تتبّع الدفعات منتهية الصلاحيّة، عبر /api/v1/inventory/*.
// مُقيَّد بالدور (inventory:view عرض، inventory:manage إضافة) وبالمستأجِر.
// لا بيانات مُلفَّقة — حالات صادقة (تحميل/خطأ/فارغ). تطابق InventoryPage في الويب.
import 'package:flutter/material.dart';
import '../permissions.dart';
import '../services/api_service.dart';
import '../widgets/form_kit.dart';
import '../widgets/state_views.dart';

class InventoryScreen extends StatefulWidget {
  const InventoryScreen({super.key});
  @override
  State<InventoryScreen> createState() => _InventoryScreenState();
}

class _InventoryScreenState extends State<InventoryScreen> {
  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _items = const [];
  List<Map<String, dynamic>> _expiring = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final items = await ApiService.instance.getInventoryItems();
      final expiring = await ApiService.instance.getExpiringBatches();
      if (!mounted) return;
      setState(() {
        _items = items;
        _expiring = expiring;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = apiErrorMessage(e);
        _loading = false;
      });
    }
  }

  double? _num(dynamic v) => v is num ? v.toDouble() : double.tryParse('$v');

  @override
  Widget build(BuildContext context) {
    final mutable = canMutate(currentRole());
    return Scaffold(
      backgroundColor: kBg,
      appBar: AppBar(
        backgroundColor: kSurface,
        title: const Text('المخزون'),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
        ],
      ),
      floatingActionButton: mutable
          ? FloatingActionButton.extended(
              backgroundColor: kPrimary,
              onPressed: _openAddItem,
              icon: const Icon(Icons.add),
              label: const Text('عنصر جديد'),
            )
          : null,
      body: _loading
          ? const LoadingView()
          : _error != null
              ? ErrorView(message: _error!, onRetry: _load)
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
                    padding: const EdgeInsets.all(12),
                    children: [
                      if (_expiring.isNotEmpty) ...[
                        const SectionTitle('دفعات قاربت الانتهاء'),
                        ..._expiring.map(_expiringTile),
                        const SizedBox(height: 12),
                      ],
                      const SectionTitle('العناصر'),
                      if (_items.isEmpty)
                        const Padding(
                          padding: EdgeInsets.only(top: 40),
                          child: EmptyView(message: 'لا توجد عناصر مخزون بعد'),
                        )
                      else
                        ..._items.map((it) => _itemTile(it, mutable)),
                    ],
                  ),
                ),
    );
  }

  Widget _expiringTile(Map<String, dynamic> b) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: kWarn.withOpacity(0.1),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: kWarn.withOpacity(0.35)),
      ),
      child: Row(
        children: [
          const Icon(Icons.warning_amber_rounded, color: kWarn, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Text('${b['name'] ?? '—'}',
                style: const TextStyle(color: Colors.white)),
          ),
          Text('${b['expiry_date'] ?? ''}',
              style: const TextStyle(color: kWarn, fontSize: 12)),
        ],
      ),
    );
  }

  Widget _itemTile(Map<String, dynamic> it, bool mutable) {
    final low = it['low_stock'] == true;
    final qty = _num(it['total_quantity']) ?? 0;
    final unit = (it['unit'] ?? '').toString();
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: kSurface,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Flexible(
                      child: Text('${it['name'] ?? '—'}',
                          style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.bold)),
                    ),
                    if (low) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: Colors.red.withOpacity(0.2),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: const Text('مخزون منخفض',
                            style:
                                TextStyle(color: Colors.redAccent, fontSize: 10)),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  '${it['category'] ?? ''} · ${qty.toStringAsFixed(1)} $unit',
                  style: const TextStyle(color: Colors.grey, fontSize: 12),
                ),
              ],
            ),
          ),
          if (mutable)
            IconButton(
              icon: const Icon(Icons.add_box_outlined, color: kPrimary),
              tooltip: 'إضافة دفعة',
              onPressed: () => _openAddBatch(it),
            ),
        ],
      ),
    );
  }

  void _openAddItem() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: kSurface,
      isScrollControlled: true,
      builder: (_) => _AddItemSheet(onDone: _load),
    );
  }

  void _openAddBatch(Map<String, dynamic> item) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: kSurface,
      isScrollControlled: true,
      builder: (_) => _AddBatchSheet(item: item, onDone: _load),
    );
  }
}

class _AddItemSheet extends StatefulWidget {
  final Future<void> Function() onDone;
  const _AddItemSheet({required this.onDone});
  @override
  State<_AddItemSheet> createState() => _AddItemSheetState();
}

class _AddItemSheetState extends State<_AddItemSheet> {
  final _name = TextEditingController();
  final _unit = TextEditingController();
  final _reorder = TextEditingController();
  String _category = 'fertilizer';
  bool _saving = false;

  static const _categories = {
    'fertilizer': 'سماد',
    'pesticide': 'مبيد',
    'seed': 'بذور',
    'fuel': 'وقود',
    'spare_part': 'قطع غيار',
    'other': 'أخرى',
  };

  @override
  void dispose() {
    _name.dispose();
    _unit.dispose();
    _reorder.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_name.text.trim().isEmpty) {
      showSnack(context, 'الاسم مطلوب', error: true);
      return;
    }
    setState(() => _saving = true);
    try {
      await ApiService.instance.createInventoryItem({
        'category': _category,
        'name': _name.text.trim(),
        if (_unit.text.trim().isNotEmpty) 'unit': _unit.text.trim(),
        if (_reorder.text.trim().isNotEmpty)
          'reorder_level': double.tryParse(_reorder.text.trim()),
      });
      if (!mounted) return;
      Navigator.pop(context);
      await widget.onDone();
    } catch (e) {
      if (mounted) {
        setState(() => _saving = false);
        showSnack(context, apiErrorMessage(e), error: true);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return SheetScaffold(
      title: 'عنصر مخزون جديد',
      saving: _saving,
      onSubmit: _submit,
      children: [
        DropdownButtonFormField<String>(
          value: _category,
          dropdownColor: kSurface,
          decoration: kDec('الفئة'),
          style: const TextStyle(color: Colors.white),
          items: _categories.entries
              .map((e) =>
                  DropdownMenuItem(value: e.key, child: Text(e.value)))
              .toList(),
          onChanged: (v) => setState(() => _category = v ?? 'other'),
        ),
        kField(_name, 'الاسم'),
        kField(_unit, 'الوحدة (كجم/لتر…)'),
        kField(_reorder, 'حدّ إعادة الطلب', number: true),
      ],
    );
  }
}

class _AddBatchSheet extends StatefulWidget {
  final Map<String, dynamic> item;
  final Future<void> Function() onDone;
  const _AddBatchSheet({required this.item, required this.onDone});
  @override
  State<_AddBatchSheet> createState() => _AddBatchSheetState();
}

class _AddBatchSheetState extends State<_AddBatchSheet> {
  final _qty = TextEditingController();
  final _code = TextEditingController();
  final _expiry = TextEditingController();
  final _supplier = TextEditingController();
  bool _saving = false;

  @override
  void dispose() {
    _qty.dispose();
    _code.dispose();
    _expiry.dispose();
    _supplier.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final qty = double.tryParse(_qty.text.trim());
    if (qty == null || qty <= 0) {
      showSnack(context, 'كمّيّة صحيحة مطلوبة', error: true);
      return;
    }
    setState(() => _saving = true);
    try {
      await ApiService.instance.addInventoryBatch(
        widget.item['item_id'].toString(),
        {
          'quantity': qty,
          if (_code.text.trim().isNotEmpty) 'batch_code': _code.text.trim(),
          if (_expiry.text.trim().isNotEmpty)
            'expiry_date': _expiry.text.trim(),
          if (_supplier.text.trim().isNotEmpty)
            'supplier': _supplier.text.trim(),
        },
      );
      if (!mounted) return;
      Navigator.pop(context);
      await widget.onDone();
    } catch (e) {
      if (mounted) {
        setState(() => _saving = false);
        showSnack(context, apiErrorMessage(e), error: true);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return SheetScaffold(
      title: 'دفعة لـ${widget.item['name'] ?? ''}',
      saving: _saving,
      onSubmit: _submit,
      children: [
        kField(_qty, 'الكمّيّة', number: true),
        kField(_code, 'رمز الدفعة (اختياري)'),
        kField(_expiry, 'تاريخ الانتهاء YYYY-MM-DD (اختياري)'),
        kField(_supplier, 'المورّد (اختياري)'),
      ],
    );
  }
}
