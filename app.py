"""
Deadstock Inventory Management System  (Flask + MySQL)
"""

from flask import Flask, render_template, request, redirect, url_for, session, make_response
import mysql.connector
import re, smtplib, random, secrets, io
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from functools import wraps

# ── ReportLab ──────────────────────────────────────────────────────
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                 Paragraph, Spacer, HRFlowable)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

app = Flask(__name__)
app.secret_key = 'deadstock_secret_key_2024'

DB_CONFIG = dict(host='127.0.0.1', user='root', password='Samruddhi@123', database='deadstock_db')

# ── Email config ────────────────────────────────────────────────────
MAIL_SENDER   = 'shalakaparhad21@gmail.com'      # ← change to your Gmail
MAIL_PASSWORD = 'uozu otzm cpfm vujk'         # ← change to your App Password

# ── In-memory OTP store ─────────────────────────────────────────────
otp_store = {}  # keyed by email

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

ROLE_TABLES = {
    'Admin': ['DEADSTOCK','BRANCH','WAREHOUSE','STOCK_ALLOCATION',
              'HEAD','CONTACTS','MATERIAL','REPORT'], 
    'Branch':           ['DEADSTOCK','MATERIAL'],
    'Warehouse':        ['DEADSTOCK','BRANCH'],
    'Stock_Allocation': ['DEADSTOCK','STOCK_ALLOCATION','REPORT'], 
}

ALLOC_COLOR_MAP = {
    'Recycle':  '#2d6a4f',
    'Donate':   '#1565c0',
    'Resell':   '#e65100',
    'Upcycle':  '#6a1e2d',
    'Rebrand':  '#4a148c',
    'Disposal': '#607d8b',
}

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'role' not in session:
            return redirect(url_for('landing'))
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get('role') not in roles:
                return render_template('denied.html')
            return f(*args, **kwargs)
        return decorated
    return decorator

def valid_email(e):
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', e.strip()))

def valid_phone(p):
    return bool(re.match(r'^\d{10}$', p.strip()))

def mask_email(email):
    """Return a***@domain.com style masked email."""
    parts = email.split('@')
    if len(parts) != 2:
        return email
    local = parts[0]
    return local[0] + '***@' + parts[1]

def send_otp_email(to_email, otp):
    """Send OTP email via Gmail SMTP SSL."""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Deadstock Inventory – Your OTP'
    msg['From']    = MAIL_SENDER
    msg['To']      = to_email
    html = f"""
    <html><body style="font-family:'Segoe UI',sans-serif;background:#f4f6f9;padding:32px">
    <div style="max-width:480px;margin:0 auto;background:white;border-radius:14px;
                padding:40px;box-shadow:0 2px 12px rgba(0,0,0,.1)">
      <div style="text-align:center;margin-bottom:28px">
        <div style="font-size:36px">♻</div>
        <h2 style="color:#1a1a2e;margin:8px 0 4px">Deadstock Inventory</h2>
        <p style="color:#888;font-size:14px">Password Reset OTP</p>
      </div>
      <p style="color:#444;font-size:14px;margin-bottom:20px">
        Your one-time password for resetting your account password is:
      </p>
      <div style="text-align:center;margin:24px 0">
        <span style="font-size:42px;font-weight:700;color:#2d6a4f;
                     letter-spacing:10px;border:2px solid #2d6a4f;
                     border-radius:10px;padding:12px 28px">{otp}</span>
      </div>
      <p style="color:#888;font-size:13px;text-align:center;margin-top:20px">
        ⏱ Valid for <strong>10 minutes</strong>.<br>
        🔒 Do not share this OTP with anyone.
      </p>
      <hr style="border:none;border-top:1px solid #eee;margin:24px 0">
      <p style="color:#aaa;font-size:11px;text-align:center">
        If you did not request this, please ignore this email.
      </p>
    </div></body></html>"""
    msg.attach(MIMEText(html, 'html'))
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(MAIL_SENDER, MAIL_PASSWORD)
            s.sendmail(MAIL_SENDER, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f'[EMAIL ERROR] {e}')
        return False

@app.template_filter('myenumerate')
def jinja_enumerate(iterable):
    return list(enumerate(iterable))

# ══════════════════════════════════════════════════════════════════
# LANDING
# ══════════════════════════════════════════════════════════════════
@app.route('/')
def landing():
    return render_template('landing.html')

# ══════════════════════════════════════════════════════════════════
# LOGIN  –  blocks deleted-branch/warehouse heads
# ══════════════════════════════════════════════════════════════════
@app.route('/login/<role>', methods=['GET','POST'])
def login(role):
    if role not in ['Admin','Branch','Warehouse','Stock_Allocation']:
        return redirect(url_for('landing'))
    error = None
    if request.method == 'POST':
        db = get_db(); cur = db.cursor()
        try:
            if role == 'Admin':
                cur.execute("SELECT Username FROM ADMIN WHERE Username=%s AND Password=%s",
                            (request.form.get('username',''), request.form.get('password','')))
                row = cur.fetchone()
                if row:
                    session.update({'role':'Admin','name':'Admin',
                                    'head_id':None,'branch_id':None,'warehouse_id':None})
                    return redirect(url_for('dashboard'))
                error = 'Invalid username or password.'
            else:
                cur.execute("SELECT Head_ID,Name FROM HEAD WHERE Email=%s AND Password=%s AND Status=%s",
                            (request.form.get('email',''), request.form.get('password',''), role))
                row = cur.fetchone()
                if row:
                    head_id = row[0]; name = row[1]
                    branch_id = warehouse_id = None
                    if role == 'Branch':
                        cur.execute("SELECT Branch_ID FROM BRANCH WHERE Head_ID=%s LIMIT 1",(head_id,))
                        br = cur.fetchone()
                        if not br:
                            error = 'Access denied. Your branch has been removed. Contact Admin.'
                            return render_template('login.html', role=role, error=error)
                        branch_id = br[0]
                    elif role == 'Warehouse':
                        cur.execute("SELECT Warehouse_ID FROM WAREHOUSE WHERE Head_ID=%s LIMIT 1",(head_id,))
                        wh = cur.fetchone()
                        if not wh:
                            error = 'Access denied. Your warehouse has been removed. Contact Admin.'
                            return render_template('login.html', role=role, error=error)
                        warehouse_id = wh[0]
                    session.update({'role':role,'name':name,'head_id':head_id,
                                    'branch_id':branch_id,'warehouse_id':warehouse_id})
                    return redirect(url_for('dashboard'))
                error = 'Invalid email or password.'
        finally:
            cur.close(); db.close()
    return render_template('login.html', role=role, error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('landing'))

# ══════════════════════════════════════════════════════════════════
# CHANGE SET 1 – FORGOT PASSWORD / OTP RESET
# ══════════════════════════════════════════════════════════════════

@app.route('/forgot_password/<role>', methods=['GET','POST'])
def forgot_password(role):
    if role not in ['Admin','Branch','Warehouse','Stock_Allocation']:
        return redirect(url_for('landing'))
    error = None
    if request.method == 'POST':
        email = request.form.get('email','').strip()
        if not valid_email(email):
            error = 'Please enter a valid email address.'
        else:
            db = get_db(); cur = db.cursor()
            found = False
            try:
                if role == 'Admin':
                    cur.execute("SELECT Email FROM ADMIN WHERE Email=%s", (email,))
                    found = cur.fetchone() is not None
                 
                else:
                    cur.execute("SELECT Head_ID FROM HEAD WHERE Email=%s AND Status=%s",
                                (email, role))
                    row = cur.fetchone()
                    found = row is not None
            finally:
                cur.close(); db.close()

            if not found:
                error = 'No account found with this email for the selected role.'
            else:
                otp   = str(random.randint(100000, 999999))
                token = secrets.token_urlsafe(32)
                otp_store[email] = {
                    'otp':      otp,
                    'expires':  datetime.now() + timedelta(minutes=10),
                    'token':    token,
                    'role':     role,
                    'used':     False,
                    'attempts': 0
                }
                sent = send_otp_email(email, otp)
                if not sent:
                    # For dev/testing: still allow flow but warn
                    print(f'[DEV] OTP for {email}: {otp}')
                return redirect(url_for('verify_otp', role=role, email=email))

    return render_template('forgot_password.html', role=role, error=error)


