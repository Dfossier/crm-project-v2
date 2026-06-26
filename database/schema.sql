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