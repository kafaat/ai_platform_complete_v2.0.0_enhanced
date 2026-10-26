// SAHOOL — features/farm_book/presentation/farm_book_screen.dart
// «دفتر المزرعة»: مصروفات وإيرادات نقديّة أو آجلة، تقرير شهريّ من الخادم، الأطراف
// (موردون وعملاء) والأرصدة، وتصدير CSV/PDF. مرآة سلوك الويب
// (frontend/src/sections/SimpleFarmBookPage.tsx) بواجهة ميدانيّة: اختيار المزرعة
// من قائمة لا كتابة معرّفها، تصنيفات بلمسة، ومبلغ يقبل الأرقام العربيّة.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:path_provider/path_provider.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/farms/data/farms_api.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:share_plus/share_plus.dart';

import '../data/farm_book_api.dart';
import '../data/farm_book_models.dart';
import 'entry_form_sheet.dart';
import 'farm_book_cubit.dart';
import 'farm_book_entries_tab.dart';
import 'farm_book_parties_tab.dart';
import 'farm_book_report_tab.dart';
import 'farm_book_state.dart';
import 'farm_book_text.dart';

/// يسلّم الملفّ المُصدَّر للمستخدم (مشاركة/حفظ). قابل للحقن في الاختبارات.
typedef FarmBookFileSharer = Future<void> Function(FarmBookExport file);

/// الافتراضيّ: يكتب الملفّ في مجلّد مؤقّت ثمّ يفتح لوحة المشاركة (حفظ في الملفّات،
/// واتساب، بريد…).
Future<void> shareFarmBookExport(FarmBookExport file) async {
  final dir = await getTemporaryDirectory();
  final path = '${dir.path}${Platform.pathSeparator}${file.filename}';
  await File(path).writeAsBytes(file.bytes, flush: true);
  await Share.shareXFiles([
    XFile(path, mimeType: file.mimeType),
  ], subject: file.filename);
}

const _monthNamesAr = [
  'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', //
  'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر',
];

String monthLabelAr(YearMonth m) => '${_monthNamesAr[m.month - 1]} ${m.year}';

class FarmBookScreen extends StatelessWidget {
  const FarmBookScreen({
    super.key,
    this.role,
    this.api,
    this.farmsApi,
    this.fieldsApi,
    this.sharer,
    this.now,
  });

  /// null ⇒ دور الجلسة الحاليّة.
  final AppRole? role;
  final FarmBookApi? api;
  final FarmsApi? farmsApi;
  final FieldsApi? fieldsApi;
  final FarmBookFileSharer? sharer;
  final DateTime Function()? now;

  @override
  Widget build(BuildContext context) {
    final access = FarmBookAccess.forRole(role ?? normalizeRole(currentRole()));
    return BlocProvider(
      create: (_) => FarmBookCubit(
        api: api ?? FarmBookApi.instance,
        access: access,
        farmsApi: farmsApi,
        fieldsApi: fieldsApi,
        now: now,
      )..load(),
      child: FarmBookView(sharer: sharer ?? shareFarmBookExport),
    );
  }
}

class FarmBookView extends StatefulWidget {
  const FarmBookView({super.key, required this.sharer});
  final FarmBookFileSharer sharer;

  @override
  State<FarmBookView> createState() => _FarmBookViewState();
}

class _FarmBookViewState extends State<FarmBookView> {
  bool _exporting = false;

