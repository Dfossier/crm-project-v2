#!/usr/bin/env python3
"""
bio_scraper.py  —  Build bios for CoI contacts from foundation and employer websites.

Strategy (per-person, in order):
  1. Serper search: "{name}" site:{foundation_domain}
     → Google has already rendered JS pages; the snippet is often a bio snippet.
     → If the linked page is static, also fetch it for a longer bio.
  2. Serper search: "{name}" site:{employer_domain}  (when employer != foundation)
  3. Serper search: "{name}" Louisiana (board OR biography OR profile OR foundation)
     → General fallback for people not findable on specific sites.

Results written to centers_of_influence.bio (column added if missing).
"""

import sqlite3, requests, json, time, re, os
from pathlib import Path
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

DB_PATH  = "/home/dfoss/crm/database/louisiana_foundations.db"
LOG_PATH = "/home/dfoss/crm/bio_scraper_log.json"
ENV_PATH = "/home/dfoss/crm/.env"
DELAY    = 1.0   # seconds between HTTP / Serper calls

# ── Config ────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

def _load_serper_key():
    key = os.getenv("SERPER_API_KEY")
    if key:
        return key
    p = Path(ENV_PATH)
    if p.exists():
        for line in p.read_text().splitlines():
            if line.startswith("SERPER_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None

SERPER_KEY = _load_serper_key()

# ── Name helpers ──────────────────────────────────────────────────────────────

_TITLES = re.compile(
    r"\b(DR|REV|VERY REV|MR|MRS|MS|PROF|JR|SR|II|III|IV|"
    r"MD|PHD|DO|DDS|ESQ|CPA|MBA|CFA|CGMA|MPT|MSN|RN|OP|"
    r"O\.P\.|M\.ED|EDD|LLC|INC)\b\.?",
    re.IGNORECASE,
)

def normalize(name: str) -> str:
    name = _TITLES.sub("", name)
    name = re.sub(r"[^a-zA-Z\s]", " ", name)
    return re.sub(r"\s+", " ", name).strip().lower()

def display_name(name: str) -> str:
    """Title-case normalized name for search queries."""
    return normalize(name).title()

def names_match(a: str, b: str) -> bool:
    ap = normalize(a).split()
    bp = normalize(b).split()
    if len(ap) < 2 or len(bp) < 2:
        return False
    return ap[-1] == bp[-1] and (ap[0] == bp[0] or ap[0] in bp or bp[0] in ap)

# ── Domain helpers ────────────────────────────────────────────────────────────

def to_domain(url_or_name: str) -> str | None:
    """Extract domain from URL, or try to guess from org name."""
    if not url_or_name:
        return None
    if url_or_name.startswith("http"):
        d = urlparse(url_or_name).netloc.lstrip("www.")
        return d if d else None
    return None

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def fetch(url: str, timeout: int = 15) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        ct = r.headers.get("content-type", "")
        if r.ok and "text/html" in ct:
            return r.text
    except Exception as e:
        print(f"      fetch error ({url[:60]}): {e}")
    return None

def serper(query: str, num: int = 5) -> list:
    if not SERPER_KEY:
        print("      SERPER_KEY not set — skipping search")
        return []
    try:
        r = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_KEY, "Content-Type": "application/json"},
            json={"q": query, "num": num},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("organic", [])
    except Exception as e:
        print(f"      serper error: {e}")
        return []

# ── Bio quality filters ───────────────────────────────────────────────────────

# Hard disqualifiers
_NOT_BIO = re.compile(
    r"(login|sign.?in|404|not.?found|subscribe|cookie|privacy policy|"
    r"terms of service|javascript|enable js|\bcart\b|\bcheckout\b)",
    re.IGNORECASE,
)
_PHONE = re.compile(r"\d{3}[-.\s]?\d{3}[-.\s]?\d{4}")
_EMAIL_ONLY = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# LinkedIn metadata — these are page-preview snippets, not real bios
_LINKEDIN_META = re.compile(
    r"(connections? on LinkedIn|View .{3,50}['']s profile on LinkedIn|"
    r"a professional community of \d|LinkedIn members|Sign in to view|"
    r"location:.*metropolitan area|followers \d+ connections)",
    re.IGNORECASE,
)

# Social media profile metadata (Instagram, Facebook, Twitter)
_SOCIAL_META = re.compile(
    r"\b(\d+\s*(followers?|following|posts?|likes?|reposts?|retweets?|shares?|views?))\b",
    re.IGNORECASE,
)

# Salary/compensation data from 990 filings
_SALARY_DATA = re.compile(r"\$[\d,]{4,}")

# Meeting-minutes patterns — person mentioned but not bio'd
_MINUTES = re.compile(
    r"(no vote was taken|motion (was|to)|seconded by|roll call|"
    r"in attendance|public comment|agenda item|meeting adjourned)",
    re.IGNORECASE,
)

# A good bio contains at least one of these role/career words
_BIO_WORDS = re.compile(
    r"\b(serves?|served|board|director|trustee|president|chair|vice|"
    r"founded|founder|ceo|officer|partner|attorney|physician|doctor|"
    r"professor|executive|community|oversee|practice|manage|lead|"
    r"degree|university|college|graduated|career|profession|"
    r"appointed|member|joined|honoree|award|recognized)\b",
    re.IGNORECASE,
)