@app.route('/verify_otp/<role>', methods=['GET','POST'])
def verify_otp(role):
    if role not in ['Admin','Branch','Warehouse','Stock_Allocation']:
        return redirect(url_for('landing'))
    email = request.args.get('email','') or request.form.get('email','')
    error = None
    resent = request.args.get('resent','')

    if request.method == 'POST':
        digits = [request.form.get(f'd{i}','') for i in range(1,7)]
        entered_otp = ''.join(digits)
        entry = otp_store.get(email)

        if not entry:
            error = 'OTP expired or not found. Please request a new one.'
        elif datetime.now() > entry['expires']:
            otp_store.pop(email, None)
            error = 'OTP expired. Please request a new one.'
        elif entry['attempts'] >= 3:
            error = 'Too many incorrect attempts. Please request a new OTP.'
        elif entered_otp != entry['otp']:
            entry['attempts'] += 1
            remaining = 3 - entry['attempts']
            if remaining <= 0:
                error = 'Too many incorrect attempts. Please request a new OTP.'
            else:
                error = f'Incorrect OTP. {remaining} attempt(s) remaining.'
        else:
            entry['used'] = True
            return redirect(url_for('reset_password',
                                    token=entry['token'], email=email))

    masked = mask_email(email) if email else ''
    return render_template('verify_otp.html', role=role, email=email,
                           masked_email=masked, error=error, resent=resent)


@app.route('/resend_otp/<role>')
def resend_otp(role):
    email = request.args.get('email','')
    if not email or email not in otp_store:
        return redirect(url_for('forgot_password', role=role))
    otp   = str(random.randint(100000, 999999))
    token = secrets.token_urlsafe(32)
    otp_store[email].update({
        'otp':      otp,
        'token':    token,
        'expires':  datetime.now() + timedelta(minutes=10),
        'attempts': 0,
        'used':     False
    })
    sent = send_otp_email(email, otp)
    if not sent:
        print(f'[DEV] Resend OTP for {email}: {otp}')
    return redirect(url_for('verify_otp', role=role, email=email, resent='1'))


@app.route('/reset_password', methods=['GET','POST'])
def reset_password():
    email = request.args.get('email','') or request.form.get('email','')
    token = request.args.get('token','') or request.form.get('token','')
    entry = otp_store.get(email)

    # Validate token
    valid = (entry is not None and
             entry.get('token') == token and
             entry.get('used') is True)

    if request.method == 'POST':
        if not valid:
            return render_template('reset_password.html',
                                   email=email, token=token,
                                   error='Invalid or expired reset link.',
                                   success=None, role=None)
        pw  = request.form.get('password','')
        cpw = request.form.get('confirm_password','')
        if len(pw) < 4:
            return render_template('reset_password.html',
                                   email=email, token=token,
                                   error='Password must be at least 4 characters.',
                                   success=None, role=entry['role'])
        if pw != cpw:
            return render_template('reset_password.html',
                                   email=email, token=token,
                                   error='Passwords do not match.',
                                   success=None, role=entry['role'])
        db = get_db(); cur = db.cursor()
        try:
            if entry['role'] == 'Admin':
                cur.execute("UPDATE ADMIN SET Password=%s WHERE Email=%s", (pw, email))
            else:
                cur.execute("UPDATE HEAD SET Password=%s WHERE Email=%s AND Status=%s",
                            (pw, email, entry['role']))
            db.commit()
            role = entry['role']
            otp_store.pop(email, None)
            return render_template('reset_password.html',
                                   email=email, token=token,
                                   error=None,
                                   success='Password updated successfully! You can now log in.',
                                   role=role)
        except Exception as e:
            return render_template('reset_password.html',
                                   email=email, token=token,
                                   error=f'Error: {e}', success=None,
                                   role=entry['role'])
        finally:
            cur.close(); db.close()

    if not valid:
        return render_template('reset_password.html',
                               email=email, token=token,
                               error='Invalid or expired reset link.',
                               success=None, role=None)
    return render_template('reset_password.html',
                           email=email, token=token,
                           error=None, success=None, role=entry['role'])

# ══════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════
@app.route('/dashboard')
@login_required
def dashboard():
    role   = session['role']
    tables = ROLE_TABLES.get(role, [])
    db = get_db(); cur = db.cursor()
    stats = {}

    cur.execute("SELECT COUNT(*) FROM DEADSTOCK"); stats['deadstock'] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM BRANCH");    stats['branches']  = cur.fetchone()[0]
    cur.execute("SELECT City,Sustainable_Rating FROM BRANCH ORDER BY Sustainable_Rating DESC LIMIT 1")
    stats['top_branch'] = cur.fetchone()

    if role == 'Branch':
        branch_id = session.get('branch_id')
        stats.update({'my_branch':None,'report':None,
                      'branch_alloc_labels':[],'branch_alloc_values':[],'branch_alloc_colors':[]})
        if branch_id:
            cur.execute("""
                SELECT b.Branch_ID,b.City,b.Sustainable_Rating,b.Last_Audit,
                       b.Warehouse_ID,b.Head_ID,w.City,h2.Name,c.Contact_no
                FROM BRANCH b
                LEFT JOIN WAREHOUSE w ON b.Warehouse_ID=w.Warehouse_ID
                LEFT JOIN HEAD h2     ON w.Head_ID=h2.Head_ID
                LEFT JOIN CONTACTS c  ON h2.Head_ID=c.Head_ID
                WHERE b.Branch_ID=%s LIMIT 1""", (branch_id,))
            stats['my_branch'] = cur.fetchone()
            cur.execute("""SELECT Report_ID,Branch_ID,Items_Resold,Items_Recycled,
                                  Items_Donated,Items_Upcycled,Items_Rebranded,
                                  Items_Disposed,Estimated_Waste_Reduced
                           FROM REPORT WHERE Branch_ID=%s""", (branch_id,))
            stats['report'] = cur.fetchone()
            cur.execute("""SELECT sa.Allocation_Type,SUM(sa.Quantity)
                           FROM STOCK_ALLOCATION sa
                           JOIN DEADSTOCK d ON sa.Deadstock_ID=d.Deadstock_ID
                           WHERE d.Branch_ID=%s GROUP BY sa.Allocation_Type""", (branch_id,))
            rows = cur.fetchall()
            stats['branch_alloc_labels'] = [r[0] for r in rows]
            stats['branch_alloc_values'] = [int(r[1]) for r in rows]
            stats['branch_alloc_colors'] = [ALLOC_COLOR_MAP.get(r[0],'#999') for r in rows]

    if role == 'Warehouse':
        wh_id = session.get('warehouse_id')
        stats.update({'warehouse_info':None,'sa_contact':None})
        if wh_id:
            cur.execute("""SELECT w.Warehouse_ID,w.City,w.Last_Audit,w.Capacity,h.Name,c.Contact_no
                           FROM WAREHOUSE w JOIN HEAD h ON w.Head_ID=h.Head_ID
                           LEFT JOIN CONTACTS c ON h.Head_ID=c.Head_ID
                           WHERE w.Warehouse_ID=%s LIMIT 1""", (wh_id,))
            stats['warehouse_info'] = cur.fetchone()
        cur.execute("""SELECT h.Name,c.Contact_no FROM HEAD h
                       LEFT JOIN CONTACTS c ON h.Head_ID=c.Head_ID
                       WHERE h.Status='Stock_Allocation' LIMIT 1""")
        stats['sa_contact'] = cur.fetchone()

    if role == 'Stock_Allocation':
        cur.execute("""SELECT Allocation_Type,COUNT(*),SUM(Quantity)
                       FROM STOCK_ALLOCATION GROUP BY Allocation_Type ORDER BY Allocation_Type""")
        stats['sustainability'] = cur.fetchall()
        cur.execute("""SELECT Allocation_Type,SUM(Quantity) FROM STOCK_ALLOCATION
                       GROUP BY Allocation_Type ORDER BY Allocation_Type""")
        stats['allocations']  = cur.fetchall()
        stats['alloc_colors'] = ALLOC_COLOR_MAP

    if role == 'Admin':
        cur.execute("""SELECT Allocation_Type,SUM(Quantity) FROM STOCK_ALLOCATION
                       GROUP BY Allocation_Type ORDER BY Allocation_Type""")
        stats['allocations']  = cur.fetchall()
        stats['alloc_colors'] = ALLOC_COLOR_MAP

    cur.close(); db.close()
    return render_template('dashboard.html', tables=tables, stats=stats)

