import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ImpactCard } from "./ImpactCard";
import type { StoryImpact } from "@/lib/api";

function impact(over: Partial<StoryImpact> = {}): StoryImpact {
  return {
    cluster_id: "1",
    headline: "Headline here.",
    personal_relevance: { score: 82, one_liner: "Matters to you." },
    dimensions: {
      professional: {
        applicable: true, relevance: "Your work changes.", mechanism: "Because X.",
        watch_items: ["license terms", "vendor moves"], horizon: "weeks",
        confidence: "high", confidence_rationale: "", evidence: [],
      },
      financial: {
        applicable: true, relevance: "Exposure via the sector.", mechanism: "",
        watch_items: [], horizon: "quarter", confidence: "medium",
        confidence_rationale: "", evidence: [], not_advice: true,
      },
      civic: {
        applicable: false, relevance: "", mechanism: "", watch_items: [],
        horizon: "year_plus", confidence: "low", confidence_rationale: "", evidence: [],
      },
    },
    caveats: "Early signal.",
    ...over,
  };
}

describe("ImpactCard (Wave A)", () => {
  it("renders the relevance band chip with the numeric score", () => {
    render(<ImpactCard clusterId={1} data={impact()} />);
    expect(screen.getByText(/HIGH FOR YOU/)).toHaveTextContent("82");
  });

  it("shows applicable dimensions and hides applicable:false ones", () => {
    render(<ImpactCard clusterId={1} data={impact()} />);
    expect(screen.getByText("PROFESSION")).toBeInTheDocument();
    expect(screen.getByText("MONEY")).toBeInTheDocument();
    expect(screen.queryByText("CIVIC")).toBeNull();
  });

  it("shows the not-financial-advice disclaimer on the money dimension", () => {
    render(<ImpactCard clusterId={1} data={impact()} />);
    expect(screen.getByText(/not financial advice/i)).toBeInTheDocument();
  });

  it("invites personalization when profession is unset", () => {
    render(<ImpactCard clusterId={1} data={{ unavailable: true, reason: "profession_unset" }} />);
    expect(screen.getByText(/set your profession/i)).toBeInTheDocument();
  });

  it("renders nothing when unavailable for another reason", () => {
    const { container } = render(
      <ImpactCard clusterId={1} data={{ unavailable: true, reason: "no_llm_key" }} />
    );
    expect(container).toBeEmptyDOMElement();
  });
});
