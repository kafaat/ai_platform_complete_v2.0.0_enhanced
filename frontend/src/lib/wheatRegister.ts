import type { Sheet } from 'read-excel-file/browser';

export const wheatCultivars = ['علس', 'حبيب', 'بوني', 'حميري', 'سمراء'];
export type WheatReference = {
  sheet: string; variety: string; hectares: number; seedKg: number; rainfed: boolean; day: string;
};

function cultivar(value: unknown) {
  const name = String(value ?? '').trim().replace(/^قمح\s+/, '').replace(/^ال/, '');
  return wheatCultivars.find(v => v === name);
}

export function readWheatReferences(sheets: Sheet[]) {
  const refs: WheatReference[] = [];
  for (const { sheet, data } of sheets) {
    const header = data.findIndex(r => String(r[1]).includes('مساحة القطاع') && String(r[4]).trim() === 'نوع البذور' && String(r[6]).includes('كمية البذور'));
    if (header < 0) continue;
    const unit = String(data[header][1]);
    const divisor = unit.includes('متر مربع') ? 10000 : unit.includes('هكتار') ? 1 : 0;
    const rows = data.slice(header + 1);
    const areas = rows.map(r => r[1]).filter(v => v != null);
    const lots = rows.filter(r => r[4] != null || r[6] != null || r[2] != null);
    const variety = cultivar(lots[0]?.[4]);
    if (!divisor || areas.length !== 1 || typeof areas[0] !== 'number' || areas[0] <= 0
      || !variety || !lots.every(r => cultivar(r[4]) === variety && typeof r[6] === 'number' && r[6] > 0)) continue;
    const dates = lots.flatMap(r => r[2] instanceof Date ? [r[2].toISOString().slice(0, 10)] : []).sort();
    refs.push({ sheet: sheet.trim(), variety, hectares: areas[0] / divisor,
      seedKg: lots.reduce((sum, row) => sum + Number(row[6]), 0),
      rainfed: sheet.includes('الري المطري'), day: dates[0] ?? '' });
  }
  return refs;
}
