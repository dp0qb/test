#!/usr/bin/env python3
"""Curate and integrate first and second batches of immutable ORIGINAL web captures.

Strict source whitelist is based on reviewed official role/major requirements or
solid-mineral exploration-specific policy/site context. Every source in the
input is recorded in the keep/exclude audit. Screenshot and attachment bytes
must remain byte-exact. Original URLs are preserved in XLSX and CSV indexes.
"""
from __future__ import annotations
import csv, collections, datetime as dt, hashlib, io, json, re, shutil, zipfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from PIL import Image
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

F = Path("original_sources")
S = Path("second_parts")
A = Path("filter_audit/audit_results.json")
INDEX = Path("second_index/全部279份原始资料索引.csv")
DEST = Path("curated_delivery")
WORK = DEST/"合集原始文件"
WORK.mkdir(parents=True,exist_ok=True)

# Actively curated after examining original live-source body and job duty/major lines.
WHITELIST = {
 "enterprise_recruit": [
   "jx_copper_2027_exploration", "jx_copper_2026_geol",
   "tongling_metals_2027_resources", "westmining_2027",
   "xiamen_tungsten_2027_job", "guangxi_key_metals_2027",
   "minmetals_2026_explore", "cmg_wuhan_2027_cug",
   "minmetals_mcc_jinji_2027"
 ],
 "geology_institution_recruit": [
   "cgs_2026_first_official", "gansu_geology_2026_jlu",
   "shandong_sixth_2026_details", "shandong_geology_2026_72",
   "hunan_geology_2026", "jiangxi_geology_2026_phd",
   "beijing_geology_2026_36"
 ],
 "field_photos": [
   "2025_geological_survey_mobilisation",
   "2026_core_digitization_mining_meeting",
   "2019_geological_core_sample_field",
   "2021_core_logging_field",
   "2025_rare_earth_geological_exploration",
   "2018_digital_drill_core_samples",
   "2018_core_image_capture"
 ],
 "geological_industry_policy_data": [
   "2024_mineral_law_beijing",
   "2024_mineral_law_mnr_original_print",
   "2026_mining_regulations",
   "2026_regulations_explanation",
   "2026_mnr_fifteenth_exploration",
   "2026_cgs_national_meeting",
   "2026_mnr_basic_geology",
   "2026_mnr_fifteenth_resources_census",
   "2026_mineral_report_2026",
   "2026_2025_mining_annual_report",
   "2026_national_deposit_congress",
   "2026_2025_geology_fund",
   "2025_mnr_strategy_interview",
   "2026_cgs_mineral_tech",
   "2026_2025_mineral_report_2025_comparison"
 ]
}
ALLOWED={x for v in WHITELIST.values() for x in v}
assert len(ALLOWED)==sum(map(len,WHITELIST.values())) and len(ALLOWED)>=30

