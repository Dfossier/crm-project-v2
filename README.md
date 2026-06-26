# Louisiana Foundations CRM Database

## 🏛️ Project Overview
A comprehensive CRM system to identify, track, and manage relationships with every foundation in Louisiana that has more than $2M in investment assets. This system automatically gathers data from IRS filings and provides a web-based interface for relationship management.

## ✨ Features

### 📊 Data Collection
- **Automated Data Acquisition**: Fetches foundation data from multiple authoritative sources
- **Real-time Updates**: Regular sync with IRS databases and nonprofit registries
- **Data Validation**: Ensures accuracy and completeness of foundation information

### 🔍 Foundation Discovery
- **Asset Filtering**: Automatically identifies foundations with >$2M in investment assets
- **Geographic Focus**: Specifically targets Louisiana-based foundations
- **Classification**: Distinguishes between private, family, corporate, and community foundations

### 💼 CRM Capabilities
- **Contact Management**: Track interactions, meetings, calls, and correspondence
- **Grant History**: Monitor grant distributions and funding patterns
- **Personnel Tracking**: Board members, trustees, and key decision makers
- **Follow-up Management**: Automated reminders and task scheduling

### 📈 Analytics & Insights
- **Asset Distribution**: Visualize foundation assets across regions and categories
- **Grant Flow Analysis**: Understand giving patterns and trends
- **Market Intelligence**: Competitive landscape and opportunity identification

## 🚀 Quick Start

### 1. Installation
```bash
git clone <repository-url>
cd louisiana-foundations-crm
python setup.py
```

### 2. Data Acquisition
```bash
python run.py acquire
```
*This process takes 15-30 minutes and gathers data from multiple sources*

### 3. Launch CRM Interface
```bash
python run.py webapp
```
*Access the CRM at http://localhost:8501*

## 📋 Data Sources

### Primary Sources
1. **ProPublica Nonprofit Explorer API**
   - 3+ million tax-exempt organizations
   - Form 990, 990-EZ, and 990-PF data
   - Financial details and operational information

2. **IRS Annual Extract**
   - Official IRS database of tax-exempt organizations
   - Verified financial data and compliance status
   - Annual updates with latest filings

3. **Direct IRS Form Downloads**
   - Complete Form 990-PF documents
   - Detailed grant recipient information
   - Board composition and compensation data

### Data Quality
- **Automated Verification**: Cross-reference multiple sources for accuracy
- **Regular Updates**: Scheduled data refreshes to maintain currency
- **Manual Curation**: Ability to add corrections and additional information

## 🎯 Target Criteria

### Foundation Requirements
- **Location**: Headquartered in Louisiana
- **Asset Threshold**: Minimum $2,000,000 in investment assets
- **Organization Type**: 501(c)(3) private foundations, corporate foundations
- **Status**: Active and in good standing with IRS

### Expected Results
Based on preliminary research, this system should identify approximately:
- **50-100+ foundations** meeting the criteria
- **$500M - $2B+** in total managed assets
- **$25M - $100M+** in annual grant distributions

## 💾 Database Schema

### Core Tables
- **foundations**: Primary foundation information and financials
- **financial_history**: Year-over-year financial tracking
- **personnel**: Board members, trustees, and key staff
- **focus_areas**: Grant-making priorities and program areas
- **grants**: Individual grant records and recipients
- **interactions**: CRM contact history and notes

### Key Fields
- Basic info: Name, EIN, address, contact information
- Financial: Assets, revenue, expenses, grant distributions
- Leadership: Board composition, compensation, tenure
- Programs: Focus areas, geographic priorities, grant criteria
- History: Multi-year financial trends and grant patterns

## 🖥️ CRM Interface

### Dashboard
- **Overview Metrics**: Total foundations, assets, annual grants
- **Geographic Distribution**: Asset concentration by city/region
- **Size Analysis**: Foundation distribution by asset ranges
- **Trend Visualization**: Year-over-year growth and giving patterns

