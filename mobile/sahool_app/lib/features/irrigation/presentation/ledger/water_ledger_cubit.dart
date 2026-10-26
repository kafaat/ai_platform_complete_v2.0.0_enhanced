// SAHOOL — features/irrigation/presentation/ledger/water_ledger_cubit.dart
// دفتر المياه اليوميّ لحقل: سجلّ آخر 30 يوماً + تسجيل الماء المضاف.
//
// لماذا الدمج: POST water-ledger upsert **يستبدل كلّ أعمدة اليوم** (ON CONFLICT DO
// UPDATE)، وقيد الإنسان يمنع العامل الآليّ من إعادة حساب ذلك اليوم. إرسال
// irrigation_mm وحده كان سيمحو ET0/الاستنزاف/الثقة التي حسبها الخادم لذلك اليوم
// فتنقلب توصية الريّ إلى insufficient_data. لذا نقرأ قيد اليوم أوّلاً ونعيد
// إرسال أعمدته كما هي، ولا نغيّر إلّا irrigation_mm. لا نُعيد حساب الاستنزاف
// محلّيّاً (ليس للعميل أن يخترع ميزاناً).
//
// دون اتّصال: يُودَع الطلب نفسه (المسار والجسم ومفتاح النيّة) في OfflineOutbox
// بنوع 'water_applied'. الإيصال يقول الحقيقة: queued فقط إن حُفظ فعلاً.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/connectivity_status.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_api.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_models.dart';
import 'package:sahool_app/features/irrigation/presentation/irrigation_format.dart'
    show isoDay;
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

const String kWaterAppliedKind = 'water_applied';

/// أقصى ريّ يوميّ مقبول في النموذج (مم). الغمر نادراً ما يتجاوز 150 مم؛ 500 حدّ
/// أمان ضدّ خطأ إدخال (م³ بدل مم مثلاً)، لا قيمة زراعيّة.
const num kMaxDailyIrrigationMm = 500;

enum WaterUnit { mm, m3 }

/// تحقّق إدخال «الماء المضاف». يقبل الأرقام العربيّة-الهنديّة. يُرجع (مم، خطأ).
({num? mm, String? error}) validateAppliedWater(
  String raw, {
  WaterUnit unit = WaterUnit.mm,
  num? areaHa,
}) {
  final text = raw.trim();
  if (text.isEmpty) return (mm: null, error: 'أدخل كمّيّة الماء');
  final v = parseLocalizedNum(text);
  if (v == null) return (mm: null, error: 'أدخل رقماً صالحاً');
  if (v < 0) return (mm: null, error: 'لا تكون الكمّيّة سالبة');
  num mm = v;
  if (unit == WaterUnit.m3) {
    if (areaHa == null || areaHa <= 0) {
      return (
        mm: null,
        error: 'مساحة الحقل غير معروفة — أدخل الكمّيّة بالمليمتر',
      );
    }
    mm = v / (areaHa * 10);
  }
  if (mm > kMaxDailyIrrigationMm) {
    return (
      mm: null,
      error:
          'الكمّيّة تتجاوز ${kMaxDailyIrrigationMm.toInt()} مم في يوم — تحقّق من الوحدة',
    );
  }
  return (mm: double.parse(mm.toStringAsFixed(2)), error: null);
}

/// يبني جسم POST: أعمدة قيد اليوم القائم كما هي + irrigation_mm الجديد.
Map<String, dynamic> mergeLedgerBody(
  String ledgerDate,
  num irrigationMm,
  WaterLedgerEntry? existing,
) {
  final body = <String, dynamic>{'ledger_date': ledgerDate};
  if (existing != null) {
    for (final k in kLedgerWritableKeys) {
      final v = existing.raw[k];
      if (v != null) body[k] = v;
    }
  }
  body['irrigation_mm'] = irrigationMm;
  return body;
}

sealed class WaterLedgerState {
  const WaterLedgerState();
}

class WaterLedgerLoading extends WaterLedgerState {
  const WaterLedgerLoading();
}

class WaterLedgerLoaded extends WaterLedgerState {
  const WaterLedgerLoaded(this.entries, {this.noteAr});

  /// الأحدث أوّلاً.
  final List<WaterLedgerEntry> entries;

  /// ملاحظة الخادم (مثل «القاعدة غير مفعّلة») — تُعرض كما هي.
  final String? noteAr;

  WaterLedgerEntry? forDate(String isoDate) {
    for (final e in entries) {
      if (e.ledgerDate == isoDate) return e;
    }
    return null;
  }
}

class WaterLedgerFailed extends WaterLedgerState {
  const WaterLedgerFailed(this.error);
  final ApiException error;
}

sealed class WaterLogResult {
  const WaterLogResult();
}

/// حفظه الخادم (persisted=true).
class WaterLogSaved extends WaterLogResult {
  const WaterLogSaved();
}

/// لا اتّصال، وأُودِع في صندوق الإرسال فعلاً.
class WaterLogQueued extends WaterLogResult {
  const WaterLogQueued();
}

/// لا اتّصال، ولم يُحفَظ في أيّ مكان (الطابور غير متاح).
class WaterLogNotQueued extends WaterLogResult {
  const WaterLogNotQueued(this.reason);
  final String? reason;
}

