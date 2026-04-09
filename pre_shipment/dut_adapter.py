"""Minimal adapter that maps DUT collection JSON into the existing actual_config flow."""

from __future__ import annotations

import json
import ipaddress
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from pre_shipment.mapping import normalize_part_number


def apply_dut_actuals_to_workbook_reports(
    reports: list[dict[str, Any]],
    dut_runs_dir: Path,
) -> list[dict[str, Any]]:
    if not dut_runs_dir.exists():
        return reports

    updated_reports = [deepcopy(report) for report in reports]
    for payload in load_latest_dut_payloads(dut_runs_dir):
        actual_config = adapt_collection_result_to_actual_config(payload)
        if not actual_config:
            continue

        match_index = _find_matching_report_index(updated_reports, payload, actual_config)
        if match_index is None:
            continue

        report = updated_reports[match_index]
        actual_source = actual_config["source_sheet"]

        report["parsed"] = dict(report.get("parsed", {}))
        report["parsed"]["actual_config"] = actual_config
        report["parsed"]["dut_collection_metadata"] = {
            "case_id": payload.get("case_id"),
            "run_id": payload.get("run_id"),
            "collection_result_path": payload.get("_collection_result_path"),
        }

        report["role_candidates"] = dict(report.get("role_candidates", {}))
        report["role_candidates"]["actual_configuration"] = actual_source

        report["field_mapping_plan"] = dict(report.get("field_mapping_plan", {}))
        actual_plan = dict(report["field_mapping_plan"].get("actual_configuration", {}))
        actual_plan["sheet"] = actual_source
        report["field_mapping_plan"]["actual_configuration"] = actual_plan

        sheet_names = list(report.get("sheet_names", []))
        if actual_source not in sheet_names:
            sheet_names.append(actual_source)
        report["sheet_names"] = sheet_names

    return updated_reports


def load_latest_dut_payloads(dut_runs_dir: Path) -> list[dict[str, Any]]:
    latest_by_case: dict[str, tuple[str, dict[str, Any]]] = {}

    for collection_path in dut_runs_dir.glob("*/*/collection_result.json"):
        payload = json.loads(collection_path.read_text(encoding="utf-8"))
        if payload.get("dry_run"):
            continue
        parsed_actual = payload.get("parsed_actual_config") or {}
        if not parsed_actual:
            continue

        case_id = str(payload.get("case_id") or collection_path.parent.parent.name)
        run_id = str(payload.get("run_id") or collection_path.parent.name)
        payload["_collection_result_path"] = str(collection_path)
        previous = latest_by_case.get(case_id)
        if not previous or run_id > previous[0]:
            latest_by_case[case_id] = (run_id, payload)

    return [item[1] for item in sorted(latest_by_case.values(), key=lambda value: value[0])]


def adapt_collection_result_to_actual_config(payload: dict[str, Any]) -> dict[str, Any]:
    parsed_actual = payload.get("parsed_actual_config") or {}
    if not parsed_actual:
        return {}

    actual: dict[str, Any] = {
        "source_sheet": "DUT collection {} ({})".format(
            payload.get("case_id", "unknown"),
            payload.get("run_id", "unknown"),
        ),
        "firmware_versions": dict(parsed_actual.get("firmware_versions") or {}),
        "lan_mac_addresses": list(parsed_actual.get("lan_mac_addresses") or []),
        "collection_method": parsed_actual.get("collection_method", "restricted_ssh"),
    }

    direct_fields = [
        "product_name",
        "product_part_number",
        "product_version",
        "product_serial",
        "board_part_number",
        "board_product",
        "board_serial",
        "chassis_part_number",
        "chassis_serial",
        "bmc_ip_address",
        "bmc_mac_address",
        "host_ipv4_address",
        "host_ipv4_candidates",
        "host_ipv4_selection_note",
        "probe_plan",
        "bsp_image",
        "nic_inventory",
        "tracking_probe",
        "pcie_probe",
        "operational_probe",
        "execution_evidence",
        "collection_notes",
    ]
    for field in direct_fields:
        value = parsed_actual.get(field)
        if value not in (None, "", [], {}):
            actual[field] = value

    if "bmc_mac_address" not in actual:
        bmc_mac = _extract_bmc_mac_address(payload)
        if bmc_mac:
            actual["bmc_mac_address"] = bmc_mac

    _apply_preferred_host_ipv4(actual, payload)

    if "product_name" not in actual and payload.get("case_id"):
        actual["product_name"] = str(payload["case_id"])

    return actual


def _extract_bmc_mac_address(payload: dict[str, Any]) -> str:
    for command in payload.get("commands", []):
        if command.get("id") != "bmc_lan":
            continue
        stdout = command.get("stdout", "")
        match = re.search(r"^\s*MAC Address\s*:\s*(?P<value>\S+)", stdout, flags=re.MULTILINE)
        if match:
            return match.group("value").strip()
    return ""


