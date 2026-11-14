import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/response_shape.dart';
import '../data/field_task.dart';

class InspectionReviewPanel extends StatefulWidget {
  const InspectionReviewPanel({super.key, required this.task});
  final FieldTask task;
  @override
  State<InspectionReviewPanel> createState() => _InspectionReviewPanelState();
}

class _InspectionReviewPanelState extends State<InspectionReviewPanel> {
  final note = TextEditingController();
  Map<String, dynamic>? history;
  bool busy = false;
  String? error;
  // field-management-service owns the hand-off (gateway /api/v1/field-tasks/ -> /internal/field-tasks/).
  String get path => '/api/v1/field-tasks/fields/${Uri.encodeComponent(widget.task.fieldId)}'
      '/tasks/${Uri.encodeComponent(widget.task.id)}/handoff';
  static const labels = {'accept':'قبول التكليف','submit':'رفع النتيجة للمراجعة',
    'return':'إعادة للاستكمال','approve':'اعتماد النتيجة','reassign':'إعادة إسناد','reopen':'إعادة فتح الزيارة'};

  @override
  void initState() { super.initState(); update(); }
  @override
  void dispose() { note.dispose(); super.dispose(); }

  Future<void> update([String? action]) async {
    if (busy) return;
    setState(() { busy = true; error = null; });
    try {
      final api = ApiClient.instance;
      final state = history;
      final events = (state?['events'] as List? ?? []).whereType<Map>().toList();
      // A review names the exact submitted evidence version (v274); a submit names the photo
      // record it shows, so a photo that changed meanwhile is refused instead of approved.
      final submitted = events.isEmpty ? null : events.last['evidence_version'];
      final current = state?['current_evidence'];
      final photo = current is Map ? current['photo_evidence_id'] : null;
      final response = action == null ? await api.get(path) :
          await api.post(action == 'accept' ? '$path/accept' : '$path/finding', data: {
            'expected_revision':state!['revision'],
            if (action != 'accept') ...{'action':action,'reason':note.text.trim()},
            if (action == 'submit' && photo != null) 'photo_evidence_id':photo,
            if (action == 'approve' || action == 'return') 'evidence_version':submitted,
          });
      if (!mounted) return;
      history = asJsonMap(response);
      if (action != null) note.clear();
    } catch (_) {
      if (!mounted) return;
      history = null;
      error = 'تعذّر تأكيد سجل الزيارة. حدّث السجل قبل إعادة المحاولة.';
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  static String evidenceLine(String label, Map item) {
    final sha = '${item['photo_content_sha256'] ?? ''}';
    return [
      '$label ${item['version'] ?? ''}'.trim(),
      item['photo_evidence_id'] != null
          ? 'صورة الدبوس ${sha.length > 12 ? sha.substring(0, 12) : sha}'
          : 'بلا صورة',
      if (item['notes'] != null) '${item['notes']}',
    ].join(' · ');
  }

  @override
  Widget build(BuildContext context) {
    final state = history;
    final approved = state?['approved_evidence'];
    final current = state?['current_evidence'];
    final actions = [
      if (state?['can_accept'] == true) 'accept',
      if (state?['can_submit'] == true) 'submit',
      if (state?['can_review'] == true) ...['approve','return'],
    ];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('نتيجة التفتيش وسجل المراجعة'),
      // v274: the approved version stays readable; a later photo record waits for review.
      if (approved is Map) Text(evidenceLine('النسخة المعتمدة', approved)),
      if (approved is Map && current is Map && current['version'] != approved['version'])
        Text(evidenceLine('نسخة بانتظار المراجعة', current)),
      if (approved is Map && state?['evidence_pending_review'] == true)
        const Text('تغيرت صورة الدبوس بعد الاعتماد. لا تُغلق الزيارة قبل اعتماد النسخة الجديدة'),
      for (final event in (state?['events'] as List? ?? []).whereType<Map>())
        Text('${labels[event['action']] ?? ''} · ${event['actor']} · ${event['reason'] ?? ''}'),
      if (error != null) Text(error!),
      if (actions.any((a) => a != 'accept'))
        TextField(controller:note, maxLength:2000, minLines:2, maxLines:5,
            onChanged: (_) => setState(() {}), decoration:const InputDecoration(labelText:'نتيجة التفتيش أو تعليق المراجع')),
      for (final action in actions)
        TextButton(onPressed:busy || (action != 'accept' && note.text.trim().isEmpty)
            ? null : () => update(action), child:Text(labels[action]!)),
      TextButton(onPressed:busy ? null : () => update(), child:const Text('تحديث سجل التفتيش')),
    ]);
  }
}
