"""
Investment Portfolio page — shows per-foundation investment allocation data.

Two views:
  1. Holdings view  — ticker-level data from investment_holdings table (manual entry / CSV import)
  2. Aggregate view — asset-class totals from ProPublica API (fallback when no holdings entered)
"""

import io
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import sqlite3
from pathlib import Path

PROPUBLICA_BASE = "https://projects.propublica.org/nonprofits/api/v2"

ASSET_CLASSES = [
    "Equities",
    "Fixed Income",
    "Government Bonds",
    "Municipal Bonds",
    "Corporate Bonds",
    "Real Estate",
    "Private Equity",
    "Hedge Funds",
    "Cash & Equivalents",
    "Commodities",
    "Other Alternatives",
    "Other",
]

# Ticker → specific investment style/sub-class
_TICKER_STYLE: dict[str, str] = {
    "CSRSX": "Real Estate",
    "DFSVX": "Small Cap Value",
    "DFCEX": "Emerging Markets",
    "DODIX": "Core Bond",
    "FNSOX": "Short-Term Bond",
    "FXAIX": "Large Cap Blend",
    "FSMDX": "Mid Cap Blend",
    "FSSNX": "Small Cap Blend",
    "FSPSX": "Intl Developed",
    "FSIIX": "Intl Developed",
    "GSIMX": "Intl Developed",
    "JANEX": "Mid Cap Growth",
    "MHYRX": "High Yield Bond",
    "SWLGX": "Large Cap Growth",
    "TRMIX": "Mid Cap Value",
    "VWENX": "Balanced",
    "VIGAX": "Large Cap Growth",
    "VENAX": "Sector - Energy",
    "VEXPX": "SMID Cap Growth",
    # Nuveen Lifecycle target-date series
    "TLIRX": "Target Date",
    "TLTRX": "Target Date",
    "TLTYX": "Target Date",
    "TLTPX": "Target Date",
    "TLTQX": "Target Date",
    "TLPRX": "Target Date",
    "TLLRX": "Target Date",
    "TLMRX": "Target Date",
    "TLGRX": "Target Date",
}

import re as _re

def _get_sub_class(ticker, description: str) -> str:
    if ticker and isinstance(ticker, str) and ticker.upper() in _TICKER_STYLE:
        style = _TICKER_STYLE[ticker.upper()]
        if style == "Target Date":
            m = _re.search(r'\b(20[2-9]\d)\b', description or '')
            return f"Target Date {m.group(1)}" if m else "Target Date"
        return style
    d = (description or "").lower()
    if any(k in d for k in ["stable asset", "stable value"]):
        return "Stable Value"
    if any(k in d for k in ["lifecyc", "lifecycle", "target date", "target-date"]):
        m = _re.search(r'\b(20[2-9]\d)\b', description or '')
        return f"Target Date {m.group(1)}" if m else "Target Date"
    if any(k in d for k in ["wellington", "balanced"]):
        return "Balanced"
    if "energy" in d and any(k in d for k in ["sector", "index"]):
        return "Sector - Energy"
    if any(k in d for k in ["realty", "real estate", "reit"]):
        return "Real Estate"
    if any(k in d for k in ["emerging market", "em equity"]):
        return "Emerging Markets"
    if any(k in d for k in ["international", "global", "intl", "foreign"]):
        return "Intl Developed"
    if "high yield" in d:
        return "High Yield Bond"
    if any(k in d for k in ["short-term bond", "short term bond"]):
        return "Short-Term Bond"
    if any(k in d for k in ["bond", "income fund", "fixed income"]):
        return "Core Bond"
    if any(k in d for k in ["small cap", "small-cap", "small cap value", "small cap growth"]):
        if "value" in d:
            return "Small Cap Value"
        if "growth" in d:
            return "Small Cap Growth"
        return "Small Cap Blend"
    if any(k in d for k in ["mid cap", "mid-cap"]):
        if "value" in d:
            return "Mid Cap Value"
        if "growth" in d:
            return "Mid Cap Growth"
        return "Mid Cap Blend"
    if any(k in d for k in ["500 index", "large cap", "large-cap", "s&p 500", "large company"]):
        if "growth" in d:
            return "Large Cap Growth"
        if "value" in d:
            return "Large Cap Value"
        return "Large Cap Blend"
    if "growth" in d:
        return "Large Cap Growth"
    if "value" in d:
        return "Large Cap Value"
    if any(k in d for k in ["money market", "cash"]):
        return "Cash & Equivalents"
    return "—"

# ── ProPublica API (aggregate) ────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_filing(ein: str) -> dict:
    """Return org + most recent filing + all filings with data for an EIN."""
    try:
        r = requests.get(
            f"{PROPUBLICA_BASE}/organizations/{ein}.json",
            timeout=30,
            headers={"User-Agent": "Foundation-Research-Tool/1.0"},
        )
        r.raise_for_status()
        data = r.json()
        org = data.get("organization", {})
        filings = data.get("filings_with_data", [])
        filing = next((f for f in filings if f.get("totassetsend")), {})
        return {"org": org, "filing": filing, "all_filings": filings}
    except Exception:
        return {"org": {}, "filing": {}, "all_filings": []}


def _val(filing, key):
    v = filing.get(key)
    return float(v) if v and float(v) > 0 else 0.0


def extract_allocations(filing: dict, total_assets: float):
    corp_stock  = _val(filing, "invstcorpstk")
    corp_bond   = _val(filing, "invstcorpbnd")
    govt_oblig  = _val(filing, "invstgovtoblig")
    other_invst = _val(filing, "othrinvstend")
    cash        = _val(filing, "othrcashamt")
    tot_sec     = _val(filing, "totinvstsec")
    invst_income = _val(filing, "netinvstinc") or _val(filing, "invstmntinc")
    gains       = _val(filing, "gnlsecur")

    has_detail = (corp_stock + corp_bond + govt_oblig) > 0
    rows = []

    if has_detail:
        known    = corp_stock + corp_bond + govt_oblig + other_invst + cash
        residual = max(0.0, tot_sec - known) if tot_sec > known else 0.0
        non_sec  = max(0.0, total_assets - max(tot_sec, known) - cash)
        buckets = [
            ("Equities / Corporate Stock",       corp_stock),
            ("Corporate Bonds",                   corp_bond),
            ("Government Obligations",            govt_oblig),
            ("Other Investments (Alternatives)",  other_invst + residual),
            ("Cash & Short-Term",                 cash),
            ("Other Assets",                      non_sec),
        ]
        denom = sum(v for _, v in buckets) or total_assets or 1
        rows = [
            {"Asset Class": lbl, "Amount ($)": amt, "Allocation (%)": amt / denom * 100}
            for lbl, amt in buckets if amt > 0
        ]
    else:
        inv_assets = _val(filing, "totassetsend") or total_assets
        buckets = [
            ("Investment Portfolio (estimated)", inv_assets * 0.87),
            ("Other Assets",                     inv_assets * 0.13),
        ]
        denom = inv_assets or 1
        rows = [
            {"Asset Class": lbl, "Amount ($)": amt, "Allocation (%)": amt / denom * 100}
            for lbl, amt in buckets if amt > 0
        ]

    return rows, has_detail, invst_income, gains


