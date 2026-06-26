# 990 Financial History Ingestion & Analysis — Design Spec
**Date:** 2026-06-24  
**Status:** Approved

## Problem

The CRM has real personnel data from IRS 990 XML filings (2022–2024) but zero real financial history. `financial_history` is empty; `investment_details` holds synthetic estimates computed as ratios of a single asset figure. There is no year-over-year view of assets, contributions, gains/losses, or grants.

## Goal

Extract real financial data from IRS 990/990PF XML filings for tax years 2020–2024 for all 41 foundations, store it in the database, and surface it through two new UI surfaces: a per-foundation Financial History tab and a cross-foundation Financial Comparison page.

---

## Architecture

### File structure

```
ingest_990_xml.py          existing — refactored to import from _990_common
ingest_990_financials.py   new — financial extraction script
_990_common.py             new — shared IRS fetch/batch/RemoteZip utilities
src/crm_app.py             modified — new tab + new sidebar page
```

### How IRS data is accessed

No files are stored locally. Both ingest scripts use `RemoteZip` HTTP range requests to stream individual XML filings from IRS bulk ZIP archives at `https://apps.irs.gov/pub/epostcard/990/xml/{year}/`. The common module handles index fetching, batch mapping (with special logic for 2023), and ZIP navigation. Each XML is fetched once and parsed for its data type.

---

## Component 1: `_990_common.py`

Extracted from `ingest_990_xml.py` — no logic changes, just moved:

- `fetch_index(year, target_eins)` — downloads IRS index CSV, returns matching rows
- `get_2023_batches()` — special batch enumeration for 2023 archive format
- `build_2023_batch_map(object_ids)` — maps object IDs → batch ZIP names for 2023
- `IRS_NS`, `BASE_URL`, `INDEX_URL`, `ZIP_URL` constants
- `_t(el, tag)`, `_yn(val)` XML helpers

`ingest_990_xml.py` is updated to `from _990_common import *` (or explicit names). Behavior unchanged.

---

## Component 2: `ingest_990_financials.py`

### Responsibilities

- For each target year (2020–2024), fetch the IRS index and find matching EINs
- Open each batch ZIP via RemoteZip, stream the XML, parse financial fields
- Migrate schema (ALTER TABLE adds new columns to `financial_history`)
- Clear synthetic `investment_details` rows and repopulate with real values
- Write a coverage report at the end: which foundations have data for which years

### Fields extracted — Form 990 (public charities)

| Field | XML element | Table |
|-------|-------------|-------|
| Total revenue | `TotalRevenueAmt` | financial_history |
| Contributions received | `CYContributionsGrantsAmt` | financial_history |
| Program service revenue | `CYProgramServiceRevenueAmt` | financial_history |
| Investment income | `CYInvestmentIncomeAmt` | financial_history |
| Capital gains/losses | `NetGainLossFromSalesOfAssetsAmt` | financial_history |
| Total expenses | `CYTotalExpensesAmt` | financial_history |
| Grants paid | `CYGrantsAndSimilarAmountsPaidAmt` | financial_history |
| Admin expenses | `CYMgmtAndGeneralExpensesAmt` | financial_history |
| Fundraising expenses | `CYFundraisingExpensesAmt` | financial_history |
| Total assets EOY | `TotalAssetsEOYAmt` | financial_history |
| Total liabilities EOY | `TotalLiabilitiesEOYAmt` | financial_history |
| Net assets EOY | `NetAssetsOrFundBalancesEOYAmt` | financial_history |
| Publicly traded securities | `InvestmentsPubliclyTradedSecAmt` | investment_details |
| Other securities | `InvestmentsOtherSecuritiesAmt` | investment_details |
| Program-related investments | `InvestmentsProgramRelatedAmt` | investment_details |

### Fields extracted — Form 990PF (private foundations)

