import { describe, expect, it } from "vitest";
import {
  buildTaskIrrigationObservation,
  pendingObservationKey,
} from "./taskIrrigationObservation";
const base = {
  execution_id: "00000000-0000-4000-8000-000000000001",
  source: "farmer_task",
  outcome: "irrigated",
  quantity_method: "unknown",
  occurred_at: "2026-01-01T12:00:00+03:00",
};
describe("task irrigation observation input contract", () => {
  it("keeps unknown quantity null and emits a timezone", () => {
    const row = buildTaskIrrigationObservation(base, "id");
    expect(row.volume_m3).toBeNull();
    expect(row.occurred_at).toBe("2026-01-01T09:00:00.000Z");
    expect(row).not.toHaveProperty("depth_mm");
    expect(row).not.toHaveProperty("status");
  });
  it("drops hidden quantity and area after outcome changes", () => {
    const row = buildTaskIrrigationObservation(
      {
        ...base,
        outcome: "not_irrigated",
        quantity_method: "meter",
        meter_start_m3: "100",
        meter_end_m3: "120",
        irrigated_area_ha: "50",
      },
      "id",
    );
    expect(row.quantity_method).toBe("unknown");
    expect(row.volume_m3).toBeNull();
    expect(row).not.toHaveProperty("meter_start_m3");
    expect(row).not.toHaveProperty("irrigated_area_ha");
  });
  it("preserves measured readings and does not manufacture a verified volume", () => {
    const row = buildTaskIrrigationObservation(
      {
        ...base,
        quantity_method: "meter",
        meter_start_m3: "100",
        meter_end_m3: "120",
        irrigated_area_ha: "2",
      },
      "id",
    );
    expect(row.meter_start_m3).toBe(100);
    expect(row.meter_end_m3).toBe(120);
    expect(row.volume_m3).toBeNull();
  });
  it.each(["NaN", "Infinity", "-1"])(
    "rejects invalid numeric value %s",
    (value) => {
      expect(() =>
        buildTaskIrrigationObservation(
          { ...base, quantity_method: "declared_volume", volume_m3: value },
          "id",
        ),
      ).toThrow();
    },
  );
  it("rejects backwards meters", () => {
    expect(() =>
      buildTaskIrrigationObservation(
        {
          ...base,
          quantity_method: "meter",
          meter_start_m3: "120",
          meter_end_m3: "100",
        },
        "id",
      ),
    ).toThrow();
  });
  it.each([
    { flow_m3_h: "0", duration_minutes: "60", interruptions_minutes: "0" },
    { flow_m3_h: "390", duration_minutes: "60", interruptions_minutes: "60" },
  ])("rejects impossible pumping duration/flow", (values) => {
    expect(() =>
      buildTaskIrrigationObservation(
        { ...base, quantity_method: "estimated_flow", ...values },
        "id",
      ),
    ).toThrow();
  });
  it("separates the pending intent by tenant, actor and task", () => {
    const key = pendingObservationKey("a", "u1", "task");
    expect(key).not.toBe(pendingObservationKey("a", "u2", "task"));
    expect(key).not.toBe(pendingObservationKey("b", "u1", "task"));
    expect(key).not.toBe(pendingObservationKey("a", "u1", "other"));
  });
});
