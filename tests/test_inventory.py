import os,sys,tempfile,unittest,sqlite3,json,io,importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from openpyxl import load_workbook
ROOT=Path(__file__).resolve().parents[1]
class StockTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();os.environ.update(DATA_DIR=self.tmp.name,OWNER_PASSWORD='test-only',SESSION_SECRET='test-only-session')
  # Existing requests must survive the inventory upgrade unchanged.
  with sqlite3.connect(Path(self.tmp.name)/'requests.db') as c:
   c.execute('CREATE TABLE requests (id TEXT PRIMARY KEY, branch TEXT NOT NULL, employee TEXT NOT NULL, createdAt TEXT NOT NULL, items TEXT NOT NULL, notes TEXT NOT NULL)')
   c.execute('INSERT INTO requests VALUES (?,?,?,?,?,?)',('legacy','Bayada','Employee','2026-11-05T12:00:00+00:00',json.dumps([{'name':'Pepsi','category':'Drinks','quantity':1}]),''))
  spec=importlib.util.spec_from_file_location('stock_app',ROOT/'app.py');self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m);self.m.app.config['TESTING']=True
  self.owner=self.m.app.test_client();self.owner.post('/api/login',json={'password':'test-only'});self.public=self.m.app.test_client()
 def tearDown(self):self.tmp.cleanup()
 def item(self,name='Marlboro Red Paper'):return next(i for i in self.owner.get('/api/stock').json['items'] if i['name']==name)
 def update(self,qty,action='set',token=None):
  i=self.item();return self.owner.post('/api/stock',json={'action':action,'id':i['id'],'version':i['version'],'quantity':qty,'token':token or self.m.secrets.token_hex(16)})
 def payload(self,branch='Bayada',quantity=1,token=None):return {'branch':branch,'employee':'Employee','notes':'','token':token or self.m.secrets.token_hex(16),'items':[{'name':'Marlboro Red Paper','category':'Cigarettes','quantity':quantity}]}
 def test_shared_deduction_and_retry(self):
  self.assertEqual(self.update(2).status_code,200)
  b=self.payload();r=self.public.post('/api/collections',json=b);self.assertEqual(r.status_code,201);self.assertEqual(self.item()['quantity'],1)
  retry=self.public.post('/api/collections',json=b);self.assertEqual(retry.json['id'],r.json['id']);self.assertEqual(self.item()['quantity'],1)
  self.assertEqual(self.public.post('/api/collections',json=self.payload('Badaro')).status_code,201);self.assertEqual(self.item()['quantity'],0)
  self.assertEqual(self.public.post('/api/collections',json=self.payload('Dekwene')).status_code,409);self.assertEqual(self.item()['quantity'],0)
 def test_requests_do_not_deduct_and_legacy_preserved(self):
  self.update(2);self.assertEqual(self.public.post('/api/requests',json=self.payload()).status_code,201);self.assertEqual(self.item()['quantity'],2)
  self.assertTrue(any(r['id']=='legacy' for r in self.owner.get('/api/requests').json))
 def test_delivery_retry_and_stale_count(self):
  self.update(2);old=self.item();token=self.m.secrets.token_hex(16)
  self.update(5,'add',token);self.update(5,'add',token);self.assertEqual(self.item()['quantity'],7)
  r=self.owner.post('/api/stock',json={'action':'set','id':old['id'],'version':old['version'],'quantity':4,'token':self.m.secrets.token_hex(16)})
  self.assertEqual(r.status_code,409);self.assertEqual(self.item()['quantity'],7)
 def test_new_product_and_export(self):
  r=self.owner.post('/api/stock',json={'action':'new','category':'Snacks','name':'New Snack','quantity':5,'token':self.m.secrets.token_hex(16)});self.assertEqual(r.status_code,200)
  self.assertIn('New Snack',self.public.get('/api/catalog').json['catalog']['Snacks'])
  b=self.payload();b['items']=[{'name':'New Snack','category':'Snacks','quantity':2}];self.assertEqual(self.public.post('/api/collections',json=b).status_code,201)
  self.assertEqual(self.item('New Snack')['quantity'],3)
  self.assertEqual(self.public.post('/api/requests',json=b).status_code,201)
  wb=load_workbook(io.BytesIO(self.owner.get('/api/export').data));self.assertEqual(wb.sheetnames,self.m.BRANCHES+['Shared Stock','Stock Movements'])
  self.assertIn('Taken from stock',[r[8] for r in wb['Bayada'].iter_rows(min_row=2,values_only=True)])
 def test_atomic_multi_item_and_concurrent_takes(self):
  self.update(2);b=self.payload();b['items'].append({'name':'Pepsi','category':'Drinks','quantity':1})
  self.assertEqual(self.public.post('/api/collections',json=b).status_code,409);self.assertEqual(self.item()['quantity'],2)
  self.update(1)
  def take(_):
   with self.m.app.test_client() as client:return client.post('/api/collections',json=self.payload()).status_code
  with ThreadPoolExecutor(2) as pool:results=list(pool.map(take,range(2)))
  self.assertEqual(sorted(results),[201,409]);self.assertEqual(self.item()['quantity'],0)
 def test_permissions_and_validation(self):
  self.assertEqual(self.public.get('/api/stock').status_code,401);self.assertEqual(self.public.post('/api/stock',json={}).status_code,401)
  for qty in [-1,0,1.5,True]:self.assertEqual(self.public.post('/api/collections',json=self.payload(quantity=qty)).status_code,400)
  self.assertEqual(self.update(-1).status_code,400)
class VariantTests(StockTests):
 def test_variants_and_legacy_migration(self):
  with self.m.connect() as c:
   c.execute("INSERT INTO inventory(category,name,quantity) VALUES ('Drinks','Buz Tin',0)")
   c.execute("INSERT INTO inventory(category,name,quantity) VALUES ('Drinks','Ice Coffee',0)")
  spec=importlib.util.spec_from_file_location('stock_app_reloaded',ROOT/'app.py');updated=importlib.util.module_from_spec(spec);spec.loader.exec_module(updated)
  client=updated.app.test_client();cat=client.get('/api/catalog').json['catalog']
  for name in ['Buz Tin Red','Buz Tin Yellow','Buz 10% White','Buz 10% Yellow','Ice Coffee Red','Ice Coffee Black']:self.assertIn(name,cat['Drinks'])
  for name in ['Buz Tin','Buz 10%','Ice Coffee']:self.assertNotIn(name,cat['Drinks'])
  self.assertEqual(sum(len(v) for v in cat.values()),49)
  self.assertEqual(cat['Snacks'][-3:],['Sandwich Wafer Red','Sandwich Wafer Blue','Sandwich Wafer Black'])
  self.assertTrue(any(r['id']=='legacy' for r in self.owner.get('/api/requests').json))
  a=self.item('Ice Coffee Red');b=self.item('Ice Coffee Black')
  for i,q in [(a,2),(b,5)]:self.assertEqual(self.owner.post('/api/stock',json={'action':'set','id':i['id'],'version':i['version'],'quantity':q,'token':self.m.secrets.token_hex(16)}).status_code,200)
  payload=self.payload();payload['items']=[{'name':'Ice Coffee Red','category':'Drinks','quantity':1}]
  self.assertEqual(client.post('/api/collections',json=payload).status_code,201)
  self.assertEqual(self.item('Ice Coffee Red')['quantity'],1);self.assertEqual(self.item('Ice Coffee Black')['quantity'],5)

if __name__=='__main__':unittest.main()
