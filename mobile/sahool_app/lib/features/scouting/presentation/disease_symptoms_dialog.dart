import 'package:flutter/material.dart';

import '../data/scouting_api.dart';
import '../data/scouting_models.dart';

/// Returns the inspector-approved note for the pin. The image stays on device.
class DiseaseSymptomsDialog extends StatefulWidget {
  const DiseaseSymptomsDialog({super.key, required this.api, required this.field});
  final ScoutingApi api;
  final ScoutingField field;

  @override
  State<DiseaseSymptomsDialog> createState() => _DiseaseSymptomsDialogState();
}

class _DiseaseSymptomsDialogState extends State<DiseaseSymptomsDialog> {
  late Future<List<Map<String, dynamic>>> catalog = widget.api.diagnosisSymptoms();
  final selected = <String, String>{};
  bool busy = false;
  String? result;
  String? error;

  Future<void> assess() async {
    setState(() { busy = true; error = null; });
    try {
      final response = await widget.api.assessSymptoms(widget.field, selected.keys.toList());
      final candidates = response['candidates'] as List;
      final names = candidates.whereType<Map>().map((item) => item['name_ar'])
          .whereType<String>().toList();
      final note = [
        'الأعراض المشاهدة: ${selected.values.join('، ')}.',
        if (names.isEmpty) 'لم تُطابق الأعراض قاعدة معروفة.'
        else 'اشتباه أولي بحسب الأعراض: ${names.join('، ')}.',
        if (response['next_step_ar'] is String) response['next_step_ar'] as String,
      ].join('\n');
      if (mounted) setState(() => result = note);
    } catch (_) {
      if (mounted) setState(() => error = 'تعذّر تحليل الأعراض. يمكنك إعادة المحاولة أو تسجيل ملاحظتك يدوياً.');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('فحص أعراض النبات'),
    content: SizedBox(
      width: 380,
      child: FutureBuilder<List<Map<String, dynamic>>>(
        future: catalog,
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return TextButton(onPressed: () => setState(() => catalog = widget.api.diagnosisSymptoms()),
                child: const Text('تعذّر تحميل الأعراض. إعادة المحاولة'));
          }
          if (!snapshot.hasData || busy) return const Center(child: CircularProgressIndicator());
          if (result != null) return SingleChildScrollView(child: SelectableText(result!));
          return ListView(shrinkWrap: true, children: [
            if (error != null) Text(error!),
            for (final item in snapshot.data!)
              CheckboxListTile(
                title: Text(item['name_ar'] as String),
                value: selected.containsKey(item['code']),
                onChanged: (on) => setState(() {
                  if (on == true) {
                    selected[item['code'] as String] = item['name_ar'] as String;
                  } else {
                    selected.remove(item['code']);
                  }
                }),
              ),
          ]);
        },
      ),
    ),
    actions: [
      TextButton(onPressed: () => Navigator.pop(context), child: const Text('إغلاق')),
      if (result == null)
        TextButton(onPressed: busy || selected.isEmpty ? null : assess, child: const Text('تحليل الأعراض'))
      else
        TextButton(onPressed: () => Navigator.pop(context, result), child: const Text('إضافة إلى الملاحظة')),
    ],
  );
}
