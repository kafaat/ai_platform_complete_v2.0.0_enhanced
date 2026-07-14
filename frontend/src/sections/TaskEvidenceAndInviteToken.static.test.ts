import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = process.cwd();
const tasks = readFileSync(join(root, 'src/sections/TasksPage.tsx'), 'utf8');
const invite = readFileSync(join(root, 'src/pages/AcceptInvitationPage.tsx'), 'utf8');

// continuation-3 P0: اختيار صورة لا يُكمل المهمّة (كان يُنشئ أثر إنجازٍ موثَّق بصورة
// بينما السجلّ الدائم بلا صورة). المعاينة محلّيّة صريحة، والإكمال إجراء مستقلّ.
describe('F-tasks — photo preview is decoupled from completion', () => {
  it('handlePhotoUpload لا يستدعي completeTask', () => {
    const start = tasks.indexOf('const handlePhotoUpload');
    const block = tasks.slice(start, tasks.indexOf('const TaskCard', start));
    expect(block).not.toContain('completeTask(');
    // يُبطِل رابط المعاينة السابق (لا تسريب object URL).
    expect(block).toContain('URL.revokeObjectURL(');
  });

  it('المعاينة المحلّيّة مُعلَّمة صراحةً بأنّها غير مرفوعة', () => {
    expect(tasks).toContain('لم تُرفَع بعد');
  });
});

// continuation-1 P0: رمز الدعوة يُزال من الرابط بعد التقاطه (لا يبقى في السجلّ/اللقطات).
describe('F-invite — invitation token is stripped from the URL after capture', () => {
  it('AcceptInvitationPage يستدعي history.replaceState لإزالة token', () => {
    expect(invite).toContain('history.replaceState');
    expect(invite).toContain("params.delete('token')");
  });
});