# ── Holdings DB helpers ───────────────────────────────────────────────────────

def load_holdings(crm, foundation_id: int) -> pd.DataFrame:
    with crm.get_connection() as conn:
        return pd.read_sql_query(
            """
            SELECT id, ticker, description, shares, cost_basis, fair_market_value,
                   asset_class, as_of_date, source
            FROM investment_holdings
            WHERE foundation_id = ?
            ORDER BY fair_market_value DESC
            """,
            conn,
            params=[foundation_id],
        )


def delete_holding(crm, holding_id: int):
    with crm.get_connection() as conn:
        conn.execute("DELETE FROM investment_holdings WHERE id = ?", (holding_id,))
        conn.commit()


def upsert_holding(crm, foundation_id: int, row: dict, holding_id: int | None = None):
    cols = ["foundation_id", "ticker", "description", "shares", "cost_basis",
            "fair_market_value", "asset_class", "as_of_date", "source"]
    vals = [
        foundation_id,
        (row.get("ticker") or "").strip().upper() or None,
        row["description"].strip(),
        row.get("shares") or None,
        row.get("cost_basis") or None,
        float(row["fair_market_value"]),
        row["asset_class"],
        row.get("as_of_date") or None,
        row.get("source", "manual"),
    ]
    with crm.get_connection() as conn:
        if holding_id:
            set_clause = ", ".join(f"{c}=?" for c in cols)
            conn.execute(
                f"UPDATE investment_holdings SET {set_clause}, updated_at=datetime('now') WHERE id=?",
                vals + [holding_id],
            )
        else:
            placeholders = ", ".join("?" for _ in cols)
            conn.execute(
                f"INSERT INTO investment_holdings ({', '.join(cols)}) VALUES ({placeholders})",
                vals,
            )
        conn.commit()


