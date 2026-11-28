#!/usr/bin/env python3
"""Prepare 560 PP images + linked games.json for PR #71, without pushing anything.

Preconditions:
  1. Run audit_wps_pp_excel.py with --all-images on the current workbook.
  2. Use its original_images folder and PP_source_audit.csv as inputs.
  3. This script downloads the Draft staging data/games.json read-only.
Example:
  python3 tools/prepare_pp_610_images.py \
    --audit-csv "$HOME/Desktop/PP核对输出_全部/PP_source_audit.csv" \
    --image-dir "$HOME/Desktop/PP核对输出_全部/original_images" \
    --out-dir "$HOME/Desktop/PP-610-待提交"

It creates out-dir/data/games.json plus 560 images in out-dir/data/images.
Do NOT merge staging PR before uploading and verifying all images.
"""
import argparse
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path
from urllib.request import urlopen

SOURCE = ("https://raw.githubusercontent.com/neil800518-bot/"
          "video-game-encyclopedia/data-pp-610-staging-20261128/data/games.json")
EXPECTED_PP = 610
EXPECTED_STAGED = 1560
PRESERVE_FIRST = 50

def parse_csv(file):
    with file.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--audit-csv",type=Path,required=True)
    p.add_argument("--image-dir",type=Path,required=True)
    p.add_argument("--out-dir",type=Path,required=True)
    p.add_argument("--staging-json",type=Path,
                   help="Local PR #71 data/games.json alternative (offline mode)")
    args=p.parse_args()
    rows=parse_csv(args.audit_csv)
    if len(rows)!=EXPECTED_PP:
        p.error("Expected exactly 610 CSV rows, got {}".format(len(rows)))
    byid={x.get("excel_id"):x for x in rows}
    if len(byid)!=EXPECTED_PP:
        p.error("Duplicate or missing Excel IDs")
    for i in range(1,EXPECTED_PP+1):
        key="PP-{:04d}".format(i)
        if key not in byid:
            p.error("Missing Excel ID {}".format(key))
    if args.staging_json:
        records=json.loads(args.staging_json.read_text(encoding="utf-8-sig"))
    else:
        with urlopen(SOURCE,timeout=30) as response:
            records=json.load(response)
    if len(records)!=EXPECTED_STAGED:
        p.error("Staging JSON expected 1560 records, got {}".format(len(records)))
    pp=[x for x in records if x.get("provider")=="PP"]
    if len(pp)!=EXPECTED_PP:
        p.error("Expected 610 PP records in staging JSON")
    lookup={x["id"]:x for x in pp}
    checked=[]
    # Validate all sources BEFORE writing any image, including 50 unchanged games.
    for i in range(1, EXPECTED_PP+1):
        id="PP-{:04d}".format(i)
        row=byid[id]
        record=lookup.get(id)
        if not record or record["name"]!=row["name"]:
            p.error("Staging game name mismatch: {}".format(id))
        if record.get("source_image_id")!=row.get("source_image_id"):
            p.error("Source image ID mismatch: {}".format(id))
        if i<=PRESERVE_FIRST:
            if not record.get("image") or record.get("image_status")!="已有图片":
                p.error("Cannot preserve existing original PP image: {}".format(id))
            continue
        if not row.get("sha256") or not row.get("image_member"):
            p.error("Unresolved source image for {}".format(id))
        extension=Path(row["image_member"]).suffix.lower()
        if extension not in (".png",".jpg",".jpeg",".webp"):
            p.error("Unsupported image extension for {}: {}".format(id,extension))
        source=args.image_dir/(id+extension)
        if not source.is_file():
            p.error("Image missing: {}".format(source))
        raw=source.read_bytes()
        h=hashlib.sha256(raw).hexdigest()
        if h.lower()!=row["sha256"].lower():
            p.error("SHA-256 mismatch for {}: {}".format(id,source))
        if row.get("dimensions") and row["dimensions"]!="375x667":
            p.error("Unexpected dimensions for {}: {}".format(id,row["dimensions"]))
        checked.append((id,source,extension,len(raw),h))
    if len(checked)!=560:
        p.error("Expected 560 validated images, got {}".format(len(checked)))

    dest=args.out_dir
    if dest.exists() and any(dest.iterdir()):
        p.error("Destination exists and is not empty: {}".format(dest))
    data_dir=dest/"data"
    images_dir=data_dir/"images"
    images_dir.mkdir(parents=True,exist_ok=True)
    for id,source,extension,size,hashvalue in checked:
        filename=id+extension
        shutil.copyfile(source, images_dir/filename)
        item=lookup[id]
        item["image"]=filename
        item["image_status"]="已有图片"
    (data_dir/"games.json").write_text(
        json.dumps(records,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    manifest=dest/"PP_560图片校验清单.csv"
    with manifest.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.writer(f)
        writer.writerow(["id","filename","bytes","sha256","source_image_id","name"])
        for id,source,extension,size,hashvalue in checked:
            writer.writerow([id,id+extension,size,hashvalue,
                             lookup[id]["source_image_id"],lookup[id]["name"]])
    print("SUCCESS: validated and prepared 560 unique images.")
    print("PP games total:",len(pp),"PP now with image fields:",sum(bool(x.get("image")) for x in pp))
    print("Other-provider games:",len(records)-len(pp))
    print("Upload target: PR #71 branch data-pp-610-staging-20261128")
    print("Prepared files:",dest)
    print("WARNING: No GitHub upload has occurred; PR must stay Draft.")
    return 0

if __name__=="__main__":
    sys.exit(main())
