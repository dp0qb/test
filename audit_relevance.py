#!/usr/bin/env python3
"""
Read ONLY original already-captured batch 1/2 source URLs, inspect live article body
to discover whether the page actually describes SOLID mineral resource exploration.
This is an internal audit; it never retypesets or alters the original screenshots.
"""
import asyncio, csv, re, json, datetime, time, unicodedata, collections, pathlib, urllib.parse, concurrent.futures, requests
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

ROOT=pathlib.Path("filter_audit")
ROOT.mkdir(exist_ok=True)
FIRST=pathlib.Path("original_sources/原始页面与图片来源索引.csv")
SECOND=pathlib.Path("raw_index/全部279份原始资料索引.csv")
TARGETS=json.loads(pathlib.Path("expanded_source_targets.json").read_text(encoding="utf-8"))["sources"]
SLUGS={s["url"]:s for s in TARGETS}
assert FIRST.exists() and SECOND.exists(),(FIRST,SECOND)
def csv_rows(f):
 with f.open(encoding="utf-8-sig",newline="") as fp:return list(csv.DictReader(fp))
first=csv_rows(FIRST)
second=csv_rows(SECOND)
mapping=collections.defaultdict(lambda:{"batches":set(),"categories":set(),"titles":set(),"files":set()})
for r in first:
 if r.get("类别")=="FAILED" or r.get("类型")=="FAILED":continue
 url=r.get("原始发布页面") or ""
 if not url.startswith("http"):continue
 obj=mapping[url]
 obj["batches"].add("第一批")
 route=(r.get("本地文件") or "").split("/")
 obj["categories"].add({"recruit":"enterprise_recruit","policy":"geological_industry_policy_data","field":"field_photos"}.get(route[1] if len(route)>1 else "",route[1] if len(route)>1 else ""))
 obj["titles"].add((route[-1] if route else "").split("__")[0])
 obj["files"].add(r.get("本地文件",""))
for r in second:
 url=r.get("原网页URL") or ""
 if not url.startswith("http"):continue
 obj=mapping[url]
 obj["batches"].add("第二批")
 cat=(r.get("原始资料类别") or "")
 obj["categories"].add({"矿业企业招聘":"enterprise_recruit","地勘单位招聘":"geology_institution_recruit","毕业生就业政策":"graduate_employment_policy","矿产行业政策":"geological_industry_policy_data"}.get(cat,cat))
 obj["titles"].add(r.get("公告或政策标题",""))
 obj["files"].add(r.get("文件名",""))
 for f in ("所在压缩包",):pass
 print("",end="")
targets=[]
for url,v in mapping.items():
 a=SLUGS.get(url,{})
 cats=sorted(x for x in v["categories"] if x)
 cat=cats[0] if cats else ""
 if "enterprise_recruit" in cats:cat="enterprise_recruit"
 elif "geology_institution_recruit" in cats:cat="geology_institution_recruit"
 elif "field_photos" in cats:cat="field_photos"
 elif "geological_industry_policy_data" in cats:cat="geological_industry_policy_data"
 elif "graduate_employment_policy" in cats:cat="graduate_employment_policy"
 obj={"url":url,"cat":cat,"slug":a.get("slug",""),"title":a.get("title","") or sorted(v["titles"])[0],
       "batches":"+".join(sorted(v["batches"])),"files_count":len(v["files"]),"file_names":sorted(v["files"])}
 targets.append(obj)
assert len(targets)>=90,len(targets)
print("ALL_ORIGINAL_SOURCE_URLS",len(targets),"FIRST",sum("第一批" in t["batches"] for t in targets),
      "SECOND",sum("第二批" in t["batches"] for t in targets),flush=True)

PRIMARY=[
 "资源勘查工程","矿产普查与勘探","固体矿产勘查","固体矿产","地矿勘查技术岗",
 "矿产勘查","矿产资源勘查","找矿突破","找矿","地质勘查","地质技术员",
 "地质技术岗","地质类管培生","勘查地质","岩芯编录","岩矿心编录","地质编录",
 "生产探矿","风险勘查","矿山地质","矿产资源评价","矿产储量","资源储量估算",
 "地质调查","矿床学","勘查技术","地质技术","矿区地质"
]
JOBTERMS=["招聘岗位","岗位名称","招聘计划","岗位描述","岗位职责","应聘要求","专业要求","岗位所需专业","需求专业","招聘人数","职位描述","招聘对象","招聘专业","岗位要求"]
MID=["地质学","地质工程","矿物学","构造地质学","地质资源与地质工程","地球化学","岩石学","地质","勘探","储量管理"]
POLICY=["中华人民共和国矿产资源法","矿产资源法实施条例","矿产资源报告","找矿突破","能源资源安全","地质调查","地质勘查","矿产资源储量","非油气地质勘查","矿产资源勘查"]
NEG=["油气勘探","石油天然气","地热资源","水文地质","地下水调查","环境地质","地质灾害","岩土工程","地质灾害防治"]
def trim(s,maxlen=28000):
 s=unicodedata.normalize("NFKC",str(s))
 return re.sub(r"\s+"," ",s).strip()[:maxlen]
