-- Louisiana Foundations CRM Database Schema

-- Main foundations table
CREATE TABLE foundations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ein TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    legal_name TEXT,
    foundation_type TEXT, -- 'private', 'corporate', 'community', 'family'
    
    -- Location information
    address TEXT,
    city TEXT,
    state TEXT DEFAULT 'LA',
    zip_code TEXT,
    phone TEXT,
    website TEXT,
    email TEXT,
    
    -- Financial data (most recent year)
    total_assets REAL,
    investment_assets REAL,
    annual_grants REAL,
    annual_revenue REAL,
    fiscal_year_end TEXT,
    filing_year INTEGER,
    
    -- Status
    tax_exempt_status TEXT,
    ruling_date TEXT,
    is_active BOOLEAN DEFAULT 1,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Ensure we only include foundations with >$2M in assets
    CONSTRAINT min_assets CHECK (investment_assets >= 2000000)
);

-- Historical financial data
CREATE TABLE financial_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    foundation_id INTEGER,
    filing_year INTEGER,
    total_assets REAL,
    investment_assets REAL,
    total_revenue REAL,
    total_expenses REAL,
    grants_paid REAL,
    administrative_expenses REAL,
    fundraising_expenses REAL,
    net_assets_change REAL,
    
    FOREIGN KEY (foundation_id) REFERENCES foundations(id),
    UNIQUE(foundation_id, filing_year)
);

-- Leadership and key personnel
CREATE TABLE personnel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    foundation_id INTEGER,
    name TEXT NOT NULL,
    title TEXT,
    role TEXT, -- 'trustee', 'officer', 'director', 'employee'
    compensation REAL,
    hours_per_week REAL,
    start_date TEXT,
    end_date TEXT,
    is_current BOOLEAN DEFAULT 1,
    
    FOREIGN KEY (foundation_id) REFERENCES foundations(id)
);

-- Grant focus areas and programs
CREATE TABLE focus_areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    foundation_id INTEGER,
    category TEXT, -- 'education', 'health', 'arts', 'environment', etc.
    subcategory TEXT,
    description TEXT,
    is_primary BOOLEAN DEFAULT 0,
    
    FOREIGN KEY (foundation_id) REFERENCES foundations(id)
);

-- Grant recipients and history (if available)
CREATE TABLE grants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    foundation_id INTEGER,
    recipient_name TEXT,
    recipient_ein TEXT,
    grant_amount REAL,
    grant_date TEXT,
    grant_purpose TEXT,
    grant_type TEXT, -- 'general', 'project', 'capacity', 'endowment'
    filing_year INTEGER,
    
    FOREIGN KEY (foundation_id) REFERENCES foundations(id)
);

-- Contact interactions and CRM data
CREATE TABLE interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    foundation_id INTEGER,
    interaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    interaction_type TEXT, -- 'call', 'email', 'meeting', 'proposal', 'grant'
    contact_person TEXT,
    subject TEXT,
    notes TEXT,
    follow_up_date DATE,
    status TEXT, -- 'pending', 'completed', 'scheduled'
    created_by TEXT,
    
    FOREIGN KEY (foundation_id) REFERENCES foundations(id)
);

-- Data sources and update tracking
CREATE TABLE data_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    foundation_id INTEGER,
    source TEXT, -- 'propublica', 'irs_extract', 'manual', 'website'
    source_url TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_quality_score INTEGER, -- 1-10 rating
    notes TEXT,
    
    FOREIGN KEY (foundation_id) REFERENCES foundations(id)
);

-- ─── Louisiana State Retirement Systems ───────────────────────────────────────

CREATE TABLE retirement_systems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    abbreviation TEXT,
    system_type TEXT,          -- 'statewide', 'parochial', 'municipal', 'specialty'
    website TEXT,
    phone TEXT,
    address TEXT,
    city TEXT DEFAULT 'Baton Rouge',
    state TEXT DEFAULT 'LA',
    zip_code TEXT,
    executive_director TEXT,
    cio TEXT,
    investment_consultant TEXT,
    actuary TEXT,
    custodian TEXT,
    total_assets REAL,         -- most recent, in dollars
    funded_ratio REAL,         -- 0–100 pct
    active_members INTEGER,
    retired_members INTEGER,
    asset_data_year INTEGER,   -- fiscal year for total_assets
    fiscal_year_end TEXT,      -- e.g. 'June 30'
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE system_financials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id INTEGER NOT NULL,
    fiscal_year INTEGER NOT NULL,
    total_assets REAL,
    actuarial_liability REAL,
    funded_ratio REAL,
    employer_contributions REAL,
    employee_contributions REAL,
    investment_return_pct REAL,
    benefits_paid REAL,
    active_members INTEGER,
    retired_members INTEGER,
    equity_pct REAL,
    fixed_income_pct REAL,
    alternatives_pct REAL,
    real_estate_pct REAL,
    cash_pct REAL,
    FOREIGN KEY (system_id) REFERENCES retirement_systems(id),
    UNIQUE (system_id, fiscal_year)
);

CREATE TABLE system_personnel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    title TEXT,
    role_type TEXT,            -- 'executive', 'board', 'investment_committee'
    is_executive_director BOOLEAN DEFAULT 0,
    is_cio BOOLEAN DEFAULT 0,
    is_board_chair BOOLEAN DEFAULT 0,
    phone TEXT,
    email TEXT,
    notes TEXT,
    FOREIGN KEY (system_id) REFERENCES retirement_systems(id),
    UNIQUE (system_id, name, title)
);

-- Create indexes for performance
CREATE INDEX idx_foundations_ein ON foundations(ein);
CREATE INDEX idx_foundations_assets ON foundations(investment_assets);
CREATE INDEX idx_foundations_name ON foundations(name);
CREATE INDEX idx_financial_year ON financial_history(filing_year);
CREATE INDEX idx_grants_amount ON grants(grant_amount);
CREATE INDEX idx_interactions_date ON interactions(interaction_date);
CREATE UNIQUE INDEX idx_personnel_990_unique ON personnel_990 (foundation_id, name, title, role_type, filing_year);

-- Create views for common queries
CREATE VIEW foundations_summary AS
SELECT 
    f.id,
    f.ein,
    f.name,
    f.city,
    f.investment_assets,
    f.annual_grants,
    f.website,
    COUNT(DISTINCT p.id) as personnel_count,
    COUNT(DISTINCT g.id) as grants_count,
    COUNT(DISTINCT i.id) as interactions_count
FROM foundations f
LEFT JOIN personnel p ON f.id = p.foundation_id AND p.is_current = 1
LEFT JOIN grants g ON f.id = g.foundation_id
LEFT JOIN interactions i ON f.id = i.foundation_id
GROUP BY f.id, f.ein, f.name, f.city, f.investment_assets, f.annual_grants, f.website;

CREATE VIEW top_foundations AS
SELECT *
FROM foundations
WHERE investment_assets >= 2000000
ORDER BY investment_assets DESC;