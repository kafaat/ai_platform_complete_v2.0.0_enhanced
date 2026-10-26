// SAHOOL — features/fields/presentation/workspace/workspace_widgets.dart
// لبنات مساحة العمل المشتركة على نظام التصميم: بطاقة قسم، صفّ معلومة، شبكة
// بطاقات متكيّفة، إبقاء التبويب حيّاً، وقسم «غير متاح بعد».
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

/// بطاقة قسم (عنوان + محتوى). العنوان يلتفّ داخل Expanded فلا يفيض مهما طال
/// (كان اسم حقل طويل يفيض 722px).
class WSectionCard extends StatelessWidget {
  const WSectionCard({
    super.key,
    required this.title,
    required this.icon,
    required this.child,
    this.trailing,
  });

  final String title;
  final IconData icon;
  final Widget child;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: SahoolSpacing.md),
    child: SectionCard(
      title: title,
      icon: icon,
      trailing: trailing,
      child: child,
    ),
  );
}

/// صفّ معلومة: التسمية في البداية والقيمة في النهاية (اتّجاهيّاً)، والقيمة
/// الطويلة تلتفّ بدل أن تفيض.
class WInfoRow extends StatelessWidget {
  const WInfoRow(this.label, this.value, {super.key});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: SahoolSpacing.xs),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Text(
            label,
            style: context.textStyles.bodyMedium?.copyWith(
              color: context.tokens.muted,
            ),
          ),
        ),
        const SizedBox(width: SahoolSpacing.md),
        Flexible(
          child: Text(
            value,
            textAlign: TextAlign.end,
            style: context.textStyles.titleSmall,
          ),
        ),
      ],
    ),
  );
}

/// قسم «غير متاح بعد» صادق حين لا تتوفّر بيانات/واجهة.
class WUnavailableSection extends StatelessWidget {
  const WUnavailableSection({
    super.key,
    required this.title,
    required this.icon,
    this.note = 'لم تُربَط واجهة هذه البيانات بالخادم بعد.',
  });

  final String title;
  final IconData icon;
  final String note;

  @override
  Widget build(BuildContext context) =>
      EmptyState(icon: icon, title: '$title — غير متاح بعد', message: note);
}

/// شبكة بطاقات متكيّفة: الأعمدة من العرض ومقياس النصّ، والارتفاع من المحتوى.
class AdaptiveTileGrid extends StatelessWidget {
  const AdaptiveTileGrid({
    super.key,
    required this.children,
    this.minTileWidth = 150,
  });

  final List<Widget> children;
  final double minTileWidth;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, c) {
      final scale = MediaQuery.textScalerOf(context).scale(1).clamp(1.0, 2.0);
      final cols = math.max(1, (c.maxWidth / (minTileWidth * scale)).floor());
      const gap = SahoolSpacing.sm;
      final w = (c.maxWidth - gap * (cols - 1)) / cols;
      return Wrap(
        spacing: gap,
        runSpacing: gap,
        children: [for (final ch in children) SizedBox(width: w, child: ch)],
      );
    },
  );
}

/// يُبقي محتوى التبويب حيّاً عند التنقّل بين التبويبات (لا إعادة جلب).
class KeepAliveTab extends StatefulWidget {
  const KeepAliveTab({super.key, required this.child});
  final Widget child;

  @override
  State<KeepAliveTab> createState() => _KeepAliveTabState();
}

class _KeepAliveTabState extends State<KeepAliveTab>
    with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return widget.child;
  }
}

/// زرّ إجراء سريع كبير (≥56dp) بأيقونة ونصّ.
class QuickActionButton extends StatelessWidget {
  const QuickActionButton({
    super.key,
    required this.icon,
    required this.label,
    required this.onPressed,
  });

  final IconData icon;
  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: SahoolSizes.buttonHeight + SahoolSpacing.xs,
    child: OutlinedButton.icon(
      onPressed: onPressed,
      icon: Icon(icon),
      label: Text(label, maxLines: 2, overflow: TextOverflow.ellipsis),
    ),
  );
}
