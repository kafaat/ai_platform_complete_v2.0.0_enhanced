// Each selected-crop chip's "×" remove button carries an accessible name, so a screen reader
// announces which crop it removes instead of a bare "times" glyph.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const files = ['fieldsetup/SeasonStep.tsx', 'AddSeasonWithStages.tsx'];

describe('crop chip remove buttons', () => {
  it.each(files)('%s names every × button', (file) => {
    const src = readFileSync(resolve(__dirname, file), 'utf8');
    // From each `<button` to its `×</button>`; `=>` inside handlers rules out a `[^>]*` scan.
    const buttons = [...src.matchAll(/<button\b(?:(?!<button)[\s\S])*?>\s*×\s*<\/button>/g)].map((m) => m[0]);
    expect(buttons.length).toBeGreaterThan(0);
    for (const button of buttons) {
      expect(button).toMatch(/aria-label=/);
      expect(button).toMatch(/type="button"/);
    }
  });
});
