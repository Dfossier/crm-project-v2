import re
import time
import streamlit as st
import pandas as pd
import requests
from urllib.parse import quote
from datetime import date, datetime, timedelta
from streamlit_calendar import calendar as st_calendar

# Colour per interaction type
_TYPE_COLOR = {
    "call":     "#4338ca",   # deep indigo
    "email":    "#1d4ed8",   # strong blue
    "meeting":  "#047857",   # deep emerald
    "proposal": "#b45309",   # dark amber
    "grant":    "#be185d",   # deep pink
    "research": "#6d28d9",   # deep violet
    "other":    "#475569",   # slate
}

_CALENDAR_OPTIONS = {
    "editable": False,
    "selectable": True,
    "headerToolbar": {
        "left":   "prev,next today",
        "center": "title",
        "right":  "dayGridMonth,timeGridWeek,listMonth",
    },
    "initialView": "dayGridMonth",
    "height": 680,
    "eventDisplay": "block",
    "dayMaxEvents": 3,
    "nowIndicator": True,
    "weekNumbers": False,
    "buttonText": {"today": "Today", "month": "Month", "week": "Week", "list": "List"},
    "eventTimeFormat": {"hour": "numeric", "minute": "2-digit", "meridiem": "short"},
}

_CALENDAR_CSS = """
    /* Toolbar */
    .fc-toolbar { padding: 4px 0 14px 0 !important; }
    .fc-toolbar-title { font-size: 1.1rem !important; font-weight: 800 !important;
                        letter-spacing: -0.02em; color: #0f172a !important; }
    .fc-button-primary {
        background: #4f46e5 !important; border-color: #4338ca !important;
        font-size: 11.5px !important; padding: 5px 14px !important;
        border-radius: 7px !important; font-weight: 600 !important;
        color: #fff !important; letter-spacing: 0.01em;
    }
    .fc-button-primary:hover  { background: #4338ca !important; border-color: #3730a3 !important; }
    .fc-button-primary:not(:disabled):active,
    .fc-button-active         { background: #312e81 !important; border-color: #312e81 !important; }

    /* Column headers */
    .fc-col-header-cell {
        font-size: 10.5px !important; font-weight: 700 !important;
        text-transform: uppercase; letter-spacing: 0.08em;
        color: #1e293b !important; background: #f1f5f9 !important;
        padding: 8px 0 !important; border-bottom: 2px solid #e2e8f0 !important;
    }

    /* Day cells */
    .fc-daygrid-day-number {
        font-size: 13px !important; font-weight: 600 !important;
        padding: 5px 8px !important; color: #1e293b !important;
    }
    .fc-day-other .fc-daygrid-day-number { color: #cbd5e1 !important; }
    .fc-day-today {
        background: #4f46e5 !important;
        box-shadow: inset 0 3px 0 0 #312e81 !important;
    }
    .fc-day-today .fc-daygrid-day-number {
        background: #fff !important; color: #4f46e5 !important;
        font-weight: 900 !important; font-size: 12.5px !important;
        border-radius: 50% !important;
        width: 28px !important; height: 28px !important; line-height: 28px !important;
        text-align: center !important; padding: 0 !important;
        margin: 4px 6px !important;
        display: inline-block !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.25) !important;
        letter-spacing: -0.01em !important;
    }
    .fc-day-today .fc-daygrid-event { opacity: 0.95 !important; }
    .fc-daygrid-day-frame { min-height: 80px !important; }
    .fc-daygrid-day { border-color: #e2e8f0 !important; }

    /* Events */
    .fc-event {
        border-radius: 5px !important; font-size: 11px !important;
        padding: 2px 7px !important; border: none !important;
        font-weight: 600 !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.18) !important;
        opacity: 1 !important;
    }
    .fc-event .fc-event-title { color: #fff !important; text-shadow: 0 1px 1px rgba(0,0,0,0.2); }
    .fc-event:hover { filter: brightness(0.92); cursor: pointer; }
    .fc-daygrid-dot-event:hover { background: rgba(99,102,241,0.12) !important; }

    /* More-link */
    .fc-daygrid-more-link { font-size: 11px !important; font-weight: 600 !important;
                             color: #4f46e5 !important; }

    /* List view */
    .fc-list-event-title  { font-size: 12.5px !important; font-weight: 500 !important; }
    .fc-list-event:hover td { background: #f1f5f9 !important; }
    .fc-list-day-cushion  { background: #f1f5f9 !important; font-weight: 700 !important;
                             color: #0f172a !important; font-size: 12px !important; }
    .fc-list-day-text, .fc-list-day-side-text { color: #0f172a !important; }

    /* General border cleanup */
    .fc-scrollgrid { border-color: #e2e8f0 !important; }
    .fc-scrollgrid td, .fc-scrollgrid th { border-color: #e2e8f0 !important; }
"""


