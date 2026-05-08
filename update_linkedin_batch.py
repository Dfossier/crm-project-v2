#!/usr/bin/env python3
"""Update LinkedIn profiles for personnel records"""

import sqlite3
import sys

# LinkedIn profiles found from searches
profiles = {
    "Jerry E Shea Jr": "https://www.linkedin.com/in/jerry-shea-b59b2812",
    "Bill Fenstermaker": "https://www.linkedin.com/in/fenstermaker",
    "Missy Andrade": "https://www.linkedin.com/in/missy-bienvenu-andrade-81363b65",
    "JOE CALDARERA": "https://www.linkedin.com/in/joseph-caldarera-257a7137b",
    "LACEY SEYMOUR ELLIS PHD": "https://www.linkedin.com/in/lacey-ellis-phd",
    "JEANE MONTE M ED": "https://www.linkedin.com/in/jeanne-monte-57421352",
    "ALLISON SHARAI": "https://www.linkedin.com/in/allisonfsharai",
    "BRIAN CHERAMINE": "https://www.linkedin.com/in/brian-cheramie-2b387791",
    "JIM GARNER": "https://www.linkedin.com/in/jamesmgarner",
    "CATHERINE M SCHENDEL": "https://www.linkedin.com/in/catherine-mixon-schendel-86a9345a",
    "DR PAMELA SCHOOLER": "https://www.linkedin.com/in/pam-schooler-ed-d-65abbb241",
    "PEGGY COLEMAN": "https://www.linkedin.com/in/peggycolemanhw",
    "TRE'VON COOPER": "https://www.linkedin.com/in/treavon-cooper-801641233",
    "ANN BURGIN": "https://www.linkedin.com/in/dr-ann-burgin-a33b5630",
    "Gordan D Ford": "https://www.linkedin.com/in/gordan-ford-9bb535b4",
    "THERESA KUMSE": "https://www.linkedin.com/in/theresathaokumse",
    "CLYDE W MITCHELL": "https://www.linkedin.com/in/clyde-mitchell-078b533",
    "BILL COMEGYS": "https://www.linkedin.com/in/william-comegys-930b35127",
    "VALARIE JAMISON": "https://www.linkedin.com/in/valerie-jamison-44ba67373",
    "RONALD SHOLES": "https://www.linkedin.com/in/ron-sholes-bbb31116",
    "OSMAN KAZAN": "https://www.linkedin.com/in/osman-kazan-32155916b",
    "ZADELL DUDLEY": "https://www.linkedin.com/in/zazell-dudley-36930255",
    "JOHN PIERRE": "https://www.linkedin.com/in/john-pierre",
    "EDDIE BOETTNER": "https://www.linkedin.com/in/ed-boettner-b323809",
    "LUCY MCGRAW KARAM": "https://www.linkedin.com/in/lucy-karam-501a3143",
    "KIMBERLY L JOYCE": "https://www.linkedin.com/in/kimberly-joyce-norgress-5239244",
    "Christa Billeaud": "https://www.linkedin.com/in/clare-billeaud-24390ab0",
    "JUDGE ULYSSES GENE THIBODEAUX": "https://www.linkedin.com/in/judge-ulysses-thibodeaux-93b92539",
    "BUBBA RASBERRY": "https://www.linkedin.com/in/brandon-rasberry-7006291b",
    "ROBERT M STUART JR": "https://www.linkedin.com/in/robert-stuart-jr-0a330177",
    "MIKE WAMPOLD": "https://www.linkedin.com/in/michael-wampold-6bb5158",
    "REBECCA BONIOL": "https://www.linkedin.com/in/rebekah-boniol-83467353",
    "MURUGAN AMBALAKANNU": "https://www.linkedin.com/in/murugan-murugan-ba55b018a",
    "LISA C CRONIN": "https://www.linkedin.com/in/lisa-cronin-92b422123",
    "RONALD L FAIA JR": "https://www.linkedin.com/in/ron-faia-730160b8",
    "LEE ABRAHAM IIL": "https://www.linkedin.com/in/abraham-lee-53b6939",
    "KRISTI GUSTAVSON": "https://www.linkedin.com/in/kristi-gustafson-ab334549",
    "ARMAND ROOS": "https://za.linkedin.com/in/armandt-roos-35494b102",
    "HENRY SHANE": "https://www.linkedin.com/in/henry-shane-02a0a6a0",
    "MARK ROMIG": "https://www.linkedin.com/in/mark-romig-7378251b",
    "W CLINTON RASBERRY": "https://www.linkedin.com/in/clinton-rasberry-3a607a135",
    "PHYLLIS KETTLING": "https://nz.linkedin.com/in/phyllis-kettle-21116822b",
    "DENNIS O'CALLAGHAN": "https://www.linkedin.com/in/denis-o-callaghan-ph-d-45488944",
    "Deiadra Garrett": "https://www.linkedin.com/in/deadra-garrett-6805884a",
    "WANDA H THOMAS": "https://www.linkedin.com/in/wanda-thomas-4a297746",
    "VINICIO MADRIGAL": "https://cr.linkedin.com/in/marco-vinicio-madrigal-jim%C3%A9nez-518983170",
    "DR CHRIS MCCANLESS": "https://www.linkedin.com/in/chris-mccanless-550941122",
    "DAVID ABDEHOU": "https://www.linkedin.com/in/sahar-abdehou-69b32397",
    "NANCY GERMANY": "https://www.linkedin.com/in/nancy-germany-06b63666",
    "DONALD POSNER": "https://www.linkedin.com/in/daniel-posner-26b5a21b4",
    "DR MELVA WILLIAMS-TURNER": "https://www.linkedin.com/in/melvin-turner-6a17194",
    "William Weldon": "https://www.linkedin.com/in/william-weldon-173612b4",
    "MICHAEL NICLOSI": "https://www.linkedin.com/in/michael-nicolosi-747b6223b",
    "G STUART MURPHY IIT": "https://uk.linkedin.com/in/stuart-murphy-9088992a",
    "LONNIE PEELER": "https://www.linkedin.com/in/lonnie-williams-a3658010",
    "Hollis H Downs": "https://www.linkedin.com/in/hollis-downs-44063940",
    "RICHARD T DASPIT SR": "https://www.linkedin.com/in/richarddaspit",
    "LOUIS HERRERO": "https://www.linkedin.com/in/louis-herrero-6b443339",
    "Raymond J Hebert": "https://www.linkedin.com/in/raymond-hebert-7b339b112",
    "GLENN KINSEY": "https://www.linkedin.com/in/glenn-kinsey-6ba5864",
    "DIANE HOLLIS": "https://www.linkedin.com/in/diane-hollis-b6b056a3",
    "EMRAH SARAC": "https://tr.linkedin.com/in/emrah-sara%C3%A7-1838a019",
    "KASHANTA HARRIS": "https://www.linkedin.com/in/keshante-harris-354908373",
    "ORHAN KIZILKAYA": "https://tr.linkedin.com/in/orhan-k%C4%B1z%C4%B1lkaya-392829112",
    "SEZAI CANKIRLI": "https://tr.linkedin.com/in/sezaiozcelik/en",
    "ANN STOKES": "https://www.linkedin.com/in/ann-stokes-b86247105",
    "COLLIN STANSBERRY": "https://www.linkedin.com/in/colin-stansberry-568329377",
    "JOSPEH SCHONACHER": "https://www.linkedin.com/in/joseph-schonacher-b82332104",
    "FATHER RALPH HOWE": "https://ca.linkedin.com/in/ralph-howe-3665b1154",
    "ALLEN MORAN OP": "https://www.linkedin.com/in/allen-moran-o-p-4273919",
    "SR ANNE CATHERINE BURLEIGH": "https://www.linkedin.com/in/anne-burleigh-20163589",
    "LOUIS MORRONE OP": "https://www.linkedin.com/in/louis-morrone-036390101",
    "THOMAS M CONDON OP": "https://www.linkedin.com/in/tom-condon-995a664",
    "KENNETH R LETOILE OP": "https://www.linkedin.com/in/kenneth-letoile-2a83b613",
    "SEBASTIAN WHITE OP": "https://www.linkedin.com/in/sebastian-white-01828860",
    "DARREN PIERRE OP": "https://www.linkedin.com/in/darren-pierre-7224a9247",
    "ROBERTO MERCED OP": "https://www.linkedin.com/in/robert-merced-sr-14456a214",
    "CHARLES A HONORE": "https://www.linkedin.com/in/dr-charles-honore-yamessou-08778416"
}

