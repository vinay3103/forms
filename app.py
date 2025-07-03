import streamlit as st
import streamlit.components.v1 as components
import libsql_experimental as libsql # type: ignore
import bcrypt
import pandas as pd
from datetime import datetime
import base64
from PIL import Image
import io
import uuid
import os

# Database setup
db_url = st.secrets["turso"]["database_url"]
auth_token = st.secrets["turso"]["auth_token"]
db = libsql.connect(db_url, auth_token=auth_token, sync_url=db_url)
cursor = db.cursor()

def log_error(message):
    timestamp = datetime.now().isoformat()
    try:
        cursor.execute('INSERT INTO error_logs (message, timestamp) VALUES (?, ?)', (message, timestamp))
        db.sync()
    except Exception as e:
        # Fallback to Streamlit error if database logging fails
        st.error(f"Failed to log error: {str(e)}")

# Initialize database
def init_db():
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        is_admin BOOLEAN DEFAULT 0
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS forms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        formNumber INTEGER,
        date TEXT,
        time TEXT,
        customerName TEXT,
        itemName TEXT,
        mobileNumber TEXT,
        grossWeight REAL,
        netWeight REAL,
        gold REAL,
        karat REAL,
        photo TEXT,
        userId INTEGER
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        itemName TEXT,
        grossWeight REAL,
        netWeight REAL,
        gold REAL,
        karat REAL,
        userId INTEGER
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT,
        userId INTEGER,
        username TEXT,
        timestamp TEXT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS error_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message TEXT,
        timestamp TEXT
    )''')
    # Create default admin user if not exists
    cursor.execute('SELECT * FROM users WHERE username = ?', ('admin',))
    if not cursor.fetchone():
        hashed_password = bcrypt.hashpw('admin123'.encode('utf-8'), bcrypt.gensalt())
        cursor.execute('INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)', ('admin', hashed_password, 1))
    db.sync()

init_db()

# Session state management
def initialize_session_state():
    if 'session_id' not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
    if 'is_admin' not in st.session_state:
        st.session_state.is_admin = False
    if 'forms' not in st.session_state:
        st.session_state.forms = []
    if 'current_form_id' not in st.session_state:
        st.session_state.current_form_id = None
    if 'current_form_index' not in st.session_state:
        st.session_state.current_form_index = -1
    if 'is_editing' not in st.session_state:
        st.session_state.is_editing = False
    if 'templates' not in st.session_state:
        st.session_state.templates = []
    if 'page' not in st.session_state:
        st.session_state.page = "login"
    if 'form_data' not in st.session_state:
        st.session_state.form_data = None
    if 'form_select' not in st.session_state:
        st.session_state.form_select = "New Form"
    if 'last_template_select' not in st.session_state:
        st.session_state.last_template_select = "None"
    if 'search_active' not in st.session_state:
        st.session_state.search_active = False

initialize_session_state()

# Custom CSS for form styling and print
st.markdown("""
    <style>
        .form-container { max-width: 800px; margin: auto; }
        .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        label { font-weight: bold; font-family: Arial, sans-serif; }
        .stTextInput > div > input { font-family: Arial, sans-serif; }
        .stNumberInput > div > input { font-family: Arial, sans-serif; }
        .logo { text-align: center; margin-bottom: 20px; }
        h1 { text-align: center; font-family: Arial, sans-serif; font-size: 24px; }
        .stButton > button { font-family: Arial, sans-serif; }
        @media print {
            .no-print { display: none; }
            .form-container { margin: 0; width: 100%; }
            img { max-width: 100%; max-height: 100%; }
            body { margin: 0; }
            .print-form { page-break-after: always; }
        }
    </style>
""", unsafe_allow_html=True)

# Login page
def login_page():
    st.title("Gold Testing Form - Login")
    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")
    if st.button("Login"):
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        if user and bcrypt.checkpw(password.encode('utf-8'), user[2]):
            st.session_state.user_id = user[0]
            st.session_state.is_admin = bool(user[3])
            cursor.execute('INSERT INTO audit_log (action, userId, username, timestamp) VALUES (?, ?, ?, ?)',
                           ('login', user[0], username, datetime.now().isoformat()))
            db.sync()
            st.session_state.form_data = new_form()
            st.session_state.form_select = "New Form"
            st.session_state.page = "main" if not st.session_state.is_admin else "admin"
            st.success("Login successful!")
            st.rerun()
        else:
            st.error("Invalid credentials")

# Logout
def logout():
    st.session_state.user_id = None
    st.session_state.is_admin = False
    st.session_state.forms = []
    st.session_state.current_form_id = None
    st.session_state.current_form_index = -1
    st.session_state.is_editing = False
    st.session_state.templates = []
    st.session_state.page = "login"
    st.session_state.form_data = None
    st.session_state.form_select = "New Form"
    st.session_state.last_template_select = "None"
    st.session_state.search_active = False
    st.rerun()

# Load forms for a user
def load_forms(user_id):
    try:
        cursor.execute('SELECT * FROM forms WHERE userId = ? ORDER BY formNumber DESC', (user_id,))
        forms = cursor.fetchall()
        st.session_state.forms = [{
            'id': row[0], 'formNumber': row[1], 'date': row[2], 'time': row[3],
            'customerName': row[4], 'itemName': row[5], 'mobileNumber': row[6],
            'grossWeight': row[7], 'netWeight': row[8], 'gold': row[9], 'karat': row[10], 'photo': row[11]
        } for row in forms]
        return len(st.session_state.forms)
    except Exception as e:
        log_error(f"Load forms error: {str(e)}")
        st.error("Failed to load forms")
        return 0

# Load templates for a user
def load_templates(user_id):
    try:
        cursor.execute('SELECT * FROM templates WHERE userId = ?', (user_id,))
        templates = cursor.fetchall()
        st.session_state.templates = [{
            'id': row[0], 'itemName': row[1], 'grossWeight': row[2], 'netWeight': row[3],
            'gold': row[4], 'karat': row[5]
        } for row in templates]
        return len(st.session_state.templates)
    except Exception as e:
        log_error(f"Load templates error: {str(e)}")
        st.error("Failed to load templates")
        return 0

# Validate form data
def validate_form(form_data):
    valid = True
    if form_data['mobileNumber'] and not (form_data['mobileNumber'].isdigit() and len(form_data['mobileNumber']) == 10):
        st.error("Please enter a valid 10-digit mobile number")
        valid = False
    
    if form_data['grossWeight'] is not None and float(form_data['grossWeight']) < 0:
        st.error("Gross Weight must be non-negative")
        valid = False
    if form_data['gold'] is not None and (float(form_data['gold']) < 0 or float(form_data['gold']) > 100):
        st.error("Gold percentage must be between 0 and 100")
        valid = False
    
    if not form_data['customerName'] or not form_data['itemName'] or form_data['grossWeight'] is None or form_data['gold'] is None:
        st.error("Customer Name, Item Name, Gross Weight, and Gold (%) are required fields for saving/printing.")
        valid = False

    return valid

# Save form
def save_form(form_data):
    try:
        gross_weight_val = float(form_data['grossWeight']) if form_data['grossWeight'] is not None else None
        gold_val = float(form_data['gold']) if form_data['grossWeight'] is not None else None

        net_weight = gross_weight_val
        karat = round((gold_val / 100) * 24, 2) if gold_val is not None else None

        if st.session_state.current_form_id:
            cursor.execute('''UPDATE forms SET formNumber = ?, date = ?, time = ?, customerName = ?, itemName = ?, mobileNumber = ?, 
                            grossWeight = ?, netWeight = ?, gold = ?, karat = ?, photo = ? WHERE id = ? AND userId = ?''',
                          (form_data['formNumber'], form_data['date'], form_data['time'], form_data['customerName'], form_data['itemName'], 
                           form_data['mobileNumber'], gross_weight_val, net_weight, gold_val, karat, form_data['photo'], 
                           st.session_state.current_form_id, st.session_state.user_id))
            cursor.execute('INSERT INTO audit_log (action, userId, username, timestamp) VALUES (?, ?, ?, ?)',
                          ('update_form', st.session_state.user_id, f"Form {form_data['formNumber']}", datetime.now().isoformat()))
        else:
            cursor.execute('''INSERT INTO forms (formNumber, date, time, customerName, itemName, mobileNumber, grossWeight, netWeight, 
                            gold, karat, photo, userId) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                          (form_data['formNumber'], form_data['date'], form_data['time'], form_data['customerName'], form_data['itemName'], 
                           form_data['mobileNumber'], gross_weight_val, net_weight, gold_val, karat, form_data['photo'], 
                           st.session_state.user_id))
            st.session_state.current_form_id = cursor.lastrowid
            cursor.execute('INSERT INTO audit_log (action, userId, username, timestamp) VALUES (?, ?, ?, ?)',
                          ('create_form', st.session_state.user_id, f"Form {form_data['formNumber']}", datetime.now().isoformat()))
        db.sync()
        load_forms(st.session_state.user_id)
        return True
    except Exception as e:
        log_error(f"Save form error: {str(e)}")
        st.error("Error saving form")
        return False