# Intentional duplicate source eliminations, explained in the audit report.
DUPLICATES = {
 "jx_copper_2027_jlu":"与江铜2027年官方招聘公告重复，保留企业原站",
 "jx_copper_2026_geology_2":"与江铜2026年官方地勘招聘公告重复，保留企业原站",
 "cmg_wuhan_2027":"与中冶武勘中国地质大学岗位公告重复，保留专业要求更明确的版本",
 "2026_mineral_report_mofcom":"同一《中国矿产资源报告2026》存在官方地调局原文，去除转载",
 "2025_fiveyear_mineral_development":"同一矿产资源报告重复解读，保留原始发布机构材料",
 "2026_cgs_geology_meeting_press":"2026全国地质调查工作会议报道重复，保留原始地调局会议页面",
 "2024_mineral_law_environment":"同法条重复公布页面，保留法律原始 PDF及政府正文",
 "2024_mineral_law_implementation":"与矿产资源法原文及实施条例原文重叠，优先保留后两项",
 "2024_natural_resources_report_official":"自然资源综合公报大量内容超出固体矿产勘查范围",
 "2026_mnr_basic_geology_explain":"与基础地质调查原通知重复，保留原始通知",
 "2019_qinghai_geological_mapping":"无法充分确认对应图片属于固体矿产勘查项目"
}
THEMES={
 "enterprise_recruit":"01_企业直接对口招聘",
 "geology_institution_recruit":"02_地勘事业单位对口岗位",
 "geological_industry_policy_data":"03_找矿政策与行业原始数据",
 "field_photos":"04_真实地质勘查工作场景"
}
CATEGORY_SEQUENCE=list(THEMES)
F_BATCH_TYPES={
 "original_webpage_full":"ORIGINAL_SITE_FULL",
 "original_webpage_viewport":"ORIGINAL_SITE_VIEWPORT",
 "original_webpage_scrolled_viewport":"ORIGINAL_SITE_SCROLL",
 "original_image":"ORIGINAL_WEBSITE_IMAGE",
 "original_pdf":"ORIGINAL_ATTACHMENT",
 "pdf_page_original_render":"ORIGINAL_PDF_PAGE_RENDER"
}
SCREEN_TYPES={"ORIGINAL_SITE_FULL","ORIGINAL_SITE_VIEWPORT","ORIGINAL_SITE_SCROLL"}
ASSET_TYPES={"ORIGINAL_WEBSITE_IMAGE","ORIGINAL_ATTACHMENT","ORIGINAL_PDF_PAGE_RENDER"}
JOB_MATCH=("资源勘查工程","矿产普查与勘探","固体矿产","矿产勘查","地质勘查",
    "地质技术","地质工程师","地质学","矿产资源勘查","地质资源与地质工程",
    "矿床学","地质编录","岩芯编录","矿山地质","探矿","地勘工程","储量估算")
PROBLEM=("应聘登记表","个人信息表","诚信承诺书","信息登记表","身份证","近亲属申报","入职申请")
def readcsv(p):
 with p.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def sha(b):return hashlib.sha256(b).hexdigest()
def filename_slug(a):
 return a["slug"] or a["title"]
def is_valid_image(path):
 try:
  with Image.open(path) as im:im.verify()
  with Image.open(path) as im:
   if im.width<140 or im.height<140:return None
   return im.width,im.height
 except Exception as e:raise RuntimeError(f"Corrupt image {path}: {e}")
def open_doc_text(path):
 ext=path.suffix.lower()
 try:
  if ext==".pdf":
   import fitz
   d=fitz.open(path)
   text=" ".join(p.get_text() for p in list(d)[:30])
   d.close();return text[:100000]
  if ext in (".xlsx",".xlsm"):
   book=load_workbook(path,read_only=True,data_only=True)
   result=[]
   for sheet in book.worksheets[:12]:
    for row in sheet.iter_rows(min_row=1,max_row=min(sheet.max_row or 1,1000),max_col=min(sheet.max_column or 1,45),values_only=True):
     result.extend(str(c) for c in row if c is not None)
   book.close()
   return " ".join(result)[:130000]
  if ext==".docx":
   import docx
   d=docx.Document(path)
   parts=[p.text for p in d.paragraphs]
   parts.extend(" ".join(c.text for c in row.cells) for t in d.tables for row in t.rows)
   return " ".join(parts)[:100000]
  if ext==".xls":return "" # Only keep old-format XLS when evidence from source already clear.
  if ext in (".zip",".pptx",".doc"):return ""
 except Exception as e:
  print("ATTACHMENT_TEXT_WARNING",path,str(e)[:80],flush=True)
 return ""
def file_type(p):
 ext=p.suffix.lower()
 if ext in (".png",".jpg",".jpeg",".webp",".gif",".tif",".tiff"):
  is_valid_image(p)
 elif ext==".pdf":
  import fitz
  d=fitz.open(p);assert d.page_count>0,p;d.close()
 elif ext in (".xlsx",".docx",".pptx",".zip"):
  assert zipfile.is_zipfile(p),p
 elif ext==".xls":
  assert p.stat().st_size>2000,p
 elif ext==".doc":
  assert p.stat().st_size>2000,p
 return ext

