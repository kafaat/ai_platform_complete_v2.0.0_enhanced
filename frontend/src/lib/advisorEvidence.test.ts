import { describe, expect, it } from 'vitest';
import {
  advisoryNotices, auditNotPersistedText, citationsFromAnnotations, ragUnavailableText, sourceBadgeText,
  unverifiedReferenceCount,
} from './advisorEvidence';

describe('citationsFromAnnotations', () => {
  it('names the publisher, links only http(s) sources, and keeps page and revision', () => {
    const citations = citationsFromAnnotations({
      rag: [
        { chunk_id: 'c1', publisher: 'FAO', source_uri: 'https://www.fao.org/x', source_revision: '2021', page: 12, section: 'Kc' },
        { chunk_id: 'c2', publisher: null, source_uri: 'sahool://seed-quarantine/7' },
        { chunk_id: 'c3', publisher: 'X', source_uri: 'javascript:alert(1)' },
      ],
    });
    expect(citations).toEqual([
      { chunkId: 'c1', publisher: 'FAO', href: 'https://www.fao.org/x', revision: '2021', locator: 'Kc · ص 12' },
      { chunkId: 'c2', publisher: null, href: null, revision: null, locator: null },
      { chunkId: 'c3', publisher: 'X', href: null, revision: null, locator: null },
    ]);
  });

  it('drops duplicates and entries without an id, and tolerates a malformed payload', () => {
    expect(citationsFromAnnotations({ rag: [{ chunk_id: 'a' }, { chunk_id: 'a' }, { publisher: 'P' }, null] })).toHaveLength(1);
    expect(citationsFromAnnotations(null)).toEqual([]);
    expect(citationsFromAnnotations({ rag: 'x' })).toEqual([]);
  });
});

describe('unverifiedReferenceCount', () => {
  it('counts references the runtime withheld from the answer', () => {
    expect(unverifiedReferenceCount({ unverified_seed_references: [{}, {}] })).toBe(2);
    expect(unverifiedReferenceCount({})).toBe(0);
  });
});

describe('advisoryNotices', () => {
  it('requires human review when the envelope is absent or does not say otherwise', () => {
    expect(advisoryNotices(undefined).requiresHumanReview).toBe(true);
    expect(advisoryNotices({ requires_human_review: 'no' }).requiresHumanReview).toBe(true);
    expect(advisoryNotices({ requires_human_review: false }).requiresHumanReview).toBe(false);
  });

  it('translates known codes and keeps unknown ones visible', () => {
    const notices = advisoryNotices({
      limitations: ['low_confidence', 'new_code'],
      evidence_missing: ['no_grounding_evidence', 'gap:soil_ph', 'context_pack:weather_history_absent'],
    });
    expect(notices.limitations).toEqual(['جودة دليل منخفضة', 'new_code']);
    expect(notices.evidenceMissing).toEqual([
      'لا دليل مرجعيّ يسند الإجابة',
      'فجوة معرفة: soil_ph',
      'سياق الحقل: weather_history_absent',
    ]);
  });
});

describe('ragUnavailableText', () => {
  it('is silent unless the runtime declared retrieval unavailable', () => {
    expect(ragUnavailableText(true, null)).toBeNull();
    expect(ragUnavailableText(undefined, 'TENANT_CORPUS_EMPTY')).toBeNull();
  });

  it('explains an empty corpus and reports any other reason code', () => {
    expect(ragUnavailableText(false, 'TENANT_CORPUS_EMPTY')).toBe('لا توجد قاعدة معرفة مراجَعة لهذا الحساب بعد');
    expect(ragUnavailableText(false, 'rag_upstream_http_503')).toContain('rag_upstream_http_503');
    expect(ragUnavailableText(false, null)).toBe('المراجع غير متاحة لهذه الإجابة');
  });
});

describe('sourceBadgeText', () => {
  it('names only the sources the answer had', () => {
    expect(sourceBadgeText([
      { key: 'rag', label_ar: 'RAG', available: false },
      { key: 'field_state', label_ar: 'حالة الحقل', available: true },
    ])).toBe('SAHOOL AI Runtime · حالة الحقل');
    expect(sourceBadgeText([])).toBe('SAHOOL AI Runtime · بلا أدلّة متاحة');
    expect(sourceBadgeText(undefined)).toBe('SAHOOL AI Runtime · بلا أدلّة متاحة');
  });
});

describe('auditNotPersistedText', () => {
  it('flags an answer whose audit record was not saved, and only then', () => {
    expect(auditNotPersistedText({ status: 'failed', persisted: false })).toBe('لم يُحفَظ سجلّ تدقيق لهذه الإجابة.');
    expect(auditNotPersistedText({ status: 'not_persisted', persisted: false })).toBe('لم يُحفَظ سجلّ تدقيق لهذه الإجابة.');
    expect(auditNotPersistedText({ status: 'unconfirmed' })).toBe('لم يتأكّد حفظ سجلّ تدقيق لهذه الإجابة.');
    expect(auditNotPersistedText({ status: 'recorded', persisted: true })).toBeNull();
    expect(auditNotPersistedText(undefined)).toBeNull();
  });
});