# Create new form
def new_form():
    st.session_state.current_form_id = None
    st.session_state.current_form_index = -1
    st.session_state.is_editing = True
    st.session_state.last_template_select = "None"
    
    cursor.execute('SELECT formNumber FROM forms WHERE userId = ? ORDER BY formNumber DESC LIMIT 1', (st.session_state.user_id,))
    latest_form_number_db = cursor.fetchone()
    form_number = int(latest_form_number_db[0]) + 1 if latest_form_number_db else 1

    now = datetime.now()
    return {
        'formNumber': form_number,
        'date': now.strftime('%d-%m-%Y'),
        'time': now.strftime('%H:%M:%S'),
        'customerName': '',
        'itemName': '',
        'mobileNumber': '',
        'grossWeight': None,
        'netWeight': None,
        'gold': None,
        'karat': None,
        'photo': '',
        'goldPurity': None
    }

# Helper to load form data into st.session_state.form_data from a given list
def load_form_from_list(index, form_list):
    if 0 <= index < len(form_list):
        st.session_state.current_form_index = index
        st.session_state.current_form_id = form_list[index]['id']
        st.session_state.is_editing = False
        form_data = form_list[index].copy()
        form_data['goldPurity'] = round((float(form_data['gold']) * float(form_data['grossWeight'])) / 100, 3) if form_data['gold'] is not None and form_data['grossWeight'] is not None else None
        return form_data
    return None

