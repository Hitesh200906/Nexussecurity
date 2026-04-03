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
from werkzeug.security import generate_password_hash, check_password_hash
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# --- Flask app configuration ---
app = Flask(__name__, template_folder='.')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-change-this')

# --- Database configuration (SQLite locally, PostgreSQL on Render) ---
database_url = os.getenv('DATABASE_URL')
if database_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url.replace('postgres://', 'postgresql://')
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///nexus_security.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'reports'
app.config['SCAN_TIMEOUT'] = 60

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Email configuration (read from .env) ---
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
    password_hash = db.Column(db.String(128), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    scans = db.relationship('ScanJob', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

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
    # New fields for user details
    full_name = db.Column(db.String(100))
    role = db.Column(db.String(100))
    company_name = db.Column(db.String(100))
    user_email = db.Column(db.String(120))
    business_email = db.Column(db.String(120))
    photo_path = db.Column(db.String(500), nullable=True)

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
    photo_path = db.Column(db.String(500), nullable=True)
    token = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    used = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Helper functions (generate_vulnerabilities, generate_report_for_job, background_worker) ---
# ... (keep exactly as in your existing code, no changes needed) ...

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

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename))

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

@app.route('/profile')
@login_required
def profile():
    scans = ScanJob.query.filter_by(user_id=current_user.id).order_by(ScanJob.created_at.desc()).all()
    return render_template('profile.html', user=current_user, scans=scans)

@app.route('/favicon.ico')
def favicon():
    return '', 204

# ========== NEW AUTH API ENDPOINTS ==========
@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')

    if not name or not email or not password:
        return jsonify({'success': False, 'message': 'Missing fields'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'message': 'Email already exists'}), 400

    user = User(email=email, name=name)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    login_user(user)
    return jsonify({'success': True, 'message': 'Registration successful'})

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'success': False, 'message': 'No account found with this email. Please sign up first.'}), 401
    if user.check_password(password):
        login_user(user)
        return jsonify({'success': True, 'message': 'Logged in'})
    else:
        return jsonify({'success': False, 'message': 'Incorrect password. Please try again.'}), 401

@app.route('/api/status')
def api_status():
    if current_user.is_authenticated:
        return jsonify({
            'logged_in': True,
            'name': current_user.name,
            'email': current_user.email
        })
    else:
        return jsonify({'logged_in': False})

# ========== SCAN REQUEST WITH EMAIL VERIFICATION ==========
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
    email_on_site = request.form.get('emailOnSite')  # 'yes' or 'no'
    photo = request.files.get('photo') if email_on_site == 'no' else None

    # Validation
    if not all([full_name, role, company_name, user_email, website_url, business_email, plan, email_on_site]):
        return jsonify({'success': False, 'message': 'All fields required'}), 400

    if email_on_site == 'no' and not photo:
        return jsonify({'success': False, 'message': 'Photo required when email not on site'}), 400

    # Save photo if provided
    photo_path = None
    if photo:
        photo_filename = f"{uuid.uuid4().hex}_{photo.filename}"
        photo_path = os.path.join(app.config['UPLOAD_FOLDER'], photo_filename)
        photo.save(photo_path)

    # Create pending scan record
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
        photo_path=photo_path,
        token=token
    )
    db.session.add(pending)
    db.session.commit()

    # Perform AI check if user said email is on site
    if email_on_site == 'yes':
        try:
            url = website_url if website_url.startswith(('http://', 'https://')) else 'http://' + website_url
            response = requests.get(url, timeout=10, headers={'User-Agent': 'Nexus-Security-Bot'})
            if response.status_code != 200:
                return jsonify({'success': False, 'message': 'Could not reach website'}), 400
            if business_email.lower() in response.text.lower():
                # Found – send verification email
                send_scan_verification_email(pending.token, business_email, website_url, plan)
                return jsonify({'success': True, 'message': 'Verification email sent'})
            else:
                return jsonify({'success': False, 'message': f'Could not find {business_email} on {website_url}.'}), 400
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error checking website: {str(e)}'}), 500
    else:
        # No – send verification email directly
        send_scan_verification_email(pending.token, business_email, website_url, plan)
        return jsonify({'success': True, 'message': 'Verification email sent'})

def send_scan_verification_email(token, email, website, plan):
    verify_url = url_for('verify_scan', token=token, _external=True)
    msg = Message(
        subject='Verify your scan request for Nexus Security',
        recipients=[email]
    )
    msg.body = f"""Hello,

You requested a security scan for {website} ({plan} plan).
Please click the link below to confirm your email and start the scan:

{verify_url}

If you did not request this, please ignore this email.

Nexus Security Team
"""
    mail.send(msg)

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
        business_email=pending.business_email,
        photo_path=pending.photo_path
    )
    db.session.add(job)
    db.session.commit()

    # Mark pending as used
    pending.used = True
    db.session.commit()

    # Start background scan (you'll implement this)
    # start_scan_background(job.id)

    flash('Scan confirmed! We will start the scan shortly. You will be notified when the report is ready.', 'success')
    return redirect(url_for('profile'))

# ========== AUTH ROUTES (Google OAuth) ==========
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

# ========== SCAN ROUTES (submit_scan removed, replaced by /api/request_scan) ==========
# Keep the view_report endpoint
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

# ========== EMAIL VERIFICATION ROUTES (for old verification tokens, kept for compatibility) ==========
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

# ========== API MOCK PAYMENT ==========
@app.route('/api/payment_mock', methods=['POST'])
def payment_mock():
    data = request.get_json()
    plan = data.get('plan')
    return jsonify({'success': True, 'payment_id': f'pay_{uuid.uuid4().hex[:12]}'})

if __name__ == '__main__':
    app.run(debug=True)