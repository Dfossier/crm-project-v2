#!/usr/bin/env python3
"""
Export foundation data to a static HTML file.
"""

import sqlite3
from pathlib import Path
import json

def export_to_html():
    """Export foundation data to a static HTML dashboard."""
    
    db_path = Path(__file__).parent / "database" / "louisiana_foundations.db"
    output_path = Path(__file__).parent / "foundation_dashboard.html"
    
    print("📊 Exporting Louisiana Foundation data to HTML...")
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Get summary stats
            cursor.execute("SELECT COUNT(*) FROM foundations")
            total = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM foundations WHERE investment_assets >= 2000000")
            qualifying = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(investment_assets), SUM(annual_grants) FROM foundations WHERE investment_assets >= 2000000")
            assets, grants = cursor.fetchone()
            assets = assets or 0
            grants = grants or 0
            
            # Get all qualifying foundations
            cursor.execute("""
                SELECT name, city, investment_assets, annual_grants, website, phone, ein, foundation_type 
                FROM foundations 
                WHERE investment_assets >= 2000000 
                ORDER BY investment_assets DESC
            """)
            foundations = cursor.fetchall()
            
            # Get personnel data
            cursor.execute("""
                SELECT f.name, p.name, p.title, p.role, p.compensation 
                FROM foundations f 
                JOIN personnel p ON f.id = p.foundation_id 
                WHERE f.investment_assets >= 2000000 
                ORDER BY f.investment_assets DESC, p.role
            """)
            personnel = cursor.fetchall()
            
            # Organize personnel by foundation
            personnel_by_foundation = {}
            for foundation_name, person_name, title, role, compensation in personnel:
                if foundation_name not in personnel_by_foundation:
                    personnel_by_foundation[foundation_name] = []
                personnel_by_foundation[foundation_name].append({
                    'name': person_name,
                    'title': title,
                    'role': role,
                    'compensation': compensation
                })
            
            # Generate HTML
            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Louisiana Foundation CRM - Complete Database</title>
    <style>
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
            margin: 0; padding: 20px; background-color: #f5f5f5; 
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ 
            background: linear-gradient(135deg, #1f4e79, #2d5aa0); 
            color: white; padding: 30px; border-radius: 12px; margin-bottom: 30px; text-align: center; 
        }}
        .header h1 {{ margin: 0; font-size: 2.5em; }}
        .header p {{ margin: 10px 0 0; opacity: 0.9; font-size: 1.1em; }}
        
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .stat-box {{ 
            background: white; padding: 20px; border-radius: 12px; text-align: center; 
            box-shadow: 0 2px 10px rgba(0,0,0,0.1); 
        }}
        .stat-number {{ font-size: 2.5em; font-weight: bold; color: #1f4e79; margin-bottom: 5px; }}
        .stat-label {{ color: #666; font-size: 0.95em; }}
        
        .search-box {{ 
            background: white; padding: 20px; border-radius: 12px; margin-bottom: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        #searchInput {{ 
            width: 100%; padding: 12px; border: 2px solid #ddd; border-radius: 8px; 
            font-size: 1.1em; box-sizing: border-box;
        }}
        #searchInput:focus {{ border-color: #1f4e79; outline: none; }}
        
        .foundations-grid {{ display: grid; gap: 20px; }}
        .foundation-card {{ 
            background: white; border-radius: 12px; padding: 25px; 
            box-shadow: 0 2px 15px rgba(0,0,0,0.1);
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .foundation-card:hover {{ 
            transform: translateY(-2px); 
            box-shadow: 0 4px 25px rgba(0,0,0,0.15); 
        }}
        
        .foundation-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 15px; }}
        .foundation-name {{ font-size: 1.3em; font-weight: bold; color: #1f4e79; margin: 0; }}
        .foundation-assets {{ font-size: 1.1em; font-weight: bold; color: #2d5aa0; }}
        
        .foundation-details {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 15px 0; }}
        .detail-item {{ display: flex; align-items: center; gap: 8px; color: #666; }}
        .detail-icon {{ width: 16px; text-align: center; }}
        
        .personnel-section {{ margin-top: 20px; }}
        .personnel-title {{ font-weight: bold; color: #1f4e79; margin-bottom: 10px; }}
        .personnel-list {{ background: #f8f9fa; padding: 15px; border-radius: 8px; }}
        .personnel-item {{ margin-bottom: 8px; font-size: 0.95em; }}
        .personnel-name {{ font-weight: 600; color: #333; }}
        .personnel-role {{ color: #666; font-size: 0.9em; }}
        
        .filter-stats {{ text-align: center; margin: 20px 0; color: #666; }}
        
        @media (max-width: 768px) {{
            .foundation-details {{ grid-template-columns: 1fr; }}
            .foundation-header {{ flex-direction: column; gap: 10px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏛️ Louisiana Foundation CRM</h1>
            <p>Complete Database of {qualifying} Louisiana Foundations with Investment Assets ≥ $2M</p>
        </div>
        
        <div class="stats">
            <div class="stat-box">
                <div class="stat-number">{qualifying}</div>
                <div class="stat-label">Qualifying Foundations<br>(≥$2M Assets)</div>
            </div>
            <div class="stat-box">
                <div class="stat-number">${assets/1e6:.0f}M</div>
                <div class="stat-label">Total Investment Assets</div>
            </div>
            <div class="stat-box">
                <div class="stat-number">${grants/1e6:.0f}M</div>
                <div class="stat-label">Annual Grant Distributions</div>
            </div>
            <div class="stat-box">
                <div class="stat-number">{(grants/assets)*100:.1f}%</div>
                <div class="stat-label">Average Payout Rate</div>
            </div>
        </div>
        
        <div class="search-box">
            <input type="text" id="searchInput" placeholder="🔍 Search foundations by name, city, or type..." onkeyup="filterFoundations()">
            <div class="filter-stats" id="filterStats">Showing all {qualifying} foundations</div>
        </div>
        
        <div class="foundations-grid" id="foundationsGrid">
"""
            
            # Generate foundation cards
            for i, (name, city, assets, grants, website, phone, ein, foundation_type) in enumerate(foundations):
                personnel_list = personnel_by_foundation.get(name, [])
                
                # Organize personnel by role
                officers = [p for p in personnel_list if p['role'] in ['president', 'cfo', 'secretary', 'vice_president']]
                board_members = [p for p in personnel_list if p['role'] == 'board_member']
                
                # Contact info
                contact_html = ""
                if website:
                    contact_html += f'<div class="detail-item"><span class="detail-icon">🌐</span><a href="{website}" target="_blank">Website</a></div>'
                if phone:
                    contact_html += f'<div class="detail-item"><span class="detail-icon">📞</span>{phone}</div>'
                
                # Personnel HTML
                personnel_html = ""
                if officers or board_members:
                    personnel_html = '<div class="personnel-section"><div class="personnel-title">Key Personnel</div><div class="personnel-list">'
                    
                    if officers:
                        for officer in officers:
                            comp = f"${officer['compensation']:,}" if officer['compensation'] > 0 else "No compensation"
                            personnel_html += f'<div class="personnel-item"><span class="personnel-name">{officer["name"]}</span> - {officer["title"]} ({comp})</div>'
                    
                    if board_members:
                        if officers:
                            personnel_html += '<div style="margin: 10px 0; color: #999;">Board Members:</div>'
                        for member in board_members:
                            comp = f"${member['compensation']:,}" if member['compensation'] > 0 else "Volunteer"
                            personnel_html += f'<div class="personnel-item"><span class="personnel-name">{member["name"]}</span> - {member["title"]} ({comp})</div>'
                    
                    personnel_html += '</div></div>'
                
                html += f"""
            <div class="foundation-card" data-name="{name.lower()}" data-city="{city.lower()}" data-type="{foundation_type or ''}">
                <div class="foundation-header">
                    <h3 class="foundation-name">{name}</h3>
                    <div class="foundation-assets">${assets/1e6:.1f}M</div>
                </div>
                
                <div class="foundation-details">
                    <div class="detail-item">
                        <span class="detail-icon">📍</span>
                        <span>{city}, Louisiana</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-icon">🎁</span>
                        <span>${grants/1e6:.1f}M annual grants</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-icon">🏛️</span>
                        <span>{foundation_type or 'Foundation'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-icon">🔢</span>
                        <span>EIN: {ein}</span>
                    </div>
                    {contact_html}
                </div>
                
                {personnel_html}
            </div>
"""
            
            html += f"""
        </div>
        
        <div style="margin-top: 40px; text-align: center; color: #666; border-top: 1px solid #ddd; padding-top: 20px;">
            <p><strong>Louisiana Foundation CRM</strong> - Generated on {__import__('datetime').datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
            <p>Data includes {total} total foundations, {qualifying} qualifying foundations with detailed financial and personnel information.</p>
        </div>
    </div>
    
    <script>
        function filterFoundations() {{
            const searchTerm = document.getElementById('searchInput').value.toLowerCase();
            const cards = document.querySelectorAll('.foundation-card');
            let visibleCount = 0;
            
            cards.forEach(card => {{
                const name = card.dataset.name || '';
                const city = card.dataset.city || '';
                const type = card.dataset.type || '';
                const text = card.textContent.toLowerCase();
                
                if (name.includes(searchTerm) || city.includes(searchTerm) || type.includes(searchTerm) || text.includes(searchTerm)) {{
                    card.style.display = 'block';
                    visibleCount++;
                }} else {{
                    card.style.display = 'none';
                }}
            }});
            
            document.getElementById('filterStats').textContent = 
                searchTerm ? `Showing ${{visibleCount}} of {qualifying} foundations` : 'Showing all {qualifying} foundations';
        }}
        
        // Add some interactive features
        document.addEventListener('DOMContentLoaded', function() {{
            console.log('Louisiana Foundation CRM Dashboard Loaded');
            console.log('Total foundations: {total}');
            console.log('Qualifying foundations: {qualifying}');
            console.log('Total assets: ${assets/1e6:.0f}M');
        }});
    </script>
</body>
</html>"""
            
        # Write the HTML file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"✅ HTML dashboard exported to: {output_path}")
        print(f"   Foundations: {qualifying} qualifying ({total} total)")
        print(f"   Assets: ${assets/1e6:.0f}M")
        print(f"   Grants: ${grants/1e6:.0f}M")
        print(f"   Personnel: {len(personnel)} records")
        print(f"\n🌐 Open this file in your browser:")
        print(f"   file://{output_path.absolute()}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error exporting HTML: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    export_to_html()