# Save template
def save_template(template_data):
    try:
        gold_val = float(template_data['gold']) if template_data['gold'] is not None else None
        karat = round((gold_val / 100) * 24, 2) if gold_val is not None else None
        gross_weight_val = float(template_data['grossWeight']) if template_data['grossWeight'] is not None else None

        cursor.execute('''INSERT INTO templates (itemName, grossWeight, netWeight, gold, karat, userId)
                         VALUES (?, ?, ?, ?, ?, ?)''',
                      (template_data['itemName'], gross_weight_val, gross_weight_val,
                       gold_val, karat, st.session_state.user_id))
        db.sync()
        load_templates(st.session_state.user_id)
        st.success("Template saved successfully")
    except Exception as e:
        log_error(f"Save template error: {str(e)}")
        st.error("Error saving template")

# Generate print HTML
def generate_print_html(form):
    karat_display = f"{form['karat']:.2f}" if form['karat'] is not None else ''
    gold_display = f"{form['gold']:.3f}" if form['gold'] is not None else ''
    sample_weight_display = f"{form['grossWeight']:.3f}" if form['grossWeight'] is not None else ''
    gold_purity_display = f"{form['goldPurity']:.3f}" if form['goldPurity'] is not None else ''

    styles = {
        'date': 'position: absolute; top: 80px; left: 30px; width: 100px; font-size: 14px;',
        'time': 'position: absolute; top: 80px; left: 200px; width: 100px; font-size: 14px;',
        'formNumber': 'position: absolute; top: 80px; left: 350px; width: 100px; font-size: 14px;',
        'customerName': 'position: absolute; top: 120px; left: 30px; width: 350px; font-size: 16px;',
        'itemName': 'position: absolute; top: 160px; left: 30px; width: 350px; font-size: 14px;',
        'sampleWeight': 'position: absolute; top: 200px; left: 30px; width: 100px; font-size: 14px;',
        'fineness': 'position: absolute; top: 240px; left: 30px; width: 100px; font-size: 14px; color: red; font-weight: bold;',
        'goldPurity': 'position: absolute; top: 280px; left: 30px; width: 100px; font-size: 14px;',
        'karat': 'position: absolute; top: 320px; left: 30px; width: 100px; font-size: 14px;',
        'photo': 'position: absolute; top: 120px; right: 30px; width: 200px; height: 200px; object-fit: contain; border: 1px solid #ccc;'
    }

    return f'''
    <html>
        <head>
            <style>
                @page {{
                    size: 6in 7.5in;
                    margin: 0;
                }}
                body {{
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 0;
                    width: 432px; /* 6 inches at 72 DPI */
                    height: 540px; /* 7.5 inches at 72 DPI */
                    position: relative;
                    overflow: hidden; /* Prevent content from spilling to additional pages */
                }}
                .print-overlay {{
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    page-break-after: avoid;
                    page-break-inside: avoid;
                }}
                .header, .footer, .title, .subtitle, .contact-info, .certificate {{
                    display: none;
                }}
            </style>
        </head>
        <body>
            <div class="print-overlay">
                <div style="{styles['date']}"><span>{form['date'] or ''}</span></div>
                <div style="{styles['time']}"><span>{form['time'] or ''}</span></div>
                <div style="{styles['formNumber']}"><span>{form['formNumber'] or ''}</span></div>
                <div style="{styles['customerName']}"><span>{form['customerName'] or ''}</span></div>
                <div style="{styles['itemName']}"><span>{form['itemName'] or ''}</span></div>
                <div style="{styles['sampleWeight']}"><span>{sample_weight_display} g</span></div>
                <div style="{styles['fineness']}"><span>{gold_display} %</span></div>
                <div style="{styles['goldPurity']}"><span>{gold_purity_display} g</span></div>
                <div style="{styles['karat']}"><span>{karat_display}</span></div>
                {f'<img src="{form["photo"]}" alt="Photo" style="{styles["photo"]}">' if form["photo"] else ''}
            </div>
        </body>
    </html>
    '''

