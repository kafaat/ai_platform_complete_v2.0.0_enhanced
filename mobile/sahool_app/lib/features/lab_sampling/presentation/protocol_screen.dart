// SAHOOL — features/lab_sampling/presentation/protocol_screen.dart
// إرشادات أخذ عيّنة التربة كما يقدّمها الخادم (GET /soil-sampling/protocol):
// عدد العيّنات الفرعيّة لمساحة الحقل، العمق حسب الغرض، الخطوات، ما يُتجنَّب،
// التوقيت. كلّ النصوص من الخادم؛ لا بروتوكول مكتوب في التطبيق.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/lab_sampling_api.dart';

List<String> _strings(Object? v) =>
    v is List ? v.map((e) => e.toString()).toList() : const [];

/// يستخرج «15-30 سم» من نصّ عمق الخادم إن بدأ بمدى صريح؛ غيره ⇒ null (لا تخمين).
(int, int)? parseDepthRangeCm(String? depthAr) {
  if (depthAr == null) return null;
  final m = RegExp(r'^\s*(\d+)\s*-\s*(\d+)\s*سم').firstMatch(depthAr);
  if (m == null) return null;
  final a = int.parse(m.group(1)!), b = int.parse(m.group(2)!);
  return b > a ? (a, b) : null;
}

class ProtocolScreen extends StatefulWidget {
  const ProtocolScreen({super.key, this.areaHa, this.api});
  final double? areaHa;
  final LabSamplingApi? api;

  @override
  State<ProtocolScreen> createState() => _ProtocolScreenState();
}

class _ProtocolScreenState extends State<ProtocolScreen> {
  String _purpose = 'general';
  late Future<Map<String, dynamic>> _future;
  Map<String, String> _purposes = const {};

  LabSamplingApi get _api => widget.api ?? LabSamplingApi.instance;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() async {
    final p = await _api.getProtocol(areaHa: widget.areaHa, purpose: _purpose);
    final depth = p['depth'];
    if (depth is Map && depth['all_purposes_ar'] is List) {
      final m = <String, String>{};
      for (final e in depth['all_purposes_ar'] as List) {
        if (e is Map && e['purpose'] != null) {
          m[e['purpose'].toString()] =
              '${e['for_ar'] ?? e['purpose']} (${e['depth_ar'] ?? ''})';
        }
      }
      if (mounted && m.isNotEmpty) setState(() => _purposes = m);
    }
    return p;
  }

  @override
  Widget build(BuildContext context) => AppScaffold(
    title: 'إرشادات أخذ العيّنة',
    body: FutureBuilder<Map<String, dynamic>>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const LoadingState();
        }
        if (snap.hasError) {
          return ErrorState(
            error: ApiException.from(snap.error!),
            onRetry: () => setState(() => _future = _load()),
          );
        }
        return _body(context, snap.data!);
      },
    ),
  );

  Widget _section(
    BuildContext context,
    String title,
    IconData icon,
    List<String> lines,
  ) => Padding(
    padding: const EdgeInsetsDirectional.only(bottom: SahoolSpacing.md),
    child: SectionCard(
      title: title,
      icon: icon,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final l in lines)
            Padding(
              padding: const EdgeInsetsDirectional.only(
                bottom: SahoolSpacing.xs,
              ),
              child: Text(l, style: context.textStyles.bodyLarge),
            ),
        ],
      ),
    ),
  );

  Widget _body(BuildContext context, Map<String, dynamic> p) {
    final depth = p['depth'] is Map ? p['depth'] as Map : const {};
    final sub = p['subsamples'] is Map ? p['subsamples'] as Map : const {};
    return ListView(
      padding: const EdgeInsets.all(SahoolSpacing.page),
      children: [
        if (_purposes.isNotEmpty)
          AppDropdown<String>(
            label: 'غرض العيّنة',
            items: _purposes,
            value: _purposes.containsKey(_purpose) ? _purpose : null,
            onChanged: (v) {
              if (v == null || v == _purpose) return;
              setState(() {
                _purpose = v;
                _future = _load();
              });
            },
          ),
        const SizedBox(height: SahoolSpacing.md),
        _section(context, 'العمق', Icons.straighten, [
          if (depth['depth_ar'] != null) '${depth['depth_ar']}',
          if (depth['applies_to_ar'] != null) '${depth['applies_to_ar']}',
          if (depth['principle_ar'] != null) '${depth['principle_ar']}',
        ]),
        if (sub['supported'] == true)
          _section(context, 'العيّنات الفرعيّة', Icons.scatter_plot_outlined, [
            if (sub['advice_ar'] != null) '${sub['advice_ar']}',
            if (sub['note_ar'] != null) '${sub['note_ar']}',
          ])
        else if (sub['message_ar'] != null)
          _section(context, 'العيّنات الفرعيّة', Icons.scatter_plot_outlined, [
            '${sub['message_ar']}',
          ]),
        if (_strings(p['steps_ar']).isNotEmpty)
          _section(
            context,
            'الخطوات',
            Icons.format_list_numbered,
            _strings(p['steps_ar']),
          ),
        if (_strings(p['avoid_ar']).isNotEmpty)
          _section(
            context,
            'تجنّب',
            Icons.do_not_disturb_on_outlined,
            _strings(p['avoid_ar']),
          ),
        if (p['timing_ar'] != null)
          _section(context, 'التوقيت', Icons.schedule, ['${p['timing_ar']}']),
        if (p['yemen_note_ar'] != null)
          _section(context, 'لماذا يهمّ', Icons.lightbulb_outline, [
            '${p['yemen_note_ar']}',
          ]),
        if (p['disclaimer_ar'] != null)
          Text(
            '${p['disclaimer_ar']}',
            style: context.textStyles.bodySmall?.copyWith(
              color: context.tokens.muted,
            ),
          ),
      ],
    );
  }
}
