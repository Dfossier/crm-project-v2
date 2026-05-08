#!/usr/bin/env python3
"""
Foundation website scraper.
For each foundation with a website:
  1. Uses Serper to find their board/leadership/team page
  2. Fetches and parses the HTML
  3. Matches names against personnel_990
  4. Extracts: LinkedIn URLs, employer/company (related_organization)
"""
import sqlite3, requests, json, time, re
from pathlib import Path
from html.parser import HTMLParser

DB_PATH = "/home/dfoss/crm/database/louisiana_foundations.db"
import os
from pathlib import Path

DB_PATH = "/home/dfoss/crm/database/louisiana_foundations.db"

# Load API key from environment or .env file
API_KEY = os.getenv("SERPER_API_KEY")
if not API_KEY:
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().strip().split("\n"):
            if line.startswith("SERPER_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip()
                break
LOG_PATH = "/home/dfoss/crm/foundation_scraper_log.json"
DELAY = 0.75

# ── HTML helpers ─────────────────────────────────────────────────────────────

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "head"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "head"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self.text_parts.append(stripped)

    def get_text(self):
        return "\n".join(self.text_parts)


def extract_text(html):
    p = TextExtractor()
    try:
        p.feed(html)
    except Exception:
        pass
    return p.get_text()


def extract_linkedin_urls(html):
    """Pull all linkedin.com/in/ URLs from raw HTML."""
    found = set()
    for m in re.finditer(r'https?://(?:www\.)?linkedin\.com/in/([^"\'>\s/?#]+)', html):
        slug = m.group(1).rstrip("/")
        found.add(f"https://www.linkedin.com/in/{slug}")
    return found


# ── Serper helpers ────────────────────────────────────────────────────────────

def serper_search(query, num=5):
    resp = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": API_KEY, "Content-Type": "application/json"},
        json={"q": query, "num": num},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("organic", [])


def find_board_page(foundation_name, website):
    """Return URL of the foundation's board/team page, or None."""
    domain = re.sub(r"^https?://", "", website).rstrip("/").split("/")[0]
    results = serper_search(
        f'site:{domain} (board OR directors OR leadership OR "board of directors" OR team OR trustees)',
        num=5,
    )
    for r in results:
        url = r.get("link", "")
        title = r.get("title", "").lower()
        snippet = r.get("snippet", "").lower()
        keywords = ("board", "director", "leadership", "team", "trustee", "officer", "staff")
        if any(k in title or k in snippet for k in keywords):
            return url
    # Fall back to first result
    return results[0].get("link") if results else None


def fetch_page(url):
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"},
            timeout=15,
        )
        if resp.ok:
            return resp.text
    except Exception:
        pass
    return None


# ── Name matching ─────────────────────────────────────────────────────────────

_STRIP_TITLES = re.compile(
    r"\b(DR|REV|VERY REV|MR|MRS|MS|PROF|JR|SR|II|III|IV|MD|PHD|DO|ESQ|OP|CPA)\b\.?",
    re.IGNORECASE,
)

def normalize_name(name):
    name = _STRIP_TITLES.sub("", name)
    name = re.sub(r"[^a-z\s]", "", name.lower())
    return re.sub(r"\s+", " ", name).strip()


def name_in_text(name, text):
    """Return True if normalized name tokens all appear near each other in text."""
    normed = normalize_name(name)
    parts = normed.split()
    if len(parts) < 2:
        return False
    # Require first AND last name to appear within 200 chars of each other
    text_lower = text.lower()
    first, last = parts[0], parts[-1]
    idx = text_lower.find(last)
    while idx != -1:
        window = text_lower[max(0, idx - 200): idx + 200]
        if first in window:
            return True
        idx = text_lower.find(last, idx + 1)
    return False


