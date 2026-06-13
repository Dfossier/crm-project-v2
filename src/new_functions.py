import re
import html
import streamlit as st
import pandas as pd
from src.bio_scraper import is_good_bio


_SOURCE_TAG = re.compile(r"^\[(.*?)\]\s*")

def bio_snippet(raw_bio: str | None, max_chars: int = 120) -> str:
    """Return first sentence of bio (≤ max_chars), source tag stripped."""
    if not raw_bio:
        return ""
    text = _SOURCE_TAG.sub("", raw_bio).strip()
    # Try to cut at first sentence boundary
    dot = text.find(". ")
    if 0 < dot < max_chars:
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


def show_followups(crm):
    """Display upcoming and overdue follow-ups."""
    st.title("📅 Follow-up Reminders")

    try:
        with crm.get_connection() as conn:
            query = """
            SELECT
                i.id,
                i.foundation_id,
                f.name as foundation_name,
                f.city,
                f.website,
                i.interaction_date,
                i.interaction_type,
                i.contact_person,
                i.subject,
                i.notes,
                i.follow_up_date,
                i.status,
                julianday(i.follow_up_date) - julianday('now') as days_until_due
            FROM interactions i
            LEFT JOIN foundations f ON i.foundation_id = f.id
            WHERE i.follow_up_date IS NOT NULL
            ORDER BY i.follow_up_date
            """
            df = pd.read_sql_query(query, conn)

            if len(df) == 0:
                st.info("No follow-ups scheduled.")
                return

            overdue  = df[df['days_until_due'] < 0]
            upcoming = df[df['days_until_due'] >= 0]

            if len(overdue) > 0:
                st.subheader(f"🔴 Overdue ({len(overdue)} items)")
                for row in overdue.itertuples(index=False):
                    days_overdue = int(abs(row.days_until_due))
                    st.warning(f"**{row.foundation_name}** ({row.city}) — {row.interaction_type.title()} with {row.contact_person}")
                    st.write(f"• Due: {row.follow_up_date} ({days_overdue} days overdue)")
                    st.write(f"• Subject: {row.subject[:100] if row.subject else 'N/A'}...")
                    if row.notes:
                        st.write(f"• Notes: {row.notes[:150]}...")
                    if row.website:
                        st.write(f"• [Visit Website]({row.website})")
                    st.divider()

            upcoming_30 = upcoming[upcoming['days_until_due'] <= 30]
            if len(upcoming_30) > 0:
                st.subheader(f"🟡 Upcoming — Next 30 Days ({len(upcoming_30)} items)")
                for row in upcoming_30.itertuples(index=False):
                    days_until = int(row.days_until_due)
                    st.success(f"**{row.foundation_name}** ({row.city}) — {row.interaction_type.title()}")
                    st.write(f"• Due: {row.follow_up_date} ({days_until} days)")
                    st.write(f"• Contact: {row.contact_person}")
                    st.write(f"• Subject: {row.subject[:100] if row.subject else 'N/A'}...")
                    if row.website:
                        st.write(f"• [Visit Website]({row.website})")
                    st.divider()

            col1, col2, col3 = st.columns(3)
            col1.metric("Total Follow-ups", len(df))
            col2.metric("Overdue", len(overdue))
            col3.metric("Upcoming (30 days)", len(upcoming_30))

    except Exception as e:
        st.error(f"Error loading follow-ups: {e}")


