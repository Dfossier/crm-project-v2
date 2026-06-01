"""
Louisiana Foundations CRM Web Interface

A Streamlit-based CRM system for managing foundation relationships and data.
"""

import sys
import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
import os
import io
from pathlib import Path

# Ensure project root is on sys.path so src.* imports resolve correctly
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.new_functions import show_followups, show_compliance, show_centers_of_influence
from src.profile_editor import show_personnel_profiles
from src.investments import show_investments

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
                    f.total_assets, f.investment_assets, f.annual_grants, f.annual_revenue,
                    f.filing_year, f.tax_exempt_status, f.is_active,
                    f.form_5500_url, f.form_5500_type,
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

def main():
    crm = FoundationCRM()
    
    # Sidebar navigation
    st.sidebar.title("🏛️ Louisiana Foundations CRM")
    page = st.sidebar.selectbox(
        "Navigate",
        ["Dashboard", "Foundation Directory", "Foundation Details", "Investment", "Follow-ups", "Compliance", "Centers of Influence", "Personnel Profiles", "Add Interaction", "Data Management", "Scrapping Data"]
    )
    
    if page == "Dashboard":
        show_dashboard(crm)
    elif page == "Foundation Directory":
        show_foundation_directory(crm)
    elif page == "Foundation Details":
        show_foundation_details(crm)
    elif page == "Investment":
        show_investments(crm)
    elif page == "Follow-ups":
        show_followups(crm)
    elif page == "Compliance":
        show_compliance(crm)
    elif page == "Centers of Influence":
        show_centers_of_influence(crm)
    elif page == "Personnel Profiles":
        show_personnel_profiles(crm)
        show_centers_of_influence(crm)
    elif page == "Add Interaction":
        show_add_interaction(crm)
    elif page == "Data Management":
        show_data_management(crm)
    elif page == "Scrapping Data":
        show_scrapping_data(crm)

