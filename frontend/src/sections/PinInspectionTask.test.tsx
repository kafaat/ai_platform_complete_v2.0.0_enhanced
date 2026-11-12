import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, test, expect } from "vitest";
import { PinInspectionTask } from "./PinInspectionTask";
import { kongApi } from "../services/api";

vi.mock("./InspectionHandoff", () => ({ InspectionHandoff: () => null }));
vi.mock("../services/api", () => ({
  kongApi: { get: vi.fn(), post: vi.fn() },
}));
test("manager assigns a server pin, then reads the saved task from the returned receipt", async () => {
  vi.mocked(kongApi.get).mockImplementation(
    async (path) =>
      ({
        data: path.endsWith("inspection-assignees")
          ? { assignees: [{ id: 7, full_name: "مختبر" }] }
          : { task: null },
      }) as never,
  );
  vi.mocked(kongApi.post).mockResolvedValue({
    data: {
      persisted: true,
      task: {
        task_id: "F-01",
        assigned_to: "7",
        due_at: "2026-11-12T08:30:00+03:00",
        status: "pending",
        priority: 3,
      },
    },
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <PinInspectionTask
        field="wheat"
        role="manager"
        tenant="tenant"
        pins={[{ id: "P-01", lat: 16, lng: 45 }]}
      />
    </QueryClientProvider>,
  );
  fireEvent.change(screen.getByLabelText("متابعة دبوس محفوظ"), {
    target: { value: "P-01" },
  });
  await screen.findByText("مختبر");
  fireEvent.change(screen.getByLabelText("المفتش"), { target: { value: "7" } });
  fireEvent.change(screen.getByLabelText("موعد النتيجة"), {
    target: { value: "2026-11-12T08:30" },
  });
  fireEvent.click(screen.getByRole("button", { name: "تكليف بزيارة تفتيش" }));
  await waitFor(() =>
    expect(kongApi.post).toHaveBeenCalledWith(
      "/api/v1/fields/wheat/pins/P-01/inspection-task",
      {
        assigned_to: 7,
        priority: 3,
        due_at: expect.stringMatching(/^2026-11-12T08:30[+-]\d\d:\d\d$/),
      },
    ),
  );
  await screen.findByText(/F-01/);
});
