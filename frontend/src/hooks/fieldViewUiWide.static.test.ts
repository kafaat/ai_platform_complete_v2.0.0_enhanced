import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const read = (rel: string) => readFileSync(join(root, rel), 'utf8');

const fieldViewPages = [
  'src/sections/AlertSystemPage.tsx',
  'src/sections/EtcDualPage.tsx',
  'src/sections/GisToolsPage.tsx',
  'src/sections/OperationCenterWallPage.tsx',
  'src/sections/RecommendationFlow.tsx',
  'src/sections/RecommendationPage.tsx',
  'src/sections/ReportsPage.tsx',
  'src/sections/ScoutingView.tsx',
  'src/sections/WaterTwinPage.tsx',
  'src/sections/ChatbotPage.tsx',
];

describe('FieldView UI-wide guards', () => {
  it('keeps core user-flow screens on useSelectedField', () => {
    for (const rel of fieldViewPages) {
      expect(read(rel), rel).toContain('useSelectedField');
    }
  });

  it('prevents direct FieldContext store reads in Chatbot runtime', () => {
    const source = read('src/sections/ChatbotPage.tsx');
    expect(source).not.toContain('useFieldContextStore');
    // The runtime resolves field context from the selected ID, not a client name.
    expect(source).toMatch(
      /const\s*\{\s*fieldId:\s*activeFieldId\s*\}\s*=\s*useSelectedField\(\)/,
    );
    expect(source).toMatch(
      /kongApi\.post\(\s*['"]\/api\/ai-agronomist\/chat['"]\s*,\s*\{[^}]*\bfield_id:\s*activeFieldId\s*\|\|\s*undefined\b/,
    );
  });

  it('keeps share/sql utilities FieldView-aware', () => {
    expect(read('src/components/sharing/SharingPanel.tsx')).toContain('useSelectedField');
    expect(read('src/components/sql/SQLEditor.tsx')).toContain('useSelectedField');
  });
});