def show_compliance(crm):
    """Display compliance and payout rate tracking."""
    st.title("📊 Compliance & Payout Tracking")

    try:
        with crm.get_connection() as conn:
            query = """
            SELECT
                f.id,
                f.name,
                f.city,
                f.investment_assets,
                f.annual_grants,
                CASE
                    WHEN f.investment_assets > 0
                    THEN (f.annual_grants * 1.0 / f.investment_assets) * 100
                    ELSE 0
                END as payout_rate
            FROM foundations f
            WHERE f.investment_assets IS NOT NULL AND f.investment_assets > 0
            ORDER BY payout_rate ASC
            """
            df = pd.read_sql_query(query, conn)

            if len(df) == 0:
                st.info("No foundation data available.")
                return

            compliant     = df[df['payout_rate'] >= 5.0]
            non_compliant = df[df['payout_rate'] < 5.0]

            col1, col2, col3 = st.columns(3)
            col1.metric("Total Foundations", len(df))
            col2.metric("Compliant (≥5%)", f"{len(compliant)} ({len(compliant)*100//len(df)}%)")
            col3.metric("Non-Compliant (<5%)", len(non_compliant))

            if len(non_compliant) > 0:
                st.subheader(f"🔴 Below 5% Payout Rate ({len(non_compliant)} foundations)")
                st.warning("Private foundations must distribute at least 5% of investment assets annually (IRS requirement).")
                disp = non_compliant[['name', 'city', 'investment_assets', 'annual_grants', 'payout_rate']].copy()
                disp['investment_assets'] = disp['investment_assets'].apply(lambda x: f"${x/1e6:.1f}M")
                disp['annual_grants']     = disp['annual_grants'].apply(lambda x: f"${x/1e6:.1f}M" if pd.notna(x) else "N/A")
                disp['payout_rate']       = disp['payout_rate'].apply(lambda x: f"{x:.2f}%")
                st.dataframe(disp, use_container_width=True)

            if len(compliant) > 0:
                st.subheader(f"🟢 Compliant Foundations ({len(compliant)} foundations)")
                disp = compliant[['name', 'city', 'investment_assets', 'annual_grants', 'payout_rate']].copy()
                disp['investment_assets'] = disp['investment_assets'].apply(lambda x: f"${x/1e6:.1f}M")
                disp['annual_grants']     = disp['annual_grants'].apply(lambda x: f"${x/1e6:.1f}M" if pd.notna(x) else "N/A")
                disp['payout_rate']       = disp['payout_rate'].apply(lambda x: f"{x:.2f}%")
                st.dataframe(disp.head(20), use_container_width=True)
                if len(compliant) > 20:
                    st.info(f"Showing 20 of {len(compliant)} compliant foundations.")

    except Exception as e:
        st.error(f"Error loading compliance data: {e}")


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

    # _has_bio: any non-empty bio text (used for metrics/filter coverage)
    # is_good_bio: passes quality heuristics (used for badge and rendering)
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
        raw_bio   = row.bio or row.notes or ""
        clean_bio = _SOURCE_TAG.sub("", str(raw_bio)).strip() if raw_bio else ""
        has_bio   = bool(clean_bio) and is_good_bio(clean_bio, row.name)

        snippet = bio_snippet(raw_bio) if has_bio else ""
        source  = bio_source_label(raw_bio) if has_bio else ""

        badge  = "✓ Bio" if has_bio else "✗ No bio"
        header = f"{badge} | {row.name}"
        if row.title:
            header += f" — {row.title}"
        if row.foundation_name:
            header += f" · {row.foundation_name}"

        with st.expander(header, expanded=False):
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
                        st.markdown(f"<small style='color:grey'>{label}</small><br>{html.escape(value)}", unsafe_allow_html=True)
                if row.linkedin_url:
                    with cols[len(contact_parts)]:
                        st.markdown(f"<small style='color:grey'>LinkedIn</small>", unsafe_allow_html=True)
                        st.markdown(f"[🔗 Profile]({html.escape(row.linkedin_url)})")
                st.divider()

            if has_bio:
                st.markdown(
                    f"<div style='border-left:3px solid #89b4fa;padding:8px 12px;"
                    f"background:#181825;border-radius:0 4px 4px 0;line-height:1.7'>"
                    f"{html.escape(clean_bio)}</div>",
                    unsafe_allow_html=True,
                )
                if source:
                    st.caption(f"Source: {source}")
