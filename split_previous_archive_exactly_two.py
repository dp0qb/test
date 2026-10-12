#!/usr/bin/env python3
"""Split validated first+second-batch original website archive into exactly two
balanced independent ZIP-download artifact directories.

Every screenshot, original photo, attachment and PDF preserves its exact bytes.
No image is generated or changed. Source grouped together across the split.
"""
import csv, hashlib, io, os, re, shutil, zipfile, collections
from pathlib import Path
from PIL import Image

SRC = Path("prior_archive")
DST = Path("two_downloads")
files=list(SRC.glob("*.zip"))
assert len(files)==1, f"Expected exactly one prior ZIP inside artifact: {files}"
original_archive=files[0]
assert original_archive.stat().st_size>30_000_000
BASE="两批精选原始素材/"
INDEXPREFIX=BASE+"00_索引与审核记录/"
ITEMS_CSV=INDEXPREFIX+"保留文件与哈希.csv"

def sha(b): return hashlib.sha256(b).hexdigest()
def verify_file(n,b):
    if n.lower().endswith((".png",".jpg",".jpeg",".webp",".gif")):
        with Image.open(io.BytesIO(b)) as im: im.verify()
    if n.lower().endswith(".pdf"):
        import fitz
        pdf=fitz.open(stream=b,filetype="pdf")
        assert len(pdf)>=1
        pdf.close()

with zipfile.ZipFile(original_archive,"r") as z:
    assert z.testzip() is None, "Original ZIP CRC failed"
    members={i.filename:i for i in z.infolist() if not i.is_dir()}
    media={k:v for k,v in members.items() if k.startswith(BASE) and not k.startswith(INDEXPREFIX)}
    metadata={k:v for k,v in members.items() if k.startswith(INDEXPREFIX)}
    assert ITEMS_CSV in metadata
    assert len(media)==57,(len(media),sorted(media)[:5])
    idxdata=z.read(ITEMS_CSV)
    idx=list(csv.DictReader(io.TextIOWrapper(io.BytesIO(idxdata),encoding="utf-8-sig")))
    assert len(idx)==57,len(idx)
    checks={}
    groups=collections.defaultdict(list)
    for row in idx:
        full=BASE+row["筛后文件"]
        assert full in media,full
        content=z.read(full)
        assert sha(content)==row["SHA256"], full
        assert len(content)==int(row["字节数"]), full
        verify_file(full,content)
        groups[(row["原始页面"],row["类别"])].append((full,content,row))
        checks[full]=content
    assert len(checks)==len(media),"Extraneous media found, recheck inventory"
    # Pack whole source pages with their original attachments in the same package.
    units=sorted(groups.items(),key=lambda x:sum(len(item[1]) for item in x[1]),reverse=True)
    bins=[[],[]]
    totals=[0,0]
    for srcgroup,mediaitems in units:
        side=0 if totals[0]<=totals[1] else 1
        bins[side].extend(mediaitems)
        totals[side]+=sum(len(item[1]) for item in mediaitems)
    assert len(bins[0])>0 and len(bins[1])>0
    assert len(bins[0])+len(bins[1])==57
    assert max(totals)<34_000_000,(totals,"File size unusually imbalanced")
    # Each independent artifact includes complete source/audit indexes, even though
    # only relevant originals for that half are present.
    allmd={path:z.read(path) for path in metadata}

for n,items in enumerate(bins,1):
    out=DST/f"part{n:02d}"
    out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for file_path,content,row in items:
        file=out/file_path
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_bytes(content)
        assert sha(file.read_bytes())==row["SHA256"]
        rows.append(row)
    for name,data in allmd.items():
        f=out/name
        f.parent.mkdir(parents=True,exist_ok=True)
        f.write_bytes(data)
    # Add a part-specific index (the complete index is preserved unmodified too).
    outname=out/INDEXPREFIX/f"本卷文件目录_第{n:02d}包.csv"
    with outname.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    # The GitHub Actions artifact ZIP is the downloadable ZIP itself,
    # rather than ZIP-inside-another-ZIP.
    original=[p for p in out.rglob("*") if p.is_file() and str(p.relative_to(out)).startswith(BASE)]
    mediafiles=[p for p in original if not str(p.relative_to(out)).startswith(INDEXPREFIX)]
    assert len(mediafiles)==len(items)
    for file_path,content,row in items:
        assert sha((out/file_path).read_bytes())==row["SHA256"]
    print("PART_VERIFIED",n,"MEDIA",len(items),"ORIGINAL_MEDIA_BYTES",totals[n-1],"TOTAL_BYTES",sum(p.stat().st_size for p in original),flush=True)
assert abs(totals[0]-totals[1])<12_000_000,totals
print("SPLIT_SUCCESS","ORIGINAL_FILE_COUNT",len(checks),"PART_COUNTS",[len(x) for x in bins],
      "PART_BYTES",totals,"SOURCE_GROUPS",len(groups),flush=True)
