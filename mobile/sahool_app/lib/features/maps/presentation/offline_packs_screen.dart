// SAHOOL — features/maps/presentation/offline_packs_screen.dart
// «خرائط بلا اتّصال»: الحزم الموجودة على الجهاز، أيّها مفعّلة، وما يصلح منها.
//
// صدق حول ما لا يتوفّر بعد:
//   • الاستيراد بمنتقي الملفّات يحتاج اعتماديّة (file_picker) غير موجودة —
//     image_picker لا يفتح .mbtiles. نعرض المجلّد الذي تُنسخ إليه الحزم بدلاً منه.
//   • التنزيل من الخادم غير متاح: نقطة الحزم في خدمة الراستر تتطلّب رمز خدمة.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/state_views.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/offline_pack_store.dart';
import '../data/offline_tiles.dart';
import 'offline_packs_cubit.dart';

class OfflinePacksScreen extends StatelessWidget {
  const OfflinePacksScreen({super.key, this.store, this.opener});

  static const routePath = '/maps/offline-packs';

  final OfflinePackStore? store;
  final PackOpener? opener;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) =>
        OfflinePacksCubit(store ?? OfflinePackStore.instance, opener: opener)
          ..load(),
    child: const _OfflinePacksView(),
  );
}

String _size(int bytes) {
  final mb = bytes / (1024 * 1024);
  return mb >= 1
      ? '${fmtNumber(mb, decimals: 1)} م.ب'
      : '${fmtNumber(bytes / 1024, decimals: 0)} ك.ب';
}

class _OfflinePacksView extends StatelessWidget {
  const _OfflinePacksView();

  @override
  Widget build(BuildContext context) {
    return BlocConsumer<OfflinePacksCubit, OfflinePacksState>(
      listenWhen: (a, b) => b.message != null && a.message != b.message,
      listener: (context, s) {
        if (s.status != OfflinePacksStatus.failed) {
          showSnack(context, s.message!);
        }
      },
      builder: (context, s) {
        final cubit = context.read<OfflinePacksCubit>();
        Widget body;
        switch (s.status) {
          case OfflinePacksStatus.loading:
            body = const LoadingState(message: 'جارٍ فحص الحزم على الجهاز');
          case OfflinePacksStatus.failed:
            body = EmptyState(
              icon: Icons.folder_off_outlined,
              title: 'تعذّر الفحص',
              message: s.message ?? 'تعذّر قراءة مجلّد الخرائط',
              actionLabel: 'إعادة المحاولة',
              onAction: cubit.load,
            );
          case OfflinePacksStatus.loaded:
            body = RefreshIndicator(
              onRefresh: cubit.load,
              child: ListView(
                padding: const EdgeInsetsDirectional.all(SahoolSpacing.page),
                children: [
                  _HowTo(folders: s.folders),
                  const SizedBox(height: SahoolSpacing.lg),
                  if (s.activePath != null)
                    Padding(
                      padding: const EdgeInsetsDirectional.only(
                        bottom: SahoolSpacing.md,
                      ),
                      child: SecondaryButton(
                        label: 'استعمال خريطة الشبكة بدل المحفوظة',
                        icon: Icons.public,
                        onPressed: cubit.deactivate,
                      ),
                    ),
                  if (s.packs.isEmpty)
                    const EmptyState(
                      icon: Icons.map_outlined,
                      title: 'لا حزم على الجهاز',
                      message:
                          'انسخ ملفّ \u200E.pmtiles أو \u200E.mbtiles إلى المجلّد أعلاه ثمّ اسحب للتحديث.',
                    ),
                  for (final p in s.packs)
                    _PackTile(
                      entry: p,
                      active: p.file.path == s.activePath,
                      busy: s.busyPath == p.file.path,
                    ),
                ],
              ),
            );
        }
        return AppScaffold(
          title: 'خرائط بلا اتّصال',
          actions: [
            AppIconButton(
              icon: Icons.refresh,
              tooltip: 'إعادة الفحص',
              onPressed: s.status == OfflinePacksStatus.loading
                  ? null
                  : cubit.load,
            ),
          ],
          body: body,
        );
      },
    );
  }
}