# ══════════════════════════════════════════════════════════════════
# SHOW TABLE  –  CHANGE SET 2: LEFT JOINs for Warehouse & Admin
# ══════════════════════════════════════════════════════════════════
@app.route('/show/<table_name>', methods=['GET'])
@login_required
def show_table(table_name):
    role   = session['role']
    tables = ROLE_TABLES.get(role, [])

    if table_name == 'HEAD':
        if role != 'Admin':
            return render_template('denied.html')
        return redirect(url_for('show_heads'))

    if table_name not in tables:
        return render_template('denied.html')

    db = get_db(); cur = db.cursor()
    rows = []; headers = []

    f_branch   = request.args.get('f_branch','')
    f_category = request.args.get('f_category','').strip()
    f_size     = request.args.get('f_size','')
    f_alloc    = request.args.get('f_alloc','')
    f_city     = request.args.get('f_city','').strip()
    f_role     = request.args.get('f_role','')
    f_sq       = request.args.get('f_sq','')
    f_sent_wh  = request.args.get('f_sent_wh','')
    f_sent_sa  = request.args.get('f_sent_sa','')

    all_branches  = []
    all_cities_br = []
    all_cities_wh = []
    all_sizes     = ['XS','S','M','L','XL','XXL']
    all_alloc     = ['Recycle','Donate','Resell','Upcycle','Rebrand','Disposal']
    all_sq        = ['High','Medium','Low']
    all_roles     = ['Branch','Warehouse','Stock_Allocation']

    if table_name == 'BRANCH':
        headers = ['Branch ID','Warehouse ID','Head ID','City','Last Audit','Sustainable Rating']
        if role == 'Branch':
            cur.execute("SELECT * FROM BRANCH WHERE Branch_ID=%s",(session.get('branch_id'),))
            rows = cur.fetchall()
        elif role == 'Warehouse':
            wh_id = session.get('warehouse_id')
            cur.execute("SELECT DISTINCT City FROM BRANCH WHERE Warehouse_ID=%s ORDER BY City",(wh_id,))
            all_cities_br = [r[0] for r in cur.fetchall()]
            q = "SELECT * FROM BRANCH WHERE Warehouse_ID=%s"; p = [wh_id]
            if f_city: q += " AND City=%s"; p.append(f_city)
            cur.execute(q + " ORDER BY Branch_ID", p)
            rows = cur.fetchall()
        else:
            # Admin: show active branches + deleted branches (with is_deleted flag)
            cur.execute("SELECT DISTINCT City FROM BRANCH ORDER BY City")
            all_cities_br = [r[0] for r in cur.fetchall()]
            # Each row: (Branch_ID, Warehouse_ID, Head_ID, City, Last_Audit, Sustainable_Rating, is_deleted)
            q = """
                SELECT Branch_ID, Warehouse_ID, Head_ID, City, Last_Audit, Sustainable_Rating, 0 AS is_deleted
                FROM BRANCH
                WHERE 1=1 {city_filter}
                UNION ALL
                SELECT Branch_ID, Warehouse_ID, Head_ID, City, Last_Audit, Sustainable_Rating, 1 AS is_deleted
                FROM DELETED_BRANCH
                WHERE 1=1 {city_filter2}
                ORDER BY is_deleted ASC, Branch_ID ASC
            """
            p = []
            city_clause = ""
            if f_city:
                city_clause = " AND City=%s"
                p.extend([f_city, f_city])
            final_q = q.replace('{city_filter}', city_clause).replace('{city_filter2}', city_clause)
            cur.execute(final_q, p)
            rows = cur.fetchall()

    elif table_name == 'WAREHOUSE':
        headers = ['Warehouse ID','Head ID','City','Last Audit','Capacity']
        if role == 'Warehouse':
            cur.execute("SELECT * FROM WAREHOUSE WHERE Warehouse_ID=%s",(session.get('warehouse_id'),))
            rows = cur.fetchall()
        else:
            cur.execute("SELECT DISTINCT City FROM WAREHOUSE ORDER BY City")
            all_cities_wh = [r[0] for r in cur.fetchall()]
            q = "SELECT * FROM WAREHOUSE WHERE 1=1"; p = []
            if f_city: q += " AND City=%s"; p.append(f_city)
            cur.execute(q + " ORDER BY Warehouse_ID", p)
            rows = cur.fetchall()

    elif table_name == 'DEADSTOCK':
        # Branches for filter dropdown: active + deleted (for Admin history)
        if role == 'Admin':
            cur.execute("""
                SELECT Branch_ID, City FROM BRANCH
                UNION
                SELECT Branch_ID, CONCAT(City,' (Deleted)') FROM DELETED_BRANCH
                ORDER BY Branch_ID
            """)
        else:
            cur.execute("SELECT Branch_ID,City FROM BRANCH ORDER BY Branch_ID")
        all_branches = cur.fetchall()

        if role == 'Branch':
            headers=['ID','Branch ID','Category','Size','Material ID','Quantity','Sent To Warehouse','Sent To SA','Allocated Type']
            q="SELECT * FROM DEADSTOCK WHERE Branch_ID=%s AND Sent_To_Warehouse=0"; p=[session.get('branch_id')]
            if f_category: q+=" AND Category LIKE %s"; p.append(f'%{f_category}%')
            if f_size:     q+=" AND Size=%s"; p.append(f_size)
            cur.execute(q, p)

        elif role == 'Warehouse':
            # LEFT JOIN so deadstock from deleted branches (orphaned) still appears.
            # Match on current Warehouse OR fall back to original warehouse via DELETED_BRANCH.
            wh_id = session.get('warehouse_id')
            headers=['ID','Branch ID','Branch','Category','Size','Material ID','Quantity','Sent To Warehouse','Sent To SA']
            q="""SELECT d.Deadstock_ID, d.Branch_ID,
                        COALESCE(b.City, db2.City, 'Deleted Branch') AS BranchCity,
                        d.Category, d.Size, d.Material_ID,
                        d.Quantity, d.Sent_To_Warehouse, d.Sent_To_SA
                 FROM DEADSTOCK d
                 LEFT JOIN BRANCH b ON d.Branch_ID = b.Branch_ID
                 LEFT JOIN DELETED_BRANCH db2 ON d.Branch_ID = db2.Branch_ID
                 WHERE d.Sent_To_Warehouse = 1 AND d.Sent_To_SA = 0
                   AND (b.Warehouse_ID = %s OR db2.Warehouse_ID = %s)"""
            p=[wh_id, wh_id]
            if f_category: q+=" AND d.Category LIKE %s"; p.append(f'%{f_category}%')
            if f_size:     q+=" AND d.Size=%s"; p.append(f_size)
            cur.execute(q+" ORDER BY d.Deadstock_ID", p)

        elif role == 'Stock_Allocation':
            headers=['ID','Branch ID','Category','Size','Material ID','Quantity','Sent To Warehouse','Sent To SA','Allocated Type']
            q="SELECT * FROM DEADSTOCK WHERE Sent_To_SA=1"; p=[]
            if f_category: q+=" AND Category LIKE %s"; p.append(f'%{f_category}%')
            if f_size:     q+=" AND Size=%s"; p.append(f_size)
            if f_alloc=='__none__': q+=" AND Allocated_Type IS NULL"
            elif f_alloc:           q+=" AND Allocated_Type=%s"; p.append(f_alloc)
            cur.execute(q+" ORDER BY Deadstock_ID", p)

        else:
            # Admin: LEFT JOIN with BRANCH so deleted-branch deadstock is always visible.
            # COALESCE shows "Deleted Branch" when branch no longer exists.
            headers=['ID','Branch ID','Branch','Category','Size','Material ID','Quantity','Sent To WH','Sent To SA','Allocated Type']
            q="""SELECT d.Deadstock_ID, d.Branch_ID,
                        COALESCE(b.City, db2.City, 'Deleted Branch') AS BranchCity,
                        d.Category, d.Size, d.Material_ID,
                        d.Quantity, d.Sent_To_Warehouse, d.Sent_To_SA, d.Allocated_Type
                 FROM DEADSTOCK d
                 LEFT JOIN BRANCH b ON d.Branch_ID = b.Branch_ID
                 LEFT JOIN DELETED_BRANCH db2 ON d.Branch_ID = db2.Branch_ID
                 WHERE 1=1"""
            p=[]
            if f_branch:   q+=" AND d.Branch_ID=%s"; p.append(f_branch)
            if f_category: q+=" AND d.Category LIKE %s"; p.append(f'%{f_category}%')
            if f_size:     q+=" AND d.Size=%s"; p.append(f_size)
            if f_alloc=='__none__': q+=" AND d.Allocated_Type IS NULL"
            elif f_alloc:           q+=" AND d.Allocated_Type=%s"; p.append(f_alloc)
            if f_sent_wh:  q+=" AND d.Sent_To_Warehouse=%s"; p.append(f_sent_wh)
            if f_sent_sa:  q+=" AND d.Sent_To_SA=%s"; p.append(f_sent_sa)
            cur.execute(q+" ORDER BY d.Deadstock_ID", p)
        rows = cur.fetchall()

    elif table_name == 'STOCK_ALLOCATION':
        headers=['Allocation ID','Deadstock ID','Head ID','Type','Quantity','Allocated At']
        cur.execute("SELECT Branch_ID,City FROM BRANCH ORDER BY Branch_ID")
        all_branches = cur.fetchall()
        q="""SELECT sa.* FROM STOCK_ALLOCATION sa
             JOIN DEADSTOCK d ON sa.Deadstock_ID=d.Deadstock_ID WHERE 1=1"""
        p=[]
        if f_branch: q+=" AND d.Branch_ID=%s"; p.append(f_branch)
        if f_alloc:  q+=" AND sa.Allocation_Type=%s"; p.append(f_alloc)
        cur.execute(q+" ORDER BY sa.Allocated_At DESC", p)
        rows = cur.fetchall()

    elif table_name == 'REPORT':
        if role == 'Branch':
            headers=['Report ID','Branch ID','Resold','Recycled','Donated','Upcycled','Rebranded','Disposed','Waste Reduced (kg)']
            cur.execute("""SELECT Report_ID,Branch_ID,Items_Resold,Items_Recycled,
                                  Items_Donated,Items_Upcycled,Items_Rebranded,
                                  Items_Disposed,Estimated_Waste_Reduced
                           FROM REPORT WHERE Branch_ID=%s""",(session.get('branch_id'),))
        else:
            headers=['Report ID','Branch City','Resold','Recycled','Donated','Upcycled','Rebranded','Disposed','Waste Reduced (kg)']
            cur.execute("""SELECT r.Report_ID,b.City,r.Items_Resold,r.Items_Recycled,
                                  r.Items_Donated,r.Items_Upcycled,r.Items_Rebranded,
                                  r.Items_Disposed,r.Estimated_Waste_Reduced
                           FROM REPORT r JOIN BRANCH b ON r.Branch_ID=b.Branch_ID
                           ORDER BY b.City""")
        rows = cur.fetchall()

    elif table_name == 'CONTACTS':
        headers=['Contact ID','Head ID','Contact No']
        q="""SELECT c.Contact_ID,c.Head_ID,c.Contact_no
             FROM CONTACTS c JOIN HEAD h ON c.Head_ID=h.Head_ID WHERE 1=1"""
        p=[]
        if f_role: q+=" AND h.Status=%s"; p.append(f_role)
        cur.execute(q+" ORDER BY c.Head_ID", p)
        rows = cur.fetchall()

    elif table_name == 'MATERIAL':
        headers=['Material ID','Material Name','Sustainability Quality']
        q="SELECT * FROM MATERIAL WHERE 1=1"; p=[]
        if f_sq: q+=" AND Sustainability_Quality=%s"; p.append(f_sq)
        cur.execute(q+" ORDER BY Material_ID", p)
        rows = cur.fetchall()

    
    cur.close(); db.close()
    branch_delete_error = session.pop('branch_delete_error', None)
    return render_template('show_tables.html',
                           table_name=table_name, headers=headers, rows=rows,
                           f_branch=f_branch, f_category=f_category, f_size=f_size,
                           f_alloc=f_alloc, f_city=f_city, f_role=f_role,
                           f_sq=f_sq, f_sent_wh=f_sent_wh, f_sent_sa=f_sent_sa,
                           all_branches=all_branches, all_cities_br=all_cities_br,
                           all_cities_wh=all_cities_wh, all_roles=all_roles,
                           all_sizes=all_sizes, all_alloc=all_alloc, all_sq=all_sq,
                           branch_delete_error=branch_delete_error)

    
