# CoI Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `show_centers_of_influence()` so each accordion row shows a bio snippet when collapsed and a contact strip + full bio when expanded.

**Architecture:** Extract two pure helper functions (`bio_snippet`, `bio_source_label`) from the rendering logic so they can be unit-tested independently. The Streamlit rendering in `show_centers_of_influence()` calls these helpers and builds the accordion using `st.expander`. No database or query changes needed.

**Tech Stack:** Python 3.12, Streamlit, pytest, existing `is_good_bio()` from `src/bio_scraper.py`

---

### Task 1: Add and test `bio_snippet` and `bio_source_label` helpers

**Files:**
- Modify: `src/new_functions.py` (add two functions above `show_centers_of_influence`)
- Create: `tests/test_new_functions.py`

- [ ] **Step 1: Create the tests file**

```python
# tests/test_new_functions.py
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
    assert len(result) <= 123  # 120 + "…" possible
    assert result.endswith("…")

def test_bio_snippet_no_period_truncates_at_120():
    bio = "[fnd:example.org] " + "word " * 40
    result = bio_snippet(bio)
    assert len(result) <= 123
    assert result.endswith("…")

def test_bio_snippet_none_returns_empty():
    assert bio_snippet(None) == ""

def test_bio_snippet_empty_returns_empty():
    assert bio_snippet("") == ""

def test_bio_snippet_strips_source_tag():
    bio = "[emp:homebank.com] Jason serves as COO. Other info."
    assert bio_snippet(bio) == "Jason serves as COO."


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
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
cd /home/dfoss/.openclaw/workspace/louisiana-foundations-crm
source venv/bin/activate
python -m pytest tests/test_new_functions.py -v 2>&1 | head -30
```

Expected: `ImportError` — `bio_snippet` and `bio_source_label` not yet defined.

- [ ] **Step 3: Add the two helpers to `src/new_functions.py`**

Insert immediately after the imports (line 5), before `show_followups`:

```python
_SOURCE_TAG = re.compile(r"^\[(.*?)\]\s*")

def bio_snippet(raw_bio: str | None, max_chars: int = 120) -> str:
    """Return first sentence of bio (≤ max_chars), source tag stripped."""
    if not raw_bio:
        return ""
    text = _SOURCE_TAG.sub("", raw_bio).strip()
    # Try to cut at first sentence boundary
    dot = text.find(". ")
    if 0 < dot <= max_chars:
        return text[: dot + 1]
    # No sentence boundary — truncate hard
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


def bio_source_label(raw_bio: str | None) -> str:
    """Extract a human-readable source label from the [tag] prefix."""
    if not raw_bio:
        return ""
    m = _SOURCE_TAG.match(raw_bio)
    if not m:
        return ""
    tag = m.group(1)
    if tag == "general":
        return "general search"
    if tag == "news":
        return "news search"
    if tag == "linkedin":
        return "LinkedIn"
    if tag.startswith("fnd:"):
        return tag[4:]
    if tag.startswith("emp:"):
        return tag[4:]
    return tag
```

- [ ] **Step 4: Run tests and confirm they pass**

```bash
python -m pytest tests/test_new_functions.py -v
```

