#!/usr/bin/env python3
"""
fix_truncated_bios.py  —  Re-fetch full bios for CoI records whose stored bio
ends with "..." (meaning we stored a truncated Google snippet).

Strategy per person:
  1. Re-run the same Serper search used originally (based on [source_label]).
  2. THIS TIME always fetch the linked page — don't rely on the snippet.
  3. Extract full bio from page via find_bio_on_page.
  4. Fall back through other source types if the original source yields nothing.
  5. Only update the DB when the new bio is longer AND not truncated.
"""

import sys, os
sys.path.insert(0, "/home/dfoss/.openclaw/workspace/louisiana-foundations-crm")

import sqlite3, re, time
from bs4 import BeautifulSoup

# Import helpers from bio_scraper
from src.bio_scraper import (
    serper, fetch, find_bio_on_page, find_bio_links,
    is_good_bio, clean_snippet, display_name, write_bio,
    to_domain, resolve_employer_domain, DELAY,
)

DB_PATH = "/home/dfoss/.openclaw/workspace/louisiana-foundations-crm/database/louisiana_foundations.db"

# ── Parse source label ────────────────────────────────────────────────────────

_TAG_RE = re.compile(r"^\[(.*?)\]")

def parse_source(bio: str):
    """Return (source_type, domain) from [source_label] prefix."""
    m = _TAG_RE.match(bio or "")
    if not m:
        return "general", None
    label = m.group(1)
    if label.startswith("fnd:"):
        return "fnd", label[4:]
    if label.startswith("emp:"):
        return "emp", label[4:]
    return "general", None


# ── Aggressive page fetcher (always fetches, doesn't rely on snippet) ─────────

def try_fetch_full(conn, cid, name, query, source_label, current_bio):
    """Run Serper query, fetch every linked page, return True if better bio found."""
    results = serper(query, num=5)
    time.sleep(DELAY)

    for r in results:
        url = r.get("link", "")
        if not url:
            continue

        # Always fetch the page — this is the key fix
        html = fetch(url)
        time.sleep(DELAY)
        if not html or len(html) < 1000:
            continue

        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all(["nav", "footer", "header", "script", "style"]):
            tag.decompose()

        page_bio = find_bio_on_page(soup, name)

        # Also follow bio-specific links from the page
        if not page_bio:
            links = find_bio_links(soup, url, [name])
            if links.get(name):
                bio_html = fetch(links[name])
                time.sleep(DELAY)
                if bio_html:
                    bio_soup = BeautifulSoup(bio_html, "lxml")
                    for tag in bio_soup.find_all(["nav", "footer", "header", "script", "style"]):
                        tag.decompose()
                    page_bio = find_bio_on_page(bio_soup, name)

        if not page_bio:
            # Snippet as last resort (may still be better if page parse failed)
            snippet = clean_snippet(r.get("snippet", ""))
            if is_good_bio(snippet, name) and not snippet.endswith("..."):
                page_bio = snippet

        if page_bio and is_good_bio(page_bio, name):
            # Only update if new bio is substantially longer or not truncated
            current_text = _TAG_RE.sub("", current_bio).strip()
            if len(page_bio) > len(current_text) * 0.9 and not page_bio.endswith("..."):
                write_bio(conn, cid, page_bio, source_label)
                print(f"    ✓ {name}: {len(current_text)} → {len(page_bio)} chars [{source_label}]")
                print(f"      {page_bio[:120]}...")
                return True

    return False


def fix_contact(conn, cur, cid, name, current_bio, fnd_website, employer, fname):
    """Try all strategies to get a non-truncated bio for one contact."""
    dname = display_name(name)
    src_type, src_domain = parse_source(current_bio)

    print(f"\n  [{cid}] {name}  (source: {src_type}:{src_domain or ''})")

    fnd_domain = to_domain(fnd_website)

    # Resolve employer domain
    employer_domain = None
    if employer and employer.lower() not in (fname or "").lower():
        employer_domain = resolve_employer_domain(employer)

    # Strategy 1: Re-search original source domain
    if src_type == "fnd" and src_domain:
        q = f'"{dname}" site:{src_domain}'
        if try_fetch_full(conn, cid, name, q, f"fnd:{src_domain}", current_bio):
            return True

    elif src_type == "emp" and src_domain:
        q = f'"{dname}" site:{src_domain}'
        if try_fetch_full(conn, cid, name, q, f"emp:{src_domain}", current_bio):
            return True

    # Strategy 2: Foundation website (if not already tried)
    if fnd_domain and fnd_domain != src_domain:
        q = f'"{dname}" site:{fnd_domain}'
        if try_fetch_full(conn, cid, name, q, f"fnd:{fnd_domain}", current_bio):
            return True

    # Strategy 3: Employer website (if not already tried)
    if employer_domain and employer_domain not in (src_domain, fnd_domain):
        q = f'"{dname}" site:{employer_domain}'
        if try_fetch_full(conn, cid, name, q, f"emp:{employer_domain}", current_bio):
            return True

    # Strategy 4: General search
    q = f'"{dname}" Louisiana (board OR director OR trustee OR foundation OR biography OR profile)'
    if try_fetch_full(conn, cid, name, q, "general", current_bio):
        return True

    print(f"    ✗ {name}: could not improve bio")
    return False


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT c.id, c.name, c.bio, c.employer,
               f.website, f.name AS fname
        FROM   centers_of_influence c
        LEFT JOIN foundations f ON c.foundation_id = f.id
        WHERE  (c.bio LIKE '%...' OR c.bio LIKE '%…')
          AND  c.bio IS NOT NULL
        ORDER  BY c.name
    """)
    rows = cur.fetchall()
    print(f"{len(rows)} truncated bios to fix\n")

    fixed = 0
    for cid, name, bio, employer, fnd_website, fname in rows:
        result = fix_contact(conn, cur, cid, name, bio, fnd_website, employer, fname)
        if result:
            fixed += 1

    print(f"\n{'='*60}")
    print(f"Done. Fixed: {fixed} / {len(rows)}")
    conn.close()


if __name__ == "__main__":
    main()