# ══════════════════════════════════════════════════════════════════
# SHOW HEADS
# ══════════════════════════════════════════════════════════════════
@app.route('/show/heads')
@login_required
@role_required('Admin')
def show_heads():
    f_role = request.args.get('f_role','')
    f_name = request.args.get('f_name','').strip()
    db = get_db(); cur = db.cursor()
    q="""SELECT h.Head_ID,h.Name,h.Email,h.Status,
                GROUP_CONCAT(c.Contact_no SEPARATOR ', ')
         FROM HEAD h LEFT JOIN CONTACTS c ON h.Head_ID=c.Head_ID WHERE 1=1"""
    p=[]
    if f_role: q+=" AND h.Status=%s"; p.append(f_role)
    if f_name: q+=" AND h.Name LIKE %s"; p.append(f'%{f_name}%')
    q+=" GROUP BY h.Head_ID,h.Name,h.Email,h.Status ORDER BY h.Status,h.Name"
    cur.execute(q, p)
    rows = cur.fetchall()
    cur.close(); db.close()
    return render_template('show_heads.html', rows=rows, f_role=f_role, f_name=f_name,
                           all_roles=['Branch','Warehouse','Stock_Allocation'])

# ══════════════════════════════════════════════════════════════════
# ADMIN BRANCH REPORT
# ══════════════════════════════════════════════════════════════════
@app.route('/admin_branch_report')
@login_required
@role_required('Admin')
def admin_branch_report():
    db = get_db(); cur = db.cursor()
    # LEFT JOIN so reports for deleted branches still appear
    cur.execute("""
        SELECT r.Branch_ID,
               COALESCE(b.City, db2.City, 'Deleted Branch') AS City,
               r.Items_Resold, r.Items_Recycled, r.Items_Donated,
               r.Items_Upcycled, r.Items_Rebranded, r.Items_Disposed,
               r.Estimated_Waste_Reduced
        FROM REPORT r
        LEFT JOIN BRANCH b         ON r.Branch_ID = b.Branch_ID
        LEFT JOIN DELETED_BRANCH db2 ON r.Branch_ID = db2.Branch_ID
        ORDER BY r.Branch_ID
    """)
    rows = cur.fetchall()
    cur.close(); db.close()
    return render_template('admin_branch_report.html', rows=rows)

# ══════════════════════════════════════════════════════════════════
# UPDATE WAREHOUSE
# ══════════════════════════════════════════════════════════════════
@app.route('/update_warehouse/<int:wh_id>', methods=['GET','POST'])
@login_required
@role_required('Admin')
def update_warehouse(wh_id):
    db = get_db(); cur = db.cursor(); msg = None
    if request.method == 'POST':
        f = request.form
        try:
            cur.execute("""UPDATE WAREHOUSE SET Head_ID=%s,City=%s,Last_Audit=%s,Capacity=%s
                           WHERE Warehouse_ID=%s""",
                        (f['head_id'],f['city'],f['last_audit'],f['capacity'],wh_id))
            db.commit(); msg = ('success','Warehouse updated successfully.')
        except Exception as e:
            msg = ('error',f'Error: {e}')
    cur.execute("SELECT * FROM WAREHOUSE WHERE Warehouse_ID=%s",(wh_id,))
    warehouse = cur.fetchone()
    cur.execute("SELECT Head_ID,Name FROM HEAD WHERE Status='Warehouse' ORDER BY Name")
    heads = cur.fetchall()
    cur.close(); db.close()
    return render_template('update_warehouse.html', warehouse=warehouse, heads=heads, msg=msg)

# ══════════════════════════════════════════════════════════════════
# ADD ROUTES
# ══════════════════════════════════════════════════════════════════
@app.route('/add/deadstock', methods=['GET','POST'])
@login_required
@role_required('Branch')
def add_deadstock():
    db = get_db(); cur = db.cursor(); msg = None
    if request.method == 'POST':
        f = request.form
        try:
            cur.execute("""INSERT INTO DEADSTOCK
                               (Branch_ID,Category,Size,Material_ID,Quantity,Sent_To_Warehouse,Sent_To_SA)
                           VALUES (%s,%s,%s,%s,%s,0,0)""",
                        (session['branch_id'],f['category'],f['size'],f['material_id'],f['quantity']))
            db.commit(); msg = ('success','Deadstock item added successfully.')
        except Exception as e:
            msg = ('error',f'Error: {e}')
    cur.execute("SELECT Material_ID,Material_Name FROM MATERIAL ORDER BY Material_Name")
    materials = cur.fetchall()
    cur.close(); db.close()
    return render_template('add_deadstock.html', materials=materials, msg=msg)

