import os,secrets,sqlite3,io,csv,smtplib,requests
from email.message import EmailMessage
from urllib.parse import urlencode
from flask import Flask,request,redirect,url_for,render_template,session,jsonify,send_file
app=Flask(__name__); app.secret_key=os.getenv('FLASK_SECRET_KEY','CHANGE_ME')
DB=os.getenv('DATABASE_PATH','queue.db'); LID=os.getenv('LINE_LOGIN_CHANNEL_ID',''); LSECRET=os.getenv('LINE_LOGIN_CHANNEL_SECRET',''); CALLBACK=os.getenv('LINE_CALLBACK_URL',''); TOKEN=os.getenv('LINE_MESSAGING_ACCESS_TOKEN',''); OA_URL=os.getenv('LINE_OFFICIAL_ACCOUNT_URL',''); ADMIN=os.getenv('ADMIN_PASSWORD','CHANGE_ME')
SMTP_HOST=os.getenv('SMTP_HOST',''); SMTP_PORT=int(os.getenv('SMTP_PORT','587')); SMTP_USER=os.getenv('SMTP_USER',''); SMTP_PASS=os.getenv('SMTP_PASSWORD',''); MAIL_FROM=os.getenv('MAIL_FROM',SMTP_USER)
def conn():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init():
 c=conn(); c.execute('''CREATE TABLE IF NOT EXISTS visitors(id INTEGER PRIMARY KEY AUTOINCREMENT,ticket INTEGER UNIQUE,name TEXT,menu TEXT,contact_method TEXT,email TEXT,line_user_id TEXT,status TEXT DEFAULT "waiting",created_at TEXT DEFAULT CURRENT_TIMESTAMP)'''); c.execute('''CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)'''); c.execute('INSERT OR IGNORE INTO settings VALUES("next_ticket","1")'); c.commit(); c.close()
def next_ticket(c):
 n=int(c.execute('SELECT value FROM settings WHERE key="next_ticket"').fetchone()['value']); c.execute('UPDATE settings SET value=? WHERE key="next_ticket"',(n+1,)); return n
