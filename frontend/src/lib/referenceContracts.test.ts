// عيّناتُ «الشكل الصحيح» منقولةٌ من مُخرَج دوالّ المنصّة نفسها (yemeni_calendars.py ·
// climate_analogs.py) — والوجهُ الآخر: كلُّ شكلٍ غير متوقّع خطأٌ صريح لا قائمةٌ فارغة.
import { describe, it, expect } from "vitest";
import {
  ApiShapeError,
  parseClimateAnalogRegions,
  parseDesertCrops,
  parseHimyariteMonths,
  parseLunarMansions,
  parseRegionalProfiles,
} from "./referenceContracts";

const mansionsBody = {
  display_only: true,
  count: 28,
  structure_ar: "٢٨ منزلة قمريّة",
  mansions: [
    {
      order: 1,
      name_ar: "الشرطان",
      approx_start_ar: "17/4",
      duration_days: 13,
      season_ar: "الصيف",
      note_ar: "بدء النجوم الشاميّة",
    },
  ],
  source_ar: "الموروث الفلكي",
};

const monthsBody = {
  display_only: true,
  count: 12,
  months: [
    {
      order: 1,
      name_ar: "ذو الثابة",
      approx_gregorian_ar: "≈ أبريل",
      meaning_ar: "أوّل الشهور الزراعيّة",
      season_himyari_ar: "دثا (الصيف)",
    },
  ],
};

const regionsBody = {
  regions: [
    {
      region_ar: "الجوف السعوديّة",
      country_ar: "السعوديّة",
      similarity_pct: 95,
      proven_crops_ar: [],
    },
  ],
  count: 1,
};

/** الأشكال التي كانت تُسقط الصفحة أو قد تصل من وسيطٍ معطوب. */
const wrongShapes: unknown[] = [
  null,
  undefined,
  "error",
  42,
  [],
  {},
  { detail: "Not Found" },
];

describe("التقاويم: يُفكّ الغلافُ المعروف", () => {
  it("المنازل والشهور والملفّات تُعاد مصفوفاتٍ بحقول الخادم", () => {
    const mansions = parseLunarMansions(mansionsBody);
    expect(mansions).toHaveLength(1);
    expect(mansions[0]).toMatchObject({ order: 1, name_ar: "الشرطان" });
    expect(parseHimyariteMonths(monthsBody)[0].approx_gregorian_ar).toBe(
      "≈ أبريل",
    );
    expect(
      parseRegionalProfiles({ profiles: [{ region_ar: "وادي حضرموت" }] }),
    ).toHaveLength(1);
  });

  it("غلافٌ صحيح بقائمةٍ فارغة يبقى «لا بيانات» لا خطأ", () => {
    expect(parseLunarMansions({ ...mansionsBody, mansions: [] })).toEqual([]);
  });

  it.each(wrongShapes)(
    "شكلٌ غير متوقّع (%j) خطأٌ صريح لا قائمةٌ فارغة",
    (body) => {
      expect(() => parseLunarMansions(body)).toThrow(ApiShapeError);
      expect(() => parseHimyariteMonths(body)).toThrow(ApiShapeError);
      expect(() => parseRegionalProfiles(body)).toThrow(ApiShapeError);
    },
  );

  it("المصفوفةُ العارية — الشكلُ الذي افترضته الواجهة خطأً — مرفوضةٌ أيضاً", () => {
    expect(() => parseLunarMansions(mansionsBody.mansions)).toThrow(
      /lunar-mansions/,
    );
  });
});

describe("النظائر المناخيّة", () => {
  it("المناطق تُطبَّع: region للتفصيل، والنسبة المئويّة كسرٌ", () => {
    const [r] = parseClimateAnalogRegions(regionsBody);
    expect(r.region).toBe("الجوف السعوديّة");
    expect(r.name_ar).toBe("الجوف السعوديّة");
    expect(r.similarity).toBeCloseTo(0.95);
  });

  it("منطقةٌ بلا region_ar خطأُ عقد، لا زرٌّ بلا اسم", () => {
    expect(() =>
      parseClimateAnalogRegions({ regions: [{ country_ar: "س" }] }),
    ).toThrow(ApiShapeError);
  });

  it.each(wrongShapes)(
    "قائمةُ المناطق بشكلٍ غير متوقّع (%j) خطأٌ صريح",
    (body) => {
      expect(() => parseClimateAnalogRegions(body)).toThrow(ApiShapeError);
    },
  );

  it("المحاصيل لفئةٍ واحدة: خريطةُ «محصول ← تقييم» تصير صفوفاً", () => {
    const crops = parseDesertCrops({
      category: "trees",
      crops: { النخيل: "ممتاز", الزيتون: "ممتاز" },
    });
    expect(crops).toEqual([
      {
        crop: "النخيل",
        name_ar: "النخيل",
        rating: "ممتاز",
        category: undefined,
      },
      {
        crop: "الزيتون",
        name_ar: "الزيتون",
        rating: "ممتاز",
        category: undefined,
      },
    ]);
  });

  it("المحاصيل للكلّ: الفئاتُ الثلاث تُسطَّح وتحمل اسمَ فئتها", () => {
    const crops = parseDesertCrops({
      all_categories: {
        trees_ar: { النخيل: "ممتاز" },
        modern_ar: { "الزراعة المحميّة": "ممتاز" },
      },
    });
    expect(crops.map((c) => c.category)).toEqual(["أشجار", "حديثة"]);
  });

  it.each(wrongShapes)("المحاصيل بشكلٍ غير متوقّع (%j) خطأٌ صريح", (body) => {
    expect(() => parseDesertCrops(body)).toThrow(ApiShapeError);
  });

  it("crops ليست خريطة ⇒ خطأ", () => {
    expect(() => parseDesertCrops({ crops: ["النخيل"] })).toThrow(
      ApiShapeError,
    );
  });
});
