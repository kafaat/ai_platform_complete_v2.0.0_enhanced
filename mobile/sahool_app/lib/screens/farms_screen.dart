// SAHOOL — lib/screens/farms_screen.dart
// إدارة المزارع (أب الحقول — هرميّة المزرعة→الحقل)، عبر /api/v1/farms (قائمة +
// إنشاء). مُقيَّد بالدور (farm:create للإنشاء — viewer قراءة فقط). صدق: لا مزارع
// مُلفَّقة — القائمة من الخادم، والتعذّر يُعرَض بحالة خطأ بإعادة محاولة، والفارغ
// بحالة قابلة للفعل. تطابق FarmsPage في الويب (farmsApi). نمط شاشات العمليّات.
import 'package:flutter/material.dart';
import '../permissions.dart';
import '../services/api_service.dart';
import '../widgets/form_kit.dart';
import '../widgets/state_views.dart';

class FarmsScreen extends StatefulWidget {
  const FarmsScreen({super.key});
  @override
  State<FarmsScreen> createState() => _FarmsScreenState();
}

class _FarmsScreenState extends State<FarmsScreen> {
  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _farms = const [];

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
      final farms = await ApiService.instance.listFarms();
      if (!mounted) return;
      setState(() {
        _farms = farms;
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

  void _openCreate() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: kSurface,
      isScrollControlled: true,
      builder: (_) => _AddFarmSheet(onDone: _load),
    );
  }

  double? _num(dynamic v) => v is num ? v.toDouble() : double.tryParse('$v');

  @override
  Widget build(BuildContext context) {
    final mutable = canMutate(currentRole());
    return Scaffold(
      backgroundColor: kBg,
      appBar: AppBar(
        backgroundColor: kSurface,
        title: const Text('المزارع'),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
        ],
      ),
      floatingActionButton: (mutable && !_loading && _error == null)
          ? FloatingActionButton.extended(
              backgroundColor: kPrimary,
              onPressed: _openCreate,
              icon: const Icon(Icons.add),
              label: const Text('مزرعة'),
            )
          : null,
      body: _loading
          ? const LoadingView()
          : _error != null
              ? ErrorView(message: _error!, onRetry: _load)
              : _farms.isEmpty
                  ? EmptyView(
                      message: 'لا مزارع بعد — أنشئ مزرعتك الأولى',
                      icon: Icons.agriculture_outlined,
                      actionLabel: mutable ? 'إنشاء مزرعة' : null,
                      onAction: mutable ? _openCreate : null,
                    )
                  : RefreshIndicator(
                      onRefresh: _load,
                      child: ListView.builder(
                        padding: const EdgeInsets.fromLTRB(12, 12, 12, 80),
                        itemCount: _farms.length,
                        itemBuilder: (_, i) => _farmCard(_farms[i]),
                      ),
                    ),
    );
  }

  Widget _farmCard(Map<String, dynamic> f) {
    final name = (f['name'] ?? '—').toString();
    final region = (f['region'] ?? f['location'] ?? '').toString();
    final area = _num(f['area_ha']);
    final subtitle = [
      if (region.isNotEmpty) region,
      if (area != null) '${area.toStringAsFixed(1)} هـ',
    ].join(' · ');
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: kSurface,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: kPrimary.withOpacity(0.15),
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Icon(Icons.agriculture_outlined, color: kPrimary),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name,
                    style: const TextStyle(
                        color: Colors.white, fontWeight: FontWeight.bold)),
                if (subtitle.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(subtitle,
                      style:
                          const TextStyle(color: Colors.grey, fontSize: 12)),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _AddFarmSheet extends StatefulWidget {
  final Future<void> Function() onDone;
  const _AddFarmSheet({required this.onDone});
  @override
  State<_AddFarmSheet> createState() => _AddFarmSheetState();
}

class _AddFarmSheetState extends State<_AddFarmSheet> {
  final _name = TextEditingController();
  final _region = TextEditingController();
  final _area = TextEditingController();
  bool _saving = false;

  @override
  void dispose() {
    _name.dispose();
    _region.dispose();
    _area.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_name.text.trim().isEmpty) {
      showSnack(context, 'الاسم مطلوب', error: true);
      return;
    }
    setState(() => _saving = true);
    try {
      await ApiService.instance.createFarm({
        'name': _name.text.trim(),
        if (_region.text.trim().isNotEmpty) 'region': _region.text.trim(),
        if (_area.text.trim().isNotEmpty)
          'area_ha': double.tryParse(_area.text.trim()),
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
      title: 'مزرعة جديدة',
      saving: _saving,
      onSubmit: _submit,
      children: [
        kField(_name, 'الاسم'),
        kField(_region, 'المنطقة (اختياري)'),
        kField(_area, 'المساحة (هكتار) اختياري', number: true),
      ],
    );
  }
}
