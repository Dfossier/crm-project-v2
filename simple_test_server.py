#!/usr/bin/env python3
"""
Simple test server for Foundation CRM data - no Streamlit dependencies.
"""

import sqlite3
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import urllib.parse

class FoundationHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.serve_dashboard()
        elif self.path.startswith('/api/foundations'):
            self.serve_api()
        else:
            self.send_error(404)
    
    def serve_dashboard(self):
        """Serve a simple HTML dashboard."""
        try:
            db_path = Path(__file__).parent / "database" / "louisiana_foundations.db"
            
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
                
                # Get top foundations
                cursor.execute("""
                    SELECT name, city, investment_assets, annual_grants 
                    FROM foundations 
                    WHERE investment_assets >= 2000000 
                    ORDER BY investment_assets DESC 
                    LIMIT 20
                """)
                top_foundations = cursor.fetchall()
                
                # Generate HTML
                html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Louisiana Foundation CRM</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .header {{ background: #1f4e79; color: white; padding: 20px; border-radius: 8px; }}
        .stats {{ display: flex; gap: 20px; margin: 20px 0; }}
        .stat-box {{ background: #f0f8ff; padding: 15px; border-radius: 8px; flex: 1; text-align: center; }}
        .stat-number {{ font-size: 2em; font-weight: bold; color: #1f4e79; }}
        .foundation-list {{ background: white; border: 1px solid #ddd; border-radius: 8px; }}
        .foundation {{ padding: 10px; border-bottom: 1px solid #eee; }}
        .foundation:last-child {{ border-bottom: none; }}
        .foundation-name {{ font-weight: bold; color: #1f4e79; }}
        .foundation-details {{ color: #666; font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🏛️ Louisiana Foundation CRM</h1>
        <p>Complete database of Louisiana foundations with >$2M in investment assets</p>
    </div>
    
    <div class="stats">
        <div class="stat-box">
            <div class="stat-number">{qualifying}</div>
            <div>Qualifying Foundations<br>(&gt;$2M assets)</div>
        </div>
        <div class="stat-box">
            <div class="stat-number">${assets/1e6:.0f}M</div>
            <div>Total Investment Assets</div>
        </div>
        <div class="stat-box">
            <div class="stat-number">${grants/1e6:.0f}M</div>
            <div>Annual Grant Distributions</div>
        </div>
        <div class="stat-box">
            <div class="stat-number">{total}</div>
            <div>Total Foundations<br>in Database</div>
        </div>
    </div>
    
    <h2>🏆 Top Louisiana Foundations by Assets</h2>
    <div class="foundation-list">
"""
                
                for i, (name, city, assets, grants) in enumerate(top_foundations, 1):
                    html += f"""
        <div class="foundation">
            <div class="foundation-name">{i}. {name}</div>
            <div class="foundation-details">
                📍 {city} | 💰 ${assets/1e6:.1f}M investment assets | 🎁 ${grants/1e6:.1f}M annual grants
            </div>
        </div>
"""
                
                html += """
    </div>
    
    <div style="margin-top: 30px; padding: 20px; background: #f9f9f9; border-radius: 8px;">
        <h3>🚀 System Status</h3>
        <p>✅ Database connection: Active</p>
        <p>✅ Foundation data: Complete</p>
        <p>✅ Simple HTTP server: Running</p>
        <p><strong>Ready for Streamlit integration!</strong></p>
    </div>
</body>
</html>
"""
                
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(html.encode())
            
        except Exception as e:
            self.send_error(500, str(e))
    
    def serve_api(self):
        """Serve JSON API for foundation data."""
        try:
            db_path = Path(__file__).parent / "database" / "louisiana_foundations.db"
            
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT name, city, investment_assets, annual_grants, website, phone
                    FROM foundations 
                    WHERE investment_assets >= 2000000 
                    ORDER BY investment_assets DESC
                """)
                
                foundations = []
                for row in cursor.fetchall():
                    foundations.append({
                        'name': row[0],
                        'city': row[1], 
                        'investment_assets': row[2],
                        'annual_grants': row[3],
                        'website': row[4],
                        'phone': row[5]
                    })
                
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(foundations, indent=2).encode())
            
        except Exception as e:
            self.send_error(500, str(e))

def run_server(port=8505):
    """Run the simple test server."""
    print(f"🌐 Starting Foundation CRM Test Server on port {port}")
    print(f"   URL: http://localhost:{port}")
    print("   Press Ctrl+C to stop")
    
    try:
        server = HTTPServer(('', port), FoundationHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Server stopped")
        server.shutdown()

if __name__ == "__main__":
    run_server()