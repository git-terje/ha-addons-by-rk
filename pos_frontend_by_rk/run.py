import os, json, logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
import uvicorn
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
PORT=8095; app=FastAPI()
def read_options():
    try:
        with open("/data/options.json","r",encoding="utf-8") as f: return json.load(f)
    except Exception: return {"backend_url":"http://supervisor:8091"}
@app.get("/config.js")
def config_js():
    o=read_options(); return f"window.config={{backend_url:'{o.get('backend_url','http://supervisor:8091')}'}}"
@app.get("/") 
def root(): return RedirectResponse(url="/index.html")
app.mount("/", StaticFiles(directory="static", html=True), name="static")
if __name__=="__main__": uvicorn.run("run:app", host="0.0.0.0", port=PORT)
