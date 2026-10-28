import { beforeEach, expect, it, vi } from "vitest";
import {
  listTaskIrrigationObservations,
  recordTaskIrrigationObservation,
  type TaskIrrigationObservation,
} from "./taskIrrigationObservations";
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("./client", () => ({ kongApi: api }));
beforeEach(() => vi.clearAllMocks());
it("reads the scoped observation projection from the existing tasks route", async () => {
  const rows = [{ observation_id: "saved" }];
  api.get.mockResolvedValue({
    data: { tasks: [], irrigation_observations: rows },
  });
  expect(await listTaskIrrigationObservations("task-a")).toEqual(rows);
  expect(api.get).toHaveBeenCalledWith("/api/v1/tasks", {
    params: { irrigation_task_id: "task-a" },
  });
});
it("does not silently interpret a task-only response as empty observations", async () => {
  api.get.mockResolvedValue({ data: { tasks: [] } });
  await expect(listTaskIrrigationObservations("task-a")).rejects.toThrow();
});
it("submits the immutable intent through the existing observations route", async () => {
  const observation: TaskIrrigationObservation = {
    observation_id: "immutable-id",
    execution_id: "operation-a",
    source: "farmer_task",
    outcome: "unknown",
    quantity_method: "unknown",
    occurred_at: "2026-01-01T00:00:00Z",
    interruptions_minutes: 0,
    volume_m3: null,
  };
  api.post.mockResolvedValue({ data: observation });
  await recordTaskIrrigationObservation("task-a", observation);
  expect(api.post).toHaveBeenCalledWith(
    "/api/v1/observations",
    { task_id: "task-a", irrigation_observation: observation },
    { headers: { "Idempotency-Key": "immutable-id" } },
  );
});
