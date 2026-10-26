// SAHOOL — features/advisor/presentation/advisor_chat_cubit.dart
// حالة محادثة المستشار: السجلّ المشفّر لكلّ مستخدم، الإرسال (واحد في كلّ مرّة)،
// الخطأ الصادق مع «أعد المحاولة» دون تكرار سؤال المستخدم، وسياق الحقل.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/advisor/data/advisor_api.dart';
import 'package:sahool_app/features/advisor/data/advisor_models.dart';
import 'package:sahool_app/features/advisor/data/chat_history_store.dart';

/// حدّ الخادم لطول السؤال (AdvisorQuery.question max_length=4000).
const int kMaxQuestionLength = 4000;

/// سؤال فشل إرساله — يُعاد كما هو (نفس الحقل) دون إضافة رسالة مستخدم ثانية.
class FailedAsk {
  const FailedAsk({required this.question, required this.error, this.fieldId});
  final String question;
  final String? fieldId;
  final ApiException error;
}

class AdvisorChatState {
  const AdvisorChatState({
    this.loadingHistory = true,
    this.persistent = false,
    this.messages = const [],
    this.sending = false,
    this.failure,
    this.fieldId,
    this.fieldName,
    this.inputError,
  });

  final bool loadingHistory;

  /// false ⇒ السجلّ في الذاكرة فقط (لا هويّة/لا مفتاح آمن) — يُعلَن للمستخدم.
  final bool persistent;
  final List<ChatEntry> messages;
  final bool sending;
  final FailedAsk? failure;
  final String? fieldId;
  final String? fieldName;
  final String? inputError;

  AdvisorChatState copyWith({
    bool? loadingHistory,
    bool? persistent,
    List<ChatEntry>? messages,
    bool? sending,
    FailedAsk? Function()? failure,
    String? Function()? fieldId,
    String? Function()? fieldName,
    String? Function()? inputError,
  }) => AdvisorChatState(
    loadingHistory: loadingHistory ?? this.loadingHistory,
    persistent: persistent ?? this.persistent,
    messages: messages ?? this.messages,
    sending: sending ?? this.sending,
    failure: failure != null ? failure() : this.failure,
    fieldId: fieldId != null ? fieldId() : this.fieldId,
    fieldName: fieldName != null ? fieldName() : this.fieldName,
    inputError: inputError != null ? inputError() : this.inputError,
  );
}

class AdvisorChatCubit extends Cubit<AdvisorChatState> {
  AdvisorChatCubit({
    required AdvisorApi api,
    required Future<AdvisorChatHistory> history,
    String? fieldId,
    String? fieldName,
    DateTime Function()? clock,
  }) : _api = api,
       _historyFuture = history,
       _clock = clock ?? DateTime.now,
       super(AdvisorChatState(fieldId: fieldId, fieldName: fieldName));

  final AdvisorApi _api;
  final Future<AdvisorChatHistory> _historyFuture;
  final DateTime Function() _clock;
  AdvisorChatHistory? _history;

  /// قفل متزامن: يُضبَط قبل أوّل await فلا تمرّ ضغطتان متتاليتان.
  bool _busy = false;

  Future<AdvisorChatHistory> _ready() async => _history ??= await _historyFuture
      .catchError((Object _) => MemoryChatHistory() as AdvisorChatHistory);

  Future<void> init() async {
    final h = await _ready();
    List<ChatEntry> items;
    try {
      items = await h.load();
    } catch (_) {
      items = const [];
    }
    if (isClosed) return;
    emit(
      state.copyWith(
        loadingHistory: false,
        persistent: h.persistent,
        messages: List.unmodifiable(items),
      ),
    );
  }

  void setField(String? id, String? name) => emit(
    state.copyWith(
      fieldId: () => (id == null || id.isEmpty) ? null : id,
      fieldName: () => name,
    ),
  );