def find_spans(text,terms,n=5):
 matches=[]
 for term in sorted(terms,key=len,reverse=True):
  for m in list(re.finditer(re.escape(term),text))[:8]:
   x=m.start();b=max(0,x-130);e=min(len(text),x+205)
   snippet=text[b:e]
   matches.append((x,term,snippet))
 matches=sorted(matches,key=lambda x:x[0])
 uniq=[]
 for it in matches:
  if not uniq or it[0]-uniq[-1][0]>60:uniq.append(it)
 return uniq[:n]
def decision(meta,txt):
 category=meta["cat"]
 title=meta["title"]
 title_match=[x for x in PRIMARY if x in title]
 primary=[x for x in PRIMARY if x in txt]
 mid=[x for x in MID if x in txt]
 policy_terms=[x for x in POLICY if x in txt or x in title]
 job_hits=[x for x in JOBTERMS if x in txt]
 if category=="graduate_employment_policy":
  if any(t in txt for t in ("矿产勘查岗位","固体矿产勘查","矿产普查与勘探","资源勘查工程毕业生")):
   rank="B";status="保留";reason="政策明确提及本专业相关就业岗位"
  else:rank="X";status="剔除";reason="通用高校毕业生就业政策，未明确涉及固体矿产勘查"
 elif category=="geological_industry_policy_data":
  if any(x in txt+" "+title for x in POLICY):
   rank="A";status="保留";reason="矿产资源勘查或地质调查专项政策/数据"
  else:rank="X";status="剔除";reason="未检出矿产勘查专项内容"
 elif category=="field_photos":
  if any(t in txt+" "+title for t in ["矿产勘查","矿产资源","岩芯","岩心","地质调查","钻探","金矿","稀土","找矿","地质队","地质勘探","地质编录","钻孔","岩矿","地质","铬铁矿"]):
   rank="B";status="保留";reason="原始工作现场记录与矿产勘查活动相关"
  else:rank="X";status="剔除";reason="不能确认图片属于固体矿产勘查工作场景"
 else:
  # Recruitment: exact department/role/context necessary, group name alone does NOT count.
  role_patterns=[
   "资源勘查工程","矿产普查与勘探","固体矿产","矿产资源勘查","矿产勘查",
   "地矿勘查","地质技术员","地质技术岗","地质类管培生","地质技术1","地质技术2",
   "地质工程师","矿山地质","勘查地质","地质编录","岩芯编录","岩矿心编录",
   "生产探矿","矿产资源评价","资源储量估算"]
  q=[x for x in role_patterns if x in txt]
  exact=[x for x in ("资源勘查工程","矿产普查与勘探","固体方向","固体矿产勘查") if x in txt]
  titlejob=bool(any(y in title for y in ["地质技术","地质类管培生","矿产资源","矿产勘查","地勘","矿产","地质大队"]))
  # Ignore words that only occur before section headings in broad corporate overview.
  regions=[m.start() for k in JOBTERMS for m in list(re.finditer(re.escape(k),txt))[:6]]
  if not regions:regions=[0]
  relevant_context=[]
  for x in q:
   positions=[m.start() for m in re.finditer(re.escape(x),txt)]
   for y in positions[:8]:
    nearest=min(abs(y-p) for p in regions) if regions else 99999
    context=txt[max(0,y-130):min(len(txt),y+220)]
    if nearest<3500 or any(t in context for t in JOBTERMS) or any(t in context for t in ["岗位","职位","招聘","专业要求","招聘人数","本科","硕士","博士","从事","负责"]):
     relevant_context.append((x,y,context))
  if exact and relevant_context:
   rank="A";status="保留";reason="招聘专业或岗位内容明确出现资源勘查工程/固体矿产勘查"
  elif q and relevant_context and job_hits and (titlejob or "矿产勘查" in q or "地质技术员" in q or len(q)>=2):
   rank="B";status="保留";reason="招聘岗位或职责明确涉及矿产地质技术、勘查、编录或资源评价"
  else:
   rank="X";status="剔除";reason="缺少与固体矿产勘查岗位直接相关的招聘证据（企业矿业背景不计）"
  if any(t in title for t in ("石油","油气","地热")) and not exact and rank!="A":
   rank="X";status="剔除";reason="招聘偏油气/地热方向，与固体矿产不符"
  if status=="保留" and any(x in title for x in ("通用招聘平台","招聘列表","招聘门户")) and not exact:
   status="剔除";rank="X";reason="招聘门户页面，无可用于专业介绍的明确职位"
 excerpts=[]
 for x,tt,sn in find_spans(txt,PRIMARY+JOBTERMS,6):
  if category in ("enterprise_recruit","geology_institution_recruit"):
   if not any(q in sn for q in ["招聘","岗位","职位","专业","从事","矿产","资源勘查工程","勘查技术","地质技术"]):continue
  excerpts.append(sn)
 return dict(status=status,grade=rank,reason=reason,primary=";".join(primary),job_terms=";".join(job_hits),
             excerpts=" || ".join(excerpts[:4]),exact_terms=";".join(exact if category in ("enterprise_recruit","geology_institution_recruit") else policy_terms))

