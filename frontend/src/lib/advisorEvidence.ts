// What the advisor's answer rests on, in a form the farmer can check.
//
// The runtime returns publisher, link, revision and page for every retrieved excerpt, a
// structured advisory envelope (human review, limitations, missing evidence) and whether
// retrieval was available at all. The chat used to show four raw evidence ids and a fixed
// "RAG/KG/Field Memory" badge, so none of that reached the screen.

export interface AdvisorCitation {
  chunkId: string;
  publisher: string | null;
  // File name of a tenant-uploaded document; such a reference has no publisher or web link.
  documentName: string | null;
  // Only http(s) links are offered as links; internal schemes stay text.
  href: string | null;
  revision: string | null;
  locator: string | null;
}

export interface AdvisorNotices {
  requiresHumanReview: boolean;
  limitations: string[];
  evidenceMissing: string[];
}

interface EvidenceSourceLike { key: string; label_ar?: string; available?: boolean }

const LIMITATION_LABELS: Record<string, string> = {
  generation_failed_evidence_only: 'فشل التوليد — أدلّة فقط',
  generation_blocked_by_policy_evidence_only: 'محجوب بالسياسة — أدلّة فقط',
  generation_suppressed_evidence_only: 'أُخمِد خرج النموذج — أدلّة فقط',
  generation_disabled_evidence_only: 'لا نموذج مُفعَّل — أدلّة فقط',
  proposed_actions_await_human_approval: 'إجراءات مقترحة بانتظار موافقة بشريّة',
  confidence_unavailable: 'جودة الدليل غير متاحة',
  low_confidence: 'جودة دليل منخفضة',
  tool_calls_truncated: 'اقتُطعت استدعاءات الأدوات',
};

const MISSING_LABELS: Record<string, string> = {
  no_grounding_evidence: 'لا دليل مرجعيّ يسند الإجابة',
  'context_pack:incomplete': 'سياق الحقل غير مكتمل',
  'context_pack:unverified': 'جاهزيّة سياق الحقل غير مؤكَّدة',
  'context_pack:warnings_invalid': 'تنبيهات سياق الحقل غير مقروءة',
};

const RAG_REASON_LABELS: Record<string, string> = {
  tenant_corpus_empty: 'لا توجد قاعدة معرفة مراجَعة لهذا الحساب بعد',
  rag_transport_unavailable: 'خدمة المراجع غير متاحة الآن',
  rag_retrieval_unavailable: 'خدمة المراجع غير متاحة الآن',
};

function text(value: unknown): string | null {
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function strings(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map(text).filter((v): v is string => v !== null);
}

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

// Uploaded documents are cited as `tenant-upload://<tenant>/<file name>`: the name is the
// only thing that identifies them to the reader, and the tenant id is not shown.
function uploadedDocumentName(uri: string | null): string | null {
  const match = uri ? /^tenant-upload:\/\/[^/]+\/(.+)$/i.exec(uri) : null;
  if (!match) return null;
  const name = match[1].split('/').pop() ?? '';
  try {
    return decodeURIComponent(name).trim() || null;
  } catch {
    return name.trim() || null;
  }
}

export function citationsFromAnnotations(annotations: unknown): AdvisorCitation[] {
  const rag = record(annotations)?.rag;
  if (!Array.isArray(rag)) return [];
  const seen = new Set<string>();
  const out: AdvisorCitation[] = [];
  for (const raw of rag) {
    const item = record(raw);
    const chunkId = text(item?.chunk_id);
    if (!item || !chunkId || seen.has(chunkId)) continue;
    seen.add(chunkId);
    const uri = text(item.source_uri);
    const page = text(item.page);
    const section = text(item.section);
    out.push({
      chunkId,
      publisher: text(item.publisher),
      documentName: uploadedDocumentName(uri),
      href: uri && /^https?:\/\//i.test(uri) ? uri : null,
      revision: text(item.source_revision),
      locator: [section, page ? `ص ${page}` : null].filter(Boolean).join(' · ') || null,
    });
  }
  return out;
}

// References that were retrieved but never checked against their original: the runtime keeps
// them out of the answer and returns pointers only.
export function unverifiedReferenceCount(annotations: unknown): number {
  const refs = record(annotations)?.unverified_seed_references;
  return Array.isArray(refs) ? refs.length : 0;
}

export function advisoryNotices(advisory: unknown): AdvisorNotices {
  const env = record(advisory);
  return {
    // Fail-safe like the server: an absent or malformed envelope means review is required.
    requiresHumanReview: env?.requires_human_review !== false,
    limitations: strings(env?.limitations).map((code) => LIMITATION_LABELS[code] ?? code),
    evidenceMissing: strings(env?.evidence_missing).map((code) => {
      if (MISSING_LABELS[code]) return MISSING_LABELS[code];
      if (code.startsWith('gap:')) return `فجوة معرفة: ${code.slice(4)}`;
      if (code.startsWith('context_pack:')) return `سياق الحقل: ${code.slice(13)}`;
      return code;
    }),
  };
}

export function ragUnavailableText(ragAvailable: unknown, reason: unknown): string | null {
  if (ragAvailable !== false) return null;
  const code = text(reason);
  const label = code ? RAG_REASON_LABELS[code.toLowerCase()] : null;
  return label ?? `المراجع غير متاحة لهذه الإجابة${code ? ` (${code})` : ''}`;
}

// The badge names only the sources this answer actually had.
export function sourceBadgeText(sources: readonly EvidenceSourceLike[] | undefined): string {
  const available = (sources ?? [])
    .filter((s) => s.available === true)
    .map((s) => s.label_ar || s.key);
  return available.length
    ? `SAHOOL AI Runtime · ${available.join(' · ')}`
    : 'SAHOOL AI Runtime · بلا أدلّة متاحة';
}

// The advisory envelope does not report a failed audit write, so it is shown on its own:
// an answer whose record was not saved must not look like a recorded consultation.
export function auditNotPersistedText(auditEvent: unknown): string | null {
  const event = record(auditEvent);
  if (!event || event.persisted === true) return null;
  // `unconfirmed`: the platform answered without saying whether it stored the record.
  if (event.status === 'unconfirmed') return 'لم يتأكّد حفظ سجلّ تدقيق لهذه الإجابة.';
  return 'لم يُحفَظ سجلّ تدقيق لهذه الإجابة.';
}
