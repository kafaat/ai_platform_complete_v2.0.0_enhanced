// SAHOOL — lib/screens/field_workspace_screen.dart
// «مساحة عمل الحقل» — المركز الذي يُفتَح عند اختيار حقل. خمسة تبويبات (كانت
// تسعة): نظرة عامّة · الموسم · المراقبة · العمليّات · التربة. النظرة العامّة
// أوّلاً، وكلّ تبويب يبقى حيّاً عند التنقّل (لا إعادة جلب).
//
// الوسيط عبر RouteSettings.arguments: خريطة الحقل (مفضَّل، من القائمة) أو
// معرّفه (String) أو FieldWorkspaceArgs؛ أو field_id من الرابط العميق. بمعرّف
// فقط يُجلب الحقل من GET /api/v1/fields/{id} (لا لوحة المؤشّرات كاملةً).
// المسار مُثبَّت: اختبارات CI خارج التطبيق تقرأ هذا الملفّ.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/fields/presentation/common/field_labels.dart';
import 'package:sahool_app/features/fields/presentation/workspace/workspace_sections.dart';

import '../features/field_forms/data/field_forms_coordinator.dart';
import '../features/field_forms/presentation/field_forms_list_screen.dart';
import '../features/realtime/realtime_screen.dart';

/// وسيط الانتقال إلى مساحة عمل الحقل: يقبل كائن الحقل أو معرّفه.
class FieldWorkspaceArgs {
  final String? fieldId;
  final Map<String, dynamic>? field;
  const FieldWorkspaceArgs({this.fieldId, this.field});
}

/// تبويبات مساحة العمل بترتيبها.
const List<String> kWorkspaceTabs = [
  'نظرة عامّة',
  'الموسم',
  'المراقبة',
  'العمليّات',
  'التربة',
];

class FieldWorkspaceScreen extends StatefulWidget {
  /// اسم المسار القديم (بديل لـ/fields/workspace).
  static const routeName = 'field_workspace';

  /// تمرير مباشر (إن لم يُستخدَم نظام المسارات): معرّف و/أو كائن الحقل.
  final String? fieldId;
  final Map<String, dynamic>? field;

  /// واجهات البرمجة (للاختبار)؛ افتراضيّاً الحقيقيّة.
  final WorkspaceDeps? deps;

  /// الدور (للاختبار)؛ افتراضيّاً من الجلسة.
  final AppRole? role;

  const FieldWorkspaceScreen({
    super.key,
    this.fieldId,
    this.field,
    this.deps,
    this.role,
  });

  @override
  State<FieldWorkspaceScreen> createState() => _FieldWorkspaceScreenState();
}

class _FieldWorkspaceScreenState extends State<FieldWorkspaceScreen> {
  late final WorkspaceDeps _deps = widget.deps ?? WorkspaceDeps();
  SeasonWorkspaceCubit? _season;

  bool _loading = true;
  ApiException? _error;
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
    _season?.close();
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
      } else if (args is Map) {
        field = args.cast<String, dynamic>();
      } else if (args is String) {
        fieldId = args;
      }
    }

    if (field != null && field.isNotEmpty) {
      _field = field;
      _fieldId = fieldIdOf(field).isNotEmpty
          ? fieldIdOf(field)
          : (fieldId ?? '');
      _ready();
      return;
    }
    // لا كائن حقل — نملك معرّفاً فقط، فنجلب تفاصيله.
    _fieldId = fieldId ?? '';
    _fetchField();
  }

  void _ready() {
    _loading = false;
    if (_fieldId.isEmpty) return;
    _season ??= SeasonWorkspaceCubit(_deps, _fieldId)..load();
    unawaited(FieldFormsCoordinator.instance.syncField(_fieldId));
  }

  Future<void> _fetchField() async {
    if (_fieldId.isEmpty) {
      setState(() {
        _loading = false;
        _error = const ApiException(
          kind: ApiErrorKind.notFound,
          messageAr: 'لم يُحدَّد الحقل.',
        );
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final field = await _deps.fields.getField(_fieldId);
      if (!mounted) return;
      setState(() {
        _field = field;
        _ready();
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = ApiException.from(e);
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final title = _field.isEmpty
        ? 'مساحة عمل الحقل'
        : fieldNameOf(_field, 'مساحة عمل الحقل');
    final ready = !_loading && _error == null && _fieldId.isNotEmpty;
    final role = widget.role ?? normalizeRole(currentRole());

    return DefaultTabController(
      length: kWorkspaceTabs.length,
      child: Scaffold(
        appBar: AppBar(
          // اسم الحقل الطويل يُختصر في سطر واحد بدل أن يفيض.
          title: Text(title, maxLines: 1, overflow: TextOverflow.ellipsis),
          actions: [
            // النماذج الميدانيّة المنزَّلة لهذا الحقل (offline-first).
            if (ready) FieldFormsEntryButton(fieldId: _fieldId),
            if (nativeRealtimeCallsEnabled && ready)
              AppIconButton(
                icon: Icons.mic_none_rounded,
                tooltip: 'استشارة صوتيّة',
                onPressed: () => Navigator.of(context).push<void>(
                  MaterialPageRoute(
                    builder: (_) => RealtimeScreen(fieldId: _fieldId),
                  ),
                ),
              ),
          ],
          bottom: ready
              ? TabBar(
                  key: const ValueKey('workspace_tabs'),
                  isScrollable: true,
                  tabAlignment: TabAlignment.start,
                  tabs: [for (final t in kWorkspaceTabs) Tab(text: t)],
                )
              : null,
        ),
        body: _loading
            ? const LoadingState(message: 'جارٍ تحميل الحقل')
            : _error != null
            ? ErrorState(error: _error!, onRetry: _fetchField)
            : _fieldId.isEmpty
            ? const WUnavailableSection(
                title: 'مساحة عمل الحقل',
                icon: Icons.grass_outlined,
                note: 'لا يتوفّر معرّف الحقل لجلب بياناته.',
              )
            : RepositoryProvider<WorkspaceDeps>.value(
                value: _deps,
                child: BlocProvider<SeasonWorkspaceCubit>.value(
                  value: _season!,
                  child: TabBarView(
                    children: [
                      KeepAliveTab(
                        child: WOverviewSection(
                          fieldId: _fieldId,
                          field: _field,
                          role: role,
                        ),
                      ),
                      KeepAliveTab(child: WSeasonSection(fieldId: _fieldId)),
                      KeepAliveTab(
                        child: WMonitoringSection(fieldId: _fieldId),
                      ),
                      KeepAliveTab(
                        child: WOperationsSection(
                          fieldId: _fieldId,
                          field: _field,
                          role: role,
                        ),
                      ),
                      KeepAliveTab(
                        child: WSoilSection(fieldId: _fieldId, field: _field),
                      ),
                    ],
                  ),
                ),
              ),
      ),
    );
  }
}
