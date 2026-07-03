import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(__dirname, '..');
const sectionsDir = path.join(root, 'sections');
const allowedSectionFiles = new Set([
  // FieldMapCenter keeps a map-specific URL/default sync path and writes to FieldView explicitly.
  'FieldMapCenter.tsx',
]);

const allowedFieldContextFiles = new Set([
  // MyFieldsPage is the FieldView entry point: it commits an explicit user selection
  // before navigating to MapHub. FieldMapCenter has its own documented map-specific sync.
  'MyFieldsPage.tsx',
  'FieldMapCenter.tsx',
]);

function walk(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return walk(full);
    return /\.tsx?$/.test(entry.name) ? [full] : [];
  });
}

describe('FieldView source-of-truth guard', () => {
  it('screens should use useSelectedField instead of local useFieldOptions field selection', () => {
    const offenders = walk(sectionsDir)
      .filter((file) => !file.endsWith('.test.ts') && !file.endsWith('.test.tsx'))
      .filter((file) => !allowedSectionFiles.has(path.basename(file)))
      .filter((file) => fs.readFileSync(file, 'utf8').includes("from '../hooks/useFieldOptions'"))
      .map((file) => path.relative(root, file));

    expect(offenders).toEqual([]);
  });

  it('screens should not read FieldView store directly except documented entry/sync points', () => {
    const offenders = walk(sectionsDir)
      .filter((file) => !file.endsWith('.test.ts') && !file.endsWith('.test.tsx'))
      .filter((file) => !allowedFieldContextFiles.has(path.basename(file)))
      .filter((file) => fs.readFileSync(file, 'utf8').includes("from '../hooks/useFieldContext'"))
      .map((file) => path.relative(root, file));

    expect(offenders).toEqual([]);
  });
});
