// SAHOOL — features/farm_book/presentation/farm_book_report_tab.dart
// التقرير الشهريّ والأرصدة كما يحسبها الخادم (/monthly و/balances). لا جمع محلّيّ:
// الخادم يصافي القيد وعكسه، ويحتسب العكس الواقع في شهر لاحق سالباً في شهره.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/farm_book_models.dart';
import 'farm_book_cubit.dart';
import 'farm_book_state.dart';
import 'farm_book_text.dart';

const String kReportNotAllowedAr =
    'التقرير الشهريّ والأرصدة متاحة للمالك والمدير والمهندس الزراعيّ فقط.';

class FarmBookReportTab extends StatelessWidget {
  const FarmBookReportTab({super.key});

  @override
  Widget build(BuildContext context) {
    return BlocBuilder<FarmBookCubit, FarmBookState>(
      builder: (context, state) {
        final cubit = context.read<FarmBookCubit>();
        final report = state.report;
        return switch (report) {
          SectionNotAllowed() => const EmptyState(
            icon: Icons.lock_outline_rounded,
            message: kReportNotAllowedAr,
          ),
          SectionLoading() => const LoadingState(
            message: 'جارٍ تحميل التقرير…',
          ),
          SectionFailed(:final error) => ErrorState(
            error: error,
            onRetry: cubit.loadBook,
          ),
          SectionLoaded(:final data) => RefreshIndicator(
            onRefresh: cubit.loadBook,
            child: ListView(
              padding: const EdgeInsetsDirectional.fromSTEB(
                SahoolSpacing.page,
                SahoolSpacing.sm,
                SahoolSpacing.page,
                SahoolSpacing.xxl * 3,
              ),
              children: [
                ...summaryView(context, data.summary),
                const SizedBox(height: SahoolSpacing.md),
                BalancesCard(section: state.balances),
                const SizedBox(height: SahoolSpacing.md),
                Text(
                  'الأرقام كما يحسبها الخادم. القيد وعكسه يتصافيان؛ والعكس '
                  'المسجَّل في شهر لاحق يظهر سالباً في شهره.',
                  style: context.textStyles.bodySmall?.copyWith(
                    color: context.tokens.muted,
                  ),
                ),
              ],
            ),
          ),
        };
      },
    );
  }

  static List<Widget> summaryView(BuildContext context, FarmBookSummary s) {
    if (s.isMultipleCurrencies) {
      return [
        SectionCard(
          title: 'عملات متعدّدة',
          icon: Icons.currency_exchange_rounded,
          child: Text(
            'قيود هذا الشهر بأكثر من عملة (${s.currencies.join('، ')}). '
            'الخادم لا يجمعها في إجمالي واحد، فلا نعرض إجماليّاً مُختلَقاً.',
          ),
        ),
      ];
    }
    if (!s.isOk) {
      return [
        SectionCard(
          child: Text('حالة تقرير غير معروفة من الخادم: ${s.status}'),
        ),
      ];
    }
    final unit = currencyUnitAr(s.currency);
    Widget tile(String label, num? v, IconData icon) =>
        MetricTile(label: label, value: v, unit: unit, decimals: 2, icon: icon);
    Widget pair(Widget a, Widget b) => Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(child: a),
        Expanded(child: b),
      ],
    );
    return [
      if (s.entriesCount == 0)
        Padding(
          padding: const EdgeInsets.only(bottom: SahoolSpacing.sm),
          child: Text(
            'لا قيود محتسبة في هذا الشهر.',
            style: context.textStyles.bodyMedium,
          ),
        ),
      pair(
        tile('المصروف', s.totalExpenses, Icons.north_east_rounded),
        tile('الإيراد', s.totalIncome, Icons.south_west_rounded),
      ),
      pair(
        tile('الصافي', s.net, Icons.balance_rounded),
        tile('أثر الصندوق', s.cashBalanceEffect, Icons.payments_outlined),
      ),
      pair(
        tile('علينا (آجل)', s.totalPayable, Icons.call_made_rounded),
        tile('لنا (آجل)', s.totalReceivable, Icons.call_received_rounded),
      ),
      if (s.entriesCount != null)
        Padding(
          padding: const EdgeInsets.only(top: SahoolSpacing.xs),
          child: Text(
            'عدد القيود المحتسبة: ${fmtNumber(s.entriesCount, decimals: 0)}',
            style: context.textStyles.bodySmall,
          ),
        ),
      if (s.expenseBreakdown.isNotEmpty) ...[
        const SizedBox(height: SahoolSpacing.md),
        _Breakdown(
          title: 'المصروف حسب التصنيف',
          values: s.expenseBreakdown,
          currency: s.currency,
        ),
      ],
      if (s.incomeBreakdown.isNotEmpty) ...[
        const SizedBox(height: SahoolSpacing.md),
        _Breakdown(
          title: 'الإيراد حسب التصنيف',
          values: s.incomeBreakdown,
          currency: s.currency,
        ),
      ],
      if (s.perHectare != null) ...[
        const SizedBox(height: SahoolSpacing.md),
        _Breakdown(
          title: 'لكلّ هكتار',
          values: {
            for (final e in s.perHectare!.entries)
              switch (e.key) {
                'expense' => 'المصروف',
                'income' => 'الإيراد',
                'net' => 'الصافي',
                final k => k,
              }: e.value,
          },
          currency: s.currency,
          translate: false,
        ),
      ],
    ];
  }
}

