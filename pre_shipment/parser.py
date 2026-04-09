"""Workbook inspection and lightweight field extraction."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pre_shipment.mapping import (
    ACTUAL_INFO_ALIASES,
    EXPECTED_FIRMWARE_COMPONENTS,
    HARDWARE_FIELD_ALIASES,
    SHEET_ROLE_HINTS,
    canonical_component_name,
    normalize_part_number,
)
from pre_shipment.xlsx_reader import SheetData, WorkbookData, iter_workbooks, read_workbook


def inspect_input_folder(input_dir: Path) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    standalone_issue_reports: list[dict[str, Any]] = []
    for workbook_path in iter_workbooks(input_dir):
        workbook = read_workbook(workbook_path)
        report = inspect_workbook(workbook)
        if _is_standalone_known_issue_report(report):
            standalone_issue_reports.append(report)
            continue
        if not _should_include_report(report):
            continue
        reports.append(report)

    _merge_standalone_known_issue_reports(reports, standalone_issue_reports)
    return reports


def inspect_workbook(workbook: WorkbookData) -> dict[str, Any]:
    sheet_names = [sheet.name for sheet in workbook.sheets]
    role_candidates = identify_sheet_roles(workbook)

    expected_sheet = _find_sheet_by_name(workbook, role_candidates.get("expected_configuration"))
    actual_sheet = _find_sheet_by_name(workbook, role_candidates.get("actual_configuration"))
    issues_sheet = _find_sheet_by_name(workbook, role_candidates.get("known_issues"))

    expected_config = parse_expected_configuration(expected_sheet) if expected_sheet else {}
    actual_config = parse_actual_configuration(actual_sheet) if actual_sheet else {}
    known_issues = parse_known_issues(issues_sheet) if issues_sheet else []
    known_issue_context = _extract_known_issue_context(issues_sheet) if issues_sheet else ""

    if issues_sheet and not known_issues:
        role_candidates["known_issues"] = None

    return {
        "workbook_name": workbook.name,
        "workbook_path": str(workbook.path),
        "sheet_names": sheet_names,
        "source_type": "real_workbook",
        "source_label": "Real Workbook Data",
        "role_candidates": role_candidates,
        "field_mapping_plan": build_field_mapping_plan(role_candidates),
        "parsed": {
            "expected_config": expected_config,
            "actual_config": actual_config,
            "known_issues": known_issues,
            "known_issue_context": known_issue_context,
        },
    }


def identify_sheet_roles(workbook: WorkbookData) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for role in SHEET_ROLE_HINTS:
        best_name: str | None = None
        best_score = -1
        for sheet in workbook.sheets:
            score = _score_sheet_for_role(sheet, role)
            if score > best_score:
                best_score = score
                best_name = sheet.name
        result[role] = best_name if best_score > 0 else None
    return result


def build_field_mapping_plan(role_candidates: dict[str, str | None]) -> dict[str, Any]:
    return {
        "expected_configuration": {
            "sheet": role_candidates.get("expected_configuration"),
            "fields": [
                "project_name",
                "system_level",
                "cpu_board",
                "hardware_items",
                "firmware_versions",
            ],
        },
        "actual_configuration": {
            "sheet": role_candidates.get("actual_configuration"),
            "fields": [
                "product_name",
                "product_part_number",
                "board_part_number",
                "product_version",
                "firmware_versions",
                "bmc_ip_address",
                "bmc_mac_address",
            ],
        },
        "known_issues": {
            "sheet": role_candidates.get("known_issues"),
            "fields": [
                "item",
                "type",
                "description",
                "status",
                "level",
                "resolution",
                "target_date",
            ],
        },
    }


def parse_expected_configuration(sheet: SheetData) -> dict[str, Any]:
    expected: dict[str, Any] = {
        "source_sheet": sheet.name,
        "project_name": "",
        "hardware_items": [],
        "firmware_versions": {},
    }
    in_hw_section = False
    in_fw_section = False

    for row in sheet.rows:
        values = row.values
        row_text = " | ".join(values).strip()
        second = _cell(values, 1)
        third = _cell(values, 2)
        fourth = _cell(values, 3)

        if "Project Name:" in row_text:
            expected["project_name"] = row_text.split("Project Name:", 1)[1].strip()

        if "2. HW BOM" in row_text:
            in_hw_section = True
            in_fw_section = False
            continue

        if "3. SW/FW Version" in row_text:
            in_hw_section = False
            in_fw_section = True
            continue

        if row_text.startswith("| 4.") or "4. Schedule plan" in row_text:
            in_hw_section = False
            in_fw_section = False

        if in_hw_section:
            field_key = HARDWARE_FIELD_ALIASES.get(second.lower())
            if field_key:
                expected[field_key] = third

            if second and second not in {"Version", "Firmware"}:
                if second not in {"Project Name:", "Qty", "Qty.", "Part Number"}:
                    expected["hardware_items"].append(
                        {
                            "item": second,
                            "value": third,
                            "qty": fourth,
                            "source_row": row.row_number,
                        }
                    )

        if in_fw_section:
            component = canonical_component_name(second)
            if second.lower() in {"version", "firmware"} or not second:
                continue
            # Keep only real firmware/component rows and skip note or rule text.
            if component not in EXPECTED_FIRMWARE_COMPONENTS:
                continue
            if _is_placeholder_expected_value(third):
                continue
            expected["firmware_versions"][component] = third

    return expected


def parse_actual_configuration(sheet: SheetData) -> dict[str, Any]:
    actual: dict[str, Any] = {
        "source_sheet": sheet.name,
        "firmware_versions": {},
        "lan_mac_addresses": [],
    }

    for row in sheet.rows:
        line = _cell(row.values, 0)
        if not line:
            continue

        version_match = re.match(
            r"^\|\*?\s*\d+\|\s*(?P<name>[^|]+?)\s*\|\s*(?P<active>[^|]+?)\|",
            line,
        )
        if version_match:
            component = canonical_component_name(version_match.group("name"))
            active_version = version_match.group("active").strip().split()[0]
            actual["firmware_versions"][component] = active_version
            continue

        kv_match = re.match(r"^(?P<key>[^:]{2,}?)\s*:\s*(?P<value>.+)$", line)
        if kv_match:
            key = " ".join(kv_match.group("key").strip().lower().split())
            value = kv_match.group("value").strip()
            mapped_key = ACTUAL_INFO_ALIASES.get(key)
            if mapped_key:
                actual[mapped_key] = value
            continue

        if re.search(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", line, flags=re.IGNORECASE):
            parts = re.split(r"\s{2,}", line.strip())
            if len(parts) >= 7:
                actual["lan_mac_addresses"].append(
                    {
                        "eth_name": parts[0],
                        "mac_address": parts[5],
                        "slot_name": parts[6],
                    }
                )

    return actual


def parse_known_issues(sheet: SheetData) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    header_seen = False

    for row in sheet.rows:
        values = row.values
        if not header_seen and values[:3] == ["Item", "Type", "Description"]:
            header_seen = True
            continue

        if not header_seen:
            continue

        first = _cell(values, 0)
        if not first.isdigit():
            continue

        issues.append(
            {
                "item": first,
                "type": _cell(values, 1),
                "description": _cell(values, 2),
                "added_by": _cell(values, 3),
                "status": _cell(values, 4),
                "level": _cell(values, 5),
                "resolution": _cell(values, 6),
                "target_date": _cell(values, 7),
            }
        )

    if issues:
        return issues

    # Fallback for lightweight RD issue sheets without a header row.
    if not _looks_like_known_issue_sheet(sheet):
        return issues

    for row in sheet.rows[1:]:
        values = row.values
        first = _cell(values, 0)
        if not first.isdigit():
            continue
        issues.append(
            {
                "item": first,
                "type": _cell(values, 2),
                "description": _cell(values, 1),
                "added_by": "",
                "status": "open",
                "level": "",
                "resolution": _cell(values, 3),
                "target_date": "",
            }
        )

    return issues


def _find_sheet_by_name(workbook: WorkbookData, sheet_name: str | None) -> SheetData | None:
    if not sheet_name:
        return None
    for sheet in workbook.sheets:
        if sheet.name == sheet_name:
            return sheet
    return None


def _preview_lines(sheet: SheetData, limit: int) -> list[str]:
    return [" | ".join(row.values).lower() for row in sheet.rows[:limit]]


def _cell(values: list[str], index: int) -> str:
    if index < len(values):
        return values[index].strip()
    return ""


def _is_placeholder_expected_value(value: str) -> bool:
    lowered = (value or "").strip().lower()
    if not lowered:
        return True
    placeholder_markers = [
        "must record",
        "n/a",
        "na",
        "tbd",
        "to be confirmed",
    ]
    return any(marker in lowered for marker in placeholder_markers)


def _extract_known_issue_context(sheet: SheetData) -> str:
    if not sheet.rows:
        return ""
    return " | ".join(sheet.rows[0].values).strip()


def _looks_like_known_issue_sheet(sheet: SheetData) -> bool:
    title = _extract_known_issue_context(sheet).lower()
    if "known issue" in title or "known issues" in title:
        return True
    preview = " ".join(" | ".join(row.values).lower() for row in sheet.rows[:8])
    return "known issue" in preview or "known issues" in preview


def _score_sheet_for_role(sheet: SheetData, role: str) -> int:
    name = sheet.name.lower()
    preview = " ".join(_preview_lines(sheet, limit=15))
    blob = f"{name} {preview}"

    score = 0
    for hint in SHEET_ROLE_HINTS[role]:
        if hint in blob:
            score += 2

    if role == "expected_configuration":
        if "ms1" in name:
            score += 5
        if "schedule" in name:
            score += 4
        if "2. hw bom" in preview:
            score += 6
        if "3. sw/fw version" in preview:
            score += 6
        if "project name:" in preview:
            score += 4

    if role == "actual_configuration":
        if "sysinfo" in name:
            score += 8
        if "versions" in preview and "product part number" in preview:
            score += 6
        if "ipmitool lan print" in preview:
            score += 4

    if role == "known_issues":
        if "known issue" in name:
            score += 8
        if "known issues" in preview:
            score += 6
        if "item | type | description" in preview:
            score += 6

    return score


def _should_include_report(report: dict[str, Any]) -> bool:
    roles = report.get("role_candidates", {})
    return bool(
        roles.get("expected_configuration")
        or roles.get("actual_configuration")
    )


def _is_standalone_known_issue_report(report: dict[str, Any]) -> bool:
    roles = report.get("role_candidates", {})
    parsed = report.get("parsed", {})
    return bool(
        not roles.get("expected_configuration")
        and not roles.get("actual_configuration")
        and parsed.get("known_issues")
    )


def _merge_standalone_known_issue_reports(
    reports: list[dict[str, Any]],
    standalone_issue_reports: list[dict[str, Any]],
) -> None:
    for issue_report in standalone_issue_reports:
        target = _find_best_issue_target_report(reports, issue_report)
        if target is None:
            continue

        parsed = target.setdefault("parsed", {})
        if parsed.get("known_issues"):
            continue

        issues = list(issue_report.get("parsed", {}).get("known_issues", []))
        context = issue_report.get("parsed", {}).get("known_issue_context", "")
        issue_source = "{}:{}".format(
            issue_report.get("workbook_name", "Known Issue Workbook"),
            issue_report.get("sheet_names", ["Sheet1"])[0],
        )

        parsed["known_issues"] = issues
        parsed["known_issue_context"] = context
        target["role_candidates"] = dict(target.get("role_candidates", {}))
        target["role_candidates"]["known_issues"] = issue_source
        target["field_mapping_plan"] = dict(target.get("field_mapping_plan", {}))
        known_plan = dict(target["field_mapping_plan"].get("known_issues", {}))
        known_plan["sheet"] = issue_source
        target["field_mapping_plan"]["known_issues"] = known_plan
        sheet_names = list(target.get("sheet_names", []))
        if issue_source not in sheet_names:
            sheet_names.append(issue_source)
        target["sheet_names"] = sheet_names


def _find_best_issue_target_report(
    reports: list[dict[str, Any]],
    issue_report: dict[str, Any],
) -> dict[str, Any] | None:
    context = issue_report.get("parsed", {}).get("known_issue_context", "")
    issue_tokens = _normalized_tokens(
        issue_report.get("workbook_name"),
        context,
    )
    if not issue_tokens:
        return None

    best_report: dict[str, Any] | None = None
    best_score = 0
    for report in reports:
        parsed = report.get("parsed", {})
        expected = parsed.get("expected_config", {})
        actual = parsed.get("actual_config", {})
        report_tokens = _normalized_tokens(
            report.get("workbook_name"),
            expected.get("project_name"),
            expected.get("system_level"),
            actual.get("product_name"),
            actual.get("product_part_number"),
        )
        score = _token_match_score(issue_tokens, report_tokens)
        if score > best_score:
            best_report = report
            best_score = score

    return best_report if best_score > 0 else None


def _normalized_tokens(*values: str) -> list[str]:
    tokens: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        candidates = [text, *re.split(r"[^A-Za-z0-9]+", text)]
        for candidate in candidates:
            normalized = normalize_part_number(candidate)
            if normalized and normalized not in tokens:
                tokens.append(normalized)
    return tokens


def _token_match_score(left: list[str], right: list[str]) -> int:
    score = 0
    for left_token in left:
        for right_token in right:
            if left_token == right_token:
                score += 3
            elif left_token in right_token or right_token in left_token:
                score += 1
    return score
