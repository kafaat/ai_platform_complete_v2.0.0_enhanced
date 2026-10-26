// SAHOOL — features/advisor/presentation/widgets/chat_bubbles.dart
// فقاعات المحادثة. ردّ المستشار يعرض ما أرسله الخادم فقط: نصّ answer_ar، حالة
// التوليد (ومنها الرفض بالسياسة)، جودة الدليل ووسم «غير معايَر» حين يقوله
// الخادم، مصادر الأدلّة، والقيم المُتحقَّقة (claims). لا نصّ ولا رقم يُخترَع.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/advisor/data/advisor_models.dart';

/// وسم الثقة غير المعايَرة (حرفيّاً كما في الويب والعقد).
const String kNotCalibrated = 'غير معايَر';

Future<void> copyToClipboard(BuildContext context, String text) async {
  await Clipboard.setData(ClipboardData(text: text));
  if (!context.mounted) return;
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(const SnackBar(content: Text('تم النسخ')));
}

class UserBubble extends StatelessWidget {
  const UserBubble({super.key, required this.entry});
  final ChatEntry entry;

  @override
  Widget build(BuildContext context) {
    final scheme = context.colors;
    return Align(
      alignment: AlignmentDirectional.centerEnd,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.sizeOf(context).width * 0.82,
        ),
        child: Container(
          margin: const EdgeInsetsDirectional.only(
            start: SahoolSpacing.xxl,
            bottom: SahoolSpacing.md,
          ),
          padding: const EdgeInsets.all(SahoolSpacing.md),
          decoration: BoxDecoration(
            color: scheme.primaryContainer,
            borderRadius: SahoolRadius.lgAll,
          ),
          child: SelectableText(
            entry.text,
            style: context.textStyles.bodyLarge?.copyWith(
              color: scheme.onPrimaryContainer,
            ),
          ),
        ),
      ),
    );
  }
}

class AssistantBubble extends StatelessWidget {
  const AssistantBubble({super.key, required this.entry});
  final ChatEntry entry;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final reply = entry.reply;
    final status = generationStatusLabel(reply?.generationStatus);
    return Container(
      margin: const EdgeInsetsDirectional.only(
        end: SahoolSpacing.xl,
        bottom: SahoolSpacing.md,
      ),
      padding: const EdgeInsets.all(SahoolSpacing.md),
      decoration: BoxDecoration(
        color: t.surface,
        border: Border.all(color: t.line),
        borderRadius: SahoolRadius.lgAll,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Icon(Icons.psychology_outlined, color: t.success),
              const SizedBox(width: SahoolSpacing.sm),
              Expanded(
                child: Text(
                  'المستشار · ${fmtDateTime(entry.at)}',
                  style: context.textStyles.bodySmall?.copyWith(color: t.muted),
                ),
              ),
              AppIconButton(
                icon: Icons.copy_rounded,
                tooltip: 'نسخ الإجابة',
                onPressed: () => copyToClipboard(context, entry.text),
              ),
            ],
          ),
          if (reply != null && reply.blockedByPolicy)
            _PolicyNotice(text: status!),
          SelectableText(entry.text, style: context.textStyles.bodyLarge),
          if (reply != null) ...[
            if (status != null && !reply.blockedByPolicy)
              Padding(
                padding: const EdgeInsets.only(top: SahoolSpacing.sm),
                child: Text(
                  status,
                  style: context.textStyles.bodySmall?.copyWith(
                    color: t.warning,
                  ),
                ),
              ),
            _ReplyMeta(reply: reply),
          ],
        ],
      ),
    );
  }
}

class _PolicyNotice extends StatelessWidget {
  const _PolicyNotice({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    return Container(
      key: const Key('advisor-policy-blocked'),
      margin: const EdgeInsets.only(bottom: SahoolSpacing.sm),
      padding: const EdgeInsets.all(SahoolSpacing.sm),
      decoration: BoxDecoration(
        color: t.warning.withValues(alpha: 0.12),
        borderRadius: SahoolRadius.mdAll,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.policy_outlined, color: t.warning),
          const SizedBox(width: SahoolSpacing.sm),
          Expanded(child: Text(text, style: context.textStyles.bodyMedium)),
        ],
      ),
    );
  }
}

