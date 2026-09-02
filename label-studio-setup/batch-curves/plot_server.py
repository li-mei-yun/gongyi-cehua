"""Local-only interactive torque-angle plot server for Label Studio CE."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
DB = BASE / 'package-scu2020/conversion_cache.sqlite3'

HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<style>html,body{margin:0;background:#fff;font:14px system-ui;color:#222}#wrap{position:relative;width:100%;height:640px}canvas{width:100%;height:100%;display:block}#tip{position:absolute;display:none;background:#111;color:#fff;padding:6px 8px;border-radius:4px;pointer-events:none;white-space:nowrap}#help{position:absolute;right:12px;top:8px;background:#fffdd9;padding:4px 7px;border:1px solid #ddd}</style></head><body><div id="wrap"><canvas id="c"></canvas><div id="tip"></div><div id="help">滚轮缩放 · 拖动平移 · 双击复位</div></div>
<script>"use strict";const A=__ANGLE__,T=__TORQUE__,ID=__ID__;const c=document.getElementById('c'),ctx=c.getContext('2d'),tip=document.getElementById('tip');let home,view,drag=null;
function extent(x){let a=Infinity,b=-Infinity;for(const v of x){if(v<a)a=v;if(v>b)b=v}if(a===b){a-=1;b+=1}return[a,b]}
function reset(){let[x0,x1]=extent(A),[y0,y1]=extent(T),px=(x1-x0)*.04,py=(y1-y0)*.08;home={x0:x0-px,x1:x1+px,y0:y0-py,y1:y1+py};view={...home};draw()}
function size(){let d=devicePixelRatio||1,w=c.clientWidth,h=c.clientHeight;c.width=Math.round(w*d);c.height=Math.round(h*d);ctx.setTransform(d,0,0,d,0,0);return[w,h]}
function sx(x,w){return 70+(x-view.x0)/(view.x1-view.x0)*(w-90)}function sy(y,h){return h-55-(y-view.y0)/(view.y1-view.y0)*(h-85)}
function nice(a,b,n=7){let s=(b-a)/n,p=10**Math.floor(Math.log10(s)),q=s/p,m=q>=5?5:q>=2?2:1,step=m*p,out=[];for(let v=Math.ceil(a/step)*step;v<=b+step*.1;v+=step)out.push(v);return out}
function draw(){const[w,h]=size();ctx.clearRect(0,0,w,h);ctx.strokeStyle='#d0d0d0';ctx.lineWidth=1;ctx.setLineDash([5,4]);ctx.font='12px system-ui';ctx.fillStyle='#333';for(const x of nice(view.x0,view.x1)){let u=sx(x,w);ctx.beginPath();ctx.moveTo(u,20);ctx.lineTo(u,h-55);ctx.stroke();ctx.fillText(Number(x.toFixed(6)).toString(),u-12,h-34)}for(const y of nice(view.y0,view.y1)){let v=sy(y,h);ctx.beginPath();ctx.moveTo(70,v);ctx.lineTo(w-20,v);ctx.stroke();ctx.fillText(Number(y.toFixed(6)).toString(),8,v+4)}ctx.setLineDash([]);ctx.strokeStyle='#1f77b4';ctx.lineWidth=1.6;ctx.beginPath();for(let i=0;i<A.length;i++){let x=sx(A[i],w),y=sy(T[i],h);i?ctx.lineTo(x,y):ctx.moveTo(x,y)}ctx.stroke();ctx.fillStyle='#111';ctx.font='18px system-ui';ctx.textAlign='center';ctx.fillText('Result ID: '+ID,w/2,18);ctx.font='15px system-ui';ctx.fillText('角度（度）',w/2,h-8);ctx.save();ctx.translate(18,h/2);ctx.rotate(-Math.PI/2);ctx.fillText('扭矩（N·m）',0,0);ctx.restore();ctx.textAlign='left'}
function point(e){let r=c.getBoundingClientRect();return[e.clientX-r.left,e.clientY-r.top]}
c.addEventListener('wheel',e=>{e.preventDefault();let[x,y]=point(e),w=c.clientWidth,h=c.clientHeight,ax=view.x0+(x-70)/(w-90)*(view.x1-view.x0),ay=view.y1-(y-20)/(h-85)*(view.y1-view.y0),k=e.deltaY<0?.82:1.22;view={x0:ax+(view.x0-ax)*k,x1:ax+(view.x1-ax)*k,y0:ay+(view.y0-ay)*k,y1:ay+(view.y1-ay)*k};draw()},{passive:false});
c.addEventListener('pointerdown',e=>{drag=[...point(e),{...view}];c.setPointerCapture(e.pointerId)});c.addEventListener('pointermove',e=>{let[x,y]=point(e),w=c.clientWidth,h=c.clientHeight;if(drag){let dx=(x-drag[0])/(w-90)*(drag[2].x1-drag[2].x0),dy=(y-drag[1])/(h-85)*(drag[2].y1-drag[2].y0);view={x0:drag[2].x0-dx,x1:drag[2].x1-dx,y0:drag[2].y0+dy,y1:drag[2].y1+dy};draw();return}let best=-1,bd=144;for(let i=0;i<A.length;i++){let dx=sx(A[i],w)-x,dy=sy(T[i],h)-y,d=dx*dx+dy*dy;if(d<bd){bd=d;best=i}}if(best<0){tip.style.display='none'}else{tip.style.display='block';tip.style.left=(x+12)+'px';tip.style.top=(y+12)+'px';tip.textContent=`点 ${best+1}　角度 ${A[best].toFixed(3)}°　扭矩 ${T[best].toFixed(3)} N·m`}});c.addEventListener('pointerup',()=>drag=null);c.addEventListener('pointercancel',()=>drag=null);c.addEventListener('dblclick',reset);addEventListener('resize',draw);reset();</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        match = re.fullmatch(r'/plot/([0-9]+)', path)
        if path == '/health':
            return self.send_body(200, b'tightening-curve-plot-v1', 'text/plain; charset=utf-8')
        if not match:
            return self.send_body(404, b'Not found', 'text/plain; charset=utf-8')
        filename = match.group(1) + '.xlsx'
        with sqlite3.connect(f'file:{DB.as_posix()}?mode=ro', uri=True) as db:
            row = db.execute('SELECT payload FROM tasks WHERE filename=?', (filename,)).fetchone()
        if not row:
            return self.send_body(404, b'Unknown curve', 'text/plain; charset=utf-8')
        task = json.loads(row[0])
        series = task['data']['series']
        body = (HTML.replace('__ANGLE__', json.dumps(series['angle_deg'],separators=(',',':')))
                    .replace('__TORQUE__', json.dumps(series['torque_nm'],separators=(',',':')))
                    .replace('__ID__', json.dumps(task['data']['curve_id']))).encode('utf-8')
        self.send_body(200, body, 'text/html; charset=utf-8')
    def send_body(self, status, body, content_type):
        self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'")
        self.end_headers();self.wfile.write(body)
    def log_message(self, fmt, *args):
        print('%s - %s' % (self.address_string(), fmt%args), flush=True)

if __name__ == '__main__':
    if not DB.is_file(): raise SystemExit(f'Missing read-only curve database: {DB}')
    server=ThreadingHTTPServer(('127.0.0.1',8091),Handler)
    print('Torque-angle plot server: http://127.0.0.1:8091 (Ctrl+C to stop)',flush=True)
    server.serve_forever()
