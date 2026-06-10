"""
PENNY BUDDY — Backend Server
Flask + SQLite REST API for personal finance tracking
Multi-user with email + password authentication
"""

import os
import io
import csv
import re
import sqlite3
import json
import hashlib
import secrets
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, g, make_response
from flask_cors import CORS

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app, origins=['capacitor://localhost', 'https://localhost', 'http://localhost:5000',
                   'https://pennybuddy.pythonanywhere.com'])

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'pennybuddy_admin_2026')

SESSION_MAX_AGE_DAYS = 30
MAX_AMOUNT = 100_000_000  # sanity cap on any single transaction

# ===== SECURITY HEADERS =====

@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    return response

# ===== RATE LIMITING (in-memory, per IP) =====

_rate_buckets = {}

def rate_limited(key_prefix, max_attempts=10, window_seconds=300):
    """Returns True if this IP has exceeded max_attempts within the window."""
    ip = request.headers.get('X-Real-IP', request.remote_addr or 'unknown')
    key = f'{key_prefix}:{ip}'
    now = datetime.now().timestamp()
    attempts = [t for t in _rate_buckets.get(key, []) if now - t < window_seconds]
    if len(attempts) >= max_attempts:
        _rate_buckets[key] = attempts
        return True
    attempts.append(now)
    _rate_buckets[key] = attempts
    # opportunistic cleanup so the dict doesn't grow forever
    if len(_rate_buckets) > 10000:
        cutoff = now - window_seconds
        for k in list(_rate_buckets):
            _rate_buckets[k] = [t for t in _rate_buckets[k] if t > cutoff]
            if not _rate_buckets[k]:
                del _rate_buckets[k]
    return False

# ===== JSON ERROR HANDLERS =====

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Endpoint not found'}), 404
    return e

