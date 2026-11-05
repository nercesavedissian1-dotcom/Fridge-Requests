import io,json,os,secrets,sqlite3,hmac
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask,request,jsonify,send_file,session,send_from_directory
from openpyxl import Workbook
from openpyxl.styles import Font,PatternFill
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash,generate_password_hash
ROOT=Path(__file__).parent
app=Flask(__name__,static_folder='static',static_url_path='')
app.wsgi_app=ProxyFix(app.wsgi_app,x_proto=1,x_host=1)
app.secret_key=os.environ.get('SESSION_SECRET') or secrets.token_hex(32)
app.config.update(MAX_CONTENT_LENGTH=65536,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',SESSION_COOKIE_SECURE=os.environ.get('RAILWAY_ENVIRONMENT_NAME') is not None)
BRANCHES=['Bayada','Badaro','Bourj Hammoud','Dekwene']
CATALOG=json.loads((ROOT/'catalog.json').read_text())
DATA=Path(os.environ.get('DATA_DIR',str(ROOT/'data')));DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/'requests.db'
OWNER_HASH=generate_password_hash(os.environ['OWNER_PASSWORD']) if os.environ.get('OWNER_PASSWORD') else None

def connect():
 c=sqlite3.connect(DB,timeout=20);c.row_factory=sqlite3.Row;return c
with connect() as c:
 c.execute('PRAGMA journal_mode=WAL')
 c.execute('CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, branch TEXT NOT NULL, employee TEXT NOT NULL, createdAt TEXT NOT NULL, items TEXT NOT NULL, notes TEXT NOT NULL)')

@app.before_request
def same_origin():
 if request.method=='POST' and request.headers.get('Origin') and request.headers['Origin'].rstrip('/')!=request.host_url.rstrip('/'):
  return jsonify(error='Please submit using this website.'),403

@app.get('/api/health')
def health():
 with connect() as c:c.execute('SELECT 1')
 return jsonify(status='ok')

@app.post('/api/login')
def login():
 b=request.get_json(silent=True) or {}
 if not OWNER_HASH:return jsonify(error='Owner access is not configured yet.'),503
 if not isinstance(b,dict) or not isinstance(b.get('password'),str) or not check_password_hash(OWNER_HASH,b['password']):return jsonify(error='Incorrect owner password.'),401
 session.clear();session['owner']=True;return jsonify(ok=True)

@app.post('/api/logout')
def logout():session.clear();return jsonify(ok=True)

@app.get('/api/requests')
def history():
 if not session.get('owner'):return jsonify(error='Owner login required.'),401
 with connect() as c:rows=c.execute('SELECT * FROM requests ORDER BY createdAt DESC').fetchall()
 return jsonify([{**dict(r),'items':json.loads(r['items'])} for r in rows])

@app.post('/api/requests')
def submit():
 b=request.get_json(silent=True)
 if not isinstance(b,dict):return jsonify(error='Invalid request.'),400
 items=b.get('items');employee=b.get('employee');branch=b.get('branch');notes=b.get('notes','')
 if branch not in BRANCHES or not isinstance(employee,str) or not employee.strip() or len(employee)>100 or not isinstance(items,list) or not 1<=len(items)<=46 or not isinstance(notes,str) or len(notes)>1000:return jsonify(error='Please check your name, branch and selected items.'),400
 seen=set()
 for i in items:
  if not isinstance(i,dict) or i.get('category') not in CATALOG or i.get('name') not in CATALOG[i['category']] or type(i.get('quantity')) is not int or not 1<=i['quantity']<=999 or i['name'] in seen:return jsonify(error='Check your selected items and quantities (1–999).'),400
  seen.add(i['name'])
 id=secrets.token_hex(16);created=datetime.now(ZoneInfo('UTC')).isoformat()
 with connect() as c:c.execute('INSERT INTO requests VALUES (?,?,?,?,?,?)',(id,branch,employee.strip(),created,json.dumps(items),notes.strip()))
 return jsonify(id=id,createdAt=created),201

@app.get('/api/export')
def export():
 if not session.get('owner'):return jsonify(error='Owner login required.'),401
 with connect() as c:rows=c.execute('SELECT * FROM requests ORDER BY createdAt DESC').fetchall()
 wb=Workbook();wb.remove(wb.active)
 for branch in BRANCHES:
  ws=wb.create_sheet(branch);ws.append(['Date (Beirut)','Employee','Branch','Category','Item','Quantity','Notes','Request ID'])
  for r in rows:
   if r['branch']!=branch:continue
   for i in json.loads(r['items']):
    vals=[datetime.fromisoformat(r['createdAt']).astimezone(ZoneInfo('Asia/Beirut')).strftime('%d/%m/%Y %H:%M'),r['employee'],branch,i['category'],i['name'],i['quantity'],r['notes'],r['id']]
    ws.append(vals)
    for cell in ws[ws.max_row]:
     if isinstance(cell.value,str):cell.data_type='s'
  for cell in ws[1]:cell.font=Font(bold=True);cell.fill=PatternFill('solid',fgColor='DCEDE6')
  ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
  for col,width in zip('ABCDEFGH',[23,25,23,18,34,12,45,36]):ws.column_dimensions[col].width=width
 output=io.BytesIO();wb.save(output);output.seek(0)
 return send_file(output,as_attachment=True,download_name='branch-requests.xlsx',mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',max_age=0)

@app.get('/')
def index():return send_from_directory(app.static_folder,'index.html')

@app.errorhandler(413)
def too_large(e):return jsonify(error='Request is too large.'),413
