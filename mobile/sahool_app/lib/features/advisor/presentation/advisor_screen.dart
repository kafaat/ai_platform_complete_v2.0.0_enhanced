// SAHOOL — features/advisor/presentation/advisor_screen.dart
// شاشة المستشار الزراعيّ (تبويب «المستشار»). تسأل /api/ai-agronomist/chat بالعقد
// الصحيح (`question` + `field_id` اختياريّاً) وتعرض answer_ar وما يرافقه كما
// أرسله الخادم. السجلّ مشفّر لكلّ مستخدم ويُحذَف عند الخروج.
//
// تشخيص الآفات بالصورة لم يعد هنا: انتقل إلى ميزة الاستكشاف الميدانيّ (scouting)
// التي تشترط الحقل وتملك الكاميرا. نربط إليها بمسارها فقط.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/advisor/advisor_paths.dart';
import 'package:sahool_app/features/advisor/data/advisor_api.dart';
import 'package:sahool_app/features/advisor/data/advisor_models.dart';
import 'package:sahool_app/features/advisor/data/chat_history_store.dart';
import 'package:sahool_app/features/advisor/presentation/advisor_chat_cubit.dart';
import 'package:sahool_app/features/advisor/presentation/widgets/chat_bubbles.dart';
import 'package:sahool_app/features/advisor/presentation/widgets/field_picker.dart';
import 'package:sahool_app/services/auth_service.dart';

const List<String> kAdvisorSuggestions = [
  'متى أروي الحقل هذا الأسبوع؟',
  'ما احتياجات التسميد للقمح الآن؟',
  'هل يوجد خطر آفات في الظروف الحاليّة؟',
];

class AdvisorScreen extends StatelessWidget {
  const AdvisorScreen({
    super.key,
    this.fieldId,
    this.fieldName,
    this.api,
    this.history,
    this.fieldLoader,
  });

  final String? fieldId;
  final String? fieldName;

  /// للاختبار: API بعميل مزيّف، وسجلّ في الذاكرة، ومحمّل حقول.
  final AdvisorApi? api;
  final Future<AdvisorChatHistory>? history;
  final FieldLoader? fieldLoader;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) => AdvisorChatCubit(
      api: api ?? AdvisorApi.instance,
      history:
          history ??
          AdvisorChatStore.instance.openFor(
            tenantId: AuthService.instance.tenantId,
            userId: AuthService.instance.userId,
          ),
      fieldId: fieldId,
      fieldName: fieldName,
    )..init(),
    child: _AdvisorView(fieldLoader: fieldLoader),
  );
}

class _AdvisorView extends StatefulWidget {
  const _AdvisorView({this.fieldLoader});
  final FieldLoader? fieldLoader;

  @override
  State<_AdvisorView> createState() => _AdvisorViewState();
}

class _AdvisorViewState extends State<_AdvisorView> {
  final _controller = TextEditingController();
  final _scroll = ScrollController();

