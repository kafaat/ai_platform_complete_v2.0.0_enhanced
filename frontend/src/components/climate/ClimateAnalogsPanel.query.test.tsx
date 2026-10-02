// لوحةُ النظائر المناخيّة تحت حالات React Query الحقيقيّة + فحصٌ بنيويّ للمواضع السبعة.
// FRONTEND-REFERENCE-PANELS-HIDE-OR-FAKE-STATE-ON-PAUSE-AND-REFETCH-ERROR-01.
import type { ReactNode } from "react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import {
  QueryClient,
  QueryClientProvider,
  onlineManager,
} from "@tanstack/react-query";
import ClimateAnalogsPanel from "./ClimateAnalogsPanel";

const api = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../../services/api", () => ({ kongApi: { get: api.get } }));

const LIST = "/api/v1/climate-analogs/list";
const KEY = ["climate-analogs", "list"] as const;
let listFail = false;

function respond(path: string) {
  if (path === LIST) {
    if (listFail) return Promise.reject(new Error("network down"));
    return Promise.resolve({
      data: {
        regions: [
          {
            region_ar: "الجوف السعوديّة",
            country_ar: "السعوديّة",
            similarity_pct: 95,
          },
        ],
      },
    });
  }
  if (path === "/api/v1/climate-analogs/desert-crops") {
    return Promise.resolve({
      data: { all_categories: { trees_ar: { النخيل: "ممتاز" } } },
    });
  }
  return Promise.resolve({ data: { tiers: [] } });
}

let client: QueryClient;
function setup() {
  api.get.mockImplementation(respond);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  render(<ClimateAnalogsPanel />, { wrapper });
}

afterEach(() => {
  onlineManager.setOnline(true);
  client?.clear();
  api.get.mockReset();
  listFail = false;
});

describe("لوحة النظائر المناخيّة تحت حالات React Query الحقيقيّة", () => {
  it("بلا اتّصالٍ قبل أوّل بيانات: إشعارُ انقطاع، لا «لا مناطق نظيرة متاحة»", async () => {
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
    expect(screen.queryByText("لا مناطق نظيرة متاحة.")).not.toBeInTheDocument();
  });

  it("فشلُ تحديث القائمة لا يُخفي المناطق الناجحة", async () => {
    setup();
    expect(await screen.findByText(/الجوف السعوديّة/)).toBeInTheDocument();
    listFail = true;
    await act(() => client.invalidateQueries({ queryKey: KEY }));
    await waitFor(() =>
      expect(client.getQueryState(KEY)).toMatchObject({
        status: "error",
        fetchStatus: "idle",
      }),
    );
    expect(screen.getByText(/الجوف السعوديّة/)).toBeInTheDocument();
    expect(screen.getByText(/تعذّر تحديث البيانات/)).toBeInTheDocument();
    expect(
      screen.queryByText("تعذّر تحميل النظائر المناخيّة."),
    ).not.toBeInTheDocument();
  });
});

describe("المواضعُ السبعة تمرّ كلُّها بـReferenceQueryState", () => {
  // لا يقرأ أيُّ موضعٍ isLoading/isError مباشرةً: تلك السلسلةُ هي ما كان يكذب.
  it.each([
    [
      "../calendars/YemeniCalendarPanel.tsx",
      ["contextQuery", "mansionsQuery", "monthsQuery"],
    ],
    [
      "./ClimateAnalogsPanel.tsx",
      ["listQuery", "detailQuery", "cropsQuery", "tiersQuery"],
    ],
  ])("%s", (file, queries) => {
    const source = readFileSync(resolve(__dirname, file), "utf-8");
    expect(source).not.toMatch(/\.(isLoading|isError|isPending)\b/);
    for (const name of queries) {
      expect(source).toContain(`query={${name}}`);
    }
  });
});