@app.errorhandler(405)
def method_not_allowed(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Method not allowed'}), 405
    return e

@app.errorhandler(500)
def internal_error(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Something went wrong on our end. Please try again.'}), 500
    return e

DATA_DIR = os.environ.get('RENDER_DISK_PATH', os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(DATA_DIR, 'pennybuddy.db')

# ===== DATABASE SETUP =====

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
    return salt, hashed

def verify_password(password, salt, hashed):
    _, check = hash_password(password, salt)
    return check == hashed

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        password_salt TEXT NOT NULL,
        name TEXT NOT NULL,
        currency TEXT DEFAULT 'INR',
        income REAL DEFAULT 0,
        savings_target REAL DEFAULT 0,
        budget REAL DEFAULT 0,
        categories TEXT DEFAULT '[]',
        theme TEXT DEFAULT 'light',
        onboarding_done INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        emoji TEXT DEFAULT '',
        amount REAL NOT NULL,
        type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
        description TEXT DEFAULT '',
        date TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        emoji TEXT DEFAULT '',
        saved REAL DEFAULT 0,
        target REAL NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS money_pulse (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        week TEXT NOT NULL,
        mood TEXT NOT NULL,
        highlight TEXT DEFAULT '',
        challenge TEXT DEFAULT '',
        goal TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS due_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        amount REAL NOT NULL,
        due_date TEXT NOT NULL,
        type TEXT NOT NULL CHECK(type IN ('emi', 'subscription', 'personal')),
        emoji TEXT DEFAULT '',
        is_recurring INTEGER DEFAULT 0,
        recur_months INTEGER DEFAULT 1,
        is_paid INTEGER DEFAULT 0,
        paid_date TEXT DEFAULT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )''')

    # Migrate: keep old single-user data if it exists
    try:
        c.execute("SELECT id FROM user WHERE id = 1")
        old_user = c.fetchone()
        if old_user:
            _migrate_old_data(c)
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

def _migrate_old_data(c):
    """One-time migration from old single-user schema to multi-user."""
    old = c.execute("SELECT * FROM user WHERE id = 1").fetchone()
    if not old:
        return
    existing = c.execute("SELECT id FROM users WHERE email = ?", (old['email'] or 'migrated@pennybuddy.app',)).fetchone()
    if existing:
        return
    salt, hashed = hash_password('changeme')
    email = old['email'] if old['email'] else 'migrated@pennybuddy.app'
    c.execute('''INSERT INTO users (email, password_hash, password_salt, name, currency, income, savings_target, budget, categories, theme, onboarding_done)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)''',
        (email, hashed, salt, old['name'], old['currency'], old['income'],
         old['savings_target'], old['budget'], old['categories'], old['theme']))
    uid = c.lastrowid
    try:
        for t in c.execute("SELECT * FROM transactions").fetchall():
            c.execute("INSERT INTO transactions (user_id, name, category, emoji, amount, type, description, date, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (uid, t['name'], t['category'], t['emoji'], t['amount'], t['type'], t['description'], t['date'], t['created_at']))
    except sqlite3.OperationalError:
        pass
    try:
        for g in c.execute("SELECT * FROM goals").fetchall():
            c.execute("INSERT INTO goals (user_id, name, emoji, saved, target, created_at) VALUES (?,?,?,?,?,?)",
                (uid, g['name'], g['emoji'], g['saved'], g['target'], g['created_at']))
    except sqlite3.OperationalError:
        pass
    try:
        for p in c.execute("SELECT * FROM money_pulse").fetchall():
            c.execute("INSERT INTO money_pulse (user_id, week, mood, highlight, challenge, goal, created_at) VALUES (?,?,?,?,?,?,?)",
                (uid, p['week'], p['mood'], p['highlight'], p['challenge'], p['goal'], p['created_at']))
    except sqlite3.OperationalError:
        pass
    try:
        for d in c.execute("SELECT * FROM due_payments").fetchall():
            c.execute("INSERT INTO due_payments (user_id, name, amount, due_date, type, emoji, is_recurring, recur_months, is_paid, paid_date, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (uid, d['name'], d['amount'], d['due_date'], d['type'], d['emoji'], d['is_recurring'], d['recur_months'], d['is_paid'], d['paid_date'], d['created_at']))
    except sqlite3.OperationalError:
        pass

init_db()

# ===== AUTH MIDDLEWARE =====

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Login required'}), 401
        conn = get_db()
        session = conn.execute('SELECT user_id, created_at FROM sessions WHERE token = ?', (token,)).fetchone()
        if not session:
            conn.close()
            return jsonify({'error': 'Invalid or expired session'}), 401
        # Expire sessions older than SESSION_MAX_AGE_DAYS
        try:
            created = datetime.fromisoformat(session['created_at'])
            if (datetime.now() - created).days > SESSION_MAX_AGE_DAYS:
                conn.execute('DELETE FROM sessions WHERE token = ?', (token,))
                conn.commit()
                conn.close()
                return jsonify({'error': 'Session expired. Please log in again.'}), 401
        except (ValueError, TypeError):
            pass
        g.user_id = session['user_id']
        g.db = conn
        try:
            return f(*args, **kwargs)
        finally:
            conn.close()
    return decorated

# ===== STATIC FILES =====

START_TS = str(int(datetime.now().timestamp()))

@app.route('/')
def serve_index():
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index.html'), 'r', encoding='utf-8') as f:
        html = f.read()
    import re
    html = re.sub(r'href="styles\.css(\?v=\d+)?"', f'href="styles.css?v={START_TS}"', html)
    html = re.sub(r'src="app\.js(\?v=\d+)?"', f'src="app.js?v={START_TS}"', html)
    response = make_response(html, 200)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    return response

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('.', 'manifest.json', mimetype='application/manifest+json')

@app.route('/sw.js')
def serve_sw():
    response = send_from_directory('.', 'sw.js', mimetype='application/javascript')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    return response

# ===== AUTH API =====

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    if rate_limited('signup', max_attempts=10, window_seconds=600):
        return jsonify({'error': 'Too many attempts. Please wait a few minutes.'}), 429
    data = request.json
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    name = (data.get('name') or '').strip()

    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not email or not re.match(email_regex, email):
        return jsonify({'error': 'Enter a valid email address (e.g. you@gmail.com)'}), 400
    if not name or len(name.strip()) < 2:
        return jsonify({'error': 'Name must be at least 2 characters'}), 400
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400
    if not re.search(r'[A-Z]', password):
        return jsonify({'error': 'Password needs at least one uppercase letter'}), 400
    if not re.search(r'[a-z]', password):
        return jsonify({'error': 'Password needs at least one lowercase letter'}), 400
    if not re.search(r'[0-9]', password):
        return jsonify({'error': 'Password needs at least one number'}), 400
    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\\/~`]', password):
        return jsonify({'error': 'Password needs at least one special character (!@#$%^&* etc.)'}), 400

    conn = get_db()
    existing = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'Email already registered. Please log in.'}), 409

    salt, hashed = hash_password(password)
    c = conn.execute('''INSERT INTO users (email, password_hash, password_salt, name) VALUES (?, ?, ?, ?)''',
        (email, hashed, salt, name))
    user_id = c.lastrowid
    token = secrets.token_urlsafe(32)
    conn.execute('INSERT INTO sessions (token, user_id) VALUES (?, ?)', (token, user_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'token': token, 'user_id': user_id, 'name': name})

@app.route('/api/auth/login', methods=['POST'])
def login():
    if rate_limited('login', max_attempts=15, window_seconds=300):
        return jsonify({'error': 'Too many login attempts. Please wait a few minutes.'}), 429
    data = request.json or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email:
        return jsonify({'error': 'Email is required'}), 400
    if not password:
        return jsonify({'error': 'Password is required'}), 400

    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    if not user or not verify_password(password, user['password_salt'], user['password_hash']):
        conn.close()
        return jsonify({'error': 'Invalid email or password'}), 401

    token = secrets.token_urlsafe(32)
    conn.execute('INSERT INTO sessions (token, user_id) VALUES (?, ?)', (token, user['id']))
    conn.commit()
    conn.close()
    return jsonify({
        'success': True,
        'token': token,
        'user_id': user['id'],
        'name': user['name'],
        'onboarding_done': bool(user['onboarding_done'])
    })

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if token:
        conn = get_db()
        conn.execute('DELETE FROM sessions WHERE token = ?', (token,))
        conn.commit()
        conn.close()
    return jsonify({'success': True})

@app.route('/api/auth/guest', methods=['POST'])
def guest_login():
    conn = get_db()
    guest_id = secrets.token_hex(4)
    guest_email = f"guest_{guest_id}@pennybuddy.guest"
    guest_name = f"Guest_{guest_id}"
    salt, hashed = hash_password(secrets.token_urlsafe(16))
    c = conn.execute('''INSERT INTO users (email, password_hash, password_salt, name) VALUES (?, ?, ?, ?)''',
        (guest_email, hashed, salt, guest_name))
    user_id = c.lastrowid
    token = secrets.token_urlsafe(32)
    conn.execute('INSERT INTO sessions (token, user_id) VALUES (?, ?)', (token, user_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'token': token, 'user_id': user_id, 'name': guest_name, 'is_guest': True})

@app.route('/api/auth/check', methods=['GET'])
def check_auth():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'authenticated': False})
    conn = get_db()
    session = conn.execute('SELECT user_id FROM sessions WHERE token = ?', (token,)).fetchone()
    if not session:
        conn.close()
        return jsonify({'authenticated': False})
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    conn.close()
    if not user:
        return jsonify({'authenticated': False})
    return jsonify({
        'authenticated': True,
        'user_id': user['id'],
        'name': user['name'],
        'onboarding_done': bool(user['onboarding_done'])
    })

# ===== USER PROFILE API =====

@app.route('/api/user', methods=['GET'])
@login_required
def get_user():
    user = g.db.execute('SELECT * FROM users WHERE id = ?', (g.user_id,)).fetchone()
    if user:
        today = date.today()
        days_in_month = (date(today.year, today.month % 12 + 1, 1) - timedelta(days=1)).day if today.month < 12 else 31
        weeks_in_month = round(days_in_month / 7, 2)
        week_num = min((today.day - 1) // 7 + 1, 4)

        monthly_income  = user['income'] or 0
        monthly_target  = user['savings_target'] or 0
        weekly_income   = round(monthly_income / weeks_in_month)
        weekly_target   = round(monthly_target / weeks_in_month)
        weekly_budget   = max(weekly_income - weekly_target, 0)

        return jsonify({
            'exists': bool(user['onboarding_done']),
            'name': user['name'],
            'email': user['email'],
            'currency': user['currency'],
            'income': monthly_income,
            'savings_target': monthly_target,
            'budget': user['budget'],
            'categories': json.loads(user['categories']),
            'theme': user['theme'],
            'weekly_income': weekly_income,
            'weekly_target': weekly_target,
            'weekly_budget': weekly_budget,
            'week_num': week_num,
            'weeks_in_month': weeks_in_month
        })
    return jsonify({'exists': False})

@app.route('/api/user', methods=['POST'])
@login_required
def create_user():
    data = request.json
    g.db.execute('''UPDATE users SET name=?, currency=?, income=?, savings_target=?, budget=?, categories=?, theme=?, onboarding_done=1 WHERE id=?''',
        (data.get('name', ''),
         data.get('currency', 'INR'),
         data.get('income', 0),
         data.get('savings_target', 0),
         data.get('budget', 0),
         json.dumps(data.get('categories', [])),
         data.get('theme', 'light'),
         g.user_id))
    g.db.commit()
    return jsonify({'success': True})

@app.route('/api/user', methods=['PUT'])
@login_required
def update_user():
    data = request.json
    fields = []
    values = []
    for key in ['name', 'email', 'currency', 'income', 'savings_target', 'budget', 'theme']:
        if key in data:
            fields.append(f"{key} = ?")
            values.append(data[key])
    if 'categories' in data:
        fields.append("categories = ?")
        values.append(json.dumps(data['categories']))
    if fields:
        values.append(g.user_id)
        g.db.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
        g.db.commit()
    return jsonify({'success': True})

# ===== TRANSACTIONS API =====

@app.route('/api/transactions', methods=['GET'])
@login_required
def get_transactions():
    month = request.args.get('month')
    category = request.args.get('category')
    query = 'SELECT * FROM transactions WHERE user_id = ?'
    params = [g.user_id]

    if month:
        query += " AND strftime('%Y-%m', date) = ?"
        params.append(month)
    if category and category != 'all':
        query += " AND category = ?"
        params.append(category)

    query += ' ORDER BY date DESC, id DESC'
    rows = g.db.execute(query, params).fetchall()

    return jsonify([{
        'id': r['id'], 'name': r['name'], 'category': r['category'],
        'emoji': r['emoji'], 'amount': r['amount'], 'type': r['type'],
        'description': r['description'], 'date': r['date']
    } for r in rows])

@app.route('/api/transactions', methods=['POST'])
@login_required
def add_transaction():
    data = request.json or {}
    try:
        amount = abs(float(data.get('amount', 0)))
    except (TypeError, ValueError):
        return jsonify({'error': 'Amount must be a number'}), 400
    if amount <= 0:
        return jsonify({'error': 'Amount must be greater than zero'}), 400
    if amount > MAX_AMOUNT:
        return jsonify({'error': 'Amount is too large'}), 400
    tx_type = data.get('type', 'expense')
    if tx_type not in ('income', 'expense'):
        return jsonify({'error': 'Invalid transaction type'}), 400
    if tx_type == 'expense':
        amount = -amount

    c = g.db.execute('''INSERT INTO transactions (user_id, name, category, emoji, amount, type, description, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (g.user_id,
         data.get('name', 'Transaction'),
         data.get('category', 'other'),
         data.get('emoji', ''),
         amount, tx_type,
         data.get('description', ''),
         data.get('date', date.today().isoformat())))
    g.db.commit()
    return jsonify({'success': True, 'id': c.lastrowid})

@app.route('/api/transactions/<int:tx_id>', methods=['DELETE'])
@login_required
def delete_transaction(tx_id):
    g.db.execute('DELETE FROM transactions WHERE id = ? AND user_id = ?', (tx_id, g.user_id))
    g.db.commit()
    return jsonify({'success': True})

# ===== SUMMARY / DASHBOARD API =====

@app.route('/api/summary', methods=['GET'])
@login_required
def get_summary():
    month = request.args.get('month', date.today().strftime('%Y-%m'))
    uid = g.user_id

    income_row = g.db.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE user_id=? AND type='income' AND strftime('%Y-%m', date) = ?",
        (uid, month)).fetchone()
    income = income_row['total']

    expense_row = g.db.execute(
        "SELECT COALESCE(SUM(ABS(amount)), 0) as total FROM transactions WHERE user_id=? AND type='expense' AND strftime('%Y-%m', date) = ?",
        (uid, month)).fetchone()
    expenses = expense_row['total']

    saved_row = g.db.execute("SELECT COALESCE(SUM(saved), 0) as total FROM goals WHERE user_id=?", (uid,)).fetchone()
    total_saved = saved_row['total']

    balance = income - expenses

    cat_rows = g.db.execute(
        "SELECT category, COALESCE(SUM(ABS(amount)), 0) as total FROM transactions WHERE user_id=? AND type='expense' AND strftime('%Y-%m', date) = ? GROUP BY category ORDER BY total DESC",
        (uid, month)).fetchall()
    categories = [{'category': r['category'], 'total': r['total']} for r in cat_rows]

    daily_rows = g.db.execute(
        "SELECT CAST(strftime('%d', date) AS INTEGER) as day, COALESCE(SUM(ABS(amount)), 0) as total FROM transactions WHERE user_id=? AND type='expense' AND strftime('%Y-%m', date) = ? GROUP BY day ORDER BY day",
        (uid, month)).fetchall()
    daily_spending = {r['day']: r['total'] for r in daily_rows}

    year, mon = int(month[:4]), int(month[5:])
    prev_month = f"{year-1}-12" if mon == 1 else f"{year}-{mon-1:02d}"

    prev_cat_rows = g.db.execute(
        "SELECT category, COALESCE(SUM(ABS(amount)), 0) as total FROM transactions WHERE user_id=? AND type='expense' AND strftime('%Y-%m', date) = ? GROUP BY category",
        (uid, prev_month)).fetchall()
    prev_categories = {r['category']: r['total'] for r in prev_cat_rows}

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    ws = week_start.strftime('%Y-%m-%d')
    we = week_end.strftime('%Y-%m-%d')

    week_expense_row = g.db.execute(
        "SELECT COALESCE(SUM(ABS(amount)), 0) as total FROM transactions WHERE user_id=? AND type='expense' AND date >= ? AND date <= ?",
        (uid, ws, we)).fetchone()
    week_expenses = week_expense_row['total']

    # Accrual: daily portion of monthly salary setting
    user_row = g.db.execute('SELECT income, savings_target FROM users WHERE id=?', (uid,)).fetchone()
    monthly_income = user_row['income'] or 0
    days_in_month = (date(today.year, today.month % 12 + 1, 1) - timedelta(days=1)).day if today.month < 12 else 31
    weeks_in_month = days_in_month / 7
    weekly_income = monthly_income / weeks_in_month
    daily_income = weekly_income / 7
    days_elapsed = today.weekday() + 1  # Mon=1 … Sun=7
    accrued_income = daily_income * days_elapsed

    # Side income = this month's logged income ABOVE the expected monthly salary
    # e.g. salary ₹30k set in profile + ₹5k freelance logged → side_income = ₹5k
    month_income_row = g.db.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE user_id=? AND type='income' AND strftime('%Y-%m', date) = ?",
        (uid, today.strftime('%Y-%m'))).fetchone()
    month_income_logged = month_income_row['total']
    side_income = max(month_income_logged - monthly_income, 0)

    # Only accrue if there's been actual financial activity this month.
    # After a reset (no transactions at all) show 0 so the card looks clean.
    has_activity = month_income_logged > 0 or week_expenses > 0
    if has_activity:
        week_saved_accrued = max(round(accrued_income + side_income - week_expenses), 0)
    else:
        week_saved_accrued = 0

    return jsonify({
        'month': month, 'income': income, 'expenses': expenses,
        'balance': balance, 'total_saved': total_saved,
        'spending_ratio': round((expenses / income * 100) if income > 0 else 0, 1),
        'categories': categories, 'daily_spending': daily_spending,
        'prev_categories': prev_categories,
        'week_expenses': week_expenses,
        'week_saved_accrued': week_saved_accrued,
        'week_start': ws, 'week_end': we,
        'days_elapsed': days_elapsed
    })