# CHANGE SET 3: Only unassigned Branch heads in dropdown; enforce one-head-one-branch
@app.route('/add/branch', methods=['GET','POST'])
@login_required
@role_required('Admin')
def add_branch():
    db = get_db(); cur = db.cursor(); msg = None
    if request.method == 'POST':
        f = request.form
        wh_id   = f.get('warehouse_id') or None
        head_id = f.get('head_id') or None
        if not wh_id:
            msg = ('error','Warehouse is required.')
        elif not head_id:
            msg = ('error','Branch Head is required.')
        else:
            # CHANGE SET 3: Check one-head-one-branch
            cur.execute("SELECT Branch_ID FROM BRANCH WHERE Head_ID=%s LIMIT 1", (head_id,))
            if cur.fetchone():
                msg = ('error','This Head is already managing a branch. One head can only manage one branch at a time.')
            else:
                try:
                    cur.execute("""INSERT INTO BRANCH (Warehouse_ID,Head_ID,City,Last_Audit)
                                   VALUES (%s,%s,%s,CURDATE())""",
                                (wh_id, head_id, f['city']))
                    new_branch_id = cur.lastrowid
                    cur.execute("""INSERT INTO REPORT
                                       (Branch_ID,Items_Resold,Items_Recycled,Items_Donated,
                                        Items_Upcycled,Items_Rebranded,Items_Disposed,Estimated_Waste_Reduced)
                                   VALUES (%s,0,0,0,0,0,0,0.00)""", (new_branch_id,))
                    db.commit(); msg = ('success','Branch added successfully.')
                except Exception as e:
                    msg = ('error',f'Error: {e}')
    cur.execute("SELECT Warehouse_ID,City FROM WAREHOUSE ORDER BY City")
    warehouses = cur.fetchall()
    # CHANGE SET 3: Only Branch heads NOT already assigned to any branch
    cur.execute("""SELECT h.Head_ID,h.Name FROM HEAD h
                   WHERE h.Status='Branch'
                   AND h.Head_ID NOT IN (SELECT Head_ID FROM BRANCH)
                   ORDER BY h.Name""")
    heads = cur.fetchall()
    cur.close(); db.close()
    return render_template('add_branch.html', warehouses=warehouses, heads=heads, msg=msg)

# CHANGE SET 3: Only unassigned Warehouse heads in dropdown; enforce one-head-one-warehouse
@app.route('/add/warehouse', methods=['GET','POST'])
@login_required
@role_required('Admin')
def add_warehouse():
    db = get_db(); cur = db.cursor(); msg = None
    if request.method == 'POST':
        f = request.form
        head_id = f.get('head_id') or None
        if not head_id:
            msg = ('error','Warehouse Head is required.')
        else:
            # CHANGE SET 3: Check one-head-one-warehouse
            cur.execute("SELECT Warehouse_ID FROM WAREHOUSE WHERE Head_ID=%s LIMIT 1", (head_id,))
            if cur.fetchone():
                msg = ('error','This Head is already managing a warehouse. One head can only manage one warehouse at a time.')
            else:
                try:
                    cur.execute("""INSERT INTO WAREHOUSE (Head_ID,City,Last_Audit,Capacity)
                                   VALUES (%s,%s,CURDATE(),%s)""",
                                (head_id, f['city'], f['capacity']))
                    db.commit(); msg = ('success','Warehouse added successfully.')
                except Exception as e:
                    msg = ('error',f'Error: {e}')
    # CHANGE SET 3: Only Warehouse heads NOT already assigned to any warehouse
    cur.execute("""SELECT h.Head_ID,h.Name FROM HEAD h
                   WHERE h.Status='Warehouse'
                   AND h.Head_ID NOT IN (SELECT Head_ID FROM WAREHOUSE)
                   ORDER BY h.Name""")
    heads = cur.fetchall()
    cur.close(); db.close()
    return render_template('add_warehouse.html', heads=heads, msg=msg)

@app.route('/add/head', methods=['GET','POST'])
@login_required
@role_required('Admin')
def add_head():
    db = get_db(); cur = db.cursor(); msg = None
    if request.method == 'POST':
        f       = request.form
        email   = f.get('email','').strip()
        contact = f.get('contact_no','').strip()
        if not valid_email(email):
            msg = ('error','Invalid email address format.')
        elif contact and not valid_phone(contact):
            msg = ('error','Contact number must be exactly 10 digits (numbers only).')
        else:
            try:
                cur.execute("INSERT INTO HEAD (Name,Email,Status,Password) VALUES (%s,%s,%s,%s)",
                            (f['name'],email,f['status'],f['password']))
                new_id = cur.lastrowid
                if contact:
                    cur.execute("INSERT INTO CONTACTS (Head_ID,Contact_no) VALUES (%s,%s)",(new_id,contact))
                db.commit(); msg = ('success',f'Head added with ID {new_id}.')
            except Exception as e:
                msg = ('error',f'Error: {e}')
    cur.close(); db.close()
    return render_template('add_head.html', msg=msg)

@app.route('/add/contacts', methods=['GET','POST'])
@login_required
@role_required('Admin')
def add_contacts():
    db = get_db(); cur = db.cursor(); msg = None
    selected_head = request.form.get('head_id','') or request.args.get('head_id','')
    existing_contacts = []
    if request.method == 'POST':
        contact = request.form.get('contact_no','').strip()
        head_id = request.form.get('head_id','')
        if not valid_phone(contact):
            msg = ('error','Contact number must be exactly 10 digits (numbers only).')
        else:
            try:
                cur.execute("INSERT INTO CONTACTS (Head_ID,Contact_no) VALUES (%s,%s)",(head_id,contact))
                db.commit(); msg = ('success','Contact added successfully.')
                selected_head = head_id
            except Exception as e:
                msg = ('error',f'Error: {e}')
    if selected_head:
        cur.execute("""SELECT Contact_ID,Contact_no FROM CONTACTS
                       WHERE Head_ID=%s ORDER BY Contact_ID""", (selected_head,))
        existing_contacts = cur.fetchall()
    cur.execute("SELECT Head_ID,Name,Status FROM HEAD ORDER BY Status,Name")
    heads = cur.fetchall()
    cur.close(); db.close()
    return render_template('add_contacts.html', heads=heads, msg=msg,
                           selected_head=selected_head, existing_contacts=existing_contacts)

@app.route('/add/material', methods=['GET','POST'])
@login_required
@role_required('Admin')
def add_material():
    db = get_db(); cur = db.cursor(); msg = None
    if request.method == 'POST':
        f = request.form
        try:
            cur.execute("INSERT INTO MATERIAL (Material_Name,Sustainability_Quality) VALUES (%s,%s)",
                        (f['material_name'],f['sustainability_quality']))
            db.commit(); msg = ('success','Material added successfully.')
        except Exception as e:
            msg = ('error',f'Error: {e}')
    cur.close(); db.close()
    return render_template('add_material.html', msg=msg)

# ══════════════════════════════════════════════════════════════════
# REPORT – Branch read-only
# ══════════════════════════════════════════════════════════════════
@app.route('/view_report')
@login_required
@role_required('Branch')
def view_report():
    db = get_db(); cur = db.cursor()
    cur.execute("""SELECT Report_ID,Branch_ID,Items_Resold,Items_Recycled,
                          Items_Donated,Items_Upcycled,Items_Rebranded,
                          Items_Disposed,Estimated_Waste_Reduced
                   FROM REPORT WHERE Branch_ID=%s""", (session.get('branch_id'),))
    report = cur.fetchone()
    cur.close(); db.close()
    return render_template('report.html', report=report, msg=None)

# ══════════════════════════════════════════════════════════════════
# SA BRANCH REPORT
# ══════════════════════════════════════════════════════════════════
@app.route('/sa_branch_report')
@login_required
@role_required('Stock_Allocation')
def sa_branch_report():
    db = get_db(); cur = db.cursor()
    # LEFT JOIN so allocation data for deleted branches still visible.
    # r[9] = Branch_ID used by template for PDF download link.
    cur.execute("""
        SELECT COALESCE(b.City, db2.City, 'Deleted Branch') AS City,
               SUM(CASE WHEN sa.Allocation_Type='Recycle'  THEN sa.Quantity ELSE 0 END),
               SUM(CASE WHEN sa.Allocation_Type='Donate'   THEN sa.Quantity ELSE 0 END),
               SUM(CASE WHEN sa.Allocation_Type='Resell'   THEN sa.Quantity ELSE 0 END),
               SUM(CASE WHEN sa.Allocation_Type='Upcycle'  THEN sa.Quantity ELSE 0 END),
               SUM(CASE WHEN sa.Allocation_Type='Rebrand'  THEN sa.Quantity ELSE 0 END),
               SUM(CASE WHEN sa.Allocation_Type='Disposal' THEN sa.Quantity ELSE 0 END),
               SUM(sa.Quantity),
               r.Estimated_Waste_Reduced,
               d.Branch_ID
        FROM STOCK_ALLOCATION sa
        JOIN  DEADSTOCK d      ON sa.Deadstock_ID = d.Deadstock_ID
        LEFT JOIN BRANCH b     ON d.Branch_ID = b.Branch_ID
        LEFT JOIN DELETED_BRANCH db2 ON d.Branch_ID = db2.Branch_ID
        LEFT JOIN REPORT r     ON d.Branch_ID = r.Branch_ID
        GROUP BY d.Branch_ID, b.City, db2.City, r.Estimated_Waste_Reduced
        ORDER BY City""")
    rows = cur.fetchall()
    cur.execute("SELECT Allocation_Type,SUM(Quantity) FROM STOCK_ALLOCATION GROUP BY Allocation_Type")
    alloc_totals = cur.fetchall()
    cur.close(); db.close()
    return render_template('sa_branch_report.html', rows=rows,
                           alloc_totals=alloc_totals, alloc_colors=ALLOC_COLOR_MAP)

