import os, json, datetime, logging, io
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Request, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn, requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from PIL import Image, ImageDraw, ImageFont
import qrcode
VERSION = "0.1.15"; APP_PORT = 8091; HA_URL = "http://supervisor/core/api"
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
def read_options()->Dict[str,Any]:
    try:
        with open("/data/options.json","r",encoding="utf-8") as f: return json.load(f)
    except Exception as e:
        logging.error(f"options.json error: {e}"); return {}
def get_creds(p): return service_account.Credentials.from_service_account_file(p, scopes=["https://www.googleapis.com/auth/spreadsheets"])
def svc(c): return build("sheets","v4",credentials=c,cache_discovery=False)
def read_tab(s, sid, tab):
    try: return s.spreadsheets().values().get(spreadsheetId=sid, range=f"{tab}!A:Z").execute().get("values",[])
    except Exception as e: logging.error(f"tab {tab} error: {e}"); return []
def to_dicts(rows):
    if not rows: return []
    h=rows[0]; return [{h[i]: (r[i] if i<len(r) else "") for i in range(len(h))} for r in rows[1:]]
def find_product(s, sid, pid=None, sid_short=None):
    for p in to_dicts(read_tab(s, sid, "Products")):
        if pid and p.get("product_id")==pid: return p
        if sid_short and p.get("short_id")==sid_short: return p
    return {}
def reseller_price(s, sid, rid, pid, on=None):
    rows = to_dicts(read_tab(s, sid, "ResellerPricing")); on = on or datetime.date.today()
    best = {}
    for r in rows:
        if r.get("reseller_id")!=rid or r.get("product_id")!=pid: continue
        try:
            vf=datetime.date.fromisoformat(r.get("valid_from","1970-01-01")); vt=datetime.date.fromisoformat(r.get("valid_to","9999-12-31"))
        except: vf,vt=datetime.date(1970,1,1),datetime.date(9999,12,31)
        if vf<=on<=vt and (not best or vf>=datetime.date.fromisoformat(best.get("valid_from","1970-01-01"))): best=r
    return best
def fire_event(name, payload):
    tok=os.environ.get("SUPERVISOR_TOKEN"); 
    if not tok: logging.warning("SUPERVISOR_TOKEN missing"); return
    try:
        r=requests.post(f"{HA_URL}/events/{name}", headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"}, data=json.dumps(payload), timeout=5)
        logging.info(f"event {name} -> {r.status_code}")
    except Exception as e: logging.error(f"event error: {e}")
app=FastAPI(); app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
@app.get("/health")
def health(): return {"status":"ok","version":VERSION,"port":APP_PORT}
@app.get("/pos/stock")
def stock(reseller_id: str = Query(None)):
    o=read_options(); s=svc(get_creds(o["service_account_json"]))
    items=to_dicts(read_tab(s,o["google_sheet_id"],"Stock"))
    return [x for x in items if (not reseller_id or x.get("reseller_id")==reseller_id)]
@app.post("/pos/sale")
async def sale(req: Request):
    p=await req.json(); rid=p.get("reseller_id",""); pid=p.get("product_id"); sid=p.get("short_id")
    qty=int(p.get("qty",1)); cid=p.get("customer_id","C-000"); pay=p.get("payment_method","cash")
    if not pid and not sid: raise HTTPException(400,"product_id or short_id required")
    o=read_options(); s=svc(get_creds(o["service_account_json"])); prod=find_product(s,o["google_sheet_id"],pid,sid)
    if not prod: raise HTTPException(404,"Product not found")
    pid=prod.get("product_id"); sid=prod.get("short_id"); rp=reseller_price(s,o["google_sheet_id"],rid,pid)
    try: price=float(rp.get("price") or prod.get("base_price") or 0)
    except: price=float(prod.get("base_price") or 0)
    total=price*qty; row=[datetime.datetime.now().isoformat(),"","",cid,pid,sid,qty,price,rp.get("commission_pct",0),total,pay]
    try:
        s.spreadsheets().values().append(spreadsheetId=o["google_sheet_id"],range="Sales!A:Z",valueInputOption="RAW",body={"values":[row]}).execute()
    except Exception as e: logging.error(f"append error: {e}"); raise HTTPException(500,"Failed to log sale")
    fire_event(o.get("ha_event","pos_sale"),{"reseller_id":rid,"customer_id":cid,"total":total,"product_id":pid,"qty":qty})
    return {"status":"ok","total":total}
@app.get("/pos/label/{product_id}")
def label(product_id: str):
    o=read_options(); s=svc(get_creds(o["service_account_json"]))
    prod = next((p for p in to_dicts(read_tab(s,o["google_sheet_id"],"Products")) if p.get("product_id")==product_id), None)
    if not prod: raise HTTPException(404,"Product not found")
    text=f"{prod.get('short_id','')} - {prod.get('name','')}\nSize: {prod.get('package_size','')}\nPrice: {prod.get('base_price','')} NOK\nProducer: {prod.get('producer','')}"
    qr=qrcode.QRCode(box_size=4,border=2); qr.add_data(json.dumps({"product_id":product_id,"short_id":prod.get('short_id')})); qr.make(fit=True)
    from PIL import Image; from PIL import ImageDraw; from PIL import ImageFont
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img=Image.new("RGB",(400,300),"white"); d=ImageDraw.Draw(img); d.text((10,10),text,fill="black",font=ImageFont.load_default()); img.paste(qr_img,(250,50))
    buf=io.BytesIO(); img.save(buf,format="PNG"); buf.seek(0); return Response(content=buf.getvalue(),media_type="image/png")
if __name__=="__main__": uvicorn.run("run:app",host="0.0.0.0",port=APP_PORT)
