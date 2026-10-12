#!/usr/bin/env python3
"""Split verified ORIGINAL browser screenshots and files into directly downloadable small bundles.

Does not render, modify, re-layout or generate any image.
"""
from pathlib import Path
import csv, hashlib, os, shutil, sys
from PIL import Image

SOURCE = Path("original_sources")
PARTS = Path("parts")
PARTS.mkdir(exist_ok=True)
TARGET_BYTES = 14_000_000
CATEGORIES = ("policy", "recruit", "field")
VALID_EXT = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}
BUNDLES = []
REJECTED = []

def verify(path):
    if path.stat().st_size <= 1000:
        return "empty/too small"
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            import fitz
            doc = fitz.open(path)
            if doc.page_count < 1:
                return "PDF has no pages"
            doc.close()
        else:
            with Image.open(path) as im:
                im.verify()
            with Image.open(path) as im:
                if im.width < 150 or im.height < 150:
                    return "image dimensions too small"
    except Exception as e:
        return str(e)[:120]
    return ""

for cat in CATEGORIES:
    files = sorted(
        (p for p in (SOURCE / cat).rglob("*")
         if p.is_file() and p.suffix.lower() in VALID_EXT),
        key=lambda p:p.name.lower())
    batch = []
    batch_bytes = 0
    for p in files:
        error = verify(p)
        if error:
            REJECTED.append((str(p),error))
            continue
        size = p.stat().st_size
        if batch and batch_bytes + size > TARGET_BYTES:
            BUNDLES.append((cat, batch))
            batch = []
            batch_bytes = 0
        batch.append(p)
        batch_bytes += size
    if batch:
        BUNDLES.append((cat,batch))

if not BUNDLES:
    raise RuntimeError("No verified source media available.")

summary = []
for i,(category,files) in enumerate(BUNDLES,1):
    label = f"part{i:02d}"
    dst = PARTS / label
    dst.mkdir(parents=True,exist_ok=True)
    manifest_rows = []
    for p in files:
        rel = p.relative_to(SOURCE.parent)
        out = dst / rel
        out.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,out)
        data = out.read_bytes()
        manifest_rows.append([str(rel),len(data),hashlib.sha256(data).hexdigest()])
    src_index = SOURCE/"原始页面与图片来源索引.csv"
    if src_index.is_file():
        shutil.copy2(src_index,dst/"原始页面与图片来源索引.csv")
    with (dst/"文件哈希核验.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f)
        w.writerow(["relative_path","size_bytes","sha256"])
        w.writerows(manifest_rows)
    types={}
    for p in files:
        typ=p.suffix.lower()
        types[typ]=types.get(typ,0)+1
    note = f"""资源勘查工程原始网页界面与图片素材 / {label}
原始类别: {category}
本卷文件数量: {len(files)}
未经修饰的原始截图、原始网页图片或原始PDF。
请以“原始页面与图片来源索引.csv”查询原发布网页。
以“文件哈希核验.csv”中的SHA256校验文件完整性。
这份文件包不包含生成图片、重新排版宣传页或示意图。
"""
    (dst/"README_下载内容说明.txt").write_text(note,encoding="utf-8")
    summary.append((label,category,len(files),sum(p.stat().st_size for p in files),types))

with (PARTS/"ALL_PARTS_MANIFEST.csv").open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.writer(f)
    w.writerow(["part","category","count","original_media_bytes","media_types"])
    for label,category,n,bytes_,types in summary:
        w.writerow([label,category,n,bytes_,str(types)])
if REJECTED:
    (PARTS/"REJECTED_FILES.txt").write_text(
        "\n".join(f"{p} : {why}" for p,why in REJECTED),encoding="utf-8")
print("BUNDLE_SUMMARY_START")
for x in summary:
    print(*x,sep="\t")
print("BUNDLE_SUMMARY_END")
print("TOTAL_FILES",sum(x[2] for x in summary))
print("TOTAL_SOURCE_BYTES",sum(x[3] for x in summary))
print("REJECTED",len(REJECTED))
if len(summary)>12:
    raise RuntimeError("Over 12 bundles; increase upload steps before running.")