/// رفضه الخادم أو فشل لسبب غير الاتّصال.
class WaterLogFailed extends WaterLogResult {
  const WaterLogFailed(this.error);
  final ApiException error;
}

class WaterLedgerCubit extends Cubit<WaterLedgerState> {
  WaterLedgerCubit(
    this._api,
    this.fieldId, {
    bool Function()? isOnline,
    OfflineOutbox Function()? outbox,
    DateTime Function()? now,
  }) : _isOnline = isOnline ?? (() => ConnectivityStatus.instance.isOnline),
       _outbox = outbox ?? (() => OfflineOutbox.instance),
       _now = now ?? DateTime.now,
       super(const WaterLedgerLoading());

  final IrrigationApi _api;
  final String fieldId;
  final bool Function() _isOnline;
  final OfflineOutbox Function() _outbox;
  final DateTime Function() _now;

  static const int historyDays = 30;

  /// «الآن» المحقون (التاريخ الافتراضيّ لنموذج التسجيل).
  DateTime now() => _now();

  Future<void> load() async {
    emit(const WaterLedgerLoading());
    try {
      final today = _now();
      final json = await _api.listWaterLedger(
        fieldId,
        from: isoDay(today.subtract(const Duration(days: historyDays))),
        to: isoDay(today),
      );
      final raw = json['entries'];
      if (raw is! List) {
        throw const FormatException('استجابة دفتر المياه بلا قائمة entries.');
      }
      final entries =
          raw
              .whereType<Map>()
              .map(
                (e) => WaterLedgerEntry.fromJson(Map<String, dynamic>.from(e)),
              )
              .toList()
            ..sort((a, b) => b.ledgerDate.compareTo(a.ledgerDate));
      if (isClosed) return;
      emit(WaterLedgerLoaded(entries, noteAr: json['note_ar']?.toString()));
    } catch (e) {
      if (!isClosed) emit(WaterLedgerFailed(ApiException.from(e)));
    }
  }

  WaterLedgerEntry? _cached(String date) {
    final s = state;
    return s is WaterLedgerLoaded ? s.forDate(date) : null;
  }

  /// يسجّل [irrigationMm] إجماليّاً ليوم [ledgerDate]. [key] ثابت لنيّة المستخدم
  /// (يُولَّد عند فتح النموذج) فتكون إعادة الإرسال والإيداع نفس الفعل.
  Future<WaterLogResult> logAppliedWater({
    required String ledgerDate,
    required num irrigationMm,
    required IdempotencyKey key,
  }) async {
    if (!_isOnline()) {
      return _enqueue(
        mergeLedgerBody(ledgerDate, irrigationMm, _cached(ledgerDate)),
        key,
        ledgerDate,
        irrigationMm,
      );
    }
    // اقرأ قيد اليوم من الخادم الآن (قد يكون العامل كتبه بعد آخر تحميل).
    WaterLedgerEntry? existing;
    try {
      final json = await _api.listWaterLedger(
        fieldId,
        from: ledgerDate,
        to: ledgerDate,
      );
      final raw = json['entries'];
      if (raw is List) {
        for (final e in raw.whereType<Map>()) {
          final entry = WaterLedgerEntry.fromJson(Map<String, dynamic>.from(e));
          if (entry.ledgerDate == ledgerDate) existing = entry;
        }
      }
    } catch (e) {
      final err = ApiException.from(e);
      if (err.isConnectivity) {
        return _enqueue(
          mergeLedgerBody(ledgerDate, irrigationMm, _cached(ledgerDate)),
          key,
          ledgerDate,
          irrigationMm,
        );
      }
      return WaterLogFailed(err);
    }
    final body = mergeLedgerBody(ledgerDate, irrigationMm, existing);
    try {
      final res = await _api.upsertWaterLedger(
        fieldId,
        body,
        idempotencyKey: key,
      );
      if (res['persisted'] != true) {
        return const WaterLogFailed(
          ApiException(
            kind: ApiErrorKind.unknown,
            messageAr: 'لم يؤكّد الخادم حفظ القيد.',
          ),
        );
      }
    } catch (e) {
      final err = ApiException.from(e);
      if (err.isConnectivity) {
        return _enqueue(body, key, ledgerDate, irrigationMm);
      }
      return WaterLogFailed(err);
    }
    await load();
    return const WaterLogSaved();
  }

  Future<WaterLogResult> _enqueue(
    Map<String, dynamic> body,
    IdempotencyKey key,
    String ledgerDate,
    num irrigationMm,
  ) async {
    try {
      final receipt = await _outbox().enqueue(
        OutboxOp(
          kind: kWaterAppliedKind,
          method: 'POST',
          path: IrrigationApi.waterLedgerPath(fieldId),
          body: body,
          idempotencyKey: key.value,
          fieldId: fieldId,
          labelAr: 'ريّ ${fmtMm(irrigationMm)} — $ledgerDate',
        ),
      );
      return receipt.queued
          ? const WaterLogQueued()
          : WaterLogNotQueued(receipt.reason);
    } catch (e) {
      return WaterLogNotQueued(e.toString());
    }
  }
}
