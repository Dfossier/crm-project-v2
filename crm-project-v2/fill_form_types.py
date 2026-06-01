import sqlite3, requests, io, re, urllib.parse, sys
import pypdf

DB = r'C:\Users\nickt\OneDrive\Desktop\Code Projects\990s\crm-project-v2\database\louisiana_foundations.db'
PDF_BASE = 'https://efast2-filings-public.s3.amazonaws.com/prd'
EFAST2_URL = 'https://www.efast.dol.gov/services/afs?q.parser=lucene&q={q}&size=100'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
    'Referer': 'https://www.efast.dol.gov/5500Search/',
}
RETIREMENT_PAT = re.compile(r'retirement|pension|401.?k|403.?b|profit.?shar|deferred.?comp', re.IGNORECASE)

def parse_pdf(pdf_url):
    """Return (form_type, sched_h_page) by scanning the PDF."""
    try:
        r = requests.get(pdf_url.split('#')[0], timeout=30)
        if r.status_code != 200:
            return None, None
        reader = pypdf.PdfReader(io.BytesIO(r.content))
        form_type = sched_h_page = None
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ''
            if form_type is None and i < 3:
                if re.search(r'Form\s+5500-EZ', text, re.IGNORECASE):
                    form_type = '5500-EZ'
                elif re.search(r'Form\s+5500-SF', text, re.IGNORECASE):
                    form_type = '5500-SF'
                elif re.search(r'Form\s+5500\b', text, re.IGNORECASE):
                    form_type = '5500'
            if sched_h_page is None and 'SCHEDULE H' in text.upper():
                sched_h_page = i + 1
            if form_type and sched_h_page:
                break
        return form_type, sched_h_page
    except Exception as e:
        print(f'  PDF error: {e}')
        return None, None

def efast2_fetch(ein):
    """Return (pdf_url_with_anchor, form_type) for best matching filing."""
    try:
        q = urllib.parse.quote(f'ein:{ein}')
        r = requests.get(EFAST2_URL.format(q=q), headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return None, None
        hits = r.json().get('hits', {}).get('hit', [])
        if not hits:
            return None, None
        large = [h for h in hits if int(h.get('fields', {}).get('participantsboy', 0) or 0) >= 100]
        pool = large if large else hits
        pool.sort(key=lambda h: h.get('fields', {}).get('datereceived', ''), reverse=True)
        retirement = [h for h in pool if RETIREMENT_PAT.search(h.get('fields', {}).get('planname', ''))]
        candidates = retirement if retirement else pool
        for candidate in candidates[:3]:
            pdf_path = candidate['fields'].get('pdfpath', '')
            if not pdf_path:
                continue
            pdf_url = PDF_BASE + pdf_path
            form_type, sched_h_page = parse_pdf(pdf_url)
            if sched_h_page:
                return f'{pdf_url}#page={sched_h_page}', form_type
        # fallback
        first_path = candidates[0]['fields'].get('pdfpath', '') if candidates else ''
        if first_path:
            pdf_url = PDF_BASE + first_path
            form_type, _ = parse_pdf(pdf_url)
            return pdf_url, form_type
        return None, None
    except Exception as e:
        print(f'  EFAST2 error: {e}')
        return None, None

conn = sqlite3.connect(DB)

# Phase 1: foundations with URL but no form type — parse their PDFs
phase1 = conn.execute(
    'SELECT id, name, form_5500_url FROM foundations WHERE form_5500_url IS NOT NULL AND (form_5500_type IS NULL OR form_5500_type="")'
).fetchall()
print(f'Phase 1: {len(phase1)} foundations with URL but no form type')
for fid, name, url in phase1:
    print(f'  {name[:50]}')
    form_type, sched_h_page = parse_pdf(url)
    new_url = url
    if sched_h_page and '#page=' not in url:
        base = url.split('#')[0]
        new_url = f'{base}#page={sched_h_page}'
    conn.execute('UPDATE foundations SET form_5500_type=?, form_5500_url=? WHERE id=?', (form_type, new_url, fid))
    conn.commit()
    print(f'    -> {form_type}, page {sched_h_page}')

# Phase 2: foundations with EIN but no URL
phase2 = conn.execute(
    'SELECT id, name, ein FROM foundations WHERE ein IS NOT NULL AND form_5500_url IS NULL'
).fetchall()
print(f'\nPhase 2: {len(phase2)} foundations to fetch from EFAST2')
found = 0
for fid, name, ein in phase2:
    ein_str = str(int(float(ein)))
    print(f'  {name[:50]} (EIN {ein_str})')
    link, form_type = efast2_fetch(ein_str)
    if link:
        conn.execute('UPDATE foundations SET form_5500_url=?, form_5500_type=? WHERE id=?', (link, form_type, fid))
        conn.commit()
        found += 1
        print(f'    -> {form_type}')
    else:
        print(f'    -> no filing found')

conn.close()
print(f'\nDone. Phase 2 found {found}/{len(phase2)} new filings.')
