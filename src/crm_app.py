"""
Louisiana Foundations CRM Web Interface

A Streamlit-based CRM system for managing foundation relationships and data.
"""

import math
import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
import os
import io
from pathlib import Path
from src.new_functions import show_followups, show_compliance, show_centers_of_influence


def _dollar_yaxis(series, allow_neg=False) -> dict:
    """Plotly yaxis dict with human-readable $M/$B labels (avoids SI 'G' prefix)."""
    s = pd.Series(series).dropna()
    if s.empty or s.abs().max() == 0:
        return dict(tickprefix='$', tickformat=',.0f')
    mx = s.abs().max()
    mn = s.min() if allow_neg else 0
    unit = 1e9 if mx >= 5e8 else 1e6
    suffix = 'B' if unit == 1e9 else 'M'
    scaled_mx = mx / unit
    mag = 10 ** math.floor(math.log10(scaled_mx))
    step = next(m * mag for m in [0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10]
                if 3 <= scaled_mx / (m * mag) <= 8)
    lo = math.floor(mn / unit / step) * step
    hi = math.ceil(scaled_mx / step + 1) * step
    n = int(round((hi - lo) / step)) + 1
    ticks = [round(lo + i * step, 10) for i in range(n)]
    return dict(
        tickvals=[t * unit for t in ticks],
        ticktext=[f'${t:.3g}{suffix}' for t in ticks],
    )

def create_link_column(df, url_col, text, tooltip):
    """Create a column with clickable links."""
    def make_link(row):
        if pd.notna(row[url_col]) and row[url_col]:
            return f'<a href="{row[url_col]}" target="_blank" title="{tooltip}">{text}</a>'
        return ''
    return df.apply(make_link, axis=1)



