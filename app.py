import os
import json
import threading
import time
import random
import uuid
import secrets
import string
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

app = Flask(__name__, template_folder='.')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-change-this')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

database_url = os.getenv('DATABASE_URL')
if database_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url.replace('postgres://', 'postgresql://')
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///nexus_security.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'reports'
app.config['SCAN_TIMEOUT'] = 60
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ---------- Supabase Client ----------
supabase_url = os.getenv('SUPABASE_URL')
supabase_anon_key = os.getenv('SUPABASE_KEY')
supabase_service_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
supabase: Client = create_client(supabase_url, supabase_anon_key)
supabase_admin: Client = create_client(supabase_url, supabase_service_key)

# ---------- Database ----------
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ---------- Database Models ----------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100))
    supabase_user_id = db.Column(db.String(36), unique=True, nullable=True)
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
    full_name = db.Column(db.String(100))
    role = db.Column(db.String(100))
    company_name = db.Column(db.String(100))
    user_email = db.Column(db.String(120))
    business_email = db.Column(db.String(120))
    verification_code = db.Column(db.String(10), nullable=True)

class VerificationToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    website = db.Column(db.String(500), nullable=False)
    plan = db.Column(db.String(50), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    used = db.Column(db.Boolean, default=False)

class PendingScan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    full_name = db.Column(db.String(100))
    role = db.Column(db.String(100))
    company_name = db.Column(db.String(100))
    user_email = db.Column(db.String(120))
    website_url = db.Column(db.String(500))
    business_email = db.Column(db.String(120))
    plan_type = db.Column(db.String(50))
    token = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    used = db.Column(db.Boolean, default=False)

class WebsiteVerificationCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    code = db.Column(db.String(10), unique=True, nullable=False)
    website_url = db.Column(db.String(500), nullable=False)
    plan_type = db.Column(db.String(50), nullable=False)
    form_data = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    verified = db.Column(db.Boolean, default=False)
    expires_at = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(hours=1))

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------- Helper: get or create user from Supabase user ----------
def get_or_create_user(supabase_user):
    email = supabase_user['email']
    name = supabase_user.get('user_metadata', {}).get('full_name', email.split('@')[0])
    supabase_id = supabase_user['id']
    user = User.query.filter_by(supabase_user_id=supabase_id).first()
    if not user:
        user = User(email=email, name=name, supabase_user_id=supabase_id)
        db.session.add(user)
        db.session.commit()
    return user

# ---------- Auth Routes (Supabase) ----------
@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/login/google')
def google_login():
    redirect_url = url_for('auth_callback', _external=True)
    response = supabase.auth.sign_in_with_oauth({
        "provider": "google",
        "options": {"redirect_to": redirect_url}
    })
    return redirect(response.url)

