Warning: Identity file D@fose420 not accessible: No such file or directory.
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
ORDER BY investment_assets DESC;-- Missing tables found in crm_app.py but not in schema.sql

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

-- Campaign management tables
CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    campaign_type TEXT, -- 'outreach', 'fundraising', 'partnership', 'education'
    start_date DATE,
    end_date DATE,
    status TEXT, -- 'planning', 'active', 'paused', 'completed'
    description TEXT,
    target_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS campaign_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER,
    target_type TEXT, -- 'foundation', 'personnel'
    target_id INTEGER,
    priority_score REAL,
    priority_rank INTEGER,
    status TEXT, -- 'not_contacted', 'contacted', 'interested', 'converted', 'rejected'
    notes TEXT,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);

CREATE TABLE IF NOT EXISTS campaign_activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER,
    target_id INTEGER,
    target_type TEXT, -- 'foundation', 'personnel'
    activity_type TEXT, -- 'email', 'call', 'meeting', 'proposal', 'follow_up'
    activity_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    outcome TEXT, -- 'no_response', 'positive', 'negative', 'pending'
    notes TEXT,
    follow_up_date DATE,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);

CREATE TABLE IF NOT EXISTS email_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    subject_template TEXT,
    body_template TEXT,
    target_segment TEXT -- 'ceo', 'cfo', 'board_chair', 'general'
);

-- Create indexes for campaign tables
CREATE INDEX idx_campaigns_status ON campaigns(status);
CREATE INDEX idx_campaign_targets_campaign ON campaign_targets(campaign_id);
CREATE INDEX idx_campaign_targets_priority ON campaign_targets(priority_rank);
CREATE INDEX idx_campaign_activities_campaign ON campaign_activities(campaign_id);

-- Additional indexes for performance
CREATE INDEX idx_personnel_990_name ON personnel_990(name);
CREATE INDEX idx_personnel_990_foundation ON personnel_990(foundation_id);
CREATE INDEX idx_centers_of_influence_name ON centers_of_influence(name);
CREATE INDEX idx_foundations_city ON foundations(city);
CREATE INDEX idx_foundations_state ON foundations(state);
CREATE INDEX idx_interactions_followup ON interactions(follow_up_date);
CREATE INDEX idx_data_sources_updated ON data_sources(last_updated);


-- Additional indexes for performance
CREATE INDEX idx_personnel_990_linkedin ON personnel_990(linkedin_url);
CREATE INDEX idx_foundations_website ON foundations(website);
CREATE INDEX idx_interactions_status ON interactions(status);
