// SAHOOL — features/alerts/presentation/notification_prefs_screen.dart
// تفضيلات الإشعار: القنوات وعناوينها، أنواع الأحداث، أدنى خطورة.
// مرآة الويب NotificationSettingsPage.tsx مع ضمان «اقرأ قبل أن تكتب».
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/alert_models.dart';
import '../data/alerts_api.dart';
import '../data/notification_prefs.dart';
import 'alert_visuals.dart';
import 'notification_prefs_cubit.dart';

class NotificationPrefsScreen extends StatelessWidget {
  const NotificationPrefsScreen({super.key, this.api, this.role});
  final AlertsApi? api;
  final String? role;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) =>
        NotificationPrefsCubit(NotificationPrefsRepository(api))..load(),
    child: _PrefsView(canEdit: canEditNotificationPrefs(role)),
  );
}

class _PrefsView extends StatelessWidget {
  const _PrefsView({required this.canEdit});
  final bool canEdit;

  @override
  Widget build(BuildContext context) {
    final cubit = context.read<NotificationPrefsCubit>();
    return BlocListener<NotificationPrefsCubit, NotificationPrefsState>(
      listenWhen: (a, b) => a.savedSeq != b.savedSeq,
      listener: (context, _) => ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('حُفظت تفضيلات الإشعار.'))),
      child: AppScaffold(
        title: 'تفضيلات الإشعار',
        body: BlocBuilder<NotificationPrefsCubit, NotificationPrefsState>(
          buildWhen: (a, b) =>
              a.prefs != b.prefs ||
              a.loadError != b.loadError ||
              a.loading != b.loading,
          builder: (context, s) {
            if (s.loading) {
              return const LoadingState(message: 'جارٍ قراءة التفضيلات…');
            }
            if (s.prefs == null) {
              // لا نموذج بلا قراءة: نموذج فارغ يُحفَظ كان سيمحو القنوات.
              return ErrorState(
                title: 'تعذّرت قراءة التفضيلات',
                error: s.loadError!,
                onRetry: cubit.load,
              );
            }
            return _PrefsForm(
              key: ValueKey(s.prefs),
              prefs: s.prefs!,
              canEdit: canEdit,
            );
          },
        ),
      ),
    );
  }
}

class _PrefsForm extends StatefulWidget {
  const _PrefsForm({super.key, required this.prefs, required this.canEdit});
  final NotificationPrefs prefs;
  final bool canEdit;

  @override
  State<_PrefsForm> createState() => _PrefsFormState();
}

class _PrefsFormState extends State<_PrefsForm> {
  final Map<NotifChannel, TextEditingController> _ctrl = {};

  @override
  void initState() {
    super.initState();
    for (final c in NotifChannel.values) {
      if (c.addressKey != null) {
        _ctrl[c] = TextEditingController(text: widget.prefs.address(c) ?? '');
      }
    }
  }

