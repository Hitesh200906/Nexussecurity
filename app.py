import os
import json
import threading
import time
import random
import uuid
import secrets
import string
import hashlib
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from supabase import create_client, Client
import razorpay

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
    credits = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    scans = db.relationship('ScanJob', backref='user', lazy=True)

class ScanJob(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    target_url = db.Column(db.String(500), nullable=False)
    plan_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(50), default='queued')
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
    scan_id = db.Column(db.String(32), nullable=True)
    credits_spent = db.Column(db.Integer, default=0)

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

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    credits_added = db.Column(db.Integer, nullable=False)
    razorpay_order_id = db.Column(db.String(100))
    razorpay_payment_id = db.Column(db.String(100))
    status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='transactions')

# ---------- Admin Settings Model ----------
class AdminSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True, default=1)
    passcode_hash = db.Column(db.String(256), nullable=False)
    credit_costs = db.Column(db.JSON, default={"basic": 0, "advanced": 10, "protection_plus": 25})
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

with app.app_context():
    db.create_all()
    admin = AdminSettings.query.get(1)
    if not admin:
        default_hash = generate_password_hash("nexus admin")
        admin = AdminSettings(id=1, passcode_hash=default_hash)
        db.session.add(admin)
        db.session.commit()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------- Helper functions ----------
def get_or_create_user(supabase_user):
    email = supabase_user['email']
    name = supabase_user.get('user_metadata', {}).get('full_name', email.split('@')[0])
    supabase_id = supabase_user['id']
    user = User.query.filter_by(supabase_user_id=supabase_id).first()
    if not user:
        user = User(email=email, name=name, supabase_user_id=supabase_id, credits=0)
        db.session.add(user)
        db.session.commit()
    return user

def generate_verification_code():
    chars = [c for c in string.ascii_uppercase + string.digits if c not in 'O0I1']
    return ''.join(random.choices(chars, k=6))

def get_credit_costs():
    admin = AdminSettings.query.get(1)
    if admin and admin.credit_costs:
        return admin.credit_costs
    return {"basic": 0, "advanced": 10, "protection_plus": 25}

def is_admin():
    return current_user.is_authenticated and current_user.email == 'nexussecurity777@gmail.com'

# ---------- Email sending using Brevo ----------
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

# ---------- Razorpay Payment Integration ----------
razorpay_client = razorpay.Client(auth=(os.getenv('RAZORPAY_KEY_ID'), os.getenv('RAZORPAY_KEY_SECRET')))