def _find_matching_report_index(
    reports: list[dict[str, Any]],
    payload: dict[str, Any],
    actual_config: dict[str, Any],
) -> int | None:
    dut_tokens = _normalized_tokens(
        payload.get("case_id"),
        actual_config.get("product_name"),
        actual_config.get("product_part_number"),
        actual_config.get("board_part_number"),
    )
    if not dut_tokens:
        return None

    best_index: int | None = None
    best_score = 0
    for index, report in enumerate(reports):
        if report.get("source_type") != "real_workbook":
            continue

        parsed = report.get("parsed", {})
        expected = parsed.get("expected_config") or {}
        current_actual = parsed.get("actual_config") or {}
        report_tokens = _normalized_tokens(
            report.get("workbook_name"),
            Path(report.get("workbook_path", "")).stem,
            expected.get("project_name"),
            expected.get("system_level"),
            current_actual.get("product_name"),
            current_actual.get("product_part_number"),
        )

        score = _match_score(dut_tokens, report_tokens)
        if score > best_score:
            best_index = index
            best_score = score

    return best_index if best_score > 0 else None


def _apply_preferred_host_ipv4(actual: dict[str, Any], payload: dict[str, Any]) -> None:
    ip_candidates = _extract_host_ipv4_candidates(payload)
    if not ip_candidates:
        return

    selected_ip, note = _select_preferred_host_ipv4(
        ip_candidates=ip_candidates,
        ssh_target_host=str(payload.get("host") or ""),
        bmc_ip=str(actual.get("bmc_ip_address") or ""),
        bmc_lan_stdout=_command_stdout(payload, "bmc_lan"),
    )
    actual["host_ipv4_candidates"] = ip_candidates
    if selected_ip:
        actual["host_ipv4_address"] = selected_ip
    else:
        actual.pop("host_ipv4_address", None)
    if note:
        actual["host_ipv4_selection_note"] = note


def _normalized_tokens(*values: Any) -> list[str]:
    tokens: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        normalized = normalize_part_number(text)
        if normalized:
            tokens.append(normalized)
    return tokens


def _match_score(dut_tokens: list[str], report_tokens: list[str]) -> int:
    score = 0
    for dut_token in dut_tokens:
        for report_token in report_tokens:
            if dut_token == report_token:
                score += 3
            elif dut_token in report_token or report_token in dut_token:
                score += 1
    return score


def _extract_host_ipv4_candidates(payload: dict[str, Any]) -> list[str]:
    stdout = _command_stdout(payload, "host_ipv4")
    if not stdout:
        return []

    candidates: list[str] = []
    for match in re.finditer(r"\binet (?P<ip>\d+\.\d+\.\d+\.\d+)/", stdout):
        ip_value = match.group("ip")
        if ip_value.startswith("127."):
            continue
        if ip_value not in candidates:
            candidates.append(ip_value)
    return candidates


def _command_stdout(payload: dict[str, Any], command_id: str) -> str:
    for command in payload.get("commands", []):
        if command.get("id") == command_id:
            return str(command.get("stdout") or "")
    return ""


def _select_preferred_host_ipv4(
    *,
    ip_candidates: list[str],
    ssh_target_host: str,
    bmc_ip: str,
    bmc_lan_stdout: str,
) -> tuple[str, str]:
    ssh_target_ip = _extract_ip_from_host_target(ssh_target_host)
    if ssh_target_ip and ssh_target_ip in ip_candidates:
        return ssh_target_ip, "Selected host IPv4 that matches the SSH target address."

    same_subnet_candidates = _same_subnet_candidates(
        ip_candidates=ip_candidates,
        bmc_ip=bmc_ip,
        bmc_lan_stdout=bmc_lan_stdout,
    )
    if len(same_subnet_candidates) == 1:
        return same_subnet_candidates[0], "Selected host IPv4 that shares the BMC management subnet."
    if len(same_subnet_candidates) > 1:
        return "", (
            "Multiple host IPv4 candidates share the BMC management subnet; no single primary host IP was chosen."
        )

    if ssh_target_ip:
        return ssh_target_ip, (
            "SSH target address was used as the preferred host IP because interface output did not provide a unique match."
        )

    if len(ip_candidates) == 1:
        return ip_candidates[0], "Selected the only non-loopback host IPv4 candidate."

    return "", (
        "Multiple non-loopback host IPv4 candidates were found; no single primary host IP was chosen."
    )


def _same_subnet_candidates(
    *,
    ip_candidates: list[str],
    bmc_ip: str,
    bmc_lan_stdout: str,
) -> list[str]:
    if not bmc_ip:
        return []

    subnet_mask_match = re.search(
        r"^\s*Subnet Mask\s*:\s*(?P<value>\S+)",
        bmc_lan_stdout,
        flags=re.MULTILINE,
    )
    subnet_mask = subnet_mask_match.group("value").strip() if subnet_mask_match else ""

    try:
        if subnet_mask:
            network = ipaddress.ip_network(f"{bmc_ip}/{subnet_mask}", strict=False)
            return [ip for ip in ip_candidates if ipaddress.ip_address(ip) in network]
    except ValueError:
        return []

    return []


def _extract_ip_from_host_target(host: str) -> str:
    target = host.rsplit("@", 1)[-1].strip()
    try:
        ipaddress.ip_address(target)
        return target
    except ValueError:
        return ""
