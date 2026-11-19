"""Isolated UI smoke check: synthetic data, no Muse requests or real user files."""
import asyncio
import base64
import json
import os
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import httpx
from agent.services.muse_gateway import chrome
from muse2api.drivers.browser.chromium import ChromiumProcess
from muse2api.drivers.browser.cdp import CDPSession

OUT = ROOT / 'windows' / 'qa-1.2.0'
OUT.mkdir(exist_ok=True)
app = FastAPI()
app.mount('/assets', StaticFiles(directory=ROOT / 'dashboard/dist/assets'))
rows = [dict(id='scene'+str(i), project_id='p1',queue_id='q1', ordinal=i,number=i,title='Phong cảnh bình minh '+str(i), image_prompt='A quiet scenic landscape with soft golden sunlight, distant hills and calm water. No people.',video_prompt='Slow pan across the landscape.', status=status,camera_label='Góc pan',video=None,error='Kết nối chậm; sẽ thử lại sau lượt chính.' if status=='error' else None) for i,status in enumerate(['completed','video','pending','error'],1)]
@app.get('/api/muse/status')
async def status():
 return dict(running=True,ready=True,driver='browser',available=7,saved_accounts=10,performance=dict(preset='balanced',max_accounts=3,videos_per_account=2,max_videos=6,automatic=True),scheduling=dict(active_accounts=3,adaptive=dict(enabled=True,target_jobs=2,ceiling=6,active_jobs=3,paused=False,cpu_percent=91,ram_percent=88,free_gb=1.4,reason='CPU/RAM cao: giảm luồng mới; giữ nguyên tác vụ đã gửi.')),quota_accounts=['Muse 2'])
@app.get('/api/muse/accounts')
async def accounts():
 return [dict(id='acc_A',label='Muse 1',enabled=True,status='active',work_role='video',additional_tokens=dict(remaining_label='29B',checked_at=1793570000)),dict(id='acc_B',label='Muse 2',enabled=True,status='cooling',quota_exhausted=True)]
@app.get('/api/muse/accounts/tokens/status')
async def tokens():return dict(running=False,completed=2,total=2)
@app.get('/api/muse/scenes/options')
async def options():return dict(cameras=[dict(id='static',label='Góc tĩnh'),dict(id='pan',label='Góc pan'),dict(id='aerial',label='Fly cam')])
@app.get('/api/muse/scenes/storage')
async def storage():return dict(directory=r'D:\video')
@app.get('/api/muse/scenes')
async def projects():return []
@app.get('/api/muse/scenes/queue')
async def queue():return dict(running=True,total_prompts=4,processing=1,waiting=1,blocked=1,items=[dict(id='q1',project_id='p1',title='Demo',count=4,target=4,videos=1,status='running',blocked=1)])
@app.get('/api/muse/scenes/queue/prompts')
async def prompts(filter: str='all'):
 group={'waiting':'pending','processing':'video','error':'error','completed':'completed'}
 data=rows if filter=='all' else [r for r in rows if r['status']==group.get(filter)]
 return dict(items=data,total=len(data),page=1,pages=1,missing=[])
@app.get('/app-icon.png')
async def icon():return FileResponse(ROOT/'windows/assets/app-icon.png')
@app.get('/')
async def index():return FileResponse(ROOT/'dashboard/dist/index.html')

async def main():
 server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=18135,log_level='error'))
 thread=threading.Thread(target=server.run,daemon=True);thread.start()
 proc=ChromiumProcess(chrome(),19215,OUT/'chrome-profile',True)
 if await proc.browser_ws_url():raise RuntimeError('QA Chrome port occupied')
 browser=None;page=None;context=None;shared=False
 try:
  for _ in range(80):
   if server.started:break
   await asyncio.sleep(.1)
  try:
   async with httpx.AsyncClient(trust_env=False, timeout=3) as client:
    shared_url=(await client.get('http://127.0.0.1:19210/json/version')).json()['webSocketDebuggerUrl']
   browser=await CDPSession.connect(shared_url)
   shared=True
  except Exception:
   browser=await CDPSession.connect(await proc.start())
  context=(await browser.send('Target.createBrowserContext',{'disposeOnDetach': True}))['browserContextId']
  target=(await browser.send('Target.createTarget',{'url':'http://127.0.0.1:18135','browserContextId':context}))['targetId']
  page=await CDPSession.connect('ws://127.0.0.1:' + ('19210' if shared else '19215') + '/devtools/page/'+target)
  await page.send('Emulation.setDeviceMetricsOverride',dict(width=1400,height=1000,deviceScaleFactor=1,mobile=False))
  for _ in range(100):
   if await page.evaluate("document.querySelectorAll('.prompt-queue-row').length===4"):break
   await asyncio.sleep(.2)
  assert await page.evaluate("document.querySelectorAll('.prompt-queue-row').length") == 4
  assert await page.evaluate("document.body.innerText.includes('Điều phối tự động') && document.body.innerText.includes('91%') && document.body.innerText.includes('Đang giảm luồng')")
  assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
  result=await page.send('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
  (OUT/'desktop.png').write_bytes(base64.b64decode(result['data']))
  await page.send('Emulation.setDeviceMetricsOverride',dict(width=1000,height=800,deviceScaleFactor=1,mobile=False))
  assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
  compact=await page.send('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
  (OUT/'compact.png').write_bytes(base64.b64decode(compact['data']))
  await page.evaluate("[...document.querySelectorAll('.queue-filter-bar button')].find(x=>x.innerText==='Cảnh lỗi').click()")
  for _ in range(60):
   if await page.evaluate("document.querySelectorAll('.prompt-queue-row').length===1"):break
   await asyncio.sleep(.2)
  assert await page.evaluate("document.querySelectorAll('.prompt-queue-row').length") == 1
  await page.evaluate("document.querySelector('.landscape-header button').click()")
  for _ in range(50):
   if await page.evaluate("document.body.innerText.includes('Còn 29B')"):break
   await asyncio.sleep(.2)
  assert await page.evaluate("document.body.innerText.includes('Còn 29B')")
  await page.send('Emulation.setDeviceMetricsOverride',dict(width=1000,height=800,deviceScaleFactor=1,mobile=False))
  assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
  shot=await page.send('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
  (OUT/'accounts.png').write_bytes(base64.b64decode(shot['data']))
  report=dict(rendered_prompts=4,error_filter=1,token_column=True,adaptive_resources=True,no_horizontal_overflow=True,synthetic_only=True)
  (OUT/'result.json').write_text(json.dumps(report));print(report)
 finally:
  if page:await page.close()
  if browser:
   try:
    if context:await browser.send('Target.disposeBrowserContext',{'browserContextId':context})
    if not shared:await browser.send('Browser.close',timeout=3)
   except Exception:pass
   await browser.close()
  await proc.stop();server.should_exit=True;thread.join(timeout=4)

if __name__=='__main__':asyncio.run(main())
