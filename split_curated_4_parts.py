#!/usr/bin/env python3
"""Repackage the VERIFIED, unmodified 57 original source files into exactly four ZIPs.
No image generation, rendering, recompression of image pixels, or editing is performed.
The archives include the untouched original source files and original indexes.
"""
import csv
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

source = Path("input_archive")
outdir = Path("deliverables")
outdir.mkdir(parents=True, exist_ok=True)

source_zips = sorted(source.rglob("*.zip"))
if len(source_zips) != 1:
    raise RuntimeError(f"Expected exactly one validated original materials ZIP, got {len(source_zips)}: {source_zips}")
archive = source_zips[0]
print("INPUT_ARCHIVE", archive.name, archive.stat().st_size, flush=True)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def stringify_csv(rows):
    handle = io.StringIO()
    keys = ["文件来源","原始素材相对路径","材料类别","批次","SHA256","原文件字节数","原始网页"]
    writer = csv.DictWriter(handle, fieldnames=keys, lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({
            "文件来源": r["原始页面"],
            "原始素材相对路径": r["筛后文件"],
            "材料类别": r["类别"],
            "批次": r["批次"],
            "SHA256": r["SHA256"],
            "原文件字节数": r["字节数"],
            "原始网页": r["原网页URL"],
        })
    return handle.getvalue().encode("utf-8-sig")

with ZipFile(archive) as original:
    bad = original.testzip()
    if bad:
        raise RuntimeError("Original source ZIP has corrupt member: " + bad)

    names = set(original.namelist())
    root = "两批精选原始素材/"
    manifest_name = root + "00_索引与审核记录/保留文件与哈希.csv"
    if manifest_name not in names:
        raise RuntimeError("Missing official original per-file SHA256 index: " + manifest_name)
    rows = list(csv.DictReader(io.StringIO(original.read(manifest_name).decode("utf-8-sig"))))
    if len(rows) != 57:
        raise RuntimeError("Expected 57 original images/pages/PDFs, got " + str(len(rows)))

    media = []
    recorded_sha = set()
    for row in rows:
        relpath = row["筛后文件"].replace("\\", "/")
        member = root + relpath
        if member not in names:
            raise RuntimeError("Original content member absent: " + member)
        data = original.read(member)
        expect_size = int(row["字节数"])
        if len(data) != expect_size:
            raise RuntimeError(f"Incorrect size for {member}: {len(data)} vs {expect_size}")
        expected_sha = row["SHA256"]
        real_sha = digest(data)
        if real_sha != expected_sha:
            raise RuntimeError(f"SHA256 mismatch: {member}")
        if expected_sha in recorded_sha:
            raise RuntimeError("Duplicate media bytes in curated selection: "+member)
        recorded_sha.add(expected_sha)
        media.append((len(data), member, row))

    # Balanced bin packing: assign next-largest original file to the smallest bin.
    # This keeps exactly four downloads and avoids a large imbalance.
    bins = [[] for _ in range(4)]
    sizes = [0, 0, 0, 0]
    for size, member, row in sorted(media, key=lambda m: (-m[0], m[1])):
        i = min(range(4), key=lambda k: sizes[k])
        bins[i].append((size, member, row))
        sizes[i] += size

    if not all(bins):
        raise RuntimeError("One of four required ZIP parts would be empty")
    print("BALANCED_ORIGINAL_BYTES", sizes, flush=True)

    # Original audit/index files included unchanged in all parts.
    index_members = [m for m in sorted(names) if m.startswith(root + "00_索引与审核记录/") and not m.endswith("/")]
    if not index_members:
        raise RuntimeError("Index originals not available")

    created = []
    for part_i, group in enumerate(bins, 1):
        filename = f"Geo_Solid_Originals_Batch1_Batch2_Part_{part_i:02d}_of_04.zip"
        dst = outdir / filename
        rows_for_part = [r for _,_,r in group]

        with ZipFile(dst, mode="w", compression=ZIP_DEFLATED, compresslevel=4, allowZip64=True) as part:
            for size, member, row in sorted(group, key=lambda t: t[1]):
                part.writestr(member, original.read(member))
            for idxname in index_members:
                part.writestr(idxname, original.read(idxname))
            part.writestr(
                root + "00_索引与审核记录/本分包原始素材清单.csv",
                stringify_csv(rows_for_part)
            )
            part.writestr(
                root + "00_索引与审核记录/拆包说明.txt",
                (f"资源勘查工程（固体）第一批+第二批原始素材精选合并版\n"
                 f"分包：{part_i:02d}/04\n"
                 f"本包原始素材文件数：{len(group)}\n"
                 f"本包原始素材字节数：{sum(x[0] for x in group)}\n"
                 "四个ZIP独立解压，无需合并压缩卷。\n"
                 "四包合计57份原始素材，没有重新排版或修改源文件图像字节。\n"
                 "每包附完整保留/剔除审核索引和本分包文件索引。\n").encode("utf-8")
            )

        # Check ZIP itself and every unmodified source member after packaging.
        with ZipFile(dst) as check:
            err = check.testzip()
            if err is not None:
                raise RuntimeError("Invalid ZIP after splitting: " + err)
            for size, member, row in group:
                data = check.read(member)
                if len(data) != size or digest(data) != row["SHA256"]:
                    raise RuntimeError("A file changed or failed to unzip: " + member)
            part_rows = list(csv.DictReader(io.StringIO(check.read(
                root+"00_索引与审核记录/本分包原始素材清单.csv"
            ).decode("utf-8-sig"))))
            if len(part_rows) != len(group):
                raise RuntimeError("Part manifest count mismatch")
        info = {
            "part":part_i,
            "file":filename,
            "media_count":len(group),
            "original_media_bytes":sum(x[0] for x in group),
            "zip_bytes":dst.stat().st_size,
            "categories":dict((cat,sum(1 for _,_,r in group if r["类别"]==cat))
                              for cat in sorted({r["类别"] for _,_,r in group})),
            "sha256":digest(dst.read_bytes())
        }
        created.append(info)
        print("PACKAGE_VERIFIED",json.dumps(info,ensure_ascii=False),flush=True)

assert len(created)==4
assert sum(c["media_count"] for c in created)==57
assert sum(c["original_media_bytes"] for c in created)==sum(sizes)
if max(c["zip_bytes"] for c in created)>21*1024*1024:
    raise RuntimeError("A package unexpectedly exceeds 21MiB: "+str([c["zip_bytes"] for c in created]))
(outdir/"manifest_4_parts.json").write_text(json.dumps(created,ensure_ascii=False,indent=2),encoding="utf-8")
print("SUCCESS_FOUR_ZIPS",sum(c["media_count"] for c in created), flush=True)