AUDIT=json.loads(A.read_text(encoding="utf-8"))
SRC={r["url"]:r for r in AUDIT}
SRC_BY_SLUG={filename_slug(r):r for r in AUDIT}
F_META=readcsv(F/"原始页面与图片来源索引.csv")
S_META=readcsv(INDEX)
entries=collections.defaultdict(list)
for r in F_META:
 url=r.get("原始发布页面","")
 if url not in SRC or r.get("类型","") not in F_BATCH_TYPES:continue
 p=Path(r.get("本地文件",""))
 if not p.is_file():raise FileNotFoundError(p)
 entries[url].append({
   "batch":"第一批", "type":F_BATCH_TYPES[r["类型"]],
   "path":p,"link":r.get("实际资源地址",url),"size":p.stat().st_size
 })
SECOND_PREFIXES={
 "Geo_Enterprise_Recruit_":"enterprise_recruit",
 "Geo_Institution_":"geology_institution_recruit",
 "Geo_Employment_Policy_Part_":"graduate_employment_policy",
 "Geo_IndustryPolicy_":"geological_industry_policy_data"
}
for r in S_META:
 url=r.get("原网页URL","")
 if url not in SRC:continue
 part=r["所在压缩包"].removesuffix(".zip")
 found=None
 for prefix,cat in SECOND_PREFIXES.items():
  if part.startswith(prefix):
   found=S/f"expanded-{cat}-part{part[len(prefix):]}"/r["文件名"]
   break
 if not found or not found.is_file():raise FileNotFoundError((r["所在压缩包"],r["文件名"]))
 if sha(found.read_bytes())!=r["SHA256"]:raise RuntimeError("Second-batch original hash mismatch "+str(found))
 entries[url].append({"batch":"第二批","type":r["文件类型"],
       "path":found,"link":r.get("原附件URL",url),"size":found.stat().st_size})
print("INPUT_FIRST_ASSETS",sum(len(v) for v in entries.values()),"SOURCE_URLS",len(entries),flush=True)

KEEP=[]
EXCLUDE=[]
ALL_FILES=[]
DIGESTS=set()
MISSING=[]
def ret_reason(a):
 if a["status"]!="保留":
  return a["reason"]
 slug=filename_slug(a)
 if slug not in ALLOWED:
  return DUPLICATES.get(slug,"已初步相关，但原件未提供明确对口岗位/存在重复或材料冗余，进一步精选剔除")
 if a["cat"] not in THEMES or slug not in WHITELIST.get(a["cat"],[]):
  return "类别不符合专业素材归档要求"
 return ""
def ranked_assets(src):
 """Keep ONE original full screenshot, or original viewport + useful original scroll.
 Other raw media screened by resolution, article relevance and attachment text.
 """
 screenshot=[s for s in src if s["type"] in SCREEN_TYPES]
 other=[s for s in src if s["type"] in ASSET_TYPES]
 # Prefer clearer higher-res second-batch browser full page when both batches exist.
 full=sorted((s for s in screenshot if s["type"]=="ORIGINAL_SITE_FULL"),
             key=lambda s:(s["batch"]=="第二批",s["size"]),reverse=True)
 if full:
  selected=[full[0]]
 else:
  viewport=sorted((s for s in screenshot if s["type"]=="ORIGINAL_SITE_VIEWPORT"),
                  key=lambda s:(s["batch"]=="第二批",s["size"]),reverse=True)
  selected=viewport[:1]
  scroll=[s for s in screenshot if s["type"]=="ORIGINAL_SITE_SCROLL"]
  selected+=sorted(scroll,key=lambda s:s["size"],reverse=True)[:2]
 # Explicit original media file filter.
 docs=sorted((s for s in other if s["type"]=="ORIGINAL_ATTACHMENT"),key=lambda s:s["size"],reverse=True)
 images=sorted((s for s in other if s["type"]=="ORIGINAL_WEBSITE_IMAGE"),key=lambda s:s["size"],reverse=True)
 if docs:
  for s in docs[:18]:
   doc_text=open_doc_text(s["path"])
   name=s["path"].name
   if any(t in name for t in PROBLEM):continue
   if s["path"].suffix.lower() in (".doc",".docx",".xls") and not any(t in doc_text for t in JOB_MATCH):
    continue
   if cat in ("enterprise_recruit","geology_institution_recruit"):
    # Avoid general group slides/form templates that do not identify a geological role.
    if not any(t in doc_text for t in JOB_MATCH):continue
   if cat=="field_photos":continue
   selected.append(s)
 if images:
  count=0
  for s in images:
   if count>=(5 if cat=="field_photos" else 3 if cat=="enterprise_recruit" else 2):break
   p=s["path"]
   wh=is_valid_image(p)
   if not wh:continue
   w,h=wh;ratio=w/h
   if cat=="enterprise_recruit" or cat=="geology_institution_recruit":
    # Tall high-res poster or long job-list original, not a company hero banner/QR code.
    if w<680 or h<800 or h/w<1.08:continue
   elif cat=="field_photos":
    if w<700 or h<390 or ratio<0.65 or ratio>3.4:continue
   else:
    if w<840 or h<450 or ratio<0.65 or ratio>3.6:continue
   selected.append(s);count+=1
 # Don't duplicate PDF pages if the actual original PDF exists; user can access original page.
 if not selected and src:
  selected=sorted(src,key=lambda s:s["size"],reverse=True)[:1]
 return selected

