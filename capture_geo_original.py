#!/usr/bin/env python3
# Capture original public web pages exactly as displayed by Chromium, and original media bytes.
import asyncio, csv, hashlib, io, re, time, zipfile
from pathlib import Path
from urllib.parse import urlparse, urljoin, unquote
import requests
from PIL import Image
from playwright.async_api import async_playwright

ROOT=Path("original_sources")
ROOT.mkdir(exist_ok=True)
SOURCES=[
 ("policy","2024_mineral_law_mnr","https://f.mnr.gov.cn/202411/t20241109_2873922.html"),
 ("policy","2024_mineral_law_fujian","https://zrzyt.fujian.gov.cn/zwgk/zcfg/flfg/202411/t20241111_6564367.htm"),
 ("policy","2024_mineral_law_beijing","https://www.beijing.gov.cn/zhengce/zhengcefagui/qtwj/202511/t20251110_4267357.html"),
 ("policy","2024_mineral_law_implementation","https://app.www.gov.cn/govdata/gov/202412/26/523060/article.html"),
 ("policy","2026_mining_regulations","https://xzfg.moj.gov.cn/front/law/detail?LawID=1815"),
 ("policy","2026_regulations_explanation","https://www.moj.gov.cn/pub/sfbgw/jgsz/jgszjgtj/jgtjlfsij/lfsijtjxw/202605/t20260525_535566.html"),
 ("policy","2024_mineral_law_mnr_original_print","https://zjjcmspublic.oss-cn-hangzhou-zwynet-d01-a.internet.cloud.zj.gov.cn/jcms_files/jcms1/web1831/site/attach/0/0b1ab024b0764e02b8574fede4bd9cad.pdf"),
 ("policy","2024_natural_resources_report_official","https://www.gov.cn/lianbo/bumen/202503/P020250322461627579892.pdf"),
 ("policy","2024_mineral_law_guangdong","https://www.xinxing.gov.cn/yfxxzrzy/gkmlpt/content/1/1929/post_1929585.html"),
 ("policy","2024_mineral_law_environment","https://www.mee.gov.cn/ywgz/fgbz/fl/202511/t20251107_1132286.shtml"),
 ("recruit","2027_jiangxi_copper_geological_exploration","https://www.jxcc.com/recruitmentAnnouncement/details_475_7119.html"),
 ("recruit","2027_jiangxi_copper_list","https://www.jxcc.com/join/recruitmentAnnouncement.html"),
 ("recruit","2027_zijin_university_original","https://cug.91wllm.cn/campus/view/id/1001713"),
 ("recruit","2027_zijin_original_posters_1","https://cug.91wllm.cn/campus/view/id/1002766"),
 ("recruit","2027_zijin_original_posters_2","https://cug.91wllm.cn/campus/view/id/1001276"),
 ("recruit","2027_zijin_central_south_university","https://career.csu.edu.cn/campus/view/id/588494"),
 ("recruit","2027_chinalco_nankai","https://career.nankai.edu.cn/correcruit/content/id/119052.html"),
 ("recruit","2027_china_gold_jilin_university","https://jdjywpt.jlu.edu.cn/mportal/recruit/details?id=2eec4cdac48e4572b47f2db943eae990"),
 ("recruit","2027_metallurgical_geology_bj_mining_uni","https://jy.cumtb.edu.cn/Zhaopin/zuijin.html?hold_date=2026-10-9&id=3e598dd1-a018-cfdb-fa00-51ba8ec30416"),
 ("recruit","2025_zijin_published_brochure_pdf","https://xsjyc.chd.edu.cn/Files/Umeditor/file/20250319/6387797394287893658590156.pdf"),
 ("field","2025_geological_survey_mobilisation","https://www.cgs.gov.cn/ywdt/dwdt/202505/t20250509_839422.html"),
 ("field","2026_core_digitization_mining_meeting","https://www.cgs.gov.cn/ddzt/zgkydh/2026kydh/ywkb2026kydh/202609/t20260920_869324.html"),
 ("field","2019_geological_core_sample_field","https://www.cgs.gov.cn/ywdt/dwdt/201908/t20190822_831125.html"),
 ("field","2021_core_logging_field","https://www.cgs.gov.cn/ywdt/dwdt/202111/t20211109_834223.html"),
 ("field","2020_tin_tungsten_gold_mineral_search","https://www.igm.cgs.gov.cn/kjdt/202011/t20201124_659163.html"),
 ("field","2025_rare_earth_geological_exploration","https://m.cgs.gov.cn/ddyw/202507/t20250722_794763.html"),
 ("field","2018_digital_drill_core_samples","https://www.cgs.gov.cn/ywdt/dwdt/201809/t20180918_829616.html"),
 ("field","2018_core_image_capture","https://www.cgs.gov.cn/ywdt/dwdt/201812/t20181214_830105.html"),
 ("field","2021_tibet_geological_exploration","https://www.igm.cgs.gov.cn/kjdt/202106/t20210601_672156.html"),
 ("field","2019_qinghai_geological_mapping","https://www.cgs.gov.cn/ywdt/dwdt/201908/t20190801_831016.html"),
]
HEADERS={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36","Accept-Language":"zh-CN,zh;q=0.9,en;q=0.6"}
manifest=[]
images_seen=set()

def save_image_original(url, referer, d, base, num):
 try:
  s=requests.Session()
  r=s.get(url,timeout=22,headers={**HEADERS,"Referer":referer},allow_redirects=True,verify=False)
  if r.status_code!=200 or len(r.content)<9000: return None
  im=Image.open(io.BytesIO(r.content))
  im.verify()
  im=Image.open(io.BytesIO(r.content))
  w,h=im.size
  if (w<450 or h<275) and (w*h<220000): return None
  dig=hashlib.sha256(r.content).hexdigest()
  if dig in images_seen: return None
  images_seen.add(dig)
  ext={"JPEG":".jpg","PNG":".png","WEBP":".webp","GIF":".gif","TIFF":".tif"}.get(im.format)
  if not ext: return None
  d.mkdir(parents=True,exist_ok=True)
  p=d/(base+"__original_"+str(num).zfill(2)+ext)
  p.write_bytes(r.content)
  manifest.append(["original_image",str(p),referer,url,r.status_code,w,h,len(r.content)])
  return str(p)
 except Exception:
  return None

def fetch_pdf_original(url,category,label):
 try:
  r=requests.get(url,headers=HEADERS,timeout=50,verify=False)
  if not r.content.startswith(b"%PDF"): return False
  d=ROOT/category
  d.mkdir(parents=True,exist_ok=True)
  path=d/(label+"__original.pdf")
  path.write_bytes(r.content)
  manifest.append(["original_pdf",str(path),url,url,200,"","",len(r.content)])
  try:
   import fitz
   doc=fitz.open(stream=r.content,filetype="pdf")
   for n in range(min(doc.page_count,5)):
    pg=doc[n]
    pix=pg.get_pixmap(matrix=fitz.Matrix(1.8,1.8),alpha=False)
    p=d/(label+"__pdf_page_"+str(n+1).zfill(2)+".png")
    pix.save(p)
    manifest.append(["pdf_page_original_render",str(p),url,url,200,pix.width,pix.height,p.stat().st_size])
  except Exception as e:
   print("PDF_RENDER_ERROR",label,str(e))
  return True
 except Exception as e:
  print("PDF_DOWNLOAD_ERROR",label,str(e))
  return False

async def browser_capture(browser,item,sem):
 async with sem:
  category,label,url=item
  if url.lower().split("?")[0].endswith(".pdf"):
   if await asyncio.to_thread(fetch_pdf_original,url,category,label):return
  d=ROOT/category
  d.mkdir(parents=True,exist_ok=True)
  context=await browser.new_context(viewport={"width":1440,"height":1150},device_scale_factor=1.5,locale="zh-CN",ignore_https_errors=True,user_agent=HEADERS["User-Agent"])
  page=await context.new_page()
  try:
   try:
    response=await page.goto(url,wait_until="domcontentloaded",timeout=30000)
   except Exception as e:
    print("NAV_WARNING",label,str(e)[:140])
    try:
     await page.goto(url,wait_until="commit",timeout=17000)
    except Exception as e2:
     manifest.append(["FAILED",label,url,"",str(e2)[:200],"","",""])
     return
   await page.wait_for_timeout(1700)
   title=await page.title()
   bodylen=await page.locator("body").evaluate("(e) => e.innerText.length").catch if False else 0
   # Save the actual Chromium-rendered viewport; no text or headers added.
   p=d/(label+"__browser_viewport.png")
   await page.screenshot(path=str(p),full_page=False,timeout=20000,animations="disabled")
   manifest.append(["original_webpage_viewport",str(p),url,page.url,response.status if response else "",1440,1150,p.stat().st_size])
   # Save the actual Chromium-rendered full original page if reasonable.
   height=await page.evaluate("Math.max(document.body.scrollHeight,document.documentElement.scrollHeight)")
   if height<=13000:
    try:
     p=d/(label+"__browser_full.png")
     await page.screenshot(path=str(p),full_page=True,timeout=30000,animations="disabled")
     manifest.append(["original_webpage_full",str(p),url,page.url,response.status if response else "",1440,height,p.stat().st_size])
    except Exception as e:
     print("FULL_PAGE_WARNING",label,str(e)[:130])
   else:
    # Viewport screenshots of original page at subsequent scroll positions.
    for n,y in enumerate([1400,3000,5000,8000],start=2):
     if y>=height:break
     await page.evaluate("(y)=>scrollTo(0,y)",y)
     await page.wait_for_timeout(450)
     p=d/(label+"__browser_viewport_"+str(n).zfill(2)+".png")
     await page.screenshot(path=str(p),full_page=False,timeout=18000,animations="disabled")
     manifest.append(["original_webpage_scrolled_viewport",str(p),url,page.url,response.status if response else "",1440,y,p.stat().st_size])
   imgs=await page.locator("img").evaluate_all("""ims => ims.map(i=>({src:i.currentSrc || i.getAttribute('data-src') || i.getAttribute('data-original') || i.getAttribute('src'),w:i.naturalWidth,h:i.naturalHeight})).filter(x=>x.src&&x.src.startsWith('http')).sort((a,b)=>b.w*b.h-a.w*a.h).slice(0,24)""")
   candidates=[x["src"] for x in imgs if x.get("w",0)>=380 or x.get("h",0)>=500]
   for i,src in enumerate(candidates[:12],start=1):
    await asyncio.to_thread(save_image_original,src,url,d,label,i)
   print("DONE",category,label,title[:60],len(candidates),height)
  except Exception as e:
   print("CAPTURE_ERROR",label,str(e)[:200])
   manifest.append(["FAILED",label,url,"",str(e)[:200],"","",""])
  finally:
   await context.close()

async def main():
 import urllib3
 urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,args=["--no-sandbox","--disable-dev-shm-usage"])
  sem=asyncio.Semaphore(3)
  await asyncio.gather(*[browser_capture(browser,item,sem) for item in SOURCES])
  await browser.close()
 csvfile=ROOT/"原始页面与图片来源索引.csv"
 with csvfile.open("w",newline="",encoding="utf-8-sig") as f:
  w=csv.writer(f)
  w.writerow(["类型","本地文件","原始发布页面","实际资源地址","HTTP状态","图宽/滚动距离","图高","文件字节数"])
  w.writerows(manifest)
 package=Path("资源勘查工程_原网页实拍截图与原始图片附件.zip")
 with zipfile.ZipFile(package,"w",zipfile.ZIP_DEFLATED,compresslevel=5) as z:
  for file in ROOT.rglob("*"):
   if file.is_file():z.write(file,file.relative_to(ROOT.parent))
 print("COMPLETED files",len(list(ROOT.rglob("*"))),"zip",package.stat().st_size)
if __name__=="__main__":asyncio.run(main())
