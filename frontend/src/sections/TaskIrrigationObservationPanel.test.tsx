import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TaskIrrigationObservationPanel from "./TaskIrrigationObservationPanel";
const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  list: vi.fn(),
  executions: vi.fn(),
  state: {
    tenantId: "tenant-a",
    user: { id: 1, email: "farmer@example.test", role: "farmer" },
  },
}));
vi.mock("../hooks/useAuth", () => ({
  useAuthStore: Object.assign(() => mocks.state, {
    getState: () => mocks.state,
  }),
}));
vi.mock("../services/api/irrigationManualOperations", () => ({
  listManualExecutions: mocks.executions,
}));
vi.mock("../services/api/taskIrrigationObservations", () => ({
  recordTaskIrrigationObservation: mocks.post,
  listTaskIrrigationObservations: mocks.list,
}));
beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  mocks.state.tenantId = "tenant-a";
  mocks.executions.mockResolvedValue([
    {
      execution_id: "00000000-0000-4000-8000-000000000001",
      field_id: "field-a",
      system_id: "pivot",
      state: "started",
    },
  ]);
  mocks.list.mockResolvedValue([]);
});
describe("task irrigation observation workflow", () => {
  it("freezes and restores the original intent after a lost response", async () => {
    mocks.post
      .mockRejectedValueOnce(new Error("response lost"))
      .mockResolvedValueOnce(undefined);
    const first = render(
      <TaskIrrigationObservationPanel
        taskId="task-a"
        fieldId="field-a"
        onClose={() => {}}
      />,
    );
    await screen.findByRole("option", { name: /pivot/ });
    fireEvent.change(screen.getByLabelText("عملية الري المرتبطة"), {
      target: { value: "00000000-0000-4000-8000-000000000001" },
    });
    fireEvent.click(screen.getByRole("button", { name: "حفظ المشاهدة فقط" }));
    await screen.findByRole("button", { name: "إعادة إرسال المحاولة الأصلية" });
    await waitFor(() =>
      expect(screen.getByLabelText("نتيجة المشاهدة")).toBeDisabled(),
    );
    const original = mocks.post.mock.calls[0][1];
    first.unmount();
    render(
      <TaskIrrigationObservationPanel
        taskId="task-a"
        fieldId="field-a"
        onClose={() => {}}
      />,
    );
    fireEvent.click(
      await screen.findByRole("button", {
        name: "إعادة إرسال المحاولة الأصلية",
      }),
    );
    await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(2));
    expect(mocks.post.mock.calls[1][1]).toEqual(original);
    expect(original.volume_m3).toBeNull();
    expect(original).not.toHaveProperty("status");
    await screen.findByText(/حُفظت المشاهدة فقط/);
  });
  it("does not send if the immutable intent cannot be persisted", async () => {
    render(
      <TaskIrrigationObservationPanel
        taskId="task-a"
        fieldId="field-a"
        onClose={() => {}}
      />,
    );
    await screen.findByRole("option", { name: /pivot/ });
    fireEvent.change(screen.getByLabelText("عملية الري المرتبطة"), {
      target: { value: "00000000-0000-4000-8000-000000000001" },
    });
    const spy = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new Error("storage full");
      });
    fireEvent.click(screen.getByRole("button", { name: "حفظ المشاهدة فقط" }));
    await screen.findByRole("alert");
    expect(mocks.post).not.toHaveBeenCalled();
    spy.mockRestore();
  });
  it("keeps the frozen identity when retry authorization fails after an uncertain result", async () => {
    mocks.post
      .mockRejectedValueOnce(new Error("lost"))
      .mockRejectedValueOnce({ response: { status: 403 } });
    render(
      <TaskIrrigationObservationPanel
        taskId="task-a"
        fieldId="field-a"
        onClose={() => {}}
      />,
    );
    await screen.findByRole("option", { name: /pivot/ });
    fireEvent.change(screen.getByLabelText("عملية الري المرتبطة"), {
      target: { value: "00000000-0000-4000-8000-000000000001" },
    });
    fireEvent.click(screen.getByRole("button", { name: "حفظ المشاهدة فقط" }));
    fireEvent.click(
      await screen.findByRole("button", {
        name: "إعادة إرسال المحاولة الأصلية",
      }),
    );
    await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(2));
    expect(mocks.post.mock.calls[1][1]).toEqual(mocks.post.mock.calls[0][1]);
    await screen.findByRole("button", { name: "إعادة إرسال المحاولة الأصلية" });
    expect(screen.getByLabelText("نتيجة المشاهدة")).toBeDisabled();
    expect(sessionStorage.length).toBe(1);
  });
  it("clears old-owner pending state on an owner change without a new stored intent", async () => {
    mocks.post.mockRejectedValueOnce(new Error("lost"));
    const view = render(
      <TaskIrrigationObservationPanel
        taskId="task-a"
        fieldId="field-a"
        onClose={() => {}}
      />,
    );
    await screen.findByRole("option", { name: /pivot/ });
    fireEvent.change(screen.getByLabelText("عملية الري المرتبطة"), {
      target: { value: "00000000-0000-4000-8000-000000000001" },
    });
    fireEvent.click(screen.getByRole("button", { name: "حفظ المشاهدة فقط" }));
    await screen.findByRole("button", { name: "إعادة إرسال المحاولة الأصلية" });
    Object.assign(mocks.state, { tenantId: "tenant-b" });
    view.rerender(
      <TaskIrrigationObservationPanel
        taskId="task-a"
        fieldId="field-a"
        onClose={() => {}}
      />,
    );
    await screen.findByRole("button", { name: "حفظ المشاهدة فقط" });
    expect(screen.getByLabelText("عملية الري المرتبطة")).toHaveValue("");
    expect(
      screen.queryByRole("button", { name: "إعادة إرسال المحاولة الأصلية" }),
    ).toBeNull();
    expect(mocks.post).toHaveBeenCalledTimes(1);
  });
});
