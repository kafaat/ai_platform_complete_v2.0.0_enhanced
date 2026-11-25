export interface UniformitySurveyInput {
  evidence_ref: string;
  samples: { sample_id: string; depth_mm: number; represented_area_m2: number }[];
}

export function parseUniformitySurvey(evidence: string, rows: string): UniformitySurveyInput | undefined {
  const evidence_ref = evidence.trim();
  if (!evidence_ref && !rows.trim()) return undefined;
  if (!evidence_ref || evidence_ref.length > 512) throw new Error('أدخل مرجع دليل القياس (حتى 512 حرفًا).');
  const lines = rows.split(/\r?\n/).filter(line => line.trim());
  if (lines.length < 4 || lines.length > 10000) throw new Error('أدخل من 4 إلى 10000 عينة.');
  const seen = new Set<string>();
  const samples = lines.map((line, index) => {
    const parts = line.split(',').map(part => part.trim());
    const [sample_id, depth, area] = parts;
    const depth_mm = Number(depth);
    const represented_area_m2 = Number(area);
    const decimal = /^(?:\d+(?:\.\d*)?|\.\d+)$/;
    if (parts.length !== 3 || !sample_id || sample_id.length > 512 || seen.has(sample_id) ||
      !decimal.test(depth ?? '') || !decimal.test(area ?? '') ||
      !Number.isFinite(depth_mm) || !Number.isFinite(represented_area_m2) || represented_area_m2 <= 0) {
      throw new Error(`عينة غير صالحة في السطر ${index + 1}: المعرّف، العمق (مم)، المساحة (م²).`);
    }
    seen.add(sample_id);
    return { sample_id, depth_mm, represented_area_m2 };
  });
  return { evidence_ref, samples };
}
