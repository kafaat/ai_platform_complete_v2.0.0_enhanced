// fieldHealthSpeech — نصّ «صحّة الحقل» المسموع لزرّ الاستشارة الصوتيّة.
//
// صدق: يُبنى من البيانات الحاضرة وحدها؛ كلُّ قسمٍ غائب يُقال صراحةً «غير متاح» أو
// «تعذّر الجلب» — لا رقمَ يُختلَق ولا صمتٌ يوحي بأنّ كلّ شيءٍ سليم. والفرقُ بين «نجح
// الطلبُ بلا بيانات» و«فشل الطلب» يُنطَق، لأنّ المزارع لا يرى الشاشة حين يستمع.
//
// ttsErrorMessage: سببُ تعذّر الصوت بلغة المزارع بدل ابتلاعه. خدمةُ الصوت تُعيد 503
// ``local_provider_unavailable_for_policy`` حين تمنع سياسةُ مشاركة البيانات المزوّدَ
// الخارجيّ ولا مزوّدَ محلّيّاً (TTS-LOCAL-ONLY-FALLS-BACK-TO-EXTERNAL-PROVIDER-01).

/** حالة قسمٍ واحد: حاضر بقيمة · نجح بلا بيانات · فشل الطلب · لم يصل بعد. */
export type SectionState = 'ok' | 'empty' | 'error' | 'loading';

export interface FieldHealthInput {
  fieldName: string;
  crop?: string | null;
  ndvi: { state: SectionState; label?: string | null; value?: number | null };
  disease: { state: SectionState; riskAr?: string | null; adviceAr?: string | null };
  nitrogen: { state: SectionState | 'disabled'; kgHa?: number | null };
}

/** سقفُ خدمة الصوت 1000 حرف؛ نترك هامشاً. */
export const MAX_SPEECH_CHARS = 900;

function ndviSentence(n: FieldHealthInput['ndvi']): string {
  if (n.state === 'ok' && typeof n.value === 'number' && Number.isFinite(n.value)) {
    const label = n.label?.trim() ? `${n.label.trim()}، ` : '';
    return `الغطاء النباتيّ: ${label}بمؤشّر ${n.value.toFixed(2)}.`;
  }
  if (n.state === 'error') return 'تعذّر جلب قراءة الغطاء النباتيّ الآن.';
  if (n.state === 'loading') return 'قراءة الغطاء النباتيّ لم تصل بعد.';
  return 'لا قراءة غطاء نباتيّ متاحة لهذا الحقل.';
}

function diseaseSentence(d: FieldHealthInput['disease']): string {
  if (d.state === 'ok' && d.riskAr?.trim()) {
    const advice = d.adviceAr?.trim() ? ` ${d.adviceAr.trim()}` : '';
    return `خطر الأمراض: ${d.riskAr.trim()}.${advice}`;
  }
  if (d.state === 'error') return 'تعذّر جلب تقدير خطر الأمراض الآن.';
  if (d.state === 'loading') return 'تقدير خطر الأمراض لم يصل بعد.';
  return 'لا تقدير لخطر الأمراض لهذا الحقل.';
}

function nitrogenSentence(n: FieldHealthInput['nitrogen']): string {
  if (n.state === 'ok' && typeof n.kgHa === 'number' && Number.isFinite(n.kgHa)) {
    return `توصية النيتروجين: ${Math.round(n.kgHa)} كيلوغرام للهكتار.`;
  }
  if (n.state === 'error') return 'تعذّر جلب توصية التسميد الآن.';
  if (n.state === 'loading') return 'توصية التسميد لم تصل بعد.';
  if (n.state === 'disabled') return 'توصية التسميد غير متاحة: خدمة التربة غير منشورة بعد.';
  return 'لا توصية تسميد متاحة لهذا الحقل.';
}

/** نصٌّ عربيّ مسموع يلخّص صحّة الحقل من البيانات الحاضرة وحدها. */
export function buildFieldHealthSpeech(input: FieldHealthInput): string {
  const crop = input.crop?.trim() && input.crop.trim() !== '—' ? `، المحصول ${input.crop.trim()}` : '';
  const parts = [
    `صحّة حقل ${input.fieldName.trim() || 'غير مسمّى'}${crop}.`,
    ndviSentence(input.ndvi),
    diseaseSentence(input.disease),
    nitrogenSentence(input.nitrogen),
  ];
  const text = parts.join(' ');
  return text.length <= MAX_SPEECH_CHARS ? text : `${text.slice(0, MAX_SPEECH_CHARS - 1)}…`;
}

/** هل وصل كلُّ قسمٍ إلى حالةٍ نهائيّة؟ (لا نُسمِع ملخّصاً نصفُه «لم يصل بعد»). */
export function isFieldHealthSettled(input: FieldHealthInput): boolean {
  return [input.ndvi.state, input.disease.state, input.nitrogen.state].every((s) => s !== 'loading');
}

const POLICY_BLOCKED = 'local_provider_unavailable_for_policy';

function isBlobLike(data: unknown): data is Blob {
  // لا ``instanceof Blob``: قد يأتي الـBlob من عالمٍ آخر (jsdom/إطار) فيكذب الفحص.
  return typeof data === 'object' && data !== null && typeof (data as Blob).size === 'number'
    && typeof (data as Blob).type === 'string';
}

function blobText(blob: Blob): Promise<string> {
  if (typeof blob.text === 'function') return blob.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

async function readErrorDetail(data: unknown): Promise<unknown> {
  // الطلبُ بـresponseType: 'blob' ⇒ جسمُ الخطأ Blob لا JSON.
  try {
    const raw = isBlobLike(data) ? await blobText(data) : data;
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
    return (parsed as { detail?: unknown } | null)?.detail;
  } catch {
    return undefined;
  }
}

/** سببُ تعذّر الصوت بلغة المزارع — يُعرض بدل ابتلاع الخطأ. */
export async function ttsErrorMessage(err: unknown): Promise<string> {
  const response = (err as { response?: { status?: number; data?: unknown } } | null)?.response;
  if (!response) return 'تعذّر الاتّصال بخدمة الصوت. تحقّق من الشبكة وأعد المحاولة.';
  const detail = await readErrorDetail(response.data);
  const code = (detail as { error?: unknown } | null)?.error;
  if (response.status === 503 && code === POLICY_BLOCKED) {
    return 'الصوت غير متاح لمزرعتك: سياسة مشاركة البيانات لا تسمح بمزوّد صوت خارجيّ، ولا يوجد مزوّد محلّيّ.';
  }
  if (response.status === 401) return 'انتهت الجلسة. سجّل الدخول من جديد ثمّ أعد المحاولة.';
  if (response.status === 422) return 'تعذّر قراءة النصّ صوتيّاً (نصّ غير صالح أو طويل جدّاً).';
  return 'خدمة الصوت غير متاحة الآن. أعد المحاولة لاحقاً.';
}