@app.route('/auth/callback')
def auth_callback():
    code = request.args.get('code')
    if not code:
        flash('Authentication failed.', 'danger')
        return redirect(url_for('login'))
    try:
        session_info = supabase.auth.exchange_code_for_session({'auth_code': code})
        user = session_info.user
        session['supabase_access_token'] = session_info.access_token
        db_user = get_or_create_user(user.dict())
        login_user(db_user)
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Authentication error: {str(e)}', 'danger')
        return redirect(url_for('login'))

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        user = res.user
        session['supabase_access_token'] = res.session.access_token
        db_user = get_or_create_user(user.dict())
        login_user(db_user)
        return jsonify({'success': True, 'message': 'Logged in'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 401

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    try:
        res = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"full_name": name}}
        })
        user = res.user
        if not user:
            return jsonify({'success': False, 'message': 'Sign-up failed'}), 400
        session['supabase_access_token'] = res.session.access_token if res.session else None
        db_user = get_or_create_user(user.dict())
        login_user(db_user)
        return jsonify({'success': True, 'message': 'Registration successful'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/logout')
@login_required
def logout():
    try:
        supabase.auth.sign_out()
    except:
        pass
    logout_user()
    session.clear()
    return redirect(url_for('index'))

# ---------- Email sending using Brevo HTTP API (no SMTP) ----------
def send_email_via_brevo(to_email, subject, body):
    api_key = os.getenv('BREVO_API_KEY')
    if not api_key:
        raise Exception("BREVO_API_KEY not set")
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json"
    }
    data = {
        "sender": {"name": "Nexus Security", "email": os.getenv('MAIL_DEFAULT_SENDER')},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": body
    }
    response = requests.post(url, json=data, headers=headers)
    if response.status_code not in (200, 201):
        raise Exception(f"Brevo API error: {response.text}")

# ---------- Simulated scanning ----------
def generate_vulnerabilities(plan_type, url):
    vulns = []
    if plan_type == 'basic':
        vulns = [
            {'name': 'Missing X-Frame-Options', 'severity': 'Medium', 'description': 'Clickjacking risk'},
            {'name': 'Insecure Cookie', 'severity': 'Low', 'description': 'Cookie missing Secure flag'}
        ]
    elif plan_type == 'advanced':
        vulns = [
            {'name': 'Missing X-Frame-Options', 'severity': 'Medium', 'description': 'Clickjacking risk'},
            {'name': 'Insecure Cookie', 'severity': 'Low', 'description': 'Cookie missing Secure flag'},
            {'name': 'SQL Injection (time-based)', 'severity': 'High', 'description': 'Parameter id vulnerable'},
            {'name': 'Stored XSS', 'severity': 'Medium', 'description': 'Comment field not sanitized'}
        ]
    elif plan_type == 'protection_plus':
        vulns = [
            {'name': 'Missing X-Frame-Options', 'severity': 'Medium', 'description': 'Clickjacking risk'},
            {'name': 'Insecure Cookie', 'severity': 'Low', 'description': 'Cookie missing Secure flag'},
            {'name': 'SQL Injection (time-based)', 'severity': 'High', 'description': 'Parameter id vulnerable'},
            {'name': 'Stored XSS', 'severity': 'Medium', 'description': 'Comment field not sanitized'},
            {'name': 'Critical: Remote Code Execution', 'severity': 'Critical', 'description': 'Unserialize user input'},
            {'name': 'Hardcoded Secret in JS', 'severity': 'High', 'description': 'API key exposed'}
        ]
    return vulns

def generate_report_for_job(job_id):
    job = ScanJob.query.get(job_id)
    if not job:
        return
    vulns = generate_vulnerabilities(job.plan_type, job.target_url)
    html = f"""<!DOCTYPE html>
<html>
<head><title>Security Report - {job.target_url}</title>
<style>
body {{ font-family: Arial; background: #0a0a0f; color: #fff; padding: 2rem; }}
h1 {{ color: #2f9b9b; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
th, td {{ border: 1px solid #2f9b9b; padding: 0.5rem; text-align: left; }}
th {{ background: #1a1a2a; }}
.critical {{ color: #ff5555; }}
.high {{ color: #ffaa55; }}
.medium {{ color: #ffff55; }}
.low {{ color: #55ff55; }}
</style>
</head>
<body>
<h1>Nexus Security Scan Report</h1>
<p><strong>Target:</strong> {job.target_url}</p>
<p><strong>Plan:</strong> {job.plan_type.upper()}</p>
<p><strong>Date:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
<h2>Vulnerabilities Found ({len(vulns)})</h2>
<table>
<tr><th>Name</th><th>Severity</th><th>Description</th></tr>
"""
    for v in vulns:
        severity_class = v['severity'].lower()
        html += f"<tr><td>{v['name']}</td><td class='{severity_class}'>{v['severity']}</td><td>{v['description']}</td></tr>"
    html += """</table>
<p>Remediation advice: Contact your developer to fix the issues listed above.</p>
<p>Nexus Security Team</p>
</body></html>"""
    filename = f"report_{job_id}_{int(time.time())}.html"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    with open(filepath, 'w') as f:
        f.write(html)
    job.report_path = filename
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    db.session.commit()
    db.session.expunge(job)

def background_worker():
    with app.app_context():
        while True:
            try:
                job = ScanJob.query.filter_by(status='pending').order_by(ScanJob.created_at).first()
                if job:
                    generate_report_for_job(job.id)
                    db.session.expunge_all()
                else:
                    time.sleep(5)
                db.session.commit()
                db.session.remove()
            except Exception as e:
                print(f"Background worker error: {e}")
                db.session.rollback()
                db.session.remove()
            time.sleep(10)

if not hasattr(app, 'scanner_started'):
    thread = threading.Thread(target=background_worker, daemon=True)
    thread.start()
    app.scanner_started = True

# ---------- Static Routes ----------
@app.route('/style.css')
def serve_css():
    return send_file('style.css')

@app.route('/script.js')
def serve_js():
    return send_file('script.js')

@app.route('/image.jpeg')
def serve_image():
    return send_file('image.jpeg')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/index.html')
def index_html():
    return render_template('index.html')

@app.route('/login.html')
def login_html():
    return render_template('login.html')

@app.route('/profile')
@login_required
def profile():
    scans = ScanJob.query.filter_by(user_id=current_user.id).order_by(ScanJob.created_at.desc()).all()
    return render_template('profile.html', user=current_user, scans=scans)

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/api/status')
def api_status():
    if current_user.is_authenticated:
        return jsonify({'logged_in': True, 'name': current_user.name, 'email': current_user.email})
    return jsonify({'logged_in': False})

# ---------- SCAN REQUEST: TWO PATHS ----------
@app.route('/api/request_scan', methods=['POST'])
@login_required
def request_scan():
    full_name = request.form.get('fullName')
    role = request.form.get('role')
    company_name = request.form.get('companyName')
    user_email = request.form.get('userEmail')
    website_url = request.form.get('websiteUrl')
    business_email = request.form.get('businessEmail')
    plan = request.form.get('plan')
    email_on_site = request.form.get('emailOnSite')

    if not all([full_name, role, company_name, user_email, website_url, business_email, plan, email_on_site]):
        return jsonify({'success': False, 'message': 'All fields required'}), 400

    if email_on_site == 'yes':
        try:
            url = website_url if website_url.startswith(('http://', 'https://')) else 'http://' + website_url
            response = requests.get(url, timeout=10, headers={'User-Agent': 'Nexus-Security-Bot'})
            if response.status_code != 200:
                return jsonify({'success': False, 'message': f'Could not reach website (HTTP {response.status_code})'}), 400
            if business_email.lower() in response.text.lower():
                token = secrets.token_urlsafe(32)
                pending = PendingScan(
                    user_id=current_user.id,
                    full_name=full_name,
                    role=role,
                    company_name=company_name,
                    user_email=user_email,
                    website_url=website_url,
                    business_email=business_email,
                    plan_type=plan,
                    token=token
                )
                db.session.add(pending)
                db.session.commit()
                try:
                    verify_url = url_for('verify_scan', token=token, _external=True)
                    email_body = f"Hello,<br><br>You requested a security scan for {website_url} ({plan} plan).<br>Please click the link below to confirm your email and start the scan:<br><br><a href='{verify_url}'>Confirm Scan</a><br><br>If you did not request this, please ignore this email.<br><br>Nexus Security Team"
                    send_email_via_brevo(business_email, 'Verify your scan request for Nexus Security', email_body)
                    return jsonify({'success': True, 'message': f'Verification email sent to {business_email}'})
                except Exception as mail_err:
                    db.session.rollback()
                    print(f"❌ Email sending failed: {mail_err}")
                    return jsonify({'success': False, 'message': f'Failed to send email: {str(mail_err)}'}), 500
            else:
                return jsonify({'success': False, 'message': f'Could not find {business_email} on {website_url}.'}), 400
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error checking website: {str(e)}'}), 500
    else:
        code = generate_verification_code()
        while WebsiteVerificationCode.query.filter_by(code=code).first():
            code = generate_verification_code()
        form_data = {
            'full_name': full_name,
            'role': role,
            'company_name': company_name,
            'user_email': user_email,
            'website_url': website_url,
            'business_email': business_email,
            'plan': plan
        }
        verification_entry = WebsiteVerificationCode(
            user_id=current_user.id,
            code=code,
            website_url=website_url,
            plan_type=plan,
            form_data=form_data,
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        db.session.add(verification_entry)
        db.session.commit()
        return jsonify({'success': True, 'code': code, 'token': verification_entry.id, 'message': 'Verification code generated'})

@app.route('/verify_scan/<token>')
def verify_scan(token):
    pending = PendingScan.query.filter_by(token=token, used=False).first()
    if not pending:
        return "Invalid or expired verification link.", 400

    prices = {'basic': 0, 'advanced': 99, 'protection_plus': 999}
    job = ScanJob(
        user_id=pending.user_id,
        target_url=pending.website_url,
        plan_type=pending.plan_type,
        price=prices.get(pending.plan_type, 0),
        payment_status='pending',
        full_name=pending.full_name,
        role=pending.role,
        company_name=pending.company_name,
        user_email=pending.user_email,
        business_email=pending.business_email
    )
    db.session.add(job)
    db.session.commit()
    pending.used = True
    db.session.commit()
    flash('Scan confirmed! We will start the scan shortly.', 'success')
    return redirect(url_for('profile'))

@app.route('/api/verify_code', methods=['POST'])
@login_required
def verify_code():
    data = request.get_json()
    verification_id = data.get('verification_id')
    website_url = data.get('website_url')
    verification = WebsiteVerificationCode.query.get(verification_id)
    if not verification or verification.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Invalid verification session'}), 400
    if verification.verified:
        return jsonify({'success': False, 'message': 'Code already verified'}), 400
    if verification.expires_at < datetime.utcnow():
        return jsonify({'success': False, 'message': 'Code expired. Please request a new scan.'}), 400
    try:
        url = website_url if website_url.startswith(('http://', 'https://')) else 'http://' + website_url
        resp = requests.get(url, timeout=10, headers={'User-Agent': 'Nexus-Verifier/1.0'})
        if resp.status_code != 200:
            return jsonify({'success': False, 'message': 'Could not reach website'}), 400
        if verification.code in resp.text:
            verification.verified = True
            fd = verification.form_data
            prices = {'basic': 0, 'advanced': 99, 'protection_plus': 999}
            job = ScanJob(
                user_id=current_user.id,
                target_url=fd['website_url'],
                plan_type=fd['plan'],
                price=prices.get(fd['plan'], 0),
                payment_status='pending',
                full_name=fd['full_name'],
                role=fd['role'],
                company_name=fd['company_name'],
                user_email=fd['user_email'],
                business_email=fd['business_email'],
                verification_code=verification.code
            )
            db.session.add(job)
            db.session.commit()
            return jsonify({'success': True, 'message': '✅ Verification successful! You can now start the scan.', 'job_id': job.id})
        else:
            return jsonify({'success': False, 'message': f'Code "{verification.code}" not found on your website. Make sure you added it to the HTML source.'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error checking website: {str(e)}'}), 500

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

@app.route('/test-email')
def test_email():
    try:
        send_email_via_brevo('hitesh.tanwar8318@gmail.com', 'Test Email from Nexus Security', '<p>This is a test email from your Flask app using Brevo API.</p>')
        return '✅ Email sent successfully! Check your inbox.'
    except Exception as e:
        return f'❌ Error: {str(e)}'

@app.route('/api/payment_mock', methods=['POST'])
def payment_mock():
    data = request.get_json()
    plan = data.get('plan')
    return jsonify({'success': True, 'payment_id': f'pay_{uuid.uuid4().hex[:12]}'})

if __name__ == '__main__':
    app.run(debug=True)
