#!/usr/bin/env python3
"""Read-only PP Excel-vs-main reconciliation. Standard Python 3, no dependencies.

Run after audit_wps_pp_excel.py:
    python3 tools/compare_pp_source_to_main.py ~/Desktop/PP核对输出_新版/PP_source_audit.csv --out-dir ~/Desktop/PP差异核对

No changes are made to Excel, GitHub, images or site.
"""
import argparse
import collections
import csv
import json
import sys
from pathlib import Path
from urllib.request import urlopen

MAIN_URL = ("https://raw.githubusercontent.com/neil800518-bot/"
            "video-game-encyclopedia/main/data/games.json")
SPECIAL_NAMES = {
    "PP-0056": "王者野牛",
    "PP-0069": "王者野牛",
    "PP-0195": "阿茲特克国王",
    "PP-0201": "阿茲特克国王",
    "PP-0180": "疯狂大鲈鱼",
    "PP-0204": "疯狂大鲈鱼",
    "PP-0497": "超疯狂大鲈鱼溅水",
    "PP-0604": "财神聚宝盆",
    "PP-0166": "巨大犀牛 加强版",
    "PP-0342": "火箭弹爆破 Megaways™",
    "PP-0589": "幸运福鼓88",
}
EXPECTED_DUPLICATES = [
    ("王者野牛", {"PP-0056", "PP-0069"}),
    ("阿茲特克国王", {"PP-0195", "PP-0201"}),
    ("疯狂大鲈鱼", {"PP-0180", "PP-0204"}),
]

def load_main(path):
    if path is not None:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    with urlopen(MAIN_URL, timeout=25) as response:
        return json.load(response)

def load_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))

def compare(src, main):
    current = [x for x in main if x.get("provider") == "PP"]
    by_name = collections.defaultdict(list)
    for x in src:
        by_name[x.get("name", "")].append(x)
    by_id = {x.get("excel_id"): x for x in src}
    old_rows = []
    for old in current:
        options = by_name[old.get("name", "")]
        old_id = old["id"]
        if len(options) == 1:
            status = "EXACT_NAME_UNIQUE"
            target = options[0]["excel_id"]
        elif len(options) > 1:
            status = "DUPLICATE_NAME_NEEDS_IMAGE_REVIEW"
            target = ""
        else:
            status = "NO_EXACT_NAME_MATCH"
            target = ""
        old_rows.append(dict(old_id=old_id, old_name=old.get("name", ""),
                             old_image=old.get("image", ""),
                             match_status=status,
                             excel_candidate_ids=";".join(x["excel_id"] for x in options),
                             suggested_new_id=target,
                             shifted=("YES" if target and target != old_id else
                                      "NO" if target else "REVIEW")))
    src_rows = []
    for x in src:
        game_id=x.get("excel_id", "")
        flags=[f for f in x.get("flags", "").split(";") if f]
        if not x.get("sha256"): flags.append("IMAGE_NOT_RESOLVED")
        if game_id in SPECIAL_NAMES and x.get("name") != SPECIAL_NAMES[game_id]:
            flags.append("NAME_DIFFERS_FROM_USER_CONFIRMED")
        if game_id == "PP-0604":
            flags = [f for f in flags if f != "NAME_MISMATCH_WITH_CONFIRMED_CORRECTION"]
            flags.append("IMAGE_VISUALLY_REVIEWED_CASH_POTS")
            flags.append("IMAGE_ORIGIN_SHA_STILL_NEEDS_VERIFICATION")
        src_rows.append(dict(x, audit_status=";".join(dict.fromkeys(flags))))
    duplicate_rows=[]
    for name, required in EXPECTED_DUPLICATES:
        group=by_name.get(name, [])
        ids={x["excel_id"] for x in group}
        hashes={x.get("sha256", "") for x in group}
        duplicate_rows.append(dict(name=name, ids=";".join(sorted(ids)),
                                  expected_ids=";".join(sorted(required)),
                                  ids_ok=(ids == required),
                                  images_distinct=(len(hashes) == len(group) and
                                                   bool(group) and "" not in hashes)))
    unique_matches=[x for x in old_rows if x["match_status"]=="EXACT_NAME_UNIQUE"]
    report=dict(excel_count=len(src),excel_unique_ids=len(by_id),
                main_pp_count=len(current),
                main_pp_with_images=sum(bool(x.get("image")) for x in current),
                unique_exact_name_matches=len(unique_matches),
                shifted_exact_matches=sum(x["shifted"]=="YES" for x in unique_matches),
                duplicate_name_old_matches=sum(
                    x["match_status"]=="DUPLICATE_NAME_NEEDS_IMAGE_REVIEW" for x in old_rows),
                non_exact_name_old_matches=sum(
                    x["match_status"]=="NO_EXACT_NAME_MATCH" for x in old_rows),
                net_extra_excel_positions=len(src)-len(current),
                pp_0604=dict(by_id.get("PP-0604", {})),
                expected_duplicate_checks=duplicate_rows,
                problems=[x for x in src_rows if
                          "NAME_DIFFERS_FROM_USER_CONFIRMED" in x["audit_status"]
                          or "IMAGE_NOT_RESOLVED" in x["audit_status"]])
    return old_rows,src_rows,report

def write_csv(path,rows):
    if not rows: return
    fields=list(rows[0].keys())
    with path.open("w",encoding="utf-8-sig",newline="") as handle:
        w=csv.DictWriter(handle,fieldnames=fields,extrasaction="ignore")
        w.writeheader();w.writerows(rows)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("source_csv",type=Path)
    p.add_argument("--main-json",type=Path,
                   help="Optional local main games.json instead of downloading")
    p.add_argument("--out-dir",type=Path,default=Path("PP差异核对"))
    args=p.parse_args()
    rows=load_csv(args.source_csv)
    main_data=load_main(args.main_json)
    old_rows,src_rows,report=compare(rows,main_data)
    args.out_dir.mkdir(parents=True,exist_ok=True)
    write_csv(args.out_dir/"PP_324旧资料到新版ID候选.csv",old_rows)
    write_csv(args.out_dir/"PP_610最新版记录与风险.csv",src_rows)
    (args.out_dir/"PP_对照汇总.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("PP Excel:",report["excel_count"],"unique IDs:",report["excel_unique_ids"])
    print("GitHub main PP:",report["main_pp_count"],
          "with images:",report["main_pp_with_images"])
    print("Name-unique matches:",report["unique_exact_name_matches"])
    print("Shifted matches:",report["shifted_exact_matches"])
    print("Old records needing manual name/image check:",
          report["duplicate_name_old_matches"]+report["non_exact_name_old_matches"])
    print("PP-0604:",report["pp_0604"].get("name"),
          report["pp_0604"].get("sha256","")[:16])
    print("Results:",args.out_dir)
    if report["excel_count"]!=610 or report["excel_unique_ids"]!=610:
        print("WARNING: Expected 610 distinct PP IDs",file=sys.stderr)
        return 2
    if report["problems"]:
        print("WARNING: source has unresolved images or confirmed-name mismatches",
              file=sys.stderr)
        return 3
    return 0

if __name__=="__main__":
    sys.exit(main())
