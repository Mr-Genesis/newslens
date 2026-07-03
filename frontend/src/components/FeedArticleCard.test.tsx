import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { FeedArticleCard } from "./FeedArticleCard";
import type { Article } from "@/lib/api";

function make(over: Partial<Article> = {}): Article {
  return {
    id: 1, title: "A story", url: "https://ext.example/a", snippet: "snippet", ai_summary: null,
    published_at: "2026-07-04T00:00:00Z", fetched_at: "2026-07-04T00:00:00Z",
    source: { id: 1, name: "Reuters", url: "https://reuters.example", is_paywalled: false },
    topics: [], cluster_id: null, ...over,
  } as Article;
}

describe("FeedArticleCard (#93)", () => {
  it("links a clustered article to the deep dive", () => {
    render(<FeedArticleCard article={make({ title: "Clustered", cluster_id: 5 })} />);
    const link = screen.getByText("Clustered").closest("a") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/story/5");
  });

  it("links an unclustered article out to the source (new tab)", () => {
    render(<FeedArticleCard article={make({ title: "Lonely", cluster_id: null, url: "https://ext.example/x" })} />);
    const link = screen.getByText("Lonely").closest("a") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("https://ext.example/x");
    expect(link.getAttribute("target")).toBe("_blank");
  });

  it("badges a research source and leaves a news source unbadged", () => {
    const { rerender } = render(
      <FeedArticleCard article={make({
        source: { id: 2, name: "NEJM", url: "https://nejm.example", is_paywalled: true, source_type: "research" },
      })} />
    );
    expect(screen.getByText("RESEARCH")).toBeInTheDocument();

    rerender(<FeedArticleCard article={make({
      source: { id: 3, name: "Reuters", url: "https://reuters.example", is_paywalled: false, source_type: "wire" },
    })} />);
    expect(screen.queryByText("RESEARCH")).toBeNull();
    expect(screen.queryByText("EXPERT")).toBeNull();
  });
});