def show_followups(crm):
    """Follow-up reminders with a live monthly calendar."""
    st.title("Follow-up Reminders")

    # ── Load all follow-up interactions ──────────────────────────────────────
    try:
        with crm.get_connection() as conn:
            df = pd.read_sql_query(
                """
                SELECT i.id, f.name AS foundation_name, f.city, f.website,
                       i.interaction_type, i.contact_person, i.subject, i.notes,
                       i.follow_up_date,
                       julianday(i.follow_up_date) - julianday('now') AS days_until_due
                FROM interactions i
                LEFT JOIN foundations f ON i.foundation_id = f.id
                WHERE i.follow_up_date IS NOT NULL
                ORDER BY i.follow_up_date
                """,
                conn,
            )
    except Exception as e:
        st.error(f"Error loading follow-ups: {e}")
        return

    # ── KPIs ─────────────────────────────────────────────────────────────────
    overdue    = df[df["days_until_due"] < 0]
    upcoming30 = df[(df["days_until_due"] >= 0) & (df["days_until_due"] <= 30)]
    future     = df[df["days_until_due"] > 30]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Scheduled", len(df))
    k2.metric("Overdue",        len(overdue),    delta=f"{len(overdue)} past due" if len(overdue) else None, delta_color="inverse")
    k3.metric("Due This Month",  len(upcoming30))
    k4.metric("Future",          len(future))
    st.divider()

    # ── Build calendar events ─────────────────────────────────────────────────
    events = []
    for _, row in df.iterrows():
        if not row["follow_up_date"]:
            continue
        itype  = str(row["interaction_type"] or "other").lower()
        color  = _TYPE_COLOR.get(itype, _TYPE_COLOR["other"])
        title  = row["foundation_name"] or "Follow-up"
        if row["contact_person"] and pd.notna(row["contact_person"]):
            title += f" · {row['contact_person']}"
        events.append({
            "title": title,
            "start": str(row["follow_up_date"])[:10],
            "color": color,
            "extendedProps": {
                "type":    itype.title(),
                "subject": str(row["subject"] or ""),
                "notes":   str(row["notes"] or ""),
            },
        })

    # ── Calendar ──────────────────────────────────────────────────────────────
    if not events:
        st.info("No follow-ups scheduled yet. Add interactions with a follow-up date via Add Interaction.")
    else:
        result = st_calendar(
            events=events,
            options=_CALENDAR_OPTIONS,
            custom_css=_CALENDAR_CSS,
            key="followup_cal",
        )

        # ── Clicked event detail ──
        clicked = (result or {}).get("eventClick", {}).get("event", {})
        if clicked:
            props = clicked.get("extendedProps", {})
            itype = props.get("type", "")
            color = _TYPE_COLOR.get(itype.lower(), "#94a3b8")
            st.markdown(
                f"""<div style="border-left:4px solid {color};background:rgba(99,102,241,0.04);
                    padding:12px 16px;border-radius:0 8px 8px 0;margin:12px 0;">
                    <div style="font-weight:600;font-size:14px">{clicked.get('title','')}</div>
                    <div style="color:#6b7280;font-size:12px;margin:2px 0 6px">
                        {clicked.get('start','')[:10]} &nbsp;·&nbsp; {itype}
                    </div>
                    {"<div style='font-size:13px'>" + props.get('subject','') + "</div>" if props.get('subject') else ""}
                    {"<div style='font-size:12px;color:#6b7280;margin-top:4px'>" + props.get('notes','')[:200] + "</div>" if props.get('notes') else ""}
                </div>""",
                unsafe_allow_html=True,
            )

    # ── Overdue strip ────────────────────────────────────────────────────────
    if not overdue.empty:
        st.divider()
        st.markdown(f"**Overdue &nbsp;·&nbsp; {len(overdue)} items**")
        for _, row in overdue.sort_values("days_until_due").iterrows():
            days  = int(abs(row["days_until_due"]))
            itype = str(row["interaction_type"] or "other").lower()
            color = _TYPE_COLOR.get(itype, "#94a3b8")
            subj  = str(row["subject"] or "")
            st.markdown(
                f"""<div style="display:flex;align-items:center;justify-content:space-between;
                    padding:10px 14px;border-radius:8px;margin-bottom:6px;
                    background:rgba(239,68,68,0.04);border:1px solid rgba(239,68,68,0.15);">
                    <div>
                        <span style="display:inline-block;width:8px;height:8px;border-radius:50%;
                            background:{color};margin-right:8px;"></span>
                        <strong>{row['foundation_name']}</strong>
                        <span style="color:#6b7280;font-size:12px;margin-left:8px">{itype.title()}</span>
                        {"<div style='font-size:12px;color:#6b7280;padding-left:16px'>" + subj[:100] + "</div>" if subj else ""}
                    </div>
                    <div style="text-align:right;white-space:nowrap;margin-left:12px">
                        <div style="color:#ef4444;font-weight:600;font-size:12px">{str(row['follow_up_date'])[:10]}</div>
                        <div style="color:#ef4444;font-size:11px">{days}d overdue</div>
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )


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


def _scrape_li_photo(linkedin_url: str) -> str | None:
    """
    Try multiple crawlers/UAs to extract a profile photo from a public LinkedIn page.
    LinkedIn serves full HTML to search-engine bots even when blocking browsers.
    """
    if not linkedin_url:
        return None

    user_agents = [
        # Search-engine bots — LinkedIn serves them full HTML for SEO
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
        "Twitterbot/1.0",
        # Regular browser as last resort
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
    ]

    for ua in user_agents:
        try:
            r = requests.get(
                linkedin_url,
                timeout=10,
                headers={
                    "User-Agent": ua,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                },
                allow_redirects=True,
            )
            if r.status_code != 200:
                continue

            html = r.text

            # 1. og:image meta tag (two attribute orderings)
            for pat in (
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            ):
                m = re.search(pat, html)
                if m:
                    url = m.group(1)
                    if "licdn.com/dms" in url and "static" not in url and "ghost" not in url:
                        return url

            # 2. JSON-LD schema — often has "image" with the CDN URL
            m = re.search(r'"image"\s*:\s*"(https://media\.licdn\.com[^"]+)"', html)
            if m:
                return m.group(1)

            # 3. data-delayed-url / src patterns on profile-photo img tags
            m = re.search(
                r'(?:data-delayed-url|src)=["\']'
                r'(https://media\.licdn\.com/dms/image/[^"\']+)["\']',
                html,
            )
            if m:
                return m.group(1)

        except Exception:
            continue

    return None


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_linkedin_photo(linkedin_url: str) -> str | None:
    return _scrape_li_photo(linkedin_url)


def _avatar_url(name: str, size: int = 80) -> str:
    """Colored initials avatar via ui-avatars.com — always works as a fallback."""
    initials = "+".join(p[0] for p in name.split() if p)[:2]
    return (
        f"https://ui-avatars.com/api/?name={quote(name)}"
        f"&size={size}&background=random&color=fff&bold=true&rounded=true"
    )


def _extract_linkedin_id(url: str) -> str | None:
    if not url:
        return None
    m = re.search(r'linkedin\.com/in/([^/?#\s]+)', url)
    return m.group(1).strip('/') if m else None


def _li_session(li_at: str, jsessionid: str):
    """Return a requests.Session pre-configured for LinkedIn's Voyager API."""
    s = requests.Session()
    s.max_redirects = 3  # fail fast instead of looping 30x

    csrf = jsessionid.strip('"')
    for domain in (".linkedin.com", "www.linkedin.com", "linkedin.com"):
        s.cookies.set("li_at",      li_at,      domain=domain, path="/")
        s.cookies.set("JSESSIONID", jsessionid, domain=domain, path="/")
        s.cookies.set("bcookie",    '"v=2&' + li_at[:8] + '"', domain=domain, path="/")

    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept":                       "application/vnd.linkedin.normalized+json+2.1",
        "Accept-Language":              "en-US,en;q=0.9",
        "Referer":                      "https://www.linkedin.com/feed/",
        "x-li-lang":                    "en_US",
        "x-restli-protocol-version":    "2.0.0",
        "csrf-token":                   csrf,
        "x-li-page-instance":           "urn:li:page:d_flagship3_profile_view_base;",
        "x-li-track":                   '{"clientVersion":"1.13.13174","osName":"web","timezoneOffset":-5,"timezone":"America/Chicago","deviceFormFactor":"DESKTOP","mpName":"voyager-web","displayDensity":1,"displayWidth":1920,"displayHeight":1080}',
    })
    return s