@app.route('/api/create-order', methods=['POST'])
@login_required
def create_order():
    data = request.get_json()
    credits = data.get('credits')
    amount = data.get('amount')  # amount in INR
    
    if not credits or not amount:
        return jsonify({'success': False, 'message': 'Invalid request'}), 400
    
    # Convert amount to paise (Razorpay expects paise)
    amount_paise = int(amount * 100)
    
    try:
        order_data = {
            'amount': amount_paise,
            'currency': 'INR',
            'receipt': f'credits_{current_user.id}_{int(datetime.utcnow().timestamp())}',
            'payment_capture': 1
        }
        order = razorpay_client.order.create(order_data)
        
        # Store transaction in database
        transaction = Transaction(
            user_id=current_user.id,
            amount=amount,
            credits_added=credits,
            razorpay_order_id=order['id'],
            status='pending'
        )
        db.session.add(transaction)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'order_id': order['id'],
            'amount': amount,
            'currency': 'INR',
            'key': os.getenv('RAZORPAY_KEY_ID')
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/verify-payment', methods=['POST'])
@login_required
def verify_payment():
    data = request.get_json()
    order_id = data.get('order_id')
    payment_id = data.get('payment_id')
    signature = data.get('signature')
    
    try:
        # Verify signature
        params_dict = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }
        razorpay_client.utility.verify_payment_signature(params_dict)
        
        # Find transaction
        transaction = Transaction.query.filter_by(razorpay_order_id=order_id, user_id=current_user.id).first()
        if not transaction:
            return jsonify({'success': False, 'message': 'Transaction not found'}), 404
        
        # Update transaction and add credits to user
        transaction.razorpay_payment_id = payment_id
        transaction.status = 'completed'
        current_user.credits = (current_user.credits or 0) + transaction.credits_added
        db.session.commit()
        
        return jsonify({'success': True, 'message': f'Added {transaction.credits_added} credits to your account!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

# ---------- Auth Routes (Supabase) ----------
@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/login/google')
def google_login():
    base_url = os.getenv('BASE_URL')
    if not base_url:
        base_url = request.host_url.rstrip('/')
    callback_url = f"{base_url}/auth/callback"
    response = supabase.auth.sign_in_with_oauth({
        "provider": "google",
        "options": {"redirect_to": callback_url}
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
        access_token = session_info.session.access_token if session_info.session else None
        session['supabase_access_token'] = access_token
        db_user = get_or_create_user(user.dict())
        login_user(db_user)
        return redirect(url_for('index'))
    except Exception as e:
        app.logger.error(f"Auth callback error: {str(e)}")
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

# ---------- Registration with email verification ----------
@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    
    if not name or not email or not password:
        return jsonify({'success': False, 'message': 'All fields required'}), 400
    
    # Check if user already exists in Supabase
    try:
        supabase.auth.sign_in_with_password({"email": email, "password": "dummy"})
    except Exception as e:
        error_str = str(e)
        if 'Invalid login credentials' in error_str or 'User not found' in error_str:
            pass
        else:
            pass
    
    # Generate a 6-digit code
    code = ''.join(random.choices('0123456789', k=6))
    
    # Store pending data in session (expires in 10 minutes)
    session['pending_signup'] = {
        'name': name,
        'email': email,
        'password': password,
        'code': code,
        'expires': (datetime.utcnow() + timedelta(minutes=10)).timestamp()
    }
    
    # Send email with code
    subject = "Verify your email - Nexus Security"
    body = f"""
    <h2>Email Verification</h2>
    <p>Hello {name},</p>
    <p>Thank you for registering with Nexus Security.</p>
    <p>Your verification code is: <strong style="font-size: 24px; color: #2f9b9b;">{code}</strong></p>
    <p>This code will expire in 10 minutes.</p>
    <p>If you didn't request this, please ignore this email.</p>
    <br>
    <p>Nexus Security Team</p>
    """
    try:
        send_email_via_brevo(email, subject, body)
        return jsonify({'success': True, 'message': 'Verification code sent to your email', 'requires_verification': True})
    except Exception as e:
        session.pop('pending_signup', None)
        return jsonify({'success': False, 'message': f'Failed to send email: {str(e)}'}), 500

@app.route('/api/verify-email-code', methods=['POST'])
def verify_email_code():
    data = request.get_json()
    code = data.get('code')
    
    pending = session.get('pending_signup')
    if not pending:
        return jsonify({'success': False, 'message': 'No pending registration. Please start over.'}), 400
    
    if datetime.utcnow().timestamp() > pending['expires']:
        session.pop('pending_signup', None)
        return jsonify({'success': False, 'message': 'Verification code expired. Please register again.'}), 400
    
    if code != pending['code']:
        return jsonify({'success': False, 'message': 'Invalid verification code'}), 400
    
    name = pending['name']
    email = pending['email']
    password = pending['password']
    
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
        session.pop('pending_signup', None)
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

# ---------- Public credit costs ----------
@app.route('/api/credit-costs')
def public_credit_costs():
    return jsonify(get_credit_costs())

# ---------- Friend's AI Scanner Integration ----------
JATIN_API_URL = os.getenv('JATIN_API_URL', 'https://monitor-oops-powerpoint-meyer.trycloudflare.com')
CALLBACK_URL = os.getenv('CALLBACK_URL', 'https://nexussecurity.onrender.com/api/scan-callback')

def send_to_friend_scanner(scan_id, url, plan, user_email):
    if not JATIN_API_URL:
        print("❌ JATIN_API_URL not configured.")
        return False

    plan_mapping = {'basic': 'basic', 'advanced': 'advanced', 'protection_plus': 'ultimate'}
    external_plan = plan_mapping.get(plan, 'basic')

    full_url = f"{JATIN_API_URL}/api/scan/submit"
    payload = {
        'url': url,
        'plan': external_plan,
        'scan_id': scan_id,
        'webhook_url': CALLBACK_URL
    }
    print(f"📤 Sending scan to {full_url} with payload: {payload}")
    try:
        response = requests.post(full_url, json=payload, timeout=15)
        print(f"✅ Scanner responded with status {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Scanner accepted scan, remote_scan_id: {data.get('scan_id')}")
            return True
        else:
            print(f"❌ Scanner error: {response.text}")
            return False
    except requests.exceptions.Timeout:
        print("❌ Request to scanner timed out after 15 seconds")
        return False
    except Exception as e:
        print(f"❌ Unexpected error calling scanner: {e}")
        return False

def deduct_credits(user, plan_type):
    costs = get_credit_costs()
    cost = costs.get(plan_type, 0)
    if cost == 0:
        return True
    if (user.credits or 0) >= cost:
        user.credits -= cost
        db.session.commit()
        return True
    return False

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

@app.route('/legal.html')
def legal():
    return render_template('legal.html')

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

# ---------- Admin Routes ----------
@app.route('/api/admin/check')
@login_required
def admin_check():
    return jsonify({'is_admin': is_admin()})

@app.route('/api/admin/verify-passcode', methods=['POST'])
@login_required
def admin_verify_passcode():
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    data = request.json
    passcode = data.get('passcode')
    admin = AdminSettings.query.get(1)
    if admin and check_password_hash(admin.passcode_hash, passcode):
        session['admin_authenticated'] = True
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Invalid passcode'}), 401

@app.route('/api/admin/request-reset', methods=['POST'])
@login_required
def admin_request_reset():
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    token = secrets.token_urlsafe(32)
    session['admin_reset_token'] = token
    reset_url = url_for('admin_reset_page', token=token, _external=True)
    email_body = f"<p>Click the link below to reset your admin passcode:</p><p><a href='{reset_url}'>Reset Passcode</a></p><p>This link expires in 10 minutes.</p>"
    try:
        send_email_via_brevo('nexussecurity777@gmail.com', 'Admin Passcode Reset', email_body)
        return jsonify({'success': True, 'message': 'Reset email sent'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/reset/<token>')
def admin_reset_page(token):
    if session.get('admin_reset_token') != token:
        return "Invalid or expired token", 400
    return '''
    <!DOCTYPE html>
    <html>
    <head><title>Reset Admin Passcode</title><style>body{background:#000;color:#fff;font-family:Arial;text-align:center;padding:2rem;}input,button{padding:0.5rem;margin:0.5rem;}</style></head>
    <body>
        <h2>Reset Admin Passcode</h2>
        <form id="resetForm">
            <input type="password" id="new_passcode" placeholder="New passcode" required>
            <button type="submit">Reset</button>
        </form>
        <div id="message"></div>
        <script>
            document.getElementById('resetForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const newPasscode = document.getElementById('new_passcode').value;
                const res = await fetch('/api/admin/reset-passcode', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({new_passcode: newPasscode})
                });
                const data = await res.json();
                if(data.success) alert(data.message);
                else alert(data.message);
            });
        </script>
    </body>
    </html>
    '''

@app.route('/api/admin/reset-passcode', methods=['POST'])
@login_required
def admin_reset_passcode():
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    if session.get('admin_reset_token') is None:
        return jsonify({'success': False, 'message': 'No reset request'}), 400
    data = request.json
    new_passcode = data.get('new_passcode')
    if not new_passcode:
        return jsonify({'success': False, 'message': 'Passcode required'}), 400
    admin = AdminSettings.query.get(1)
    admin.passcode_hash = generate_password_hash(new_passcode)
    db.session.commit()
    session.pop('admin_reset_token', None)
    return jsonify({'success': True, 'message': 'Passcode updated'})

@app.route('/admin')
@login_required
def admin_panel():
    if not is_admin():
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    if not session.get('admin_authenticated'):
        return redirect(url_for('admin_login_page'))
    return render_template('admin.html')

@app.route('/admin/login')
@login_required
def admin_login_page():
    if not is_admin():
        return redirect(url_for('index'))
    return '''
    <!DOCTYPE html>
    <html>
    <head><title>Admin Login</title><style>body{background:#000;color:#fff;font-family:Arial;text-align:center;padding:2rem;}input,button{padding:0.5rem;margin:0.5rem;}</style></head>
    <body>
        <h2>Admin Passcode Required</h2>
        <form id="passcodeForm">
            <input type="password" id="passcode" placeholder="Enter passcode" required>
            <button type="submit">Verify</button>
        </form>
        <p><a href="#" id="forgotLink">Forgot passcode?</a></p>
        <div id="message"></div>
        <script>
            document.getElementById('passcodeForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const passcode = document.getElementById('passcode').value;
                const res = await fetch('/api/admin/verify-passcode', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({passcode})
                });
                const data = await res.json();
                if(data.success) window.location.href = '/admin';
                else alert(data.message);
            });
            document.getElementById('forgotLink').addEventListener('click', async (e) => {
                e.preventDefault();
                const res = await fetch('/api/admin/request-reset', {method: 'POST'});
                const data = await res.json();
                alert(data.message);
            });
        </script>
    </body>
    </html>
    '''

@app.route('/api/admin/users')
@login_required
def admin_get_users():
    if not is_admin() or not session.get('admin_authenticated'):
        return jsonify({'error': 'Unauthorized'}), 403
    users = User.query.all()
    result = []
    for user in users:
        total_scans = ScanJob.query.filter_by(user_id=user.id).count()
        result.append({
            'id': user.id,
            'email': user.email,
            'name': user.name,
            'credits': user.credits or 0,
            'total_scans': total_scans
        })
    return jsonify(result)

@app.route('/api/admin/give-credits', methods=['POST'])
@login_required
def admin_give_credits():
    if not is_admin() or not session.get('admin_authenticated'):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.json
    user_id = data.get('user_id')
    credits = data.get('credits')
    if not user_id or not credits:
        return jsonify({'success': False, 'message': 'Missing fields'}), 400
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    user.credits = (user.credits or 0) + int(credits)
    db.session.commit()
    return jsonify({'success': True, 'message': f'Added {credits} credits to {user.email}'})

@app.route('/api/admin/update-prices', methods=['POST'])
@login_required
def admin_update_prices():
    if not is_admin() or not session.get('admin_authenticated'):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.json
    new_costs = data.get('credit_costs')
    if not new_costs:
        return jsonify({'success': False, 'message': 'No data'}), 400
    admin = AdminSettings.query.get(1)
    admin.credit_costs = new_costs
    db.session.commit()
    return jsonify({'success': True, 'message': 'Prices updated'})

@app.route('/api/admin/credit-costs')
@login_required
def admin_credit_costs():
    if not is_admin() or not session.get('admin_authenticated'):
        return jsonify({'error': 'Unauthorized'}), 403
    return jsonify(get_credit_costs())

# ---------- Debug Environment Variables ----------
@app.route('/debug/env')
def debug_env():
    import os
    return jsonify({
        'JATIN_API_URL': os.getenv('JATIN_API_URL'),
        'CALLBACK_URL': os.getenv('CALLBACK_URL'),
        'BASE_URL': os.getenv('BASE_URL')
    })

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
                    email_body = f"""
                    Hello,<br><br>
                    You requested a security scan for {website_url} ({plan} plan).<br><br>
                    Click the link below to confirm and start the scan:<br><br>
                    <a href='{verify_url}'>Confirm Scan</a><br><br>
                    You do not need to be logged in – the scan will be associated with your account automatically.<br><br>
                    If you did not request this, please ignore this email.<br><br>
                    Nexus Security Team
                    """
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
        return "<h2>Invalid or expired verification link.</h2><p>Please request a new scan.</p>", 400

    user = User.query.get(pending.user_id)
    if not user:
        return "<h2>User not found.</h2><p>Please contact support.</p>", 400

    prices = {'basic': 0, 'advanced': 99, 'protection_plus': 999}
    scan_id = hashlib.md5(f"{pending.website_url}{pending.user_email}{datetime.utcnow()}".encode()).hexdigest()[:16]

    costs = get_credit_costs()
    cost = costs.get(pending.plan_type, 0)
    if cost > 0 and (user.credits or 0) < cost:
        return f"<h2>Insufficient credits</h2><p>You need {cost} credits for this scan. Please buy credits and request again.</p>", 400

    if cost > 0:
        user.credits -= cost
        db.session.commit()

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
        scan_id=scan_id,
        status='queued',
        credits_spent=cost
    )
    db.session.add(job)
    db.session.commit()
    pending.used = True
    db.session.commit()

    remote_success = send_to_friend_scanner(scan_id, pending.website_url, pending.plan_type, pending.user_email)
    if not remote_success:
        job.status = 'failed'
        db.session.commit()
        failure_msg = "Scan request could not be sent to the scanner. Please try again later."
    else:
        failure_msg = ""

    if current_user.is_authenticated and current_user.id == pending.user_id:
        flash('Scan confirmed! The AI scanner will process your request.' + (' ' + failure_msg if failure_msg else ''), 'success' if remote_success else 'danger')
        return redirect(url_for('profile'))
    else:
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Scan Started – Nexus Security</title>
            <style>
                body {{ background: #000; color: #fff; font-family: Arial, sans-serif; text-align: center; padding: 2rem; }}
                .container {{ max-width: 600px; margin: 0 auto; background: #0a0a0f; padding: 2rem; border-radius: 1rem; border: 1px solid #2f9b9b; }}
                h1 {{ color: #2f9b9b; }}
                a {{ color: #2f9b9b; text-decoration: none; }}
                .btn {{ display: inline-block; margin-top: 1rem; padding: 0.5rem 1rem; background: #2f9b9b; border-radius: 2rem; color: #fff; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>✅ Scan Started!</h1>
                <p>Your security scan for <strong>{pending.website_url}</strong> ({pending.plan_type} plan) has been queued.</p>
                <p>You will receive the report in your <strong>Profile</strong> once it's ready.</p>
                <p>Please <a href="/login.html" class="btn">Log in</a> to view your scan history and download the report later.</p>
                <p><small>If you are already logged in, <a href="/profile">go to your profile</a>.</small></p>
                {f"<p style='color:#ef4444;'>{failure_msg}</p>" if failure_msg else ""}
            </div>
        </body>
        </html>
        """
        return html

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
            scan_id = hashlib.md5(f"{fd['website_url']}{fd['user_email']}{datetime.utcnow()}".encode()).hexdigest()[:16]

            if not deduct_credits(current_user, fd['plan']):
                return jsonify({'success': False, 'message': 'Insufficient credits. Please buy credits.'}), 400

            costs = get_credit_costs()
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
                verification_code=verification.code,
                scan_id=scan_id,
                status='queued',
                credits_spent=costs.get(fd['plan'], 0)
            )
            db.session.add(job)
            db.session.commit()

            remote_success = send_to_friend_scanner(scan_id, fd['website_url'], fd['plan'], fd['user_email'])
            if remote_success:
                return jsonify({'success': True, 'message': '✅ Verification successful! Scan queued.', 'job_id': job.id})
            else:
                job.status = 'failed'
                db.session.commit()
                return jsonify({'success': False, 'message': 'Scan request failed. Please try again.'}), 500
        else:
            return jsonify({'success': False, 'message': f'Code "{verification.code}" not found on your website. Make sure you added it to the HTML source.'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error checking website: {str(e)}'}), 500

@app.route('/api/scan-callback', methods=['POST'])
def scan_callback():
    data = request.json
    scan_id = data.get('scan_id')
    status = data.get('status')
    report_html = data.get('report_html')
    report_url = data.get('report_url')

    if not scan_id:
        return jsonify({'error': 'Missing scan_id'}), 400

    job = ScanJob.query.filter_by(scan_id=scan_id).first()
    if not job:
        return jsonify({'error': 'Scan job not found'}), 404

    if status == 'completed':
        html_content = None
        if report_html:
            html_content = report_html
            print(f"✅ Received direct HTML for scan {scan_id}")
        elif report_url:
            try:
                resp = requests.get(report_url, timeout=30)
                if resp.status_code == 200:
                    html_content = resp.text
                    print(f"✅ Downloaded report from {report_url}")
                else:
                    print(f"❌ Failed to download report, HTTP {resp.status_code}")
            except Exception as e:
                print(f"❌ Error downloading report: {e}")

        if html_content:
            filename = f"report_{scan_id}.html"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            job.report_path = filename
            job.status = 'completed'
            job.completed_at = datetime.utcnow()
            db.session.commit()
            print(f"✅ Report saved for scan {scan_id}")
            return jsonify({'status': 'ok'})
        else:
            job.status = 'failed'
            db.session.commit()
            return jsonify({'error': 'No report content received'}), 500
    else:
        job.status = status or 'failed'
        db.session.commit()
        print(f"⚠️ Scan {scan_id} reported status: {status}")
        return jsonify({'status': 'updated'})

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

@app.route('/download_report/<int:job_id>')
@login_required
def download_report(job_id):
    job = ScanJob.query.get_or_404(job_id)
    if job.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('profile'))
    if job.status != 'completed' or not job.report_path:
        flash('Report is not ready yet. Please check back later.', 'info')
        return redirect(url_for('profile'))
    return send_file(
        os.path.join(app.config['UPLOAD_FOLDER'], job.report_path),
        as_attachment=True,
        download_name=f"security_report_{job.id}.html"
    )

@app.route('/test-email')
def test_email():
    try:
        send_email_via_brevo('hitesh.tanwar8318@gmail.com', 'Test Email from Nexus Security', '<p>This is a test email from your Flask app using Brevo API.</p>')
        return '✅ Email sent successfully! Check your inbox.'
    except Exception as e:
        return f'❌ Error: {str(e)}'

if __name__ == '__main__':
    app.run(debug=True)