def extract_employer_near_name(name, text):
    """
    Try to extract an employer/title phrase near the person's name in page text.
    Looks for patterns like 'Name, Title at Company' or 'Name\nTitle\nCompany'.
    Returns a string or None.
    """
    normed_last = normalize_name(name).split()[-1]
    text_lower = text.lower()
    idx = text_lower.find(normed_last)
    if idx == -1:
        return None
    # Grab surrounding context
    context = text[max(0, idx - 50): idx + 300]
    # Look for "at [Company]" pattern
    m = re.search(r"\bat\s+([A-Z][A-Za-z &,\.]{3,60})", context)
    if m:
        return m.group(1).strip()
    # Look for lines after the name that look like a company/org
    lines = [l.strip() for l in context.split("\n") if l.strip()]
    for line in lines[1:4]:
        # Skip lines that look like navigation/boilerplate
        if len(line) > 8 and len(line) < 80 and not line.lower().startswith(("home", "about", "contact", "donate", "news")):
            # Prefer lines that contain an org-like word
            if re.search(r"\b(LLC|Inc|Corp|Foundation|Hospital|University|Bank|Group|Partners|Consulting|Services|Law|Medical|Health|School|College)\b", line, re.IGNORECASE):
                return line
    return None


# ── LinkedIn slug → name matching ─────────────────────────────────────────────

def slug_matches_name(slug, name):
    """Check if a LinkedIn slug plausibly belongs to this person."""
    normed = normalize_name(name)
    parts = normed.split()
    if len(parts) < 2:
        return False
    first, last = parts[0], parts[-1]
    slug_lower = slug.lower()
    # Both first and last name should appear in slug
    return first in slug_lower and last in slug_lower


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT f.id, f.name, f.website FROM foundations f
        WHERE f.website IS NOT NULL AND f.website != ''
        ORDER BY f.id
    """)
    foundations = cur.fetchall()
    print(f"Processing {len(foundations)} foundations with websites...\n")

    log = []
    linkedin_added = 0
    employer_added = 0

    for fid, fname, website in foundations:
        print(f"── {fname[:50]}")
        print(f"   Website: {website}")

        # Get personnel for this foundation
        cur.execute("""
            SELECT id, name, linkedin_url, related_organization
            FROM personnel_990
            WHERE foundation_id = ?
        """, (fid,))
        personnel = cur.fetchall()
        if not personnel:
            print("   No personnel — skipping")
            continue

        # Find board page
        try:
            board_url = find_board_page(fname, website)
            time.sleep(DELAY)
        except Exception as e:
            print(f"   Serper error: {e}")
            log.append({"foundation": fname, "status": "serper_error", "error": str(e)})
            continue

        if not board_url:
            print("   No board page found")
            log.append({"foundation": fname, "status": "no_board_page"})
            continue

        print(f"   Board page: {board_url}")

        # Fetch page
        html = fetch_page(board_url)
        if not html:
            print("   Fetch failed")
            log.append({"foundation": fname, "board_url": board_url, "status": "fetch_failed"})
            continue

        page_text = extract_text(html)
        page_linkedin_urls = extract_linkedin_urls(html)

        f_log = {"foundation": fname, "board_url": board_url, "updates": []}

        for pid, pname, existing_linkedin, existing_employer in personnel:
            updates = {}

            # 1. LinkedIn: check if any URL on the page matches this person's name
            if not existing_linkedin:
                for url in page_linkedin_urls:
                    slug = url.split("/in/")[-1].rstrip("/")
                    if slug_matches_name(slug, pname):
                        updates["linkedin_url"] = url
                        break

            # 2. Employer: look for context near name in page text
            if not existing_employer and name_in_text(pname, page_text):
                employer = extract_employer_near_name(pname, page_text)
                if employer:
                    updates["related_organization"] = employer

            if updates:
                set_clause = ", ".join(f"{k} = ?" for k in updates)
                cur.execute(
                    f"UPDATE personnel_990 SET {set_clause} WHERE id = ?",
                    (*updates.values(), pid)
                )
                conn.commit()

                if "linkedin_url" in updates:
                    linkedin_added += 1
                    print(f"   LinkedIn  {pname}: {updates['linkedin_url']}")
                if "related_organization" in updates:
                    employer_added += 1
                    print(f"   Employer  {pname}: {updates['related_organization']}")

                f_log["updates"].append({"id": pid, "name": pname, **updates})

        if not f_log["updates"]:
            print("   No new data found")
        f_log["status"] = "ok"
        log.append(f_log)
        time.sleep(DELAY)

    conn.close()
    Path(LOG_PATH).write_text(json.dumps(log, indent=2))
    print(f"\nDone. LinkedIn added: {linkedin_added}, Employers added: {employer_added}")
    print(f"Log: {LOG_PATH}")


if __name__ == "__main__":
    main()
