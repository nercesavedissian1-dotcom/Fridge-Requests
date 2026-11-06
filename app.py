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
BRANCHES=['Bayada','Badaro','Bourj Hammoud','Dekwene','Main Office Mano']
CATALOG=json.loads((ROOT/'catalog.json').read_text())
DATA=Path(os.environ.get('DATA_DIR',str(ROOT/'data')));DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/'requests.db'
OWNER_HASH=generate_password_hash(os.environ['OWNER_PASSWORD']) if os.environ.get('OWNER_PASSWORD') else None

def connect():
 c=sqlite3.connect(DB,timeout=20);c.row_factory=sqlite3.Row;return c
with connect() as c:
 c.execute('PRAGMA journal_mode=WAL')
 c.execute('CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, branch TEXT NOT NULL, employee TEXT NOT NULL, createdAt TEXT NOT NULL, items TEXT NOT NULL, notes TEXT NOT NULL)')
 c.execute('BEGIN IMMEDIATE')
 columns={r['name'] for r in c.execute('PRAGMA table_info(requests)')}
 if 'status' not in columns:c.execute("ALTER TABLE requests ADD COLUMN status TEXT NOT NULL DEFAULT 'Pending'")
 if 'decidedAt' not in columns:c.execute("ALTER TABLE requests ADD COLUMN decidedAt TEXT NOT NULL DEFAULT ''")

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
 with connect() as c:
  rows=[{**dict(r),'type':'Request'} for r in c.execute('SELECT * FROM requests')] + [{**dict(r),'type':'Taken from stock','status':'Collected','decidedAt':''} for r in c.execute('SELECT * FROM collections')]
 return jsonify([{**r,'items':json.loads(r['items'])} for r in sorted(rows,key=lambda r:r['createdAt'],reverse=True)])

@app.post('/api/requests')
def submit():
 b=request.get_json(silent=True)
 if not isinstance(b,dict):return jsonify(error='Invalid request.'),400
 items=b.get('items');employee=b.get('employee');branch=b.get('branch');notes=b.get('notes','')
 if branch not in BRANCHES or not isinstance(employee,str) or not employee.strip() or len(employee)>100 or not isinstance(items,list) or not 1<=len(items)<=500 or not isinstance(notes,str) or len(notes)>1000:return jsonify(error='Please check your name, branch and selected items.'),400
 seen=set()
 catalog=catalog_data()
 for i in items:
  if not isinstance(i,dict) or not isinstance(i.get('category'),str) or i.get('category') not in catalog or not isinstance(i.get('name'),str) or i.get('name') not in catalog[i['category']] or type(i.get('quantity')) is not int or not 1<=i['quantity']<=999 or i['name'] in seen:return jsonify(error='Check your selected items and quantities (1–999).'),400
  seen.add(i['name'])
 id=secrets.token_hex(16);created=datetime.now(ZoneInfo('UTC')).isoformat()
 with connect() as c:c.execute('INSERT INTO requests (id,branch,employee,createdAt,items,notes) VALUES (?,?,?,?,?,?)',(id,branch,employee.strip(),created,json.dumps(items),notes.strip()))
 return jsonify(id=id,createdAt=created,status='Pending'),201

