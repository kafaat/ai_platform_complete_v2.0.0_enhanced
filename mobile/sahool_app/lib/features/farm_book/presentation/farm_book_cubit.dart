// SAHOOL — features/farm_book/presentation/farm_book_cubit.dart
// منطق شاشة دفتر المزرعة: اختيار المزرعة/الحقل/الشهر، تحميل القيود والتقرير
// والأرصدة والأطراف من الخادم، وكتابة القيود والعكوس والأطراف بمفتاح ثابت للنيّة.
//
// صدق الأرقام: الإجماليّات تأتي من /monthly و/balances فقط؛ لا يجمع التطبيق قيوداً
// بنفسه. التصحيح عكسٌ لا تعديل (الخادم لا يملك PUT/DELETE للقيود): قيد مرآة يحمل
// reverses_entry_id، ويصافيه الخادم مع الأصل — وإن وقع العكس في شهر آخر احتُسب
// سالباً في شهره هو.
import 'dart:async';

import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/farms/data/farms_api.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

import '../data/farm_book_api.dart';
import '../data/farm_book_models.dart';
import 'farm_book_state.dart';
import 'farm_book_text.dart';

/// ما يكتبه المستخدم في نموذج القيد، بعد التحقّق.
class FarmBookEntryDraft {
  const FarmBookEntryDraft({
    required this.entryType,
    required this.paymentMethod,
    required this.category,
    required this.amount,
    required this.occurredOn,
    this.fieldId,
    this.partyId,
    this.settles,
    this.description,
  });

  /// expense | income | payment
  final String entryType;

  /// cash | credit (السداد نقديّ دائماً).
  final String paymentMethod;
  final String category;

  /// نصّ عشريّ مطبَّع (normalizeAmount).
  final String amount;

  /// YYYY-MM-DD
  final String occurredOn;
  final String? fieldId;
  final String? partyId;

  /// القيد الآجل الذي يسدّده هذا السداد.
  final FarmBookEntry? settles;
  final String? description;
}

class FarmBookCubit extends Cubit<FarmBookState> {
  FarmBookCubit({
    required FarmBookApi api,
    required this.access,
    FarmsApi? farmsApi,
    FieldsApi? fieldsApi,
    OfflineOutbox Function()? outbox,
    DateTime Function()? now,
  }) : _api = api,
       _farmsApi = farmsApi ?? FarmsApi.instance,
       _fieldsApi = fieldsApi ?? FieldsApi.instance,
       _outbox = outbox ?? (() => OfflineOutbox.instance),
       _now = now ?? DateTime.now,
       super(FarmBookState(month: YearMonth.of((now ?? DateTime.now)())));

  final FarmBookApi _api;
  final FarmsApi _farmsApi;
  final FieldsApi _fieldsApi;
  final OfflineOutbox Function() _outbox;
  final DateTime Function() _now;
  final FarmBookAccess access;

  static const _entriesPath = '/api/v1/farm-book/entries';

  int _bookGen = 0;
  int _fieldsGen = 0;

  YearMonth get currentMonth => YearMonth.of(_now());
  String get today => isoDay(_now());

  void _emit(FarmBookState s) {
    if (!isClosed) emit(s);
  }

  /// التحميل الأوّل (وإعادة المحاولة الكاملة).
  Future<void> load() async {
    _emit(
      state.copyWith(
        farms: const SectionLoading(),
        parties: const SectionLoading(),
      ),
    );
    unawaited(loadParties());
    try {
      final rows = await _farmsApi.listFarms();
      final farms = [
        for (final r in rows)
          if (r['farm_id'] != null)
            FarmBookOption(
              r['farm_id'].toString(),
              (r['name'] ?? r['farm_id']).toString(),
              currency: r['currency']?.toString(),
            ),
      ];
      final keep = farms.any((f) => f.id == state.farmId);
      final farmId = keep
          ? state.farmId
          : (farms.isEmpty ? null : farms.first.id);
      _emit(state.copyWith(farms: SectionLoaded(farms), farmId: () => farmId));
      if (farmId == null) return;
      unawaited(_loadFields());
      await loadBook();
    } on Object catch (e) {
      _emit(state.copyWith(farms: SectionFailed(ApiException.from(e))));
    }
  }

  Future<void> loadParties() async {
    _emit(state.copyWith(parties: const SectionLoading()));
    try {
      final list = await _api.listParties();
      _emit(state.copyWith(parties: SectionLoaded(list)));
    } on Object catch (e) {
      _emit(state.copyWith(parties: SectionFailed(ApiException.from(e))));
    }
  }

