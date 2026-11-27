#!/usr/bin/env python3
"""Read WPS DISPIMG images from an XLSX without changing the workbook.

Usage:
  python3 tools/audit_wps_pp_excel.py "/path/电子游戏百科(6).xlsx" \
    --out-dir "/path/PP核对输出"

Creates PP_source_audit.csv and extracts selected original PP pictures.
No third-party dependencies. In particular, never assume equal names mean
equal pictures: inspect hashes and the extracted files.
"""
import argparse
import collections
import csv
import hashlib
import posixpath
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFREL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKGREL = "http://schemas.openxmlformats.org/package/2006/relationships"
EMBED = "{" + OFFREL + "}embed"
ID_PATTERN = re.compile(r"ID_[0-9A-Fa-f]{20,}")
CELL_PATTERN = re.compile(r"^([A-Z]+)([0-9]+)$")
DEFAULT_IDS = {56, 69, 166, 180, 195, 201, 204, 342, 497, 589, 604}


def tag_name(elem):
    return elem.tag.rsplit("}", 1)[-1]


def resolve_path(base_path, relative):
    if relative.startswith("/"):
        return relative.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(base_path), relative))


def relmap(z, xml_name):
    prefix, name = posixpath.split(xml_name)
    rels_path = posixpath.join(prefix, "_rels", name + ".rels")
    if rels_path not in z.namelist():
        return {}
    root = ET.fromstring(z.read(rels_path))
    result = {}
    for rel in root:
        if tag_name(rel) != "Relationship" or rel.get("TargetMode") == "External":
            continue
        result[rel.get("Id")] = resolve_path(xml_name, rel.get("Target", ""))
    return result


def shared_strings(z):
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join((t.text or "") for t in si.iter() if tag_name(t) == "t")
            for si in root if tag_name(si) == "si"]


def worksheet_path(z, display_name):
    root = ET.fromstring(z.read("xl/workbook.xml"))
    relationships = relmap(z, "xl/workbook.xml")
    for elem in root.iter():
        if tag_name(elem) != "sheet" or elem.get("name") != display_name:
            continue
        rel_id = elem.get("{" + OFFREL + "}id")
        target = relationships.get(rel_id)
        if not target:
            raise ValueError("Cannot resolve relationship for sheet " + display_name)
        return target
    raise ValueError("Workbook has no worksheet named " + display_name)


def sheet_cells(z, path, sst):
    root = ET.fromstring(z.read(path))
    data = {}
    for c in root.iter():
        if tag_name(c) != "c" or not c.get("r"):
            continue
        v = c.find("{" + MAIN + "}v")
        f = c.find("{" + MAIN + "}f")
        inline = c.find("{" + MAIN + "}is")
        if f is not None and f.text:
            formula = "=" + f.text
        else:
            formula = ""
        if c.get("t") == "s" and v is not None and v.text is not None:
            value = sst[int(v.text)]
        elif c.get("t") == "inlineStr" and inline is not None:
            value = "".join(t.text or "" for t in inline.iter()
                            if tag_name(t) == "t")
        elif v is not None and v.text is not None:
            value = v.text
        elif inline is not None:
            value = "".join(t.text or "" for t in inline.iter()
                            if tag_name(t) == "t")
        else:
            value = ""
        data[c.get("r")] = (value, formula)
    return data


def image_index(z):
    candidates = [n for n in z.namelist()
                  if n.endswith("/cellimages.xml") or n == "xl/cellimages.xml"]
    if not candidates:
        raise ValueError("WPS cellimages.xml is not present; image IDs cannot be mapped.")
    path = candidates[0]
    rels = relmap(z, path)
    root = ET.fromstring(z.read(path))
    mapping = {}
    for block in root.iter():
        if tag_name(block) != "cellImage":
            continue
        ids = []
        embeds = []
        for elem in block.iter():
            for key, value in elem.attrib.items():
                if not isinstance(value, str):
                    continue
                ids.extend(ID_PATTERN.findall(value))
                if key == EMBED:
                    embeds.append(value)
        embeds = list(dict.fromkeys(embeds))
        for image_id in dict.fromkeys(ids):
            if len(embeds) == 1 and embeds[0] in rels:
                mapping[image_id.upper()] = rels[embeds[0]]
    if not mapping:
        raise ValueError("cellimages.xml found, but image ID relationships were not resolved.")
    return mapping


