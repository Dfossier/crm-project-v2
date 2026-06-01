-- Missing tables found in crm_app.py but not in schema.sql

-- Investment advisors (legacy table)
CREATE TABLE IF NOT EXISTS investment_advisors (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 foundation_id INTEGER,
 advisor_name TEXT,
 advisor_ein TEXT,
 annual_fee REAL,
 fee_type TEXT, -- 'percentage', 'flat', 'tiered'
 fee_percentage REAL,
 assets_managed REAL,
 services TEXT,
 contract_start TEXT,
 FOREIGN KEY (foundation_id) REFERENCES foundations(id)
);

-- Detailed 990 personnel data
CREATE TABLE IF NOT EXISTS personnel_990 (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 foundation_id INTEGER,
 name TEXT NOT NULL,
 title TEXT,
 compensation REAL,
 benefits REAL,
 hours_per_week REAL,
 is_president BOOLEAN DEFAULT 0,
 is_ceo BOOLEAN DEFAULT 0,
 is_cfo BOOLEAN DEFAULT 0,
 is_vice_president BOOLEAN DEFAULT 0,
 is_secretary BOOLEAN DEFAULT 0,
 is_treasurer BOOLEAN DEFAULT 0,
 is_director BOOLEAN DEFAULT 0,
 is_trustee BOOLEAN DEFAULT 0,
 is_officer BOOLEAN DEFAULT 0,
 is_990_filer BOOLEAN DEFAULT 0,
 linkedin_url TEXT,
 related_organization TEXT,
 FOREIGN KEY (foundation_id) REFERENCES foundations(id)
);

-- Investment portfolio details
CREATE TABLE IF NOT EXISTS investment_details (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 foundation_id INTEGER,
 filing_year INTEGER,
 securities_publicly_traded REAL,
 securities_other REAL,
 program_related_investments REAL,
 other_investments REAL,
 dividend_income REAL,
 interest_income REAL,
 capital_gains REAL,
 investment_expenses REAL,
 net_investment_income REAL,
 FOREIGN KEY (foundation_id) REFERENCES foundations(id)
);

-- Consultants and professional services
CREATE TABLE IF NOT EXISTS consultants_990 (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 foundation_id INTEGER,
 name TEXT NOT NULL,
 service_type TEXT, -- 'legal', 'accounting', 'investment', 'management', 'other'
 amount_paid REAL,
 is_investment_advisor BOOLEAN DEFAULT 0,
 fee_percentage REAL,
 description TEXT,
 FOREIGN KEY (foundation_id) REFERENCES foundations(id)
);

-- Centers of Influence (board members for introductions)
CREATE TABLE IF NOT EXISTS centers_of_influence (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 foundation_id INTEGER,
 name TEXT NOT NULL,
 title TEXT,
 location TEXT,
 linkedin_url TEXT,
 notes TEXT,
 FOREIGN KEY (foundation_id) REFERENCES foundations(id)
);

-- Create indexes
CREATE INDEX idx_personnel_990_foundation ON personnel_990(foundation_id);
CREATE INDEX idx_investment_details_foundation ON investment_details(foundation_id);
CREATE INDEX idx_consultants_990_foundation ON consultants_990(foundation_id);
CREATE INDEX idx_centers_of_influence_foundation ON centers_of_influence(foundation_id);
CREATE INDEX idx_investment_advisors_foundation ON investment_advisors(foundation_id);
