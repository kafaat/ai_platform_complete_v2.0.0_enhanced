// SAHOOL — lib/widgets/form_kit.dart
// عناصر نموذج موحّدة (حقل نصّ، قائمة منسدلة، غلاف ورقة سفليّة بزرّ حفظ) تُشارَك
// بين شاشات العمليّات الستّ لضمان اتّساق مظهر/سلوك واحد. عامّة (public) ليُعاد
// استخدامها عبر الملفّات (الخاصّ بـ_ محصور بمكتبته).
import 'package:flutter/material.dart';
import 'state_views.dart';

InputDecoration kDec(String label) => InputDecoration(
      labelText: label,
      labelStyle: const TextStyle(color: Colors.grey),
      enabledBorder: const OutlineInputBorder(
        borderSide: BorderSide(color: Colors.white24),
      ),
      focusedBorder: const OutlineInputBorder(
        borderSide: BorderSide(color: kPrimary),
      ),
    );

Widget kField(TextEditingController c, String label, {bool number = false}) =>
    Padding(
      padding: const EdgeInsets.only(top: 12),
      child: TextField(
        controller: c,
        keyboardType: number
            ? const TextInputType.numberWithOptions(decimal: true)
            : TextInputType.text,
        style: const TextStyle(color: Colors.white),
        decoration: kDec(label),
      ),
    );

class SheetScaffold extends StatelessWidget {
  final String title;
  final bool saving;
  final VoidCallback onSubmit;
  final List<Widget> children;
  const SheetScaffold({
    super.key,
    required this.title,
    required this.saving,
    required this.onSubmit,
    required this.children,
  });
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 16,
        right: 16,
        top: 16,
        bottom: MediaQuery.of(context).viewInsets.bottom + 16,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(title,
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.bold)),
            ...children,
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: saving ? null : onSubmit,
              style: ElevatedButton.styleFrom(backgroundColor: kPrimary),
              child: saving
                  ? const SizedBox(
                      height: 18,
                      width: 18,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : const Text('حفظ'),
            ),
          ],
        ),
      ),
    );
  }
}

/// عنوان قسم موحّد داخل القوائم.
class SectionTitle extends StatelessWidget {
  final String text;
  const SectionTitle(this.text, {super.key});
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 8, top: 4),
        child: Text(text,
            style: const TextStyle(
                color: Colors.white70, fontWeight: FontWeight.bold)),
      );
}