  Future<void> _loadFields() async {
    final gen = ++_fieldsGen;
    final farmId = state.farmId;
    _emit(state.copyWith(fields: const SectionLoading()));
    try {
      final rows = await _fieldsApi.listFields();
      if (gen != _fieldsGen) return;
      final fields = [
        for (final r in rows)
          if (r['field_id'] != null && r['farm_id']?.toString() == farmId)
            FarmBookOption(
              r['field_id'].toString(),
              (r['name_ar'] ?? r['name'] ?? r['field_id']).toString(),
            ),
      ];
      _emit(state.copyWith(fields: SectionLoaded(fields)));
    } on Object catch (e) {
      if (gen != _fieldsGen) return;
      _emit(state.copyWith(fields: SectionFailed(ApiException.from(e))));
    }
  }

  Future<void> selectFarm(String farmId) async {
    if (farmId == state.farmId) return;
    _emit(state.copyWith(farmId: () => farmId, fieldId: () => null));
    unawaited(_loadFields());
    await loadBook();
  }

  Future<void> selectField(String? fieldId) async {
    if (fieldId == state.fieldId) return;
    _emit(state.copyWith(fieldId: () => fieldId));
    await loadBook();
  }

  Future<void> setMonth(YearMonth month) async {
    if (month == state.month || month.compareTo(currentMonth) > 0) return;
    _emit(state.copyWith(month: month));
    await loadBook();
  }

  /// القيود + التقرير الشهريّ + الأرصدة للنافذة الحاليّة. نتيجة متأخّرة لاختيار
  /// سابق (تبديل مزرعة سريع) تُهمَل.
  Future<void> loadBook() async {
    final farmId = state.farmId;
    if (farmId == null) return;
    final gen = ++_bookGen;
    final month = state.month;
    final fieldId = state.fieldId;
    _emit(
      state.copyWith(
        entries: const SectionLoading(),
        report: access.canReport
            ? const SectionLoading()
            : const SectionNotAllowed(),
        balances: access.canReport
            ? const SectionLoading()
            : const SectionNotAllowed(),
      ),
    );

    Future<void> run<T>(
      Future<T> Function() call,
      FarmBookState Function(Section<T>) apply,
    ) async {
      Section<T> s;
      try {
        s = SectionLoaded(await call());
      } on Object catch (e) {
        s = SectionFailed(ApiException.from(e));
      }
      if (gen == _bookGen) _emit(apply(s));
    }

    await Future.wait([
      run<List<FarmBookEntry>>(
        () => _api.listEntries(
          farmId: farmId,
          fieldId: fieldId,
          from: month.firstDay,
          to: month.lastDay,
        ),
        (s) => state.copyWith(entries: s),
      ),
      if (access.canReport)
        run<FarmBookMonthly>(
          () =>
              _api.monthly(month: month.key, farmId: farmId, fieldId: fieldId),
          (s) => state.copyWith(report: s),
        ),
      if (access.canReport)
        run<FarmBookBalances>(
          () => _api.balances(farmId: farmId, fieldId: fieldId, asOf: today),
          (s) => state.copyWith(balances: s),
        ),
    ]);
  }

  /// قيود آجلة مفتوحة للسداد (كلّ تاريخ المزرعة، أحدث 2000 من الخادم): ليست
  /// سداداً ولا عكساً ولا معكوسة. المتبقّي عليها يتحقّق منه الخادم (409).
  Future<List<FarmBookEntry>> openCreditEntries() async {
    final farmId = state.farmId;
    if (farmId == null) return const [];
    final all = await _api.listEntries(farmId: farmId);
    final reversed = {
      for (final e in all)
        if (e.reversesEntryId != null) e.reversesEntryId!,
    };
    return [
      for (final e in all)
        if (e.isCredit &&
            !e.isPayment &&
            !e.isReversal &&
            !reversed.contains(e.entryId))
          e,
    ];
  }

  String _currencyFor(FarmBookOption? farm) {
    final c = farm?.currency?.toUpperCase();
    return (c != null && RegExp(r'^[A-Z]{3}$').hasMatch(c)) ? c : 'YER';
  }

  /// جسم POST /entries لقيد جديد.
  Map<String, dynamic> entryBody(FarmBookEntryDraft d) {
    final isPayment = d.entryType == 'payment';
    return {
      'entry_type': d.entryType,
      'payment_method': isPayment ? 'cash' : d.paymentMethod,
      'category': isPayment ? kPaymentCategory : d.category,
      'amount': d.amount,
      'currency': isPayment && d.settles != null
          ? d.settles!.currency
          : _currencyFor(state.farm),
      'occurred_on': d.occurredOn,
      'farm_id': state.farmId,
      if (d.fieldId != null) 'field_id': d.fieldId,
      if ((isPayment ? d.settles?.partyId : d.partyId) != null)
        'party_id': isPayment ? d.settles!.partyId : d.partyId,
      if (isPayment && d.settles != null)
        'settles_entry_id': d.settles!.entryId,
      if (d.description != null && d.description!.trim().isNotEmpty)
        'description': d.description!.trim(),
      'source': 'manual_mobile',
    };
  }