for a in AUDIT:
 slug=filename_slug(a)
 url=a["url"]
 why=ret_reason(a)
 if not why and url not in entries:why="本地文件不存在，未纳入"
 if why:
  EXCLUDE.append({"批次":a["batches"],"类别":a["cat"],"来源标题":a["title"],"原网页":url,"剔除原因":why})
  continue
 cat=a["cat"]
 originals=entries[url]
 kept=ranked_assets(originals)
 if not kept:
  EXCLUDE.append({"批次":a["batches"],"类别":cat,"来源标题":a["title"],"原网页":url,"剔除原因":"原始附件/图片不满足质量与专业相关性审核"})
  continue
 source_saved=[]
 for s in kept:
  orig=s["path"]
  b=orig.read_bytes()
  digest=sha(b)
  if digest in DIGESTS:continue
  DIGESTS.add(digest)
  typ=file_type(orig)
  path=WORK/THEMES[cat]/s["batch"]/(slug+"__"+orig.name)
  path.parent.mkdir(parents=True,exist_ok=True)
  path.write_bytes(b)
  assert sha(path.read_bytes())==digest
  source_saved.append(path)
  ALL_FILES.append({
   "类别":THEMES[cat],"批次":s["batch"],"原始页面":a["title"],
   "专业关联等级":a["grade"],"原始文件":str(orig),"筛后文件":str(path.relative_to(WORK)),
   "文件类型":s["type"],"字节数":len(b),"SHA256":digest,
   "原网页URL":url,"原附件URL":s.get("link",url),
   "精简说明":a["reason"]
  })
 if source_saved:
  KEEP.append({
    "批次":a["batches"],"类别":THEMES[cat],"专业关联等级":a["grade"],
    "原始来源标题":a["title"],"文件数":len(source_saved),
    "专业关联依据":a["reason"],
    "公告原文证据":a.get("excerpts","")[:390],
    "直接关联术语":a.get("exact_terms","") or a.get("primary","")[:210],
    "原网址":url,
    "图片或附件": " | ".join(x.name for x in source_saved[:3]),
    "slug":slug
  })
 else:
  EXCLUDE.append({"批次":a["batches"],"类别":cat,"来源标题":a["title"],
   "原网页":url,"剔除原因":"与其他来源文件内容完全相同，已按SHA256跨批去重"})

assert len(KEEP)>=24,(len(KEEP),KEEP)
assert len(ALL_FILES)>=40,len(ALL_FILES)
assert len(KEEP)+len(EXCLUDE)==len(AUDIT),(len(KEEP),len(EXCLUDE),len(AUDIT))
print("KEEP_SOURCES",len(KEEP),"EXCLUDED_SOURCES",len(EXCLUDE),"KEEP_FILES",len(ALL_FILES),
      "KEEP_MB",round(sum(x["字节数"] for x in ALL_FILES)/1048576,2),flush=True)
