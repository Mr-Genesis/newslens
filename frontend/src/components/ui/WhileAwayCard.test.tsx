import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({ getDigest: vi.fn() }));

import { WhileAwayCard } from "./WhileAwayCard";
import { getDigest } from "@/lib/api";

describe("WhileAwayCard (Wave C)", () => {
  beforeEach(() => vi.mocked(getDigest).mockReset());

  it("renders the digest items when something moved", async () => {
    vi.mocked(getDigest).mockResolvedValue({
      count: 2,
      since: "2026-06-23T00:00:00Z",
      items: [
        { cluster_id: 1, title: "Story One", headline: "Touches your work." },
        { cluster_id: 2, title: "Story Two", headline: null },
      ],
    });
    render(<WhileAwayCard />);
    expect(await screen.findByText(/while you were away/i)).toBeInTheDocument();
    expect(screen.getByText("Story One")).toBeInTheDocument();
    expect(screen.getByText("Touches your work.")).toBeInTheDocument();
  });

  it("renders nothing when caught up", async () => {
    vi.mocked(getDigest).mockResolvedValue({ count: 0, since: "x", items: [] });
    const { container } = render(<WhileAwayCard />);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});

class FakeES {
  static instances: FakeES[] = [];
  url: string;
  closed = false;
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  onerror: unknown = null;
  constructor(url: string) {
    this.url = url;
    FakeES.instances.push(this);
  }
  addEventListener(type: string, cb: (e: MessageEvent) => void) {
    (this.listeners[type] ||= []).push(cb);
  }
  removeEventListener(type: string, cb: (e: MessageEvent) => void) {
    this.listeners[type] = (this.listeners[type] || []).filter((c) => c !== cb);
  }
  emit(type: string, data: unknown) {
    (this.listeners[type] || []).forEach((cb) => cb({ data: JSON.stringify(data) } as MessageEvent));
  }
  close() {
    this.closed = true;
  }
}

const DIGEST = { count: 1, since: "2026-07-04", items: [{ cluster_id: 5, title: "A story", headline: "why" }] };

describe("WhileAwayCard live refresh (#102)", () => {
  beforeEach(() => {
    FakeES.instances = [];
    vi.stubGlobal("EventSource", FakeES);
    vi.mocked(getDigest).mockReset().mockResolvedValue(DIGEST);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("fetches the digest on mount and re-fetches on a feed_refresh event", async () => {
    render(<WhileAwayCard />);
    await waitFor(() => expect(screen.getByText("A story")).toBeInTheDocument());
    expect(getDigest).toHaveBeenCalledTimes(1);
    expect(FakeES.instances).toHaveLength(1);

    FakeES.instances[0].emit("feed_refresh", { new_articles: 3 });
    await waitFor(() => expect(getDigest).toHaveBeenCalledTimes(2));
  });

  it("closes the EventSource on unmount", async () => {
    const { unmount } = render(<WhileAwayCard />);
    await waitFor(() => expect(FakeES.instances).toHaveLength(1));
    unmount();
    expect(FakeES.instances[0].closed).toBe(true);
  });
});
