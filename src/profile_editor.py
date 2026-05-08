#!/usr/bin/env python3
"""
Profile Editor for Personnel Profiles
Manual data entry for biographical information
"""

import streamlit as st
import sqlite3
from datetime import datetime

def get_personnel_list(crm):
    """Get list of personnel with foundation info"""
    conn = crm
    cursor = conn.cursor()
    
    query = """
    SELECT 
        p.id, p.name, p.title,
        f.name as foundation_name, f.city,
        pp.id as profile_id, pp.confidence_score,
        pp.bio_summary
    FROM personnel_990 p
    LEFT JOIN foundations f ON p.foundation_id = f.id
    LEFT JOIN personnel_profiles pp ON p.id = pp.personnel_id
    WHERE p.name IS NOT NULL
    ORDER BY f.name, p.name
    """
    
    cursor.execute(query)
    return cursor.fetchall()


def get_profile_data(crm, personnel_id):
    """Get existing profile data for a personnel"""
    conn = crm
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM personnel_profiles WHERE personnel_id = ?
    """, (personnel_id,))
    
    columns = [desc[0] for desc in cursor.description]
    row = cursor.fetchone()
    
    if row:
        return dict(zip(columns, row))
    return None


def save_profile(crm, profile_data):
    """Save or update profile in database"""
    conn = crm
    cursor = conn.cursor()
    
    # Check if profile exists
    cursor.execute("""
        SELECT id FROM personnel_profiles WHERE personnel_id = ?
    """, (profile_data['personnel_id'],))
    
    existing = cursor.fetchone()
    
    if existing:
        # Update existing
        cursor.execute("""
            UPDATE personnel_profiles SET
                bio_summary = ?,
                career_history = ?,
                education = ?,
                news_mentions = ?,
                data_sources = ?,
                last_updated = ?,
                confidence_score = ?,
                website_status = ?,
                linkedin_status = ?,
                news_status = ?
            WHERE personnel_id = ?
        """, (
            profile_data['bio_summary'],
            profile_data['career_history'],
            profile_data['education'],
            profile_data['news_mentions'],
            profile_data['data_sources'],
            profile_data['last_updated'],
            profile_data['confidence_score'],
            profile_data['website_status'],
            profile_data['linkedin_status'],
            profile_data['news_status'],
            profile_data['personnel_id']
        ))
    else:
        # Insert new
        cursor.execute("""
            INSERT INTO personnel_profiles (
                personnel_id, bio_summary, career_history, education,
                news_mentions, data_sources, last_updated, confidence_score,
                website_status, linkedin_status, news_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            profile_data['personnel_id'],
            profile_data['bio_summary'],
            profile_data['career_history'],
            profile_data['education'],
            profile_data['news_mentions'],
            profile_data['data_sources'],
            profile_data['last_updated'],
            profile_data['confidence_score'],
            profile_data['website_status'],
            profile_data['linkedin_status'],
            profile_data['news_status']
        ))
    
    conn.commit()


def show_profile_dashboard(crm):
    """Show dashboard of all profiles"""
    st.header("📊 Personnel Profiles Dashboard")
    
    personnel = get_personnel_list(crm)
    
    # Stats
    total = len(personnel)
    with_profiles = sum(1 for p in personnel if p[6] is not None)  # profile_id exists
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Personnel", total)
    with col2:
        st.metric("With Profiles", with_profiles)
    with col3:
        st.metric("Coverage", f"{with_profiles/total:.1%}" if total > 0 else "0%")
    
    st.divider()
    
    # Filter options
    col1, col2 = st.columns(2)
    with col1:
        search = st.text_input("🔍 Search by name")
    with col2:
        filter_status = st.selectbox(
            "Filter by status",
            ["All", "Has Profile", "No Profile"]
        )
    
    # Table
    st.subheader("Personnel List")
    
    for row in personnel:
        pid, name, title, foundation, city, profile_id, confidence, bio = row
        
        # Apply filters
        if search and search.lower() not in name.lower():
            continue
        if filter_status == "Has Profile" and profile_id is None:
            continue
        if filter_status == "No Profile" and profile_id is not None:
            continue
        
        with st.expander(f"{name} - {foundation}"):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**Title:** {title}")
                st.write(f"**City:** {city}")
            with col2:
                if profile_id:
                    st.write(f"**Confidence:** {confidence:.1f}/1.0")
                    if bio:
                        st.write(f"**Bio preview:** {bio[:100]}...")
                else:
                    st.write("**Status:** No profile")
            with col3:
                if st.button("📝 Edit", key=f"edit_{pid}"):
                    st.session_state['editing_personnel_id'] = pid