def show_dashboard(crm):
    """Display the main dashboard with summary statistics."""
    st.title("Louisiana Foundations")
    st.caption("Louisiana philanthropic landscape — investment assets, grant activity, and geographic distribution")

    _CHART_THEME = dict(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=12),
    )
    _PALETTE = [
        "#6366f1", "#f59e0b", "#10b981", "#3b82f6",
        "#ec4899", "#8b5cf6", "#14b8a6", "#f97316",
        "#06b6d4", "#84cc16",
    ]

    try:
        stats = crm.get_summary_stats()

        # ── KPI strip ────────────────────────────────────────────────────────
        st.divider()
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.metric("Foundations Tracked", f"{stats['total_foundations']:,}")
        with k2:
            st.metric("Total Investment Assets",
                      f"${stats['total_assets']/1e9:.2f}B" if stats['total_assets'] else "—")
        with k3:
            st.metric("Annual Grants",
                      f"${stats['total_grants']/1e6:.1f}M" if stats['total_grants'] else "—")
        with k4:
            if stats['total_assets'] and stats['total_grants']:
                st.metric("Avg Payout Rate",
                          f"{stats['total_grants']/stats['total_assets']*100:.1f}%")
            else:
                st.metric("Avg Payout Rate", "—")
        st.divider()

        # ── Row 1: assets by city (horizontal bar) + asset-size donut ────────
        if len(stats['assets_by_city']) > 0 and len(stats['asset_ranges']) > 0:
            col_bar, col_donut = st.columns([3, 2])

            with col_bar:
                city_df = stats['assets_by_city'].sort_values("total_assets")
                fig_city = go.Figure(go.Bar(
                    x=city_df["total_assets"],
                    y=city_df["city"],
                    orientation="h",
                    marker=dict(
                        color=city_df["total_assets"],
                        colorscale=[[0, "#c7d2fe"], [1, "#4f46e5"]],
                        showscale=False,
                    ),
                    text=[f"${v/1e6:.0f}M" for v in city_df["total_assets"]],
                    textposition="outside",
                    hovertemplate="%{y}: $%{x:,.0f}<extra></extra>",
                ))
                fig_city.update_layout(
                    **_CHART_THEME,
                    title=dict(text="Investment Assets by City", font=dict(size=14)),
                    height=360,
                    margin=dict(t=32, b=32, l=16, r=80),
                    xaxis=dict(
                        tickprefix="$", tickformat=".2s", showgrid=True,
                        gridcolor="rgba(128,128,128,0.1)", zeroline=False,
                        range=[0, city_df["total_assets"].max() * 1.35],
                    ),
                    yaxis=dict(showgrid=False),
                )
                st.plotly_chart(fig_city, use_container_width=True)

            with col_donut:
                order = ["$2M - $5M", "$5M - $10M", "$10M - $25M",
                         "$25M - $50M", "$50M - $100M", "$100M+"]
                ranges_df = stats['asset_ranges'].copy()
                ranges_df["sort_key"] = ranges_df["asset_range"].apply(
                    lambda x: order.index(x) if x in order else 99
                )
                ranges_df = ranges_df.sort_values("sort_key")

                fig_donut = go.Figure(go.Pie(
                    labels=ranges_df["asset_range"],
                    values=ranges_df["count"],
                    hole=0.55,
                    marker=dict(colors=_PALETTE, line=dict(color="white", width=2)),
                    textinfo="percent",
                    textfont=dict(size=11),
                    hovertemplate="%{label}<br>%{value} foundations (%{percent})<extra></extra>",
                    sort=False,
                ))
                total_f = ranges_df["count"].sum()
                fig_donut.add_annotation(
                    text=f"<b>{total_f}</b><br><span style='font-size:11px'>foundations</span>",
                    x=0.5, y=0.5, showarrow=False,
                    font=dict(size=16),
                    align="center",
                )
                fig_donut.update_layout(
                    **_CHART_THEME,
                    title=dict(text="Foundations by Asset Size", font=dict(size=14)),
                    height=360,
                    margin=dict(t=32, b=32, l=16, r=160),
                    legend=dict(
                        orientation="v", x=1.02, y=0.5, xanchor="left",
                        font=dict(size=11),
                    ),
                )
                st.plotly_chart(fig_donut, use_container_width=True)

        # ── Row 2: foundation count by city (clean dot/lollipop) ─────────────
        if len(stats['assets_by_city']) > 0:
            city_df = stats['assets_by_city'].sort_values("foundation_count")
            fig_count = go.Figure()
            fig_count.add_trace(go.Scatter(
                x=city_df["foundation_count"],
                y=city_df["city"],
                mode="markers",
                marker=dict(size=14, color="#f59e0b",
                            line=dict(width=2, color="white")),
                hovertemplate="%{y}: %{x} foundations<extra></extra>",
                name="",
            ))
            for _, row in city_df.iterrows():
                fig_count.add_shape(
                    type="line",
                    x0=0, x1=row["foundation_count"],
                    y0=row["city"], y1=row["city"],
                    line=dict(color="rgba(245,158,11,0.35)", width=2),
                )
            fig_count.update_layout(
                **_CHART_THEME,
                title=dict(text="Number of Foundations by City", font=dict(size=14)),
                height=320,
                margin=dict(t=32, b=32, l=16, r=16),
                xaxis=dict(
                    showgrid=True, gridcolor="rgba(128,128,128,0.1)",
                    zeroline=False, title="",
                    range=[0, city_df["foundation_count"].max() * 1.2],
                ),
                yaxis=dict(showgrid=False),
                showlegend=False,
            )
            st.plotly_chart(fig_count, use_container_width=True)

    except Exception as e:
        st.error(f"Error loading dashboard data: {e}")

def _efast2_parse_pdf(pdf_url: str) -> tuple[str | None, int | None]:
    """Download a Form 5500 PDF; return (form_type, sched_h_page) parsed from its text.

    form_type is e.g. '5500', '5500-SF', '5500-EZ'.
    sched_h_page is the 1-based page number where Schedule H starts, or None.
    """
    import requests, io, re
    try:
        import pypdf
    except ImportError:
        return None, None
    try:
        r = requests.get(pdf_url, timeout=30)
        if r.status_code != 200:
            return None, None
        reader = pypdf.PdfReader(io.BytesIO(r.content))
        form_type = None
        sched_h_page = None
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ''
            # Detect form type from the first few pages
            if form_type is None and i < 3:
                if re.search(r'Form\s+5500-EZ', text, re.IGNORECASE):
                    form_type = '5500-EZ'
                elif re.search(r'Form\s+5500-SF', text, re.IGNORECASE):
                    form_type = '5500-SF'
                elif re.search(r'Form\s+5500\b', text, re.IGNORECASE):
                    form_type = '5500'
            # Detect Schedule H
            if sched_h_page is None and ('SCHEDULE H' in text.upper()):
                sched_h_page = i + 1
            if form_type and sched_h_page:
                break
        return form_type, sched_h_page
    except Exception:
        return None, None