  /// يُرجع true إن قُبل السؤال (فيُفرَّغ حقل الإدخال).
  Future<bool> send(String text) async {
    if (_busy || state.sending) return false; // لا إرسال مزدوج
    final question = text.trim();
    if (question.isEmpty) return false;
    if (question.length > kMaxQuestionLength) {
      emit(
        state.copyWith(
          inputError: () =>
              'السؤال أطول من الحدّ المسموح ($kMaxQuestionLength حرف) — اختصره.',
        ),
      );
      return false;
    }
    _busy = true;
    try {
      await _sendAccepted(question);
    } finally {
      _busy = false;
    }
    return true;
  }

  Future<void> _sendAccepted(String question) async {
    final h = await _ready();
    final entry = ChatEntry(
      role: ChatRole.user,
      text: question,
      at: _clock(),
      fieldId: state.fieldId,
    );
    await _persist(h, entry);
    if (isClosed) return;
    emit(
      state.copyWith(
        messages: List.unmodifiable([...state.messages, entry]),
        inputError: () => null,
      ),
    );
    await _ask(question, entry.fieldId);
  }

  /// يعيد إرسال آخر سؤال فشل (نفس الحقل) دون إضافة رسالة مستخدم جديدة.
  Future<void> retry() async {
    final f = state.failure;
    if (f == null || _busy || state.sending) return;
    _busy = true;
    try {
      await _ask(f.question, f.fieldId);
    } finally {
      _busy = false;
    }
  }

  Future<void> _ask(String question, String? fieldId) async {
    emit(state.copyWith(sending: true, failure: () => null));
    try {
      final json = await _api.askAgent(question, fieldId: fieldId);
      final reply = AdvisorReply.fromJson(json);
      final entry = ChatEntry(
        role: ChatRole.assistant,
        text: reply.answerAr,
        at: _clock(),
        reply: reply,
        fieldId: fieldId,
      );
      await _persist(await _ready(), entry);
      if (isClosed) return;
      emit(
        state.copyWith(
          sending: false,
          messages: List.unmodifiable([...state.messages, entry]),
        ),
      );
    } catch (e) {
      if (isClosed) return;
      emit(
        state.copyWith(
          sending: false,
          failure: () => FailedAsk(
            question: question,
            fieldId: fieldId,
            error: ApiException.from(e),
          ),
        ),
      );
    }
  }

  Future<void> clearHistory() async {
    final h = await _ready();
    try {
      await h.clear();
    } catch (_) {
      // المسح المحلّيّ أفضل-جهد؛ القائمة المعروضة تُفرَّغ على أيّ حال.
    }
    if (isClosed) return;
    emit(state.copyWith(messages: const [], failure: () => null));
  }

  Future<void> _persist(AdvisorChatHistory h, ChatEntry entry) async {
    try {
      await h.append(entry);
    } catch (_) {
      // فشل الحفظ لا يُسقط المحادثة الجارية.
    }
  }
}

/// نصّ الخطأ الصادق لفشل المحادثة. رسائل 401/403/404/503 عقدٌ لا تُستبدَل.
String advisorChatErrorText(ApiException e) {
  final detail = e.detail;
  if (e.statusCode == 502 && detail is Map) {
    final dep = detail['dependency']?.toString();
    if (dep == 'canonical-field-state') {
      return 'تعذّر جلب سياق الحقل من المنصّة؛ الخادم يرفض الإجابة الخاصّة بحقل '
          'حين يغيب سياقه. أزِل ربط الحقل أو أعد المحاولة لاحقاً.';
    }
    if (dep != null) {
      return 'تعذّر الوصول إلى مصدر الأدلّة ($dep) — لم تُولَّد إجابة.';
    }
  }
  if (e.kind == ApiErrorKind.validation) {
    return 'رفض الخادم السؤال (422): ${e.messageAr}';
  }
  if (e.kind == ApiErrorKind.timeout) {
    return '${e.messageAr} (مهلة المستشار ${kAdvisorTimeout.inSeconds} ثانية)';
  }
  return e.messageAr;
}
