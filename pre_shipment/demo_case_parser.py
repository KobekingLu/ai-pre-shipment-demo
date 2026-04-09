"""Lightweight parser for simplified fake demo cases."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from pre_shipment.mapping import canonical_component_name


def inspect_demo_cases(root: Path) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for expected_path in sorted(root.glob("*_expected_config.csv")):
        prefix = expected_path.name[: -len("_expected_config.csv")]
        actual_path = root / f"{prefix}_actual_sysinfo.txt"
        issues_path = root / f"{prefix}_known_issues.csv"

        if not actual_path.exists() or not issues_path.exists():
            continue

        display_name = _display_name(prefix)
        expected = parse_expected_config(expected_path)
        actual = parse_actual_sysinfo(actual_path)
        issues = parse_known_issues(issues_path)

        reports.append(
            {
                "workbook_name": display_name,
                "workbook_path": str(root / prefix),
                "sheet_names": [
                    expected_path.name,
                    actual_path.name,
                    issues_path.name,
                ],
                "source_type": "demo_case",
                "source_label": "Fake Demo Data",
                "case_id": prefix,
                "role_candidates": {
                    "expected_configuration": expected_path.name,
                    "actual_configuration": actual_path.name,
                    "known_issues": issues_path.name,
                },
                "field_mapping_plan": {
                    "expected_configuration": {
                        "sheet": expected_path.name,
                        "fields": [
                            "project_name",
                            "system_level",
                            "cpu",
                            "memory",
                            "storage",
                            "firmware_versions",
                        ],
                    },
                    "actual_configuration": {
                        "sheet": actual_path.name,
                        "fields": [
                            "product_name",
                            "product_part_number",
                            "cpu",
                            "memory",
                            "storage",
                            "firmware_versions",
                            "bmc_ip_address",
                        ],
                    },
                    "known_issues": {
                        "sheet": issues_path.name,
                        "fields": [
                            "item",
                            "type",
                            "description",
                            "status",
                            "level",
                            "resolution",
                            "affected_component",
                            "affected_version_or_condition",
                        ],
                    },
                },
                "parsed": {
                    "expected_config": expected,
                    "actual_config": actual,
                    "known_issues": issues,
                },
            }
        )
    return reports


def parse_expected_config(path: Path) -> dict[str, Any]:
    expected: dict[str, Any] = {
        "source_sheet": path.name,
        "project_name": "",
        "hardware_items": [],
        "firmware_versions": {},
    }

    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            field = (row.get("field") or "").strip()
            value = (row.get("expected_value") or "").strip()
            if not field:
                continue

            lowered = field.lower()
            if lowered == "project_name":
                expected["project_name"] = value
            elif lowered == "system_level":
                expected["system_level"] = value
                expected["hardware_items"].append({"item": "System Level", "value": value})
            elif lowered in {"cpu", "memory", "storage"}:
                expected[lowered] = value
                expected["hardware_items"].append({"item": field.upper(), "value": value})
            else:
                expected["firmware_versions"][canonical_component_name(field)] = value

    return expected


def parse_actual_sysinfo(path: Path) -> dict[str, Any]:
    actual: dict[str, Any] = {
        "source_sheet": path.name,
        "firmware_versions": {},
        "lan_mac_addresses": [],
    }

    alias_map = {
        "project": "product_name",
        "system level": "product_part_number",
        "cpu": "cpu",
        "memory": "memory",
        "storage": "storage",
        "bmc_ip": "bmc_ip_address",
    }

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue

        key, value = [part.strip() for part in line.split(":", 1)]
        lowered = key.lower()

        if lowered in alias_map:
            actual[alias_map[lowered]] = value
            continue

        actual["firmware_versions"][canonical_component_name(key)] = value

    return actual


def parse_known_issues(path: Path) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            issues.append(
                {
                    "item": (row.get("item") or "").strip(),
                    "type": (row.get("type") or "").strip(),
                    "description": (row.get("description") or "").strip(),
                    "status": (row.get("status") or "").strip(),
                    "level": (row.get("level") or "").strip(),
                    "resolution": (row.get("resolution") or "").strip(),
                    "target_date": "",
                    "affected_component": (row.get("affected_component") or "").strip(),
                    "affected_version_or_condition": (
                        row.get("affected_version_or_condition") or ""
                    ).strip(),
                }
            )
    return issues


def _display_name(prefix: str) -> str:
    mapping = {
        "go": "GO Demo Case",
        "conditional_go": "Conditional Go Demo Case",
        "nogo": "No-Go Demo Case",
    }
    return mapping.get(prefix, prefix.replace("_", " ").title())