# Print form directly
def print_form(form):
    try:
        form['grossWeight'] = float(form['grossWeight']) if form['grossWeight'] is not None and form['grossWeight'] != '' else None
        form['gold'] = float(form['gold']) if form['grossWeight'] is not None and form['gold'] != '' else None

        if validate_form(form):
            form['netWeight'] = form['grossWeight']
            form['karat'] = round((float(form['gold']) / 100) * 24, 2) if form['gold'] is not None else None
            form['goldPurity'] = round((float(form['gold']) * float(form['grossWeight'])) / 100, 3) if form['gold'] is not None and form['grossWeight'] is not None else None

            if save_form(form):
                html_content = generate_print_html(form)
                components.html(
                    f"""
                    <script>
                        var win = window.open('', '_blank');
                        if (win) {{
                            win.document.write(`{html_content}`);
                            win.document.close();
                            win.onload = function() {{
                                setTimeout(function() {{
                                    win.print();
                                    win.close();
                                }}, 500);
                            }};
                        }} else {{
                            console.error('Failed to open new window. Please allow pop-ups.');
                            alert('Failed to open print window. Please allow pop-ups for this site.');
                        }}
                    </script>
                    """,
                    height=0,
                    width=0
                )
                st.success("Form saved and sent to printer!")
                st.session_state.form_data = new_form()
                st.session_state.form_select = "New Form"
                st.session_state.search_active = False
                st.rerun()
            else:
                st.error("Failed to save form")
        else:
            st.error("Please fill in all required fields correctly (Customer Name, Item Name, Gross Weight, Gold %).")
    except ValueError as ve:
        log_error(f"Print form data conversion error: {str(ve)}")
        st.error("Invalid numeric input for Gross Weight or Gold (%). Please enter valid numbers.")
    except Exception as e:
        log_error(f"Print form error: {str(e)}")
        st.error("Failed to prepare form for printing. Check if pop-ups are allowed and try again.")