def _li_fetch_profile(session, public_id: str) -> dict:
    """
    Fetch a LinkedIn profile via the Voyager dash API.
    Returns a normalised dict with keys: headline, summary, locationName,
    photo_url, years_at_company, phone, email, _status, _raw_keys.
    """
    base = "https://www.linkedin.com/voyager/api/"

    try:
        r = session.get(
            base + "identity/dash/profiles",
            params={
                "q": "memberIdentity",
                "memberIdentity": public_id,
                "decorationId": "com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-93",
            },
            timeout=12,
        )
    except requests.exceptions.TooManyRedirects:
        return {"_status": 302, "_body": "Too many redirects — cookies are invalid or expired. Refresh linkedin.com and copy fresh li_at / JSESSIONID values."}
    except Exception as ex:
        return {"_status": 0, "_body": str(ex)}

    if r.status_code != 200:
        return {"_status": r.status_code, "_body": r.text[:400]}

    data = r.json()

    # The response has an "included" array of mixed typed objects
    profile   = {}
    positions = []
    for item in data.get("included") or []:
        t = item.get("$type", "")
        if not profile and "Profile" in t and "firstName" in item:
            profile = item
        elif "Position" in t or "Experience" in t:
            positions.append(item)

    if not profile:
        # Surface what came back so we can debug
        included_types = list({i.get("$type", "?") for i in (data.get("included") or [])})
        return {
            "_status": 200,
            "_body": f"No Profile object in included. Types present: {included_types}",
            "_raw_keys": list(data.keys()),
        }

    # ── core fields ───────────────────────────────────────────────────────────
    headline = profile.get("headline") or ""
    if isinstance(headline, dict):
        headline = headline.get("text", "")

    summary  = profile.get("summary") or ""
    location = profile.get("locationName") or ""

    # ── photo ─────────────────────────────────────────────────────────────────
    photo = None
    pp  = profile.get("profilePicture") or {}
    vec = ((pp.get("displayImageReference") or {}).get("vectorImage") or {})
    root = vec.get("rootUrl", "")
    arts = vec.get("artifacts") or []
    if root and arts:
        photo = root + arts[-1].get("fileIdentifyingUrlPathSegment", "")

    # ── years at current company ──────────────────────────────────────────────
    years = None
    for pos in positions:
        dr    = pos.get("dateRange") or {}
        start = dr.get("start") or pos.get("timePeriod", {}).get("startDate") or {}
        end   = dr.get("end")   or pos.get("timePeriod", {}).get("endDate")
        if not end and start.get("year"):
            yr = start["year"]; mo = start.get("month", 1)
            years = round((date.today() - date(yr, mo, 1)).days / 365.25, 1)
            break

    # ── contact info ──────────────────────────────────────────────────────────
    phone = email = None
    rc = session.get(
        base + f"identity/profiles/{public_id}/profileContactInfo", timeout=10
    )
    if rc.status_code == 200:
        ci    = rc.json()
        nums  = ci.get("phoneNumbers") or ci.get("phone_numbers") or []
        phone = nums[0].get("number") if nums else None
        email = ci.get("emailAddress") or ci.get("email_address") or None

    return {
        "headline":         headline or None,
        "summary":          summary or None,
        "locationName":     location or None,
        "photo_url":        photo,
        "years_at_company": years,
        "phone":            phone,
        "email":            email,
        "_status":          200,
        "_raw_keys":        list(data.keys()),
    }


