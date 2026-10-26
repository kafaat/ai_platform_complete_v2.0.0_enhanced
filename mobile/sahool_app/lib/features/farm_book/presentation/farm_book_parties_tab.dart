// SAHOOL — features/farm_book/presentation/farm_book_parties_tab.dart
// الأطراف (موردون وعملاء) وإضافة طرف. الخادم يردّ إجماليّ ما علينا/ما لنا فقط؛
// رصيد كلّ طرف على حدة غير متاح بعد منه، فنقول ذلك بدل حسابه محلّيّاً.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/farm_book_models.dart';
import 'farm_book_cubit.dart';
import 'farm_book_report_tab.dart';
import 'farm_book_state.dart';
import 'farm_book_text.dart';

const String kPerPartyBalanceUnavailableAr =
    'رصيد كلّ طرف على حدة غير متاح بعد من الخادم؛ المعروض أعلاه إجماليّ الأطراف.';

class FarmBookPartiesTab extends StatelessWidget {
  const FarmBookPartiesTab({super.key});

  @override
  Widget build(BuildContext context) {
    return BlocBuilder<FarmBookCubit, FarmBookState>(
      builder: (context, state) {
        final cubit = context.read<FarmBookCubit>();
        final parties = state.parties;
        final header = <Widget>[
          if (cubit.access.canReport) BalancesCard(section: state.balances),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: SahoolSpacing.sm),
            child: Text(
              kPerPartyBalanceUnavailableAr,
              style: context.textStyles.bodySmall?.copyWith(
                color: context.tokens.muted,
              ),
            ),
          ),
          if (cubit.access.canWrite)
            SecondaryButton(
              label: 'إضافة مورد أو عميل',
              icon: Icons.person_add_alt_1_outlined,
              onPressed: () => openPartySheet(context, cubit),
            ),
          const SizedBox(height: SahoolSpacing.sm),
        ];
        final List<Widget> body = switch (parties) {
          SectionLoading() || SectionNotAllowed() => const [
            Padding(
              padding: EdgeInsets.all(SahoolSpacing.xl),
              child: LoadingState(),
            ),
          ],
          SectionFailed(:final error) => [
            ErrorState(error: error, onRetry: cubit.loadParties),
          ],
          SectionLoaded(:final data) when data.isEmpty => const [
            EmptyState(
              icon: Icons.people_outline_rounded,
              message: 'لا موردين ولا عملاء بعد.',
            ),
          ],
          SectionLoaded(:final data) => [
            for (final p in data)
              AppListTile(
                title: p.name,
                subtitle: [
                  partyTypeLabel(p.partyType),
                  if (p.phone != null) p.phone!,
                ].join(' · '),
                icon: p.partyType == 'customer'
                    ? Icons.storefront_outlined
                    : Icons.local_shipping_outlined,
              ),
          ],
        };
        return RefreshIndicator(
          onRefresh: cubit.loadParties,
          child: ListView(
            padding: const EdgeInsetsDirectional.fromSTEB(
              SahoolSpacing.page,
              SahoolSpacing.sm,
              SahoolSpacing.page,
              SahoolSpacing.xxl * 3,
            ),
            children: [...header, ...body],
          ),
        );
      },
    );
  }
}

/// يفتح نموذج طرف جديد ويُرجع الطرف المحفوظ (أو null عند الإلغاء).
Future<FarmBookParty?> openPartySheet(
  BuildContext context,
  FarmBookCubit cubit,
) => showAppBottomSheet<FarmBookParty>(
  context,
  builder: (_) => PartyFormSheet(cubit: cubit),
);

class PartyFormSheet extends StatefulWidget {
  const PartyFormSheet({super.key, required this.cubit});
  final FarmBookCubit cubit;

  @override
  State<PartyFormSheet> createState() => _PartyFormSheetState();
}

class _PartyFormSheetState extends State<PartyFormSheet> {
  final IdempotencyKey _key = IdempotencyKey.generate();
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _phone = TextEditingController();
  String _type = 'supplier';
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_submitting || !(_form.currentState?.validate() ?? false)) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      final party = await widget.cubit.createParty(
        name: _name.text,
        partyType: _type,
        phone: _phone.text,
        key: _key,
      );
      if (mounted) Navigator.of(context).pop(party);
    } on Object catch (e) {
      if (!mounted) return;
      setState(() {
        _submitting = false;
        _error = farmBookErrorMessage(e);
      });
    }
  }

  @override
  Widget build(BuildContext context) => Form(
    key: _form,
    child: AppSheet(
      title: 'مورد أو عميل جديد',
      submitLabel: 'حفظ الطرف',
      submitting: _submitting,
      errorText: _error,
      onSubmit: _submit,
      children: [
        AppTextField(
          label: 'الاسم',
          controller: _name,
          textInputAction: TextInputAction.next,
          validator: (v) {
            final s = v?.trim() ?? '';
            if (s.isEmpty) return 'أدخل الاسم';
            if (s.length > 160) return 'الاسم أطول من المسموح';
            return null;
          },
        ),
        AppDropdown<String>(
          label: 'النوع',
          items: kPartyTypes,
          value: _type,
          onChanged: (v) => setState(() => _type = v ?? _type),
        ),
        AppTextField(
          label: 'الهاتف (اختياريّ)',
          controller: _phone,
          keyboardType: TextInputType.phone,
          inputFormatters: const [LocalizedDigitsFormatter()],
          validator: (v) => (v?.trim().length ?? 0) > 40
              ? 'رقم الهاتف أطول من المسموح'
              : null,
        ),
      ],
    ),
  );
}