# Page configuration
st.set_page_config(
    page_title="Louisiana Foundations CRM",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

class FoundationCRM:
    def __init__(self):
        self.base_dir = Path(__file__).parent.parent
        self.db_path = self.base_dir / "database" / "louisiana_foundations.db"
        
    def get_connection(self):
        """Get database connection."""
        return sqlite3.connect(self.db_path)
    
    def load_foundations(self, filters=None):
        """Load foundations data with optional filters."""
        with self.get_connection() as conn:
            query = """
                SELECT 
                    f.id, f.ein, f.name, f.city, f.state, f.zip_code,
                    f.website, f.phone, f.email,
                    f.board_url, f.about_url,
                    f.investment_assets, f.annual_grants, f.annual_revenue,
                    f.filing_year, f.tax_exempt_status, f.is_active,
                    f.created_at, f.updated_at
                FROM foundations f
                WHERE 1=1
            """
            params = []
            
            if filters:
                if filters.get('min_assets'):
                    query += " AND f.investment_assets >= ?"
                    params.append(filters['min_assets'])
                
                if filters.get('max_assets'):
                    query += " AND f.investment_assets <= ?"
                    params.append(filters['max_assets'])
                
                if filters.get('city'):
                    query += " AND f.city LIKE ?"
                    params.append(f"%{filters['city']}%")
                
                if filters.get('name_search'):
                    query += " AND f.name LIKE ?"
                    params.append(f"%{filters['name_search']}%")
            
            query += " ORDER BY f.investment_assets DESC"
            
            df = pd.read_sql_query(query, conn, params=params)
            return df
    
    def load_foundation_details(self, foundation_id):
        """Load detailed information for a specific foundation."""
        with self.get_connection() as conn:
            # Basic foundation info
            foundation_query = """
                SELECT * FROM foundations WHERE id = ?
            """
            foundation_df = pd.read_sql_query(foundation_query, conn, params=[foundation_id])
            
            # Personnel
            personnel_query = """
                SELECT * FROM personnel WHERE foundation_id = ? AND is_current = 1
                ORDER BY title, name
            """
            personnel_df = pd.read_sql_query(personnel_query, conn, params=[foundation_id])
            
            # Focus areas
            focus_query = """
                SELECT * FROM focus_areas WHERE foundation_id = ?
                ORDER BY is_primary DESC, category
            """
            focus_df = pd.read_sql_query(focus_query, conn, params=[foundation_id])
            
            # Recent interactions
            interactions_query = """
                SELECT * FROM interactions WHERE foundation_id = ?
                ORDER BY interaction_date DESC LIMIT 10
            """
            interactions_df = pd.read_sql_query(interactions_query, conn, params=[foundation_id])
            
            # Investment advisors (legacy table)
            advisor_query = """
                SELECT * FROM investment_advisors WHERE foundation_id = ?
                ORDER BY annual_fee DESC
            """
            try:
                advisors_df = pd.read_sql_query(advisor_query, conn, params=[foundation_id])
            except Exception:
                advisors_df = pd.DataFrame()
            
            # Detailed 990 personnel data
            personnel_990_query = """
                SELECT * FROM personnel_990 WHERE foundation_id = ?
                ORDER BY 
                    CASE 
                        WHEN is_president = 1 OR is_ceo = 1 THEN 1
                        WHEN is_cfo = 1 THEN 2
                        WHEN is_vice_president = 1 THEN 3
                        WHEN is_secretary = 1 THEN 4
                        WHEN is_990_filer = 1 THEN 5
                        WHEN is_officer = 1 THEN 6
                        ELSE 7
                    END,
                    compensation DESC
            """
            try:
                personnel_990_df = pd.read_sql_query(personnel_990_query, conn, params=[foundation_id])
            except Exception:
                personnel_990_df = pd.DataFrame()
            
            # Investment details
            investment_details_query = """
                SELECT * FROM investment_details WHERE foundation_id = ?
                ORDER BY filing_year DESC LIMIT 1
            """
            try:
                investment_details_df = pd.read_sql_query(investment_details_query, conn, params=[foundation_id])
            except Exception:
                investment_details_df = pd.DataFrame()
            
            # Consultants and professional services
            consultants_query = """
                SELECT * FROM consultants_990 WHERE foundation_id = ?
                ORDER BY amount_paid DESC
            """
            try:
                consultants_df = pd.read_sql_query(consultants_query, conn, params=[foundation_id])
            except Exception:
                consultants_df = pd.DataFrame()
            
            return {
                'foundation': foundation_df.iloc[0] if len(foundation_df) > 0 else None,
                'personnel': personnel_df,
                'focus_areas': focus_df,
                'interactions': interactions_df,
                'investment_advisors': advisors_df,
                'personnel_990': personnel_990_df,
                'investment_details': investment_details_df,
                'consultants': consultants_df
            }

    def load_financial_history(self, foundation_id: int):
        with self.get_connection() as conn:
            fh = pd.read_sql_query("""
                SELECT filing_year,
                       total_assets, investment_assets, total_revenue,
                       contributions_received, program_service_revenue,
                       investment_income, capital_gains_losses,
                       total_expenses, grants_paid, administrative_expenses,
                       fundraising_expenses, total_liabilities, net_assets_eoy
                FROM financial_history
                WHERE foundation_id = ?
                ORDER BY filing_year
            """, conn, params=(foundation_id,))

            inv = pd.read_sql_query("""
                SELECT filing_year,
                       securities_publicly_traded, securities_other,
                       program_related_investments, capital_gains, net_investment_income
                FROM investment_details
                WHERE foundation_id = ?
                ORDER BY filing_year
            """, conn, params=(foundation_id,))

        return fh, inv

    def load_comparison_data(self, foundation_ids: list, years: list) -> pd.DataFrame:
        if not foundation_ids or not years:
            return pd.DataFrame()
        placeholders_f = ','.join('?' * len(foundation_ids))
        placeholders_y = ','.join('?' * len(years))
        with self.get_connection() as conn:
            df = pd.read_sql_query(f"""
                SELECT f.name, COALESCE(f.short_name, f.name) AS short_name,
                       fh.foundation_id, fh.filing_year,
                       fh.total_assets, fh.investment_assets, fh.total_revenue,
                       fh.contributions_received, fh.investment_income,
                       fh.capital_gains_losses, fh.grants_paid, fh.net_assets_eoy,
                       fh.total_liabilities, fh.administrative_expenses,
                       fh.total_expenses,
                       CASE WHEN fh.total_assets > 0
                            THEN fh.grants_paid / fh.total_assets * 100
                            ELSE NULL END AS grant_payout_ratio
                FROM financial_history fh
                JOIN foundations f ON f.id = fh.foundation_id
                WHERE fh.foundation_id IN ({placeholders_f})
                  AND fh.filing_year IN ({placeholders_y})
                ORDER BY f.name, fh.filing_year
            """, conn, params=foundation_ids + years)
        return df

    def add_interaction(self, foundation_id, interaction_type, contact_person, 
                       subject, notes, follow_up_date=None):
        """Add a new interaction record."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO interactions 
                (foundation_id, interaction_type, contact_person, subject, notes, follow_up_date, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (foundation_id, interaction_type, contact_person, subject, notes, 
                  follow_up_date, "CRM User"))
            conn.commit()
    
    def get_summary_stats(self):
        """Get summary statistics for dashboard."""
        with self.get_connection() as conn:
            stats = {}
            
            # Total foundations
            stats['total_foundations'] = pd.read_sql_query(
                "SELECT COUNT(*) as count FROM foundations", conn
            ).iloc[0]['count']
            
            # Total assets
            stats['total_assets'] = pd.read_sql_query(
                "SELECT SUM(investment_assets) as total FROM foundations", conn
            ).iloc[0]['total']
            
            # Total grants
            stats['total_grants'] = pd.read_sql_query(
                "SELECT SUM(annual_grants) as total FROM foundations WHERE annual_grants IS NOT NULL", conn
            ).iloc[0]['total']
            
            # Assets by city
            stats['assets_by_city'] = pd.read_sql_query("""
                SELECT city, SUM(investment_assets) as total_assets, COUNT(*) as foundation_count
                FROM foundations 
                WHERE city IS NOT NULL
                GROUP BY city 
                ORDER BY total_assets DESC
                LIMIT 10
            """, conn)
            
            # Asset distribution
            stats['asset_ranges'] = pd.read_sql_query("""
                SELECT 
                    CASE 
                        WHEN investment_assets < 5000000 THEN '$2M - $5M'
                        WHEN investment_assets < 10000000 THEN '$5M - $10M'
                        WHEN investment_assets < 25000000 THEN '$10M - $25M'
                        WHEN investment_assets < 50000000 THEN '$25M - $50M'
                        WHEN investment_assets < 100000000 THEN '$50M - $100M'
                        ELSE '$100M+'
                    END as asset_range,
                    COUNT(*) as count,
                    SUM(investment_assets) as total_assets
                FROM foundations
                GROUP BY asset_range
                ORDER BY MIN(investment_assets)
            """, conn)
            
            return stats

def show_financial_history_tab(crm, foundation_id: int):
    fh, inv = crm.load_financial_history(foundation_id)
    all_years = list(range(2020, 2026))

    # ── Coverage row ────────────────────────────────────────────────────────
    st.subheader("Data Coverage")
    years_with_data = set(fh['filing_year'].tolist()) if not fh.empty else set()
    missing = [y for y in all_years if y not in years_with_data]

    cols = st.columns(len(all_years))
    for i, year in enumerate(all_years):
        with cols[i]:
            if year in years_with_data:
                st.success(f"✓ {year}")
            else:
                st.error(f"✗ {year}")

    if missing:
        st.info(f"No filing data found for: {', '.join(str(y) for y in missing)}. "
                f"These years will show as gaps in the charts below.")

    if fh.empty:
        st.warning("No financial history available for this foundation. "
                   "Run `ingest_990_financials.py` to populate real data.")
        return

    # Shared x-axis config: always show 2020-2025 so gaps are visible
    _xaxis = dict(tickmode='array', tickvals=all_years,
                  range=[2019.5, 2025.5], dtick=1)

    # ── YoY: Assets ─────────────────────────────────────────────────────────
    st.subheader("Assets Over Time")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=fh['filing_year'], y=fh['total_assets'],
                             mode='lines+markers', name='Total Assets',
                             connectgaps=False))
    fig.add_trace(go.Scatter(x=fh['filing_year'], y=fh['investment_assets'],
                             mode='lines+markers', name='Investment Assets',
                             connectgaps=False))
    _assets = pd.concat([fh['total_assets'], fh['investment_assets']])
    fig.update_layout(yaxis=_dollar_yaxis(_assets), xaxis=_xaxis,
                      height=300, margin=dict(t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # Delta row
    if len(fh) >= 2:
        latest = fh.iloc[-1]
        prior  = fh.iloc[-2]
        if pd.notna(latest['total_assets']) and pd.notna(prior['total_assets']):
            delta = latest['total_assets'] - prior['total_assets']
            direction = "▲" if delta >= 0 else "▼"
            st.caption(f"Total Assets {direction} ${abs(delta)/1e6:.1f}M from {int(prior['filing_year'])}")

    # ── YoY: Revenue breakdown ───────────────────────────────────────────────
    st.subheader("Revenue Breakdown")
    fig2 = go.Figure()
    rev_cols = ['contributions_received', 'investment_income', 'program_service_revenue']
    for col, label in zip(rev_cols, ['Contributions', 'Investment Income', 'Program Svc Revenue']):
        if col in fh.columns:
            fig2.add_trace(go.Scatter(x=fh['filing_year'], y=fh[col],
                                      mode='lines+markers', name=label,
                                      connectgaps=False))
    _rev = pd.concat([fh[c] for c in rev_cols if c in fh.columns])
    fig2.update_layout(yaxis=_dollar_yaxis(_rev), xaxis=_xaxis,
                       height=300, margin=dict(t=20, b=20))
    st.plotly_chart(fig2, use_container_width=True)

    # ── YoY: Capital gains/losses ────────────────────────────────────────────
    st.subheader("Capital Gains / Losses")
    if 'capital_gains_losses' in fh.columns and fh['capital_gains_losses'].notna().any():
        colors = ['#2ecc71' if v >= 0 else '#e74c3c'
                  for v in fh['capital_gains_losses'].fillna(0)]
        fig3 = go.Figure(go.Bar(x=fh['filing_year'], y=fh['capital_gains_losses'],
                                marker_color=colors, name='Capital Gains/Losses'))
        fig3.add_hline(y=0, line_dash='dash', line_color='gray')
        fig3.update_layout(yaxis=_dollar_yaxis(fh['capital_gains_losses'], allow_neg=True),
                           xaxis=_xaxis, height=280, margin=dict(t=20, b=20))
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("Capital gains/losses data not available.")

    # ── YoY: Grants paid + payout ratio ─────────────────────────────────────
    st.subheader("Grants Paid & Payout Ratio")
    fig4 = go.Figure()
    fig4.add_trace(go.Bar(x=fh['filing_year'], y=fh['grants_paid'],
                          name='Grants Paid', yaxis='y1'))
    payout = (fh['grants_paid'] / fh['total_assets'] * 100).where(fh['total_assets'] > 0)
    fig4.add_trace(go.Scatter(x=fh['filing_year'], y=payout, mode='lines+markers',
                              name='Payout %', yaxis='y2'))
    _grants_yfmt = {**_dollar_yaxis(fh['grants_paid']), 'title': 'Grants Paid'}
    fig4.update_layout(
        yaxis=_grants_yfmt,
        yaxis2=dict(ticksuffix='%', overlaying='y', side='right', title='Payout %'),
        xaxis=_xaxis,
        height=300, margin=dict(t=20, b=20), legend=dict(orientation='h')
    )
    st.plotly_chart(fig4, use_container_width=True)

    # ── Investment breakdown (most recent year) ──────────────────────────────
    if not inv.empty:
        st.subheader(f"Investment Breakdown ({int(inv.iloc[-1]['filing_year'])})")
        latest_inv = inv.iloc[-1]
        breakdown = {
            'Publicly Traded Securities': latest_inv.get('securities_publicly_traded') or 0,
            'Other Securities':           latest_inv.get('securities_other') or 0,
            'Program-Related':            latest_inv.get('program_related_investments') or 0,
        }
        breakdown = {k: v for k, v in breakdown.items() if v > 0}
        if breakdown:
            fig5 = go.Figure(go.Pie(labels=list(breakdown.keys()),
                                    values=list(breakdown.values()),
                                    hole=0.35))
            fig5.update_layout(height=280, margin=dict(t=20, b=20))
            st.plotly_chart(fig5, use_container_width=True)

    # ── Performance Analysis table ────────────────────────────────────────────
    st.subheader("Performance Analysis")
    perf_rows = []
    fh_sorted = fh.sort_values('filing_year').reset_index(drop=True)
    for i, row in fh_sorted.iterrows():
        yr        = int(row['filing_year'])
        end       = row.get('total_assets')
        begin     = fh_sorted.loc[i - 1, 'total_assets'] if i > 0 else None
        inv_a     = row.get('investment_assets')  # Schedule D securities total
        # Use Schedule D assets only when they represent ≥60% of total (likely comprehensive).
        # Otherwise use total_assets — Schedule D is a partial view for many foundations.
        inv_a_ok  = pd.notna(inv_a) and inv_a and inv_a > 0 and pd.notna(end) and end and (inv_a / end) >= 0.6
        denom     = inv_a if inv_a_ok else end
        contribs  = row.get('contributions_received')
        grants    = row.get('grants_paid')
        inc       = row.get('investment_income')
        cap       = row.get('capital_gains_losses')
        admin     = row.get('administrative_expenses')
        total_exp = row.get('total_expenses')
        total_rev = row.get('total_revenue')

        def _pct(num, den):
            if pd.notna(num) and pd.notna(den) and den and den != 0:
                return num / den * 100
            return None

        net_flows  = (contribs - grants) if (pd.notna(contribs) and pd.notna(grants)) else None
        raw_chg    = _pct(end - begin, begin) if (pd.notna(begin) and begin and pd.notna(end)) else None

        # Modified Dietz: strips external cash flows from apparent asset change
        if pd.notna(begin) and begin and pd.notna(end) and net_flows is not None:
            md_denom = begin + 0.5 * net_flows
            mod_dietz = _pct(end - begin - net_flows, md_denom) if md_denom else None
        else:
            mod_dietz = None

        income_yield = _pct(inc, denom)
        cap_return   = _pct(cap, denom)
        total_ret    = (
            (income_yield or 0) + (cap_return or 0)
            if (income_yield is not None or cap_return is not None) else None
        )
        payout       = _pct(grants, end)
        overhead     = _pct(admin, total_exp)
        contrib_dep  = _pct(contribs, total_rev)

        perf_rows.append({
            'Year':               yr,
            'Total Assets':       end,
            'Asset Δ %':          raw_chg,
            'Net Flows':          net_flows,
            'Mod. Dietz %':       mod_dietz,
            'Income Yield %':     income_yield,
            'Cap. Return %':      cap_return,
            'Total Return %':     total_ret,
            'Payout Ratio %':     payout,
            'Overhead %':         overhead,
            'Contrib. Dep. %':    contrib_dep,
        })

    perf = pd.DataFrame(perf_rows).set_index('Year')

    def _fmt_dollar(v):
        if pd.isna(v) or v is None: return '—'
        sign = '-' if v < 0 else ''
        av = abs(v)
        if av >= 1e9: return f'{sign}${av/1e9:.2f}B'
        if av >= 1e6: return f'{sign}${av/1e6:.1f}M'
        return f'{sign}${av:,.0f}'

    def _fmt_pct(v):
        if pd.isna(v) or v is None: return '—'
        return f"{v:+.1f}%"

    def _fmt_pct_plain(v):
        if pd.isna(v) or v is None: return '—'
        return f"{v:.1f}%"

    pct_sign_cols = ['Asset Δ %', 'Mod. Dietz %', 'Income Yield %',
                     'Cap. Return %', 'Total Return %']
    pct_plain_cols = ['Payout Ratio %', 'Overhead %', 'Contrib. Dep. %']

    display = perf.copy()
    display['Total Assets'] = display['Total Assets'].apply(_fmt_dollar)
    display['Net Flows']    = display['Net Flows'].apply(_fmt_dollar)
    for c in pct_sign_cols:
        display[c] = display[c].apply(_fmt_pct)
    for c in pct_plain_cols:
        display[c] = display[c].apply(_fmt_pct_plain)

    def _color_signed(v):
        if isinstance(v, str) and v.startswith('+'):
            return 'color: #27ae60; font-weight: bold'
        if isinstance(v, str) and v.startswith('-'):
            return 'color: #e74c3c; font-weight: bold'
        return ''

    styled = display.style.applymap(_color_signed, subset=pct_sign_cols)
    st.dataframe(styled, use_container_width=True)
    st.caption(
        "**Modified Dietz** adjusts for contributions received and grants paid at period midpoint, "
        "isolating investment performance from external cash flows. "
        "**Income Yield** and **Cap. Return** denominator: Schedule D investment assets when they "
        "represent ≥60% of total assets (portfolio appears comprehensive); otherwise total assets. "
        "**Overhead** = admin expenses ÷ total expenses. "
        "**Contrib. Dep.** = contributions ÷ total revenue."
    )


COMPARISON_METRICS = {
    'Total Assets':         'total_assets',
    'Investment Assets':    'investment_assets',
    'Capital Gains/Losses': 'capital_gains_losses',
    'Contributions Received': 'contributions_received',
    'Investment Income':    'investment_income',
    'Grants Paid':          'grants_paid',
    'Net Assets':           'net_assets_eoy',
    'Grant Payout Ratio %': 'grant_payout_ratio',
}


def show_financial_comparison(crm):
    st.title("📊 Financial Comparison")

    # ── Sidebar controls ─────────────────────────────────────────────────────
    metric_label = st.sidebar.selectbox("Metric", list(COMPARISON_METRICS.keys()))
    metric_col   = COMPARISON_METRICS[metric_label]

    all_years = list(range(2020, 2026))
    year_range = st.sidebar.select_slider(
        "Year Range", options=all_years, value=(2020, 2025)
    )
    selected_years = list(range(year_range[0], year_range[1] + 1))

    try:
        with crm.get_connection() as conn:
            all_foundations = pd.read_sql_query(
                "SELECT id, name FROM foundations ORDER BY name",
                conn
            )
    except Exception as e:
        st.error(f"Could not load foundations: {e}")
        return

    selected_names = st.sidebar.multiselect(
        "Foundations", options=all_foundations['name'].tolist(),
        default=all_foundations['name'].tolist()
    )
    selected_ids = all_foundations[
        all_foundations['name'].isin(selected_names)
    ]['id'].tolist()

    if not selected_ids:
        st.info("Select at least one foundation.")
        return

    df = crm.load_comparison_data(selected_ids, selected_years)

    # ── Snapshot vs. Trend view ───────────────────────────────────────────────
    is_single_year = len(selected_years) == 1

    if is_single_year:
        year = selected_years[0]
        st.subheader(f"{metric_label} — {year}")

        # Build full roster including foundations with no data
        snap_src = df[df['filing_year'] == year][['name', 'short_name', metric_col]].copy()
        all_names_df = pd.DataFrame({'name': selected_names})
        snapshot = all_names_df.merge(snap_src, on='name', how='left')
        snapshot['short_name'] = snapshot['short_name'].fillna(snapshot['name'])
        snapshot = snapshot.sort_values(metric_col, ascending=True, na_position='first')

        is_pct = 'ratio' in metric_col or 'pct' in metric_col
        colors = ['#cccccc' if pd.isna(v) else '#2c7bb6' for v in snapshot[metric_col]]
        hover = snapshot[metric_col].apply(
            lambda v: "No data" if pd.isna(v)
            else (f"{v:.1f}%" if is_pct else f"${v:,.0f}")
        )

        fig = go.Figure(go.Bar(
            x=snapshot[metric_col], y=snapshot['short_name'],
            orientation='h', marker_color=colors,
            hovertext=hover, hoverinfo='text+y'
        ))
        if is_pct:
            xaxis_fmt = dict(tickformat='.1f', ticksuffix='%')
        else:
            xaxis_fmt = _dollar_yaxis(snapshot[metric_col])
        fig.update_layout(
            xaxis=xaxis_fmt,
            height=max(400, len(selected_names) * 22),
            margin=dict(l=150, t=20, b=40)
        )
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.subheader(f"{metric_label} — {selected_years[0]}–{selected_years[-1]}")

        is_pct = 'ratio' in metric_col or 'pct' in metric_col
        fig = go.Figure()
        for name in selected_names:
            fdata = df[df['name'] == name].sort_values('filing_year')
            short = fdata['short_name'].iloc[0] if not fdata.empty else name
            n_years = fdata['filing_year'].nunique()
            completeness = f"{n_years}/{len(selected_years)} yrs"
            fig.add_trace(go.Scatter(
                x=fdata['filing_year'], y=fdata[metric_col],
                mode='lines+markers', name=f"{short} ({completeness})",
                connectgaps=False
            ))
        if is_pct:
            yaxis_fmt = dict(tickformat='.1f', ticksuffix='%')
        else:
            yaxis_fmt = _dollar_yaxis(df[metric_col])
        fig.update_layout(
            yaxis=yaxis_fmt,
            xaxis=dict(tickmode='array', tickvals=selected_years,
                       range=[min(selected_years) - 0.5, max(selected_years) + 0.5]),
            height=450, margin=dict(t=20, b=20),
            legend=dict(orientation='v', x=1.01)
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Data table ───────────────────────────────────────────────────────────
    st.subheader("Data Table")
    if df.empty:
        st.info("No data for selected foundations and years.")
    else:
        pivot = df.pivot_table(index='name', columns='filing_year',
                               values=metric_col, aggfunc='first')
        pivot = pivot.reindex(columns=selected_years)
        pivot.columns = [str(y) for y in pivot.columns]
        pivot = pivot.reset_index().rename(columns={'name': 'Foundation'})

        # Format for display
        is_pct = 'ratio' in metric_col or 'pct' in metric_col
        year_cols = [str(y) for y in selected_years]
        display = pivot.copy()
        for col in year_cols:
            display[col] = display[col].apply(
                lambda v: '—' if pd.isna(v)
                else (f"{v:.1f}%" if is_pct else f"${v:,.0f}")
            )
        st.dataframe(display, use_container_width=True, hide_index=True)

        # CSV export (raw numbers)
        csv_bytes = pivot.to_csv(index=False).encode()
        st.download_button(
            label="⬇ Download CSV",
            data=csv_bytes,
            file_name=f"foundation_{metric_col}_comparison.csv",
            mime='text/csv'
        )

    # ── Performance Analysis ──────────────────────────────────────────────────
    st.divider()
    st.subheader("Performance Analysis")

    avail_years = sorted(df['filing_year'].dropna().unique().astype(int), reverse=True)
    if not avail_years:
        st.info("No data available for the selected foundations and years.")
        return

    perf_year = st.selectbox(
        "Year", options=avail_years, key='comparison_perf_year',
        help="Metrics computed for this tax year. Modified Dietz uses prior year as starting value."
    )

    # Load prior year outside the selected range if needed
    prior_year = perf_year - 1
    if prior_year in [row for row in df['filing_year'].unique()]:
        prior_df = df[df['filing_year'] == prior_year]
    else:
        prior_df = crm.load_comparison_data(selected_ids, [prior_year])

    curr_df = df[df['filing_year'] == perf_year]

    def _p(num, den):
        if pd.notna(num) and pd.notna(den) and den and den != 0:
            return num / den * 100
        return None

    perf_rows = []
    full_name_map = {}  # short_name -> full name (for navigation)
    for _, curr in curr_df.iterrows():
        name  = curr['name']
        short = curr['short_name']
        full_name_map[short] = name
        prior = prior_df[prior_df['name'] == name]
        begin = prior['total_assets'].iloc[0] if not prior.empty else None

        end       = curr['total_assets']
        inv_a     = curr['investment_assets']
        inv_ok    = pd.notna(inv_a) and inv_a and inv_a > 0 and pd.notna(end) and end and (inv_a / end) >= 0.6
        denom     = inv_a if inv_ok else end
        contribs  = curr['contributions_received']
        grants    = curr['grants_paid']
        inc       = curr['investment_income']
        cap       = curr['capital_gains_losses']
        admin     = curr['administrative_expenses']
        total_exp = curr['total_expenses']
        total_rev = curr['total_revenue']

        net_flows = (contribs - grants) if (pd.notna(contribs) and pd.notna(grants)) else None
        raw_chg   = _p(end - begin, begin) if (pd.notna(begin) and begin and pd.notna(end)) else None

        if pd.notna(begin) and begin and pd.notna(end) and net_flows is not None:
            md_d = begin + 0.5 * net_flows
            mod_dietz = _p(end - begin - net_flows, md_d) if md_d else None
        else:
            mod_dietz = None

        income_yield = _p(inc, denom)
        cap_return   = _p(cap, denom)
        total_ret    = (
            (income_yield or 0) + (cap_return or 0)
            if (income_yield is not None or cap_return is not None) else None
        )

        perf_rows.append({
            'Foundation':       short,
            'Total Assets':     end,
            'Asset Δ %':        raw_chg,
            'Mod. Dietz %':     mod_dietz,
            'Income Yield %':   income_yield,
            'Cap. Return %':    cap_return,
            'Total Return %':   total_ret,
            'Net Flows':        net_flows,
            'Payout Ratio %':   _p(grants, end),
            'Overhead %':       _p(admin, total_exp),
            'Contrib. Dep. %':  _p(contribs, total_rev),
        })

    if not perf_rows:
        st.info(f"No data for {perf_year}.")
        return

    perf = pd.DataFrame(perf_rows)

    def _fd(v):
        if pd.isna(v) or v is None: return None
        sign = '-' if v < 0 else ''
        av = abs(v)
        if av >= 1e9: return f'{sign}${av/1e9:.2f}B'
        if av >= 1e6: return f'{sign}${av/1e6:.1f}M'
        return f'{sign}${av:,.0f}'

    def _fp(v, signed=True):
        if pd.isna(v) or v is None: return None
        return f"{v:+.1f}%" if signed else f"{v:.1f}%"

    sign_cols  = ['Asset Δ %', 'Mod. Dietz %', 'Income Yield %', 'Cap. Return %', 'Total Return %']
    plain_cols = ['Payout Ratio %', 'Overhead %', 'Contrib. Dep. %']

    display = perf.copy()
    display['Total Assets'] = display['Total Assets'].apply(_fd)
    display['Net Flows']    = display['Net Flows'].apply(_fd)
    for c in sign_cols:
        display[c] = display[c].apply(_fp)
    for c in plain_cols:
        display[c] = display[c].apply(lambda v: _fp(v, signed=False))

    def _color(v):
        if isinstance(v, str) and v.startswith('+'):
            return 'color: #27ae60; font-weight: bold'
        if isinstance(v, str) and v.startswith('-'):
            return 'color: #e74c3c; font-weight: bold'
        return ''

    styled = display.style.applymap(_color, subset=sign_cols)
    sel = st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        key="comparison_perf_table",
    )
    st.caption(
        f"**{perf_year}** performance. Click a row to select, then open foundation details. "
        "Click any column header to sort. "
        "**Mod. Dietz** strips contributions and grants at midpoint. "
        "Income/Cap. Return use Schedule D assets when ≥60% of total; otherwise total assets. "
        "**Contrib. Dep.** = contributions ÷ total revenue."
    )

    selected_rows = sel.selection.rows
    if selected_rows:
        short = perf.iloc[selected_rows[0]]['Foundation']
        full  = full_name_map.get(short, short)
        if st.button(f"📋 Open {short} — Foundation Details", key="comparison_perf_nav"):
            st.session_state._pending_nav    = 'Foundation Details'
            st.session_state._nav_foundation = full
            st.rerun()

    perf_csv = perf.to_csv(index=False).encode()
    st.download_button("⬇ Download Performance CSV", perf_csv,
                       file_name=f"performance_{perf_year}.csv", mime='text/csv')


def main():
    crm = FoundationCRM()

    # Resolve any pending navigation BEFORE widgets are instantiated
    if '_pending_nav' in st.session_state:
        st.session_state._sidebar_nav = st.session_state.pop('_pending_nav')

    # Sidebar navigation
    st.sidebar.title("🏛️ Louisiana Foundations CRM")
    _pages = ["Dashboard", "Foundation Directory", "Foundation Details", "Follow-ups",
              "Compliance", "Centers of Influence", "Add Interaction", "Data Management",
              "📊 Financial Comparison"]
    if '_sidebar_nav' not in st.session_state:
        st.session_state._sidebar_nav = 'Dashboard'
    page = st.sidebar.selectbox("Navigate", _pages, key='_sidebar_nav')
    
    if page == "Dashboard":
        show_dashboard(crm)
    elif page == "Foundation Directory":
        show_foundation_directory(crm)
    elif page == "Foundation Details":
        show_foundation_details(crm)
    elif page == "Follow-ups":
        show_followups(crm)
    elif page == "Compliance":
        show_compliance(crm)
    elif page == "Centers of Influence":
        show_centers_of_influence(crm)
    elif page == "Add Interaction":
        show_add_interaction(crm)
    elif page == "Data Management":
        show_data_management(crm)
    elif page == "📊 Financial Comparison":
        show_financial_comparison(crm)

def show_dashboard(crm):
    """Display the main dashboard with summary statistics."""
    st.title("📊 Dashboard")
    st.markdown("### Louisiana Foundations Overview")
    
    try:
        stats = crm.get_summary_stats()
        
        # Key metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "Total Foundations", 
                f"{stats['total_foundations']:,}",
                help="Foundations with >$2M in investment assets"
            )
        
        with col2:
            if stats['total_assets']:
                st.metric(
                    "Total Assets", 
                    f"${stats['total_assets']/1e9:.1f}B",
                    help="Combined investment assets of all foundations"
                )
            else:
                st.metric("Total Assets", "No data")
        
        with col3:
            if stats['total_grants']:
                st.metric(
                    "Annual Grants", 
                    f"${stats['total_grants']/1e6:.1f}M",
                    help="Total annual grant distributions"
                )
            else:
                st.metric("Annual Grants", "No data")
        
        with col4:
            if stats['total_assets'] and stats['total_grants']:
                payout_rate = (stats['total_grants'] / stats['total_assets']) * 100
                st.metric(
                    "Avg Payout Rate", 
                    f"{payout_rate:.1f}%",
                    help="Annual grants as % of total assets"
                )
            else:
                st.metric("Avg Payout Rate", "No data")
        
        # Charts
        if len(stats['assets_by_city']) > 0:
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Assets by City")
                fig = px.bar(
                    stats['assets_by_city'], 
                    x='city', 
                    y='total_assets',
                    title="Investment Assets by City"
                )
                fig.update_yaxes(title="Total Assets ($)")
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.subheader("Foundation Count by City")
                fig = px.bar(
                    stats['assets_by_city'], 
                    x='city', 
                    y='foundation_count',
                    title="Number of Foundations by City"
                )
                fig.update_yaxes(title="Number of Foundations")
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
        
        if len(stats['asset_ranges']) > 0:
            st.subheader("Asset Size Distribution")
            fig = px.pie(
                stats['asset_ranges'], 
                values='count', 
                names='asset_range',
                title="Foundations by Asset Range"
            )
            st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"Error loading dashboard data: {e}")
        st.info("💡 Try running the data acquisition script first to populate the database.")

def show_foundation_directory(crm):
    """Display the searchable foundation directory."""
    st.title("📁 Foundation Directory")
    
    # Search and filter controls
    st.sidebar.subheader("🔍 Search & Filter")
    
    name_search = st.sidebar.text_input("Foundation Name", placeholder="Search by name...")
    city_filter = st.sidebar.text_input("City", placeholder="Filter by city...")
    
    min_assets = st.sidebar.number_input(
        "Minimum Assets ($M)", 
        min_value=2.0, 
        value=2.0, 
        step=1.0
    ) * 1_000_000
    
    max_assets = st.sidebar.number_input(
        "Maximum Assets ($M)", 
        min_value=2.0, 
        value=1000.0, 
        step=10.0
    ) * 1_000_000
    
    filters = {
        'name_search': name_search if name_search else None,
        'city': city_filter if city_filter else None,
        'min_assets': min_assets,
        'max_assets': max_assets
    }
    
    try:
        df = crm.load_foundations(filters)
        
        if len(df) == 0:
            st.warning("No foundations found matching your criteria.")
            return
        
        st.success(f"Found {len(df)} foundations")
        
        # Format the display
        display_df = df.copy()
        display_df['investment_assets'] = display_df['investment_assets'].apply(
            lambda x: f"${x/1_000_000:.1f}M" if pd.notna(x) else "N/A"
        )
        display_df['annual_grants'] = display_df['annual_grants'].apply(
            lambda x: f"${x/1_000_000:.1f}M" if pd.notna(x) else "N/A"
        )
        
        # Create link columns for board and about pages
        def make_board_link(row):
            if pd.notna(row['board_url']) and row['board_url']:
                return f'<a href="{row["board_url"]}" target="_blank" title="View Board Page">👥 Board</a>'
            return ''
        
        def make_about_link(row):
            if pd.notna(row['about_url']) and row['about_url']:
                return f'<a href="{row["about_url"]}" target="_blank" title="View About Page">ℹ️ About</a>'
            return ''
        
        def make_website_link(row):
            if pd.notna(row['website']) and row['website']:
                return f'<a href="{row["website"]}" target="_blank" title="Visit Website">🌐 Website</a>'
            return ''
        
        display_df['Board'] = display_df.apply(make_board_link, axis=1)
        display_df['About'] = display_df.apply(make_about_link, axis=1)
        display_df['Website'] = display_df.apply(make_website_link, axis=1)
        
        # Display table
        st.dataframe(
            display_df[[
                'name', 'city', 'investment_assets', 'annual_grants', 
                'Board', 'About', 'Website', 'filing_year'
            ]].rename(columns={
                'name': 'Foundation Name',
                'city': 'City',
                'investment_assets': 'Investment Assets',
                'annual_grants': 'Annual Grants',
                'filing_year': 'Last Filing'
            }),
            use_container_width=True,
            height=600,
            column_config={
                'Board': st.column_config.LinkColumn("Board Page", display_text="Board"),
                'About': st.column_config.LinkColumn("About Page", display_text="About"),
                'Website': st.column_config.LinkColumn("Website", display_text="Website"),
            }
        )
        
        # Export option
        if st.button("📥 Export to CSV"):
            csv = df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"louisiana_foundations_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        
    except Exception as e:
        st.error(f"Error loading foundation data: {e}")

def show_foundation_details(crm):
    """Show detailed view of a specific foundation."""
    st.title("🏛️ Foundation Details")
    
    # Foundation selection
    try:
        df = crm.load_foundations()
        if len(df) == 0:
            st.warning("No foundation data available.")
            return
        
        foundation_options = {f"{row['name']} ({row['city']})": row['id']
                            for _, row in df.iterrows()}

        nav_f = st.session_state.pop('_nav_foundation', None)
        if nav_f:
            for k in foundation_options.keys():
                if nav_f.lower() in k.lower():
                    st.session_state['_detail_foundation'] = k
                    break

        selected_name = st.selectbox(
            "Select Foundation",
            options=list(foundation_options.keys()),
            key='_detail_foundation',
        )
        
        if selected_name:
            foundation_id = foundation_options[selected_name]
            details = crm.load_foundation_details(foundation_id)
            
            if details['foundation'] is not None:
                foundation = details['foundation']
                tab_overview, tab_financial = st.tabs(["📋 Overview", "📈 Financial History"])

                with tab_overview:
                    # Basic information
                    col1, col2 = st.columns(2)

                    with col1:
                        st.subheader("📋 Basic Information")
                        st.text(f"EIN: {foundation['ein']}")
                        st.text(f"Legal Name: {foundation['name']}")
                        st.text(f"City: {foundation['city']}, {foundation['state']} {foundation['zip_code']}")

                        # Website links
                        if foundation.get('website'):
                            st.markdown(f"[🌐 Visit Website]({foundation['website']})")

                        if foundation.get('board_url') and foundation['board_url'] != '':
                            st.markdown(f"[👥 View Board Page]({foundation['board_url']})")

                        if foundation.get('about_url') and foundation['about_url'] != '':
                            st.markdown(f"[ℹ️ View About Page]({foundation['about_url']})")

                        if foundation.get('phone'):
                            st.text(f"Phone: {foundation['phone']}")
                        if foundation.get('email'):
                            st.text(f"Email: {foundation['email']}")

                    with col2:
                        st.subheader("💰 Financial Summary")
                        if foundation['investment_assets']:
                            st.metric("Investment Assets", f"${foundation['investment_assets']/1_000_000:.1f}M")
                        if foundation['annual_grants']:
                            st.metric("Annual Grants", f"${foundation['annual_grants']/1_000_000:.1f}M")
                        if foundation['annual_revenue']:
                            st.metric("Annual Revenue", f"${foundation['annual_revenue']/1_000_000:.1f}M")

                        st.text(f"Last Filing: {foundation['filing_year']}")
                        st.text(f"Tax Status: {foundation['tax_exempt_status']}")

                    # Detailed 990 Personnel Information
                    if len(details['personnel_990']) > 0:
                        st.subheader("👥 Executive Leadership & Board (Form 990 Data)")

                        personnel_990_df = details['personnel_990']

                        # Executive Officers with Compensation
                        executives = personnel_990_df[
                            (personnel_990_df['is_president'] == 1) |
                            (personnel_990_df['is_ceo'] == 1) |
                            (personnel_990_df['is_cfo'] == 1) |
                            (personnel_990_df['is_vice_president'] == 1)
                        ]

                        if len(executives) > 0:
                            st.write("**💼 Executive Officers & Compensation:**")
                            for _, exec in executives.iterrows():
                                roles = []
                                if exec['is_president'] == 1: roles.append('President')
                                if exec['is_ceo'] == 1: roles.append('CEO')
                                if exec['is_cfo'] == 1: roles.append('CFO')
                                if exec['is_vice_president'] == 1: roles.append('Vice President')

                                role_str = ' & '.join(roles)
                                total_comp = exec['compensation'] + (exec['benefits'] or 0)

                                st.write(f"• **{exec['name']}** - {role_str}")
                                st.write(f"  💰 Base: ${exec['compensation']:,.0f} | Benefits: ${exec['benefits'] or 0:,.0f} | **Total: ${total_comp:,.0f}**")
                                if exec['hours_per_week']:
                                    st.write(f"  ⏰ Hours/week: {exec['hours_per_week']}")

                        # 990 Filer
                        filer = personnel_990_df[personnel_990_df['is_990_filer'] == 1]
                        if len(filer) > 0:
                            st.write("**📋 Form 990 Filed By:**")
                            for _, f in filer.iterrows():
                                comp_str = f"${f['compensation']:,.0f}" if f['compensation'] > 0 else "No compensation"
                                st.write(f"• **{f['name']}** - {f['title']} ({comp_str})")

                        # Other Officers (Secretary, Treasurer, etc.)
                        other_officers = personnel_990_df[
                            (personnel_990_df['is_officer'] == 1) &
                            (personnel_990_df['is_president'] != 1) &
                            (personnel_990_df['is_ceo'] != 1) &
                            (personnel_990_df['is_cfo'] != 1) &
                            (personnel_990_df['is_vice_president'] != 1)
                        ]

                        if len(other_officers) > 0:
                            with st.expander("🏛️ Other Officers"):
                                for _, officer in other_officers.iterrows():
                                    comp_str = f"${officer['compensation']:,.0f}" if officer['compensation'] > 0 else "No compensation"
                                    st.write(f"• **{officer['name']}** - {officer['title']} ({comp_str})")

                        # Board of Trustees/Directors
                        board = personnel_990_df[
                            (personnel_990_df['is_trustee'] == 1) |
                            (personnel_990_df['is_director'] == 1)
                        ]

                        if len(board) > 0:
                            with st.expander("👥 Board of Directors/Trustees"):
                                for _, member in board.iterrows():
                                    comp_str = f"${member['compensation']:,.0f}" if member['compensation'] > 0 else "Volunteer"
                                    hours_str = f" ({member['hours_per_week']}h/week)" if member['hours_per_week'] else ""
                                    st.write(f"• **{member['name']}** - {member['title']} ({comp_str}){hours_str}")
                                    # Display bio if available
                                    if member.get('bio') and member['bio'] and str(member['bio']).strip():
                                        st.write(f"  📝 *{member['bio'][:200]}{'...' if len(str(member['bio'])) > 200 else ''}*")
                                    elif member.get('biography') and member['biography'] and str(member['biography']).strip():
                                        st.write(f"  📝 *{member['biography'][:200]}{'...' if len(str(member['biography'])) > 200 else ''}*")
                                    # Display LinkedIn link if available
                                    if member.get('linkedin_url') and member['linkedin_url']:
                                        st.markdown(f"[💼 LinkedIn Profile]({member['linkedin_url']})")

                    # Investment Portfolio Details
                    if len(details['investment_details']) > 0:
                        st.subheader("📊 Investment Portfolio Analysis")

                        inv_details = details['investment_details'].iloc[0]

                        col1, col2 = st.columns(2)

                        with col1:
                            st.write("**Portfolio Allocation:**")
                            total_investments = inv_details['securities_publicly_traded'] + inv_details['securities_other'] + inv_details['program_related_investments'] + inv_details['other_investments']

                            if total_investments > 0:
                                st.write(f"• Publicly Traded Securities: ${inv_details['securities_publicly_traded']/1e6:.1f}M ({inv_details['securities_publicly_traded']/total_investments*100:.1f}%)")
                                st.write(f"• Other Securities: ${inv_details['securities_other']/1e6:.1f}M ({inv_details['securities_other']/total_investments*100:.1f}%)")
                                st.write(f"• Program Related Investments: ${inv_details['program_related_investments']/1e6:.1f}M ({inv_details['program_related_investments']/total_investments*100:.1f}%)")
                                st.write(f"• Other Investments: ${inv_details['other_investments']/1e6:.1f}M ({inv_details['other_investments']/total_investments*100:.1f}%)")

                        with col2:
                            st.write("**Investment Performance:**")
                            st.write(f"• Dividend Income: ${inv_details['dividend_income']/1e6:.1f}M")
                            st.write(f"• Interest Income: ${inv_details['interest_income']/1e6:.1f}M")
                            st.write(f"• Capital Gains: ${inv_details['capital_gains']/1e6:.1f}M")
                            st.write(f"• Investment Expenses: ${inv_details['investment_expenses']/1e6:.1f}M")
                            st.write(f"• **Net Investment Income: ${inv_details['net_investment_income']/1e6:.1f}M**")

                            net_return = inv_details['net_investment_income'] / total_investments * 100 if total_investments > 0 else 0
                            st.write(f"• **Total Return: {net_return:.1f}%**")

                    # Professional Services & Consultants
                    if len(details['consultants']) > 0:
                        st.subheader("💼 Professional Services & Consultant Payments")

                        consultants_df = details['consultants']

                        # Investment Management
                        investment_mgmt = consultants_df[consultants_df['is_investment_advisor'] == 1]
                        if len(investment_mgmt) > 0:
                            st.write("**💰 Investment Management:**")
                            for _, advisor in investment_mgmt.iterrows():
                                fee_pct_str = f" ({advisor['fee_percentage']*100:.2f}% of assets)" if advisor['fee_percentage'] else ""
                                st.write(f"• **{advisor['name']}** - ${advisor['amount_paid']:,.0f}/year{fee_pct_str}")
                                if advisor['description']:
                                    st.write(f"  📝 {advisor['description']}")

                        # Other Professional Services
                        other_services = consultants_df[consultants_df['is_investment_advisor'] != 1]
                        if len(other_services) > 0:
                            with st.expander("🏢 Other Professional Services"):
                                for _, service in other_services.iterrows():
                                    service_type = service['service_type'].replace('_', ' ').title()
                                    st.write(f"• **{service['name']}** ({service_type}) - ${service['amount_paid']:,.0f}")
                                    if service['description']:
                                        st.write(f"  📝 {service['description']}")

                        # Total professional service costs
                        total_costs = consultants_df['amount_paid'].sum()
                        st.write(f"**📊 Total Professional Service Costs: ${total_costs:,.0f}/year**")

                    # Legacy personnel data (fallback if 990 data not available)
                    elif len(details['personnel']) > 0:
                        st.subheader("👥 Key Personnel & Board Members")

                        personnel_df = details['personnel']

                        with st.expander("📋 Personnel Information"):
                            display_cols = ['name', 'title', 'role', 'compensation', 'hours_per_week']
                            available_cols = [col for col in display_cols if col in personnel_df.columns]
                            st.dataframe(personnel_df[available_cols], width=None)

                    # Investment Advisors
                    if len(details['investment_advisors']) > 0:
                        st.subheader("💼 Investment Advisors & Contract Payments")

                        for _, advisor in details['investment_advisors'].iterrows():
                            with st.expander(f"📊 {advisor['advisor_name']} - ${advisor['annual_fee']:,}/year"):
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.write(f"**EIN**: {advisor['advisor_ein']}")
                                    st.write(f"**Services**: {advisor['services']}")
                                    st.write(f"**Contract Start**: {advisor['contract_start']}")
                                with col2:
                                    st.write(f"**Annual Fee**: ${advisor['annual_fee']:,}")
                                    st.write(f"**Fee Type**: {advisor['fee_type'].replace('_', ' ').title()}")
                                    if advisor['fee_percentage']:
                                        st.write(f"**Fee Rate**: {advisor['fee_percentage']:.2f}% of assets")
                                    st.write(f"**Assets Managed**: ${advisor['assets_managed']/1_000_000:.1f}M")

                    # Focus Areas
                    if len(details['focus_areas']) > 0:
                        st.subheader("🎯 Focus Areas")
                        st.dataframe(details['focus_areas'][['category', 'subcategory', 'description']], use_container_width=True)

                    # Recent Interactions
                    if len(details['interactions']) > 0:
                        st.subheader("📞 Recent Interactions")
                        st.dataframe(
                            details['interactions'][['interaction_date', 'interaction_type', 'contact_person', 'subject']],
                            use_container_width=True
                        )
                    else:
                        st.info("No interactions recorded yet.")

                with tab_financial:
                    show_financial_history_tab(crm, foundation_id)
            
    except Exception as e:
        st.error(f"Error loading foundation details: {e}")

def show_add_interaction(crm):
    """Form to add new interaction records."""
    st.title("📝 Add Interaction")
    
    try:
        df = crm.load_foundations()
        if len(df) == 0:
            st.warning("No foundation data available.")
            return
        
        foundation_options = {f"{row['name']} ({row['city']})": row['id']
                            for _, row in df.iterrows()}
        
        with st.form("add_interaction"):
            selected_name = st.selectbox("Foundation", options=list(foundation_options.keys()))
            foundation_id = foundation_options[selected_name]
            
            interaction_type = st.selectbox(
                "Interaction Type",
                ["call", "email", "meeting", "proposal", "grant", "research", "other"]
            )
            
            contact_person = st.text_input("Contact Person")
            subject = st.text_input("Subject/Purpose")
            notes = st.text_area("Notes", height=100)
            
            follow_up_date = st.date_input(
                "Follow-up Date (Optional)",
                value=None
            )
            
            if st.form_submit_button("Save Interaction"):
                crm.add_interaction(
                    foundation_id=foundation_id,
                    interaction_type=interaction_type,
                    contact_person=contact_person,
                    subject=subject,
                    notes=notes,
                    follow_up_date=follow_up_date
                )
                st.success("Interaction saved successfully!")
    
    except Exception as e:
        st.error(f"Error saving interaction: {e}")

def show_data_management(crm):
    """Data management and import utilities."""
    st.title("⚙️ Data Management")
    
    tab1, tab2, tab3 = st.tabs(["Import Data", "Export Data", "Database Stats"])
    
    with tab1:
        st.subheader("📥 Import Foundation Data")
        
        st.markdown("""
        **Data Sources:**
        - ProPublica Nonprofit Explorer API
        - IRS Annual Extract files
        - Manual CSV uploads
        """)
        
        if st.button("🔄 Run Data Acquisition"):
            with st.spinner("Fetching foundation data... This may take several minutes."):
                # This would run the data acquisition script
                st.info("Data acquisition process started. Check the console for progress.")
                # In a real implementation, you'd run the acquisition script here
        
        st.subheader("📄 Upload CSV Data")
        uploaded_file = st.file_uploader("Choose CSV file", type="csv")
        
        if uploaded_file is not None:
            try:
                df = pd.read_csv(uploaded_file)
                st.dataframe(df.head())
                
                if st.button("Import CSV Data"):
                    # Process and import CSV data
                    st.success("CSV data imported successfully!")
            except Exception as e:
                st.error(f"Error processing CSV: {e}")
    
    with tab2:
        st.subheader("📤 Export Foundation Data")
        
        try:
            with crm.get_connection() as conn:
                # Export foundations
                foundations_df = pd.read_sql_query("SELECT * FROM foundations", conn)
                if len(foundations_df) > 0:
                    csv = foundations_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download Foundations (CSV)",
                        data=csv,
                        file_name=f"foundations_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                
                # Export personnel
                personnel_df = pd.read_sql_query("SELECT * FROM personnel_990", conn)
                if len(personnel_df) > 0:
                    csv = personnel_df.to_csv(index=False)
                    st.download_button(
                        label="👥 Download Personnel (CSV)",
                        data=csv,
                        file_name=f"personnel_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                
                # Export centers of influence
                coi_df = pd.read_sql_query("SELECT * FROM centers_of_influence", conn)
                if len(coi_df) > 0:
                    csv = coi_df.to_csv(index=False)
                    st.download_button(
                        label="👔 Download Centers of Influence (CSV)",
                        data=csv,
                        file_name=f"centers_of_influence_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                
                # Export interactions
                interactions_df = pd.read_sql_query("SELECT * FROM interactions", conn)
                if len(interactions_df) > 0:
                    csv = interactions_df.to_csv(index=False)
                    st.download_button(
                        label="📝 Download Interactions (CSV)",
                        data=csv,
                        file_name=f"interactions_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                
                # Export grants
                grants_df = pd.read_sql_query("SELECT * FROM grants", conn)
                if len(grants_df) > 0:
                    csv = grants_df.to_csv(index=False)
                    st.download_button(
                        label="💰 Download Grants (CSV)",
                        data=csv,
                        file_name=f"grants_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                
                # Export focus areas
                focus_df = pd.read_sql_query("SELECT * FROM focus_areas", conn)
                if len(focus_df) > 0:
                    csv = focus_df.to_csv(index=False)
                    st.download_button(
                        label="🎯 Download Focus Areas (CSV)",
                        data=csv,
                        file_name=f"focus_areas_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
            
            # Excel export with multiple sheets
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                if len(foundations_df) > 0:
                    foundations_df.to_excel(writer, sheet_name='Foundations', index=False)
                if len(personnel_df) > 0:
                    personnel_df.to_excel(writer, sheet_name='Personnel', index=False)
                if len(coi_df) > 0:
                    coi_df.to_excel(writer, sheet_name='Centers of Influence', index=False)
                if len(interactions_df) > 0:
                    interactions_df.to_excel(writer, sheet_name='Interactions', index=False)
            
            st.download_button(
                label="📊 Download Complete Database (Excel)",
                data=excel_buffer.getvalue(),
                file_name=f"crm_database_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        except Exception as e:
            st.error(f"Error preparing export: {e}")
    
    with tab3:
        st.subheader("📊 Database Statistics")
        
        try:
            with crm.get_connection() as conn:
                # Table sizes
                ALLOWED_TABLES = {'foundations', 'personnel', 'focus_areas', 'grants', 'interactions'}
                tables = ['foundations', 'personnel', 'focus_areas', 'grants', 'interactions']
                
                for table in tables:
                    if table not in ALLOWED_TABLES:
                        continue
                    count = pd.read_sql_query(f"SELECT COUNT(*) as count FROM {table}", conn).iloc[0]['count']
                    st.metric(f"{table.title()} Records", f"{count:,}")
                
                # Database file size
                if crm.db_path.exists():
                    size_mb = crm.db_path.stat().st_size / (1024 * 1024)
                    st.metric("Database Size", f"{size_mb:.1f} MB")
        
        except Exception as e:
            st.error(f"Error loading database stats: {e}")

if __name__ == "__main__":
    main()