def normalize_name(name):
    """Normalize name for comparison"""
    return name.lower().replace(".", "").replace("-", "").strip()

def main():
    conn = sqlite3.connect('database/louisiana_foundations.db')
    cursor = conn.cursor()
    
    # First ensure columns exist
    cursor.execute("PRAGMA table_info(personnel_990)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if "notes" not in columns:
        cursor.execute("ALTER TABLE personnel_990 ADD COLUMN notes TEXT")
        print("Added notes column")
    
    updated = 0
    not_found = []
    
    for search_name, url in profiles.items():
        search_normalized = normalize_name(search_name)
        
        # Get all personnel and try to match
        cursor.execute("SELECT id, name, title FROM personnel_990 WHERE linkedin_url IS NULL OR linkedin_url = ''")
        rows = cursor.fetchall()
        
        matched = False
        for row in rows:
            db_id, db_name, db_title = row
            db_normalized = normalize_name(db_name)
            
            # Check for name match
            if search_normalized in db_normalized or db_normalized in search_normalized:
                cursor.execute(
                    "UPDATE personnel_990 SET linkedin_url = ?, notes = ? WHERE id = ?",
                    (url, f"Found LinkedIn profile", db_id)
                )
                updated += 1
                print(f"Updated: {db_name} (id={db_id})")
                matched = True
                break
        
        if not matched:
            not_found.append(search_name)
    
    conn.commit()
    
    print(f"\n{'='*60}")
    print(f"Updated {updated} records")
    
    if not_found:
        print(f"\nCould not match these names:")
        for name in not_found:
            print(f"  - {name}")
    
    conn.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())