print("KEEP_CATEGORIES",dict(collections.Counter(a["类别"] for a in KEEP)),flush=True)
print("KEEP_ORIGIN_BATCHES",dict(collections.Counter(a["批次"] for a in ALL_FILES)),flush=True)
for a in KEEP:print("KEEP",a["批次"],a["类别"],a["slug"],"files",a["文件数"],flush=True)

# Write straightforward XLSX/CSV indexes; media remain untouched.
TABLES=DEST/"索引与审核记录";TABLES.mkdir(parents=True,exist_ok=True)
for name,rows in [("保留原始来源.csv",KEEP),("保留文件与哈希.csv",ALL_FILES),("剔除来源及理由.csv",EXCLUDE)]:
 if rows:
  with (TABLES/name).open("w",encoding="utf-8-sig",newline="") as f:
   cols=[c for c in rows[0] if c!="slug"]
   w=csv.DictWriter(f,fieldnames=cols,extrasaction="ignore");w.writeheader();w.writerows(rows)

wb=Workbook()
ws=wb.active;ws.title="保留资料来源"
keep_cols=["批次","类别","专业关联等级","原始来源标题","文件数","专业关联依据","公告原文证据","直接关联术语","原网址","图片或附件"]
ws.append(keep_cols)
for r in KEEP:
 ws.append([r.get(k,"") for k in keep_cols])
ex=wb.create_sheet("剔除来源及理由")
exc_cols=["批次","类别","来源标题","原网页","剔除原因"]
ex.append(exc_cols)
for r in EXCLUDE:ex.append([r.get(k,"") for k in exc_cols])
fs=wb.create_sheet("原始文件核对清单")
cols=["类别","批次","原始页面","专业关联等级","原始文件","筛后文件","文件类型","字节数","SHA256","原网页URL","原附件URL"]
fs.append(cols)
for r in ALL_FILES:fs.append([r.get(k,"") for k in cols])
sumws=wb.create_sheet("统计与筛选规则",0)
sumws.append(["资源勘查工程（固体）第一批+第二批 原始资料精选合集"])
sumws.append(["原始网页来源",len(AUDIT)])
sumws.append(["专业相关保留来源",len(KEEP)])
sumws.append(["剔除/合并来源",len(EXCLUDE)])
sumws.append(["已核验原始素材文件",len(ALL_FILES)])
sumws.append(["保留文件原始字节数",sum(r["字节数"] for r in ALL_FILES)])
sumws.append(["筛选标准","仅保留与固体矿产勘查、矿山地质技术、找矿、储量评价、岩芯编录等有明确关联的岗位、政策和工作现场原件"])
sumws.append(["排除标准","泛矿企校招、就业通用政策、偏油气/水文/地灾而无矿产对口岗位、重复公告、二维码和企业宣传横幅"])
sumws.append(["原图规则","网页截图、原图、原PDF、附件均保留采集时的原始字节；未重排、未修饰"])
sumws.append(["主题","有效原网页数","原始素材文件数"])
for theme in THEMES.values():
 sumws.append([theme,sum(1 for r in KEEP if r["类别"]==theme),sum(1 for r in ALL_FILES if r["类别"]==theme)])
for sheet in wb:
 sheet.sheet_view.showGridLines=False
 sheet.freeze_panes="C2"
 sheet.sheet_properties.pageSetUpPr.fitToPage=True
 sheet.row_dimensions[1].height=34
 for cell in sheet[1]:
  cell.fill=PatternFill("solid",fgColor="193A4D")
  cell.font=Font(name="微软雅黑",size=11,bold=True,color="FFFFFF")
  cell.alignment=Alignment(vertical="center",wrap_text=True)
 for row in sheet.iter_rows(min_row=2):
  for cell in row:
   cell.font=Font(name="微软雅黑",size=10,color="156A4E" if isinstance(cell.value,str) and cell.value.startswith(("https://","http://")) else "303B44")
   cell.alignment=Alignment(vertical="center",wrap_text=True)
   if isinstance(cell.value,str) and cell.value.startswith(("https://","http://")):cell.hyperlink=cell.value
 if sheet.title!="统计与筛选规则":sheet.auto_filter.ref=sheet.dimensions
 widths={
  "保留资料来源":[17,34,18,52,13,51,96,65,77,65],
  "剔除来源及理由":[18,31,57,87,83],
  "原始文件核对清单":[31,16,54,17,80,86,29,18,74,75,77],
  "统计与筛选规则":[38,25,25]
 }.get(sheet.title,[30])
 for i,w in enumerate(widths,1):sheet.column_dimensions[get_column_letter(i)].width=w
