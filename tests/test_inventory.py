import os,tempfile,unittest,sqlite3,json,io,importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from openpyxl import load_workbook
ROOT=Path(__file__).resolve().parents[1]
class ApprovalTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();os.environ.update(DATA_DIR=self.tmp.name,OWNER_PASSWORD='test-only',SESSION_SECRET='test-only-session')
  with sqlite3.connect(Path(self.tmp.name)/'requests.db') as c:
   c.execute('CREATE TABLE requests (id TEXT PRIMARY KEY, branch TEXT NOT NULL, employee TEXT NOT NULL, createdAt TEXT NOT NULL, items TEXT NOT NULL, notes TEXT NOT NULL)')
   c.execute('INSERT INTO requests VALUES (?,?,?,?,?,?)',('legacy','Bayada','Employee','2026-11-05T12:00:00+00:00',json.dumps([{'name':'Pepsi','category':'Drinks','quantity':1}]),''))
   c.execute('CREATE TABLE inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, name TEXT NOT NULL COLLATE NOCASE UNIQUE, quantity INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 0)')
   c.execute("INSERT INTO inventory(category,name,quantity) VALUES ('Drinks','Water',476)")
  spec=importlib.util.spec_from_file_location('stock_app',ROOT/'app.py');self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m);self.m.app.config['TESTING']=True
  self.owner=self.m.app.test_client();self.owner.post('/api/login',json={'password':'test-only'});self.public=self.m.app.test_client()
 def tearDown(self):self.tmp.cleanup()
 def item(self,name='Marlboro Red Paper'):return next(i for i in self.owner.get('/api/stock').json['items'] if i['name']==name)
 def setqty(self,qty,name='Marlboro Red Paper',action='set',token=None):
  i=self.item(name);return self.owner.post('/api/stock',json={'action':action,'id':i['id'],'version':i['version'],'quantity':qty,'token':token or self.m.secrets.token_hex(16)})
 def payload(self,branch='Bayada',quantity=1):return {'branch':branch,'employee':'Employee','notes':'','items':[{'name':'Marlboro Red Paper','category':'Cigarettes','quantity':quantity}]}
 def submit(self,payload=None):
  r=self.public.post('/api/requests',json=payload or self.payload());self.assertEqual(r.status_code,201,r.json);return r.json['id']
 def decision(self,id,action='accept'):return self.owner.post(f'/api/requests/{id}/decision',json={'action':action})
 def status(self,id):return next(r for r in self.owner.get('/api/requests').json if r['id']==id)['status']
 def test_pending_and_permissions(self):
  self.setqty(2);id=self.submit();self.assertEqual(self.item()['quantity'],2);self.assertEqual(self.status(id),'Pending')
  self.assertEqual(self.public.post(f'/api/requests/{id}/decision',json={'action':'accept'}).status_code,401)
  self.assertEqual(self.decision(id,'invalid').status_code,400);self.assertEqual(self.status(id),'Pending')
 def test_accept_deducts_once(self):
  self.setqty(2);id=self.submit();a=self.decision(id);self.assertEqual(a.status_code,200);self.assertEqual(self.item()['quantity'],1);self.assertEqual(self.status(id),'Accepted')
  b=self.decision(id);self.assertEqual(b.json['decidedAt'],a.json['decidedAt']);self.assertEqual(self.item()['quantity'],1)
  self.assertEqual(self.decision(id,'refuse').status_code,409)
  ledger=self.owner.get('/api/stock').json['movements'];self.assertEqual(len([m for m in ledger if m['reference']==id]),1)
 def test_refuse_does_not_touch_stock(self):
  self.setqty(2);id=self.submit();self.assertEqual(self.decision(id,'refuse').status_code,200);self.assertEqual(self.item()['quantity'],2);self.assertEqual(self.status(id),'Refused')
  self.assertEqual(self.decision(id,'refuse').status_code,200);self.assertEqual(self.decision(id).status_code,409)
 def test_insufficient_stock_is_atomic_and_can_retry_after_delivery(self):
  self.setqty(2);p=self.payload();p['items'].append({'name':'Pepsi','category':'Drinks','quantity':1});id=self.submit(p)
  self.assertEqual(self.decision(id).status_code,409);self.assertEqual(self.status(id),'Pending');self.assertEqual(self.item()['quantity'],2)
  self.setqty(1,'Pepsi');self.assertEqual(self.decision(id).status_code,200);self.assertEqual(self.item()['quantity'],1);self.assertEqual(self.item('Pepsi')['quantity'],0)
 def test_same_request_concurrent_accept(self):
  self.setqty(2);id=self.submit()
  def accept(_):
   with self.m.app.test_client() as c:
    c.post('/api/login',json={'password':'test-only'});return c.post(f'/api/requests/{id}/decision',json={'action':'accept'}).status_code
  with ThreadPoolExecutor(2) as pool:results=list(pool.map(accept,range(2)))
  self.assertEqual(results,[200,200]);self.assertEqual(self.item()['quantity'],1)
 def test_two_requests_cannot_oversell(self):
  self.setqty(1);ids=[self.submit(),self.submit(self.payload('Badaro'))]
  def accept(id):
   with self.m.app.test_client() as c:
    c.post('/api/login',json={'password':'test-only'});return c.post(f'/api/requests/{id}/decision',json={'action':'accept'}).status_code
  with ThreadPoolExecutor(2) as pool:results=list(pool.map(accept,ids))
  self.assertEqual(sorted(results),[200,409]);self.assertEqual(self.item()['quantity'],0)
 def test_old_take_route_disabled(self):
  self.setqty(2)
  for c in [self.public,self.owner]:self.assertEqual(c.post('/api/collections',json=self.payload()).status_code,410)
  self.assertEqual(self.item()['quantity'],2)
 def test_migration_preserves_counts_and_history(self):
  self.assertEqual(self.item('Water')['quantity'],476);self.assertEqual(self.status('legacy'),'Pending')
  spec=importlib.util.spec_from_file_location('stock_reloaded',ROOT/'app.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  self.assertEqual(self.item('Water')['quantity'],476);self.assertEqual(self.status('legacy'),'Pending')
 def test_export_and_new_product(self):
  self.owner.post('/api/stock',json={'action':'new','category':'Snacks','name':'New Snack','quantity':5,'token':self.m.secrets.token_hex(16)})
  p=self.payload();p['items']=[{'name':'New Snack','category':'Snacks','quantity':2}];id=self.submit(p);self.assertEqual(self.decision(id).status_code,200);self.assertEqual(self.item('New Snack')['quantity'],3)
  refused=self.submit();self.decision(refused,'refuse')
  w=load_workbook(io.BytesIO(self.owner.get('/api/export').data));self.assertEqual(w.sheetnames,self.m.BRANCHES+['Shared Stock','Stock Movements'])
  statuses=[r[9] for r in w['Bayada'].iter_rows(min_row=2,values_only=True)];self.assertIn('Accepted',statuses);self.assertIn('Refused',statuses);self.assertIn('Pending',statuses)
 def test_catalog_and_delivery_retry(self):
  catalog=self.public.get('/api/catalog').json['catalog'];self.assertEqual(sum(map(len,catalog.values())),49)
  self.assertIn('Ice Coffee Red',catalog['Drinks']);self.assertIn('Ice Coffee Black',catalog['Drinks'])
  self.setqty(2);token=self.m.secrets.token_hex(16);self.setqty(3,action='add',token=token);self.setqty(3,action='add',token=token);self.assertEqual(self.item()['quantity'],5)
if __name__=='__main__':unittest.main()
