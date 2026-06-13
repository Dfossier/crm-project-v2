import pytest
from src.new_functions import bio_snippet, bio_source_label


# ── bio_snippet ───────────────────────────────────────────────────────────────

def test_bio_snippet_returns_first_sentence():
    bio = "[general] He is a banker. He has worked in finance for 30 years."
    assert bio_snippet(bio) == "He is a banker."

def test_bio_snippet_truncates_at_120_chars():
    long_sentence = "A" * 130 + "."
    bio = f"[general] {long_sentence} Next sentence."
    result = bio_snippet(bio)
    assert len(result) <= 121  # 120 chars + "…"
    assert result.endswith("…")

def test_bio_snippet_no_period_truncates_at_120():
    bio = "[fnd:example.org] " + "word " * 40
    result = bio_snippet(bio)
    assert len(result) <= 121
    assert result.endswith("…")

def test_bio_snippet_none_returns_empty():
    assert bio_snippet(None) == ""

def test_bio_snippet_empty_returns_empty():
    assert bio_snippet("") == ""

def test_bio_snippet_strips_source_tag():
    bio = "[emp:homebank.com] Jason serves as COO. Other info."
    assert bio_snippet(bio) == "Jason serves as COO."

def test_bio_snippet_no_source_tag():
    bio = "He is a banker. He has worked in finance for 30 years."
    assert bio_snippet(bio) == "He is a banker."


# ── bio_source_label ──────────────────────────────────────────────────────────

def test_bio_source_label_general():
    assert bio_source_label("[general] some bio") == "general search"

def test_bio_source_label_fnd():
    assert bio_source_label("[fnd:cfacadiana.org] bio") == "cfacadiana.org"

def test_bio_source_label_emp():
    assert bio_source_label("[emp:homebank.com] bio") == "homebank.com"

def test_bio_source_label_linkedin():
    assert bio_source_label("[linkedin] bio") == "LinkedIn"

def test_bio_source_label_news():
    assert bio_source_label("[news] bio") == "news search"

def test_bio_source_label_no_tag():
    assert bio_source_label("bio with no tag") == ""

def test_bio_source_label_none():
    assert bio_source_label(None) == ""

def test_bio_source_label_unknown_tag():
    assert bio_source_label("[custom] bio") == "custom"
