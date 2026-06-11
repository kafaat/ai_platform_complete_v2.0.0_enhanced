// SAHOOL — lib/screens/documents_screen.dart
// الوثائق: سجلّ بيانات وصفيّة (عقود/تقارير/صور/خرائط/نتائج مخبريّة) عبر
// /api/v1/documents. إدارة فقط (owner/manager): التسجيل محكوم بـcanManage.
// صدق مهمّ: هذا سجلّ metadata فقط — الملفّ الفعليّ في تخزين الكائنات وstorage_ref
// مسار/رابط له؛ النموذج يُسجّل مرجعاً ولا يرفع ملفّاً. تطابق DocumentsPage.
import 'package:flutter/material.dart';
import '../permissions.dart';
import '../services/api_service.dart';
import '../widgets/form_kit.dart';
import '../widgets/state_views.dart';

const Map<String, String> kDocCategories = {
  'contract': 'عقد',
  'report': 'تقرير',
  'image': 'صورة',
  'map': 'خريطة',
  'lab_result': 'نتيجة مخبريّة',
  'other': 'أخرى',
};

class DocumentsScreen extends StatefulWidget {
  const DocumentsScreen({super.key});
  @override
  State<DocumentsScreen> createState() => _DocumentsScreenState();
}

class _DocumentsScreenState extends State<DocumentsScreen> {
  bool _loading = true;
  String? _error;
  String? _filter; // null = الكلّ
  List<Map<String, dynamic>> _docs = const [];

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
      final data = await ApiService.instance.listDocuments(category: _filter);
      if (!mounted) return;
      setState(() {
        _docs = data;
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

  IconData _icon(String cat) {
    switch (cat) {
      case 'contract':
        return Icons.description_outlined;
      case 'report':
        return Icons.bar_chart;
      case 'image':
        return Icons.image_outlined;
      case 'map':
        return Icons.map_outlined;
      case 'lab_result':
        return Icons.science_outlined;
      default:
        return Icons.insert_drive_file_outlined;
    }
  }

  @override
  Widget build(BuildContext context) {
    final manageable = canManage(currentRole());
    return Scaffold(
      backgroundColor: kBg,
      appBar: AppBar(
        backgroundColor: kSurface,
        title: const Text('الوثائق'),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
        ],
      ),
      floatingActionButton: manageable
          ? FloatingActionButton.extended(
              backgroundColor: kPrimary,
              onPressed: _openRegister,
              icon: const Icon(Icons.add),
              label: const Text('تسجيل وثيقة'),
            )
          : null,
      body: Column(
        children: [
          const InfoBanner(
            text:
                'سجلّ بيانات وصفيّة فقط — الملفّ الفعليّ في تخزين الكائنات، وهذا النموذج يسجّل مرجعاً (storage_ref) لا يرفع ملفّاً.',
            color: kSecondary,
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: DropdownButtonFormField<String?>(
              value: _filter,
              dropdownColor: kSurface,
              decoration: kDec('التصفية بالفئة'),
              style: const TextStyle(color: Colors.white),
              items: [
                const DropdownMenuItem<String?>(
                    value: null, child: Text('الكلّ')),
                ...kDocCategories.entries.map(
                  (e) => DropdownMenuItem<String?>(
                      value: e.key, child: Text(e.value)),
                ),
              ],
              onChanged: (v) {
                setState(() => _filter = v);
                _load();
              },
            ),
          ),
          Expanded(
            child: _loading
                ? const LoadingView()
                : _error != null
                    ? ErrorView(message: _error!, onRetry: _load)
                    : _docs.isEmpty
                        ? const EmptyView(message: 'لا وثائق مسجّلة')
                        : RefreshIndicator(
                            onRefresh: _load,
                            child: ListView.builder(
                              padding: const EdgeInsets.all(12),
                              itemCount: _docs.length,
                              itemBuilder: (_, i) {
                                final d = _docs[i];
                                final cat = (d['category'] ?? 'other').toString();
                                return Container(
                                  margin: const EdgeInsets.only(bottom: 8),
                                  padding: const EdgeInsets.all(12),
                                  decoration: BoxDecoration(
                                    color: kSurface,
                                    borderRadius: BorderRadius.circular(10),
                                  ),
                                  child: Row(
                                    children: [
                                      Icon(_icon(cat),
                                          color: kSecondary, size: 22),
                                      const SizedBox(width: 12),
                                      Expanded(
                                        child: Column(
                                          crossAxisAlignment:
                                              CrossAxisAlignment.start,
                                          children: [
                                            Text('${d['title'] ?? '—'}',
                                                style: const TextStyle(
                                                    color: Colors.white,
                                                    fontWeight:
                                                        FontWeight.bold)),
                                            const SizedBox(height: 2),
                                            Text(
                                              '${kDocCategories[cat] ?? cat} · إصدار ${d['version'] ?? 1}',
                                              style: const TextStyle(
                                                  color: Colors.grey,
                                                  fontSize: 12),
                                            ),
                                          ],
                                        ),
                                      ),
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

  void _openRegister() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: kSurface,
      isScrollControlled: true,
      builder: (_) => _RegisterDocSheet(onDone: _load),
    );
  }
}

class _RegisterDocSheet extends StatefulWidget {
  final Future<void> Function() onDone;
  const _RegisterDocSheet({required this.onDone});
  @override
  State<_RegisterDocSheet> createState() => _RegisterDocSheetState();
}

class _RegisterDocSheetState extends State<_RegisterDocSheet> {
  final _title = TextEditingController();
  final _storageRef = TextEditingController();
  final _contentType = TextEditingController();
  String _category = 'report';
  bool _saving = false;

  @override
  void dispose() {
    _title.dispose();
    _storageRef.dispose();
    _contentType.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_title.text.trim().isEmpty) {
      showSnack(context, 'العنوان مطلوب', error: true);
      return;
    }
    setState(() => _saving = true);
    try {
      await ApiService.instance.createDocument({
        'category': _category,
        'title': _title.text.trim(),
        if (_storageRef.text.trim().isNotEmpty)
          'storage_ref': _storageRef.text.trim(),
        if (_contentType.text.trim().isNotEmpty)
          'content_type': _contentType.text.trim(),
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
      title: 'تسجيل وثيقة (مرجع)',
      saving: _saving,
      onSubmit: _submit,
      children: [
        DropdownButtonFormField<String>(
          value: _category,
          dropdownColor: kSurface,
          decoration: kDec('الفئة'),
          style: const TextStyle(color: Colors.white),
          items: kDocCategories.entries
              .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
              .toList(),
          onChanged: (v) => setState(() => _category = v ?? 'other'),
        ),
        kField(_title, 'العنوان'),
        kField(_storageRef, 'مرجع التخزين storage_ref (مسار/رابط)'),
        kField(_contentType, 'نوع المحتوى مثل application/pdf (اختياري)'),
      ],
    );
  }
}