# ===== GOALS API =====

@app.route('/api/goals', methods=['GET'])
@login_required
def get_goals():
    rows = g.db.execute('SELECT * FROM goals WHERE user_id = ? ORDER BY created_at DESC', (g.user_id,)).fetchall()
    return jsonify([{
        'id': r['id'], 'name': r['name'], 'emoji': r['emoji'],
        'saved': r['saved'], 'target': r['target']
    } for r in rows])

@app.route('/api/goals', methods=['POST'])
@login_required
def add_goal():
    data = request.json
    c = g.db.execute('INSERT INTO goals (user_id, name, emoji, saved, target) VALUES (?, ?, ?, ?, ?)',
        (g.user_id, data.get('name', 'Goal'), data.get('emoji', ''), data.get('saved', 0), data.get('target', 0)))
    g.db.commit()
    return jsonify({'success': True, 'id': c.lastrowid})

@app.route('/api/goals/<int:goal_id>', methods=['PUT'])
@login_required
def update_goal(goal_id):
    data = request.json
    if 'add_amount' in data:
        g.db.execute('UPDATE goals SET saved = MIN(saved + ?, target) WHERE id = ? AND user_id = ?',
            (abs(float(data['add_amount'])), goal_id, g.user_id))
    else:
        fields, values = [], []
        for key in ['name', 'emoji', 'saved', 'target']:
            if key in data:
                fields.append(f"{key} = ?")
                values.append(data[key])
        if fields:
            values.extend([goal_id, g.user_id])
            g.db.execute(f"UPDATE goals SET {', '.join(fields)} WHERE id = ? AND user_id = ?", values)
    g.db.commit()
    return jsonify({'success': True})

