import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SpeakButton from "./SpeakButton";
import { synthesizeSpeech } from "../services/api";

vi.mock("../services/api", () => ({ synthesizeSpeech: vi.fn() }));

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe("SpeakButton unavailable audio", () => {
  it("keeps written advice and announces blocked synthesis", async () => {
    vi.mocked(synthesizeSpeech).mockRejectedValue(new Error("blocked"));
    render(
      <>
        <p>التوصية المكتوبة</p>
        <SpeakButton text="التوصية المكتوبة" />
      </>,
    );
    fireEvent.click(screen.getByRole("button", { name: "استماع" }));
    expect(
      await screen.findByRole("button", {
        name: "الصوت غير متاح؛ اقرأ التوصية المكتوبة",
      }),
    ).toBeTruthy();
    expect(screen.getByText("التوصية المكتوبة")).toBeTruthy();
    expect(
      screen.getByText("الصوت غير متاح؛ اقرأ النص").getAttribute("aria-live"),
    ).toBe("polite");
  });

  it("allows a new attempt after failure without clipping the written text", async () => {
    vi.mocked(synthesizeSpeech).mockRejectedValue(new Error("unavailable"));
    const text = "هذه توصية مكتوبة تبقى ظاهرة";
    render(<SpeakButton text={text} />);
    fireEvent.click(screen.getByRole("button", { name: "استماع" }));
    fireEvent.click(
      await screen.findByRole("button", {
        name: "الصوت غير متاح؛ اقرأ التوصية المكتوبة",
      }),
    );
    await screen.findByRole("button", {
      name: "الصوت غير متاح؛ اقرأ التوصية المكتوبة",
    });
    expect(synthesizeSpeech).toHaveBeenCalledTimes(2);
    expect(synthesizeSpeech).toHaveBeenNthCalledWith(2, text);
  });
});
