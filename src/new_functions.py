def show_followups(crm):
    """Display upcoming and overdue follow-ups."""
    st.title("📅 Follow-up Reminders")
    
    try:
        with crm.get_connection() as conn:
            # Get all interactions with follow-up dates
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
            
            # Separate by status
            overdue = df[df['days_until_due'] < 0]
            upcoming = df[df['days_until_due'] >= 0]
            
            # Overdue follow-ups
            if len(overdue) > 0:
                st.subheader(f"🔴 Overdue ({len(overdue)} items)")
                
                for row in overdue.itertuples(index=False):
                    days_overdue = int(abs(row.days_until_due))
                    st.warning(f"**{row.foundation_name}** ({row.city}) - {row.interaction_type.title()} with {row.contact_person}")
                    st.write(f"• Due: {row.follow_up_date} ({days_overdue} days overdue)")
                    st.write(f"• Subject: {row.subject[:100] if row.subject else 'N/A'}...")
                    if row.notes:
                        st.write(f"• Notes: {row.notes[:150]}...")
                    if row.website:
                        st.write(f"• [Visit Website]({row.website})")
                    st.divider()
            
            # Upcoming follow-ups (next 30 days)
            upcoming_30 = upcoming[upcoming['days_until_due'] <= 30]
            if len(upcoming_30) > 0:
                st.subheader(f"🟡 Upcoming (Next 30 Days - {len(upcoming_30)} items)")
                
                for row in upcoming_30.itertuples(index=False):
                    days_until = int(row.days_until_due)
                    st.success(f"**{row.foundation_name}** ({row.city}) - {row.interaction_type.title()}")
                    st.write(f"• Due: {row.follow_up_date} ({days_until} days)")
                    st.write(f"• Contact: {row.contact_person}")
                    st.write(f"• Subject: {row.subject[:100] if row.subject else 'N/A'}...")
                    if row.website:
                        st.write(f"• [Visit Website]({row.website})")
                    st.divider()
            
            # Summary stats
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Follow-ups", f"{len(df)}")
            with col2:
                st.metric("Overdue", f"{len(overdue)}", delta="⚠️" if len(overdue) > 0 else None)
            with col3:
                st.metric("Upcoming (30 days)", f"{len(upcoming_30)}")
    
    except Exception as e:
        st.error(f"Error loading follow-ups: {e}")


def show_compliance(crm):
    """Display compliance and payout rate tracking."""
    st.title("📊 Compliance & Payout Tracking")
    
    try:
        with crm.get_connection() as conn:
            # Get payout rates for all foundations
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
            
            # Separate by compliance status
            compliant = df[df['payout_rate'] >= 5.0]
            non_compliant = df[df['payout_rate'] < 5.0]
            
            # Summary metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Foundations", f"{len(df)}")
            with col2:
                st.metric("Compliant (≥5%)", f"{len(compliant)}", delta=f"{len(compliant)*100/len(df):.1f}%")
            with col3:
                st.metric("Non-Compliant (<5%)", f"{len(non_compliant)}", delta="⚠️" if len(non_compliant) > 0 else None)
            
            # Non-compliant foundations (below 5%)
            if len(non_compliant) > 0:
                st.subheader(f"🔴 Below 5% Payout Rate ({len(non_compliant)} foundations)")
                st.warning("Private foundations must distribute at least 5% of investment assets annually (IRS requirement)")
                
                display_df = non_compliant[['name', 'city', 'investment_assets', 'annual_grants', 'payout_rate']].copy()
                display_df['investment_assets'] = display_df['investment_assets'].apply(lambda x: f"${x/1e6:.1f}M")
                display_df['annual_grants'] = display_df['annual_grants'].apply(lambda x: f"${x/1e6:.1f}M" if pd.notna(x) else "N/A")
                display_df['payout_rate'] = display_df['payout_rate'].apply(lambda x: f"{x:.2f}%")
                
                st.dataframe(display_df, use_container_width=True)
            
            # Compliant foundations
            if len(compliant) > 0:
                st.subheader(f"🟢 Compliant Foundations ({len(compliant)} foundations)")
                
                display_df = compliant[['name', 'city', 'investment_assets', 'annual_grants', 'payout_rate']].copy()
                display_df['investment_assets'] = display_df['investment_assets'].apply(lambda x: f"${x/1e6:.1f}M")
                display_df['annual_grants'] = display_df['annual_grants'].apply(lambda x: f"${x/1e6:.1f}M" if pd.notna(x) else "N/A")
                display_df['payout_rate'] = display_df['payout_rate'].apply(lambda x: f"{x:.2f}%")
                
                st.dataframe(display_df.head(20), use_container_width=True)
                if len(compliant) > 20:
                    st.info(f"Showing 20 of {len(compliant)} compliant foundations")
    
    except Exception as e:
        st.error(f"Error loading compliance data: {e}")


def show_centers_of_influence(crm):
    """Display centers of influence - board members for introductions."""
    st.title("👥 Centers of Influence")
    st.markdown("Board members and officers who can make introductions to other foundations")
    
    try:
        with crm.get_connection() as conn:
            # Get centers of influence with foundation info
            query = """
            SELECT 
                coi.id,
                coi.name,
                coi.title,
                coi.location,
                coi.linkedin_url,
                coi.notes,
                f.name as foundation_name,
                f.city as foundation_city
            FROM centers_of_influence coi
            LEFT JOIN foundations f ON coi.foundation_id = f.id
            ORDER BY coi.name
            """
            
            df = pd.read_sql_query(query, conn)
            
            if len(df) == 0:
                st.info("No centers of influence recorded. Add board member data to start building your network map.")
                return
            
            # Summary
            st.metric("Total Contacts", f"{len(df)}")
            
            # Search
            search_name = st.text_input("Search by name...", placeholder="Enter name to filter...")
            
            if search_name:
                df = df[df['name'].str.contains(search_name, case=False, na=False)]
            
            # Display contacts
            for row in df.itertuples(index=False):
                st.markdown(f"**{row.name}** - {row.title}")
                st.write(f"• Foundation: {row.foundation_name} ({row.foundation_city})")
                st.write(f"• Location: {row.location if row.location else 'N/A'}")
                if row.linkedin_url:
                    st.write(f"• [LinkedIn Profile]({row.linkedin_url})")
                if row.notes:
                    st.write(f"• Notes: {row.notes}")
                st.divider()
    
    except Exception as e:
        st.error(f"Error loading centers of influence: {e}")
