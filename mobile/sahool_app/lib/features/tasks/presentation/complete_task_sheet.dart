// SAHOOL — features/tasks/presentation/complete_task_sheet.dart
// ورقة إنجاز مهمّة (أو إضافة ملاحظة): ملاحظة اختياريّة + صورة محلّيّة اختياريّة.
//
// * الزرّ يُعطَّل أثناء الإرسال (لا إرسال مزدوج)، والخطأ يُعرَض داخل الورقة
//   لأنّ SnackBar يُرسَم تحتها. الورقة تبقى مفتوحة عند الفشل فيعيد المستخدم
//   المحاولة بالمفتاح نفسه (يحمله الـcubit).
// * الصورة تُحفَظ على الجهاز فقط بعد نجاح الإجراء أو إيداعه، مع تنبيه صريح
//   بأنّ رفع الصور غير متاح في الخادم.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/tasks/data/field_task.dart';
import 'package:sahool_app/features/tasks/data/offline_write.dart';
import 'package:sahool_app/features/tasks/data/task_photo_store.dart';

/// يلتقط صورة ويُعيد مسارها (null إن ألغى المستخدم).
typedef PhotoPicker = Future<String?> Function();

Future<String?> cameraPhotoPicker() async {
  final x = await ImagePicker().pickImage(
    source: ImageSource.camera,
    imageQuality: 70,
    maxWidth: 1600,
  );
  return x?.path;
}

class CompleteTaskSheet extends StatefulWidget {
  const CompleteTaskSheet({
    super.key,
    required this.title,
    required this.submitLabel,
    required this.onSubmit,
    this.noteRequired = false,
    this.existingNotes,
    this.pickPhoto,
    this.savePhoto,
  });

  final String title;
  final String submitLabel;

  /// يُرسِل الإجراء بالملاحظة. null ⇒ تُجوهل (كتابة جارية على المهمّة).
  final Future<WriteOutcome<FieldTask>?> Function(String note) onSubmit;
  final bool noteRequired;
  final String? existingNotes;

  /// null ⇒ لا زرّ صورة.
  final PhotoPicker? pickPhoto;
  final Future<void> Function(String path)? savePhoto;

  @override
  State<CompleteTaskSheet> createState() => _CompleteTaskSheetState();
}

class _CompleteTaskSheetState extends State<CompleteTaskSheet> {
  final _note = TextEditingController();
  String? _photoPath;
  bool _submitting = false;
  String? _error;
  String? _noteError;

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  Future<void> _takePhoto() async {
    final pick = widget.pickPhoto;
    if (pick == null) return;
    try {
      final path = await pick();
      if (!mounted || path == null) return;
      setState(() => _photoPath = path);
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = 'تعذّر فتح الكاميرا على هذا الجهاز.');
    }
  }

  Future<void> _submit() async {
    if (_submitting) return;
    final note = _note.text.trim();
    if (widget.noteRequired && note.isEmpty) {
      setState(() => _noteError = 'اكتب الملاحظة أوّلاً');
      return;
    }
    if (note.length > 2000) {
      setState(() => _noteError = 'الملاحظة أطول من 2000 حرف');
      return;
    }
    setState(() {
      _submitting = true;
      _error = null;
      _noteError = null;
    });
    final outcome = await widget.onSubmit(note);
    if (!mounted) return;
    if (outcome == null) {
      setState(() => _submitting = false);
      return;
    }
    if (outcome.isFailed) {
      setState(() {
        _submitting = false;
        _error = outcome.messageAr;
      });
      return;
    }
    final photo = _photoPath;
    if (photo != null && widget.savePhoto != null) {
      try {
        await widget.savePhoto!(photo);
      } catch (_) {
        if (!mounted) return;
        setState(() {
          _submitting = false;
          _photoPath = null;
          _error =
              'حُفظ الإجراء، لكن تعذّر حفظ الصورة على الجهاز. يمكنك التقاطها مجدّداً من تفاصيل المهمّة.';
        });
        return;
      }
    }
    if (!mounted) return;
    Navigator.of(context).pop(outcome);
  }

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final existing = widget.existingNotes?.trim() ?? '';
    return AppSheet(
      title: widget.title,
      submitLabel: widget.submitLabel,
      onSubmit: _submit,
      submitting: _submitting,
      errorText: _error,
      children: [
        if (existing.isNotEmpty) ...[
          const SizedBox(height: SahoolSpacing.md),
          Text(
            'ملاحظات المهمّة الحاليّة',
            style: context.textStyles.labelLarge?.copyWith(color: t.muted),
          ),
          const SizedBox(height: SahoolSpacing.xs),
          Text(
            existing,
            maxLines: 4,
            overflow: TextOverflow.ellipsis,
            style: context.textStyles.bodyMedium,
          ),
        ],
        AppTextField(
          label: widget.noteRequired ? 'الملاحظة' : 'ملاحظة (اختياريّة)',
          controller: _note,
          maxLines: 3,
          errorText: _noteError,
          enabled: !_submitting,
          helper: existing.isEmpty
              ? null
              : 'تُضاف ملاحظتك إلى ملاحظات المهمّة ولا تستبدلها.',
        ),
        if (widget.pickPhoto != null) ...[
          const SizedBox(height: SahoolSpacing.md),
          if (_photoPath != null)
            Row(
              children: [
                ClipRRect(
                  borderRadius: const BorderRadius.all(
                    Radius.circular(SahoolRadius.sm),
                  ),
                  child: Image.file(
                    File(_photoPath!),
                    width: 72,
                    height: 72,
                    fit: BoxFit.cover,
                    errorBuilder: (_, _, _) => const SizedBox(
                      width: 72,
                      height: 72,
                      child: Icon(Icons.image_not_supported_outlined),
                    ),
                  ),
                ),
                const SizedBox(width: SahoolSpacing.md),
                Expanded(
                  child: Text(
                    'صورة مرفقة (على هذا الجهاز)',
                    style: context.textStyles.bodyMedium,
                  ),
                ),
                AppIconButton(
                  icon: Icons.delete_outline,
                  tooltip: 'إزالة الصورة',
                  onPressed: _submitting
                      ? null
                      : () => setState(() => _photoPath = null),
                ),
              ],
            )
          else
            SecondaryButton(
              label: 'التقاط صورة',
              icon: Icons.photo_camera_outlined,
              onPressed: _submitting ? null : _takePhoto,
            ),
          const SizedBox(height: SahoolSpacing.sm),
          Text(
            TaskPhotoStore.notice,
            style: context.textStyles.bodySmall?.copyWith(color: t.muted),
          ),
        ],
      ],
    );
  }
}
