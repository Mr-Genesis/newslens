"""Wave D1: the retrieval seam — full bodies, budgeted by depth, snippet fallback. TDD (pure)."""
from app.services import retrieval as R


class _Src:
    def __init__(self, name, paywalled=False):
        self.name = name
        self.is_paywalled = paywalled


class _Art:
    def __init__(self, title, snippet=None, extracted_text=None, src="Reuters", paywalled=False):
        self.title = title
        self.snippet = snippet
        self.extracted_text = extracted_text
        self.source = _Src(src, paywalled)


class _Cl:
    def __init__(self, title="C", summary="S"):
        self.title = title
        self.summary = summary


def test_source_lines_uses_full_body_budgeted_by_depth():
    arts = [_Art("T", snippet="short", extracted_text="x" * 5000)]
    brief = R.source_lines(arts, depth_pref="brief")
    standard = R.source_lines(arts, depth_pref="standard")
    expert = R.source_lines(arts, depth_pref="expert")
    assert len(brief) < len(standard) < len(expert)  # depth = budget
    assert "Reuters" in standard and "free" in standard


def test_source_lines_falls_back_to_snippet_when_no_body():
    out = R.source_lines([_Art("T", snippet="only the snippet", extracted_text=None)])
    assert "only the snippet" in out


def test_source_lines_marks_paywall():
    out = R.source_lines([_Art("T", extracted_text="body", src="WSJ", paywalled=True)])
    assert "paywall" in out and "WSJ" in out


def test_cluster_text_includes_full_body():
    txt = R.cluster_text(_Cl(title="Headline"), [_Art("Headline", extracted_text="full body here")])
    assert "Headline" in txt and "full body here" in txt


def test_unknown_depth_defaults_to_standard():
    arts = [_Art("T", extracted_text="y" * 5000)]
    assert len(R.source_lines(arts, depth_pref="bogus")) == len(R.source_lines(arts, depth_pref="standard"))
