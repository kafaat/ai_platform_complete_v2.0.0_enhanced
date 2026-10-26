// SAHOOL — features/farm_book/presentation/farm_book_state.dart
// حالة شاشة دفتر المزرعة: كلّ قسم (المزارع، الحقول، القيود، التقرير، الأرصدة،
// الأطراف) له حالته الصريحة — تحميل / محمَّل / فشل بـApiException / غير مسموح
// للدور — فلا يُعرض قسم فاشل كقائمة فارغة ولا تقرير ممنوع كأصفار.
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/permissions/permissions.dart';

import '../data/farm_book_models.dart';

sealed class Section<T> {
  const Section();
}

class SectionLoading<T> extends Section<T> {
  const SectionLoading();
}

class SectionLoaded<T> extends Section<T> {
  const SectionLoaded(this.data);
  final T data;
}

class SectionFailed<T> extends Section<T> {
  const SectionFailed(this.error);
  final ApiException error;
}

/// الخادم يرفض هذا القسم لدور المستخدم؛ لا نطلبه أصلاً.
class SectionNotAllowed<T> extends Section<T> {
  const SectionNotAllowed();
}

/// ما يسمح به الخادم لكلّ دور (core/authorization.py):
/// كتابة = ACTIVITY_EXECUTE (مالك/مدير/عامل)، تقارير = ANALYTICS_VIEW
/// (مالك/مدير/مهندس). المُشاهِد لا يصل إلى الشاشة أصلاً (allowedRoles).
class FarmBookAccess {
  const FarmBookAccess({required this.canWrite, required this.canReport});

  factory FarmBookAccess.forRole(AppRole role) => FarmBookAccess(
    canWrite:
        role == AppRole.owner ||
        role == AppRole.manager ||
        role == AppRole.worker,
    canReport:
        role == AppRole.owner ||
        role == AppRole.manager ||
        role == AppRole.agronomist,
  );

  final bool canWrite;
  final bool canReport;
}

/// خيار مزرعة/حقل للاختيار.
class FarmBookOption {
  const FarmBookOption(this.id, this.name, {this.currency});
  final String id;
  final String name;
  final String? currency;
}

class FarmBookState {
  const FarmBookState({
    required this.month,
    this.farms = const SectionLoading(),
    this.farmId,
    this.fields = const SectionLoading(),
    this.fieldId,
    this.entries = const SectionLoading(),
    this.report = const SectionLoading(),
    this.balances = const SectionLoading(),
    this.parties = const SectionLoading(),
  });

  final YearMonth month;
  final Section<List<FarmBookOption>> farms;
  final String? farmId;
  final Section<List<FarmBookOption>> fields;

  /// null ⇒ كلّ الحقول.
  final String? fieldId;
  final Section<List<FarmBookEntry>> entries;
  final Section<FarmBookMonthly> report;
  final Section<FarmBookBalances> balances;
  final Section<List<FarmBookParty>> parties;

  FarmBookOption? get farm {
    final f = farms;
    if (f is! SectionLoaded<List<FarmBookOption>>) return null;
    for (final o in f.data) {
      if (o.id == farmId) return o;
    }
    return null;
  }

  List<FarmBookOption> get fieldOptions {
    final f = fields;
    return f is SectionLoaded<List<FarmBookOption>> ? f.data : const [];
  }

  List<FarmBookParty> get partyList {
    final p = parties;
    return p is SectionLoaded<List<FarmBookParty>> ? p.data : const [];
  }

  /// معرّفات القيود التي عُكست ضمن القائمة المحمَّلة.
  Set<String> get reversedIds {
    final e = entries;
    if (e is! SectionLoaded<List<FarmBookEntry>>) return const {};
    return {
      for (final x in e.data)
        if (x.reversesEntryId != null) x.reversesEntryId!,
    };
  }

  FarmBookState copyWith({
    YearMonth? month,
    Section<List<FarmBookOption>>? farms,
    String? Function()? farmId,
    Section<List<FarmBookOption>>? fields,
    String? Function()? fieldId,
    Section<List<FarmBookEntry>>? entries,
    Section<FarmBookMonthly>? report,
    Section<FarmBookBalances>? balances,
    Section<List<FarmBookParty>>? parties,
  }) => FarmBookState(
    month: month ?? this.month,
    farms: farms ?? this.farms,
    farmId: farmId != null ? farmId() : this.farmId,
    fields: fields ?? this.fields,
    fieldId: fieldId != null ? fieldId() : this.fieldId,
    entries: entries ?? this.entries,
    report: report ?? this.report,
    balances: balances ?? this.balances,
    parties: parties ?? this.parties,
  );
}

/// نتيجة كتابة (قيد أو عكس).
sealed class FarmBookWriteOutcome {
  const FarmBookWriteOutcome();
}

class WriteSaved extends FarmBookWriteOutcome {
  const WriteSaved(this.receipt);
  final FarmBookWriteReceipt receipt;
}

/// لا اتّصال، وحُفظت العمليّة فعلاً في صندوق الإرسال بالمفتاح نفسه.
class WriteQueued extends FarmBookWriteOutcome {
  const WriteQueued();
}

class WriteFailed extends FarmBookWriteOutcome {
  const WriteFailed(this.error, this.messageAr);
  final ApiException error;
  final String messageAr;
}
