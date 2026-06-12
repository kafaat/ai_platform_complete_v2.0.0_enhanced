// SAHOOL — lib/screens/field_workspace_screen.dart
// «مساحة عمل الحقل» — المركز الموحّد الذي يُفتَح عند اختيار حقل. تبويبات:
// نظرة عامّة / موسم / أقمار / ريّ / أنشطة / تربة / طقس / خطّ زمنيّ.
// يستقبل وسيطاً عبر RouteSettings.arguments: إمّا خريطة بيانات الحقل (مفضَّل،
// من النظرة العامّة) أو معرّف الحقل (String) — فيُجلَب الحقل من getDashboard.
// صدق: التبويبات التي لا تتوفّر لها واجهة برمجيّة في ApiService تُعرَض كـ«غير
// متاح بعد» بدل اختلاق بيانات. تستعمل حالات العرض الموحّدة وRTL العربيّ.
import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../widgets/state_views.dart';
import '../widgets/workspace/workspace_sections.dart';

/// وسيط الانتقال إلى مساحة عمل الحقل: يقبل كائن الحقل أو معرّفه.
class FieldWorkspaceArgs {
  final String? fieldId;
  final Map<String, dynamic>? field;
  const FieldWorkspaceArgs({this.fieldId, this.field});
}

class FieldWorkspaceScreen extends StatefulWidget {
  /// اسم المسار المقصود.
  static const routeName = 'field_workspace';

  /// تمرير مباشر (إن لم يُستخدَم نظام المسارات): معرّف و/أو كائن الحقل.
  final String? fieldId;
  final Map<String, dynamic>? field;

  const FieldWorkspaceScreen({super.key, this.fieldId, this.field});

  @override
  State<FieldWorkspaceScreen> createState() => _FieldWorkspaceScreenState();
}

class _FieldWorkspaceScreenState extends State<FieldWorkspaceScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs = TabController(length: 8, vsync: this);

  bool _loading = true;
  String? _error;
  Map<String, dynamic> _field = const {};
  String _fieldId = '';
  bool _resolved = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // الوصول إلى ModalRoute.arguments آمن هنا (لا في initState). يُنفَّذ مرّة.
    if (_resolved) return;
    _resolved = true;
    _resolveArgs();
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  // حلّ الوسيط: من الـconstructor أوّلاً، ثمّ من RouteSettings.arguments.
  void _resolveArgs() {
    Map<String, dynamic>? field = widget.field;
    String? fieldId = widget.fieldId;

    final args = ModalRoute.of(context)?.settings.arguments;
    if (field == null && fieldId == null && args != null) {
      if (args is FieldWorkspaceArgs) {
        field = args.field;
        fieldId = args.fieldId;
      } else if (args is Map<String, dynamic>) {
        field = args;
      } else if (args is String) {
        fieldId = args;
      }
    }

    if (field != null && field.isNotEmpty) {
      _field = field;
      _fieldId =
          (field['field_id'] ?? field['id'] ?? fieldId ?? '').toString();
      _loading = false;
      return;
    }
    // لا كائن حقل — نملك معرّفاً فقط، فنجلب الحقل من النظرة العامّة.
    _fieldId = (fieldId ?? '').toString();
    _fetchField();
  }

  Future<void> _fetchField() async {
    if (_fieldId.isEmpty) {
      setState(() {
        _loading = false;
        _error = 'لم يُحدَّد الحقل.';
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await ApiService.instance.getDashboard();
      final raw =
          data['fields'] ?? data['fields_summary'] ?? data['field_list'];
      final fields = raw is List
          ? raw.whereType<Map>().map((e) => e.cast<String, dynamic>()).toList()
          : const <Map<String, dynamic>>[];
      Map<String, dynamic> match = const {};
      for (final f in fields) {
        final id = (f['field_id'] ?? f['id'] ?? '').toString();
        if (id == _fieldId) {
          match = f;
          break;
        }
      }
      if (!mounted) return;
      setState(() {
        _field = match;
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
    final title = _field.isEmpty
        ? 'مساحة عمل الحقل'
        : wText(_field['field_name'] ?? _field['name'], 'مساحة عمل الحقل');

    return Scaffold(
      backgroundColor: kBg,
      appBar: AppBar(
        backgroundColor: kSurface,
        title: Text(title),
        bottom: TabBar(
          controller: _tabs,
          isScrollable: true,
          indicatorColor: kPrimary,
          labelColor: Colors.white,
          unselectedLabelColor: Colors.grey,
          tabs: const [
            Tab(text: 'نظرة عامّة'),
            Tab(text: 'الموسم'),
            Tab(text: 'الأقمار'),
            Tab(text: 'الريّ'),
            Tab(text: 'الأنشطة'),
            Tab(text: 'التربة'),
            Tab(text: 'الطقس'),
            Tab(text: 'الخطّ الزمنيّ'),
          ],
        ),
      ),
      body: _loading
          ? const LoadingView()
          : _error != null
              ? ErrorView(message: _error!, onRetry: _fetchField)
              : TabBarView(
                  controller: _tabs,
                  children: [
                    // نظرة عامّة — من بيانات الحقل (متاح).
                    WOverviewSection(field: _field),
                    // الموسم — لا واجهة seasons في ApiService بعد ⇒ placeholder.
                    const WUnavailableSection(
                      title: 'الموسم الحاليّ والتاريخ',
                      icon: Icons.calendar_month,
                      note:
                          'سيُعرَض الموسم النشط وسجلّ المواسم عند ربط واجهة المواسم بالخادم.',
                    ),
                    // الأقمار/NDVI — getFieldIndicators (متاح).
                    _fieldId.isEmpty
                        ? const WUnavailableSection(
                            title: 'مؤشّرات الأقمار',
                            icon: Icons.satellite_alt,
                            note: 'لا يتوفّر معرّف الحقل لجلب المؤشّرات.',
                          )
                        : WSatelliteSection(fieldId: _fieldId),
                    // الريّ — معلومات الحقل + listSchedules(fieldId) (متاح).
                    WIrrigationSection(fieldId: _fieldId, field: _field),
                    // الأنشطة — لا واجهة activities في ApiService بعد ⇒ placeholder.
                    const WUnavailableSection(
                      title: 'أنشطة الحقل',
                      icon: Icons.assignment,
                      note:
                          'ستُعرَض قائمة العمليّات الزراعيّة عند ربط واجهة الأنشطة بالخادم.',
                    ),
                    // التربة — نوع التربة + كيمياء إن أرسلها الخادم (متاح جزئيّاً).
                    WSoilSection(field: _field),
                    // الطقس — لا واجهة weather في ApiService بعد ⇒ placeholder.
                    const WUnavailableSection(
                      title: 'الطقس والإرشاد',
                      icon: Icons.cloud,
                      note:
                          'ستُعرَض الحالة الجوّيّة والتوصيات عند ربط واجهة الطقس بالخادم.',
                    ),
                    // الخطّ الزمنيّ — يعتمد على الأنشطة/الأحداث (غير متاح بعد).
                    const WUnavailableSection(
                      title: 'الخطّ الزمنيّ',
                      icon: Icons.timeline,
                      note:
                          'سيُعرَض تسلسل الأحداث والأنشطة زمنيّاً عند توفّر واجهة الأحداث.',
                    ),
                  ],
                ),
    );
  }
}