# ══════════════════════════════════════════════════════════════════
# SEND ROUTES
# ══════════════════════════════════════════════════════════════════
@app.route('/send_to_warehouse/<int:deadstock_id>', methods=['POST'])
@login_required
@role_required('Branch')
def send_to_warehouse(deadstock_id):
    branch_id = session.get('branch_id')
    db = get_db(); cur = db.cursor()
    try:
        cur.execute("""SELECT Deadstock_ID FROM DEADSTOCK
                       WHERE Deadstock_ID=%s AND Branch_ID=%s AND Sent_To_Warehouse=0""",
                    (deadstock_id,branch_id))
        if cur.fetchone():
            cur.execute("UPDATE DEADSTOCK SET Sent_To_Warehouse=1 WHERE Deadstock_ID=%s",(deadstock_id,))
            db.commit()
    except Exception:
        pass
    finally:
        cur.close(); db.close()
    return redirect(url_for('show_table', table_name='DEADSTOCK'))

@app.route('/send_to_sa/<int:deadstock_id>', methods=['POST'])
@login_required
@role_required('Warehouse')
def send_to_sa(deadstock_id):
    wh_id = session.get('warehouse_id')
    db = get_db(); cur = db.cursor()
    try:
        # LEFT JOIN handles orphaned deadstock from deleted branches.
        # Also check DELETED_BRANCH so warehouse head can still send it to SA.
        cur.execute("""SELECT d.Deadstock_ID FROM DEADSTOCK d
                       LEFT JOIN BRANCH b ON d.Branch_ID=b.Branch_ID
                       LEFT JOIN DELETED_BRANCH db2 ON d.Branch_ID=db2.Branch_ID
                       WHERE d.Deadstock_ID=%s
                         AND (b.Warehouse_ID=%s OR db2.Warehouse_ID=%s)
                         AND d.Sent_To_Warehouse=1 AND d.Sent_To_SA=0""",
                    (deadstock_id, wh_id, wh_id))
        if cur.fetchone():
            cur.execute("UPDATE DEADSTOCK SET Sent_To_SA=1 WHERE Deadstock_ID=%s",(deadstock_id,))
            db.commit()
    except Exception:
        pass
    finally:
        cur.close(); db.close()
    return redirect(url_for('show_table', table_name='DEADSTOCK'))

# ══════════════════════════════════════════════════════════════════
# ALLOCATE
# ══════════════════════════════════════════════════════════════════
@app.route('/allocate/<int:deadstock_id>', methods=['POST'])
@login_required
@role_required('Stock_Allocation')
def allocate(deadstock_id):
    alloc_type  = request.form.get('alloc_type','')
    valid_types = ['Recycle','Donate','Resell','Upcycle','Rebrand','Disposal']
    if alloc_type not in valid_types:
        return redirect(url_for('show_table', table_name='DEADSTOCK'))
    head_id = session.get('head_id')
    db = get_db(); cur = db.cursor()
    try:
        cur.execute("""SELECT Quantity,Branch_ID FROM DEADSTOCK
                       WHERE Deadstock_ID=%s AND Sent_To_SA=1 AND Allocated_Type IS NULL""",
                    (deadstock_id,))
        row = cur.fetchone()
        if row:
            qty = row[0]; branch_id = row[1]
            cur.execute("UPDATE DEADSTOCK SET Allocated_Type=%s WHERE Deadstock_ID=%s",
                        (alloc_type,deadstock_id))
            cur.execute("""INSERT INTO STOCK_ALLOCATION (Deadstock_ID,Head_ID,Allocation_Type,Quantity)
                           VALUES (%s,%s,%s,%s)""",
                        (deadstock_id,head_id,alloc_type,qty))
            col_map = {
                'Resell':   ('Items_Resold',    0.6),
                'Recycle':  ('Items_Recycled',  0.8),
                'Donate':   ('Items_Donated',   0.5),
                'Upcycle':  ('Items_Upcycled',  0.9),
                'Rebrand':  ('Items_Rebranded', 0.7),
                'Disposal': ('Items_Disposed',  0.0),
            }
            col, factor = col_map.get(alloc_type, ('Items_Disposed', 0.0))
            cur.execute("""SELECT Report_ID,Estimated_Waste_Reduced FROM REPORT
                           WHERE Branch_ID=%s""", (branch_id,))
            rep = cur.fetchone()
            if rep:
                new_waste = float(rep[1] or 0) + (qty * factor)
                cur.execute(f"""UPDATE REPORT SET {col}={col}+%s,
                                                   Estimated_Waste_Reduced=%s
                               WHERE Report_ID=%s""",
                            (qty, round(new_waste,2), rep[0]))
            db.commit()
    except Exception:
        pass
    finally:
        cur.close(); db.close()
    return redirect(url_for('show_table', table_name='DEADSTOCK'))

# ══════════════════════════════════════════════════════════════════
# UPDATE HEAD PASSWORD
# ══════════════════════════════════════════════════════════════════
@app.route('/update_head/<int:head_id>', methods=['GET','POST'])
@login_required
@role_required('Admin')
def update_head(head_id):
    db = get_db(); cur = db.cursor(); msg = None
    if request.method == 'POST':
        pw  = request.form.get('password','')
        cpw = request.form.get('confirm_password','')
        if not pw:
            msg = ('error','Password cannot be empty.')
        elif pw != cpw:
            msg = ('error','Passwords do not match.')
        elif len(pw) < 4:
            msg = ('error','Password must be at least 4 characters.')
        else:
            try:
                cur.execute("UPDATE HEAD SET Password=%s WHERE Head_ID=%s",(pw,head_id))
                db.commit(); msg = ('success','Password updated successfully.')
            except Exception as e:
                msg = ('error',f'Error: {e}')
    cur.execute("SELECT Head_ID,Name,Email,Status FROM HEAD WHERE Head_ID=%s",(head_id,))
    head = cur.fetchone()
    cur.close(); db.close()
    return render_template('update_head.html', head=head, msg=msg)

# ══════════════════════════════════════════════════════════════════
# DELETE BRANCH
# ══════════════════════════════════════════════════════════════════
@app.route('/delete/branch/<int:branch_id>', methods=['POST'])
@login_required
@role_required('Admin')
def delete_branch(branch_id):
    """
    Branch deletion logic:
      STEP 1 – Mark all unsent deadstock (Sent_To_Warehouse=0) as sent-to-warehouse
               so the warehouse head can still process it. Nothing is deleted.
      STEP 2 – Deadstock already at warehouse / SA / allocated → untouched.
      STEP 3 – Archive branch to DELETED_BRANCH.
      STEP 4 – Remove the FK reference: set Branch_ID=NULL in DEADSTOCK temporarily
               only to satisfy the DB FK constraint; the DELETED_BRANCH archive
               preserves all branch info and the original Branch_ID is kept in
               DELETED_BRANCH for reporting lookups.
               NOTE: If you removed the DEADSTOCK Branch_ID FK (ON DELETE SET NULL
               or dropped it entirely) in your ALTER script, STEP 4 is not needed.
      STEP 5 – Delete the BRANCH row.

    ⚠  PREREQUISITE: The FK on DEADSTOCK(Branch_ID) must allow branch deletion.
       Run this in MySQL before using this route:
         ALTER TABLE DEADSTOCK DROP FOREIGN KEY <fk_name>;
         ALTER TABLE DEADSTOCK ADD CONSTRAINT fk_deadstock_branch
           FOREIGN KEY (Branch_ID) REFERENCES BRANCH(Branch_ID) ON DELETE SET NULL;
       This lets Branch_ID in DEADSTOCK become NULL when a branch is deleted,
       while DELETED_BRANCH preserves all branch history for reporting.
    """
    db = get_db(); cur = db.cursor()
    try:
        cur.execute("SELECT * FROM BRANCH WHERE Branch_ID=%s", (branch_id,))
        row = cur.fetchone()
        if not row:
            # Already deleted or never existed — just redirect cleanly
            return redirect(url_for('show_table', table_name='BRANCH'))

        # STEP 1: Mark all unsent deadstock as sent-to-warehouse
        cur.execute("""UPDATE DEADSTOCK
                       SET Sent_To_Warehouse = 1
                       WHERE Branch_ID = %s AND Sent_To_Warehouse = 0""",
                    (branch_id,))

        # STEP 3: Archive branch record to DELETED_BRANCH
        # (ignore duplicate-key error in case already archived)
        cur.execute("""INSERT IGNORE INTO DELETED_BRANCH
                           (Branch_ID, Warehouse_ID, Head_ID, City,
                            Last_Audit, Sustainable_Rating)
                       VALUES (%s, %s, %s, %s, %s, %s)""", row)

        # STEP 5: Delete the BRANCH row.
        # If your FK is ON DELETE SET NULL, DEADSTOCK.Branch_ID will become NULL
        # automatically.  The DELETED_BRANCH table preserves history for reports.
        cur.execute("DELETE FROM BRANCH WHERE Branch_ID=%s", (branch_id,))
        db.commit()

    except Exception as e:
        db.rollback()
        print(f'[DELETE BRANCH ERROR] Branch #{branch_id}: {e}')
        # Surface the error briefly in the session so the template can show it
        session['branch_delete_error'] = (
            f'Could not delete Branch #{branch_id}. '
            f'Ensure the DEADSTOCK FK is set to ON DELETE SET NULL '
            f'(see ALTER script). DB error: {e}'
        )
    finally:
        cur.close(); db.close()

    return redirect(url_for('show_table', table_name='BRANCH'))

