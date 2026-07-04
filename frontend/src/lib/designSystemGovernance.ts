export type DesignTokenDomain = 'color' | 'radius' | 'shadow' | 'spacing' | 'font' | 'motion';
export type DesignGovernanceSeverity = 'ok' | 'info' | 'warn' | 'critical';

export interface DesignTokenContract {
  name: string;
  domain: DesignTokenDomain;
  purpose: string;
  cssVar?: string;
  value?: string;
  agentHint: string;
}

export interface DesignComponentContract {
  name: string;
  layer: 'primitive' | 'pattern' | 'screen';
  accessibilityContract: string[];
  themingContract: string[];
  safeOverrides: string[];
  antiPatterns: string[];
}

export interface DesignSystemGovernanceResult {
  score: number;
  severity: DesignGovernanceSeverity;
  summary: string;
  tokenCount: number;
  componentCount: number;
  missingDomains: DesignTokenDomain[];
  agentRules: string[];
  evidence: string[];
}

export const SAHOOL_TOKEN_CONTRACTS: DesignTokenContract[] = [
  { name: 'sahool-bg', domain: 'color', cssVar: '--sahool-bg', purpose: 'خلفية التطبيق حسب الثيم', agentHint: 'استخدم rgb(var(--sahool-bg)) ولا تضع لون خلفية ثابتاً في الشاشات.' },
  { name: 'sahool-surface', domain: 'color', cssVar: '--sahool-surface', purpose: 'أسطح البطاقات والحوارات', agentHint: 'كل بطاقة/لوحة يجب أن تعتمد على surface أو surface-2.' },
  { name: 'sahool-text', domain: 'color', cssVar: '--sahool-text', purpose: 'النص الرئيسي', agentHint: 'لا تستخدم white/black مباشرة إلا في حالات overlay موثقة.' },
  { name: 'sahool-muted', domain: 'color', cssVar: '--sahool-muted', purpose: 'النص الثانوي', agentHint: 'استخدمه للملاحظات لا للقرارات الحرجة.' },
  { name: 'sahool-green', domain: 'color', cssVar: '--sahool-green', purpose: 'الإجراء الزراعي الأساسي', agentHint: 'CTA الزراعي الأساسي فقط؛ لا تجعله لوناً عاماً لكل شيء.' },
  { name: 'sahool-accent', domain: 'color', cssVar: '--sahool-accent', purpose: 'تمييز المعلومات/المسارات', agentHint: 'للطبقات والرسوم لا للتنبيهات.' },
  { name: 'sahool-radius-sm', domain: 'radius', cssVar: '--sahool-radius-sm', purpose: 'زوايا مدمجة للجوال', agentHint: 'استخدم radius tokens بدلاً من أرقام عشوائية.' },
  { name: 'sahool-radius-md', domain: 'radius', cssVar: '--sahool-radius-md', purpose: 'زوايا البطاقة الافتراضية', agentHint: 'القيمة الافتراضية للبطاقات.' },
  { name: 'sahool-radius-lg', domain: 'radius', cssVar: '--sahool-radius-lg', purpose: 'زوايا اللوحات الكبيرة', agentHint: 'للـ dashboards/panels لا للأزرار الصغيرة.' },
  { name: 'sahool-shadow-soft', domain: 'shadow', cssVar: '--sahool-shadow-soft', purpose: 'ظلّ موحد للبطاقات', agentHint: 'لا تنسخ box-shadow جديداً في كل شاشة.' },
  { name: 'sahool-page-pad', domain: 'spacing', cssVar: '--sahool-page-pad', purpose: 'حافة الصفحة المتجاوبة', agentHint: 'استخدمه في صفحات FieldView بدلاً من padding ثابت.' },
  { name: 'font-ar', domain: 'font', cssVar: '--font-ar', purpose: 'خط عربي موحد', agentHint: 'التزم بالخط العربي المعلن بدلاً من system-ui مباشر.' },
  { name: 'motion-reduced', domain: 'motion', purpose: 'احترام prefers-reduced-motion', value: '@media (prefers-reduced-motion: reduce)', agentHint: 'أي animation جديدة يجب أن تكون قابلة للإطفاء ضمن media query.' },
];

