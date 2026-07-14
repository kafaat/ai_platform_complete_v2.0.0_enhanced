import { describe, expect, it } from "vitest";
import { IRRIGATION_ENGINEERING_SECTIONS } from "./irrigationEngineering";

describe("IRR-X1 workspace contract", () => {
  it("keeps vendor-neutral operational sections", () => {
    expect(IRRIGATION_ENGINEERING_SECTIONS).toContain("water_demand");
    expect(IRRIGATION_ENGINEERING_SECTIONS).toContain("commissioning");
    expect(IRRIGATION_ENGINEERING_SECTIONS).toContain("manual_operation");
    expect(IRRIGATION_ENGINEERING_SECTIONS).not.toContain("valley");
  });
});
