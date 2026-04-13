"""
SCANNER BACKEND INTEGRATION
================================
This file handles:
- Receiving scan requests from your website users
- Sending them to Jatin's AI Scanner API
- Storing scan results
- Serving reports to users

Jatin's API: https://remix-kissing-michael-project.trycloudflare.com

HOW TO USE:
1. Save this file as scanner_backend.py
2. Install: pip install flask requests
3. Update JATIN_API_URL below with Jatin's IP
4. Run: python scanner_backend.py
5. Your website frontend calls /api/start-scan
"""

import os
import json
import time
import sqlite3
import hashlib
import requests
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# ========== CONFIGURATION ==========

# Jatin's AI Scanner API (UPDATE THIS)
JATIN_API_URL = "https://remix-kissing-michael-project.trycloudflare.com"  # <-- JATIN'S IP

# Your website domain
YOUR_DOMAIN = "https://nexussecurity.onrender.com"  # <-- YOUR DOMAIN

# ========== INITIALIZE FLASK ==========

app = Flask(__name__)
CORS(app)

# ========== DATABASE ==========

def init_db():
    conn = sqlite3.connect('scans.db')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT UNIQUE,
            user_email TEXT,
            url TEXT,
            plan TEXT,
            status TEXT,
            report_path TEXT,
            created_at TIMESTAMP,
            completed_at TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ Database ready")

# ========== HELPER FUNCTIONS ==========

def save_scan(scan_id, user_email, url, plan):
    conn = sqlite3.connect('scans.db')
    conn.execute('''
        INSERT INTO scans (scan_id, user_email, url, plan, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (scan_id, user_email, url, plan, 'pending', datetime.now()))
    conn.commit()
    conn.close()

def update_scan(scan_id, status, report_path=None):
    conn = sqlite3.connect('scans.db')
    if report_path:
        conn.execute('''
            UPDATE scans SET status = ?, report_path = ?, completed_at = ?
            WHERE scan_id = ?
        ''', (status, report_path, datetime.now(), scan_id))
    else:
        conn.execute('UPDATE scans SET status = ? WHERE scan_id = ?', (status, scan_id))
    conn.commit()
    conn.close()

def get_scan(scan_id):
    conn = sqlite3.connect('scans.db')
    cursor = conn.execute('SELECT * FROM scans WHERE scan_id = ?', (scan_id,))
    scan = cursor.fetchone()
    conn.close()
    return scan

# ========== SEND TO JATIN'S API ==========

def send_to_jatin_scanner(scan_id, url, plan):
    """Send scan request to Jatin's AI Scanner"""
    try:
        response = requests.post(
            f"{JATIN_API_URL}/api/scan/submit",
            json={
                'url': url,
                'plan': plan,
                'scan_id': scan_id,
                'webhook_url': f"{YOUR_DOMAIN}/api/scan-callback"
            },
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ Scan {scan_id} sent to Jatin's scanner")
            update_scan(scan_id, 'queued')
            return True
        else:
            print(f"❌ Failed: {response.text}")
            update_scan(scan_id, 'failed')
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        update_scan(scan_id, 'failed')
        return False

# ========== API ENDPOINTS ==========

@app.route('/api/start-scan', methods=['POST'])
def start_scan():
    """
    Your website calls this when user wants a scan
    Expects: { "url": "https://example.com", "plan": "advanced", "email": "user@example.com" }
    """
    data = request.json
    url = data.get('url')
    plan = data.get('plan', 'basic')
    user_email = data.get('email')
    
    if not url:
        return jsonify({'error': 'URL required'}), 400
    
    # Generate unique scan ID
    scan_id = hashlib.md5(f"{url}{user_email}{time.time()}".encode()).hexdigest()[:16]
    
    # Save to database
    save_scan(scan_id, user_email, url, plan)
    
    # Send to Jatin's scanner
    send_to_jatin_scanner(scan_id, url, plan)
    
    return jsonify({
        'scan_id': scan_id,
        'status': 'queued',
        'message': 'Scan started! Check status at /api/scan-status/' + scan_id
    })

@app.route('/api/scan-callback', methods=['POST'])
def scan_callback():
    """
    Jatin's scanner calls this when scan is complete
    """
    data = request.json
    scan_id = data.get('scan_id')
    report_url = data.get('report_url')
    status = data.get('status')
    
    print(f"📥 Callback received for scan {scan_id}: {status}")
    
    if status == 'completed' and report_url:
        try:
            # Download report from Jatin's server
            report_response = requests.get(report_url, timeout=30)
            
            if report_response.status_code == 200:
                # Save report locally
                os.makedirs('reports', exist_ok=True)
                report_filename = f"reports/scan_{scan_id}.html"
                with open(report_filename, 'wb') as f:
                    f.write(report_response.content)
                
                update_scan(scan_id, 'completed', report_filename)
                return jsonify({'status': 'ok'})
                
        except Exception as e:
            print(f"❌ Error downloading report: {e}")
            update_scan(scan_id, 'failed')
            return jsonify({'status': 'error'}), 500
    
    update_scan(scan_id, 'failed')
    return jsonify({'status': 'error'}), 400

@app.route('/api/scan-status/<scan_id>', methods=['GET'])
def scan_status(scan_id):
    """Check scan status"""
    scan = get_scan(scan_id)
    
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    
    # Column indices
    status_idx = 5
    report_path_idx = 6
    
    return jsonify({
        'scan_id': scan_id,
        'status': scan[status_idx],
        'report_ready': scan[report_path_idx] is not None
    })

@app.route('/api/download-report/<scan_id>', methods=['GET'])
def download_report(scan_id):
    """Download the security report"""
    scan = get_scan(scan_id)
    
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    
    report_path_idx = 6
    
    if scan[report_path_idx] and os.path.exists(scan[report_path_idx]):
        return send_file(
            scan[report_path_idx],
            as_attachment=True,
            download_name=f"security_report_{scan_id}.html"
        )
    
    return jsonify({'error': 'Report not ready'}), 404

@app.route('/api/health', methods=['GET'])
def health():
    """Check if backend is running"""
    return jsonify({'status': 'online', 'jatin_api': JATIN_API_URL})

# ========== START SERVER ==========

if __name__ == '__main__':
    init_db()
    os.makedirs('reports', exist_ok=True)
    print("\n" + "="*60)
    print("🚀 SCANNER BACKEND READY")
    print("="*60)
    print(f"Jatin's API: {JATIN_API_URL}")
    print(f"Your API: http://0.0.0.0:5000")
    print("\nEndpoints:")
    print("  POST /api/start-scan - Submit scan")
    print("  GET  /api/scan-status/<id> - Check status")
    print("  GET  /api/download-report/<id> - Download report")
    print("  GET  /api/health - Health check")
    print("="*60)
    
    app.run(host='0.0.0.0', port=5002, debug=False)