| Field | XML element | Table |
|-------|-------------|-------|
| Contributions received | `TotContriPaidAmt` | financial_history |
| Dividend income | `DividendsAmt` | investment_details |
| Interest income | `InterestAmt` | investment_details |
| Investment income (sum) | `DividendsAmt + InterestAmt` | financial_history (investment_income) |
| Net capital gain/loss | `NetGainLossCapitalAmt` | financial_history |
| Total revenue | `TotalRevenueAndExpensesAmt` | financial_history |
| Qualifying distributions | `QualifyingDistributionsAmt` | financial_history (grants_paid) |
| Total assets EOY | `TotAssetsEOYAmt` | financial_history |
| Total liabilities EOY | `TotLiabilitiesEOYAmt` | financial_history |
| Net assets EOY | `TotNetAstOrFundBalancesEOYAmt` | financial_history |
| Investment securities EOY | `InvstmntSecEOYAmt` | investment_details |

### Schema migration

`ALTER TABLE financial_history ADD COLUMN` for each missing column (safe — existing rows get NULL, no data lost):

```sql
contributions_received    REAL
investment_income         REAL
capital_gains_losses      REAL
total_liabilities         REAL
net_assets_eoy            REAL
program_service_revenue   REAL
```

All existing `investment_details` rows are synthetic (confirmed: 41 rows, all filing_year=2022, all estimates). The table is truncated before repopulation:
```sql
DELETE FROM investment_details;
```

### Coverage report

After ingestion, the script prints and writes `logs/financial_coverage.txt`:

```
Foundation                         2020  2021  2022  2023  2024
Baton Rouge Area Foundation          ✓     ✓     ✓     ✓     ✓
Community Foundation of Acadiana     -     ✓     ✓     ✓     ✓
Kemper & Leila Williams Foundation   -     -     -     ✓     ✓
...
```

Missing years (`-`) are expected for foundations that filed late, changed EIN, or had no digital filing.

---

## Component 3: UI — Financial History tab

**Location:** Foundation Details page (`show_foundation_details`), new tab added to a `st.tabs` bar splitting the existing content into "Overview" | "Financial History".

### Financial History tab layout

1. **Data coverage row** — 5 chips (2020–2024), each showing ✓ (has data) or ✗ (no filing found). Rendered inline before any charts.

2. **YoY line charts** (Plotly, stacked vertically):
   - Total Assets vs. Investment Assets
   - Revenue breakdown: contributions, program service revenue, investment income
   - Capital gains/losses (can go negative — use a bar chart with color encoding positive/negative)
   - Grants paid + grant payout ratio (grants / total assets %)

3. **Investment breakdown** — pie chart for most recent year with real data: publicly traded securities vs. other securities vs. program-related.

4. **Year-over-year delta row** — below each chart, a metric row showing change from prior year (e.g., "Total Assets ▼ $12.3M from 2022").

5. **Missing year callout** — `st.info()` listing any missing years by name, not a silent gap.

Charts show gaps (not interpolation) for missing years.

---

## Component 4: UI — Financial Comparison page

**Location:** New entry in sidebar `selectbox`: "📊 Financial Comparison"

### Sidebar controls

- **Metric** — dropdown: Total Assets, Investment Assets, Capital Gains/Losses, Contributions Received, Investment Income, Grants Paid, Net Assets, Grant Payout Ratio
- **Year range** — slider: 2020–2024
- **Foundations** — multi-select, default all 41

### Main panel

**Snapshot view** (single year): horizontal bar chart ranking all selected foundations by metric. Foundations with no data for that year render as a gray "No data" bar — never silently omitted.

**Trend view** (multiple years): line chart, one line per foundation. Legend shows data completeness per foundation (e.g., "3/5 years").

**Data table** — sortable, all selected foundations × all selected years. Missing cells show "—". Exportable to CSV via `st.download_button`.

---

## Error handling

- XML parse errors: log warning, skip filing, continue (same as personnel ingest)
- Missing XML element: treat as `None` / `0.0` depending on field — never crash
- Foundation in DB but no IRS filing found for a year: recorded as missing in coverage report, no row written to `financial_history`
- Network timeout: retry once with 5s backoff, then skip and log

---

## Out of scope

- Parsing Schedule D investment detail (individual securities) — too granular for this pass
- Grants schedule (Schedule I recipients) — separate feature
- Updating `foundations.total_assets` / `investment_assets` with 2024 values — existing pipeline handles that
