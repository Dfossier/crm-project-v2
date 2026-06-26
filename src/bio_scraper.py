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

DB_PATH  = "/home/dfoss/.openclaw/workspace/louisiana-foundations-crm/database/louisiana_foundations.db"
LOG_PATH = "/home/dfoss/.openclaw/workspace/louisiana-foundations-crm/bio_scraper_log.json"
ENV_PATH = "/home/dfoss/.openclaw/workspace/louisiana-foundations-crm/.env"
DELAY    = 1.0   # seconds between HTTP / Serper calls

LINKEDIN_SKIP_DOMAINS = {"linkedin.com", "www.linkedin.com"}

# ── Config ────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

def _load_env_key(var: str) -> str | None:
    val = os.getenv(var)
    if val:
        return val
    p = Path(ENV_PATH)
    if p.exists():
        for line in p.read_text().splitlines():
            if line.startswith(f"{var}="):
                return line.split("=", 1)[1].strip()
    return None

SERPER_KEY     = _load_env_key("SERPER_API_KEY")
LOCAL_LLM_URL  = _load_env_key("LOCAL_LLM_URL")
LOCAL_LLM_MODEL = _load_env_key("LOCAL_LLM_MODEL")

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
        r = requests.get(
            "https://serpapi.com/search",
            params={"engine": "google", "q": query, "num": num, "api_key": SERPER_KEY},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("organic_results", [])
    except Exception as e:
        print(f"      serper error: {e}")
        return []

# ── Bio quality filters ───────────────────────────────────────────────────────

# Hard disqualifiers
_NOT_BIO = re.compile(
    r"(login|sign.?in|404|not.?found|subscribe|cookie|privacy policy|"
    r"terms of service|javascript|enable js|\bcart\b|\bcheckout\b|"
    r"show search box|select the type of search|nonprofit explorer)",
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

# LinkedIn people-search results: "Name. --. Location." repeated
_LINKEDIN_PEOPLE_SEARCH = re.compile(r"(\w[\w\s]+\.\s*--\s*\..*){2,}", re.IGNORECASE)

# Social media profile metadata (Instagram, Facebook, Twitter)
_SOCIAL_META = re.compile(
    r"\b(\d+\s*(followers?|following|posts?|likes?|reposts?|retweets?|shares?|views?))\b",
    re.IGNORECASE,
)

# Salary/compensation data from 990 filings
_SALARY_DATA = re.compile(r"\$[\d,]{4,}")
# 990 compensation-table row: "(Title), $0, $0"
_990_TABLE = re.compile(r"\([\w\s]{3,40}\),\s*\$\d", re.IGNORECASE)

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
    if text.startswith("...") or text.startswith("…"):
        return False  # mid-snippet, truncated at start
    if text.rstrip().endswith("...") or text.rstrip().endswith("…"):
        return False  # Google snippet truncated at end
    if _NOT_BIO.search(text):
        return False
    if _LINKEDIN_META.search(text):
        return False
    if _LINKEDIN_PEOPLE_SEARCH.search(text):
        return False
    if _SOCIAL_META.search(text) and len(text) < 200:
        return False   # social media profile stats, not a bio
    if _SALARY_DATA.search(text) and len(text) < 300:
        return False   # 990 comp table row, not a bio
    if _990_TABLE.search(text):
        return False   # 990 compensation table row
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

# ── LLM bio synthesis ─────────────────────────────────────────────────────────

def llm_extract_bio(page_text: str, person_name: str, source_url: str = "") -> str | None:
    """
    Use the local LLM to extract a clean professional bio from raw page text.
    Calls the OpenAI-compatible endpoint at LOCAL_LLM_URL.
    Returns None if endpoint not configured or extraction fails.
    """
    if not LOCAL_LLM_URL:
        return None
    try:
        excerpt = page_text[:6000]
        payload = {
            "model": LOCAL_LLM_MODEL or "local",
            "max_tokens": 400,
            "temperature": 0.1,
            "messages": [{
                "role": "user",
                "content": (
                    f"Extract a professional biography for {person_name} from the text below. "
                    "Write 2-4 sentences covering their role, career background, and community involvement. "
                    "Use only facts stated in the text — do not invent anything. "
                    "If the text contains no meaningful information about this person, reply with exactly: NO_BIO\n\n"
                    f"Source: {source_url}\n\n{excerpt}"
                ),
            }],
        }
        r = requests.post(
            f"{LOCAL_LLM_URL}/chat/completions",
            json=payload,
            timeout=60,
        )
        r.raise_for_status()
        result = r.json()["choices"][0]["message"]["content"].strip()
        if len(result) < 40:
            return None
        # Detect when the LLM signals no usable info (strict or verbose)
        no_info_signals = (
            "NO_BIO",
            "no meaningful information",
            "does not contain",
            "no relevant details",
            "no information about",
            "cannot find",
            "not mentioned",
        )
        lower = result.lower()
        if any(s.lower() in lower for s in no_info_signals):
            return None
        return result
    except Exception as e:
        print(f"      llm error: {e}")
        return None


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
        "UPDATE centers_of_influence SET bio=? WHERE id=?",
        (f"[{source}] {bio}", cid),
    )
    conn.commit()

def has_bio(conn: sqlite3.Connection, cid: int) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT bio FROM centers_of_influence WHERE id=?", (cid,))
    row = cur.fetchone()
    return bool(row and row[0])

# ── Per-person bio finder ─────────────────────────────────────────────────────

def _fetch_and_extract(url: str, name: str) -> str | None:
    """Fetch a URL and extract bio via regex + optional LLM fallback."""
    if urlparse(url).netloc.lstrip("www.") in LINKEDIN_SKIP_DOMAINS:
        return None  # LinkedIn blocks scraping
    html = fetch(url)
    if not html or len(html) < 1000:
        return None
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["nav", "footer", "header", "script", "style"]):
        tag.decompose()
    bio = find_bio_on_page(soup, name)
    if bio and is_good_bio(bio, name):
        return bio
    # LLM fallback on full page text when regex comes up empty
    page_text = soup.get_text(" ", strip=True)
    return llm_extract_bio(page_text, name, source_url=url)