def _write_li_result(crm, row_id: int, result: dict):
    """Write a _li_fetch_profile result dict back to the DB row."""
    parts = [
        "linkedin_headline=?", "linkedin_about=?",
        "linkedin_phone=?", "linkedin_email=?",
        "linkedin_years_at_company=?",
        "linkedin_scraped_at=datetime('now')",
    ]
    params = [
        result.get("headline"), result.get("summary"),
        result.get("phone"), result.get("email"),
        result.get("years_at_company"),
    ]
    if result.get("locationName"):
        parts.append("location=?"); params.append(result["locationName"])
    if result.get("photo_url"):
        parts.append("photo_url=?"); params.append(result["photo_url"])
    params.append(row_id)
    with crm.get_connection() as conn:
        conn.execute(f"UPDATE centers_of_influence SET {', '.join(parts)} WHERE id=?", params)
        conn.commit()


def show_centers_of_influence(crm):
    """Display centers of influence - board members for introductions."""
    st.title("Centers of Influence")
    st.markdown("Board members and officers who can make introductions to other foundations.")

    # ── DB migration: add scraped columns if not present ──────────────────────
    with crm.get_connection() as conn:
        for col in (
            "linkedin_headline TEXT",
            "linkedin_about TEXT",
            "linkedin_scraped_at TEXT",
            "linkedin_phone TEXT",
            "linkedin_email TEXT",
            "linkedin_years_at_company REAL",
            "birthday TEXT",
        ):
            try:
                conn.execute(f"ALTER TABLE centers_of_influence ADD COLUMN {col}")
            except Exception:
                pass
        conn.commit()

    # Load foundation list for the add form
    with crm.get_connection() as conn:
        foundations_df = pd.read_sql_query(
            "SELECT id, name, city FROM foundations ORDER BY name", conn
        )

    foundation_options = {
        f"{row['name']} ({row['city']})": row['id']
        for _, row in foundations_df.iterrows()
    }

    # ── Add contact form ──────────────────────────────────────────────────────
    with st.expander("Add / Edit Contact", expanded=False):
        with st.form("add_coi_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                contact_name = st.text_input("Full Name *")
                contact_title = st.text_input("Title / Role", placeholder="Board Chair, Trustee, CFO…")
                contact_location = st.text_input("Address", placeholder="New Orleans, LA")
            with c2:
                selected_foundation = st.selectbox(
                    "Associated Foundation *",
                    options=list(foundation_options.keys()),
                )
                linkedin = st.text_input("LinkedIn URL", placeholder="https://linkedin.com/in/…")
                photo_url = st.text_input("Photo URL (optional)", placeholder="Paste a direct image URL to override")
                birthday = st.date_input("Birthday", value=None, format="MM/DD/YYYY")
                notes = st.text_area("Notes", height=68, placeholder="Relationship context, best way to reach…")

            if st.form_submit_button("Save Contact"):
                if not contact_name.strip():
                    st.error("Name is required.")
                else:
                    fid = foundation_options[selected_foundation]
                    bday = birthday.strftime("%Y-%m-%d") if birthday else None
                    with crm.get_connection() as conn:
                        conn.execute(
                            """INSERT INTO centers_of_influence
                               (foundation_id, name, title, location, linkedin_url, photo_url, birthday, notes)
                               VALUES (?,?,?,?,?,?,?,?)""",
                            (fid, contact_name.strip(), contact_title.strip() or None,
                             contact_location.strip() or None,
                             linkedin.strip() or None,
                             photo_url.strip() or None,
                             bday,
                             notes.strip() or None),
                        )
                        conn.commit()
                    st.success(f"Added: {contact_name}")
                    st.rerun()

    # ── Grab Profile Photos (no auth needed) ─────────────────────────────────
    with st.expander("Grab Profile Photos", expanded=False):
        st.caption(
            "Scrapes the public LinkedIn profile page for each contact and saves their photo. "
            "No login required — works for publicly visible profiles."
        )
        pc1, pc2 = st.columns([2, 1])
        with pc1:
            overwrite_photos = st.checkbox("Overwrite existing photos", value=False, key="photo_overwrite")
        with pc2:
            pass

        if st.button("Grab All Photos", type="primary", key="grab_photos_btn"):
            with crm.get_connection() as conn:
                q = (
                    "SELECT id, name, linkedin_url FROM centers_of_influence "
                    "WHERE linkedin_url IS NOT NULL AND linkedin_url != ''"
                )
                if not overwrite_photos:
                    q += " AND (photo_url IS NULL OR photo_url = '')"
                rows = pd.read_sql_query(q, conn)

            if rows.empty:
                st.info("No contacts need photos (all already have one, or none have a LinkedIn URL).")
            else:
                prog = st.progress(0)
                status_ph = st.empty()
                saved, skipped = 0, 0

                for idx, row in rows.iterrows():
                    status_ph.text(f"Fetching photo for {row['name']} ({idx + 1}/{len(rows)})…")
                    photo = _scrape_li_photo(row["linkedin_url"])  # bypass cache
                    if photo:
                        with crm.get_connection() as conn:
                            conn.execute(
                                "UPDATE centers_of_influence SET photo_url=? WHERE id=?",
                                (photo, int(row["id"])),
                            )
                            conn.commit()
                        saved += 1
                    else:
                        skipped += 1
                    prog.progress((idx + 1) / len(rows))
                    time.sleep(0.5)

                status_ph.empty()
                prog.empty()
                st.success(f"Saved {saved} photos. {skipped} profiles returned no photo (private or blocked).")
                if saved:
                    st.rerun()

        st.divider()
        single_photo_url = st.text_input(
            "Test a single LinkedIn URL",
            key="single_photo_url",
            placeholder="https://www.linkedin.com/in/username/",
        )
        if st.button("Grab 1 Photo", key="grab_1_photo_btn"):
            if not single_photo_url.strip():
                st.warning("Enter a LinkedIn URL.")
            else:
                with st.spinner("Fetching…"):
                    photo = _scrape_li_photo(single_photo_url.strip())
                if photo:
                    st.success(f"Found: {photo}")
                    st.image(photo, width=120)
                    with crm.get_connection() as conn:
                        match = conn.execute(
                            "SELECT id, name FROM centers_of_influence WHERE linkedin_url LIKE ?",
                            (f"%{_extract_linkedin_id(single_photo_url.strip()) or '~~~'}%",)
                        ).fetchone()
                    if match:
                        with crm.get_connection() as conn:
                            conn.execute(
                                "UPDATE centers_of_influence SET photo_url=? WHERE id=?",
                                (photo, match[0]),
                            )
                            conn.commit()
                        st.success(f"Saved to DB for: {match[1]}")
                        st.rerun()
                else:
                    st.warning("No photo found — profile may be private or LinkedIn is blocking the request.")

    # ── LinkedIn Sync panel ───────────────────────────────────────────────────
    with st.expander("Sync LinkedIn Data", expanded=False):
        st.markdown(
            "**Get your session cookies from Chrome/Edge:**  \n"
            "1. Open **linkedin.com** while logged in.  \n"
            "2. Press **F12** → **Application** → **Cookies** → `https://www.linkedin.com`  \n"
            "3. Copy the **Value** of **`li_at`** and **`JSESSIONID`** (both required)."
        )
        lc1, lc2 = st.columns(2)
        with lc1:
            li_at = st.text_input("li_at", type="password", key="li_sync_liat",
                                  placeholder="li_at cookie value…")
        with lc2:
            li_jsid = st.text_input("JSESSIONID", type="password", key="li_sync_jsid",
                                    placeholder="JSESSIONID cookie value…")

        # ── Single-profile test ───────────────────────────────────────────────
        st.divider()
        single_url = st.text_input("Test a single LinkedIn URL", key="li_single_url",
                                   placeholder="https://www.linkedin.com/in/username/")
        if st.button("Sync 1 Profile", key="li_single_btn"):
            if not li_at.strip() or not li_jsid.strip():
                st.warning("Paste both cookies first.")
            elif not single_url.strip():
                st.warning("Enter a LinkedIn URL.")
            else:
                lid = _extract_linkedin_id(single_url.strip())
                if not lid:
                    st.error(f"Could not parse a profile ID from: {single_url}")
                else:
                    with st.spinner(f"Fetching '{lid}'…"):
                        sess = _li_session(li_at.strip(), li_jsid.strip())
                        result = _li_fetch_profile(sess, lid)

                    status = result.get("_status")
                    if status != 200:
                        st.error(f"HTTP {status} — {result.get('_body', '')}")
                        st.caption("Tip: cookies may be expired — refresh linkedin.com and copy fresh values.")
                    else:
                        st.success(f"OK — API keys: {result['_raw_keys']}")
                        st.json({k: v for k, v in result.items() if not k.startswith("_")})

                        with crm.get_connection() as conn:
                            match = conn.execute(
                                "SELECT id, name FROM centers_of_influence WHERE linkedin_url LIKE ?",
                                (f"%{lid}%",)
                            ).fetchone()

                        if match:
                            _write_li_result(crm, match[0], result)
                            st.success(f"Saved to DB: {match[1]}")
                            st.rerun()
                        else:
                            st.info("No matching contact in DB for this URL.")

        st.divider()
        if st.button("Sync All Profiles", type="primary", key="li_sync_btn"):
            if not li_at.strip() or not li_jsid.strip():
                st.warning("Paste both li_at and JSESSIONID cookies first.")
            else:
                with crm.get_connection() as sync_conn:
                    rows_to_sync = pd.read_sql_query(
                        "SELECT id, name, linkedin_url FROM centers_of_influence "
                        "WHERE linkedin_url IS NOT NULL AND linkedin_url != ''",
                        sync_conn,
                    )

                total = len(rows_to_sync)
                if total == 0:
                    st.info("No contacts have a LinkedIn URL.")
                else:
                    sess = _li_session(li_at.strip(), li_jsid.strip())
                    prog = st.progress(0)
                    status_txt = st.empty()
                    updated, failed = 0, 0
                    debug_log = []

                    for idx, (_, row) in enumerate(rows_to_sync.iterrows()):
                        lid = _extract_linkedin_id(row["linkedin_url"])
                        if not lid:
                            debug_log.append(f"[SKIP] {row['name']}: bad URL '{row['linkedin_url']}'")
                            failed += 1
                            prog.progress((idx + 1) / total)
                            continue

                        status_txt.text(f"Fetching {row['name']} ({idx + 1}/{total})…")
                        result = _li_fetch_profile(sess, lid)

                        if result.get("_status") != 200:
                            debug_log.append(f"[ERR] {row['name']} ('{lid}'): HTTP {result.get('_status')} {result.get('_body','')[:80]}")
                            failed += 1
                        else:
                            _write_li_result(crm, int(row["id"]), result)
                            debug_log.append(
                                f"[OK] {row['name']}: headline={result['headline']!r} "
                                f"photo={'yes' if result['photo_url'] else 'no'} "
                                f"phone={result['phone']!r} email={result['email']!r}"
                            )
                            updated += 1

                        time.sleep(0.8)
                        prog.progress((idx + 1) / total)

                    status_txt.empty()
                    prog.empty()
                    st.success(f"Synced {updated} profiles. {failed} failed or skipped.")

                    if debug_log:
                        with st.expander(f"Sync log ({len(debug_log)} entries)"):
                            st.code("\n".join(debug_log))

                    if updated:
                        st.rerun()

    # ── Load contacts ─────────────────────────────────────────────────────────
    try:
        with crm.get_connection() as conn:
            df = pd.read_sql_query(
                """
                SELECT coi.id, coi.name, coi.title, coi.location,
                       coi.linkedin_url, coi.photo_url, coi.notes,
                       coi.linkedin_headline, coi.linkedin_about, coi.linkedin_scraped_at,
                       coi.linkedin_phone, coi.linkedin_email, coi.linkedin_years_at_company,
                       coi.birthday,
                       f.name AS foundation_name,
                       f.city AS foundation_city
                FROM centers_of_influence coi
                LEFT JOIN foundations f ON coi.foundation_id = f.id
                ORDER BY coi.name
                """,
                conn,
            )

        if df.empty:
            st.info("No contacts yet. Use the form above to add your first board member or officer.")
            return

        # ── Search / filter ───────────────────────────────────────────────────
        col_search, col_metric = st.columns([3, 1])
        with col_search:
            search = st.text_input("Search by name, foundation, or headline…", placeholder="Enter name…")
        with col_metric:
            st.metric("Total Contacts", len(df))

        if search:
            mask = (
                df["name"].str.contains(search, case=False, na=False)
                | df["foundation_name"].str.contains(search, case=False, na=False)
                | df["linkedin_headline"].fillna("").str.contains(search, case=False, na=False)
            )
            df = df[mask]

        if df.empty:
            st.warning("No contacts match your search.")
            return

        # ── Table view ────────────────────────────────────────────────────────
        def _s(v):
            return str(v).strip() if (v is not None and pd.notna(v) and str(v).strip() not in ("", "nan")) else ""

        display = df.copy()
        display["LinkedIn"]  = display["linkedin_url"].apply(_s)
        display["Notes"]     = display["notes"].apply(_s)
        display["Address"]   = display["location"].apply(_s)
        display["Title"]     = display["title"].apply(_s)
        display["Headline"]  = display["linkedin_headline"].apply(_s)
        display["About"]     = display["linkedin_about"].apply(_s)
        display["Phone"]     = display["linkedin_phone"].apply(_s)
        display["Email"]     = display["linkedin_email"].apply(_s)
        display["Yrs @ Co"]  = display["linkedin_years_at_company"]
        display["Birthday"]  = pd.to_datetime(display["birthday"], errors="coerce")

        table = display[[
            "name", "Title", "foundation_name", "Address",
            "Headline", "Phone", "Email", "Yrs @ Co",
            "Birthday", "LinkedIn", "About", "Notes",
        ]].copy()
        table.columns = [
            "Name", "Title", "Foundation", "Address",
            "Headline", "Phone", "Email", "Yrs @ Co",
            "Birthday", "LinkedIn", "About", "Notes",
        ]
        table.insert(0, "#", range(1, len(table) + 1))

        col_cfg = {
            "#":          st.column_config.NumberColumn("#", width=40),
            "Name":       st.column_config.TextColumn("Name", width="medium"),
            "Title":      st.column_config.TextColumn("Title", width="medium"),
            "Foundation": st.column_config.TextColumn("Foundation", width="large"),
            "Address":    st.column_config.TextColumn("Address", width="medium"),
            "Headline":   st.column_config.TextColumn("Headline", width="large"),
            "Phone":      st.column_config.TextColumn("Phone", width="small"),
            "Email":      st.column_config.TextColumn("Email", width="medium"),
            "Yrs @ Co":   st.column_config.NumberColumn("Yrs @ Co", format="%.1f", width="small"),
            "Birthday":   st.column_config.DateColumn("Birthday", format="MMM D, YYYY", width="small"),
            "LinkedIn":   st.column_config.LinkColumn("LinkedIn", display_text="Profile", width="small"),
            "About":      st.column_config.TextColumn("About", width="large"),
            "Notes":      st.column_config.TextColumn("Notes", width="large"),
        }

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
            height=min(40 + len(table) * 35, 600),
            column_config=col_cfg,
        )

        # ── Delete by name ────────────────────────────────────────────────────
        with st.expander("Remove a contact"):
            opts = {f"{r['name']}  —  {_s(r['foundation_name'])}": r["id"] for _, r in df.iterrows()}
            to_del = st.multiselect("Select contacts to remove", list(opts.keys()))
            if to_del and st.button("Delete selected", type="primary"):
                with crm.get_connection() as conn:
                    for label in to_del:
                        conn.execute("DELETE FROM centers_of_influence WHERE id=?", (opts[label],))
                    conn.commit()
                st.rerun()

    except Exception as e:
        st.error(f"Error loading centers of influence: {e}")