Expected: 13 tests, all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/new_functions.py tests/test_new_functions.py
git commit -m "feat: add bio_snippet and bio_source_label helpers with tests"
```

---

### Task 2: Rewrite `show_centers_of_influence()`

**Files:**
- Modify: `src/new_functions.py:136-245` — replace the full function body

- [ ] **Step 1: Replace `show_centers_of_influence()` with the new implementation**

Replace the entire function (line 136 to end of file) with:

```python
def show_centers_of_influence(crm):
    """Display centers of influence — board members who can make introductions."""
    st.title("👥 Centers of Influence")
    st.markdown("Board members and key contacts across all foundations.")

    try:
        with crm.get_connection() as conn:
            df = pd.read_sql_query("""
                SELECT
                    coi.id, coi.name, coi.title, coi.role,
                    coi.employer, coi.employer_city, coi.employer_state,
                    coi.linkedin_url, coi.bio, coi.notes,
                    coi.email, coi.phone,
                    f.name AS foundation_name,
                    f.city AS foundation_city
                FROM centers_of_influence coi
                LEFT JOIN foundations f ON coi.foundation_id = f.id
                ORDER BY coi.name
            """, conn)
    except Exception as e:
        st.error(f"Error loading centers of influence: {e}")
        return

    if df.empty:
        st.info("No centers of influence recorded.")
        return

    # ── Metrics ───────────────────────────────────────────────────────────────
    total = len(df)

    def _has_bio(raw):
        if not raw:
            return False
        clean = _SOURCE_TAG.sub("", str(raw)).strip()
        return bool(clean)

    with_bio = int(df['bio'].apply(_has_bio).sum())
    with_linkedin = int(df['linkedin_url'].notna().sum())

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Contacts", total)
    col2.metric("With Bio", f"{with_bio} ({with_bio * 100 // total}%)")
    col3.metric("With LinkedIn", f"{with_linkedin} ({with_linkedin * 100 // total}%)")

    st.divider()

    # ── Filters ───────────────────────────────────────────────────────────────
    col_f, col_s, col_b = st.columns([2, 2, 1])
    fnd_options = ["All foundations"] + sorted(df['foundation_name'].dropna().unique().tolist())
    selected_fnd = col_f.selectbox("Filter by foundation", fnd_options)
    search_name  = col_s.text_input("Search by name", placeholder="Type a name...")
    only_no_bio  = col_b.checkbox("Missing bio only")

    filtered = df.copy()
    if selected_fnd != "All foundations":
        filtered = filtered[filtered['foundation_name'] == selected_fnd]
    if search_name:
        filtered = filtered[filtered['name'].str.contains(search_name, case=False, na=False)]
    if only_no_bio:
        filtered = filtered[~filtered['bio'].apply(_has_bio)]

    st.caption(f"Showing {len(filtered)} of {total} contacts")

    # ── Contact accordion ─────────────────────────────────────────────────────
    for row in filtered.itertuples(index=False):
        raw_bio  = row.bio or row.notes or ""
        clean_bio = _SOURCE_TAG.sub("", str(raw_bio)).strip() if raw_bio else ""
        has_bio  = bool(clean_bio) and is_good_bio(clean_bio, row.name)

        snippet  = bio_snippet(raw_bio) if has_bio else ""
        source   = bio_source_label(raw_bio) if has_bio else ""

        # Collapsed row label
        badge  = "✓ Bio" if has_bio else "✗ No bio"
        header = f"{badge} | {row.name}"
        if row.title:
            header += f" — {row.title}"
        if row.foundation_name:
            header += f" · {row.foundation_name}"

        with st.expander(header, expanded=False):
            # Bio snippet shown at top of expander header area via caption
            if snippet:
                st.caption(f"_{snippet}_")
            elif not has_bio:
                st.caption("_No bio available yet._")

            # Contact strip — only show fields that have data
            contact_parts = []
            if row.employer:
                loc = ", ".join(filter(None, [row.employer_city, row.employer_state]))
                contact_parts.append(("Employer", f"{row.employer}" + (f", {loc}" if loc else "")))
            if row.email:
                contact_parts.append(("Email", row.email))
            if row.phone:
                contact_parts.append(("Phone", row.phone))

            if contact_parts or row.linkedin_url:
                cols = st.columns(len(contact_parts) + (1 if row.linkedin_url else 0))
                for i, (label, value) in enumerate(contact_parts):
                    with cols[i]:
                        st.markdown(f"<small style='color:grey'>{label}</small><br>{value}", unsafe_allow_html=True)
                if row.linkedin_url:
                    with cols[len(contact_parts)]:
                        st.markdown(f"<small style='color:grey'>LinkedIn</small><br>[🔗 Profile]({row.linkedin_url})", unsafe_allow_html=True)
                st.divider()

            # Full bio
            if has_bio:
                st.markdown(
                    f"<div style='border-left:3px solid #89b4fa;padding:8px 12px;"
                    f"background:#181825;border-radius:0 4px 4px 0;line-height:1.7'>"
                    f"{clean_bio}</div>",
                    unsafe_allow_html=True,
                )
                if source:
                    st.caption(f"Source: {source}")
```

- [ ] **Step 2: Verify the app loads without errors**

```bash
cd /home/dfoss/.openclaw/workspace/louisiana-foundations-crm
source venv/bin/activate
python -c "from src.new_functions import show_centers_of_influence; print('import ok')"
```

Expected: `import ok`

- [ ] **Step 3: Run existing tests to confirm helpers still pass**

```bash
python -m pytest tests/test_new_functions.py -v
```

Expected: 13 tests, all PASS.

- [ ] **Step 4: Restart the CRM and manually verify the CoI page**

```bash
bash /home/dfoss/.openclaw/workspace/louisiana-foundations-crm/manage_crm.sh restart
```

Open http://localhost:8888 → navigate to **Centers of Influence**.

> **Note:** Streamlit's `st.expander` label is a single-line string — the bio snippet cannot be embedded in the collapsed header. Instead it appears as the first item inside the expanded body (italic caption), which is the first thing seen when clicking. This is a minor UX difference from the mockup; the collapsed row shows name, title, foundation, and ✓/✗ badge only.

Check:
- [ ] Jason Freyou row: collapsed shows name + title + foundation + green ✓ badge
- [ ] Jerry Shea Jr row: same — green ✓ badge
- [ ] A contact without a bio: "No bio available yet." in muted text, red ✗ badge
- [ ] Expand Jason Freyou: contact strip shows LinkedIn, bio block has left blue border, source caption visible
- [ ] Expand a no-bio contact: no contact strip shown if all fields empty, no bio block
- [ ] Filter "Missing bio only": only ✗ rows shown
- [ ] Name search works

- [ ] **Step 5: Commit**

```bash
git add src/new_functions.py
git commit -m "feat: redesign CoI page with bio snippet in collapsed row and contact strip expanded view"
```

---

### Task 3: Add `.superpowers/` to `.gitignore`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add entry**

Add `.superpowers/` to `.gitignore` (the brainstorm mockup files should not be committed).

```
.superpowers/
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore .superpowers/ brainstorm directory"
```