  @override
  void dispose() {
    _controller.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _send(String text) async {
    FocusScope.of(context).unfocus();
    final pending = context.read<AdvisorChatCubit>().send(text);
    // يُفرَّغ الحقل حين يُقبَل السؤال (غير فارغ وضمن الحدّ)؛ يبقى عند الرفض.
    final trimmed = text.trim();
    if (trimmed.isNotEmpty && trimmed.length <= kMaxQuestionLength) {
      _controller.clear();
    }
    await pending;
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _chooseField() async {
    final cubit = context.read<AdvisorChatCubit>();
    final picked = await pickField(context, loader: widget.fieldLoader);
    if (!mounted || picked == null) return;
    cubit.setField(picked.id, picked.name);
  }

  Future<void> _confirmClear() async {
    final cubit = context.read<AdvisorChatCubit>();
    final ok = await showConfirmDialog(
      context,
      title: 'مسح المحادثة؟',
      message: 'تُحذف رسائل المستشار المحفوظة على هذا الجهاز لحسابك فقط.',
      confirmLabel: 'مسح',
      destructive: true,
    );
    if (ok && mounted) await cubit.clearHistory();
  }

  @override
  Widget build(BuildContext context) {
    return BlocConsumer<AdvisorChatCubit, AdvisorChatState>(
      listenWhen: (a, b) =>
          a.messages.length != b.messages.length ||
          a.sending != b.sending ||
          a.failure != b.failure,
      listener: (_, _) => _scrollToEnd(),
      builder: (context, state) {
        final cubit = context.read<AdvisorChatCubit>();
        return AppScaffold(
          title: 'المستشار الزراعي',
          actions: [
            AppIconButton(
              icon: Icons.fact_check_outlined,
              tooltip: 'توصيات الحقل',
              onPressed: () => context.openRoute(
                AdvisorPaths.recommendationsFor(state.fieldId),
              ),
            ),
            AppIconButton(
              icon: Icons.delete_outline,
              tooltip: 'مسح المحادثة',
              onPressed: state.messages.isEmpty ? null : _confirmClear,
            ),
          ],
          body: Column(
            children: [
              _ContextBar(
                fieldName: state.fieldName ?? state.fieldId,
                onPick: state.sending ? null : _chooseField,
                onClear: state.fieldId == null || state.sending
                    ? null
                    : () => cubit.setField(null, null),
              ),
              if (!state.loadingHistory && !state.persistent)
                const _NotSavedBanner(),
              Expanded(child: _messages(context, state)),
              _InputBar(
                controller: _controller,
                sending: state.sending,
                errorText: state.inputError,
                onSend: _send,
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _messages(BuildContext context, AdvisorChatState state) {
    final cubit = context.read<AdvisorChatCubit>();
    if (state.loadingHistory) {
      return const LoadingState(message: 'جارٍ تحميل المحادثة…');
    }
    final failure = state.failure;
    if (state.messages.isEmpty && !state.sending && failure == null) {
      return _Welcome(onAsk: _send);
    }
    return ListView(
      controller: _scroll,
      padding: const EdgeInsets.all(SahoolSpacing.lg),
      children: [
        for (final m in state.messages)
          m.role == ChatRole.user
              ? UserBubble(entry: m)
              : AssistantBubble(entry: m),
        if (state.sending) const TypingIndicator(),
        if (failure != null)
          FailureCard(
            message: advisorChatErrorText(failure.error),
            question: failure.question,
            onRetry: failure.error.isUnauthorized || failure.error.isForbidden
                ? null
                : cubit.retry,
          ),
      ],
    );
  }
}

class _ContextBar extends StatelessWidget {
  const _ContextBar({required this.fieldName, this.onPick, this.onClear});
  final String? fieldName;
  final VoidCallback? onPick;
  final VoidCallback? onClear;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    return Material(
      color: t.surfaceAlt,
      child: Padding(
        padding: const EdgeInsetsDirectional.symmetric(
          horizontal: SahoolSpacing.lg,
          vertical: SahoolSpacing.xs,
        ),
        child: Row(
          children: [
            Icon(Icons.grass_outlined, color: t.muted),
            const SizedBox(width: SahoolSpacing.sm),
            Expanded(
              child: Text(
                fieldName == null
                    ? 'سؤال عامّ — بلا حقل مربوط'
                    : 'السياق: حقل $fieldName',
                style: context.textStyles.bodyMedium,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            TextButton(
              onPressed: onPick,
              child: Text(fieldName == null ? 'اربط حقلاً' : 'غيّر'),
            ),
            if (fieldName != null)
              AppIconButton(
                icon: Icons.link_off_rounded,
                tooltip: 'إزالة ربط الحقل',
                onPressed: onClear,
              ),
          ],
        ),
      ),
    );
  }
}

class _NotSavedBanner extends StatelessWidget {
  const _NotSavedBanner();

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    return Container(
      width: double.infinity,
      color: t.warning.withValues(alpha: 0.12),
      padding: const EdgeInsetsDirectional.symmetric(
        horizontal: SahoolSpacing.lg,
        vertical: SahoolSpacing.sm,
      ),
      child: Text(
        'المحادثة غير محفوظة على هذا الجهاز (تعذّر التخزين المشفّر).',
        style: context.textStyles.bodySmall,
      ),
    );
  }
}

class _Welcome extends StatelessWidget {
  const _Welcome({required this.onAsk});
  final ValueChanged<String> onAsk;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    return ListView(
      padding: const EdgeInsets.all(SahoolSpacing.xl),
      children: [
        Icon(Icons.psychology_outlined, size: 56, color: t.success),
        const SizedBox(height: SahoolSpacing.md),
        Text(
          'المستشار الزراعي',
          textAlign: TextAlign.center,
          style: context.textStyles.titleLarge,
        ),
        const SizedBox(height: SahoolSpacing.sm),
        Text(
          'يجيب من أدلّة المنصّة (RAG والرسم المعرفيّ وحالة الحقل). اربط حقلاً '
          'لإجابة خاصّة به. القرار التنفيذيّ يبقى لك وللمهندس.',
          textAlign: TextAlign.center,
          style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
        ),
        const SizedBox(height: SahoolSpacing.lg),
        for (final q in kAdvisorSuggestions)
          Padding(
            padding: const EdgeInsets.only(bottom: SahoolSpacing.sm),
            child: SecondaryButton(label: q, onPressed: () => onAsk(q)),
          ),
        const SizedBox(height: SahoolSpacing.md),
        AppListTile(
          icon: Icons.camera_alt_outlined,
          title: 'تشخيص الآفات بالصورة',
          subtitle: 'انتقل إلى الاستكشاف الميدانيّ (يتطلّب اختيار الحقل).',
          onTap: () => context.openRoute(AdvisorPaths.scouting),
        ),
      ],
    );
  }
}

class _InputBar extends StatelessWidget {
  const _InputBar({
    required this.controller,
    required this.sending,
    required this.onSend,
    this.errorText,
  });

  final TextEditingController controller;
  final bool sending;
  final ValueChanged<String> onSend;
  final String? errorText;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    return Material(
      color: t.surface,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(
            SahoolSpacing.md,
            SahoolSpacing.sm,
            SahoolSpacing.sm,
            SahoolSpacing.sm,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: TextField(
                  key: const Key('advisor-input'),
                  controller: controller,
                  minLines: 1,
                  maxLines: 4,
                  textInputAction: TextInputAction.send,
                  onSubmitted: sending ? null : onSend,
                  decoration: InputDecoration(
                    hintText: 'اسأل عن حقلك…',
                    errorText: errorText,
                    errorMaxLines: 2,
                  ),
                ),
              ),
              const SizedBox(width: SahoolSpacing.xs),
              AppIconButton(
                icon: Icons.send_rounded,
                tooltip: sending ? 'جارٍ الإرسال' : 'إرسال',
                onPressed: sending ? null : () => onSend(controller.text),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
