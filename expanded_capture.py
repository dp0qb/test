#!/usr/bin/env python3
"""
Capture ORIGINAL public employment/mineral-exploration web pages as displayed by
Chromium; download the untouched original image and attachment bytes.
NEVER reconstruct source text or add branding/explanations to screenshots.
All generated files are provenance manifests and packaging metadata only.
"""
import asyncio, csv, datetime as dt, hashlib, io, json, os, re, sys, urllib.parse, zipfile
from collections import defaultdict
from pathlib import Path
import requests, urllib3
from PIL import Image
from playwright.async_api import async_playwright
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CATEGORY = os.getenv("CAPTURE_CATEGORY","enterprise_recruit")
TARGETS = json.loads(Path("expanded_source_targets.json").read_text(encoding="utf-8"))
SOURCES = [x for x in TARGETS["sources"] if x["category"] == CATEGORY]
ROOT = Path("expanded_sources") / CATEGORY
ROOT.mkdir(parents=True,exist_ok=True)
OUT = Path("download_parts") / CATEGORY
OUT.mkdir(parents=True,exist_ok=True)
MANIFEST = []
FAILURES = []
SEEN_DIGEST = set()
TIMEOUT=24000
HEADERS={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36","Accept-Language":"zh-CN,zh;q=0.9,en;q=0.7"}
IMG_EXTS={".jpg",".jpeg",".png",".webp",".gif",".tif",".tiff"}
DOC_EXTS={".pdf",".doc",".docx",".xls",".xlsx",".zip",".ppt",".pptx"}
ALL_EXTS=IMG_EXTS|DOC_EXTS
WORDS=("地质","勘查","资源","招聘","矿业","矿产","就业","求职","大学","毕业","地勘","岗位","报告","政策")
OUTDATED=("404 Not Found","403 Forbidden","Access Denied","网站维护中","Page not found","找不到页面","无法找到网页","Oops! Something went wrong","This site can’t be reached","This site can't be reached")
def safe_base(s):return re.sub(r"[^a-zA-Z0-9_-]","_",s)[:78]
def sha(b):return hashlib.sha256(b).hexdigest()
def write_local(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)
    return str(path)
def row(source,kind,path,url,ht_code="",width="",height="",extra=""):
    p=Path(path)
    MANIFEST.append({
      "category":CATEGORY,"page_name":source["title"],"source_url":source["url"],
      "asset_type":kind,"file":str(p),"asset_url":url,"http_status":str(ht_code),
      "width_px":width,"height_px":height,"bytes":p.stat().st_size,
      "sha256":sha(p.read_bytes()),"details":str(extra)[:300]})
def fail(source,reason,code=""):
    print("FAIL",source["slug"],str(reason)[:130],flush=True)
    FAILURES.append({"category":CATEGORY,"name":source["title"],"url":source["url"],"failure":str(reason)[:260],"status":str(code)})

def collect_original(source, url, ref, group, ix):
    try:
        u=urllib.parse.urlparse(url)
        if u.scheme not in ("http","https"):return False
        ext=Path(urllib.parse.unquote(u.path)).suffix.lower()
        # Never auto-fetch pages listed in article anchors; only images and original downloadable attachments.
        if ext not in ALL_EXTS:return False
        if u.hostname is None:return False
        resp=requests.get(url,headers={**HEADERS,"Referer":ref},timeout=(8,18),
                          verify=False,allow_redirects=True,stream=True)
        if resp.status_code!=200:return False
        max_bytes=31_000_000 if ext==".pdf" else 26_000_000
        chunks=[];n=0
        for c in resp.iter_content(256*1024):
            n+=len(c)
            if n>max_bytes:return False
            chunks.append(c)
        data=b"".join(chunks)
        if len(data)<500:return False
        digest=sha(data)
        if digest in SEEN_DIGEST:return False
        suffix=ext
        if data.startswith(b"%PDF"):
            suffix=".pdf"
            import fitz
            doc=fitz.open(stream=data,filetype="pdf")
            if doc.page_count<1:return False
        elif data[:2]==b"PK" and ext in {".xlsx",".docx",".pptx",".zip"}:
            if not zipfile.is_zipfile(io.BytesIO(data)):return False
        elif ext in IMG_EXTS:
            im=Image.open(io.BytesIO(data))
            im.verify()
            im=Image.open(io.BytesIO(data))
            w,h=im.size
            if w<460 or h<260:return False
            suffix={"JPEG":".jpg","PNG":".png","WEBP":".webp","GIF":".gif","TIFF":".tif"}.get(im.format,ext)
        elif ext==".pdf":
            return False
        elif ext in {".xls",".doc"}:
            if data[:8] != bytes.fromhex("D0CF11E0A1B11AE1") and len(data)<4096:return False
        SEEN_DIGEST.add(digest)
        fname=f"{source['slug']}__{group}_{ix:02d}{suffix}"
        out=ROOT/fname
        write_local(out,data)
        row(source,"ORIGINAL_ATTACHMENT" if ext in DOC_EXTS else "ORIGINAL_WEBSITE_IMAGE",
            out,resp.url,resp.status_code,*((w,h) if ext in IMG_EXTS else ("","")),extra=f"source_exact:{ref}")
        if suffix==".pdf":
            try:
                import fitz
                doc=fitz.open(stream=data,filetype="pdf")
                for pg_i in range(min(doc.page_count,3)):
                    pix=doc[pg_i].get_pixmap(matrix=fitz.Matrix(1.7,1.7),alpha=False)
                    dst=ROOT/f"{source['slug']}__{group}_{ix:02d}__pdf_page{pg_i+1:02d}.png"
                    pix.save(dst)
                    row(source,"ORIGINAL_PDF_PAGE_RENDER",dst,resp.url,resp.status_code,pix.width,pix.height,
                        f"page:{pg_i+1}")
            except Exception as e:
                print("PDF_WARN",source["slug"],str(e)[:160],flush=True)
        return True
    except Exception as e:
        print("RAW_WARN",source["slug"],str(e)[:100],flush=True)
        return False

async def capture_one(browser,source,sem):
  async with sem:
    slug=source["slug"]
    rawurl=source["url"]
    if urllib.parse.urlparse(rawurl).path.lower().endswith(".pdf"):
        good=await asyncio.to_thread(collect_original,source,rawurl,rawurl,"original_pdf",1)
        if good:
            print("OK_PDF",slug,flush=True)
        else:fail(source,"PDF download not available")
        return
    context=await browser.new_context(viewport={"width":1440,"height":1100},device_scale_factor=1.25,
                     user_agent=HEADERS["User-Agent"],locale="zh-CN",ignore_https_errors=True)
    page=await context.new_page()
    try:
        response=None
        try:
            response=await page.goto(rawurl,wait_until="domcontentloaded",timeout=TIMEOUT)
        except Exception as e:
            try:
                response=await page.goto(rawurl,wait_until="commit",timeout=12000)
            except Exception as e2:
                fail(source,"navigation failed: "+str(e2)[:140])
                return
        await page.wait_for_timeout(1100)
        status=response.status if response else 0
        title=await page.title()
        url=page.url
        body=await page.locator("body").evaluate("(e)=>e.innerText.slice(0,25000)").catch if False else ""
        try:
            body=await page.locator("body").evaluate("(e)=>e.innerText.slice(0,25000)")
        except Exception:
            body=""
        short=body[:500]
        if status>=400 or len(body.strip())<110 or (sum(w in body for w in WORDS)<1) or any(z.lower() in (title+" "+short).lower() for z in OUTDATED):
            fail(source,f"page invalid / no job or policy content; title={title[:50]} bodylen={len(body)}",status)
            return
        height=await page.evaluate("Math.max(document.body.scrollHeight,document.documentElement.scrollHeight)")
        height=int(min(max(height,1100),150000))
        # Browser screenshot is direct Playwright output, no synthetic layout or adornment.
        vpath=ROOT/f"{slug}__ORIGINAL_SITE_VIEWPORT.png"
        await page.screenshot(path=str(vpath),full_page=False,animations="disabled",timeout=30000)
        row(source,"ORIGINAL_SITE_VIEWPORT",vpath,url,status,1800,1375,f"html_title:{title}")
        # Entire original DOM page screenshot, only when practical.
        if height<=10000:
            try:
                fpath=ROOT/f"{slug}__ORIGINAL_SITE_FULL.png"
                await page.screenshot(path=str(fpath),full_page=True,animations="disabled",timeout=45000)
                row(source,"ORIGINAL_SITE_FULL",fpath,url,status,1800,int(height*1.25),f"html_title:{title}")
            except Exception as e:
                print("FULL_WARN",slug,str(e)[:180],flush=True)
        else:
            # Scroll to the original job table/requirements in situ; no DOM editing.
            marks=await page.evaluate(r"""() => {
              const els=Array.from(document.querySelectorAll('h1,h2,h3,h4,p,li,td,section,article,div')).slice(0,1800);
              const terms=['岗位需求','招聘岗位','招聘专业','学历要求','岗位信息','岗位列表','职位列表','招聘人数','专业要求','招聘计划','招聘条件','薪酬','补贴','就业政策','地质','资源勘查工程'];
              const vals=[];
              for(const e of els){
                const t=(e.innerText||'').trim();
                if(t.length<4 || t.length>650)continue;
                if(terms.some(x=>t.includes(x))){
                  const r=e.getBoundingClientRect();
                  const y=Math.round(r.top+window.scrollY);
                  if(y>1100 && y<120000)vals.push(y);
                }
              }
              return vals.sort((a,b)=>a-b);
            }""")
            selected=[]
            for value in [*marks,round(height*.52),round(height*.8)]:
                if len(selected)>=3:break
                y=min(max(600,int(value)-170),height-1000)
                if all(abs(y-p)>1000 for p in selected):selected.append(y)
            for i,y in enumerate(selected,2):
                try:
                    await page.evaluate("(y)=>window.scrollTo(0,y)",y)
                    await page.wait_for_timeout(400)
                    dst=ROOT/f"{slug}__ORIGINAL_SITE_SCROLL_{i:02d}.png"
                    await page.screenshot(path=str(dst),full_page=False,timeout=18000,animations="disabled")
                    row(source,"ORIGINAL_SITE_SCROLL",dst,url,status,1800,1375,f"original_scroll_y:{y}")
                except Exception as e:print("SCROLL_WARN",slug,str(e)[:130],flush=True)
        # Only raw original source files: images and attachments directly published on webpage.
        try:
            vals=await page.locator("img").evaluate_all(r"""els=>els.map(e=>({
              src:e.currentSrc||e.getAttribute('data-original')||e.getAttribute('data-src')||e.getAttribute('src'),
              w:e.naturalWidth,h:e.naturalHeight
            })).filter(x=>x.src).sort((a,b)=>(b.w*b.h)-(a.w*a.h)).slice(0,40)""")
            urls=[]
            for ob in vals:
                src=urllib.parse.urljoin(url,str(ob.get("src") or ""))
                if src.startswith(("http://","https://")) and src not in urls:urls.append(src)
            for ix,src in enumerate(urls[:10],1):
                await asyncio.to_thread(collect_original,source,src,url,"image",ix)
        except Exception as e:print("IMG_EXTRACT_WARN",slug,str(e)[:130],flush=True)
        try:
            links=await page.locator("a[href]").evaluate_all(r"""els=>els.map(e=>e.href).filter(Boolean).slice(0,250)""")
            candidates=[] 
            for u in links:
                ext=Path(urllib.parse.urlparse(u).path).suffix.lower()
                if ext in DOC_EXTS and u not in candidates:candidates.append(u)
            for ix,u in enumerate(candidates[:12],1):
                await asyncio.to_thread(collect_original,source,u,url,"attachment",ix)
        except Exception as e:print("ATTACH_WARN",slug,str(e)[:120],flush=True)
        print("CAPTURED",CATEGORY,slug,status,len(body),height,
              len([e for e in MANIFEST if e["page_name"]==source["title"]]),flush=True)
    except Exception as e:
        fail(source,str(e))
    finally:
        await context.close()

def build_parts():
    index=ROOT/"source_manifest.csv"
    cols=["category","page_name","source_url","asset_type","file","asset_url","http_status",
          "width_px","height_px","bytes","sha256","details"]
    with index.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(MANIFEST)
    errors=ROOT/"failed_sources.csv"
    with errors.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["category","name","url","failure","status"])
        w.writeheader();w.writerows(FAILURES)
    successes={a["source_url"] for a in MANIFEST if a["asset_type"]=="ORIGINAL_SITE_VIEWPORT" or a["asset_type"]=="ORIGINAL_ATTACHMENT"}
    js=ROOT/"capture_run_info.json"
    js.write_text(json.dumps({
      "date_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
      "category":CATEGORY,"attempted_urls":len(SOURCES),"pages_or_pdfs_success":len(successes),
      "files":len(MANIFEST),"failed_urls":len(FAILURES),
      "by_kind":{k:sum(a["asset_type"]==k for a in MANIFEST) for k in sorted({a["asset_type"] for a in MANIFEST})},
    },ensure_ascii=False,indent=2),encoding="utf-8")
    MEDIA=[p for p in sorted(ROOT.iterdir()) if p.is_file() and p.suffix.lower() in IMG_EXTS|DOC_EXTS]
    TARGET=13_000_000
    groups=[];batch=[];size=0
    for p in MEDIA:
        n=p.stat().st_size
        if batch and size+n>TARGET:
            groups.append(batch);batch=[];size=0
        batch.append(p);size+=n
    if batch:groups.append(batch)
    if not groups:raise RuntimeError("Zero valid source media files were collected for "+CATEGORY)
    for i,g in enumerate(groups,1):
        if i>25:raise RuntimeError("Part count exceeds 25; increase TARGET or uploading jobs")
        p=OUT/f"part{i:02d}"
        p.mkdir(parents=True,exist_ok=True)
        for file in g:
            out=p/file.name
            out.write_bytes(file.read_bytes())
        for inf in [index,errors,js]:
            (p/inf.name).write_bytes(inf.read_bytes())
        # Verify every packaged item against its unmodified original.
        for file in g:
            original=file.read_bytes()
            assert sha(original)==sha((p/file.name).read_bytes())
        print("PART",CATEGORY,i,len(g),sum(f.stat().st_size for f in g),flush=True)
    print("SUMMARY",CATEGORY,"sources",len(SOURCES),"success",len(successes),
          "files",len(MANIFEST),"parts",len(groups),"total_bytes",sum(x.stat().st_size for x in MEDIA),
          "failures",len(FAILURES),flush=True)

async def main():
    if not SOURCES: raise RuntimeError("Unknown category: "+CATEGORY)
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
        sem=asyncio.Semaphore(5)
        await asyncio.gather(*(capture_one(browser,s,sem) for s in SOURCES))
        await browser.close()
    build_parts()

if __name__=="__main__":
    asyncio.run(main())
