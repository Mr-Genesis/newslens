"""Wave D1: the single retrieval seam.

The deep dive was thin because lenses saw only the ≤300-char ``snippet``. This module assembles a
depth-budgeted context from the FULL article body (``extracted_text``, captured at ingest) with a
snippet fallback. All lenses route their source-text assembly through here, so deepening retrieval
is one change, not five. The depth ladder (brief/standard/expert, from ``persona.depth_pref``) is a
per-source character BUDGET — not a separate engine.
"""

# Per-source character budget by depth preference.
_DEPTH_BUDGET = {"brief": 800, "standard": 2500, "expert": 16000}


def budget_for(depth_pref: str | None) -> int:
    return _DEPTH_BUDGET.get((depth_pref or "standard"), _DEPTH_BUDGET["standard"])


def _body(article) -> str:
    """Full extracted body if present, else the snippet, else the title."""
    return (getattr(article, "extracted_text", None) or article.snippet or article.title or "")


def source_lines(articles, *, depth_pref: str = "standard") -> str:
    """`Outlet — <budgeted body> [free|paywall]` per source — the `<sources>` block for the lenses."""
    budget = budget_for(depth_pref)
    out = []
    for a in articles:
        src = getattr(a, "source", None)
        outlet = src.name if src else "Unknown"
        tag = "paywall" if (src and src.is_paywalled) else "free"
        body = _body(a)[:budget].strip()
        out.append(f"{outlet} — {body} [{tag}]")
    return "\n".join(out)


def cluster_text(cluster, articles, *, depth_pref: str = "standard") -> str:
    """Numbered story + per-source budgeted bodies — replaces the old snippet[:400] concatenation."""
    budget = budget_for(depth_pref)
    lines = [f"STORY: {cluster.title}"]
    for i, a in enumerate(articles, 1):
        lines.append(f"\n{i}. {a.title}")
        body = _body(a)[:budget].strip()
        if body:
            lines.append(f"   {body}")
    return "\n".join(lines)