def is_good_bio(text: str, person_name: str, min_len: int = 45) -> bool:
    if not text or len(text) < min_len:
        return False
    if _NOT_BIO.search(text):
        return False
    if _LINKEDIN_META.search(text):
        return False
    if _SOCIAL_META.search(text) and len(text) < 200:
        return False   # social media profile stats, not a bio
    if _SALARY_DATA.search(text) and len(text) < 300:
        return False   # 990 comp table row, not a bio
    if _MINUTES.search(text):
        return False
    # Pure contact info
    if _PHONE.search(text) and len(text) < 200:
        return False
    if _EMAIL_ONLY.match(text.strip()):
        return False
    # Too many newlines relative to length → nav list
    line_count = text.count("\n") + 1
    if line_count > 8 and (len(text) / line_count) < 25:
        return False
    # Should have at least one bio-like word for longer texts
    if len(text) > 120 and not _BIO_WORDS.search(text):
        return False
    return True

def clean_snippet(text: str) -> str:
    # Remove date prefix: "May 14, 2026 — text"
    text = re.sub(r"^[A-Z][a-z]{2,8}\s+\d{1,2},\s+\d{4}\s*[—–\-]+\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()[:1600]

# ── Bio extraction from full HTML page ───────────────────────────────────────

_BOILERPLATE_CLS = re.compile(
    r"\b(nav|menu|footer|header|sidebar|cookie|banner|social|"
    r"share|search|pagination|breadcrumb|widget|advertisement)\b",
    re.IGNORECASE,
)

def _is_chrome(tag) -> bool:
    cls = " ".join(tag.get("class", []))
    tid = tag.get("id", "")
    return bool(_BOILERPLATE_CLS.search(cls) or _BOILERPLATE_CLS.search(tid))

def _para_text(tag) -> str:
    paras = [p.get_text(" ", strip=True)
             for p in tag.find_all("p")
             if len(p.get_text(strip=True)) > 35]
    if paras:
        return " ".join(paras)
    # Fall back to divs with enough text
    for div in tag.find_all("div"):
        t = div.get_text(" ", strip=True)
        if 50 < len(t) < 2500 and not _is_chrome(div):
            return t
    return tag.get_text(" ", strip=True)

def find_bio_on_page(soup: BeautifulSoup, person_name: str) -> str | None:
    parts = normalize(person_name).split()
    if len(parts) < 2:
        return None
    first, last = parts[0], parts[-1]

    candidates = []

    for node in soup.find_all(string=re.compile(re.escape(last), re.IGNORECASE)):
        container = node.parent
        depth = 0
        while container and depth < 7:
            if container.name in ("html", "body", "[document]"):
                break
            if _is_chrome(container):
                container = container.parent
                depth += 1
                continue
            ctext = container.get_text(" ", strip=True).lower()
            if first in ctext and last in ctext:
                raw = _para_text(container)
                raw = re.sub(r"\s+", " ", raw).strip()
                # Strip leading "Name" line
                raw = re.sub(
                    r"^" + re.escape(person_name) + r"\s*[,\-–|]?\s*",
                    "", raw, flags=re.IGNORECASE,
                )
                # Sanity: container shouldn't be so large it's the whole page body
                if 45 < len(raw) < 3500:
                    candidates.append(raw)
                break
            container = container.parent
            depth += 1

    if not candidates:
        return None

    # Prefer the shortest candidate that passes quality check (avoids grabbing too much)
    candidates.sort(key=len)
    for c in candidates:
        if is_good_bio(c, person_name, min_len=45):
            return c[:1600]
    return None

# ── Bio-link discovery ────────────────────────────────────────────────────────

def find_bio_links(soup: BeautifulSoup, base_url: str, names: list) -> dict:
    bio_links = {}
    base_domain = urlparse(base_url).netloc

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        full = urljoin(base_url, href)
        if urlparse(full).netloc != base_domain:
            continue

        link_text = a.get_text(" ", strip=True)
        slug = re.sub(r"[^a-z\s]", " ", urlparse(full).path.lower())

        for name in names:
            if name in bio_links:
                continue
            if names_match(link_text, name):
                bio_links[name] = full
            else:
                np = normalize(name).split()
                if len(np) >= 2 and np[-1] in slug and np[0] in slug:
                    bio_links[name] = full

    return bio_links

# ── DB helpers ────────────────────────────────────────────────────────────────

def ensure_bio_column(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(centers_of_influence)")
    if "bio" not in [r[1] for r in cur.fetchall()]:
        cur.execute("ALTER TABLE centers_of_influence ADD COLUMN bio TEXT")
        conn.commit()
        print("  [db] Added 'bio' column to centers_of_influence")

def write_bio(conn: sqlite3.Connection, cid: int, bio: str, source: str):
    cur = conn.cursor()
    cur.execute(
        "UPDATE centers_of_influence SET bio=?, updated_at=datetime('now') WHERE id=?",
        (f"[{source}] {bio}", cid),
    )
    conn.commit()

def has_bio(conn: sqlite3.Connection, cid: int) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT bio FROM centers_of_influence WHERE id=?", (cid,))
    row = cur.fetchone()
    return bool(row and row[0])

# ── Per-person bio finder ─────────────────────────────────────────────────────

def try_serper_and_fetch(conn, cid, name, query, source_label):
    """Run *query* through Serper; try snippet first, then fetch linked page."""
    results = serper(query, num=5)
    time.sleep(DELAY)

    for r in results:
        snippet = clean_snippet(r.get("snippet", ""))
        url = r.get("link", "")

        # Try fetching the full page for a longer bio
        page_bio = None
        if url and len(snippet) < 400:
            html = fetch(url)
            if html and len(html) > 3000:
                soup = BeautifulSoup(html, "lxml")
                for tag in soup.find_all(["nav","footer","header","script","style"]):
                    tag.decompose()
                page_bio = find_bio_on_page(soup, name)
                time.sleep(DELAY)

                # Also follow individual bio links from this page
                if not page_bio:
                    links = find_bio_links(soup, url, [name])
                    if links.get(name):
                        bio_html = fetch(links[name])
                        time.sleep(DELAY)
                        if bio_html:
                            bio_soup = BeautifulSoup(bio_html, "lxml")
                            for tag in bio_soup.find_all(["nav","footer","header","script","style"]):
                                tag.decompose()
                            page_bio = find_bio_on_page(bio_soup, name)

        # Pick best bio: prefer page_bio if longer, else snippet
        bio = page_bio if (page_bio and len(page_bio) > len(snippet)) else snippet
        if is_good_bio(bio, name):
            write_bio(conn, cid, bio, source_label)
            print(f"      ✓ {name} ({len(bio)} chars) [{source_label}]")
            print(f"        {bio[:110]}...")
            return True

    return False


def find_bio_for_contact(conn, cid, name, foundation_domain, employer, employer_domain):
    """Try all methods for one CoI contact. Returns True if bio written."""
    dname = display_name(name)

    # 1. Foundation site search
    if foundation_domain:
        q = f'"{dname}" site:{foundation_domain}'
        if try_serper_and_fetch(conn, cid, name, q, f"fnd:{foundation_domain}"):
            return True

    # 2. Employer site search (only if different from foundation)
    if employer_domain and employer_domain != foundation_domain:
        q = f'"{dname}" site:{employer_domain}'
        if try_serper_and_fetch(conn, cid, name, q, f"emp:{employer_domain}"):
            return True

    # 3. General fallback search
    q = f'"{dname}" Louisiana (board OR director OR trustee OR foundation OR biography OR profile)'
    if try_serper_and_fetch(conn, cid, name, q, "general"):
        return True

    return False

# ── Employer domain resolver ──────────────────────────────────────────────────

_EMP_DOMAIN_CACHE: dict = {}

def resolve_employer_domain(employer: str) -> str | None:
    """Use Serper to find the employer's website domain."""
    if employer in _EMP_DOMAIN_CACHE:
        return _EMP_DOMAIN_CACHE[employer]
    results = serper(f'"{employer}" official website', num=3)
    time.sleep(DELAY)
    for r in results:
        url = r.get("link", "")
        domain = to_domain(url)
        if domain:
            _EMP_DOMAIN_CACHE[employer] = domain
            return domain
    _EMP_DOMAIN_CACHE[employer] = None
    return None

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    conn = sqlite3.connect(DB_PATH)
    ensure_bio_column(conn)
    cur = conn.cursor()

    cur.execute("""
        SELECT c.id, c.name, c.employer,
               f.website,
               f.name AS fname
        FROM   centers_of_influence c
        LEFT JOIN foundations f ON c.foundation_id = f.id
        WHERE  (c.bio IS NULL OR c.bio = '')
        ORDER  BY f.id, c.name
    """)
    contacts = cur.fetchall()
    print(f"\n{len(contacts)} CoI contacts without bios\n")

    log = []
    total = 0

    for cid, name, employer, fnd_website, fname in contacts:
        print(f"\n  [{cid}] {name}")
        if fname:
            print(f"       Foundation: {fname}")
        if employer:
            print(f"       Employer:   {employer}")

        foundation_domain = to_domain(fnd_website)

        # Resolve employer domain (skip if employer IS the foundation)
        employer_domain = None
        if employer and employer.lower() not in (fname or "").lower():
            employer_domain = resolve_employer_domain(employer)

        found = find_bio_for_contact(
            conn, cid, name,
            foundation_domain,
            employer,
            employer_domain,
        )

        if found:
            total += 1
        else:
            print(f"      ✗ {name}: no bio found")

        log.append({
            "id": cid,
            "name": name,
            "found": found,
            "foundation_domain": foundation_domain,
            "employer_domain": employer_domain,
        })

    Path(LOG_PATH).write_text(json.dumps(log, indent=2))
    print(f"\n{'='*60}")
    print(f"Done. Bios written: {total} / {len(contacts)}")
    print(f"Log: {LOG_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
