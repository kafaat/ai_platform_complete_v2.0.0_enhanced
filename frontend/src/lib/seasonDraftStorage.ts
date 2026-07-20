// SAHOOL — lib/seasonDraftStorage.ts
// استمرار مسودّة إدخال الموسم عبر الجلسات (SEASON-RECORD-ENTRY-01 شريحة 3c).
// يبني على نمط workspaceStorage: عميل-فقط، best-effort، أيّ تعذّر/فساد ⇒ null.
//
// draft_key هو مفتاح التكرار (idempotency) للنقطة الخلفيّة POST /api/v1/seasons —
// نُولّده مرّة عند بدء التدفّق ونحفظه محليّاً، فإعادة تحميل الصفحة أثناء الترقيم
// تستأنف نفس المسودّة (والخادم يعيد نفس season_id لا نسخة).

const KEY = 'sahool-season-draft-v1';

export interface SeasonDraftSnapshot {
  draftKey: string; // مفتاح التكرار الثابت لهذه المسودّة
  fieldId: string; // الحقل المرسوم (يُملأ فور إنشائه)
  fieldName: string;
  seasonId?: string; // معرّف الموسم الخلفيّ (يُملأ بعد POST المسودّة)
  phase: string; // مرحلة التدفّق الحاليّة (draw/details/logbook/review)
  observedFrom?: string;
  observedTo?: string;
  seasonLabel?: string;
  varietyName?: string;
  sowingDate?: string;
  hasLogbook?: boolean;
}

/** مُعرّف تكرار عشوائيّ ثابت للمسودّة. يستعمل crypto إن توفّر، وإلّا احتياطيّ عميل. */
export function newDraftKey(): string {
  try {
    if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
      return `season-${crypto.randomUUID()}`;
    }
  } catch {
    /* تجاهُل — احتياطيّ أدناه */
  }
  // احتياطيّ (بيئات بلا crypto.randomUUID): عشوائيّة كافية لمفتاح تكرار.
  const rand = Array.from({ length: 4 }, () =>
    Math.floor(Math.random() * 0xffff)
      .toString(16)
      .padStart(4, '0'),
  ).join('');
  return `season-${rand}`;
}

/** يقرأ لقطة المسودّة المحفوظة؛ تعذّر/فساد ⇒ null (يبدأ المستخدم تدفّقاً جديداً). */
export function loadSeasonDraft(): SeasonDraftSnapshot | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as unknown;
    if (!data || typeof data !== 'object') return null;
    const s = data as Partial<SeasonDraftSnapshot>;
    if (!s.draftKey || !s.phase) return null; // لقطة ناقصة ⇒ تجاهُل
    return s as SeasonDraftSnapshot;
  } catch {
    return null;
  }
}

/** يحفظ لقطة المسودّة (best-effort — تجاهُل أيّ تعذّر تخزين). */
export function saveSeasonDraft(snap: SeasonDraftSnapshot): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(snap));
  } catch {
    /* تجاهُل — التخزين غير متاح/ممتلئ لا يكسر الجلسة */
  }
}

/** يمسح المسودّة المحفوظة (بعد القبول أو الإلغاء). */
export function clearSeasonDraft(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* تجاهُل */
  }
}