# ══════════════════════════════════════════════════════════════════
# DELETE WAREHOUSE
# ══════════════════════════════════════════════════════════════════
@app.route('/delete/warehouse/<int:wh_id>', methods=['POST'])
@login_required
@role_required('Admin')
def delete_warehouse(wh_id):
    return redirect(url_for('reassign_warehouse', wh_id=wh_id))

@app.route('/delete/warehouse/reassign/<int:wh_id>', methods=['GET','POST'])
@login_required
@role_required('Admin')
def reassign_warehouse(wh_id):
    db = get_db(); cur = db.cursor(); msg = None
    if request.method == 'POST':
        try:
            cur.execute("SELECT Branch_ID FROM BRANCH WHERE Warehouse_ID=%s",(wh_id,))
            branch_ids = [r[0] for r in cur.fetchall()]
            for bid in branch_ids:
                new_wh = request.form.get(f'new_warehouse_{bid}','')
                if new_wh:
                    cur.execute("UPDATE BRANCH SET Warehouse_ID=%s WHERE Branch_ID=%s",(new_wh,bid))
            if branch_ids:
                fmt = ','.join(['%s'] * len(branch_ids))
                cur.execute(f"""UPDATE DEADSTOCK SET Sent_To_SA=1
                                WHERE Branch_ID IN ({fmt})
                                  AND Sent_To_Warehouse=1
                                  AND Sent_To_SA=0""", branch_ids)
            cur.execute("SELECT * FROM WAREHOUSE WHERE Warehouse_ID=%s",(wh_id,))
            row = cur.fetchone()
            if row:
                cur.execute("""INSERT INTO DELETED_WAREHOUSE
                                   (Warehouse_ID,Head_ID,City,Last_Audit,Capacity)
                               VALUES (%s,%s,%s,%s,%s)""", row)
                cur.execute("DELETE FROM WAREHOUSE WHERE Warehouse_ID=%s",(wh_id,))
            db.commit()
            return redirect(url_for('show_table', table_name='WAREHOUSE'))
        except Exception as e:
            db.rollback()
            msg = ('error', f'Error: {e}')

    cur.execute("SELECT * FROM WAREHOUSE WHERE Warehouse_ID=%s",(wh_id,))
    warehouse = cur.fetchone()
    cur.execute("SELECT Branch_ID,City,Head_ID FROM BRANCH WHERE Warehouse_ID=%s",(wh_id,))
    branches = cur.fetchall()
    cur.execute("SELECT Warehouse_ID,City FROM WAREHOUSE WHERE Warehouse_ID!=%s ORDER BY City",(wh_id,))
    other_warehouses = cur.fetchall()
    cur.close(); db.close()
    return render_template('reassign_warehouse.html',
                           warehouse=warehouse, branches=branches,
                           other_warehouses=other_warehouses, msg=msg)

# ══════════════════════════════════════════════════════════════════
# DELETED RECORDS
# ══════════════════════════════════════════════════════════════════
@app.route('/deleted/<entity>')
@login_required
@role_required('Admin')
def deleted(entity):
    db = get_db(); cur = db.cursor()
    rows = []; headers = []
    if entity == 'branch':
        headers=['Branch ID','Warehouse ID','Head ID','City','Last Audit','Rating','Deleted At']
        cur.execute("SELECT * FROM DELETED_BRANCH ORDER BY Deleted_At DESC")
        rows = cur.fetchall()
    elif entity == 'warehouse':
        headers=['Warehouse ID','Head ID','City','Last Audit','Capacity','Deleted At']
        cur.execute("SELECT * FROM DELETED_WAREHOUSE ORDER BY Deleted_At DESC")
        rows = cur.fetchall()
    cur.close(); db.close()
    return render_template('show_tables.html',
                           table_name=f'DELETED_{entity.upper()}',
                           headers=headers, rows=rows,
                           f_branch='',f_category='',f_size='',f_alloc='',
                           f_city='',f_role='',f_sq='',f_sent_wh='',f_sent_sa='',
                           all_branches=[],all_cities_br=[],all_cities_wh=[],
                           all_roles=[],all_sizes=[],all_alloc=[],all_sq=[])

