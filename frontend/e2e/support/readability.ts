import { expect, type Locator } from '@playwright/test';

export async function expectReadableText(element: Locator) {
  await expect(element).toBeVisible();
  const result = await element.evaluate(node => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 1;
    const context = canvas.getContext('2d', { willReadFrequently: true })!;
    const luminance = (color: string) => {
      // Tailwind may return oklch(), so use the browser's sRGB conversion.
      context.fillStyle = color;
      context.fillRect(0, 0, 1, 1);
      const rgb = Array.from(context.getImageData(0, 0, 1, 1).data).slice(0, 3);
      const linear = rgb.map(channel => {
        const value = channel / 255;
        return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
      });
      return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
    };
    let surface: Element | null = node;
    while (surface) {
      const background = getComputedStyle(surface).backgroundColor;
      if (background !== 'transparent' && background !== 'rgba(0, 0, 0, 0)') {
        const foreground = getComputedStyle(node).color;
        const foregroundL = luminance(foreground);
        const backgroundL = luminance(background);
        return {
          foreground,
          background,
          contrast: (Math.max(foregroundL, backgroundL) + 0.05) / (Math.min(foregroundL, backgroundL) + 0.05),
        };
      }
      surface = surface.parentElement;
    }
    throw new Error('The text must have a painted background');
  });
  expect(result.contrast, JSON.stringify(result)).toBeGreaterThanOrEqual(4.5);
}