@app.route('/api/goals/<int:goal_id>', methods=['DELETE'])
@login_required
def delete_goal(goal_id):
    g.db.execute('DELETE FROM goals WHERE id = ? AND user_id = ?', (goal_id, g.user_id))
    g.db.commit()
    return jsonify({'success': True})

# ===== MONEY PULSE API =====

@app.route('/api/pulse', methods=['GET'])
@login_required
def get_pulse():
    rows = g.db.execute('SELECT * FROM money_pulse WHERE user_id = ? ORDER BY created_at DESC LIMIT 8', (g.user_id,)).fetchall()
    return jsonify([{
        'id': r['id'], 'week': r['week'], 'mood': r['mood'],
        'highlight': r['highlight'], 'challenge': r['challenge'], 'goal': r['goal']
    } for r in rows])

@app.route('/api/pulse', methods=['POST'])
@login_required
def add_pulse():
    data = request.json
    g.db.execute('INSERT INTO money_pulse (user_id, week, mood, highlight, challenge, goal) VALUES (?, ?, ?, ?, ?, ?)',
        (g.user_id, data.get('week', ''), data.get('mood', 'neutral'),
         data.get('highlight', ''), data.get('challenge', ''), data.get('goal', '')))
    g.db.commit()
    return jsonify({'success': True})