class _ReplyMeta extends StatelessWidget {
  const _ReplyMeta({required this.reply});
  final AdvisorReply reply;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final small = context.textStyles.bodySmall;
    final confidence = reply.confidence;
    return Padding(
      padding: const EdgeInsets.only(top: SahoolSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Divider(color: t.line, height: SahoolSpacing.lg),
          Wrap(
            spacing: SahoolSpacing.sm,
            runSpacing: SahoolSpacing.xs,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(
                'جودة الدليل: ${confidence == null ? kNotMeasured : fmtPct(confidence, fraction: true)}',
                style: small,
              ),
              if (reply.confidenceCalibrated == false)
                const StatusChip(
                  label: kNotCalibrated,
                  tone: StatusTone.warning,
                  icon: Icons.tune_outlined,
                ),
              if (reply.requiresHumanReview == true)
                const StatusChip(
                  label: 'يحتاج مراجعة بشريّة',
                  tone: StatusTone.info,
                  icon: Icons.person_search_outlined,
                ),
              if (reply.generationProvider != null)
                Text(
                  [
                    reply.generationProvider,
                    reply.generationModel,
                  ].whereType<String>().join(' · '),
                  style: small?.copyWith(color: t.muted),
                ),
            ],
          ),
          if (reply.evidenceSources.isNotEmpty) ...[
            const SizedBox(height: SahoolSpacing.sm),
            Text('مصادر الأدلّة', style: context.textStyles.titleSmall),
            const SizedBox(height: SahoolSpacing.xs),
            Wrap(
              spacing: SahoolSpacing.xs,
              runSpacing: SahoolSpacing.xs,
              children: [
                for (final s in reply.evidenceSources)
                  StatusChip(
                    label: s.available
                        ? (s.count != null
                              ? '${s.labelAr} · ${s.count}'
                              : s.labelAr)
                        : '${s.labelAr} · غير متاح',
                    tone: s.available ? StatusTone.info : StatusTone.neutral,
                    icon: s.available
                        ? Icons.check_circle_outline
                        : Icons.remove_circle_outline,
                  ),
              ],
            ),
          ],
          if (reply.claims.isNotEmpty) ...[
            const SizedBox(height: SahoolSpacing.sm),
            Text(
              'قيم مُعلَنة من مالك البيانات (تطابق رقميّ، لا شهادة علميّة)',
              style: context.textStyles.titleSmall,
            ),
            for (final c in reply.claims)
              Text('• ${c.path}: ${c.value}', style: small),
          ],
          if (reply.readinessWarnings.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: SahoolSpacing.sm),
              child: Text(
                'تنبيه جاهزيّة: ${reply.readinessWarnings.take(3).join('؛ ')}',
                style: small?.copyWith(color: t.warning),
              ),
            ),
          if (reply.pendingApprovals > 0)
            Padding(
              padding: const EdgeInsets.only(top: SahoolSpacing.sm),
              child: Text(
                'إجراءات مقترحة بانتظار موافقة بشريّة (${reply.pendingApprovals}) — '
                'لا تُنفَّذ من المحادثة.',
                style: small?.copyWith(color: t.info),
              ),
            ),
          if (reply.limitations.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: SahoolSpacing.sm),
              child: Text(
                'قيود: ${reply.limitations.map((l) => kLimitationLabels[l] ?? l).join('، ')}',
                style: small?.copyWith(color: t.muted),
              ),
            ),
        ],
      ),
    );
  }
}

/// مؤشّر «المستشار يكتب…» مع تنبيه المهلة (حتى دقيقتين على شبكة ضعيفة).
class TypingIndicator extends StatelessWidget {
  const TypingIndicator({super.key});

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    return Semantics(
      liveRegion: true,
      label: 'المستشار يكتب',
      child: Container(
        key: const Key('advisor-typing'),
        margin: const EdgeInsetsDirectional.only(
          end: SahoolSpacing.xl,
          bottom: SahoolSpacing.md,
        ),
        padding: const EdgeInsets.all(SahoolSpacing.md),
        decoration: BoxDecoration(
          color: t.surface,
          border: Border.all(color: t.line),
          borderRadius: SahoolRadius.lgAll,
        ),
        child: Row(
          children: [
            SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: t.success,
              ),
            ),
            const SizedBox(width: SahoolSpacing.md),
            Expanded(
              child: Text(
                'المستشار يكتب… قد يستغرق حتى دقيقتين.',
                style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// بطاقة فشل الإرسال: نصّ صادق + «أعد المحاولة» (لا تُعرض لـ401/403 حيث الإعادة لا تفيد).
class FailureCard extends StatelessWidget {
  const FailureCard({
    super.key,
    required this.message,
    required this.question,
    this.onRetry,
  });

  final String message;
  final String question;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    return Container(
      key: const Key('advisor-failure'),
      margin: const EdgeInsetsDirectional.only(
        end: SahoolSpacing.xl,
        bottom: SahoolSpacing.md,
      ),
      padding: const EdgeInsets.all(SahoolSpacing.md),
      decoration: BoxDecoration(
        color: t.danger.withValues(alpha: 0.10),
        border: Border.all(color: t.danger.withValues(alpha: 0.4)),
        borderRadius: SahoolRadius.lgAll,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.error_outline, color: t.danger),
              const SizedBox(width: SahoolSpacing.sm),
              Expanded(
                child: Semantics(
                  liveRegion: true,
                  child: Text(message, style: context.textStyles.bodyMedium),
                ),
              ),
            ],
          ),
          if (onRetry != null) ...[
            const SizedBox(height: SahoolSpacing.sm),
            SecondaryButton(
              label: 'أعد المحاولة',
              icon: Icons.refresh_rounded,
              onPressed: onRetry,
            ),
          ],
        ],
      ),
    );
  }
}