@app.get('/api/export')
def export():
 if not session.get('owner'):return jsonify(error='Owner login required.'),401
 with connect() as c:
  rows=[{**dict(r),'type':'Request'} for r in c.execute('SELECT * FROM requests')] + [{**dict(r),'type':'Taken from stock','status':'Collected','decidedAt':''} for r in c.execute('SELECT * FROM collections')]
  stock=inventory_rows(c);movements=[dict(r) for r in c.execute('SELECT * FROM stock_movements ORDER BY createdAt DESC')]
 rows.sort(key=lambda r:r['createdAt'],reverse=True)
 wb=Workbook();wb.remove(wb.active)
 for branch in BRANCHES:
  ws=wb.create_sheet(branch);ws.append(['Date (Beirut)','Employee','Branch','Category','Item','Quantity','Notes','Request ID','Type','Status','Decision date (Beirut)'])
  for r in rows:
   if r['branch']!=branch:continue
   for i in json.loads(r['items']):
    vals=[datetime.fromisoformat(r['createdAt']).astimezone(ZoneInfo('Asia/Beirut')).strftime('%d/%m/%Y %H:%M'),r['employee'],branch,i['category'],i['name'],i['quantity'],r['notes'],r['id'],r['type'],r['status'],datetime.fromisoformat(r['decidedAt']).astimezone(ZoneInfo('Asia/Beirut')).strftime('%d/%m/%Y %H:%M') if r['decidedAt'] else '']
    ws.append(vals)
    for cell in ws[ws.max_row]:
     if isinstance(cell.value,str):cell.data_type='s'
  for cell in ws[1]:cell.font=Font(bold=True);cell.fill=PatternFill('solid',fgColor='DCEDE6')
  ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
  for col,width in zip('ABCDEFGHIJK',[23,25,23,18,34,12,45,36,24,18,26]):ws.column_dimensions[col].width=width
 ws=wb.create_sheet('Shared Stock');ws.append(['Category','Item','Current Quantity'])
 for r in stock:ws.append([r['category'],r['name'],r['quantity']])
 ws=wb.create_sheet('Stock Movements');ws.append(['Date (Beirut)','Item','Category','Action','Change','Before','After','Branch','Employee','Note','Reference'])
 for r in movements:ws.append([datetime.fromisoformat(r['createdAt']).astimezone(ZoneInfo('Asia/Beirut')).strftime('%d/%m/%Y %H:%M'),r['name'],r['category'],r['kind'],r['delta'],r['before_qty'],r['after_qty'],r['branch'],r['employee'],r['note'],r['reference']])
 for ws in wb:
  ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
  for cell in ws[1]:cell.font=Font(bold=True);cell.fill=PatternFill('solid',fgColor='DCEDE6')
  for row in ws:
   for cell in row:
    if isinstance(cell.value,str):cell.data_type='s'
  if ws.title in ['Shared Stock','Stock Movements']:
   for col in ws.columns:ws.column_dimensions[col[0].column_letter].width=26
 output=io.BytesIO();wb.save(output);output.seek(0)
 return send_file(output,as_attachment=True,download_name='branch-requests.xlsx',mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',max_age=0)

@app.get('/')
def index():return send_from_directory(app.static_folder,'index.html')

@app.errorhandler(413)
def too_large(e):return jsonify(error='Request is too large.'),413


# Shared inventory changes only when the owner accepts a request.
with connect() as c:
 c.execute('CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, name TEXT NOT NULL COLLATE NOCASE UNIQUE, quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity>=0), version INTEGER NOT NULL DEFAULT 0)')
 c.execute('CREATE TABLE IF NOT EXISTS collections (id TEXT PRIMARY KEY, token TEXT NOT NULL UNIQUE, branch TEXT NOT NULL, employee TEXT NOT NULL, createdAt TEXT NOT NULL, items TEXT NOT NULL, notes TEXT NOT NULL)')
 c.execute('CREATE TABLE IF NOT EXISTS stock_movements (id TEXT PRIMARY KEY, token TEXT NOT NULL, item_id INTEGER NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL, createdAt TEXT NOT NULL, kind TEXT NOT NULL, delta INTEGER NOT NULL, before_qty INTEGER NOT NULL, after_qty INTEGER NOT NULL, branch TEXT NOT NULL, employee TEXT NOT NULL, note TEXT NOT NULL, reference TEXT NOT NULL, UNIQUE(token,item_id))')
 c.execute('BEGIN IMMEDIATE')
 if 'active' not in {r['name'] for r in c.execute('PRAGMA table_info(inventory)')}:c.execute('ALTER TABLE inventory ADD COLUMN active INTEGER NOT NULL DEFAULT 1')
 # Retain original rows and historical references; retire only empty, unsplit products.
 for name in ['Buz Tin','Buz 10%','Ice Coffee']:
  c.execute("UPDATE inventory SET active=0 WHERE category='Drinks' AND name=? AND quantity=0",(name,))
 for category,names in CATALOG.items():
  for name in names:c.execute('INSERT OR IGNORE INTO inventory(category,name) VALUES (?,?)',(category,name))

def now():return datetime.now(ZoneInfo('UTC')).isoformat()
def inventory_rows(c):return [dict(r) for r in c.execute('SELECT * FROM inventory WHERE active=1 ORDER BY id')]
def catalog_data():
 with connect() as c:
  rows=inventory_rows(c)
 result={k:[] for k in CATALOG}
 for r in rows:result[r['category']].append(r['name'])
 return result

def movement(c,token,row,kind,delta,before,after,branch='',employee='Owner',note='',reference=''):
 c.execute('INSERT INTO stock_movements VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(secrets.token_hex(16),token,row['id'],row['name'],row['category'],now(),kind,delta,before,after,branch,employee,note,reference))

@app.get('/api/catalog')
def get_catalog():
 with connect() as c:rows=inventory_rows(c)
 result={k:[] for k in CATALOG}
 for r in rows:result[r['category']].append(r['name'])
 return jsonify(catalog=result,availability={r['name']:r['quantity'] for r in rows})

@app.get('/api/stock')
def get_stock():
 if not session.get('owner'):return jsonify(error='Owner login required.'),401
 with connect() as c:
  rows=inventory_rows(c);movements=[dict(r) for r in c.execute('SELECT * FROM stock_movements ORDER BY createdAt DESC LIMIT 200')]
 return jsonify(items=rows,movements=movements)

@app.post('/api/stock')
def update_stock():
 if not session.get('owner'):return jsonify(error='Owner login required.'),401
 b=request.get_json(silent=True)
 if not isinstance(b,dict):return jsonify(error='Invalid stock update.'),400
 action=b.get('action');qty=b.get('quantity');token=b.get('token');note=b.get('note','')
 if action not in ['set','add','new'] or type(qty) is not int or qty<0 or qty>1000000 or not isinstance(token,str) or not 16<=len(token)<=100 or not isinstance(note,str) or len(note)>500 or (action=='add' and qty==0):return jsonify(error='Enter a valid whole quantity and try again.'),400
 with connect() as c:
  c.execute('BEGIN IMMEDIATE')
  if c.execute('SELECT 1 FROM stock_movements WHERE token=?',(token,)).fetchone():return jsonify(ok=True,replayed=True)
  if action=='new':
   category=b.get('category');name=b.get('name')
   if not isinstance(category,str) or category not in CATALOG or not isinstance(name,str) or not name.strip() or len(name.strip())>100:return jsonify(error='Choose a category and enter the new item name.'),400
   if c.execute('SELECT 1 FROM inventory WHERE name=?',(name.strip(),)).fetchone():return jsonify(error='This item already exists. Use Add delivery instead.'),409
   cur=c.execute('INSERT INTO inventory(category,name,quantity) VALUES (?,?,?)',(category,name.strip(),qty))
   row=c.execute('SELECT * FROM inventory WHERE id=? AND active=1',(cur.lastrowid,)).fetchone();before=0;after=qty;kind='New item'
  else:
   if type(b.get('id')) is not int:return jsonify(error='Choose an item.'),400
   row=c.execute('SELECT * FROM inventory WHERE id=? AND active=1',(b['id'],)).fetchone()
   if not row:return jsonify(error='Item not found.'),404
   before=row['quantity'];after=before+qty if action=='add' else qty
   if action=='set' and b.get('version')!=row['version']:return jsonify(error='Stock changed while you were editing. Refresh and check the current balance.'),409
   if after>1000000:return jsonify(error='Quantity is too large.'),400
   c.execute('UPDATE inventory SET quantity=?,version=version+1 WHERE id=?',(after,row['id']))
   kind='Delivery' if action=='add' else 'Stock count'
  movement(c,token,row,kind,after-before,before,after,note=note)
 return jsonify(ok=True)

@app.post('/api/collections')
def collect_stock():
 # Old tabs must not bypass owner approval.
 return jsonify(error='Direct collections are no longer available. Submit a request for owner approval.'),410

@app.post('/api/requests/<request_id>/decision')
def decide_request(request_id):
 if not session.get('owner'):return jsonify(error='Owner login required.'),401
 b=request.get_json(silent=True)
 if not isinstance(b,dict) or b.get('action') not in ['accept','refuse']:return jsonify(error='Choose Accept or Refuse.'),400
 status='Accepted' if b['action']=='accept' else 'Refused'
 with connect() as c:
  c.execute('BEGIN IMMEDIATE')
  req=c.execute('SELECT * FROM requests WHERE id=?',(request_id,)).fetchone()
  if not req:return jsonify(error='Request not found.'),404
  if req['status']==status:return jsonify(ok=True,status=status,decidedAt=req['decidedAt'],replayed=True)
  if req['status']!='Pending':return jsonify(error=f"This request has already been {req['status'].lower()}. Refresh the list."),409
  if status=='Accepted':
   selected=[]
   for item in json.loads(req['items']):
    row=c.execute('SELECT * FROM inventory WHERE name=? AND category=? AND active=1',(item['name'],item['category'])).fetchone()
    if not row:return jsonify(error=f"{item['name']} is no longer selectable. Refuse this request and ask the branch to submit the separate item."),409
    if row['quantity']<item['quantity']:return jsonify(error=f"Not enough {row['name']}: {row['quantity']} available, {item['quantity']} requested. Nothing was deducted."),409
    selected.append((row,item['quantity']))
   for row,qty in selected:
    after=row['quantity']-qty
    c.execute('UPDATE inventory SET quantity=?,version=version+1 WHERE id=?',(after,row['id']))
    movement(c,'request:'+request_id,row,'Accepted request',-qty,row['quantity'],after,req['branch'],req['employee'],req['notes'],request_id)
  decided=now()
  c.execute('UPDATE requests SET status=?,decidedAt=? WHERE id=?',(status,decided,request_id))
 return jsonify(ok=True,status=status,decidedAt=decided)
