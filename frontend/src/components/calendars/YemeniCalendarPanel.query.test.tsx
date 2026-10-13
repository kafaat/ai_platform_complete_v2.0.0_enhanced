// حالاتُ React Query الحقيقيّة على لوحة التقويم — المكتبةُ المقفلة في المستودع لا بدائل.
// FRONTEND-REFERENCE-PANELS-HIDE-OR-FAKE-STATE-ON-PAUSE-AND-REFETCH-ERROR-01.
//
// كلُّ اختبارٍ يُثبت **الحالة التي بلغها الاستعلام** (getQueryState) قبل أن يحكم على العرض؛
// فظهورُ البيانات وغيابُ الطلب وحدهما يتحقّقان أيضاً إن لم تبدأ إعادةُ الجلب أصلاً.
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import {
  QueryClient,
  QueryClientProvider,
  onlineManager,
} from "@tanstack/react-query";
import YemeniCalendarPanel from "./YemeniCalendarPanel";

const api = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../../services/api", () => ({ kongApi: { get: api.get } }));

const MANSIONS = "/api/v1/calendars/lunar-mansions";
const KEY = ["calendars", "lunar-mansions"] as const;

let mansionName = "الشرطان";
let mansionsFail = false;

function respond(path: string) {
  if (path === MANSIONS) {
    if (mansionsFail) return Promise.reject(new Error("network down"));
    return Promise.resolve({
      data: { mansions: [{ order: 1, name_ar: mansionName }] },
    });
  }
  if (path === "/api/v1/calendars/himyarite-months") {
    return Promise.resolve({
      data: { months: [{ order: 1, name_ar: "ذو الثابة" }] },
    });
  }
  return Promise.resolve({ data: { date_iso: "2026-10-03" } });
}

const mansionCalls = () =>
  api.get.mock.calls.filter(([p]) => p === MANSIONS).length;

let client: QueryClient;
function setup() {
  api.get.mockImplementation(respond);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  render(<YemeniCalendarPanel />, { wrapper });
}

afterEach(() => {
  onlineManager.setOnline(true);
  client?.clear();
  api.get.mockReset();
  mansionName = "الشرطان";
  mansionsFail = false;
});

describe("لوحة التقويم تحت حالات React Query الحقيقيّة", () => {
  it("البياناتُ المخبّأة تبقى ظاهرةً حين تتوقّف إعادةُ جلبها بلا اتّصال، ثمّ تتحدّث عند عودته", async () => {
    setup();
    expect(await screen.findByText("الشرطان")).toBeInTheDocument();
    expect(mansionCalls()).toBe(1);

    onlineManager.setOnline(false);
    await act(() => client.invalidateQueries({ queryKey: KEY }));
    await waitFor(() =>
      expect(client.getQueryState(KEY)).toMatchObject({
        status: "success",
        fetchStatus: "paused",
      }),
    );
    expect(screen.getByText("الشرطان")).toBeInTheDocument();
    expect(screen.getByText(/التحديث متوقّف: لا اتّصال/)).toBeInTheDocument();
    expect(mansionCalls()).toBe(1);

    mansionName = "منزلة بعد العودة";
    onlineManager.setOnline(true);
    await waitFor(() =>
      expect(client.getQueryState(KEY)).toMatchObject({
        status: "success",
        fetchStatus: "idle",
      }),
    );
    expect(await screen.findByText("منزلة بعد العودة")).toBeInTheDocument();
    expect(mansionCalls()).toBe(2);
    expect(screen.queryByText(/التحديث متوقّف/)).not.toBeInTheDocument();
  });

  it("بلا اتّصالٍ قبل أوّل بيانات: إشعارُ انقطاع، لا «لا منازل متاحة» ولا تحميلٌ دائم", async () => {
    onlineManager.setOnline(false);
    setup();
    await waitFor(() =>
      expect(client.getQueryState(KEY)).toMatchObject({
        status: "pending",
        fetchStatus: "paused",
      }),
    );
    expect(
      screen.getAllByText(/لا اتّصال، ولم تُحمَّل هذه البيانات بعد/).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText("لا منازل متاحة.")).not.toBeInTheDocument();
    expect(screen.queryByText("جارٍ التحميل…")).not.toBeInTheDocument();
    expect(mansionCalls()).toBe(0);
  });

  it("فشلُ تحديثٍ خلفيّ لا يُخفي آخرَ بياناتٍ ناجحة، ويُقال تحذيراً غيرَ حاجب", async () => {
    setup();
    expect(await screen.findByText("الشرطان")).toBeInTheDocument();

    mansionsFail = true;
    await act(() => client.invalidateQueries({ queryKey: KEY }));
    await waitFor(() =>
      expect(client.getQueryState(KEY)).toMatchObject({
        status: "error",
        fetchStatus: "idle",
      }),
    );
    expect(client.getQueryData(KEY)).toBeDefined();
    expect(screen.getByText("الشرطان")).toBeInTheDocument();
    expect(screen.getByText(/تعذّر تحديث البيانات/)).toBeInTheDocument();
    expect(
      screen.queryByText("تعذّر تحميل المنازل القمريّة."),
    ).not.toBeInTheDocument();
  });
});
