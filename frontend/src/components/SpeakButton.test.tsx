import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SpeakButton from "./SpeakButton";
import { synthesizeSpeech } from "../services/api";

vi.mock("../services/api", () => ({ synthesizeSpeech: vi.fn() }));

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  vi.unstubAllGlobals();
});

function mockAudio(play: (index: number) => Promise<void>) {
  const instances: MockAudio[] = [];
  class MockAudio {
    onended: (() => void) | null = null;
    onerror: (() => void) | null = null;
    pause = vi.fn();
    play = vi.fn(() => play(instances.indexOf(this)));

    constructor() {
      instances.push(this);
    }
  }
  vi.stubGlobal("Audio", MockAudio);
  vi.stubGlobal("URL", {
    createObjectURL: vi
      .fn()
      .mockReturnValueOnce("blob:old")
      .mockReturnValueOnce("blob:new"),
    revokeObjectURL: vi.fn(),
  });
  vi.mocked(synthesizeSpeech).mockResolvedValue(
    new Blob(["audio"], { type: "audio/mpeg" }),
  );
  return instances;
}

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

  it("clears failure for a different recommendation", async () => {
    vi.mocked(synthesizeSpeech).mockRejectedValue(new Error("blocked"));
    const view = render(<SpeakButton text="النص الأول" />);
    fireEvent.click(screen.getByRole("button", { name: "استماع" }));
    await screen.findByRole("button", {
      name: "الصوت غير متاح؛ اقرأ التوصية المكتوبة",
    });
    view.rerender(<SpeakButton text="النص الثاني" />);
    expect(screen.getByRole("button", { name: "استماع" })).toBeTruthy();
  });

  it("ignores delayed playback completion for a replaced recommendation", async () => {
    let completePlayback!: () => void;
    const pendingPlayback = new Promise<void>((resolve) => {
      completePlayback = resolve;
    });
    const audio = mockAudio(() => pendingPlayback);
    const view = render(<SpeakButton text="النص الأول" />);
    fireEvent.click(screen.getByRole("button", { name: "استماع" }));
    await waitFor(() => expect(audio).toHaveLength(1));
    view.rerender(<SpeakButton text="النص الثاني" />);
    await act(async () => completePlayback());
    expect(screen.getByRole("button", { name: "استماع" })).toBeTruthy();
    expect(audio[0].pause).toHaveBeenCalled();
  });

  it("keeps new audio and its URL when old audio emits late events", async () => {
    const audio = mockAudio(async () => {});
    const view = render(<SpeakButton text="النص الأول" />);
    fireEvent.click(screen.getByRole("button", { name: "استماع" }));
    await screen.findByRole("button", { name: "إيقاف الاستماع" });
    view.rerender(<SpeakButton text="النص الثاني" />);
    fireEvent.click(screen.getByRole("button", { name: "استماع" }));
    await screen.findByRole("button", { name: "إيقاف الاستماع" });
    act(() => {
      audio[0].onended?.();
      audio[0].onerror?.();
    });
    expect(screen.getByRole("button", { name: "إيقاف الاستماع" })).toBeTruthy();
    expect(URL.revokeObjectURL).not.toHaveBeenCalledWith("blob:new");
  });
});