def show_profile_editor(crm, personnel_id):
    """Show form to edit a personnel profile"""
    st.header("✏️ Edit Profile")
    
    # Get personnel info
    cursor = crm.cursor()
    cursor.execute("""
        SELECT p.id, p.name, p.title, f.name, f.website, f.city, p.linkedin_url
        FROM personnel_990 p
        LEFT JOIN foundations f ON p.foundation_id = f.id
        WHERE p.id = ?
    """, (personnel_id,))
    row = cursor.fetchone()
    
    if not row:
        st.error("Personnel not found")
        return
    
    pid, name, title, foundation, website, city, linkedin = row
    
    st.write(f"**{name}** - {title}")
    st.write(f"Foundation: {foundation} ({city})")
    if website:
        st.write(f"Website: [{website}]({website})")
    if linkedin:
        st.write(f"LinkedIn: [{linkedin}]({linkedin})")
    
    # Get existing profile data
    existing = get_profile_data(crm, pid)
    
    with st.form("profile_form"):
        st.subheader("📝 Biographical Summary")
        bio_summary = st.text_area(
            "Bio Summary",
            value=existing['bio_summary'] if existing and existing['bio_summary'] else "",
            height=200,
            placeholder="Enter biographical information..."
        )
        
        st.subheader("💼 Career History")
        career_history = st.text_area(
            "Career History",
            value=existing['career_history'] if existing and existing['career_history'] else "",
            height=200,
            placeholder="List previous positions, companies, dates..."
        )
        
        st.subheader("🎓 Education")
        education = st.text_area(
            "Education",
            value=existing['education'] if existing and existing['education'] else "",
            height=100,
            placeholder="Degrees, institutions, years..."
        )
        
        st.subheader("📰 News Mentions")
        news_mentions = st.text_area(
            "News Mentions",
            value=existing['news_mentions'] if existing and existing['news_mentions'] else "",
            height=150,
            placeholder="- Article title: Brief description\n- Another article..."
        )
        
        st.subheader("🔗 Data Sources")
        sources = st.multiselect(
            "Data Sources",
            options=["website", "linkedin", "news", "manual_entry", "other"],
            default=existing['data_sources'].split(', ') if existing and existing['data_sources'] else []
        )
        
        st.subheader("📊 Confidence Score")
        confidence = st.slider(
            "Confidence (0-1)",
            0.0, 1.0,
            value=existing['confidence_score'] if existing and existing['confidence_score'] else 0.5,
            step=0.1
        )
        
        # Status fields
        col1, col2, col3 = st.columns(3)
        with col1:
            website_status = st.selectbox(
                "Website Status",
                ["pending", "success", "blocked", "not_found"],
                index=["pending", "success", "blocked", "not_found"].index(existing['website_status']) if existing else 0
            )
        with col2:
            linkedin_status = st.selectbox(
                "LinkedIn Status",
                ["pending", "success", "blocked", "not_found"],
                index=["pending", "success", "blocked", "not_found"].index(existing['linkedin_status']) if existing else 0
            )
        with col3:
            news_status = st.selectbox(
                "News Status",
                ["pending", "success", "not_found", "error"],
                index=["pending", "success", "not_found", "error"].index(existing['news_status']) if existing else 0
            )
        
        submitted = st.form_submit_button("💾 Save Profile")
        
        if submitted:
            profile_data = {
                'personnel_id': pid,
                'bio_summary': bio_summary if bio_summary else None,
                'career_history': career_history if career_history else None,
                'education': education if education else None,
                'news_mentions': news_mentions if news_mentions else None,
                'data_sources': ', '.join(sources) if sources else None,
                'last_updated': datetime.now().isoformat(),
                'confidence_score': confidence,
                'website_status': website_status,
                'linkedin_status': linkedin_status,
                'news_status': news_status
            }
            
            save_profile(crm, profile_data)
            st.success("✅ Profile saved!")
            
            # Clear editing state
            if 'editing_personnel_id' in st.session_state:
                del st.session_state['editing_personnel_id']


def show_personnel_profiles(crm):
    """Main function to show personnel profiles page"""
    
    # Check if editing a profile
    if 'editing_personnel_id' in st.session_state:
        show_profile_editor(crm, st.session_state['editing_personnel_id'])
    else:
        show_profile_dashboard(crm)