def try_serper_and_fetch(conn, cid, name, query, source_label):
    """Run *query* through SerpAPI; try snippet first, then fetch linked pages."""
    results = serper(query, num=5)
    time.sleep(DELAY)

    for r in results:
        snippet = clean_snippet(r.get("snippet", ""))
        url     = r.get("link", "")

        # Try fetching the full page for a richer bio
        page_bio = None
        if url:
            page_bio = _fetch_and_extract(url, name)
            time.sleep(DELAY)

            # Follow individual bio links discovered on the page
            if not page_bio:
                html = fetch(url)
                if html:
                    soup = BeautifulSoup(html, "lxml")
                    links = find_bio_links(soup, url, [name])
                    if links.get(name):
                        page_bio = _fetch_and_extract(links[name], name)
                        time.sleep(DELAY)

        # Pick best: prefer longer page bio, fall back to snippet
        bio = page_bio if (page_bio and len(page_bio) > len(snippet)) else snippet
        if is_good_bio(bio, name):
            write_bio(conn, cid, bio, source_label)
            print(f"      ✓ {name} ({len(bio)} chars) [{source_label}]")
            print(f"        {bio[:110]}...")
            return True

    return False


def try_direct_url(conn, cid, name, url, source_label):
    """Fetch a known URL directly (e.g. LinkedIn profile page)."""
    if urlparse(url).netloc.lstrip("www.") in LINKEDIN_SKIP_DOMAINS:
        # LinkedIn blocks scraping — search for the specific profile URL as the query
        # so SerpAPI returns a cached snippet for that exact profile, not a people-search page
        return try_serper_and_fetch(conn, cid, name, url, source_label)
    bio = _fetch_and_extract(url, name)
    if bio and is_good_bio(bio, name):
        write_bio(conn, cid, bio, source_label)
        print(f"      ✓ {name} ({len(bio)} chars) [{source_label}]")
        print(f"        {bio[:110]}...")
        return True
    return False


def find_bio_for_contact(conn, cid, name, foundation_domain, employer,
                         employer_domain, linkedin_url=None, title=None):
    """Try all strategies for one CoI contact. Returns True if bio written."""
    dname = display_name(name)

    # 1. LinkedIn — use known URL or search
    if linkedin_url:
        if try_direct_url(conn, cid, name, linkedin_url, "linkedin"):
            return True

    # 2. Foundation site search
    if foundation_domain:
        q = f'"{dname}" site:{foundation_domain}'
        if try_serper_and_fetch(conn, cid, name, q, f"fnd:{foundation_domain}"):
            return True

    # 3. Employer site search (only if different from foundation)
    if employer_domain and employer_domain != foundation_domain:
        q = f'"{dname}" site:{employer_domain}'
        if try_serper_and_fetch(conn, cid, name, q, f"emp:{employer_domain}"):
            return True

    # 4. News / press releases — often richest narrative bios
    q = f'"{dname}" Louisiana (bank OR attorney OR doctor OR executive OR president)'
    if title:
        q = f'"{dname}" "{title}" Louisiana'
    if try_serper_and_fetch(conn, cid, name, q, "news"):
        return True

    # 5. General biography / profile search
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
        SELECT c.id, c.name, c.title, c.employer, c.linkedin_url,
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

    for cid, name, title, employer, linkedin_url, fnd_website, fname in contacts:
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
            linkedin_url=linkedin_url,
            title=title,
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