@app.route('/api/pulse/current-week', methods=['GET'])
@login_required
def get_current_pulse():
    today = date.today()
    iso = today.isocalendar()
    current_week = f"{iso[0]}-W{iso[1]}"
    row = g.db.execute('SELECT * FROM money_pulse WHERE user_id = ? AND week = ?', (g.user_id, current_week)).fetchone()
    if row:
        return jsonify({
            'completed': True, 'mood': row['mood'],
            'highlight': row['highlight'], 'challenge': row['challenge'], 'goal': row['goal']
        })
    return jsonify({'completed': False, 'current_week': current_week})

# ===== DUE PAYMENTS API =====

@app.route('/api/dues', methods=['GET'])
@login_required
def get_dues():
    rows = g.db.execute('SELECT * FROM due_payments WHERE user_id = ? ORDER BY due_date ASC', (g.user_id,)).fetchall()
    return jsonify([{
        'id': r['id'], 'name': r['name'], 'amount': r['amount'],
        'due_date': r['due_date'], 'type': r['type'], 'emoji': r['emoji'],
        'is_recurring': r['is_recurring'], 'recur_months': r['recur_months'],
        'is_paid': r['is_paid'], 'paid_date': r['paid_date']
    } for r in rows])

@app.route('/api/dues/upcoming', methods=['GET'])
@login_required
def get_upcoming_dues():
    from datetime import timedelta
    today = date.today()
    cutoff = (today + timedelta(days=5)).isoformat()
    rows = g.db.execute(
        "SELECT * FROM due_payments WHERE user_id = ? AND is_paid = 0 AND due_date <= ? ORDER BY due_date ASC",
        (g.user_id, cutoff)).fetchall()
    dues = []
    for r in rows:
        due_d = date.fromisoformat(r['due_date'])
        days_left = (due_d - today).days
        dues.append({
            'id': r['id'], 'name': r['name'], 'amount': r['amount'],
            'due_date': r['due_date'], 'type': r['type'], 'emoji': r['emoji'],
            'is_recurring': r['is_recurring'], 'recur_months': r['recur_months'],
            'days_left': days_left,
            'status': 'overdue' if days_left < 0 else ('due_today' if days_left == 0 else 'upcoming')
        })
    return jsonify(dues)