export const SAHOOL_COMPONENT_CONTRACTS: DesignComponentContract[] = [
  {
    name: 'Card',
    layer: 'primitive',
    accessibilityContract: ['role=button فقط عند وجود onClick', 'يدعم Enter/Space عند قابلية النقر'],
    themingContract: ['يستخدم T.card/T.line/RADIUS', 'لا يثبت ألواناً خارج tokens'],
    safeOverrides: ['className', 'style محدود', 'pad'],
    antiPatterns: ['div قابل للنقر بلا tabIndex', 'border/background hard-coded خارج سياق موثق'],
  },
  {
    name: 'FieldViewInsightStrip',
    layer: 'pattern',
    accessibilityContract: ['section باسم واضح', 'أزرار CTA فعلية لا div'],
    themingContract: ['نغمات ok/info/warn/critical', 'يعرض evidence مختصر'],
    safeOverrides: ['onBackfill/onShowAlerts/onShowTasks/onOpenTimeline'],
    antiPatterns: ['اقتراح action بلا evidence', 'تغيير field global من بطاقة إنشاء سجل'],
  },
  {
    name: 'DataTable',
    layer: 'primitive',
    accessibilityContract: ['table عند وجود صفوف', 'empty state عند الفراغ', 'فرز بزر لا بنص قابل للنقر فقط'],
    themingContract: ['يتبع tokens ولا يعتمد على ألوان Tailwind عشوائية'],
    safeOverrides: ['columns/render/rowKey/mobileBreakpoint'],
    antiPatterns: ['فرز يغير rows الأصلية', 'خلايا بلا fallback للقيم الغائبة'],
  },
];

function missingDomains(tokens: DesignTokenContract[]): DesignTokenDomain[] {
  const required: DesignTokenDomain[] = ['color', 'radius', 'shadow', 'spacing', 'font', 'motion'];
  const present = new Set(tokens.map((token) => token.domain));
  return required.filter((domain) => !present.has(domain));
}

function severityFromScore(score: number): DesignGovernanceSeverity {
  if (score < 50) return 'critical';
  if (score < 75) return 'warn';
  if (score < 90) return 'info';
  return 'ok';
}

export function evaluateDesignSystemGovernance(
  tokens: DesignTokenContract[] = SAHOOL_TOKEN_CONTRACTS,
  components: DesignComponentContract[] = SAHOOL_COMPONENT_CONTRACTS,
): DesignSystemGovernanceResult {
  const missing = missingDomains(tokens);
  const tokenCoverage = Math.round(((6 - missing.length) / 6) * 100);
  const componentScore = components.length >= 3 ? 100 : components.length >= 2 ? 84 : components.length >= 1 ? 60 : 20;
  const hasAgentHints = tokens.every((token) => token.agentHint.trim().length > 12);
  const agentScore = hasAgentHints ? 100 : 65;
  const score = Math.round((tokenCoverage * 0.45) + (componentScore * 0.35) + (agentScore * 0.20));
  const severity = severityFromScore(score);
  const agentRules = [
    'غيّر الثيم عبر CSS variables لا عبر نسخ مكونات كاملة.',
    'استخدم primitives الموثقة قبل بناء مكوّن جديد.',
    'أي شاشة FieldView يجب أن تُظهر evidence عند اقتراح action.',
    'نماذج الإنشاء prefill فقط ولا تخطف activeFieldId عالمياً.',
  ];
  const evidence = [
    `tokens=${tokens.length}`,
    `components=${components.length}`,
    `domains=${Array.from(new Set(tokens.map((t) => t.domain))).join(',')}`,
    `agentHints=${hasAgentHints}`,
  ];
  const summary = missing.length
    ? `نظام التصميم يحتاج تغطية: ${missing.join('، ')}`
    : `نظام التصميم جاهز للإنسان والوكيل بدرجة ${score}%`;
  return { score, severity, summary, tokenCount: tokens.length, componentCount: components.length, missingDomains: missing, agentRules, evidence };
}
