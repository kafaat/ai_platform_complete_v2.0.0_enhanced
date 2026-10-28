// تسميات أنواع المهامّ العربيّة — مصدر واحد لصفحة المهامّ الرئيسيّة (TasksPage) ولوحة مهامّ
// مساحة عمل الحقل (UI-W8): الخادم يعيد task_type لا عنواناً، فتُشتقّ التسمية من هنا.
export const TASK_TYPE_LABELS_AR: Record<string, string> = {
  irrigation: 'ري',
  fertilization: 'تسميد',
  spraying: 'رش مبيدات',
  harvest: 'حصاد',
  scouting: 'استكشاف',
  soil_sampling: 'أخذ عينات تربة',
};

/** تسمية نوع المهمّة؛ النوع غير المعروف يُعاد كما أرسله الخادم (لا تسمية مضلِّلة). */
export function taskTypeLabel(taskType: string | null | undefined): string | undefined {
  if (!taskType) return undefined;
  return TASK_TYPE_LABELS_AR[taskType] ?? taskType;
}
