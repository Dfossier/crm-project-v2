# CoI Page Redesign — Design Spec
**Date:** 2026-06-13  
**Status:** Approved

## Goal

Redesign the Centers of Influence page in `src/new_functions.py` to surface biographical information collected by the bio scraper pipeline. The current accordion shows name, title, and foundation but hides everything else behind expansion. The new design makes the bio scannable at a glance and shows full contact details when expanded.

---

## Layout

### Page structure (unchanged)
- Header: "Centers of Influence" title + subtitle
- Metrics bar: Total Contacts · With Bio (%) · With LinkedIn (%)
- Filter row: foundation dropdown · name search · "Missing bio only" checkbox
- Contact list: accordion of rows

### Collapsed row
Each row shows three lines:
1. **Name** (bold, highlighted) — Title · Foundation name
2. Bio snippet: first sentence of bio in muted italic, or "No bio available yet." in dimmed text if absent
3. **Badge** (right-aligned): `✓ Bio ▸` in green if bio present, `✗ No bio ▸` in red if absent

Rows with no bio are visually de-emphasised (reduced opacity) so contacts with bios stand out.

### Expanded row
When clicked, replaces the collapsed row with:

**Contact strip** (single horizontal row, smaller text):
- Employer name
- City, State
- 🔗 LinkedIn (link, shown only if present)
- Email (shown only if present)
- Phone (shown only if present)
- Fields with no data are omitted entirely (not shown as dashes)

Divider line beneath the strip.

**Full bio block** (full width):
- Left border accent (blue)
- Bio text at readable size with 1.7 line height
- Source caption in small muted text below-right (e.g. "Source: general search") — strips the `[tag]` prefix from the stored value

---

## Data

Query already fetches all needed columns from `centers_of_influence` joined to `foundations`:
`id, name, title, role, employer, employer_city, employer_state, linkedin_url, bio, notes, email, phone, foundation_name, foundation_city`

Bio cleaning (already in place): strip `[source:tag]` prefix via regex before display. Source label is extracted separately for the caption.

`is_good_bio()` check retained — if the stored bio fails quality check it is treated as absent.

---

## Files changed

| File | Change |
|------|--------|
| `src/new_functions.py` | Rewrite `show_centers_of_influence()` — collapsed row markup, expanded body layout |

No other files need to change. The data model, query, filters, and metrics are all kept as-is.

---

## Edge cases

- **No bio, no notes**: show "No bio available yet." in dimmed italic; red badge
- **Bio fails `is_good_bio()`**: treat same as absent
- **All optional contact fields absent**: contact strip is omitted entirely, only bio block shown
- **Long bio**: no truncation in expanded view — full text always shown
- **Snippet for collapsed row**: take text up to the first period + space, max 120 chars, append `…` if truncated. If no bio, show placeholder text.