def number_from_position(col, number_row):
    ncol = 0
    for ch in col:
        ncol = ncol * 26 + (ord(ch) - ord("A") + 1)
    return ((number_row - 2) // 4) * 10 + ncol


def image_dimensions(blob, extension):
    if extension == ".png" and blob[:8] == b"\x89PNG\r\n\x1a\n" and len(blob) >= 24:
        return "{}x{}".format(int.from_bytes(blob[16:20], "big"),
                              int.from_bytes(blob[20:24], "big"))
    return "not checked"


def audit(input_path, out_dir, extract_ids):
    out_dir.mkdir(parents=True, exist_ok=True)
    img_dir = out_dir / "original_images"
    img_dir.mkdir(exist_ok=True)
    rows = []
    with zipfile.ZipFile(input_path) as z:
        strings = shared_strings(z)
        sheet = sheet_cells(z, worksheet_path(z, "PP电子"), strings)
        images = image_index(z)
        used_image = set()
        for ref, (value, formula) in sheet.items():
            found = ID_PATTERN.search(formula)
            if not found or "DISPIMG" not in formula.upper():
                continue
            match = CELL_PATTERN.match(ref)
            if not match:
                continue
            col, row_s = match.groups()
            row = int(row_s)
            num_ref = col + str(row + 1)
            name_ref = col + str(row + 2)
            name = sheet.get(name_ref, ("", ""))[0].strip()
            if not name:
                continue
            number = number_from_position(col, row + 1)
            id_number = sheet.get(num_ref, ("", ""))[0].strip()
            image_id = found.group(0).upper()
            member = images.get(image_id, "")
            problems = []
            if id_number.isdigit() and int(id_number) != number:
                problems.append("NUMERIC_ID_CONFLICT")
            if not member or member not in z.namelist():
                problems.append("UNRESOLVED_IMAGE_ID")
            if number < 1 or number > 610:
                problems.append("OUTSIDE_1_610")
            if number in used_image:
                problems.append("DUPLICATE_NUMBER")
            used_image.add(number)
            sha, dimensions, length = "", "", 0
            if member and member in z.namelist():
                blob = z.read(member)
                sha = hashlib.sha256(blob).hexdigest()
                length = len(blob)
                extension = Path(member).suffix.lower()
                dimensions = image_dimensions(blob, extension)
                if number in extract_ids:
                    fname = "PP-{:04d}{}".format(number, extension or ".bin")
                    (img_dir / fname).write_bytes(blob)
            if number == 604:
                problems.append("IMAGE_MANUAL_REVIEW_REQUIRED")
                if name != "疯狂大鲈鱼欢乐爆发 1000":
                    problems.append("NAME_MISMATCH_WITH_CONFIRMED_CORRECTION")
            rows.append(dict(
                excel_id="PP-{:04d}".format(number),
                name=name, name_cell=name_ref, number_cell=num_ref,
                number_cached=id_number, image_cell=ref, source_image_id=image_id,
                image_member=member, bytes=length, dimensions=dimensions,
                sha256=sha, flags=";".join(problems)))
    rows.sort(key=lambda r: r["excel_id"])
    csv_path = out_dir / "PP_source_audit.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    unique = {r["excel_id"] for r in rows}
    name_groups = collections.defaultdict(list)
    for r in rows:
        name_groups[r["name"]].append(r)
    print("Entries:", len(rows), "/ Expected: 610")
    print("Unique IDs:", len(unique))
    print("Resolved images:", sum(bool(r["sha256"]) for r in rows))
    print("Images extracted:", len(list(img_dir.iterdir())))
    for name in ("王者野牛", "阿茲特克国王", "疯狂大鲈鱼", "超疯狂大鲈鱼溅水"):
        print("\n", name)
        for row in name_groups.get(name, []):
            print(" ", row["excel_id"], row["dimensions"],
                  row["sha256"][:16], row["flags"])
    for r in rows:
        if r["excel_id"] == "PP-0604":
            print("\nPP-0604:", r)
    print("\nCSV:", csv_path)
    if len(rows) != 610 or len(unique) != 610:
        print("WARNING: PP row count/ID validation FAILED", file=sys.stderr)
        return 2
    if any("UNRESOLVED_IMAGE_ID" in r["flags"] for r in rows):
        print("WARNING: some image IDs are unresolved", file=sys.stderr)
        return 3
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xlsx", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("PP_excel_audit"))
    parser.add_argument("--all-images", action="store_true",
                        help="Extract all 610 original images, not just 11 review images")
    args = parser.parse_args()
    if not args.xlsx.is_file():
        parser.error("Excel file not found: {}".format(args.xlsx))
    return audit(args.xlsx, args.out_dir,
                 set(range(1, 611)) if args.all_images else DEFAULT_IDS)


if __name__ == "__main__":
    sys.exit(main())