_RETIREMENT_PAT = None

def _efast2_fetch_latest(ein: str) -> tuple[str | None, str | None]:
    """Query EFAST2 for an EIN; return (schedule_h_url, form_type) for the best matching filing."""
    import requests, urllib.parse, re
    global _RETIREMENT_PAT
    if _RETIREMENT_PAT is None:
        _RETIREMENT_PAT = re.compile(r'retirement|pension|401.?k|403.?b|profit.?shar|deferred.?comp', re.IGNORECASE)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Referer': 'https://www.efast.dol.gov/5500Search/',
    }
    try:
        q = urllib.parse.quote(f'ein:{ein}')
        url = f'https://www.efast.dol.gov/services/afs?q.parser=lucene&q={q}&size=100'
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None, None
        hits = r.json().get('hits', {}).get('hit', [])
        if not hits:
            return None, None
        large = [h for h in hits if int(h.get('fields', {}).get('participantsboy', 0) or 0) >= 100]
        pool = large if large else hits
        pool.sort(key=lambda h: h.get('fields', {}).get('datereceived', ''), reverse=True)
        retirement = [h for h in pool if _RETIREMENT_PAT.search(h.get('fields', {}).get('planname', ''))]
        candidates = retirement if retirement else pool
        for candidate in candidates[:3]:
            pdf_path = candidate['fields'].get('pdfpath', '')
            if not pdf_path:
                continue
            pdf_url = 'https://efast2-filings-public.s3.amazonaws.com/prd' + pdf_path
            form_type, sched_h_page = _efast2_parse_pdf(pdf_url)
            if sched_h_page:
                return f'{pdf_url}#page={sched_h_page}', form_type
        # fallback: return first candidate without page anchor
        first_path = candidates[0]['fields'].get('pdfpath', '') if candidates else ''
        if first_path:
            pdf_url = 'https://efast2-filings-public.s3.amazonaws.com/prd' + first_path
            form_type, _ = _efast2_parse_pdf(pdf_url)
            return pdf_url, form_type
        return None, None
    except Exception:
        return None, None


