// SAHOOL — features/farm_book/data/farm_book_models.dart
// نماذج دفتر المزرعة كما يردّها simple_farm_book.py حرفيّاً. حقل لازم ناقص ⇒
// FormatException (تُعرض خطأً)، لا قيمة مُختلَقة. الأرقام تُقرأ كما هي من الخادم؛
// الإجماليّات لا تُحسب هنا أبداً (الخادم وحده يصافي القيود وعكوسها).

String _req(Map<String, dynamic> j, String key) {
  final v = j[key];
  if (v is String && v.isNotEmpty) return v;
  throw FormatException('استجابة دفتر المزرعة ينقصها الحقل «$key».');
}

String? _opt(Map<String, dynamic> j, String key) {
  final v = j[key];
  if (v == null) return null;
  final s = v.toString();
  return s.isEmpty ? null : s;
}

num? _num(Map<String, dynamic> j, String key) {
  final v = j[key];
  if (v is num) return v;
  if (v is String) return num.tryParse(v);
  return null;
}

/// طرف: مورد أو عميل أو كلاهما (party_type: supplier|customer|both).
class FarmBookParty {
  const FarmBookParty({
    required this.partyId,
    required this.partyType,
    required this.name,
    this.phone,
    this.notes,
    this.createdAt,
  });

  factory FarmBookParty.fromJson(Map<String, dynamic> j) => FarmBookParty(
    partyId: _req(j, 'party_id'),
    partyType: _req(j, 'party_type'),
    name: _req(j, 'name'),
    phone: _opt(j, 'phone'),
    notes: _opt(j, 'notes'),
    createdAt: _opt(j, 'created_at'),
  );

  final String partyId;
  final String partyType;
  final String name;
  final String? phone;
  final String? notes;
  final String? createdAt;
}

/// قيد واحد (صفّ farm_ledger_entries + party_name + settled_entry_type).
class FarmBookEntry {
  const FarmBookEntry({
    required this.entryId,
    required this.entryType,
    required this.paymentMethod,
    required this.category,
    required this.amount,
    required this.currency,
    required this.occurredOn,
    this.direction,
    this.farmId,
    this.fieldId,
    this.seasonId,
    this.partyId,
    this.partyName,
    this.settlesEntryId,
    this.settledEntryType,
    this.reversesEntryId,
    this.description,
    this.createdAt,
  });

  factory FarmBookEntry.fromJson(Map<String, dynamic> j) {
    final amount = _num(j, 'amount');
    if (amount == null) {
      throw const FormatException('استجابة دفتر المزرعة ينقصها مبلغ القيد.');
    }
    return FarmBookEntry(
      entryId: _req(j, 'entry_id'),
      entryType: _req(j, 'entry_type'),
      paymentMethod: _req(j, 'payment_method'),
      category: _req(j, 'category'),
      amount: amount,
      currency: _req(j, 'currency'),
      occurredOn: _req(j, 'occurred_on'),
      direction: _opt(j, 'direction'),
      farmId: _opt(j, 'farm_id'),
      fieldId: _opt(j, 'field_id'),
      seasonId: _opt(j, 'season_id'),
      partyId: _opt(j, 'party_id'),
      partyName: _opt(j, 'party_name'),
      settlesEntryId: _opt(j, 'settles_entry_id'),
      settledEntryType: _opt(j, 'settled_entry_type'),
      reversesEntryId: _opt(j, 'reverses_entry_id'),
      description: _opt(j, 'description'),
      createdAt: _opt(j, 'created_at'),
    );
  }

  final String entryId;

  /// expense | income | payment
  final String entryType;

  /// cash | credit
  final String paymentMethod;
  final String category;
  final num amount;
  final String currency;

  /// YYYY-MM-DD
  final String occurredOn;
  final String? direction;
  final String? farmId;
  final String? fieldId;
  final String? seasonId;
  final String? partyId;
  final String? partyName;
  final String? settlesEntryId;
  final String? settledEntryType;
  final String? reversesEntryId;
  final String? description;
  final String? createdAt;

  bool get isReversal => reversesEntryId != null;
  bool get isPayment => entryType == 'payment';
  bool get isCredit => paymentMethod == 'credit';
}

/// ردّ POST /entries.
class FarmBookWriteReceipt {
  const FarmBookWriteReceipt({
    required this.entryId,
    required this.persisted,
    required this.replayed,
  });

  factory FarmBookWriteReceipt.fromJson(Map<String, dynamic> j) =>
      FarmBookWriteReceipt(
        entryId: _req(j, 'entry_id'),
        persisted: j['persisted'] == true,
        replayed: j['replayed'] == true,
      );

  final String entryId;
  final bool persisted;
  final bool replayed;
}

