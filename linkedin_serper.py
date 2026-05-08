#!/usr/bin/env python3
"""
LinkedIn profile search via Serper.dev
Searches personnel_990 records without linkedin_url and writes confirmed hits back to DB.
Two-pass: (1) name + foundation, (2) name + Louisiana fallback.
"""
import sqlite3, requests, json, time, re
from pathlib import Path

DB_PATH = "/home/dfoss/crm/database/louisiana_foundations.db"
import os
API_KEY = os.getenv("SERPER_API_KEY")
LOG_PATH = "/home/dfoss/crm/linkedin_serper_log.json"
DELAY = 0.5  # seconds between requests

# Prefixes/suffixes to strip from names before searching
_STRIP = re.compile(
    r"\b(DR|REV|VERY REV|SR|MR|MRS|MS|PROF|"
    r"JR|SR|II|III|IV|IIT|"
    r"MD|PHD|PHD|DO|DDS|ESQ|AHOS|"
    r"OP|M\.?ED\.?)\b\.?",
    re.IGNORECASE
)

def clean_name(name):
    name = _STRIP.sub("", name)
    name = re.sub(r"\s{2,}", " ", name).strip().strip(".")
    return name

def _query(q):
    resp = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": API_KEY, "Content-Type": "application/json"},
        json={"q": q, "num": 5},
        timeout=10
    )
    resp.raise_for_status()
    for r in resp.json().get("organic", []):
        url = r.get("link", "")
        if "linkedin.com/in/" in url:
            match = re.match(r"(https://[a-z]+\.linkedin\.com/in/[^/?#]+)", url)
            if match:
                return match.group(1), r.get("title", ""), r.get("snippet", "")
    return None, None, None

def search_linkedin(name, foundation):
    cleaned = clean_name(name)
    # Pass 1: cleaned name + foundation
    url, title, snippet = _query(f'"{cleaned}" "{foundation}" site:linkedin.com/in')
    if url:
        return url, title, snippet, "foundation"
    # Pass 2: cleaned name + Louisiana
    url, title, snippet = _query(f'"{cleaned}" "Louisiana" site:linkedin.com/in')
    if url:
        return url, title, snippet, "louisiana"
    return None, None, None, None

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT p.id, p.name, p.title, f.name
        FROM personnel_990 p
        JOIN foundations f ON p.foundation_id = f.id
        WHERE p.linkedin_url IS NULL OR p.linkedin_url = ''
        ORDER BY p.id
    """)
    rows = cur.fetchall()
    print(f"Searching {len(rows)} people...")

    log = []
    found = 0

    for i, (pid, name, title, foundation) in enumerate(rows):
        print(f"[{i+1}/{len(rows)}] {name} ({foundation[:35]})", end="... ", flush=True)
        try:
            url, title_text, snippet, method = search_linkedin(name, foundation)
            if url:
                cur.execute("UPDATE personnel_990 SET linkedin_url = ? WHERE id = ?", (url, pid))
                conn.commit()
                found += 1
                print(f"FOUND ({method}): {url}")
                log.append({"id": pid, "name": name, "foundation": foundation,
                            "linkedin_url": url, "title": title_text,
                            "snippet": snippet, "method": method, "status": "found"})
            else:
                print("not found")
                log.append({"id": pid, "name": name, "foundation": foundation,
                            "linkedin_url": None, "status": "not_found"})
        except Exception as e:
            print(f"ERROR: {e}")
            log.append({"id": pid, "name": name, "foundation": foundation,
                        "linkedin_url": None, "status": "error", "error": str(e)})
        time.sleep(DELAY)

    conn.close()
    Path(LOG_PATH).write_text(json.dumps(log, indent=2))
    print(f"\nDone. Found {found}/{len(rows)} profiles. Log: {LOG_PATH}")

if __name__ == "__main__":
    main()