def bulk_import_holdings(crm, foundation_id: int, df: pd.DataFrame, as_of_date: str):
    """Insert rows from a validated DataFrame; clears existing holdings first."""
    with crm.get_connection() as conn:
        conn.execute(
            "DELETE FROM investment_holdings WHERE foundation_id = ? AND source = 'csv'",
            (foundation_id,),
        )
        for _, row in df.iterrows():
            ticker = str(row.get("Ticker", "") or "").strip().upper() or None
            desc   = str(row.get("Description", "") or row.get("Name", "")).strip()
            if not desc:
                continue
            fmv = float(row.get("Fair Market Value", 0) or row.get("FMV", 0) or row.get("Value", 0) or 0)
            if fmv <= 0:
                continue
            shares = row.get("Shares") or row.get("Units") or None
            cost   = row.get("Cost Basis") or row.get("Cost") or None
            ac     = str(row.get("Asset Class", "Equities") or "Equities").strip()
            if ac not in ASSET_CLASSES:
                ac = "Other"
            conn.execute(
                """INSERT INTO investment_holdings
                   (foundation_id, ticker, description, shares, cost_basis,
                    fair_market_value, asset_class, as_of_date, source)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (foundation_id, ticker, desc, shares, cost, fmv, ac, as_of_date, "csv"),
            )
        conn.commit()


# ── Holdings display ──────────────────────────────────────────────────────────

def show_holdings_view(crm, foundation_id: int, frow, filing: dict, total_assets: float, form5500_url: str | None = None):
    holdings = load_holdings(crm, foundation_id)

    total_holdings_val = holdings["fair_market_value"].sum() if not holdings.empty else 0

    # ── Top KPIs ──
    inv_income = _val(filing, "netinvstinc") or _val(filing, "invstmntinc")
    gains      = _val(filing, "gnlsecur")
    fair_mkt   = _val(filing, "fairmrktvaleoy") or _val(filing, "fairmrktvalamt")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        reported = fair_mkt or total_assets
        st.metric("Reported Assets", f"${reported/1e6:.1f}M")
    with col2:
        st.metric("Holdings Entered", f"${total_holdings_val/1e6:.1f}M" if total_holdings_val else "None yet")
    with col3:
        if inv_income:
            y = inv_income / (fair_mkt or total_assets) * 100 if (fair_mkt or total_assets) else 0
            st.metric("Investment Yield", f"{y:.2f}%")
        else:
            st.metric("Investment Yield", "N/A")
    with col4:
        st.metric("Realized Gains", f"${gains/1e6:.1f}M" if gains else "N/A")

    st.divider()

    # ── Source note ──
    if not holdings.empty and (holdings["source"] == "form5500").any():
        as_of = holdings.loc[holdings["source"] == "form5500", "as_of_date"].iloc[0]
        st.caption(f"Holdings sourced from Form 5500 Schedule H (as of {as_of}). Use the import panel below to refresh.")

    return holdings


def _render_holdings_charts(holdings: pd.DataFrame):
    holdings = holdings.copy()
    total = holdings["fair_market_value"].sum()
    holdings["Pct (%)"] = holdings["fair_market_value"] / total * 100

    # ── Plan type label ──
    if (holdings["source"] == "form5500").any():
        st.markdown(f"### 401(k) Plan &nbsp;&nbsp;&nbsp; <span style='font-size:1rem;font-weight:400;color:gray;'>Total FMV: ${total:,.0f}</span>", unsafe_allow_html=True)

    # ── Full-width holdings table ──
    st.subheader(f"Holdings  ({len(holdings)} positions)")
    holdings["Style"] = holdings.apply(
        lambda r: _get_sub_class(r["ticker"], r["description"]), axis=1
    )
    display = holdings[["ticker", "description", "asset_class", "Style",
                         "fair_market_value", "Pct (%)", "as_of_date"]].copy()
    display.columns = ["Ticker", "Description", "Asset Class", "Style",
                       "Fair Market Value ($)", "% of Portfolio", "As-of Date"]
    display["Fair Market Value ($)"] = display["Fair Market Value ($)"].apply(lambda x: f"${x:,.0f}")
    display["% of Portfolio"]        = display["% of Portfolio"].apply(lambda x: f"{x:.2f}%")
    st.dataframe(display, use_container_width=True, hide_index=True)

    # ── Donut below table ──
    st.subheader("By Asset Class")

    # Remap for donut: use Style, collapse Target Date variants, fix "Other"
    donut = holdings.copy()
    def _donut_label(row):
        style = row.get("Style", "") or ""
        if style.startswith("Target Date"):
            return "Target Date"
        ac = row["asset_class"]
        if ac == "Other":
            return style if (style and style != "—") else "Target Date"
        return style if (style and style != "—") else ac
    donut["donut_class"] = donut.apply(_donut_label, axis=1)

    class_df = (
        donut.groupby("donut_class", as_index=False)["fair_market_value"]
        .sum()
        .sort_values("fair_market_value", ascending=False)
    )

    # Themed color map — same family shares similar hues, different shades per style
    _DONUT_COLORS = {
        # Equities — blue/indigo family
        "Large Cap Blend":      "#1d4ed8",
        "Large Cap Growth":     "#4f46e5",
        "Large Cap Value":      "#818cf8",
        "Mid Cap Blend":        "#2563eb",
        "Mid Cap Growth":       "#6366f1",
        "Mid Cap Value":        "#93c5fd",
        "Small Cap Blend":      "#0284c7",
        "Small Cap Growth":     "#38bdf8",
        "Small Cap Value":      "#7dd3fc",
        "SMID Cap Growth":      "#06b6d4",
        # International — teal family
        "Intl Developed":       "#0d9488",
        "Emerging Markets":     "#2dd4bf",
        # Fixed Income — green family
        "Core Bond":            "#15803d",
        "Short-Term Bond":      "#4ade80",
        "Intermediate Bond":    "#16a34a",
        "High Yield Bond":      "#f59e0b",
        # Real Assets / Alternatives
        "Real Estate":          "#d97706",
        "Sector - Energy":      "#f97316",
        "Balanced":             "#fb923c",
        # Target Date — purple
        "Target Date":          "#7c3aed",
        # Stable / Cash
        "Stable Value":         "#94a3b8",
        "Cash & Equivalents":   "#cbd5e1",
        # Catch-all
        "Other":                "#6b7280",
    }

    fig = px.pie(
        class_df,
        names="donut_class",
        values="fair_market_value",
        hole=0.4,
        color="donut_class",
        color_discrete_map=_DONUT_COLORS,
    )
    # Shift donut to left half of figure; legend occupies the right half naturally
    fig.update_traces(
        textposition="auto", textinfo="percent+label",
        domain=dict(x=[0, 0.55], y=[0, 1]),
    )
    fig.update_layout(
        showlegend=True,
        margin=dict(t=40, b=40, l=20, r=20),
        height=480,
        legend=dict(
            orientation="v",
            x=0.58, y=0.5,
            xanchor="left", yanchor="middle",
            font=dict(size=12),
        ),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Top-10 bar chart
    top10 = holdings.nlargest(10, "fair_market_value").copy()
    top10["label"] = top10.apply(
        lambda r: r["ticker"] if (r["ticker"] and isinstance(r["ticker"], str)) else r["description"][:30], axis=1
    )
    # Remap asset_class "Other" → "Target Date" for bar color grouping
    top10["bar_class"] = top10["asset_class"].replace("Other", "Target Date")
    top10["pct_text"] = top10["fair_market_value"].apply(
        lambda v: f"{v / total * 100:.1f}%"
    )
    fig2 = px.bar(
        top10,
        x="fair_market_value",
        y="label",
        orientation="h",
        color="bar_class",
        text="pct_text",
        labels={"fair_market_value": "Fair Market Value ($)", "label": "", "bar_class": "Asset Class"},
        color_discrete_map=_DONUT_COLORS,
    )
    fig2.update_traces(textposition="inside", insidetextanchor="middle", textfont_size=12)
    fig2.update_xaxes(tickprefix="$", tickformat=".2s")
    fig2.update_layout(
        title="Top 10 Holdings by Value",
        showlegend=True,
        height=380,
        margin=dict(t=40, b=20, l=10, r=20),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig2, use_container_width=True)


def _import_from_form5500(crm, foundation_id: int, pdf_url: str, start_page: int = None) -> int:
    """Parse Schedule of Assets from a Form 5500 PDF and bulk-insert holdings. Returns count inserted."""
    import io, re
    try:
        import pypdf
    except ImportError:
        return 0

    def _classify(desc):
        d = desc.lower()
        if any(k in d for k in ['stable asset', 'stable value', 'money market', 'short-term bond']):
            return 'Cash & Equivalents'
        if any(k in d for k in ['high yield', 'bond', 'income fund', 'fixed income']):
            return 'Fixed Income'
        if any(k in d for k in ['realty', 'real estate']):
            return 'Real Estate'
        if any(k in d for k in ['lifecyc', 'lifecycle', 'target date']):
            return 'Target Date'
        if 'wellington' in d:
            return 'Balanced'
        return 'Equities'

    import os
    from urllib.parse import unquote
    path = pdf_url.strip().strip('"').strip("'")
    if path.startswith("file:///"):
        path = unquote(path[8:]).replace("/", os.sep)
    elif path.startswith("file://"):
        path = unquote(path[7:])
    if os.path.exists(path):
        with open(path, "rb") as f:
            reader = pypdf.PdfReader(io.BytesIO(f.read()))
    else:
        raw_url = path.split('#')[0]
        resp = requests.get(raw_url, timeout=60)
        if resp.status_code != 200:
            return 0
        reader = pypdf.PdfReader(io.BytesIO(resp.content))

    # Find the Schedule of Assets page
    asset_text = None
    if start_page is not None:
        # User-specified page (1-indexed)
        pages_to_search = list(range(start_page - 1, min(start_page + 9, len(reader.pages))))
    else:
        pages_to_search = range(len(reader.pages))

    for i in pages_to_search:
        t = reader.pages[i].extract_text() or ''
        if start_page is not None:
            # Accept any page when user specifies start; stop at first page with dollar values
            if re.search(r'\d[\d,]+', t):
                asset_text = (asset_text or '') + '\n' + t
        else:
            if 'Schedule of Assets' in t and 'End of Year' in t:
                asset_text = t
                break

    if not asset_text:
        return 0

    holdings = []
    as_of_match = re.search(r'December 31[,\s]+(\d{4})', asset_text)
    as_of = f"{as_of_match.group(1)}-12-31" if as_of_match else '2024-12-31'

    for line in asset_text.splitlines():
        line = line.strip()
        if not line.startswith('*'):
            continue
        line = line[1:].strip()
        m = re.search(r'([\d,]+)[\$\s]*$', line)
        if not m:
            continue
        try:
            val = float(m.group(1).replace(',', ''))
        except ValueError:
            continue
        if val < 100:
            continue
        desc = line[:m.start()].strip().rstrip('$').strip()
        if not desc or 'notes receivable' in desc.lower():
            continue
        words = desc.split()
        if len(words) > 2 and words[0] == words[2]:
            desc = ' '.join(words[2:])
        holdings.append({'description': desc, 'fmv': val, 'asset_class': _classify(desc)})

    if not holdings:
        return 0

    with crm.get_connection() as conn:
        conn.execute("DELETE FROM investment_holdings WHERE foundation_id=? AND source='form5500'", (foundation_id,))
        for h in holdings:
            conn.execute(
                """INSERT INTO investment_holdings
                   (foundation_id, description, fair_market_value, asset_class, as_of_date, source)
                   VALUES (?,?,?,?,?,?)""",
                (foundation_id, h['description'], h['fmv'], h['asset_class'], as_of, 'form5500'),
            )
        conn.commit()
    return len(holdings)


def _render_import_panel(crm, foundation_id: int, existing: pd.DataFrame, form5500_url=None):
    st.divider()
    with st.expander("Manage Holdings — Import CSV or Add Manually", expanded=existing.empty):
        form5500_url = form5500_url if isinstance(form5500_url, str) and form5500_url.strip() else None
        tabs = ["Form 5500", "CSV Import", "Add Single Holding", "Delete Holdings"] if form5500_url else ["CSV Import", "Add Single Holding", "Delete Holdings"]
        tab_list = st.tabs(tabs)
        tab_offset = 0

        if form5500_url:
            tab_5500 = tab_list[0]
            tab_offset = 1
            with tab_5500:
                st.markdown(
                    f"This foundation has a Form 5500 on file. Click below to re-import the "
                    f"Schedule of Assets (Held at End of Year) directly from the filed PDF."
                )
                st.caption(f"Source: {form5500_url.split('#')[0][-60:]}")
                if st.button("Re-import from Form 5500 Schedule H", key="reimport_5500"):
                    with st.spinner("Downloading and parsing PDF…"):
                        count = _import_from_form5500(crm, foundation_id, form5500_url)
                    if count:
                        st.success(f"Imported {count} holdings from Form 5500 Schedule H.")
                        st.rerun()
                    else:
                        st.warning("Could not find Schedule of Assets in this PDF.")

        tab_csv    = tab_list[tab_offset]
        tab_manual = tab_list[tab_offset + 1]
        tab_delete = tab_list[tab_offset + 2]

        # ── CSV Import ──
        with tab_csv:
            st.markdown(
                "Upload a CSV with columns: **Ticker** (optional), **Description**, "
                "**Fair Market Value**, **Asset Class**, **Shares** (optional), **Cost Basis** (optional)."
            )
            st.download_button(
                "Download template CSV",
                data=_csv_template(),
                file_name="holdings_template.csv",
                mime="text/csv",
            )
            as_of = st.date_input("As-of date", key="csv_asof")
            uploaded = st.file_uploader("Upload CSV", type=["csv"], key="csv_upload")

            if uploaded:
                try:
                    df_raw = pd.read_csv(uploaded)
                    st.write("Preview (first 5 rows):")
                    st.dataframe(df_raw.head(), use_container_width=True)
                    if st.button("Import all rows", key="do_csv_import"):
                        bulk_import_holdings(crm, foundation_id, df_raw, str(as_of))
                        st.success(f"Imported {len(df_raw)} holdings.")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error reading CSV: {e}")

        # ── Manual entry ──
        with tab_manual:
            with st.form("add_holding_form", clear_on_submit=True):
                c1, c2 = st.columns([1, 3])
                with c1:
                    ticker = st.text_input("Ticker (optional)", placeholder="AAPL")
                with c2:
                    description = st.text_input("Description *", placeholder="Apple Inc.")

                c3, c4, c5 = st.columns(3)
                with c3:
                    fmv = st.number_input("Fair Market Value ($) *", min_value=0.0, step=1000.0)
                with c4:
                    shares = st.number_input("Shares (optional)", min_value=0.0, step=1.0)
                with c5:
                    cost = st.number_input("Cost Basis ($, optional)", min_value=0.0, step=1000.0)

                c6, c7 = st.columns([2, 1])
                with c6:
                    asset_class = st.selectbox("Asset Class", ASSET_CLASSES)
                with c7:
                    as_of_manual = st.date_input("As-of date", key="manual_asof")

                submitted = st.form_submit_button("Add Holding")
                if submitted:
                    if not description.strip():
                        st.error("Description is required.")
                    elif fmv <= 0:
                        st.error("Fair market value must be > 0.")
                    else:
                        upsert_holding(crm, foundation_id, {
                            "ticker": ticker,
                            "description": description,
                            "shares": shares or None,
                            "cost_basis": cost or None,
                            "fair_market_value": fmv,
                            "asset_class": asset_class,
                            "as_of_date": str(as_of_manual),
                            "source": "manual",
                        })
                        st.success(f"Added: {description}")
                        st.rerun()

        # ── Delete ──
        with tab_delete:
            if existing.empty:
                st.info("No holdings to delete.")
            else:
                opts = {f"{r['description']} ({r['ticker'] or '—'})  ${r['fair_market_value']:,.0f}": r["id"]
                        for _, r in existing.iterrows()}
                sel = st.multiselect("Select holdings to delete", list(opts.keys()))
                if sel and st.button("Delete selected", type="primary"):
                    for label in sel:
                        delete_holding(crm, opts[label])
                    st.success(f"Deleted {len(sel)} holdings.")
                    st.rerun()

                if not existing.empty and st.button("Delete ALL holdings for this foundation", type="primary"):
                    with crm.get_connection() as conn:
                        conn.execute(
                            "DELETE FROM investment_holdings WHERE foundation_id = ?", (foundation_id,)
                        )
                        conn.commit()
                    st.success("All holdings deleted.")
                    st.rerun()


def _csv_template() -> str:
    return (
        "Ticker,Description,Fair Market Value,Asset Class,Shares,Cost Basis\n"
        "AAPL,Apple Inc.,1250000,Equities,5000,980000\n"
        "BRK.B,Berkshire Hathaway,850000,Equities,2000,700000\n"
        "AGG,iShares Core US Aggregate Bond ETF,600000,Fixed Income,6000,590000\n"
        "T,US Treasury Bond 4.5% 2030,500000,Government Bonds,,490000\n"
        ",Money Market Fund,200000,Cash & Equivalents,,200000\n"
    )


# ── Aggregate view (ProPublica fallback) ─────────────────────────────────────

def show_aggregate_view(filing: dict, total_assets: float, frow, year):
    rows, has_detail, _, _ = extract_allocations(filing, total_assets)

    if not rows:
        st.info("No investment breakdown data available from IRS filings for this foundation.")
        return

    if not has_detail:
        st.info(
            "This foundation files Form 990 (not 990-PF), so only an estimated asset-class "
            "split is available from IRS filings. Enter holdings manually to see ticker-level data."
        )

    alloc_df = pd.DataFrame(rows)
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("Allocation Breakdown (IRS 990)")
        display = alloc_df.copy()
        display["Amount ($)"]    = display["Amount ($)"].apply(lambda x: f"${x:,.0f}")
        display["Allocation (%)"] = display["Allocation (%)"].apply(lambda x: f"{x:.1f}%")
        st.dataframe(display, use_container_width=True, hide_index=True)
        total_shown = alloc_df["Amount ($)"].sum()
        st.caption(f"Total shown: ${total_shown:,.0f}  ·  Investment assets on file: ${total_assets:,.0f}")

    with col_right:
        st.subheader("Portfolio Allocation")
        fig = px.pie(
            alloc_df,
            names="Asset Class",
            values="Amount ($)",
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Safe,
        )
        fig.update_traces(textposition="outside", textinfo="percent+label")
        fig.update_layout(
            showlegend=True,
            legend=dict(orientation="v", x=1.05),
            margin=dict(t=20, b=20, l=20, r=20),
            height=420,
        )
        st.plotly_chart(fig, use_container_width=True)

    if has_detail:
        st.divider()
        st.subheader("990-PF Investment Detail")
        tot_sec    = _val(filing, "totinvstsec")
        min_dist   = _val(filing, "cmpmininvstret")
        excise_tax = _val(filing, "invstexcisetx")
        net_inv    = _val(filing, "netinvstinc")
        fmv_unused = _val(filing, "tfairmrktunuse")
        fair_mkt   = _val(filing, "fairmrktvaleoy") or _val(filing, "fairmrktvalamt")

        cols = st.columns(3)
        metrics = [
            ("Total Securities",              f"${tot_sec/1e6:.1f}M" if tot_sec else "N/A"),
            ("Net Investment Income",          f"${net_inv/1e6:.2f}M" if net_inv else "N/A"),
            ("Min Distribution Req.",          f"${min_dist/1e6:.2f}M" if min_dist else "N/A"),
            ("Excise Tax (on inv. income)",    f"${excise_tax:,.0f}" if excise_tax else "N/A"),
            ("FMV (per 990-PF)",               f"${fmv_unused/1e6:.1f}M" if fmv_unused else "N/A"),
        ]
        for i, (label, value) in enumerate(metrics):
            with cols[i % 3]:
                st.metric(label, value)
        if net_inv and fair_mkt and fair_mkt > 0:
            roi = net_inv / fair_mkt * 100
            st.markdown(f"**Net Investment Return:** {roi:.2f}%")


# ── 401k portfolio returns chart (yfinance) ──────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_benchmark_returns(equity_wt: float = 0.70, bond_wt: float = 0.30) -> pd.Series:
    """70/30 benchmark: SPY (equities) + AGG (bonds), annually rebalanced."""
    try:
        import yfinance as yf
    except ImportError:
        return pd.Series(dtype=float)
    try:
        raw = yf.download(["SPY", "AGG"], period="10y", interval="1mo",
                          progress=False, auto_adjust=True, actions=False)
        prices = raw["Close"] if "Close" in raw.columns else raw
        annual = prices.resample("YE").last()
        ret    = annual.pct_change().dropna(how="all")
        benchmark = pd.Series(0.0, index=ret.index)
        if "SPY" in ret.columns:
            benchmark = benchmark.add(ret["SPY"] * equity_wt, fill_value=0)
        if "AGG" in ret.columns:
            benchmark = benchmark.add(ret["AGG"] * bond_wt, fill_value=0)
        benchmark.index = benchmark.index.year
        return (benchmark * 100).round(2)
    except Exception:
        return pd.Series(dtype=float)


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_return_data(ticker_weight_pairs: tuple) -> dict:
    """
    Returns dict with:
      portfolio_annual  – pd.Series  (year → weighted annual return %)
      holding_annualized – dict      (ticker → 10yr CAGR %)
      cumulative         – pd.Series (year → $10k grown)
    """
    try:
        import yfinance as yf
    except ImportError:
        return {}

    tickers = [t for t, _ in ticker_weight_pairs]
    weights = {t: w for t, w in ticker_weight_pairs}

    try:
        raw = yf.download(tickers, period="10y", interval="1mo",
                          progress=False, auto_adjust=True, actions=False)
        prices = raw["Close"] if "Close" in raw.columns else raw
        if isinstance(prices, pd.Series):
            prices = prices.to_frame(tickers[0])
    except Exception:
        return {}

    annual  = prices.resample("YE").last()
    ret     = annual.pct_change().dropna(how="all")

    # ── Portfolio weighted annual returns ──
    portfolio      = pd.Series(0.0, index=ret.index)
    covered_weight = 0.0
    for ticker in tickers:
        if ticker in ret.columns:
            portfolio = portfolio.add(ret[ticker] * weights[ticker], fill_value=0)
            covered_weight += weights[ticker]
    if 0 < covered_weight < 1:
        portfolio = portfolio / covered_weight
    portfolio.index = portfolio.index.year

    # ── Cumulative growth of $10,000 ──
    cumulative = (1 + portfolio).cumprod() * 10_000

    # ── Per-holding 10-yr CAGR ──
    holding_cagr = {}
    for ticker in tickers:
        if ticker not in ret.columns:
            continue
        series = ret[ticker].dropna()
        if len(series) < 1:
            continue
        n = len(series)
        total_growth = (1 + series).prod()
        cagr = (total_growth ** (1 / n) - 1) * 100
        holding_cagr[ticker] = round(cagr, 2)

    return {
        "portfolio_annual":   (portfolio * 100).round(2) if not (portfolio * 100).empty else portfolio,
        "cumulative":         cumulative.round(0),
        "holding_annualized": holding_cagr,
    }


def _render_401k_returns_chart(holdings: pd.DataFrame):
    """Annual returns bar, cumulative growth line, 10yr CAGR, per-holding comparison."""
    tickered = holdings[
        holdings["ticker"].apply(lambda x: isinstance(x, str) and bool(x.strip()))
    ].copy()
    if tickered.empty:
        return

    total = tickered["fair_market_value"].sum()
    pairs = tuple(
        (row["ticker"].upper(), row["fair_market_value"] / total)
        for _, row in tickered.iterrows()
    )

    with st.spinner("Fetching 10-year historical prices…"):
        data      = _fetch_return_data(pairs)
        bench_ret = _fetch_benchmark_returns(0.70, 0.30)

    if not data:
        st.warning("Could not fetch historical price data for this portfolio.")
        return

    port_ret   = data["portfolio_annual"]
    cumulative = data["cumulative"]
    h_cagr     = data["holding_annualized"]

    # Align benchmark to same years as portfolio
    common_years = port_ret.index.intersection(bench_ret.index) if not bench_ret.empty else port_ret.index
    bench_aligned = bench_ret.reindex(common_years)
    bench_cum     = (1 + bench_ret.reindex(port_ret.index).fillna(0) / 100).cumprod() * 10_000

    # ── KPI row ──
    cagr_10yr  = 0.0
    bench_cagr = 0.0
    final_val  = 0.0
    bench_final = 0.0
    if len(port_ret) >= 2:
        n             = len(port_ret)
        cagr_10yr     = ((1 + port_ret / 100).prod() ** (1 / n) - 1) * 100
        final_val     = cumulative.iloc[-1] if not cumulative.empty else 0
        if len(bench_ret) >= 2:
            nb            = len(bench_ret.reindex(port_ret.index).dropna())
            bench_cagr    = ((1 + bench_ret.reindex(port_ret.index).dropna() / 100).prod() ** (1 / nb) - 1) * 100
            bench_final   = bench_cum.iloc[-1] if not bench_cum.empty else 0

        alpha = cagr_10yr - bench_cagr
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Portfolio Annualized Return", f"{cagr_10yr:.2f}%")
        k2.metric("Benchmark Annualized Return (70/30)", f"{bench_cagr:.2f}%")
        k3.metric("Alpha vs Benchmark", f"{alpha:+.2f}%", delta=f"{alpha:+.2f}%")
        k4.metric("Portfolio $10k →", f"${final_val:,.0f}")
        k5.metric("Benchmark $10k →", f"${bench_final:,.0f}")

    # Stash in session state for save button
    st.session_state["_401k_returns_cache"] = {
        "port_ret":   port_ret,
        "cumulative": cumulative,
        "cagr_10yr":  round(cagr_10yr, 4),
        "final_val":  round(final_val, 2),
    }

    st.divider()

    # ── Cumulative growth — portfolio vs benchmark ──
    st.subheader("Cumulative Growth of $10,000")
    st.caption("Portfolio vs 70/30 benchmark (SPY + AGG), starting value $10,000.")
    fig_cum = go.Figure()
    fig_cum.add_trace(go.Scatter(
        x=cumulative.index.astype(str), y=cumulative.values,
        name="Portfolio", mode="lines+markers",
        line=dict(color="#6366f1", width=3), marker=dict(size=6),
        fill="tozeroy", fillcolor="rgba(99,102,241,0.10)",
        hovertemplate="%{x} Portfolio: $%{y:,.0f}<extra></extra>",
    ))
    if not bench_cum.empty:
        fig_cum.add_trace(go.Scatter(
            x=bench_cum.index.astype(str), y=bench_cum.values,
            name="70/30 Benchmark", mode="lines+markers",
            line=dict(color="#f59e0b", width=2, dash="dash"), marker=dict(size=5),
            hovertemplate="%{x} Benchmark: $%{y:,.0f}<extra></extra>",
        ))
    fig_cum.update_layout(
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        height=320, margin=dict(t=20, b=20, l=20, r=20),
        legend=dict(orientation="h", y=1.08, x=0),
        yaxis=dict(tickprefix="$", tickformat=",", gridcolor="rgba(128,128,128,0.1)"),
        xaxis=dict(showgrid=False, tickmode="linear", dtick=1, tickangle=-45),
    )
    st.plotly_chart(fig_cum, use_container_width=True)

    st.divider()

    # ── Annual returns — portfolio vs benchmark ──
    st.subheader("Annual Return by Year")
    st.caption("Portfolio vs 70/30 benchmark (SPY + AGG). Untickered / stable-value holdings excluded from portfolio.")
    years_str = port_ret.index.astype(str).tolist()
    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        name="Portfolio",
        x=years_str, y=port_ret.values,
        marker_color=["rgba(99,102,241,0.85)" if v >= 0 else "rgba(248,113,113,0.85)" for v in port_ret],
        text=[f"{v:+.1f}%" for v in port_ret.values], textposition="outside",
        hovertemplate="%{x} Portfolio: %{y:.2f}%<extra></extra>",
    ))
    if not bench_aligned.empty:
        fig_bar.add_trace(go.Bar(
            name="70/30 Benchmark",
            x=bench_aligned.index.astype(str), y=bench_aligned.values,
            marker_color=["rgba(245,158,11,0.75)" if v >= 0 else "rgba(200,100,50,0.75)" for v in bench_aligned],
            text=[f"{v:+.1f}%" for v in bench_aligned.values], textposition="outside",
            hovertemplate="%{x} Benchmark: %{y:.2f}%<extra></extra>",
        ))
    fig_bar.update_layout(
        barmode="group", bargap=0.25, bargroupgap=0.05,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        height=380, margin=dict(t=40, b=20, l=20, r=20),
        legend=dict(orientation="h", y=1.08, x=0),
        yaxis=dict(ticksuffix="%", zeroline=True,
                   zerolinecolor="rgba(200,200,200,0.6)", zerolinewidth=1,
                   gridcolor="rgba(128,128,128,0.1)"),
        xaxis=dict(showgrid=False, tickmode="linear", dtick=1, tickangle=-45),
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # ── Per-holding annualized return comparison ──
    if h_cagr:
        st.divider()
        st.subheader("10-Year Annualized Return by Holding")
        st.caption("Annualized return calculated from adjusted monthly close prices over available history.")

        # Include weight info
        weight_map = {t.upper(): w for t, w in pairs}
        cagr_rows = sorted(h_cagr.items(), key=lambda x: x[1], reverse=True)
        cagr_df = pd.DataFrame([
            {
                "Ticker":           t,
                "Annualized Return": f"{v:+.2f}%",
                "Portfolio Weight":  f"{weight_map.get(t, 0)*100:.1f}%",
            }
            for t, v in cagr_rows
        ])

        bar_colors = ["rgba(52,211,153,0.85)" if v >= 0 else "rgba(248,113,113,0.85)"
                      for _, v in cagr_rows]
        fig_h = go.Figure(go.Bar(
            x=[v for _, v in cagr_rows],
            y=[t for t, _ in cagr_rows],
            orientation="h",
            marker_color=bar_colors,
            text=[f"{v:+.1f}%" for _, v in cagr_rows],
            textposition="outside",
            hovertemplate="%{y}: %{x:.2f}%<extra></extra>",
        ))
        fig_h.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=max(300, len(cagr_rows) * 26 + 60),
            margin=dict(t=20, b=20, l=80, r=60),
            xaxis=dict(ticksuffix="%", zeroline=True,
                       zerolinecolor="rgba(200,200,200,0.6)", zerolinewidth=1,
                       gridcolor="rgba(128,128,128,0.1)"),
            yaxis=dict(showgrid=False, autorange="reversed"),
        )
        st.plotly_chart(fig_h, use_container_width=True)
        st.dataframe(cagr_df, use_container_width=True, hide_index=True)


# ── Historical portfolio chart ────────────────────────────────────────────────

def _render_historical_chart(all_filings: list):
    """
    Dual-axis chart:
      • Filled area  = net additions (year-over-year change in portfolio value)
      • Line         = actual portfolio value (fair market value or total assets)
    """
    rows = []
    for f in all_filings:
        yr = f.get("tax_prd_yr")
        if not yr:
            continue
        fmv = (
            _val(f, "fairmrktvaleoy")
            or _val(f, "fairmrktvalamt")
            or _val(f, "totassetsend")
        )
        if fmv:
            # Grants paid = withdrawals (reduce portfolio but not investment loss)
            grants = (
                _val(f, "totgrntspd")
                or _val(f, "grantspd")
                or _val(f, "totgrnts")
                or 0
            )
            # Contributions received = new money in (inflate portfolio but not investment gain)
            contribs = (
                _val(f, "totcntrbgfts")
                or _val(f, "contribgfts")
                or _val(f, "totcntrbgftsprgmrsrv")
                or 0
            )
            rows.append({"year": int(yr), "value": fmv, "grants": grants, "contribs": contribs})

    if len(rows) < 2:
        return

    hist = pd.DataFrame(rows).drop_duplicates("year").sort_values("year").reset_index(drop=True)
    hist["net_addition"] = hist["value"].diff()

    st.divider()
    st.subheader("Portfolio Value & Net Additions Over Time")

    fig = go.Figure()

    # Filled area — net additions (positive = green, negative = red via marker colors)
    colors = [
        "rgba(52, 211, 153, 0.75)" if v >= 0 else "rgba(248, 113, 113, 0.75)"
        for v in hist["net_addition"].fillna(0)
    ]
    fig.add_trace(
        go.Bar(
            x=hist["year"],
            y=hist["net_addition"],
            name="Net Addition ($)",
            marker_color=colors,
            yaxis="y2",
            opacity=0.75,
        )
    )

    # Gradient fill under the value line
    fig.add_trace(
        go.Scatter(
            x=hist["year"],
            y=hist["value"],
            name="Portfolio Value ($)",
            mode="lines+markers",
            line=dict(color="#6366f1", width=3),
            marker=dict(size=8, color="#6366f1", line=dict(width=2, color="white")),
            fill="tozeroy",
            fillcolor="rgba(99, 102, 241, 0.15)",
            yaxis="y1",
        )
    )

    # Value labels on the line
    fig.add_trace(
        go.Scatter(
            x=hist["year"],
            y=hist["value"],
            mode="text",
            text=[f"${v/1e6:.1f}M" for v in hist["value"]],
            textposition="top center",
            textfont=dict(size=11, color="#6366f1"),
            showlegend=False,
            yaxis="y1",
        )
    )

    max_val   = hist["value"].max()
    max_add   = hist["net_addition"].abs().max() or 1
    first_val = hist["value"].iloc[0]

    # y1 starts just below first_val so the x-axis baseline = starting portfolio value.
    y1_bottom = first_val * 0.92
    y1_top    = max_val * 1.12

    # Align y2=0 with y1=first_val:
    #   alpha = fractional position of first_val within [y1_bottom, y1_top]
    #   solve (0 - y2_bottom) / (y2_top - y2_bottom) = alpha  =>  y2_bottom = -y2_top * alpha / (1 - alpha)
    y2_top = max_add * 1.5
    alpha  = (first_val - y1_bottom) / (y1_top - y1_bottom)
    y2_bottom = -y2_top * alpha / (1 - alpha) if alpha < 1 else -y2_top

    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=460,
        margin=dict(t=30, b=40, l=20, r=20),
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
        bargap=0.3,
        xaxis=dict(
            tickmode="linear",
            dtick=1,
            gridcolor="rgba(128,128,128,0.1)",
        ),
        yaxis=dict(
            title=dict(text="Portfolio Value ($)", font=dict(color="#6366f1")),
            tickprefix="$",
            tickformat=".2s",
            range=[y1_bottom, y1_top],
            gridcolor="rgba(128,128,128,0.1)",
            tickfont=dict(color="#6366f1"),
        ),
        yaxis2=dict(
            title=dict(text="Net Addition ($)", font=dict(color="#34d399")),
            tickprefix="$",
            tickformat=".2s",
            overlaying="y",
            side="right",
            range=[y2_bottom, y2_top],
            tickfont=dict(color="#34d399"),
            showgrid=False,
            zeroline=True,
            zerolinecolor="rgba(200,200,200,0.5)",
            zerolinewidth=1,
        ),
    )

    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Net addition = year-over-year change in portfolio value  ·  "
        f"Green bars = growth, red bars = decline"
    )

    # ── Returns table ──
    # net_addition    = value − prev_value
    # investment_gain = net_addition − contributions
    # annual_return   = investment_gain / prev_value
    tbl = hist.copy()
    tbl["prev_value"]   = tbl["value"].shift(1)
    tbl["net_addition"] = tbl["value"] - tbl["prev_value"]
    tbl["inv_gain"]     = tbl["net_addition"] - tbl["contribs"].fillna(0)
    tbl["return_pct"]   = (tbl["inv_gain"] / tbl["prev_value"] * 100).round(2)

    base = tbl["value"].iloc[0]
    tbl["cumul_return_pct"] = ((tbl["value"] - base) / base * 100).round(1)

    display_tbl = tbl[tbl["prev_value"].notna()].copy()
    has_contribs = (display_tbl["contribs"].fillna(0) > 0).any()

    cols_out  = ["year", "value", "net_addition", "inv_gain", "return_pct", "cumul_return_pct"]
    col_names = ["Year", "Portfolio Value", "Net Addition ($)", "Investment Gain ($)", "Annual Return (%)", "Cumulative Return (%)"]
    if has_contribs:
        cols_out  = ["year", "value", "net_addition", "contribs", "inv_gain", "return_pct", "cumul_return_pct"]
        col_names = ["Year", "Portfolio Value", "Net Addition ($)", "Contributions ($)", "Investment Gain ($)", "Annual Return (%)", "Cumulative Return (%)"]

    display_tbl = display_tbl[cols_out].copy()
    display_tbl.columns = col_names

    def _fmt_dollar(x):
        return (f"+${x:,.0f}" if x >= 0 else f"-${abs(x):,.0f}") if pd.notna(x) else "—"

    display_tbl["Portfolio Value"]       = display_tbl["Portfolio Value"].apply(lambda x: f"${x:,.0f}")
    display_tbl["Net Addition ($)"]      = display_tbl["Net Addition ($)"].apply(_fmt_dollar)
    display_tbl["Investment Gain ($)"]   = display_tbl["Investment Gain ($)"].apply(_fmt_dollar)
    display_tbl["Annual Return (%)"]     = display_tbl["Annual Return (%)"].apply(lambda x: f"{x:+.2f}%")
    display_tbl["Cumulative Return (%)"] = display_tbl["Cumulative Return (%)"].apply(lambda x: f"{x:+.1f}%")
    if has_contribs:
        display_tbl["Contributions ($)"] = display_tbl["Contributions ($)"].apply(lambda x: f"${x:,.0f}" if pd.notna(x) and x else "—")

    st.subheader("Annual Returns")
    st.dataframe(display_tbl, use_container_width=True, hide_index=True)


# ── Main page ────────────────────────────────────────────────────────────────

def show_investments(crm):
    st.markdown("""
<style>
[data-testid="stPlotlyChart"] .main-svg,
[data-testid="stPlotlyChart"] .js-plotly-plot,
[data-testid="stPlotlyChart"] {
    cursor: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='20' height='20'%3E%3Ccircle cx='10' cy='10' r='8' fill='none' stroke='white' stroke-width='2'/%3E%3C/svg%3E") 10 10, crosshair !important;
}
</style>
""", unsafe_allow_html=True)

    st.title("Investment Portfolios")
    st.markdown(
        "Select a foundation to view its investment portfolio. "
        "Enter holdings manually or import from CSV for ticker-level detail."
    )

    with crm.get_connection() as conn:
        df = pd.read_sql_query(
            """
            SELECT f.id, f.ein, f.name, f.city, f.investment_assets, f.annual_revenue,
                   f.filing_year, f.form_5500_url,
                   COUNT(h.id) AS holdings_count
            FROM foundations f
            LEFT JOIN investment_holdings h ON h.foundation_id = f.id
            GROUP BY f.id
            ORDER BY f.investment_assets DESC
            """,
            conn,
        )

    if df.empty:
        st.warning("No foundation data available.")
        return

    options = {
        f"{'★ ' if row['holdings_count'] > 0 else ''}{row['name']}  —  ${row['investment_assets']/1e6:.0f}M  ({row['city']})": row["ein"]
        for _, row in df.iterrows()
    }
    selected_label = st.selectbox("Select Foundation  (★ = holdings entered)", list(options.keys()), index=0)
    ein = options[selected_label]

    frow = df[df["ein"] == ein].iloc[0]
    total_assets   = frow["investment_assets"]
    foundation_id  = int(frow["id"])
    holdings_count = int(frow["holdings_count"])
    form5500_url   = frow.get("form_5500_url") or None

    with st.spinner("Loading portfolio data…"):
        result = fetch_filing(ein)

    org    = result["org"]
    filing = result["filing"]
    fc     = org.get("foundation_code")
    year   = filing.get("tax_prd_yr") or frow["filing_year"]

    FORM_TYPE = {
        4:  "990-PF (Private Foundation)",
        3:  "990-PF (Private Foundation)",
        12: "990-PF (Private Operating Foundation)",
    }.get(fc, "Form 990 (Public Charity / Community Foundation)")

    st.markdown(f"### {frow['name']}")
    st.caption(f"{org.get('city', frow['city'])} · Filing: {year} · {FORM_TYPE}")

    holdings_df = None
    if holdings_count > 0:
        holdings_df = show_holdings_view(crm, foundation_id, frow, filing, total_assets, form5500_url=form5500_url)
    else:
        # Show aggregate + attach the import panel below
        inv_income = _val(filing, "netinvstinc") or _val(filing, "invstmntinc")
        gains      = _val(filing, "gnlsecur")
        fair_mkt   = _val(filing, "fairmrktvaleoy") or _val(filing, "fairmrktvalamt")
        tot_revenue = _val(filing, "totrevenue") or frow["annual_revenue"]

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Investment Assets", f"${total_assets/1e6:.1f}M")
        with col2:
            lbl = "Fair Market Value" if fair_mkt else "Investment Income"
            val = fair_mkt if fair_mkt else inv_income
            st.metric(lbl, f"${val/1e6:.1f}M" if val else "N/A")
        with col3:
            if inv_income:
                y = inv_income / total_assets * 100 if total_assets else 0
                st.metric("Investment Yield", f"{y:.2f}%")
            else:
                st.metric("Investment Yield", "N/A")
        with col4:
            if gains:
                st.metric("Realized Gains", f"${gains/1e6:.1f}M")
            else:
                st.metric("Total Revenue", f"${tot_revenue/1e6:.1f}M" if tot_revenue else "N/A")

        st.divider()
        show_aggregate_view(filing, total_assets, frow, year)

    # ── Historical chart (ProPublica multi-year) ──
    all_filings = result.get("all_filings", [])
    _render_historical_chart(all_filings)

    st.caption(
        f"Source: IRS Form 990 / 990-PF via ProPublica Nonprofit Explorer · "
        f"EIN {ein} · Filing year {year}"
    )

    # ── Holdings, donut, bar chart — rendered after Annual Returns ──
    if holdings_df is not None and not holdings_df.empty:
        st.divider()
        _render_401k_returns_chart(holdings_df)
        st.divider()
        _render_holdings_charts(holdings_df)

    # ── Manage Holdings — always at the bottom ──
    st.divider()
    existing = holdings_df if holdings_df is not None else pd.DataFrame()
    _render_import_panel(crm, foundation_id, existing, form5500_url=form5500_url)
