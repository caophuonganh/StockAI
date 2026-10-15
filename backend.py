# -*- coding: utf-8 -*-
"""Stock AI GitHub backend: news + AI + technical signals + Telegram + JSON dashboard."""
import os, json, re, html, urllib.request, urllib.parse, urllib.error
import xml.etree.ElementTree as ET
import unicodedata
from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
DASH=DATA/'dashboard.json'
DEFAULT_TICKERS=['APG','MSR','VPB','VPG','PET','SGR','VPI','HHP']

def env(k,d=''):
    v=os.getenv(k); return d if v is None else v.strip()

def tickers():
    raw=env('STOCK_TICKERS',','.join(DEFAULT_TICKERS)); out=[]
    for x in re.split(r'[,;\s]+',raw.upper()):
        if re.fullmatch(r'[A-Z0-9]{2,10}',x) and x not in out: out.append(x)
    return out or DEFAULT_TICKERS[:]

def get(url,timeout=20):
    req=urllib.request.Request(url,headers={'User-Agent':'StockAI-GitHub/2.0'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return r.read()

def norm(s):
    s=unicodedata.normalize('NFKD',(s or '').lower())
    s=''.join(c for c in s if not unicodedata.combining(c))
    s=re.sub(r'[^a-z0-9]+',' ',s); return re.sub(r'\s+',' ',s).strip()

def dup(title,old):
    a=norm(title)
    for x in old:
        b=norm(x)
        if a==b:return True
        sa,sb=set(a.split()),set(b.split())
        if min(len(sa),len(sb))>=5:
            ov=len(sa&sb)/max(1,min(len(sa),len(sb)))
            if ov>=.90 or SequenceMatcher(None,a,b).ratio()>=.92:return True
    return False

def news(ticker):
    q=urllib.parse.quote(f'"{ticker}" cổ phiếu OR chứng khoán')
    root=ET.fromstring(get(f'https://news.google.com/rss/search?q={q}&hl=vi&gl=VN&ceid=VN:vi',15)); out=[]
    for it in root.findall('./channel/item')[:12]:
        title=(it.findtext('title') or '').strip(); link=(it.findtext('link') or '').strip()
        if not title or not link:continue
        desc=html.unescape(it.findtext('description') or ''); desc=re.sub(r'<[^>]+>',' ',desc); desc=re.sub(r'\s+',' ',desc).strip()
        out.append({'ticker':ticker,'title':title,'link':link,'source':(it.findtext('source') or 'Google News').strip(),'published':(it.findtext('pubDate') or '').strip(),'summary':desc[:1200]})
    return out

def quote(ticker):
    try:
        u='https://query1.finance.yahoo.com/v8/finance/chart/'+urllib.parse.quote(ticker+'.VN',safe='.')+'?range=1d&interval=5m&includePrePost=false'
        r=(json.loads(get(u,15).decode()).get('chart',{}).get('result') or [None])[0]
        if not r:raise RuntimeError('Yahoo không trả dữ liệu')
        meta=r.get('meta',{}); q=(r.get('indicators',{}).get('quote') or [{}])[0]
        opens=[x for x in q.get('open',[]) if isinstance(x,(int,float)) and x>0]; cur=meta.get('regularMarketPrice')
        if cur is None:
            cs=[x for x in q.get('close',[]) if isinstance(x,(int,float)) and x>0]; cur=cs[-1] if cs else None
        op=opens[0] if opens else None; pct=((cur-op)/op*100) if op and cur else None
        return {'open':op,'current':cur,'change_pct':pct,'checked_at':datetime.now().isoformat(timespec='seconds')}
    except Exception as e:return {'open':None,'current':None,'change_pct':None,'error':str(e)}

def daily(ticker):
    u='https://query1.finance.yahoo.com/v8/finance/chart/'+urllib.parse.quote(ticker+'.VN',safe='.')+'?range=120d&interval=1d&includePrePost=false'
    r=(json.loads(get(u,15).decode()).get('chart',{}).get('result') or [None])[0]
    if not r:raise RuntimeError(f'{ticker}: không có dữ liệu')
    q=(r.get('indicators',{}).get('quote') or [{}])[0]; rows=[]
    for h,l,c,v in zip(q.get('high') or [],q.get('low') or [],q.get('close') or [],q.get('volume') or []):
        if all(isinstance(x,(int,float)) for x in (h,l,c,v)) and c>0:rows.append((float(h),float(l),float(c),float(v)))
    if len(rows)<35:raise RuntimeError(f'{ticker}: chỉ có {len(rows)} phiên')
    return rows

def ema(v,p):
    if len(v)<p:return [None]*len(v)
    o=[None]*len(v); prev=sum(v[:p])/p; o[p-1]=prev; a=2/(p+1)
    for i in range(p,len(v)):prev=(v[i]-prev)*a+prev;o[i]=prev
    return o

def rsi(v,p=14):
    o=[None]*len(v)
    if len(v)<=p:return o
    g=[max(v[i]-v[i-1],0) for i in range(1,len(v))]; l=[max(v[i-1]-v[i],0) for i in range(1,len(v))]
    ag=sum(g[:p])/p; al=sum(l[:p])/p
    o[p]=100 if al==0 and ag>0 else (0 if al==0 else 100-100/(1+ag/al))
    for i in range(p+1,len(v)):
        ag=((p-1)*ag+g[i-1])/p; al=((p-1)*al+l[i-1])/p
        o[i]=100 if al==0 and ag>0 else (0 if al==0 else 100-100/(1+ag/al))
    return o

def mfi(h,l,c,v,p=14):
    tp=[(a+b+x)/3 for a,b,x in zip(h,l,c)]; mf=[tp[i]*v[i] for i in range(len(tp))]; pos=[0]*len(tp);neg=[0]*len(tp);o=[None]*len(tp)
    for i in range(1,len(tp)):
        if tp[i]>tp[i-1]:pos[i]=mf[i]
        elif tp[i]<tp[i-1]:neg[i]=mf[i]
    for i in range(p,len(tp)):
        a=sum(pos[i-p+1:i+1]);b=sum(neg[i-p+1:i+1]);o[i]=100 if b==0 and a>0 else (0 if b==0 else 100-100/(1+a/b))
    return o

def stoch(h,l,c,p=14,s=3):
    raw=[None]*len(c);o=[None]*len(c)
    for i in range(p-1,len(c)):
        hh=max(h[i-p+1:i+1]);ll=min(l[i-p+1:i+1]);raw[i]=50 if hh==ll else 100*(c[i]-ll)/(hh-ll)
    for i in range(p+s-2,len(c)):
        a=raw[i-s+1:i+1]
        if all(x is not None for x in a):o[i]=sum(a)/s
    return o

def technical(ticker):
    rows=daily(ticker);h=[x[0] for x in rows];l=[x[1] for x in rows];c=[x[2] for x in rows];v=[x[3] for x in rows]
    R=rsi(c);M=mfi(h,l,c,v);S=stoch(h,l,c);E5,E10,E20=ema(c,5),ema(c,10),ema(c,20);E12,E26=ema(c,12),ema(c,26);MAC=[a-b if a is not None and b is not None else None for a,b in zip(E12,E26)];VM=[sum(v[i-19:i+1])/20 if i>=19 else None for i in range(len(v))]
    return {'ticker':ticker,'price':c[-1],'rsi':R[-1],'rsi_prev':R[-2],'mfi':M[-1],'mfi_prev':M[-2],'stochk':S[-1],'stochk_prev':S[-2],'macd':MAC[-1],'macd_prev':MAC[-2],'ema5':E5[-1],'ema5_prev':E5[-2],'ema10':E10[-1],'ema10_prev':E10[-2],'ema20':E20[-1],'ema20_prev':E20[-2],'volume':v[-1],'volume_ma20':VM[-1],'checked_at':datetime.now().isoformat(timespec='seconds')}

def signals(t):
    keys=['rsi','rsi_prev','mfi','mfi_prev','stochk','stochk_prev','macd','macd_prev','volume_ma20','ema5','ema5_prev','ema10','ema10_prev','ema20','ema20_prev']
    if any(t.get(k) is None for k in keys):return []
    buy4=t['volume_ma20']>300000 and t['macd']>t['macd_prev'] and t['rsi']>t['rsi_prev'] and t['rsi']<40 and t['mfi']>t['mfi_prev'] and t['mfi']<40 and t['stochk']>t['stochk_prev'] and t['stochk']<40
    ema_buy=t['ema5']>t['ema10'] and t['ema5_prev']<=t['ema10_prev'] and t['ema10']>t['ema20'] and t['ema10_prev']<=t['ema20_prev']
    return (['BẮT ĐÁY'] if buy4 else [])+(['MUA MẠNH'] if ema_buy else [])

def ai(prompt):
    provider=env('AI_PROVIDER','gemini').lower()
    if provider=='gemini':
        key=env('GEMINI_API_KEY'); model=env('GEMINI_MODEL','gemini-2.5-flash')
        if not key:raise RuntimeError('Thiếu GEMINI_API_KEY')
        u='https://generativelanguage.googleapis.com/v1beta/models/'+urllib.parse.quote(model,safe='')+':generateContent?key='+urllib.parse.quote(key,safe='')
        body=json.dumps({'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'temperature':.2}}).encode();req=urllib.request.Request(u,data=body,headers={'Content-Type':'application/json'},method='POST')
        with urllib.request.urlopen(req,timeout=90) as r:d=json.loads(r.read().decode())
        return '\n'.join(x.get('text','') for x in ((d.get('candidates') or [{}])[0].get('content',{}).get('parts') or []) if x.get('text')).strip()
    key=env('OPENAI_API_KEY');model=env('OPENAI_MODEL','gpt-4.1-mini')
    if not key:raise RuntimeError('Thiếu OPENAI_API_KEY')
    body=json.dumps({'model':model,'input':prompt}).encode();req=urllib.request.Request('https://api.openai.com/v1/responses',data=body,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=90) as r:d=json.loads(r.read().decode())
    if d.get('output_text'):return d['output_text'].strip()
    out=[]
    for b in d.get('output',[]):
        for c in b.get('content',[]):
            if c.get('type')=='output_text':out.append(c.get('text',''))
    return '\n'.join(out).strip()

def telegram(text):
    if env('TELEGRAM_ENABLED','0').lower() not in ('1','true','yes','on'):return 'disabled'
    token=env('TELEGRAM_BOT_TOKEN');chat=env('TELEGRAM_CHAT_ID')
    if not token or not chat:return 'not_configured'
    if not re.fullmatch(r'\d+:[A-Za-z0-9_-]+',token):raise RuntimeError('TELEGRAM_BOT_TOKEN sai định dạng')
    if not re.fullmatch(r'-?\d+',chat):raise RuntimeError('TELEGRAM_CHAT_ID phải là số')
    u=f'https://api.telegram.org/bot{token}/sendMessage';body=json.dumps({'chat_id':chat,'text':text[:3900],'disable_web_page_preview':True},ensure_ascii=False).encode();req=urllib.request.Request(u,data=body,headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=20) as r:d=json.loads(r.read().decode())
    if not d.get('ok'):raise RuntimeError(str(d))
    return 'sent'

def classify(title,analysis):
    t=norm(title);a=norm(analysis)
    cat='Cổ tức' if any(x in t for x in ['co tuc','tra co tuc','chia co tuc']) else ('BCTC' if any(x in t for x in ['bao cao tai chinh','bctc','ket qua kinh doanh','loi nhuan quy']) else 'Tin khác')
    important=('rat quan trong' in a or 'uu tien cao' in a)
    warn=any(x in t or x in a for x in ['canh bao','rui ro','bi dieu tra','khoi to','xu phat','huy niem yet','vo no','mat kha nang thanh toan','lo nang'])
    return cat,('Rất quan trọng' if important else 'Bình thường'),warn

def compact(s,n=650):
    s=re.sub(r'\s+',' ',s or '').strip();return s if len(s)<=n else s[:n].rsplit(' ',1)[0]+'…'

def analyze_news(item,q):
    return ai(f'''Bạn là chuyên viên phân tích tin tức chứng khoán Việt Nam. Không bịa dữ liệu.\nMã: {item['ticker']}\nTiêu đề: {item['title']}\nNguồn: {item['source']}\nNgày: {item['published']}\nMô tả: {item['summary']}\nGiá mở cửa: {q.get('open')}\nGiá hiện tại: {q.get('current')}\nBiến động: {q.get('change_pct')}\nTrả lời tiếng Việt tối đa 900 ký tự theo: 1) Tóm tắt; 2) Tác động; 3) Chiều hướng Tích cực/Trung tính/Tiêu cực; 4) Mức độ tác động Cao/Vừa/Thấp; 5) MỨC ĐỘ QUAN TRỌNG: Rất quan trọng/Bình thường; 6) Điều cần kiểm chứng; 7) Kịch bản ngắn hạn. Không cam kết giá.''')

def technical_alert(t, sigs):
    if not sigs:return None
    sig='BẮT ĐÁY + MUA MẠNH' if len(sigs)==2 else sigs[0]
    try:report=ai(f'''Bạn là AI phân tích kỹ thuật cổ phiếu Việt Nam. Máy tính đã xác nhận tín hiệu {sig}; không thay đổi điều kiện. Mã {t['ticker']}, giá {t['price']:.2f}; RSI14 {t['rsi']:.2f} trước {t['rsi_prev']:.2f}; MFI14 {t['mfi']:.2f} trước {t['mfi_prev']:.2f}; StochK14,3 {t['stochk']:.2f} trước {t['stochk_prev']:.2f}; MACD {t['macd']:.4f} trước {t['macd_prev']:.4f}; EMA5 {t['ema5']:.2f}; EMA10 {t['ema10']:.2f}; EMA20 {t['ema20']:.2f}; Volume {t['volume']:.0f}; MA20 {t['volume_ma20']:.0f}. Giải thích ngắn gọn động lượng và rủi ro, kết luận Tín hiệu xác nhận/Cần thận trọng, tối đa 700 ký tự.''')
    except Exception as e:report='AI lỗi: '+str(e)
    msg=f'''🚨 STOCK AI – {sig}\n\n{t['ticker']} | Giá {t['price']:.2f}\nRSI {t['rsi']:.1f} ↑ | MFI {t['mfi']:.1f} ↑ | StochK {t['stochk']:.1f} ↑\nMACD {t['macd']:.4f} ↑\nEMA5 {t['ema5']:.2f} | EMA10 {t['ema10']:.2f} | EMA20 {t['ema20']:.2f}\nVol {t['volume']:,.0f} | MA20 {t['volume_ma20']:,.0f}\n\n🤖 AI: {compact(report)}'''
    try:tg=telegram(msg)
    except Exception as e:tg='error: '+str(e)
    return {'ticker':t['ticker'],'signal':sig,'price':t['price'],'ai_analysis':report,'telegram':tg,'created_at':datetime.now().isoformat(timespec='seconds')}

def scan_once():
    started=datetime.now();ts=tickers();prev={}
    if DASH.exists():
        try:prev=json.loads(DASH.read_text(encoding='utf-8'))
        except Exception:prev={}
    old=prev.get('news',[]);old_titles=[x.get('title','') for x in old];found=0;new=[];quotes={};tech=[];alerts=[];errors=[]
    print('STOCK AI SCAN');print('Tickers:',','.join(ts))
    def one(t):return t,news(t),quote(t)
    with ThreadPoolExecutor(max_workers=min(8,len(ts))) as pool:
        for f in as_completed([pool.submit(one,t) for t in ts]):
            try:
                t,items,q=f.result();quotes[t]=q;found+=len(items);local=old_titles[:]
                for item in items:
                    if dup(item['title'],local):continue
                    item.update({'fetched_at':datetime.now().isoformat(timespec='seconds'),'price_open':q.get('open'),'price_current':q.get('current'),'price_change_pct':q.get('change_pct')})
                    try:item['analysis']=analyze_news(item,q);item['sentiment']='Tiêu cực' if 'tiêu cực' in item['analysis'].lower() else ('Tích cực' if 'tích cực' in item['analysis'].lower() else 'Trung tính')
                    except Exception as e:item['analysis']='AI chưa phân tích: '+str(e);item['sentiment']='Chưa phân tích'
                    item['category'],item['importance'],item['warning']=classify(item['title'],item['analysis']);new.append(item);local.append(item['title'])
            except Exception as e:errors.append('News/quote: '+str(e))
    for item in new:
        if item.get('warning') or item.get('importance')=='Rất quan trọng':
            try:item['telegram']=telegram('\n'.join(['🚨 CẢNH BÁO' if item.get('warning') else '🟣 RẤT QUAN TRỌNG',f"{item['ticker']} | {item['sentiment']}",item['title'],'AI: '+compact(item.get('analysis','')),item.get('link','')]))
            except Exception as e:item['telegram']='error: '+str(e)
    seen=set();allnews=[]
    for item in new+old:
        key=item.get('link') or norm(item.get('title',''))
        if key in seen:continue
        seen.add(key);allnews.append(item)
    allnews=allnews[:300]
    for t in ts:
        try:
            x=technical(t);tech.append(x);a=technical_alert(x,signals(x))
            if a:alerts.append(a)
        except Exception as e:errors.append(f'Technical {t}: {e}')
    status='OK' if not errors else 'PARTIAL';done=datetime.now();dashboard={'generated_at':done.isoformat(timespec='seconds'),'status':status,'tickers':ts,'summary':{'news_found':found,'news_new':len(new),'technical_checked':len(tech),'signals':len(alerts)},'quotes':quotes,'technical':tech,'technical_alerts':alerts[:100],'news':allnews,'errors':errors[:50]}
    DASH.write_text(json.dumps(dashboard,ensure_ascii=False,indent=2),encoding='utf-8');print('STOCK AI SCAN FINISHED');print(json.dumps(dashboard['summary'],ensure_ascii=False));return dashboard

if __name__=='__main__':scan_once()