  Future<void> _export(String format) async {
    if (_exporting) return;
    final cubit = context.read<FarmBookCubit>();
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _exporting = true);
    try {
      final file = await cubit.export(format);
      await widget.sharer(file);
    } on ApiException catch (e) {
      messenger.showSnackBar(
        SnackBar(content: Text('تعذّر التصدير: ${farmBookErrorMessage(e)}')),
      );
    } on Object catch (e) {
      messenger.showSnackBar(
        SnackBar(content: Text('تعذّر التصدير: ${farmBookErrorMessage(e)}')),
      );
    } finally {
      if (mounted) setState(() => _exporting = false);
    }
  }

  Future<void> _openEntryForm() async {
    final cubit = context.read<FarmBookCubit>();
    final messenger = ScaffoldMessenger.of(context);
    final outcome = await showAppBottomSheet<FarmBookWriteOutcome>(
      context,
      builder: (_) => EntryFormSheet(cubit: cubit),
    );
    if (!mounted || outcome == null) return;
    messenger.showSnackBar(
      SnackBar(
        content: Text(switch (outcome) {
          WriteSaved(:final receipt) =>
            receipt.replayed
                ? 'القيد محفوظ مسبقاً (لم يُكرَّر).'
                : 'حُفظ القيد.',
          WriteQueued() =>
            'لا اتّصال: حُفظ القيد في صندوق الإرسال وسيُرسَل عند عودة الشبكة.',
          WriteFailed(:final messageAr) => messageAr,
        }),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return BlocBuilder<FarmBookCubit, FarmBookState>(
      builder: (context, state) {
        final cubit = context.read<FarmBookCubit>();
        final ready = state.farmId != null;
        return DefaultTabController(
          length: 3,
          child: AppScaffold(
            title: 'دفتر المزرعة',
            actions: [
              if (cubit.access.canReport && ready)
                _exporting
                    ? const Padding(
                        padding: EdgeInsetsDirectional.all(SahoolSpacing.md),
                        child: SizedBox.square(
                          dimension: SahoolSizes.iconMd,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                      )
                    : PopupMenuButton<String>(
                        tooltip: 'تصدير تقرير الشهر',
                        icon: const Icon(Icons.download_rounded),
                        onSelected: _export,
                        itemBuilder: (_) => const [
                          PopupMenuItem(
                            value: 'csv',
                            child: Text('تصدير CSV (جدول)'),
                          ),
                          PopupMenuItem(value: 'pdf', child: Text('تصدير PDF')),
                        ],
                      ),
            ],
            bottom: const TabBar(
              tabs: [
                Tab(text: 'الحركات'),
                Tab(text: 'التقرير الشهريّ'),
                Tab(text: 'الأطراف'),
              ],
            ),
            floatingActionButton: cubit.access.canWrite && ready
                ? AppFab(
                    heroKey: '/farm-book',
                    label: 'قيد جديد',
                    icon: Icons.add_rounded,
                    onPressed: _openEntryForm,
                  )
                : null,
            body: _body(context, state, cubit),
          ),
        );
      },
    );
  }

  Widget _body(BuildContext context, FarmBookState state, FarmBookCubit cubit) {
    final farms = state.farms;
    return switch (farms) {
      SectionLoading() => const LoadingState(message: 'جارٍ تحميل المزارع…'),
      SectionNotAllowed() => const SizedBox.shrink(),
      SectionFailed(:final error) => ErrorState(
        error: error,
        onRetry: cubit.load,
      ),
      SectionLoaded(:final data) when data.isEmpty => const EmptyState(
        icon: Icons.agriculture_outlined,
        title: 'لا مزارع بعد',
        message: 'الدفتر يُفتح لمزرعة. أنشئ مزرعتك أوّلاً من «المزارع».',
      ),
      SectionLoaded() => Column(
        children: [
          _FilterBar(state: state, cubit: cubit),
          Expanded(
            child: TabBarView(
              children: [
                FarmBookEntriesTab(onAdd: _openEntryForm),
                const FarmBookReportTab(),
                const FarmBookPartiesTab(),
              ],
            ),
          ),
        ],
      ),
    };
  }
}

class _FilterBar extends StatelessWidget {
  const _FilterBar({required this.state, required this.cubit});
  final FarmBookState state;
  final FarmBookCubit cubit;

  @override
  Widget build(BuildContext context) {
    final farms = (state.farms as SectionLoaded<List<FarmBookOption>>).data;
    final atCurrent = state.month == cubit.currentMonth;
    return Material(
      color: context.tokens.surface,
      child: Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(
          SahoolSpacing.page,
          0,
          SahoolSpacing.page,
          SahoolSpacing.sm,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (farms.length > 1)
              AppDropdown<String>(
                key: ValueKey('farm:${state.farmId}'),
                label: 'المزرعة',
                items: {for (final f in farms) f.id: f.name},
                value: state.farmId,
                onChanged: (v) {
                  if (v != null) cubit.selectFarm(v);
                },
              )
            else
              Padding(
                padding: const EdgeInsets.only(top: SahoolSpacing.md),
                child: Text(
                  farms.single.name,
                  style: context.textStyles.titleMedium,
                ),
              ),
            _fieldFilter(context),
            const SizedBox(height: SahoolSpacing.sm),
            Row(
              children: [
                AppIconButton(
                  icon: Icons.chevron_left_rounded,
                  tooltip: 'الشهر السابق',
                  onPressed: () => cubit.setMonth(state.month.previous),
                ),
                Expanded(
                  child: Text(
                    monthLabelAr(state.month),
                    textAlign: TextAlign.center,
                    style: context.textStyles.titleMedium,
                  ),
                ),
                AppIconButton(
                  icon: Icons.chevron_right_rounded,
                  tooltip: 'الشهر التالي',
                  onPressed: atCurrent
                      ? null
                      : () => cubit.setMonth(state.month.next),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _fieldFilter(BuildContext context) {
    final fields = state.fields;
    return switch (fields) {
      SectionLoaded(:final data) when data.isNotEmpty => AppDropdown<String?>(
        key: ValueKey('field:${state.farmId}:${state.fieldId}'),
        label: 'الحقل',
        items: {null: 'كلّ الحقول', for (final f in data) f.id: f.name},
        value: state.fieldId,
        onChanged: cubit.selectField,
      ),
      SectionFailed() => Padding(
        padding: const EdgeInsets.only(top: SahoolSpacing.sm),
        child: Text(
          'تعذّر تحميل الحقول — يُعرض دفتر المزرعة كلّها.',
          style: context.textStyles.bodySmall?.copyWith(
            color: context.tokens.warning,
          ),
        ),
      ),
      _ => const SizedBox.shrink(),
    };
  }
}