def show_foundation_directory(crm):
    """Display the searchable foundation directory."""
    st.title("📁 Foundation Directory")

    # DB migration: add form_5500 columns if missing
    with crm.get_connection() as conn:
        for col in ["form_5500_url TEXT", "form_5500_type TEXT"]:
            try:
                conn.execute(f"ALTER TABLE foundations ADD COLUMN {col}")
            except Exception:
                pass
        conn.commit()

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

        # ── Form 5500 fetch button ──────────────────────────────────────────
        with st.expander("Form 5500 (Employee Benefit Plan Filings)"):
            st.caption(
                "Fetches the most recent Form 5500 filing PDF from the DOL EFAST2 database for each foundation's EIN. "
                "Form 5500 covers employee benefit plans (pension / 401k / health) — not the foundation's endowment. "
                "Many private foundations won't have filings; large university funds typically do."
            )
            col_f1, col_f2, col_f3 = st.columns([1, 1, 3])
            fetch_one_5500 = col_f1.button("Fetch 1 Form 5500")
            fetch_all_5500 = col_f2.button("Fetch All Form 5500 Links")

            if fetch_one_5500:
                first = df[df['ein'].notna()].iloc[0]
                ein_str = str(int(float(first['ein'])))
                st.text(f"Testing: {first['name']} (EIN {ein_str})")
                link, ftype = _efast2_fetch_latest(ein_str)
                if link:
                    with crm.get_connection() as conn:
                        conn.execute(
                            "UPDATE foundations SET form_5500_url=?, form_5500_type=? WHERE id=?",
                            (link, ftype, int(first['id']))
                        )
                        conn.commit()
                    st.success(f"Found ({ftype}): {link}")
                    st.rerun()
                else:
                    st.warning("No Form 5500 filing found for this foundation.")

            if fetch_all_5500:
                eins = df[df['ein'].notna()][['id', 'ein', 'name']].values.tolist()
                prog = st.progress(0)
                status_box = st.empty()
                found_count = 0
                with crm.get_connection() as conn:
                    for i, (fid, ein, name) in enumerate(eins):
                        ein_str = str(int(float(ein))) if ein else ''
                        status_box.text(f"Checking {name} (EIN {ein_str})…")
                        link, ftype = _efast2_fetch_latest(ein_str)
                        if link:
                            conn.execute(
                                "UPDATE foundations SET form_5500_url=?, form_5500_type=? WHERE id=?",
                                (link, ftype, fid)
                            )
                            found_count += 1
                        prog.progress((i + 1) / len(eins))
                    conn.commit()
                status_box.text(f"Done. Found Form 5500 filings for {found_count} of {len(eins)} foundations.")
                st.rerun()

        # Format display
        display_df = df.copy()

        def _clean_url(v):
            return str(v).strip() if pd.notna(v) and str(v).strip() not in ("", "nan") else None

        display_df['website']      = display_df['website'].apply(_clean_url)
        display_df['board_url']    = display_df['board_url'].apply(_clean_url)
        display_df['about_url']    = display_df['about_url'].apply(_clean_url)
        display_df['form_5500_url']  = display_df['form_5500_url'].apply(_clean_url)
        display_df['form_5500_type'] = display_df['form_5500_type'].apply(
            lambda v: str(v).strip() if pd.notna(v) and str(v).strip() not in ('', 'nan') else ''
        )

        # Add row index
        display_df.insert(0, '#', range(1, len(display_df) + 1))

        def _fmt_dollars(v):
            return f"${v:,.0f}" if pd.notna(v) and v else ""

        display_df['total_assets_fmt']      = display_df['total_assets'].apply(_fmt_dollars)
        display_df['investment_assets_fmt'] = display_df['investment_assets'].apply(_fmt_dollars)
        display_df['annual_grants_fmt']     = display_df['annual_grants'].apply(_fmt_dollars)

        table = display_df[[
            '#', 'name', 'ein', 'city', 'state', 'zip_code', 'phone', 'email',
            'total_assets_fmt', 'investment_assets_fmt', 'annual_grants_fmt',
            'website', 'board_url', 'about_url', 'filing_year',
            'form_5500_type', 'form_5500_url',
        ]].copy()
        table.columns = [
            '#', 'Name', 'EIN', 'City', 'State', 'ZIP', 'Phone', 'Email',
            'Total Assets', 'Investment Assets', 'Annual Grants',
            'Website', 'Board Page', 'About Page', 'Last Filing',
            'Form Type', 'Schedule H',
        ]

        st.dataframe(
            table,
            use_container_width=True,
            height=600,
            hide_index=True,
            column_config={
                '#':                  st.column_config.NumberColumn('#', width=40),
                'Name':               st.column_config.TextColumn('Name', width='large'),
                'EIN':                st.column_config.TextColumn('EIN', width='small'),
                'City':               st.column_config.TextColumn('City', width='small'),
                'State':              st.column_config.TextColumn('State', width=50),
                'ZIP':                st.column_config.TextColumn('ZIP', width=70),
                'Phone':              st.column_config.TextColumn('Phone', width='small'),
                'Email':              st.column_config.TextColumn('Email', width='medium'),
                'Total Assets':       st.column_config.TextColumn('Total Assets', width='medium'),
                'Investment Assets':  st.column_config.TextColumn('Investment Assets', width='medium'),
                'Annual Grants':      st.column_config.TextColumn('Annual Grants', width='medium'),
                'Website':            st.column_config.LinkColumn('Website', display_text='Visit', width='small'),
                'Board Page':         st.column_config.LinkColumn('Board Page', display_text='Board', width='small'),
                'About Page':         st.column_config.LinkColumn('About Page', display_text='About', width='small'),
                'Last Filing':        st.column_config.NumberColumn('Last Filing', format='%d', width='small'),
                'Form Type':          st.column_config.TextColumn('Form Type', width=90),
                'Schedule H':         st.column_config.LinkColumn('Schedule H', display_text='View PDF', width='small'),
            },
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

        selected_name = st.selectbox(
            "Select Foundation",
            options=list(foundation_options.keys())
        )
        
        if selected_name:
            foundation_id = foundation_options[selected_name]
            details = crm.load_foundation_details(foundation_id)
            
            if details['foundation'] is not None:
                foundation = details['foundation']
                
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
                        for _, exec_row in executives.iterrows():
                            roles = []
                            if exec_row['is_president'] == 1: roles.append('President')
                            if exec_row['is_ceo'] == 1: roles.append('CEO')
                            if exec_row['is_cfo'] == 1: roles.append('CFO')
                            if exec_row['is_vice_president'] == 1: roles.append('Vice President')

                            role_str = ' & '.join(roles)
                            total_comp = exec_row['compensation'] + (exec_row['benefits'] or 0)

                            st.write(f"• **{exec_row['name']}** - {role_str}")
                            st.write(f"  💰 Base: ${exec_row['compensation']:,.0f} | Benefits: ${exec_row['benefits'] or 0:,.0f} | **Total: ${total_comp:,.0f}**")
                            if exec_row['hours_per_week']:
                                st.write(f"  ⏰ Hours/week: {exec_row['hours_per_week']}")

                    # 990 Filer
                    filer = personnel_990_df[personnel_990_df['is_990_filer'] == 1]
                    if len(filer) > 0:
                        st.write("**📋 Form 990 Filed By:**")
                        for _, f_row in filer.iterrows():
                            comp_str = f"${f_row['compensation']:,.0f}" if f_row['compensation'] > 0 else "No compensation"
                            st.write(f"• **{f_row['name']}** - {f_row['title']} ({comp_str})")

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
                                if pd.notna(member.get('linkedin_url')) and member['linkedin_url']:
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
            
    except Exception as e:
        st.error(f"Error loading foundation details: {e}")

def show_add_interaction(crm):
    """Form to add new interaction records."""
    st.title("Log Interaction")
    st.caption("Record a call, meeting, email, or any touchpoint with a foundation.")

    _TYPE_COLORS = {
        "call": "#6366f1", "email": "#3b82f6", "meeting": "#10b981",
        "proposal": "#f59e0b", "grant": "#ec4899", "research": "#8b5cf6", "other": "#94a3b8",
    }

    try:
        df = crm.load_foundations()
        if len(df) == 0:
            st.warning("No foundation data available.")
            return

        foundation_options = {
            f"{row['name']} ({row['city']})": row['id']
            for _, row in df.iterrows()
        }

        col_form, col_recent = st.columns([3, 2])

        with col_form:
            with st.form("add_interaction", clear_on_submit=True):
                selected_name = st.selectbox("Foundation", options=list(foundation_options.keys()))

                c1, c2 = st.columns(2)
                with c1:
                    interaction_type = st.selectbox(
                        "Type",
                        ["call", "email", "meeting", "proposal", "grant", "research", "other"],
                        format_func=lambda x: x.title(),
                    )
                with c2:
                    contact_person = st.text_input("Contact Person", placeholder="Name or role")

                subject = st.text_input("Subject", placeholder="Brief description of the interaction")
                notes   = st.text_area("Notes", height=120, placeholder="Key takeaways, next steps, context…")

                c3, c4 = st.columns(2)
                with c3:
                    interaction_date = st.date_input("Interaction Date", value=date.today())
                with c4:
                    follow_up_date = st.date_input("Follow-up Date (optional)", value=None)

                submitted = st.form_submit_button("Save Interaction", use_container_width=True, type="primary")
                if submitted:
                    crm.add_interaction(
                        foundation_id=foundation_options[selected_name],
                        interaction_type=interaction_type,
                        contact_person=contact_person,
                        subject=subject,
                        notes=notes,
                        follow_up_date=follow_up_date,
                    )
                    st.success(f"Saved — {interaction_type.title()} with {selected_name.split('(')[0].strip()}")

        with col_recent:
            st.markdown("**Recent Interactions**")
            with crm.get_connection() as conn:
                recent = pd.read_sql_query(
                    """SELECT f.name, i.interaction_type, i.contact_person,
                              i.subject, i.interaction_date, i.follow_up_date
                       FROM interactions i
                       LEFT JOIN foundations f ON i.foundation_id = f.id
                       ORDER BY i.interaction_date DESC, i.id DESC
                       LIMIT 10""",
                    conn,
                )
            if recent.empty:
                st.caption("No interactions logged yet.")
            else:
                for _, row in recent.iterrows():
                    itype = str(row["interaction_type"] or "other").lower()
                    color = _TYPE_COLORS.get(itype, "#94a3b8")
                    name  = str(row["name"] or "")
                    subj  = str(row["subject"] or "")
                    dt    = str(row["interaction_date"] or "")[:10]
                    fu    = str(row["follow_up_date"] or "")[:10]
                    st.markdown(
                        f"""<div style="padding:10px 12px;border-radius:8px;margin-bottom:6px;
                            border-left:3px solid {color};background:rgba(0,0,0,0.02);">
                            <div style="font-weight:600;font-size:13px">{name}</div>
                            <div style="color:#6b7280;font-size:11px;margin:1px 0">
                                {itype.title()} &nbsp;·&nbsp; {dt}
                                {"&nbsp;·&nbsp; follow-up " + fu if fu and fu != "None" else ""}
                            </div>
                            {"<div style='font-size:12px;margin-top:2px'>" + subj[:80] + "</div>" if subj else ""}
                        </div>""",
                        unsafe_allow_html=True,
                    )

    except Exception as e:
        st.error(f"Error: {e}")

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
        
        st.subheader("Import Centers of Influence CSV")
        st.markdown(
            "Expected columns: **Name**, **Foundation Name**, **Title** (opt), "
            "**LinkedIn URL** (opt), **Role** (opt), **Employer** (opt), "
            "**Company City** (opt), **Company State** (opt)."
        )
        coi_file = st.file_uploader("Upload Centers of Influence CSV", type=["csv"], key="coi_import")
        if coi_file:
            try:
                coi_raw = pd.read_csv(coi_file)
                st.dataframe(coi_raw.head(), use_container_width=True)
                if st.button("Import COI CSV", key="do_coi_import"):
                    deduped = coi_raw.drop_duplicates(subset=["Name", "Foundation Name"], keep="last")
                    with crm.get_connection() as conn:
                        c = conn.cursor()
                        c.execute("SELECT id, name FROM foundations")
                        fmap = {r[1].lower().strip(): r[0] for r in c.fetchall()}
                        n_ok = n_skip = 0
                        for _, row in deduped.iterrows():
                            fname = str(row.get("Foundation Name", "")).strip()
                            fid = fmap.get(fname.lower())
                            if not fid or not str(row.get("Name", "")).strip():
                                n_skip += 1
                                continue
                            city  = str(row.get("Company City", "") or "").strip()
                            state = str(row.get("Company State", "") or "").strip()
                            loc   = ", ".join(filter(None, [city, state])) or None
                            role  = str(row.get("Role", "") or "").strip() or None
                            emp   = str(row.get("Employer", "") or "").strip() or None
                            notes_parts = []
                            title = str(row.get("Title", "") or "").strip() or None
                            if role and role != title:
                                notes_parts.append(f"Role: {role}")
                            if emp:
                                notes_parts.append(f"Employer: {emp}")
                            c.execute(
                                """INSERT INTO centers_of_influence
                                   (foundation_id, name, title, location, linkedin_url, notes)
                                   VALUES (?,?,?,?,?,?)""",
                                (fid, str(row["Name"]).strip(), title, loc,
                                 str(row.get("LinkedIn URL", "") or "").strip() or None,
                                 " | ".join(notes_parts) or None),
                            )
                            n_ok += 1
                        conn.commit()
                    st.success(f"Imported {n_ok} contacts ({n_skip} skipped — unmatched foundation or missing name).")
                    st.rerun()
            except Exception as e:
                st.error(f"Error reading CSV: {e}")
    
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

def show_scrapping_data(crm):
    st.title("Scrapping Data")
    st.caption("Web scraping tools for enriching foundation data.")


if __name__ == "__main__":
    main()