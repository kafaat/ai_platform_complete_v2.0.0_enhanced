// SAHOOL — lib/screens/master_data_screen.dart
// البيانات المرجعيّة: كتالوج (محصول/تربة/سماد/مبيد/صنف بذور/نوع معدّة/أخرى) عبر
// /api/v1/master-data. إدارة فقط (owner/manager): العرض متاح لمن يصل الشاشة،
// لكن الإضافة محكومة بـcanManage. 409 عند تكرار (المستأجِر،الفئة،الرمز).
// لا بيانات مُلفَّقة. تطابق MasterDataPage في الويب.
import 'package:flutter/material.dart';
import '../permissions.dart';
import '../services/api_service.dart';
import '../widgets/form_kit.dart';
import '../widgets/state_views.dart';

const Map<String, String> kMasterCategories = {
  'crop': 'المحاصيل',
  'soil_type': 'أنواع التربة',
  'fertilizer': 'الأسمدة',
  'pesticide': 'المبيدات',
  'seed_variety': 'أصناف البذور',
  'equipment_type': 'أنواع المعدّات',
  'other': 'أخرى',
};

class MasterDataScreen extends StatefulWidget {
  const MasterDataScreen({super.key});
  @override
  State<MasterDataScreen> createState() => _MasterDataScreenState();
}

class _MasterDataScreenState extends State<MasterDataScreen> {
  bool _loading = true;
  String? _error;
  String _category = 'crop';
  List<Map<String, dynamic>> _entries = const [];

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
      final data = await ApiService.instance.getMasterData(_category);
      if (!mounted) return;
      setState(() {
        _entries = data;
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

  @override
  Widget build(BuildContext context) {
    // إدارة فقط: الإضافة محكومة بـcanManage (owner/manager).
    final manageable = canManage(currentRole());
    return Scaffold(
      backgroundColor: kBg,
      appBar: AppBar(
        backgroundColor: kSurface,
        title: const Text('البيانات المرجعيّة'),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
        ],
      ),
      floatingActionButton: manageable
          ? FloatingActionButton.extended(
              backgroundColor: kPrimary,
              onPressed: _openAdd,
              icon: const Icon(Icons.add),
              label: const Text('إدخال'),
            )
          : null,
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: DropdownButtonFormField<String>(
              value: _category,
              dropdownColor: kSurface,
              decoration: kDec('الفئة'),
              style: const TextStyle(color: Colors.white),
              items: kMasterCategories.entries
                  .map((e) =>
                      DropdownMenuItem(value: e.key, child: Text(e.value)))
                  .toList(),
              onChanged: (v) {
                if (v != null) {
                  setState(() => _category = v);
                  _load();
                }
              },
            ),
          ),
          Expanded(
            child: _loading
                ? const LoadingView()
                : _error != null
                    ? ErrorView(message: _error!, onRetry: _load)
                    : _entries.isEmpty
                        ? const EmptyView(message: 'لا إدخالات في هذه الفئة')
                        : RefreshIndicator(
                            onRefresh: _load,
                            child: ListView.builder(
                              padding: const EdgeInsets.all(12),
                              itemCount: _entries.length,
                              itemBuilder: (_, i) {
                                final e = _entries[i];
                                return Container(
                                  margin: const EdgeInsets.only(bottom: 8),
                                  padding: const EdgeInsets.all(12),
                                  decoration: BoxDecoration(
                                    color: kSurface,
                                    borderRadius: BorderRadius.circular(10),
                                  ),
                                  child: Row(
                                    children: [
                                      Expanded(
                                        child: Column(
                                          crossAxisAlignment:
                                              CrossAxisAlignment.start,
                                          children: [
                                            Text('${e['name_ar'] ?? '—'}',
                                                style: const TextStyle(
                                                    color: Colors.white,
                                                    fontWeight:
                                                        FontWeight.bold)),
                                            if ((e['name_en'] ?? '')
                                                .toString()
                                                .isNotEmpty)
                                              Text('${e['name_en']}',
                                                  style: const TextStyle(
                                                      color: Colors.grey,
                                                      fontSize: 12)),
                                          ],
                                        ),
                                      ),
                                      Text('${e['code'] ?? ''}',
                                          style: const TextStyle(
                                              color: kSecondary, fontSize: 12)),
                                    ],
                                  ),
                                );
                              },
                            ),
                          ),
          ),
        ],
      ),
    );
  }

  void _openAdd() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: kSurface,
      isScrollControlled: true,
      builder: (_) =>
          _AddEntrySheet(category: _category, onDone: _load),
    );
  }
}

class _AddEntrySheet extends StatefulWidget {
  final String category;
  final Future<void> Function() onDone;
  const _AddEntrySheet({required this.category, required this.onDone});
  @override
  State<_AddEntrySheet> createState() => _AddEntrySheetState();
}

class _AddEntrySheetState extends State<_AddEntrySheet> {
  final _code = TextEditingController();
  final _nameAr = TextEditingController();
  final _nameEn = TextEditingController();
  bool _saving = false;

  @override
  void dispose() {
    _code.dispose();
    _nameAr.dispose();
    _nameEn.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_code.text.trim().isEmpty || _nameAr.text.trim().isEmpty) {
      showSnack(context, 'الرمز والاسم العربيّ مطلوبان', error: true);
      return;
    }
    setState(() => _saving = true);
    try {
      await ApiService.instance.createMasterDataEntry({
        'category': widget.category,
        'code': _code.text.trim(),
        'name_ar': _nameAr.text.trim(),
        if (_nameEn.text.trim().isNotEmpty) 'name_en': _nameEn.text.trim(),
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
      title: 'إدخال في ${kMasterCategories[widget.category] ?? ''}',
      saving: _saving,
      onSubmit: _submit,
      children: [
        kField(_code, 'الرمز'),
        kField(_nameAr, 'الاسم العربيّ'),
        kField(_nameEn, 'الاسم الإنجليزيّ (اختياري)'),
      ],
    );
  }
}