  /// جسم القيد العكسي: مرآة الأصل (النوع/الدفع/المبلغ/العملة/الطرف) كما يشترط
  /// _assert_reversal، بتاريخ اليوم (أو تاريخ الأصل إن كان لاحقاً لليوم) فيصافيه
  /// الخادم في نافذة اليوم إن كان الأصل في شهر سابق.
  Map<String, dynamic> reversalBody(FarmBookEntry original) {
    final t = today;
    final date = original.occurredOn.compareTo(t) > 0 ? original.occurredOn : t;
    return {
      'entry_type': original.entryType,
      'payment_method': original.paymentMethod,
      'category': original.category,
      'amount': original.amount.toStringAsFixed(2),
      'currency': original.currency,
      'occurred_on': date,
      'farm_id': original.farmId ?? state.farmId,
      if (original.fieldId != null) 'field_id': original.fieldId,
      if (original.seasonId != null) 'season_id': original.seasonId,
      if (original.partyId != null) 'party_id': original.partyId,
      'reverses_entry_id': original.entryId,
      'description': 'تصحيح: عكس قيد ${original.occurredOn}',
      'source': 'manual_mobile',
    };
  }

  Future<FarmBookWriteOutcome> submitEntry(
    FarmBookEntryDraft draft,
    IdempotencyKey key,
  ) => _write(
    entryBody(draft),
    key,
    kind: 'farm_book_entry',
    labelAr:
        '${entryTypeLabel(draft.entryType)}: '
        '${categoryLabel(draft.category)}',
    fieldId: draft.fieldId,
  );

  /// يعكس [original]. يرفض محلّيّاً ما يرفضه الخادم حتماً (سداد، عكس، معكوس).
  Future<FarmBookWriteOutcome> reverse(
    FarmBookEntry original,
    IdempotencyKey key,
  ) async {
    final local = reversalBlockReason(original);
    if (local != null) {
      return WriteFailed(
        ApiException(kind: ApiErrorKind.validation, messageAr: local),
        local,
      );
    }
    return _write(
      reversalBody(original),
      key,
      kind: 'farm_book_reversal',
      labelAr: 'عكس ${categoryLabel(original.category)}',
      fieldId: original.fieldId,
    );
  }

  /// لماذا لا يُعكس هذا القيد (null ⇒ يُعكس).
  String? reversalBlockReason(FarmBookEntry e) {
    if (e.isPayment) return 'لا يمكن عكس قيد سداد.';
    if (e.isReversal) return 'لا يمكن عكس قيد عكسي.';
    if (state.reversedIds.contains(e.entryId)) {
      return 'هذا القيد عُكس من قبل؛ لا يُعكس مرّتين.';
    }
    return null;
  }

  Future<FarmBookWriteOutcome> _write(
    Map<String, dynamic> body,
    IdempotencyKey key, {
    required String kind,
    required String labelAr,
    String? fieldId,
  }) async {
    try {
      final receipt = await _api.createEntry(body, idempotencyKey: key);
      unawaited(loadBook());
      return WriteSaved(receipt);
    } on Object catch (error) {
      final e = ApiException.from(error);
      if (e.isConnectivity) {
        final receipt = await _outbox().enqueue(
          OutboxOp(
            kind: kind,
            method: 'POST',
            path: _entriesPath,
            body: {...body, 'client_operation_id': key.value},
            idempotencyKey: key.value,
            fieldId: fieldId,
            labelAr: labelAr,
          ),
        );
        if (receipt.queued) return const WriteQueued();
        return WriteFailed(
          e,
          '${e.messageAr} لم يُحفظ القيد: الحفظ دون اتّصال غير متاح بعد.',
        );
      }
      return WriteFailed(e, farmBookErrorMessage(e));
    }
  }

  /// ينشئ طرفاً. [key] ثابت للنيّة، ومنه party_id الثابت فتكون الإعادة آمنة.
  Future<FarmBookParty> createParty({
    required String name,
    required String partyType,
    String? phone,
    String? notes,
    required IdempotencyKey key,
  }) async {
    final hex = key.value.replaceAll('-', '');
    final party = await _api.createParty({
      'party_id': 'party_${hex.substring(hex.length - 16)}',
      'party_type': partyType,
      'name': name.trim(),
      if (phone != null && phone.trim().isNotEmpty) 'phone': phone.trim(),
      if (notes != null && notes.trim().isNotEmpty) 'notes': notes.trim(),
    }, idempotencyKey: key);
    final list = [
      ...state.partyList.where((p) => p.partyId != party.partyId),
      party,
    ]..sort((a, b) => a.name.compareTo(b.name));
    _emit(state.copyWith(parties: SectionLoaded(list)));
    return party;
  }

  Future<FarmBookExport> export(String format) {
    final farmId = state.farmId;
    return _api.export(
      month: state.month.key,
      format: format,
      farmId: farmId,
      fieldId: state.fieldId,
    );
  }
}
