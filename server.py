"""
PENNY BUDDY — Backend Server
Flask + SQLite REST API for personal finance tracking
"""

import os
import sqlite3
import json
from datetime import datetime, date
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app, origins=['*', 'capacitor://localhost', 'https://localhost', 'http://localhost:5000'])

DATA_DIR = os.environ.get('RENDER_DISK_PATH', os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(DATA_DIR, 'pennybuddy.db')

# ===== DATABASE SETUP =====

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS user (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        name TEXT NOT NULL,
        email TEXT DEFAULT '',
        currency TEXT DEFAULT 'INR',
        income REAL DEFAULT 0,
        savings_target REAL DEFAULT 0,
        budget REAL DEFAULT 0,
        categories TEXT DEFAULT '[]',
        theme TEXT DEFAULT 'light',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        emoji TEXT DEFAULT '📦',
        amount REAL NOT NULL,
        type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
        description TEXT DEFAULT '',
        date TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        emoji TEXT DEFAULT '🎯',
        saved REAL DEFAULT 0,
        target REAL NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS money_pulse (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        week TEXT NOT NULL,
        mood TEXT NOT NULL,
        highlight TEXT DEFAULT '',
        challenge TEXT DEFAULT '',
        goal TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS due_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        amount REAL NOT NULL,
        due_date TEXT NOT NULL,
        type TEXT NOT NULL CHECK(type IN ('emi', 'subscription', 'personal')),
        emoji TEXT DEFAULT '📅',
        is_recurring INTEGER DEFAULT 0,
        recur_months INTEGER DEFAULT 1,
        is_paid INTEGER DEFAULT 0,
        paid_date TEXT DEFAULT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    conn.commit()
    conn.close()

init_db()

# ===== STATIC FILES =====

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('.', 'manifest.json', mimetype='application/manifest+json')

@app.route('/sw.js')
def serve_sw():
    response = send_from_directory('.', 'sw.js', mimetype='application/javascript')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    return response

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

# ===== USER API =====

@app.route('/api/user', methods=['GET'])
def get_user():
    conn = get_db()
    user = conn.execute('SELECT * FROM user WHERE id = 1').fetchone()
    conn.close()
    if user:
        return jsonify({
            'exists': True,
            'name': user['name'],
            'email': user['email'],
            'currency': user['currency'],
            'income': user['income'],
            'savings_target': user['savings_target'],
            'budget': user['budget'],
            'categories': json.loads(user['categories']),
            'theme': user['theme']
        })
    return jsonify({'exists': False})

@app.route('/api/user', methods=['POST'])
def create_user():
    data = request.json
    conn = get_db()
    conn.execute('''INSERT OR REPLACE INTO user (id, name, email, currency, income, savings_target, budget, categories, theme)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (data.get('name', ''),
         data.get('email', ''),
         data.get('currency', 'INR'),
         data.get('income', 0),
         data.get('savings_target', 0),
         data.get('budget', 0),
         json.dumps(data.get('categories', [])),
         data.get('theme', 'light')))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/user', methods=['PUT'])
def update_user():
    data = request.json
    conn = get_db()
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
        values.append(1)
        conn.execute(f"UPDATE user SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
    conn.close()
    return jsonify({'success': True})

# ===== TRANSACTIONS API =====

@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    month = request.args.get('month')  # format: YYYY-MM
    category = request.args.get('category')
    conn = get_db()
    query = 'SELECT * FROM transactions'
    params = []
    conditions = []

    if month:
        conditions.append("strftime('%Y-%m', date) = ?")
        params.append(month)
    if category and category != 'all':
        conditions.append("category = ?")
        params.append(category)

    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    query += ' ORDER BY date DESC, id DESC'

    rows = conn.execute(query, params).fetchall()
    conn.close()

    transactions = []
    for r in rows:
        transactions.append({
            'id': r['id'],
            'name': r['name'],
            'category': r['category'],
            'emoji': r['emoji'],
            'amount': r['amount'],
            'type': r['type'],
            'description': r['description'],
            'date': r['date']
        })
    return jsonify(transactions)

@app.route('/api/transactions', methods=['POST'])
def add_transaction():
    data = request.json
    amount = abs(float(data.get('amount', 0)))
    tx_type = data.get('type', 'expense')
    if tx_type == 'expense':
        amount = -amount

    conn = get_db()
    c = conn.execute('''INSERT INTO transactions (name, category, emoji, amount, type, description, date)
        VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (data.get('name', 'Transaction'),
         data.get('category', 'other'),
         data.get('emoji', '📦'),
         amount,
         tx_type,
         data.get('description', ''),
         data.get('date', date.today().isoformat())))
    conn.commit()
    tx_id = c.lastrowid
    conn.close()
    return jsonify({'success': True, 'id': tx_id})

@app.route('/api/transactions/<int:tx_id>', methods=['DELETE'])
def delete_transaction(tx_id):
    conn = get_db()
    conn.execute('DELETE FROM transactions WHERE id = ?', (tx_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ===== SUMMARY / DASHBOARD API =====

@app.route('/api/summary', methods=['GET'])
def get_summary():
    """Returns dashboard summary for current month"""
    month = request.args.get('month', date.today().strftime('%Y-%m'))
    conn = get_db()

    # Income this month
    income_row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE type='income' AND strftime('%Y-%m', date) = ?",
        (month,)).fetchone()
    income = income_row['total']

    # Expenses this month (stored as negative)
    expense_row = conn.execute(
        "SELECT COALESCE(SUM(ABS(amount)), 0) as total FROM transactions WHERE type='expense' AND strftime('%Y-%m', date) = ?",
        (month,)).fetchone()
    expenses = expense_row['total']

    # Total saved across goals
    saved_row = conn.execute("SELECT COALESCE(SUM(saved), 0) as total FROM goals").fetchone()
    total_saved = saved_row['total']

    balance = income - expenses

    # Spending by category
    cat_rows = conn.execute(
        "SELECT category, COALESCE(SUM(ABS(amount)), 0) as total FROM transactions WHERE type='expense' AND strftime('%Y-%m', date) = ? GROUP BY category ORDER BY total DESC",
        (month,)).fetchall()
    categories = [{'category': r['category'], 'total': r['total']} for r in cat_rows]

    # Daily spending for trend chart
    daily_rows = conn.execute(
        "SELECT CAST(strftime('%d', date) AS INTEGER) as day, COALESCE(SUM(ABS(amount)), 0) as total FROM transactions WHERE type='expense' AND strftime('%Y-%m', date) = ? GROUP BY day ORDER BY day",
        (month,)).fetchall()
    daily_spending = {r['day']: r['total'] for r in daily_rows}

    # Previous month for comparison
    year, mon = int(month[:4]), int(month[5:])
    if mon == 1:
        prev_month = f"{year-1}-12"
    else:
        prev_month = f"{year}-{mon-1:02d}"

    prev_cat_rows = conn.execute(
        "SELECT category, COALESCE(SUM(ABS(amount)), 0) as total FROM transactions WHERE type='expense' AND strftime('%Y-%m', date) = ? GROUP BY category",
        (prev_month,)).fetchall()
    prev_categories = {r['category']: r['total'] for r in prev_cat_rows}

    conn.close()

    return jsonify({
        'month': month,
        'income': income,
        'expenses': expenses,
        'balance': balance,
        'total_saved': total_saved,
        'spending_ratio': round((expenses / income * 100) if income > 0 else 0, 1),
        'categories': categories,
        'daily_spending': daily_spending,
        'prev_categories': prev_categories
    })

# ===== GOALS API =====

@app.route('/api/goals', methods=['GET'])
def get_goals():
    conn = get_db()
    rows = conn.execute('SELECT * FROM goals ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([{
        'id': r['id'],
        'name': r['name'],
        'emoji': r['emoji'],
        'saved': r['saved'],
        'target': r['target']
    } for r in rows])

@app.route('/api/goals', methods=['POST'])
def add_goal():
    data = request.json
    conn = get_db()
    c = conn.execute('INSERT INTO goals (name, emoji, saved, target) VALUES (?, ?, ?, ?)',
        (data.get('name', 'Goal'),
         data.get('emoji', '🎯'),
         data.get('saved', 0),
         data.get('target', 0)))
    conn.commit()
    goal_id = c.lastrowid
    conn.close()
    return jsonify({'success': True, 'id': goal_id})

@app.route('/api/goals/<int:goal_id>', methods=['PUT'])
def update_goal(goal_id):
    data = request.json
    conn = get_db()
    if 'add_amount' in data:
        conn.execute('UPDATE goals SET saved = MIN(saved + ?, target) WHERE id = ?',
            (abs(float(data['add_amount'])), goal_id))
    else:
        fields, values = [], []
        for key in ['name', 'emoji', 'saved', 'target']:
            if key in data:
                fields.append(f"{key} = ?")
                values.append(data[key])
        if fields:
            values.append(goal_id)
            conn.execute(f"UPDATE goals SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/goals/<int:goal_id>', methods=['DELETE'])
def delete_goal(goal_id):
    conn = get_db()
    conn.execute('DELETE FROM goals WHERE id = ?', (goal_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ===== MONEY PULSE API =====

@app.route('/api/pulse', methods=['GET'])
def get_pulse():
    conn = get_db()
    rows = conn.execute('SELECT * FROM money_pulse ORDER BY created_at DESC LIMIT 8').fetchall()
    conn.close()
    return jsonify([{
        'id': r['id'],
        'week': r['week'],
        'mood': r['mood'],
        'highlight': r['highlight'],
        'challenge': r['challenge'],
        'goal': r['goal']
    } for r in rows])

@app.route('/api/pulse', methods=['POST'])
def add_pulse():
    data = request.json
    conn = get_db()
    conn.execute('INSERT INTO money_pulse (week, mood, highlight, challenge, goal) VALUES (?, ?, ?, ?, ?)',
        (data.get('week', ''),
         data.get('mood', 'neutral'),
         data.get('highlight', ''),
         data.get('challenge', ''),
         data.get('goal', '')))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/pulse/current-week', methods=['GET'])
def get_current_pulse():
    """Check if pulse is done for current week"""
    today = date.today()
    iso = today.isocalendar()
    current_week = f"{iso[0]}-W{iso[1]}"
    conn = get_db()
    row = conn.execute('SELECT * FROM money_pulse WHERE week = ?', (current_week,)).fetchone()
    conn.close()
    if row:
        return jsonify({
            'completed': True,
            'mood': row['mood'],
            'highlight': row['highlight'],
            'challenge': row['challenge'],
            'goal': row['goal']
        })
    return jsonify({'completed': False, 'current_week': current_week})

# ===== DUE PAYMENTS API =====

@app.route('/api/dues', methods=['GET'])
def get_dues():
    conn = get_db()
    rows = conn.execute('SELECT * FROM due_payments ORDER BY due_date ASC').fetchall()
    conn.close()
    return jsonify([{
        'id': r['id'], 'name': r['name'], 'amount': r['amount'],
        'due_date': r['due_date'], 'type': r['type'], 'emoji': r['emoji'],
        'is_recurring': r['is_recurring'], 'recur_months': r['recur_months'],
        'is_paid': r['is_paid'], 'paid_date': r['paid_date']
    } for r in rows])

@app.route('/api/dues/upcoming', methods=['GET'])
def get_upcoming_dues():
    """Get unpaid dues within next 5 days (or overdue)"""
    from datetime import timedelta
    today = date.today()
    cutoff = (today + timedelta(days=5)).isoformat()
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM due_payments WHERE is_paid = 0 AND due_date <= ? ORDER BY due_date ASC",
        (cutoff,)).fetchall()
    conn.close()
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
def add_due():
    data = request.json
    type_emojis = {'emi': '\U0001f3e6', 'subscription': '\U0001f504', 'personal': '\U0001f4cc'}
    due_type = data.get('type', 'personal')
    conn = get_db()
    c = conn.execute(
        'INSERT INTO due_payments (name, amount, due_date, type, emoji, is_recurring, recur_months) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (data.get('name', 'Payment'),
         abs(float(data.get('amount', 0))),
         data.get('due_date', date.today().isoformat()),
         due_type,
         type_emojis.get(due_type, '\ud83d\udcc5'),
         1 if data.get('is_recurring') else 0,
         data.get('recur_months', 1)))
    conn.commit()
    due_id = c.lastrowid
    conn.close()
    return jsonify({'success': True, 'id': due_id})

@app.route('/api/dues/<int:due_id>/pay', methods=['POST'])
def mark_due_paid(due_id):
    """Mark a due as paid. If recurring, create next month's due."""
    from datetime import timedelta
    today = date.today()
    conn = get_db()
    row = conn.execute('SELECT * FROM due_payments WHERE id = ?', (due_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'error': 'Not found'}), 404

    # Mark current as paid
    conn.execute('UPDATE due_payments SET is_paid = 1, paid_date = ? WHERE id = ?',
        (today.isoformat(), due_id))

    # Also log as expense transaction
    conn.execute('INSERT INTO transactions (name, category, emoji, amount, type, description, date) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (row['name'], 'bills', row['emoji'], -abs(row['amount']), 'expense',
         f"Due payment: {row['name']}", today.isoformat()))

    # If recurring, create next due
    if row['is_recurring']:
        old_due = date.fromisoformat(row['due_date'])
        months = row['recur_months'] or 1
        # Add months
        new_month = old_due.month + months
        new_year = old_due.year + (new_month - 1) // 12
        new_month = ((new_month - 1) % 12) + 1
        try:
            new_due_date = old_due.replace(year=new_year, month=new_month)
        except ValueError:
            import calendar
            last_day = calendar.monthrange(new_year, new_month)[1]
            new_due_date = old_due.replace(year=new_year, month=new_month, day=min(old_due.day, last_day))

        conn.execute(
            'INSERT INTO due_payments (name, amount, due_date, type, emoji, is_recurring, recur_months) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (row['name'], row['amount'], new_due_date.isoformat(), row['type'], row['emoji'], 1, months))

    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/dues/<int:due_id>', methods=['DELETE'])
def delete_due(due_id):
    conn = get_db()
    conn.execute('DELETE FROM due_payments WHERE id = ?', (due_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ===== RESET =====

@app.route('/api/reset', methods=['POST'])
def reset_all():
    conn = get_db()
    conn.execute('DELETE FROM user')
    conn.execute('DELETE FROM transactions')
    conn.execute('DELETE FROM goals')
    conn.execute('DELETE FROM money_pulse')
    conn.execute('DELETE FROM due_payments')
    conn.commit()
    conn.close()
    if os.path.exists(DB_PATH):
        pass  # keep the file, tables are just empty
    return jsonify({'success': True})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('RENDER') is None
    print(f"Penny Buddy server running at http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