async def scrape(browser,meta,sem):
 async with sem:
  url=meta["url"]
  ctx=await browser.new_context(locale="zh-CN",ignore_https_errors=True, user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36")
  page=await ctx.new_page()
  text=""
  realtitle=""
  error=""
  code=0
  try:
   if urllib.parse.urlparse(url).path.lower().endswith(".pdf"):
    try:
     import fitz
     r=await asyncio.to_thread(requests.get,url,timeout=15,verify=False)
     if r.content.startswith(b"%PDF"):
      doc=fitz.open(stream=r.content,filetype="pdf")
      text=" ".join(pg.get_text(sort=True) for pg in list(doc)[:8])
      realtitle=meta["title"];code=r.status_code
    except Exception as e:error=f"PDF {type(e).__name__}: {str(e)[:110]}"
   else:
    r=None
    try:
     r=await page.goto(url,wait_until="domcontentloaded",timeout=20000)
    except Exception as e:
     try:r=await page.goto(url,wait_until="commit",timeout=8000)
     except Exception as e2:error=f"navigation:{str(e2)[:115]}"
    if r is not None:code=r.status
    try:
     await page.wait_for_timeout(400)
     realtitle=await page.title()
     # Extract actual page main text only, no inferred text.
     text=await page.evaluate(r"""() => {
       const root=document.querySelector('article,[role=main],.article,.article-content,.detail,.main-content,.news-detail,.recruitment-detail,.content-main,.content-container,#article,#article-content');
       const roottext=(root?.innerText||'').trim();
       const body=(document.body?.innerText||'').trim();
       return roottext.length>250 && roottext.length<70000 ? roottext : body
     }""")
    except Exception as e:error=f"DOM:{str(e)[:100]}"
  except Exception as e:error=f"outer:{str(e)[:150]}"
  finally:
   await ctx.close()
  txt=trim(text)
  d=decision(meta,txt)
  # If body empty but original source was valid, should not automatically keep.
  if len(txt)<130 and d["status"]=="保留":
    d.update({"status":"剔除","grade":"X","reason":"原站正文无法提取和核实具体关联；已排除防止误收"})
  result={**{k:meta[k] for k in ["url","cat","slug","title","batches","files_count"]},
          "actual_page_title":trim(realtitle,170),"http_code":code,"text_length":len(txt),"error":error,
          **d}
  result["text_excerpt_intro"]=txt[:450]
  print("AUDIT",meta["cat"],d["grade"],meta["slug"] or meta["title"][:25],
        "text",len(txt),"http",code,"hits",d["primary"][:100],flush=True)
  return result

async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,args=["--no-sandbox","--disable-dev-shm-usage"])
  sem=asyncio.Semaphore(6)
  result=await asyncio.gather(*(scrape(browser,t,sem) for t in targets))
  await browser.close()
  keys=["batches","cat","slug","title","actual_page_title","url","status","grade","reason","primary",
       "exact_terms","job_terms","text_length","http_code","error","text_excerpt_intro","excerpts","files_count"]
  with (ROOT/"专业相关性逐页审查.csv").open("w",encoding="utf-8-sig",newline="") as f:
   w=csv.DictWriter(f,fieldnames=keys)
   w.writeheader()
   w.writerows({k:item.get(k,"") for k in keys} for item in result)
  with (ROOT/"audit_results.json").open("w",encoding="utf-8") as f:
   json.dump(result,f,ensure_ascii=False,indent=2)
  total=collections.Counter((d["cat"],d["status"]) for d in result)
  print("FINAL_AUDIT_COUNTS",json.dumps({str(k):v for k,v in total.items()},ensure_ascii=False),flush=True)
  print("KEEP_LIST")
  for d in result:
   if d["status"]=="保留":print(d["batches"],d["cat"],d["grade"],d["slug"] or d["title"],d["primary"][:110],flush=True)
  print("END_KEEP_LIST")
if __name__=="__main__":
 asyncio.run(main())