  @override
  void dispose() {
    for (final c in _ctrl.values) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(
    BuildContext context,
  ) => BlocBuilder<NotificationPrefsCubit, NotificationPrefsState>(
    builder: (context, s) {
      final cubit = context.read<NotificationPrefsCubit>();
      final p = widget.prefs;
      final d = s.draft;
      final t = context.tokens;
      final edit = widget.canEdit && !s.saving;
      return ListView(
        padding: const EdgeInsets.all(SahoolSpacing.lg),
        children: [
          if (!widget.canEdit)
            Padding(
              padding: const EdgeInsets.only(bottom: SahoolSpacing.md),
              child: Text(
                'تعديل التفضيلات يتطلّب صلاحيّة المالك أو المدير على الخادم '
                'حاليّاً — تُعرَض هنا للقراءة فقط.',
                style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
              ),
            ),
          SectionCard(
            title: 'قنوات التسليم',
            icon: Icons.send_outlined,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (final c in NotifChannel.values)
                  _channel(context, cubit, p, d, c, edit),
              ],
            ),
          ),
          const SizedBox(height: SahoolSpacing.md),
          SectionCard(
            title: 'أدنى درجة خطورة تُرسَل',
            icon: Icons.filter_alt_outlined,
            child: Wrap(
              spacing: SahoolSpacing.sm,
              runSpacing: SahoolSpacing.sm,
              children: [
                _sevChip(cubit, d.minSeverityOf(p), null, 'كلّ الدرجات', edit),
                for (final sev in [
                  AlertSeverity.info,
                  AlertSeverity.warning,
                  AlertSeverity.critical,
                ])
                  _sevChip(
                    cubit,
                    d.minSeverityOf(p),
                    sev.wire,
                    sev.labelAr,
                    edit,
                  ),
              ],
            ),
          ),
          const SizedBox(height: SahoolSpacing.md),
          SectionCard(
            title: 'أنواع الأحداث',
            icon: Icons.category_outlined,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (p.eventTypes.isEmpty && d.addEvents.isEmpty)
                  Text(
                    'لا نوع محدّد على الخادم.',
                    style: context.textStyles.bodySmall?.copyWith(
                      color: t.muted,
                    ),
                  ),
                for (final e in kNotifEventTypesAr.entries)
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(e.value),
                    value: d.eventOn(p, e.key),
                    onChanged: edit
                        ? (v) => cubit.toggleEvent(e.key, v ?? false)
                        : null,
                  ),
                // أنواع يحفظها الخادم ولا نعرفها: تُعرَض وتُحفَظ كما هي.
                for (final e in p.eventTypes.where(
                  (x) => !kNotifEventTypesAr.containsKey(x),
                ))
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(e),
                    subtitle: const Text('نوع محفوظ على الخادم — يبقى كما هو'),
                  ),
              ],
            ),
          ),
          const SizedBox(height: SahoolSpacing.lg),
          if (s.saveError != null) ...[
            Text(
              s.saveError!,
              style: context.textStyles.bodyMedium?.copyWith(color: t.danger),
            ),
            const SizedBox(height: SahoolSpacing.sm),
          ],
          if (widget.canEdit)
            PrimaryButton(
              label: 'حفظ التفضيلات',
              icon: Icons.save_outlined,
              loading: s.saving,
              onPressed: d.isEmpty ? null : cubit.save,
            ),
          const SizedBox(height: SahoolSpacing.xl),
        ],
      );
    },
  );

  Widget _sevChip(
    NotificationPrefsCubit cubit,
    String? current,
    String? value,
    String label,
    bool edit,
  ) => ChoiceChip(
    label: Text(label),
    selected: current == value,
    materialTapTargetSize: MaterialTapTargetSize.padded,
    onSelected: edit ? (_) => cubit.setMinSeverity(value) : null,
  );

  Widget _channel(
    BuildContext context,
    NotificationPrefsCubit cubit,
    NotificationPrefs p,
    PrefsDraft d,
    NotifChannel c,
    bool edit,
  ) {
    final on = d.enabledOf(p, c);
    final ctrl = _ctrl[c];
    final address = d.addressOf(p, c);
    final missingAddress =
        on == true &&
        ctrl != null &&
        (address == null || address.trim().isEmpty);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: Text(c.labelAr),
          // null ⇒ الخادم لم يُرسل القيمة: نعرضها «غير معروفة» لا «معطّلة».
          subtitle: on == null
              ? const Text('القيمة غير معروفة من الخادم')
              : null,
          value: on ?? false,
          onChanged: edit ? (v) => cubit.setEnabled(c, v) : null,
        ),
        if (ctrl != null)
          AppTextField(
            label: c == NotifChannel.email ? 'عنوان البريد' : 'رقم الهاتف',
            controller: ctrl,
            enabled: edit,
            keyboardType: c == NotifChannel.email
                ? TextInputType.emailAddress
                : TextInputType.phone,
            inputFormatters: c == NotifChannel.email
                ? null
                : const [LocalizedDigitsFormatter()],
            errorText: missingAddress
                ? 'القناة مفعّلة بلا عنوان — لن يصل إليها شيء.'
                : null,
            onChanged: (v) => cubit.setAddress(c, v),
          ),
        if (c == NotifChannel.push)
          Text(
            'رمز الجهاز يُسجَّل تلقائيّاً عند تفعيل الإشعارات على هذا الجهاز.',
            style: context.textStyles.bodySmall?.copyWith(
              color: context.tokens.muted,
            ),
          ),
        const SizedBox(height: SahoolSpacing.sm),
      ],
    );
  }
}
