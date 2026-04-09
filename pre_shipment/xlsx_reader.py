"""Very small XLSX reader based on XML inside the .xlsx zip container."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

MAIN_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
PACKAGE_REL_NS = {
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}


@dataclass
class SheetRow:
    row_number: int
    values: list[str]


@dataclass
class SheetData:
    name: str
    rows: list[SheetRow]


@dataclass
class WorkbookData:
    path: Path
    sheets: list[SheetData]

    @property
    def name(self) -> str:
        return self.path.name


def iter_workbooks(root: Path) -> Iterable[Path]:
    for path in sorted(root.glob("*.xlsx")):
        if path.name.startswith("~$"):
            continue
        yield path


def read_workbook(path: Path, max_cols: int = 40) -> WorkbookData:
    with zipfile.ZipFile(path) as archive:
        shared_strings = _parse_shared_strings(archive)
        sheet_map = _parse_workbook_sheet_map(archive)
        sheets = [
            SheetData(
                name=sheet_name,
                rows=_parse_sheet_rows(archive, sheet_path, shared_strings, max_cols=max_cols),
            )
            for sheet_name, sheet_path in sheet_map
        ]
    return WorkbookData(path=path, sheets=sheets)


def _parse_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    shared_strings_path = "xl/sharedStrings.xml"
    if shared_strings_path not in archive.namelist():
        return []

    root = ET.fromstring(archive.read(shared_strings_path))
    values: list[str] = []
    for item in root.findall("a:si", MAIN_NS):
        parts = [node.text or "" for node in item.iterfind(".//a:t", MAIN_NS)]
        values.append("".join(parts))
    return values


def _parse_workbook_sheet_map(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
    rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_root.findall("pr:Relationship", PACKAGE_REL_NS)
    }

    sheets: list[tuple[str, str]] = []
    for sheet in workbook_root.findall("a:sheets/a:sheet", MAIN_NS):
        rel_id = sheet.attrib[
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        ]
        target = rel_map[rel_id]
        if not target.startswith("worksheets/"):
            target = f"worksheets/{Path(target).name}"
        sheets.append((sheet.attrib["name"], f"xl/{target}"))
    return sheets


def _parse_sheet_rows(
    archive: zipfile.ZipFile,
    sheet_path: str,
    shared_strings: list[str],
    max_cols: int,
) -> list[SheetRow]:
    root = ET.fromstring(archive.read(sheet_path))
    rows: list[SheetRow] = []

    for row in root.findall("a:sheetData/a:row", MAIN_NS):
        cells: dict[int, str] = {}
        for cell in row.findall("a:c", MAIN_NS):
            ref = cell.attrib.get("r", "")
            match = re.match(r"([A-Z]+)(\d+)", ref)
            if not match:
                continue

            col_index = _col_letters_to_index(match.group(1))
            if col_index >= max_cols:
                continue

            value = _cell_text(cell, shared_strings)
            if value != "":
                cells[col_index] = value

        if not cells:
            continue

        max_index = max(cells)
        values = [cells.get(i, "").strip() for i in range(max_index + 1)]
        rows.append(SheetRow(row_number=int(row.attrib.get("r", "0")), values=values))

    return rows


def _col_letters_to_index(col_letters: str) -> int:
    total = 0
    for char in col_letters:
        total = total * 26 + (ord(char.upper()) - 64)
    return total - 1


def _cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")

    if cell_type == "inlineStr":
        text_node = cell.find("a:is/a:t", MAIN_NS)
        return (text_node.text or "").strip() if text_node is not None else ""

    value_node = cell.find("a:v", MAIN_NS)
    if value_node is None or value_node.text is None:
        return ""

    raw = value_node.text.strip()
    if cell_type == "s":
        try:
            return shared_strings[int(raw)].strip()
        except (IndexError, ValueError):
            return raw
    return _normalize_numeric_text(raw)


def _normalize_numeric_text(raw: str) -> str:
    text = (raw or "").strip()
    if not re.fullmatch(r"-?\d+\.\d+", text):
        return text

    whole, fraction = text.split(".", 1)
    if len(fraction) <= 6:
        return text

    # XLSX numeric cells sometimes surface binary-float artifacts such as
    # 2.0699999999999998 for a human-entered value like 2.07.
    normalized = f"{float(text):.6f}".rstrip("0").rstrip(".")
    if "." not in normalized:
        return normalized

    return normalized