# ══════════════════════════════════════════════════════════════════
# CHANGE SET 4 – DOWNLOAD BRANCH REPORT AS PDF
# ══════════════════════════════════════════════════════════════════
@app.route('/download_report/<int:branch_id>')
@login_required
def download_report(branch_id):
    role = session.get('role')
    # Access control
    if role == 'Branch' and session.get('branch_id') != branch_id:
        return render_template('denied.html')
    if role not in ['Admin','Branch','Stock_Allocation']:
        return render_template('denied.html')

    db = get_db(); cur = db.cursor()

    # Branch + warehouse + head info — LEFT JOIN handles deleted branches
    cur.execute("""
        SELECT b.Branch_ID,
               COALESCE(b.City, db2.City, 'Deleted Branch') AS City,
               COALESCE(b.Sustainable_Rating, db2.Sustainable_Rating) AS Rating,
               COALESCE(b.Last_Audit, db2.Last_Audit) AS LastAudit,
               w.City AS WhCity,
               h.Name AS HeadName,
               COALESCE(b.Warehouse_ID, db2.Warehouse_ID) AS WarehouseID
        FROM REPORT r
        LEFT JOIN BRANCH b           ON r.Branch_ID = b.Branch_ID
        LEFT JOIN DELETED_BRANCH db2 ON r.Branch_ID = db2.Branch_ID
        LEFT JOIN WAREHOUSE w        ON COALESCE(b.Warehouse_ID, db2.Warehouse_ID) = w.Warehouse_ID
        LEFT JOIN HEAD h             ON COALESCE(b.Head_ID, db2.Head_ID) = h.Head_ID
        WHERE r.Branch_ID=%s LIMIT 1
    """, (branch_id,))
    branch_info = cur.fetchone()
    if not branch_info:
        # Try fetching directly from DELETED_BRANCH as fallback
        cur.execute("""
            SELECT db2.Branch_ID, db2.City, db2.Sustainable_Rating, db2.Last_Audit,
                   w.City, h.Name, db2.Warehouse_ID
            FROM DELETED_BRANCH db2
            LEFT JOIN WAREHOUSE w ON db2.Warehouse_ID=w.Warehouse_ID
            LEFT JOIN HEAD h      ON db2.Head_ID=h.Head_ID
            WHERE db2.Branch_ID=%s LIMIT 1
        """, (branch_id,))
        branch_info = cur.fetchone()
    if not branch_info:
        cur.close(); db.close()
        return "Branch not found.", 404

    # Report data
    cur.execute("""SELECT Items_Resold,Items_Recycled,Items_Donated,
                          Items_Upcycled,Items_Rebranded,Items_Disposed,
                          Estimated_Waste_Reduced
                   FROM REPORT WHERE Branch_ID=%s""", (branch_id,))
    report = cur.fetchone() or (0,0,0,0,0,0,0.0)

    # Deadstock items for this branch
    cur.execute("""SELECT d.Category,d.Size,m.Material_Name,d.Quantity,
                          d.Sent_To_Warehouse,d.Sent_To_SA,d.Allocated_Type
                   FROM DEADSTOCK d
                   LEFT JOIN MATERIAL m ON d.Material_ID=m.Material_ID
                   WHERE d.Branch_ID=%s
                   ORDER BY d.Deadstock_ID""", (branch_id,))
    deadstock_rows = cur.fetchall()
    cur.close(); db.close()

    # Build PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=20*mm, rightMargin=20*mm,
                            topMargin=20*mm, bottomMargin=20*mm)

    GREEN  = colors.HexColor('#2d6a4f')
    LGREEN = colors.HexColor('#e8f5e9')
    DGRAY  = colors.HexColor('#333333')
    LGRAY  = colors.HexColor('#f4f6f9')

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('title', fontSize=18, textColor=GREEN,
                                  fontName='Helvetica-Bold', alignment=TA_CENTER,
                                  spaceAfter=4)
    sub_style   = ParagraphStyle('sub',   fontSize=11, textColor=DGRAY,
                                  fontName='Helvetica', alignment=TA_CENTER,
                                  spaceAfter=2)
    label_style = ParagraphStyle('label', fontSize=10, textColor=GREEN,
                                  fontName='Helvetica-Bold')
    body_style  = ParagraphStyle('body',  fontSize=10, textColor=DGRAY,
                                  fontName='Helvetica', leading=16)
    sec_style   = ParagraphStyle('sec',   fontSize=12, textColor=GREEN,
                                  fontName='Helvetica-Bold', spaceBefore=14, spaceAfter=6)
    footer_style= ParagraphStyle('footer',fontSize=9, textColor=colors.grey,
                                  fontName='Helvetica', alignment=TA_CENTER)

    story = []

    # ── Header ──
    story.append(Paragraph('♻ Deadstock Inventory Management System', title_style))
    story.append(Paragraph('Branch Report', sub_style))
    story.append(Spacer(1, 6*mm))
    story.append(HRFlowable(width='100%', thickness=2, color=GREEN))
    story.append(Spacer(1, 4*mm))

    # Branch info table
    b_city      = branch_info[1]
    b_rating    = branch_info[2] or 'N/A'
    b_audit     = str(branch_info[3]) if branch_info[3] else 'N/A'
    wh_city     = branch_info[4] or 'N/A'
    head_name   = branch_info[5] or 'N/A'
    date_gen    = datetime.now().strftime('%d %B %Y, %I:%M %p')

    info_data = [
        ['Branch ID', str(branch_id),       'Branch City',     b_city],
        ['Branch Head', head_name,           'Warehouse City',  wh_city],
        ['Last Audit', b_audit,              'Generated On',    date_gen],
    ]
    info_table = Table(info_data, colWidths=[40*mm, 55*mm, 45*mm, 55*mm])
    info_table.setStyle(TableStyle([
        ('FONTNAME',  (0,0),(-1,-1), 'Helvetica'),
        ('FONTNAME',  (0,0),(0,-1),  'Helvetica-Bold'),
        ('FONTNAME',  (2,0),(2,-1),  'Helvetica-Bold'),
        ('FONTSIZE',  (0,0),(-1,-1), 10),
        ('TEXTCOLOR', (0,0),(0,-1),  GREEN),
        ('TEXTCOLOR', (2,0),(2,-1),  GREEN),
        ('BACKGROUND',(0,0),(-1,-1), LGRAY),
        ('ROWBACKGROUNDS',(0,0),(-1,-1),[LGRAY, colors.white]),
        ('GRID',      (0,0),(-1,-1), 0.5, colors.HexColor('#dddddd')),
        ('PADDING',   (0,0),(-1,-1), 6),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 5*mm))

    # ── Sustainability Rating ──
    story.append(Paragraph('Sustainability Rating', sec_style))
    rating_val = float(b_rating) if b_rating != 'N/A' else 0.0
    filled = int(round(rating_val * 2)) # out of 10 half-stars
    stars = '★' * int(rating_val) + ('½' if (rating_val % 1 >= 0.5) else '') + '☆' * (5 - int(rating_val) - (1 if rating_val%1>=0.5 else 0))
    rating_data = [['Sustainable Rating', f'{b_rating} / 5.0', stars]]
    rating_table = Table(rating_data, colWidths=[70*mm, 40*mm, 85*mm])
    rating_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,-1), LGREEN),
        ('FONTNAME',   (0,0),(0,0),   'Helvetica-Bold'),
        ('FONTNAME',   (1,0),(1,0),   'Helvetica-Bold'),
        ('FONTSIZE',   (0,0),(-1,-1), 11),
        ('TEXTCOLOR',  (1,0),(1,0),   GREEN),
        ('TEXTCOLOR',  (2,0),(2,0),   colors.HexColor('#e65100')),
        ('GRID',       (0,0),(-1,-1), 0.5, colors.HexColor('#a5d6a7')),
        ('PADDING',    (0,0),(-1,-1), 8),
    ]))
    story.append(rating_table)
    story.append(Spacer(1, 5*mm))

    # ── Allocation Summary ──
    story.append(Paragraph('Allocation Summary', sec_style))
    alloc_headers = [['Allocation Type', 'Items Count']]
    alloc_rows = [
        ['Resold',    str(report[0])],
        ['Recycled',  str(report[1])],
        ['Donated',   str(report[2])],
        ['Upcycled',  str(report[3])],
        ['Rebranded', str(report[4])],
        ['Disposed',  str(report[5])],
    ]
    total_alloc = sum(int(r[1]) for r in alloc_rows)
    alloc_rows.append(['TOTAL', str(total_alloc)])
    alloc_data = alloc_headers + alloc_rows
    alloc_table = Table(alloc_data, colWidths=[100*mm, 95*mm])
    alloc_style = TableStyle([
        ('BACKGROUND', (0,0),(-1,0),   GREEN),
        ('TEXTCOLOR',  (0,0),(-1,0),   colors.white),
        ('FONTNAME',   (0,0),(-1,0),   'Helvetica-Bold'),
        ('FONTNAME',   (0,-1),(-1,-1), 'Helvetica-Bold'),
        ('BACKGROUND', (0,-1),(-1,-1), LGREEN),
        ('TEXTCOLOR',  (0,-1),(-1,-1), GREEN),
        ('ROWBACKGROUNDS',(0,1),(-1,-2),[colors.white, LGRAY]),
        ('GRID',       (0,0),(-1,-1),  0.5, colors.HexColor('#cccccc')),
        ('FONTSIZE',   (0,0),(-1,-1),  10),
        ('PADDING',    (0,0),(-1,-1),  7),
        ('ALIGN',      (1,0),(-1,-1),  'CENTER'),
    ])
    alloc_table.setStyle(alloc_style)
    story.append(alloc_table)
    story.append(Spacer(1, 4*mm))

    # Waste reduced
    waste_data = [['Estimated Waste Reduced', f'{float(report[6]):.2f} kg']]
    waste_table = Table(waste_data, colWidths=[100*mm, 95*mm])
    waste_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,-1), colors.HexColor('#fff3e0')),
        ('FONTNAME',   (0,0),(0,0),   'Helvetica-Bold'),
        ('FONTNAME',   (1,0),(1,0),   'Helvetica-Bold'),
        ('TEXTCOLOR',  (1,0),(1,0),   colors.HexColor('#e65100')),
        ('FONTSIZE',   (0,0),(-1,-1), 10),
        ('GRID',       (0,0),(-1,-1), 0.5, colors.HexColor('#ffcc80')),
        ('PADDING',    (0,0),(-1,-1), 7),
        ('ALIGN',      (1,0),(1,0),   'CENTER'),
    ]))
    story.append(waste_table)
    story.append(Spacer(1, 5*mm))

    # ── Deadstock Inventory ──
    story.append(Paragraph('Deadstock Inventory', sec_style))
    ds_headers = [['Category','Size','Material','Qty','Status']]
    ds_rows = []
    for d in deadstock_rows:
        if d[6]:
            status = f'Allocated – {d[6]}'
        elif d[5]:
            status = 'Sent to SA'
        elif d[4]:
            status = 'At Warehouse'
        else:
            status = 'At Branch'
        ds_rows.append([d[0], d[1], d[2] or '—', str(d[3]), status])
    if not ds_rows:
        ds_rows = [['No deadstock records found','','','','']]
    ds_data = ds_headers + ds_rows
    ds_table = Table(ds_data, colWidths=[45*mm, 22*mm, 40*mm, 18*mm, 70*mm])
    ds_style = TableStyle([
        ('BACKGROUND', (0,0),(-1,0),  GREEN),
        ('TEXTCOLOR',  (0,0),(-1,0),  colors.white),
        ('FONTNAME',   (0,0),(-1,0),  'Helvetica-Bold'),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white, LGRAY]),
        ('GRID',       (0,0),(-1,-1), 0.5, colors.HexColor('#cccccc')),
        ('FONTSIZE',   (0,0),(-1,-1), 9),
        ('PADDING',    (0,0),(-1,-1), 6),
        ('ALIGN',      (3,0),(3,-1),  'CENTER'),
    ])
    ds_table.setStyle(ds_style)
    story.append(ds_table)
    story.append(Spacer(1, 8*mm))

    # ── Footer ──
    story.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#cccccc')))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph(f'Generated on {date_gen} by Deadstock IMS  |  Branch #{branch_id} – {b_city}',
                            footer_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    date_str = datetime.now().strftime('%Y%m%d')
    filename = f'branch_report_{branch_id}_{date_str}.pdf'
    response = make_response(pdf_bytes)
    response.headers['Content-Type']        = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

if __name__ == '__main__':
    app.run(debug=True)