class _HowTo extends StatelessWidget {
  const _HowTo({required this.folders});
  final List<String> folders;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    return SectionCard(
      title: 'كيف أضيف خريطة؟',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'الحزمة ملفّ صور خرائط (\u200E.pmtiles أو \u200E.mbtiles) لمنطقتك يعمل بلا شبكة. '
            'انسخه إلى أحد المجلّدات التالية ثمّ اسحب الشاشة للتحديث:',
            style: context.textStyles.bodyMedium,
          ),
          const SizedBox(height: SahoolSpacing.sm),
          for (final f in folders)
            Row(
              children: [
                Expanded(
                  child: SelectableText(
                    f,
                    textDirection: TextDirection.ltr,
                    style: context.textStyles.bodySmall,
                  ),
                ),
                AppIconButton(
                  icon: Icons.copy,
                  tooltip: 'نسخ المسار',
                  onPressed: () async {
                    await Clipboard.setData(ClipboardData(text: f));
                    if (context.mounted) showSnack(context, 'نُسخ المسار');
                  },
                ),
              ],
            ),
          const SizedBox(height: SahoolSpacing.sm),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.info_outline, size: SahoolSizes.iconSm, color: t.info),
              const SizedBox(width: SahoolSpacing.xs),
              Expanded(
                child: Text(
                  'الاستيراد من الملفّات داخل التطبيق وتنزيل الحزم من الخادم غير متاحين بعد. '
                  'الحزم النقطيّة فقط تُعرض.',
                  style: context.textStyles.bodySmall?.copyWith(color: t.muted),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _PackTile extends StatelessWidget {
  const _PackTile({
    required this.entry,
    required this.active,
    required this.busy,
  });

  final OfflinePackEntry entry;
  final bool active;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final cubit = context.read<OfflinePacksCubit>();
    final f = entry.file;
    final kind = f.format == OfflinePackFormat.pmtiles ? 'PMTiles' : 'MBTiles';
    final zoom = (entry.minZoom != null && entry.maxZoom != null)
        ? ' · تكبير ${entry.minZoom}–${entry.maxZoom}'
        : '';
    return Card(
      key: ValueKey('pack-${f.name}'),
      margin: const EdgeInsetsDirectional.only(bottom: SahoolSpacing.md),
      child: Padding(
        padding: const EdgeInsetsDirectional.all(SahoolSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    f.name,
                    textDirection: TextDirection.ltr,
                    textAlign: TextAlign.start,
                    style: context.textStyles.titleSmall,
                  ),
                ),
                if (active)
                  const StatusChip(label: 'مفعّلة', tone: StatusTone.success)
                else if (!entry.usable)
                  const StatusChip(label: 'غير صالحة', tone: StatusTone.danger),
              ],
            ),
            const SizedBox(height: SahoolSpacing.xs),
            Text(
              '$kind · ${_size(f.sizeBytes)} · ${fmtDate(f.modified)}$zoom',
              style: context.textStyles.bodySmall,
            ),
            if (entry.error != null)
              Padding(
                padding: const EdgeInsetsDirectional.only(
                  top: SahoolSpacing.xs,
                ),
                child: Text(
                  entry.error!,
                  style: context.textStyles.bodySmall?.copyWith(
                    color: context.tokens.danger,
                  ),
                ),
              ),
            const SizedBox(height: SahoolSpacing.sm),
            Row(
              children: [
                if (entry.usable && !active)
                  Expanded(
                    child: PrimaryButton(
                      label: 'تفعيل',
                      icon: Icons.check,
                      loading: busy,
                      onPressed: () => cubit.activate(entry),
                    ),
                  ),
                if (entry.usable && !active)
                  const SizedBox(width: SahoolSpacing.sm),
                Expanded(
                  child: SecondaryButton(
                    label: 'حذف',
                    icon: Icons.delete_outline,
                    onPressed: busy
                        ? null
                        : () async {
                            final ok = await showConfirmDialog(
                              context,
                              title: 'حذف الحزمة؟',
                              message:
                                  'سيُحذف «${f.name}» من الجهاز ولن تعمل هذه المنطقة بلا شبكة حتى تُنسخ من جديد.',
                              confirmLabel: 'حذف',
                              destructive: true,
                            );
                            if (ok) await cubit.delete(entry);
                          },
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