def waiting_count(c): return c.execute('SELECT COUNT(*) n FROM visitors WHERE status="waiting"').fetchone()['n']
def send_line(uid,text):
 if not TOKEN or not uid:return False
 r=requests.post('https://api.line.me/v2/bot/message/push',headers={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'},json={'to':uid,'messages':[{'type':'text','text':text}]},timeout=15); return r.ok
def send_mail(to,text):
 if not all([SMTP_HOST,SMTP_USER,SMTP_PASS,to]):return False
 m=EmailMessage();m['From']=MAIL_FROM;m['To']=to;m['Subject']='Estoy マルシェ 順番のお知らせ';m.set_content(text)
 with smtplib.SMTP(SMTP_HOST,SMTP_PORT,timeout=20) as s:s.starttls();s.login(SMTP_USER,SMTP_PASS);s.send_message(m)
 return True
def notify(v,text): return send_line(v['line_user_id'],text) if v['contact_method']=='line' else send_mail(v['email'],text)
@app.get('/')
def home(): return render_template('index.html',line_enabled=bool(LID and CALLBACK))
@app.post('/register')
def register():
 name=request.form.get('name','').strip();menu=request.form.get('menu','').strip();method=request.form.get('contact_method','');email=request.form.get('email','').strip() or None
 if not name or not menu or method not in ('line','email') or (method=='email' and not email):return render_template('error.html',message='入力内容を確認してください。'),400
 c=conn();t=next_ticket(c);c.execute('INSERT INTO visitors(ticket,name,menu,contact_method,email) VALUES(?,?,?,?,?)',(t,name,menu,method,email));c.commit();c.close();session['oauth_state']=secrets.token_urlsafe(24);session['ticket']=t
 return redirect(url_for('line_login',ticket=t)) if method=='line' else redirect(url_for('status',ticket=t))
@app.get('/line-login/<int:ticket>')
def line_login(ticket):
 if not(LID and CALLBACK):return render_template('error.html',message='LINE連携はまだ設定されていません。メール受付をご利用ください。'),503
 state=session['oauth_state'];p={'response_type':'code','client_id':LID,'redirect_uri':CALLBACK,'state':state,'scope':'profile openid','bot_prompt':'aggressive'}
 return redirect('https://access.line.me/oauth2/v2.1/authorize?'+urlencode(p))
@app.get('/line/callback')
def callback():
 if request.args.get('state')!=session.get('oauth_state'):return render_template('error.html',message='LINEログイン確認に失敗しました。'),400
 code=request.args.get('code');ticket=session.get('ticket')
 r=requests.post('https://api.line.me/oauth2/v2.1/token',data={'grant_type':'authorization_code','code':code,'redirect_uri':CALLBACK,'client_id':LID,'client_secret':LSECRET},timeout=15)
 if not r.ok:return render_template('error.html',message='LINEとの接続に失敗しました。'),502
 at=r.json()['access_token'];p=requests.get('https://api.line.me/v2/profile',headers={'Authorization':'Bearer '+at},timeout=15)
 if not p.ok:return render_template('error.html',message='LINEプロフィールを取得できませんでした。'),502
 uid=p.json()['userId'];c=conn();c.execute('UPDATE visitors SET line_user_id=? WHERE ticket=?',(uid,ticket));c.commit();c.close();return redirect(url_for('status',ticket=ticket))
@app.get('/status/<int:ticket>')
def status(ticket):
 c=conn();v=c.execute('SELECT * FROM visitors WHERE ticket=?',(ticket,)).fetchone();pos=None
 if v and v['status']=='waiting':pos=c.execute('SELECT COUNT(*) n FROM visitors WHERE status="waiting" AND created_at<=?',(v['created_at'],)).fetchone()['n']
 c.close();
 if not v:return render_template('error.html',message='受付番号が見つかりません。'),404
 return render_template('status.html',visitor=v,position=pos,oa_url=OA_URL)
@app.route('/admin/login',methods=['GET','POST'])
def login():
 if request.method=='POST' and request.form.get('password')==ADMIN:session['admin']=1;return redirect('/admin')
 return render_template('login.html')
def auth():return session.get('admin')==1
@app.get('/admin')
def admin():
 if not auth():return redirect('/admin/login')
 c=conn();rows=c.execute('SELECT * FROM visitors ORDER BY id DESC').fetchall();n=waiting_count(c);c.close();return render_template('admin.html',rows=rows,n=n)
@app.post('/admin/call-next')
def call_next():
 if not auth():return jsonify(ok=False),403
 c=conn();v=c.execute('SELECT * FROM visitors WHERE status="waiting" ORDER BY id LIMIT 1').fetchone()
 if not v:c.close();return jsonify(ok=False,message='待っている方はいません。')
 c.execute('UPDATE visitors SET status="called" WHERE id=?',(v['id'],));c.commit();left=waiting_count(c);c.close();text=f'🗿 Estoy マルシェ\n{v["name"]}さん、もうすぐ順番です！\n現在、待ちはあと{left}組です。\n5〜10分ほどでブースへお越しください。';return jsonify(ok=True,ticket=v['ticket'],notified=notify(v,text))
@app.post('/admin/complete/<int:ticket>')
def complete(ticket):
 if not auth():return jsonify(ok=False),403
 c=conn();c.execute('UPDATE visitors SET status="completed" WHERE ticket=?',(ticket,));c.commit();c.close();return jsonify(ok=True)
@app.get('/admin/export.csv')
def export_csv():
 if not auth():return jsonify(ok=False),403
 c=conn();rows=c.execute('SELECT ticket,name,menu,contact_method,email,line_user_id,status,created_at FROM visitors ORDER BY id').fetchall();c.close();s=io.StringIO();w=csv.writer(s);w.writerow(['受付番号','名前','メニュー','連絡方法','メール','LINEユーザーID','状態','受付日時']);[w.writerow(list(r)) for r in rows];return send_file(io.BytesIO(s.getvalue().encode('utf-8-sig')),mimetype='text/csv',as_attachment=True,download_name='estoy_marche_customers.csv')
init()
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.getenv('PORT','5000')))