class _Breakdown extends StatelessWidget {
  const _Breakdown({
    required this.title,
    required this.values,
    required this.currency,
    this.translate = true,
  });
  final String title;
  final Map<String, num> values;
  final String? currency;
  final bool translate;

  @override
  Widget build(BuildContext context) => SectionCard(
    title: title,
    child: Column(
      children: [
        for (final e in values.entries)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: SahoolSpacing.xs),
            child: Row(
              children: [
                Expanded(child: Text(translate ? categoryLabel(e.key) : e.key)),
                Text(
                  fmtMoney(e.value, currency),
                  style: context.textStyles.titleSmall,
                ),
              ],
            ),
          ),
      ],
    ),
  );
}

/// ما علينا/ما لنا تراكميّاً حتى اليوم (/balances).
class BalancesCard extends StatelessWidget {
  const BalancesCard({super.key, required this.section});
  final Section<FarmBookBalances> section;

  @override
  Widget build(BuildContext context) {
    final s = section;
    final Widget body = switch (s) {
      SectionNotAllowed() => const Text(kReportNotAllowedAr),
      SectionLoading() => const Padding(
        padding: EdgeInsets.all(SahoolSpacing.sm),
        child: Center(child: CircularProgressIndicator()),
      ),
      SectionFailed(:final error) => Text(
        farmBookErrorMessage(error),
        style: context.textStyles.bodyMedium?.copyWith(
          color: context.tokens.danger,
        ),
      ),
      SectionLoaded(:final data) when !data.summary.isOk => Text(
        data.summary.isMultipleCurrencies
            ? 'الأرصدة بعملات متعدّدة (${data.summary.currencies.join('، ')}) — لا إجمالي واحد.'
            : 'حالة أرصدة غير معروفة: ${data.summary.status}',
      ),
      SectionLoaded(:final data) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: MetricTile(
              label: 'إجمالي ما علينا',
              value: data.summary.totalPayable,
              unit: currencyUnitAr(data.summary.currency),
              decimals: 2,
            ),
          ),
          Expanded(
            child: MetricTile(
              label: 'إجمالي ما لنا',
              value: data.summary.totalReceivable,
              unit: currencyUnitAr(data.summary.currency),
              decimals: 2,
            ),
          ),
        ],
      ),
    };
    return SectionCard(
      title: 'الأرصدة حتى اليوم',
      icon: Icons.account_balance_wallet_outlined,
      child: body,
    );
  }
}