# Admin page
def admin_page():
    st.title("Admin Portal")
    st.subheader("Create New User")
    new_username = st.text_input("New Username", key="new_username")
    new_password = st.text_input("New Password", type="password", key="new_password")
    if st.button("Create User"):
        if not new_username or not new_password:
            st.error("Username and password are required")
        elif len(new_password) < 8 or not any(c.isalpha() for c in new_password) or not any(c.isdigit() for c in new_password):
            st.error("Password must be at least 8 characters with letters and numbers")
        else:
            cursor.execute('SELECT * FROM users WHERE username = ?', (new_username,))
            if cursor.fetchone():
                st.error("Username already exists")
            else:
                hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
                try:
                    cursor.execute('INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)', (new_username, hashed_password, 0))
                    cursor.execute('INSERT INTO audit_log (action, userId, username, timestamp) VALUES (?, ?, ?, ?)',
                                  ('create_user', st.session_state.user_id, new_username, datetime.now().isoformat()))
                    db.sync()
                    st.success("User created successfully")
                except Exception as e:
                    log_error(f"Create user error: {str(e)}")
                    st.error("Error creating user")

    st.subheader("Workflow Monitoring")
    sort_by = st.selectbox("Sort By", ["formNumber", "date", "username"], key="sort_by")
    filter_username = st.text_input("Filter by Username", key="filter_username")
    items_per_page = 10
    
    try:
        cursor.execute('SELECT f.*, u.username FROM forms f JOIN users u ON f.userId = u.id')
        forms = cursor.fetchall()
        df = pd.DataFrame([{
            'Username': row[12], 'Form Number': row[1], 'Date': row[2], 'Customer Name': row[4],
            'Item Name': row[5], 'Mobile Number': row[6], 'Gross Weight': row[7],
            'Net Weight': row[8], 'Gold': row[9], 'Karat': row[10], 'id': row[0], 'Photo': row[11]
        } for row in forms])

        if filter_username:
            df = df[df['Username'].str.lower().str.contains(filter_username.lower())]
        
        df['Date_dt'] = pd.to_datetime(df['Date'], format='%d-%m-%Y', errors='coerce')

        if sort_by == 'formNumber':
            df = df.sort_values('Form Number', ascending=False)
        elif sort_by == 'date':
            df = df.sort_values('Date_dt', ascending=False)
        elif sort_by == 'username':
            df = df.sort_values('Username')
        
        df = df.drop(columns=['Date_dt'])

        total_pages = max(1, (len(df) + items_per_page - 1) // items_per_page)
        page = st.number_input("Select Page", min_value=1, value=1, step=1, key="page_select")
        page = min(page, total_pages)
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        paginated_df = df.iloc[start_idx:end_idx]
        
        st.write(f"Showing page {page} of {total_pages}")
        for index, row in paginated_df.iterrows():
            with st.expander(f"Form {row['Form Number']} - {row['Customer Name'] or 'No Customer'}"):
                st.write(f"**Username:** {row['Username']}")
                st.write(f"**Date:** {row['Date']}")
                st.write(f"**Item Name:** {row['Item Name'] or 'N/A'}")
                st.write(f"**Mobile Number:** {row['Mobile Number'] or 'N/A'}")
                st.write(f"**Gross Weight:** {row['Gross Weight'] or 'N/A'} g")
                st.write(f"**Net Weight:** {row['Net Weight'] or 'N/A'} g")
                st.write(f"**Gold:** {row['Gold'] or 'N/A'} %")
                st.write(f"**Karat:** {f'{row['Karat']:.2f}' if row['Karat'] is not None else 'N/A'}")
                if row['Photo']:
                    st.image(row['Photo'], caption="Form Photo", width=300)
                if st.button(f"Delete Form {row['Form Number']}", key=f"delete_{row['id']}"):
                    try:
                        cursor.execute('DELETE FROM forms WHERE id = ?', (row['id'],))
                        cursor.execute('INSERT INTO audit_log (action, userId, username, timestamp) VALUES (?, ?, ?, ?)',
                                      ('delete_form', st.session_state.user_id, f"Form {row['Form Number']}", datetime.now().isoformat()))
                        db.sync()
                        st.success("Form deleted successfully")
                        st.rerun()
                    except Exception as e:
                        log_error(f"Delete form error: {str(e)}")
                        st.error("Error deleting form")
    except Exception as e:
        log_error(f"Get all forms error: {str(e)}")
        st.error("Failed to load workflow")

    st.subheader("Audit Log")
    try:
        cursor.execute('SELECT * FROM audit_log ORDER BY timestamp DESC')
        logs = cursor.fetchall()
        df = pd.DataFrame([{
            'Action': row[1], 'User ID': row[2], 'Username': row[3], 'Timestamp': row[4]
        } for row in logs])
        st.dataframe(df)
    except Exception as e:
        log_error(f"Audit log error: {str(e)}")
        st.error("Failed to load audit log")

# Report page
def report_page():
    st.title("Form Report")
    sort_by = st.selectbox("Sort By", ["formNumber", "date"], key="report_sort_by")
    filter_customer = st.text_input("Filter by Customer Name", key="filter_customer")
    items_per_page = 10
    
    try:
        cursor.execute('SELECT * FROM forms WHERE userId = ?', (st.session_state.user_id,))
        forms = cursor.fetchall()
        df = pd.DataFrame([{
            'Form Number': row[1], 'Date': row[2], 'Customer Name': row[4], 'Item Name': row[5],
            'Mobile Number': row[6], 'Gross Weight': row[7], 'Net Weight': row[8],
            'Gold': row[9], 'Karat': row[10]
        } for row in forms])
        
        df['Date_dt'] = pd.to_datetime(df['Date'], format='%d-%m-%Y', errors='coerce')

        if filter_customer:
            df = df[df['Customer Name'].str.lower().str.contains(filter_customer.lower(), na=False)]
        
        if sort_by == 'formNumber':
            df = df.sort_values('Form Number', ascending=False)
        elif sort_by == 'date':
            df = df.sort_values('Date_dt', ascending=False)
        
        df = df.drop(columns=['Date_dt'])

        df['Karat'] = df['Karat'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else 'N/A')
        
        total_pages = max(1, (len(df) + items_per_page - 1) // items_per_page)
        page = st.number_input("Select Page", min_value=1, value=1, step=1, key="report_page_select")
        page = min(page, total_pages)
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        paginated_df = df.iloc[start_idx:end_idx]
        
        st.write(f"Showing page {page} of {total_pages}")
        st.dataframe(paginated_df)
        csv = df.to_csv(index=False)
        st.download_button("Download CSV", csv, file_name="report.csv", mime="text/csv")
    except Exception as e:
        log_error(f"Report error: {str(e)}")
        st.error("Failed to load report")

# Main form page
def main_page():
    st.title("Gold Testing Form")
    load_forms(st.session_state.user_id)
    load_templates(st.session_state.user_id)

    st.markdown('<div class="logo no-print"><img src="https://via.placeholder.com/150?text=Logo" style="height: 60px;"></div>', unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])
    with col1:
        search_query = st.text_input("Search by Customer or Form Number", key="form_search")
        
        current_forms_list = st.session_state.forms
        st.session_state.search_active = False

        if search_query:
            current_forms_list = [
                f for f in st.session_state.forms
                if search_query.lower() in f['customerName'].lower() or str(search_query) in str(f['formNumber'])
            ]
            st.session_state.search_active = True
            
            if not current_forms_list:
                st.warning("No forms found matching your search. Showing a new form.")
                st.session_state.form_data = new_form()
                st.session_state.form_select = "New Form"
                st.session_state.is_editing = True
                st.session_state.search_active = False
                st.rerun()
                return

        if st.session_state.form_data is None:
            if st.session_state.forms:
                st.session_state.form_data = load_form_from_list(0, st.session_state.forms)
                st.session_state.form_select = f"Form {st.session_state.form_data['formNumber']} - {st.session_state.form_data['customerName'] or 'No Customer'}"
            else:
                st.session_state.form_data = new_form()
                st.session_state.form_select = "New Form"
                st.session_state.is_editing = True

        form_options_display = [f"Form {f['formNumber']} - {f['customerName'] or 'No Customer'}" for f in current_forms_list]
        form_options_display.insert(0, "New Form")

        initial_form_select_index = 0
        if st.session_state.form_select == "New Form":
            initial_form_select_index = 0
        elif st.session_state.current_form_id:
            current_form_display_string = f"Form {st.session_state.form_data['formNumber']} - {st.session_state.form_data['customerName'] or 'No Customer'}"
            try:
                initial_form_select_index = form_options_display.index(current_form_display_string)
            except ValueError:
                initial_form_select_index = 0
                st.session_state.form_data = new_form()
                st.session_state.form_select = "New Form"
                st.session_state.is_editing = True

        form_select = st.selectbox("Select Form", form_options_display, index=initial_form_select_index, key="form_select_box")

        if form_select != st.session_state.form_select:
            st.session_state.form_select = form_select
            if form_select == "New Form":
                st.session_state.form_data = new_form()
                st.session_state.is_editing = True
                st.session_state.search_active = False
            else:
                selected_form_number_str = form_select.split(' ')[1]
                selected_form_obj = next((f for f in current_forms_list if str(f['formNumber']) == selected_form_number_str), None)
                if selected_form_obj:
                    idx_in_current_list = current_forms_list.index(selected_form_obj)
                    st.session_state.form_data = load_form_from_list(idx_in_current_list, current_forms_list)
                    st.session_state.is_editing = False
                else:
                    st.error("Selected form not found. Loading a new form.")
                    st.session_state.form_data = new_form()
                    st.session_state.form_select = "New Form"
                    st.session_state.is_editing = True
            st.rerun()

    with col2:
        st.markdown("<div style='height: 30px;'></div>", unsafe_allow_html=True)
        if st.button("New Form", key="new_form_button_side"):
            st.session_state.form_data = new_form()
            st.session_state.form_select = "New Form"
            st.session_state.search_active = False
            st.rerun()
        
        if st.button("Previous", key="prev_form_button"):
            if current_forms_list and (st.session_state.current_form_index == -1 or st.session_state.current_form_index + 1 < len(current_forms_list)):
                new_index = st.session_state.current_form_index + 1 if st.session_state.current_form_index != -1 else 0
                st.session_state.form_data = load_form_from_list(new_index, current_forms_list)
                if st.session_state.form_data:
                    st.session_state.form_select = f"Form {st.session_state.form_data['formNumber']} - {st.session_state.form_data['customerName'] or 'No Customer'}"
                st.rerun()
            else:
                st.warning("No older forms available.")

        if st.button("Next", key="next_form_button"):
            if current_forms_list and st.session_state.current_form_index > 0:
                new_index = st.session_state.current_form_index - 1
                st.session_state.form_data = load_form_from_list(new_index, current_forms_list)
                if st.session_state.form_data:
                    st.session_state.form_select = f"Form {st.session_state.form_data['formNumber']} - {st.session_state.form_data['customerName'] or 'No Customer'}"
                st.rerun()
            else:
                st.warning("No newer forms available.")

        if st.button("Report", key="report_button"):
            st.session_state.page = "report"
            st.rerun()

    st.markdown('<div class="no-print"><h3>Template Options</h3></div>', unsafe_allow_html=True)
    template_options = [t['itemName'] or f"Template {i+1}" for i, t in enumerate(st.session_state.templates)]
    template_options.append("None")
    
    try:
        initial_template_index = template_options.index(st.session_state.last_template_select)
    except ValueError:
        initial_template_index = len(template_options) - 1

    template_select = st.selectbox("Select Template", template_options, index=initial_template_index, key="template_select")
    
    if template_select != "None" and (template_select != st.session_state.last_template_select):
        index = next((i for i, t in enumerate(st.session_state.templates) if t['itemName'] == template_select or f"Template {i+1}" == template_select), None)
        if index is not None:
            template = st.session_state.templates[index]
            st.session_state.form_data.update({
                'itemName': template['itemName'],
                'grossWeight': template['grossWeight'],
                'netWeight': template['grossWeight'],
                'gold': template['gold'],
                'karat': template['karat']
            })
            st.session_state.is_editing = True
            st.session_state.last_template_select = template_select
            st.rerun()

    if st.button("Save as Template", key="save_template_button"):
        gw = st.session_state.form_data['grossWeight']
        gold_perc = st.session_state.form_data['gold']

        template_data = {
            'itemName': st.session_state.form_data['itemName'],
            'grossWeight': float(gw) if gw is not None else None,
            'netWeight': float(gw) if gw is not None else None,
            'gold': float(gold_perc) if gold_perc is not None else None,
            'karat': round((float(gold_perc) / 100) * 24, 2) if gold_perc is not None else None,
            'userId': st.session_state.user_id
        }
        
        if not template_data['itemName']:
            st.error("Template requires an Item Name.")
        elif template_data['grossWeight'] is None or template_data['gold'] is None:
            st.error("Template requires Gross Weight and Gold (%) to be specified.")
        elif template_data['grossWeight'] < 0:
            st.error("Gross Weight must be non-negative for template.")
        elif not (0 <= template_data['gold'] <= 100):
            st.error("Gold percentage must be between 0 and 100 for template.")
        else:
            save_template(template_data)

    st.markdown('<div class="form-container"><div class="form-grid">', unsafe_allow_html=True)
    form_data = st.session_state.form_data

    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<label>Form Number</label>', unsafe_allow_html=True)
        form_data['formNumber'] = st.text_input("Form Number", value=str(form_data['formNumber']) if form_data['formNumber'] is not None else '', disabled=True, key="form_number")
    with col2:
        st.markdown('<label>Date</label>', unsafe_allow_html=True)
        form_data['date'] = st.text_input("Date", value=form_data['date'], disabled=True, key="date")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<label>Time</label>', unsafe_allow_html=True)
        form_data['time'] = st.text_input("Time", value=form_data['time'], disabled=True, key="time")
    with col2:
        st.markdown('<label>Customer Name</label>', unsafe_allow_html=True)
        form_data['customerName'] = st.text_input("Customer Name", value=form_data['customerName'], disabled=not st.session_state.is_editing, key="customer_name")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<label>Item Name</label>', unsafe_allow_html=True)
        form_data['itemName'] = st.text_input("Item Name", value=form_data['itemName'], disabled=not st.session_state.is_editing, key="item_name")
    with col2:
        st.markdown('<label>Mobile Number</label>', unsafe_allow_html=True)
        form_data['mobileNumber'] = st.text_input("Mobile Number", value=form_data['mobileNumber'], disabled=not st.session_state.is_editing, key="mobile_number")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<label>Gross Weight (g)</label>', unsafe_allow_html=True)
        current_gross_weight = float(form_data['grossWeight']) if form_data['grossWeight'] is not None else 0.0
        def update_net_weight():
            st.session_state.form_data['netWeight'] = st.session_state.gross_weight_input
        form_data['grossWeight'] = st.number_input("Gross Weight (g)", value=current_gross_weight, step=0.001, format="%.3f", disabled=not st.session_state.is_editing, key="gross_weight_input", on_change=update_net_weight)
    with col2:
        st.markdown('<label>Net Weight (g)</label>', unsafe_allow_html=True)
        net_weight_display = float(form_data['grossWeight']) if form_data['grossWeight'] is not None else 0.0
        form_data['netWeight'] = net_weight_display
        st.number_input("Net Weight (g)", value=net_weight_display, step=0.001, format="%.3f", disabled=True, key="net_weight_display")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<label>Gold (%)</label>', unsafe_allow_html=True)
        current_gold = float(form_data['gold']) if form_data['gold'] is not None else 0.0
        def update_karat():
            gold_val = st.session_state.gold_input
            st.session_state.form_data['karat'] = round((float(gold_val) / 100) * 24, 2) if gold_val is not None else 0.0
        form_data['gold'] = st.number_input("Gold (%)", value=current_gold, step=0.01, min_value=0.0, max_value=100.0, format="%.2f", disabled=not st.session_state.is_editing, key="gold_input", on_change=update_karat)
    with col2:
        st.markdown('<label>Karat</label>', unsafe_allow_html=True)
        karat_display_value = round((float(form_data['gold']) / 100) * 24, 2) if form_data['gold'] is not None else 0.0
        form_data['karat'] = karat_display_value
        st.number_input("Karat", value=karat_display_value, step=0.01, min_value=0.0, max_value=24.0, format="%.2f", disabled=True, key="karat_display")
    
    st.markdown('<div style="grid-column: span 2;"><label>Photo</label></div>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Upload Photo", type=["png", "jpg", "jpeg"], disabled=not st.session_state.is_editing, key="photo_uploader")
    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        form_data['photo'] = f"data:image/png;base64,{base64.b64encode(buffered.getvalue()).decode()}"
    
    if form_data['photo']:
        st.image(form_data['photo'], caption="Photo Preview", width=300)
        if st.button("Clear Photo", key="clear_photo_button"):
            form_data['photo'] = ''
            st.rerun()

    st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown('<div style="text-align: center; margin-top: 20px;" class="no-print">', unsafe_allow_html=True)
    if st.button("Print Form", key="print_form_button"):
        print_form(form_data)
    st.markdown('</div>', unsafe_allow_html=True)

# Main app routing
if st.session_state.user_id:
    st.sidebar.button("Logout", on_click=logout)
    
    nav_options = ["Main", "Report"]
    if st.session_state.is_admin:
        nav_options.insert(1, "Admin")

    if st.session_state.page.capitalize() not in nav_options:
        st.session_state.page = "main"

    selected_nav = st.sidebar.radio("Navigate", nav_options, index=nav_options.index(st.session_state.page.capitalize()))
    
    if selected_nav.lower() != st.session_state.page:
        st.session_state.page = selected_nav.lower()
        st.rerun()

if st.session_state.page == "login":
    login_page()
elif st.session_state.page == "admin":
    admin_page()
elif st.session_state.page == "report":
    report_page()
else:
    main_page()