### Foundation Directory
- **Advanced Search**: Filter by name, location, asset size, focus areas
- **Sortable Columns**: Order by assets, grants, establishment date
- **Export Options**: CSV and Excel downloads for external analysis
- **Quick Actions**: Direct access to contact forms and interaction logs

### Foundation Profiles
- **Complete Overview**: All available information in organized sections
- **Financial Summary**: Assets, revenue, expenses with historical trends
- **Leadership Details**: Board composition, compensation, backgrounds
- **Grant Analysis**: Distribution patterns, recipient categories, award sizes
- **Contact History**: Chronological interaction log with follow-up tracking

### Relationship Management
- **Interaction Tracking**: Log calls, meetings, emails, proposals
- **Follow-up Management**: Schedule and track future contact points
- **Relationship Mapping**: Identify connections and mutual contacts
- **Opportunity Pipeline**: Track potential funding opportunities

## 🛠️ Technical Architecture

### Backend
- **Language**: Python 3.8+
- **Database**: SQLite (portable) with PostgreSQL option
- **APIs**: RESTful integration with data sources
- **Processing**: Pandas for data manipulation and analysis

### Frontend
- **Framework**: Streamlit for rapid development and deployment
- **Visualization**: Plotly for interactive charts and graphs
- **Export**: Native CSV/Excel download capabilities
- **Responsive**: Works on desktop, tablet, and mobile devices

### Data Pipeline
- **ETL Process**: Extract, Transform, Load from multiple sources
- **Scheduling**: Automated daily/weekly updates
- **Error Handling**: Robust retry logic and data validation
- **Monitoring**: Logging and alert system for data quality

## 📈 Usage Examples

### For Development Officers
- Identify high-capacity foundations in specific program areas
- Research foundation giving history and patterns
- Track cultivation activities and relationship development
- Monitor foundation board changes and leadership transitions

### For Executive Leadership
- Analyze market landscape and competitive positioning
- Track overall foundation sector health and trends
- Identify strategic partnership opportunities
- Monitor grant flow patterns in key program areas

### For Research Teams
- Generate prospect lists for specific campaigns or initiatives
- Analyze foundation investment and spending patterns
- Research best practices in foundation governance and operations
- Export data for external analysis and reporting

## 🔧 Advanced Configuration

### Customization Options
- **Asset Thresholds**: Adjust minimum asset requirements
- **Geographic Scope**: Expand or narrow geographic focus
- **Data Sources**: Enable/disable specific data providers
- **Update Frequency**: Configure automatic data refresh schedules

### Integration Capabilities
- **CRM Systems**: Export contacts to Salesforce, HubSpot, etc.
- **Email Marketing**: Integrate with MailChimp, Constant Contact
- **Analytics**: Connect to Tableau, Power BI for advanced visualization
- **Document Management**: Link to SharePoint, Google Drive for file storage

## 📞 Support and Documentation

### Getting Help
- **User Guide**: Comprehensive documentation in `/docs` folder
- **Video Tutorials**: Step-by-step walkthroughs for common tasks
- **FAQ**: Answers to frequently asked questions
- **Community**: User forum for questions and feature requests

### Troubleshooting
- **Common Issues**: Solutions to typical installation and setup problems
- **Performance Tips**: Optimization strategies for large datasets
- **Data Quality**: Best practices for maintaining accurate information
- **Backup/Recovery**: Procedures for data protection and restoration

## 🔒 Privacy and Compliance

### Data Security
- **Local Storage**: All data stored locally, no cloud dependencies
- **Access Control**: User authentication and permission management
- **Encryption**: Sensitive data protected with industry-standard encryption
- **Audit Trail**: Complete log of data access and modifications

### Ethical Considerations
- **Public Information**: Uses only publicly available IRS filings
- **Transparency**: Clear attribution of data sources and collection methods
- **Consent**: Respects foundation privacy preferences and communication wishes
- **Accuracy**: Commitment to maintaining accurate and up-to-date information

---

*This CRM system empowers organizations to build stronger relationships with Louisiana's philanthropic community through better information, analysis, and relationship management capabilities.*