/// ملخّص summarize_entries كما يحسبه الخادم. [status]: ok | multiple_currencies.
class FarmBookSummary {
  const FarmBookSummary({
    required this.status,
    this.currency,
    this.currencies = const [],
    this.entriesCount,
    this.totalExpenses,
    this.totalIncome,
    this.net,
    this.cashBalanceEffect,
    this.totalPayable,
    this.totalReceivable,
    this.expenseBreakdown = const {},
    this.incomeBreakdown = const {},
    this.perHectare,
  });

  factory FarmBookSummary.fromJson(Map<String, dynamic> j) {
    Map<String, num> breakdown(String key) {
      final v = j[key];
      if (v is! Map) return const {};
      return {
        for (final e in v.entries)
          if (e.value is num) e.key.toString(): e.value as num,
      };
    }

    final ph = j['per_hectare'];
    return FarmBookSummary(
      status: _req(j, 'status'),
      currency: _opt(j, 'currency'),
      currencies: (j['currencies'] is List)
          ? (j['currencies'] as List).map((e) => e.toString()).toList()
          : const [],
      entriesCount: _num(j, 'entries_count')?.toInt(),
      totalExpenses: _num(j, 'total_expenses'),
      totalIncome: _num(j, 'total_income'),
      net: _num(j, 'net'),
      cashBalanceEffect: _num(j, 'cash_balance_effect'),
      totalPayable: _num(j, 'total_payable'),
      totalReceivable: _num(j, 'total_receivable'),
      expenseBreakdown: breakdown('expense_breakdown'),
      incomeBreakdown: breakdown('income_breakdown'),
      perHectare: ph is Map
          ? {
              for (final e in ph.entries)
                if (e.value is num) e.key.toString(): e.value as num,
            }
          : null,
    );
  }

  final String status;
  final String? currency;
  final List<String> currencies;
  final int? entriesCount;
  final num? totalExpenses;
  final num? totalIncome;
  final num? net;
  final num? cashBalanceEffect;
  final num? totalPayable;
  final num? totalReceivable;
  final Map<String, num> expenseBreakdown;
  final Map<String, num> incomeBreakdown;

  /// موجود فقط حين يُطلب التقرير لحقل له مساحة.
  final Map<String, num>? perHectare;

  bool get isOk => status == 'ok';
  bool get isMultipleCurrencies => status == 'multiple_currencies';
}

/// ردّ GET /monthly: {month, summary}.
class FarmBookMonthly {
  const FarmBookMonthly({required this.month, required this.summary});

  factory FarmBookMonthly.fromJson(Map<String, dynamic> j) {
    final s = j['summary'];
    if (s is! Map) {
      throw const FormatException('استجابة التقرير الشهريّ بلا ملخّص.');
    }
    return FarmBookMonthly(
      month: _req(j, 'month'),
      summary: FarmBookSummary.fromJson(s.cast<String, dynamic>()),
    );
  }

  final String month;
  final FarmBookSummary summary;
}

/// ردّ GET /balances: {as_of, summary}.
class FarmBookBalances {
  const FarmBookBalances({required this.asOf, required this.summary});

  factory FarmBookBalances.fromJson(Map<String, dynamic> j) {
    final s = j['summary'];
    if (s is! Map) {
      throw const FormatException('استجابة الأرصدة بلا ملخّص.');
    }
    return FarmBookBalances(
      asOf: _opt(j, 'as_of'),
      summary: FarmBookSummary.fromJson(s.cast<String, dynamic>()),
    );
  }

  final String? asOf;
  final FarmBookSummary summary;
}

/// شهر تقويميّ (YYYY-MM) — نافذة التقرير والقائمة.
class YearMonth implements Comparable<YearMonth> {
  const YearMonth(this.year, this.month) : assert(month >= 1 && month <= 12);

  factory YearMonth.of(DateTime d) => YearMonth(d.year, d.month);

  final int year;
  final int month;

  YearMonth get next =>
      month == 12 ? YearMonth(year + 1, 1) : YearMonth(year, month + 1);
  YearMonth get previous =>
      month == 1 ? YearMonth(year - 1, 12) : YearMonth(year, month - 1);

  /// «2026-03» كما يتوقّعه الخادم.
  String get key => '$year-${month.toString().padLeft(2, '0')}';

  /// أوّل يوم (شامل).
  String get firstDay => '$key-01';

  /// آخر يوم (شامل) — لـ`to` في /entries.
  String get lastDay {
    final last = DateTime(year, month + 1, 0).day;
    return '$key-${last.toString().padLeft(2, '0')}';
  }

  @override
  int compareTo(YearMonth other) =>
      year != other.year ? year - other.year : month - other.month;

  @override
  bool operator ==(Object other) =>
      other is YearMonth && other.year == year && other.month == month;

  @override
  int get hashCode => Object.hash(year, month);

  @override
  String toString() => key;
}

/// تاريخ محلّيّ بصيغة YYYY-MM-DD (occurred_on/as_of).
String isoDay(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}'
    '-${d.day.toString().padLeft(2, '0')}';