@app.route('/api/dues', methods=['POST'])
@login_required
def add_due():
    data = request.json
    type_emojis = {'emi': '\U0001f3e6', 'subscription': '\U0001f504', 'personal': '\U0001f4cc'}
    due_type = data.get('type', 'personal')
    c = g.db.execute(
        'INSERT INTO due_payments (user_id, name, amount, due_date, type, emoji, is_recurring, recur_months) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (g.user_id, data.get('name', 'Payment'), abs(float(data.get('amount', 0))),
         data.get('due_date', date.today().isoformat()), due_type,
         type_emojis.get(due_type, '📅'),
         1 if data.get('is_recurring') else 0, data.get('recur_months', 1)))
    g.db.commit()
    return jsonify({'success': True, 'id': c.lastrowid})

@app.route('/api/dues/<int:due_id>/pay', methods=['POST'])
@login_required
def mark_due_paid(due_id):
    from datetime import timedelta
    today = date.today()
    row = g.db.execute('SELECT * FROM due_payments WHERE id = ? AND user_id = ?', (due_id, g.user_id)).fetchone()
    if not row:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    g.db.execute('UPDATE due_payments SET is_paid = 1, paid_date = ? WHERE id = ? AND user_id = ?',
        (today.isoformat(), due_id, g.user_id))

    g.db.execute('INSERT INTO transactions (user_id, name, category, emoji, amount, type, description, date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (g.user_id, row['name'], 'bills', row['emoji'], -abs(row['amount']), 'expense',
         f"Due payment: {row['name']}", today.isoformat()))

    if row['is_recurring']:
        old_due = date.fromisoformat(row['due_date'])
        months = row['recur_months'] or 1
        new_month = old_due.month + months
        new_year = old_due.year + (new_month - 1) // 12
        new_month = ((new_month - 1) % 12) + 1
        try:
            new_due_date = old_due.replace(year=new_year, month=new_month)
        except ValueError:
            import calendar
            last_day = calendar.monthrange(new_year, new_month)[1]
            new_due_date = old_due.replace(year=new_year, month=new_month, day=min(old_due.day, last_day))

        g.db.execute(
            'INSERT INTO due_payments (user_id, name, amount, due_date, type, emoji, is_recurring, recur_months) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (g.user_id, row['name'], row['amount'], new_due_date.isoformat(), row['type'], row['emoji'], 1, months))

    g.db.commit()
    return jsonify({'success': True})

@app.route('/api/dues/<int:due_id>', methods=['DELETE'])
@login_required
def delete_due(due_id):
    g.db.execute('DELETE FROM due_payments WHERE id = ? AND user_id = ?', (due_id, g.user_id))
    g.db.commit()
    return jsonify({'success': True})

# ===== ADMIN API (hidden, password-protected) =====

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        pwd = request.headers.get('X-Admin-Key', '')
        if pwd != ADMIN_PASSWORD:
            return jsonify({'error': 'Unauthorized'}), 403
        return f(*args, **kwargs)
    return decorated

@app.route('/api/admin/overview', methods=['GET'])
@admin_required
def admin_overview():
    conn = get_db()
    users = conn.execute('SELECT id, email, name, currency, income, savings_target, budget, onboarding_done, created_at FROM users ORDER BY created_at DESC').fetchall()
    user_list = []
    for u in users:
        tx_count = conn.execute('SELECT COUNT(*) as c FROM transactions WHERE user_id=?', (u['id'],)).fetchone()['c']
        goal_count = conn.execute('SELECT COUNT(*) as c FROM goals WHERE user_id=?', (u['id'],)).fetchone()['c']
        total_income = conn.execute("SELECT COALESCE(SUM(amount),0) as t FROM transactions WHERE user_id=? AND type='income'", (u['id'],)).fetchone()['t']
        total_expense = conn.execute("SELECT COALESCE(SUM(ABS(amount)),0) as t FROM transactions WHERE user_id=? AND type='expense'", (u['id'],)).fetchone()['t']
        user_list.append({
            'id': u['id'], 'email': u['email'], 'name': u['name'],
            'currency': u['currency'], 'income': u['income'],
            'savings_target': u['savings_target'], 'budget': u['budget'],
            'onboarding_done': bool(u['onboarding_done']),
            'created_at': u['created_at'], 'tx_count': tx_count,
            'goal_count': goal_count, 'total_income': total_income,
            'total_expense': total_expense
        })
    stats = {
        'total_users': len(user_list),
        'active_users': sum(1 for u in user_list if u['onboarding_done']),
        'total_transactions': sum(u['tx_count'] for u in user_list),
        'total_goals': sum(u['goal_count'] for u in user_list)
    }
    conn.close()
    return jsonify({'stats': stats, 'users': user_list})

@app.route('/api/admin/export', methods=['GET'])
@admin_required
def admin_export():
    conn = get_db()
    output = io.StringIO()

    # Users sheet
    output.write('=== USERS ===\n')
    w = csv.writer(output)
    w.writerow(['ID','Email','Name','Currency','Income','Savings Target','Budget','Onboarding Done','Created At'])
    for u in conn.execute('SELECT * FROM users ORDER BY id').fetchall():
        w.writerow([u['id'], u['email'], u['name'], u['currency'], u['income'], u['savings_target'], u['budget'], bool(u['onboarding_done']), u['created_at']])

    output.write('\n=== TRANSACTIONS ===\n')
    w.writerow(['ID','User ID','User Email','Name','Category','Amount','Type','Description','Date','Created At'])
    for t in conn.execute('SELECT t.*, u.email as user_email FROM transactions t JOIN users u ON t.user_id=u.id ORDER BY t.date DESC').fetchall():
        w.writerow([t['id'], t['user_id'], t['user_email'], t['name'], t['category'], t['amount'], t['type'], t['description'], t['date'], t['created_at']])

    output.write('\n=== GOALS ===\n')
    w.writerow(['ID','User ID','User Email','Name','Saved','Target','Created At'])
    for g_row in conn.execute('SELECT g.*, u.email as user_email FROM goals g JOIN users u ON g.user_id=u.id ORDER BY g.id').fetchall():
        w.writerow([g_row['id'], g_row['user_id'], g_row['user_email'], g_row['name'], g_row['saved'], g_row['target'], g_row['created_at']])

    output.write('\n=== DUE PAYMENTS ===\n')
    w.writerow(['ID','User ID','User Email','Name','Amount','Due Date','Type','Recurring','Paid','Paid Date'])
    for d in conn.execute('SELECT d.*, u.email as user_email FROM due_payments d JOIN users u ON d.user_id=u.id ORDER BY d.due_date').fetchall():
        w.writerow([d['id'], d['user_id'], d['user_email'], d['name'], d['amount'], d['due_date'], d['type'], bool(d['is_recurring']), bool(d['is_paid']), d['paid_date']])

    conn.close()

    resp = make_response(output.getvalue())
    resp.headers['Content-Type'] = 'text/csv'
    resp.headers['Content-Disposition'] = f'attachment; filename=pennybuddy_export_{date.today().isoformat()}.csv'
    return resp

# ===== RESET =====

@app.route('/api/reset', methods=['POST'])
@login_required
def reset_all():
    uid = g.user_id
    g.db.execute('DELETE FROM transactions WHERE user_id = ?', (uid,))
    g.db.execute('DELETE FROM goals WHERE user_id = ?', (uid,))
    g.db.execute('DELETE FROM money_pulse WHERE user_id = ?', (uid,))
    g.db.execute('DELETE FROM due_payments WHERE user_id = ?', (uid,))
    g.db.commit()
    return jsonify({'success': True})

# ===== CATCH-ALL FOR SPA =====

@app.route('/<path:path>')
def serve_static(path):
    response = make_response(send_from_directory('.', path))
    if path.endswith(('.js', '.css')):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
    return response


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('RENDER') is None
    print(f"Penny Buddy server running at http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