p=TABLES/"资源勘查工程_固体_两批原始素材_精选筛选索引.xlsx"
wb.save(p)
check=load_workbook(p,read_only=True)
assert check["保留资料来源"].max_row==len(KEEP)+1
assert check["原始文件核对清单"].max_row==len(ALL_FILES)+1
check.close()

# Fewer, larger thematic packages. Each ZIP is independently extractable and
# includes complete audit indexes. Aim >=35MB for all except last; never >70MB.
files_by_cat=collections.defaultdict(list)
for r in ALL_FILES:
 files_by_cat[r["类别"]].append((r,WORK/r["筛后文件"]))
ordered=[]
for theme in THEMES.values():
 ordered.extend(sorted(files_by_cat[theme],key=lambda f:(f[0]["原始页面"],f[0]["筛后文件"])))
TARGET=53_000_000
MAX=69_000_000
groups=[];batch=[];size=0
for r,f in ordered:
 n=f.stat().st_size
 if batch and size+n>TARGET:
  groups.append(batch);batch=[];size=0
 batch.append((r,f));size+=n
if batch:groups.append(batch)
# Avoid many tiny last bundles: safe merges preserve 69MB ceiling.
if len(groups)>=2 and sum(p.stat().st_size for _,p in groups[-1]) < 12_000_000:
 a=sum(p.stat().st_size for _,p in groups[-2]);b=sum(p.stat().st_size for _,p in groups[-1])
 if a+b<=MAX:
  groups[-2].extend(groups[-1]);groups.pop()
assert 1<=len(groups)<=5,len(groups)
zdir=DEST/"可下载精选压缩包";zdir.mkdir(parents=True,exist_ok=True)
report=[]
for i,group in enumerate(groups,1):
 label=f"资源勘查工程_固体_两批精选原始素材_第{i:02d}包.zip"
 zpath=zdir/label
 with zipfile.ZipFile(zpath,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=4,allowZip64=True) as z:
  for r,p in group:
   z.write(p,"两批精选原始素材/"+r["筛后文件"])
  for ind in TABLES.iterdir():
   if ind.is_file():z.write(ind,"两批精选原始素材/00_索引与审核记录/"+ind.name)
 # Validate every archive member decompresses intact and hash exactly matches source.
 with zipfile.ZipFile(zpath,"r") as z:
  bad=z.testzip()
  assert bad is None,(zpath,bad)
  for r,p in group:
   member="两批精选原始素材/"+r["筛后文件"]
   assert sha(z.read(member))==r["SHA256"],member
 total=sum(p.stat().st_size for _,p in group)
 report.append({
  "分卷":f"第{i:02d}包","文件":label,
  "原始文件数":len(group),"原始数据MB":round(total/1048576,2),
  "ZIP文件MB":round(zpath.stat().st_size/1048576,2),
  "涉及主题":"、".join(t for t in THEMES.values() if t in {r["类别"] for r,_ in group})
 })
 print("ZIP_CREATED",label,"FILES",len(group),"MB",round(zpath.stat().st_size/1048576,2),flush=True)
with (DEST/"分卷说明.json").open("w",encoding="utf-8") as f:json.dump(report,f,ensure_ascii=False,indent=2)
with (DEST/"分卷文件列表.csv").open("w",encoding="utf-8-sig",newline="") as f:
 w=csv.writer(f);w.writerow(["原始文件","所在压缩包"])
 for gi,group in enumerate(groups,1):
  for r,p in group:w.writerow([r["筛后文件"],report[gi-1]["文件"]])
print("CURATED_DONE",len(groups),"BUNDLES",len(KEEP),"SOURCES",len(ALL_FILES),"ORIGINAL_FILES",flush=True)
