import re
import streamlit as st
import pandas as pd
from src.bio_scraper import is_good_bio


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
            query = """
            SELECT
                coi.id,
                coi.name,
                coi.title,
                coi.role,
                coi.employer,
                coi.employer_city,
                coi.employer_state,
                coi.linkedin_url,
                coi.bio,
                coi.notes,
                coi.email,
                coi.phone,
                f.name  AS foundation_name,
                f.city  AS foundation_city
            FROM centers_of_influence coi
            LEFT JOIN foundations f ON coi.foundation_id = f.id
            ORDER BY coi.name
            """
            df = pd.read_sql_query(query, conn)

        if len(df) == 0:
            st.info("No centers of influence recorded.")
            return

        # ── Coverage metrics ─────────────────────────────────────────────────
        total        = len(df)
        with_bio     = int(df['bio'].notna().sum() - (df['bio'] == '').sum())
        with_linkedin = int(df['linkedin_url'].notna().sum())

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Contacts", total)
        col2.metric("With Bio", f"{with_bio} ({with_bio * 100 // total}%)")
        col3.metric("With LinkedIn", f"{with_linkedin} ({with_linkedin * 100 // total}%)")

        st.divider()

        # ── Filters ───────────────────────────────────────────────────────────
        col_f, col_s, col_b = st.columns([2, 2, 1])

        fnd_options = ["All foundations"] + sorted(
            df['foundation_name'].dropna().unique().tolist()
        )
        selected_fnd = col_f.selectbox("Filter by foundation", fnd_options)
        search_name  = col_s.text_input("Search by name", placeholder="Type a name...")
        only_no_bio  = col_b.checkbox("Missing bio only")

        filtered = df.copy()
        if selected_fnd != "All foundations":
            filtered = filtered[filtered['foundation_name'] == selected_fnd]
        if search_name:
            filtered = filtered[filtered['name'].str.contains(search_name, case=False, na=False)]
        if only_no_bio:
            filtered = filtered[filtered['bio'].isna() | (filtered['bio'] == '')]

        st.caption(f"Showing {len(filtered)} of {total} contacts")

        # ── Contact cards ─────────────────────────────────────────────────────
        for row in filtered.itertuples(index=False):
            bio_raw = row.bio or row.notes or ""
            # Strip scraper source tag: "[fnd:example.org] actual bio text"
            bio_clean = re.sub(r"^\[.*?\]\s*", "", str(bio_raw)).strip() if bio_raw else ""

            has_bio = bool(bio_clean) and is_good_bio(bio_clean, row.name)
            label   = f"{'✅' if has_bio else '❌'} {row.name}"
            if row.title:
                label += f" — {row.title}"
            if row.foundation_name:
                label += f" | {row.foundation_name}"

            with st.expander(label):
                # Contact details
                detail_cols = st.columns(2)
                with detail_cols[0]:
                    if row.employer:
                        loc = ", ".join(filter(None, [row.employer_city, row.employer_state]))
                        st.write(f"**Employer:** {row.employer}" + (f", {loc}" if loc else ""))
                    if row.role and row.role != row.title:
                        st.write(f"**Role:** {row.role}")
                    if row.email:
                        st.write(f"**Email:** {row.email}")
                    if row.phone:
                        st.write(f"**Phone:** {row.phone}")
                with detail_cols[1]:
                    if row.linkedin_url:
                        st.markdown(f"[🔗 LinkedIn Profile]({row.linkedin_url})")
                    if row.foundation_city:
                        st.write(f"**Foundation city:** {row.foundation_city}")

                # Bio
                st.markdown("---")
                if bio_clean and is_good_bio(bio_clean, row.name):
                    st.markdown("**Bio**")
                    st.write(bio_clean)
                    source_match = re.match(r"^\[(.*?)\]", str(bio_raw))
                    if source_match:
                        st.caption(f"Source: {source_match.group(1)}")
                else:
                    st.caption("No bio available yet.")

    except Exception as e:
        st.error(f"Error loading centers of influence: {e}")
