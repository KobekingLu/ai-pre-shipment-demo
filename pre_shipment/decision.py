"""Comparison and recommendation logic for the prototype."""

from __future__ import annotations

import re
from typing import Any

from pre_shipment.mapping import (
    canonical_component_name,
    normalize_part_number,
    normalize_version,
)
from pre_shipment.probe_planner import build_probe_plan

BOM_MODEL_HINTS = {
    normalize_part_number("XSKY-MCX755106AS"): ["CONNECTX-7"],
    normalize_part_number("PCIE-2221BP-00A1E"): ["I350 GIGABIT NETWORK CONNECTION"],
}


def analyze_workbook_report(report: dict[str, Any]) -> dict[str, Any]:
    expected = report["parsed"].get("expected_config") or {}
    actual = report["parsed"].get("actual_config") or {}
    known_issues = report["parsed"].get("known_issues") or []

    mismatches = compare_expected_actual(expected, actual)
    matched_issues = match_known_issues(mismatches, known_issues)
    decision = make_decision(expected, actual, mismatches, matched_issues)

    result = dict(report)
    result["analysis"] = {
        "mismatch_items": mismatches,
        "matched_known_issues": matched_issues,
        **decision,
        **build_explainability(report, mismatches, matched_issues, decision),
    }
    return result


def compare_expected_actual(
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    if not expected or not actual:
        return mismatches

    _compare_identity_field(
        mismatches,
        field="project_name",
        expected_value=expected.get("project_name", ""),
        actual_candidates=[
            actual.get("product_name", ""),
            actual.get("chassis_part_number", ""),
        ],
    )
    _compare_identity_field(
        mismatches,
        field="system_level",
        expected_value=expected.get("system_level", ""),
        actual_candidates=[
            actual.get("product_part_number", ""),
            actual.get("product_name", ""),
        ],
    )
    _compare_identity_field(
        mismatches,
        field="cpu_board",
        expected_value=expected.get("cpu_board", ""),
        actual_candidates=[actual.get("board_part_number", "")],
    )

    expected_fw = expected.get("firmware_versions", {})
    actual_fw = actual.get("firmware_versions", {})
    for component, expected_version in expected_fw.items():
        actual_version = actual_fw.get(component)
        if not actual_version:
            continue
        if normalize_version(expected_version) != normalize_version(actual_version):
            mismatches.append(
                {
                    "field": f"firmware_versions.{component}",
                    "component": component,
                    "expected": expected_version,
                    "actual": actual_version,
                    "severity": "medium",
                }
            )

    mismatches.extend(compare_expected_hardware(expected, actual))
    for item in mismatches:
        item.setdefault("category", classify_mismatch_category(item))
    return mismatches


def compare_expected_hardware(
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    hardware_items = expected.get("hardware_items", []) or []
    if not hardware_items or not actual:
        return mismatches

    tracking_probe = actual.get("tracking_probe") or {}
    pcie_probe = actual.get("pcie_probe") or {}

    memory_item = _first_hardware_item(hardware_items, "memory")
    if memory_item and tracking_probe.get("memory"):
        mismatches.extend(_compare_memory_item(memory_item, tracking_probe["memory"]))

    cpu_item = _first_hardware_item(hardware_items, "cpu")
    if cpu_item and tracking_probe.get("cpu"):
        mismatches.extend(_compare_cpu_item(cpu_item, tracking_probe["cpu"]))

    gpu_item = _first_hardware_item(hardware_items, "gpu")
    if gpu_item:
        mismatches.extend(_compare_gpu_item(gpu_item, tracking_probe, pcie_probe))

    nic_items = _hardware_items_with_keywords(hardware_items, ["nic"])
    if nic_items and pcie_probe.get("nic_devices"):
        mismatches.extend(_compare_nic_items(nic_items, pcie_probe))

    storage_items = _hardware_items_with_keywords(hardware_items, ["ssd", "m.2", "nvme"])
    if storage_items and tracking_probe.get("storage"):
        mismatches.extend(_compare_storage_items(storage_items, tracking_probe["storage"]))

    return mismatches


def match_known_issues(
    mismatches: list[dict[str, Any]],
    known_issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not known_issues:
        return []

    mismatch_components = {
        canonical_component_name(item.get("component", ""))
        for item in mismatches
        if item.get("component")
    }

    matched: list[dict[str, Any]] = []
    for issue in known_issues:
        if issue.get("status", "").lower() != "open":
            continue

        raw_types = re.split(r"[,/]", issue.get("type", ""))
        issue_components = {
            canonical_component_name(token) for token in raw_types if token.strip()
        }

        if not mismatch_components or mismatch_components & issue_components:
            matched.append(issue)

    if matched:
        return matched

    return [issue for issue in known_issues if issue.get("status", "").lower() == "open"]


def _first_hardware_item(
    hardware_items: list[dict[str, Any]],
    keyword: str,
) -> dict[str, Any] | None:
    keyword = keyword.lower()
    for item in hardware_items:
        name = str(item.get("item") or "").strip().lower()
        if name == keyword:
            return item
    for item in hardware_items:
        name = str(item.get("item") or "").lower()
        if keyword in name:
            return item
    return None


def _hardware_items_with_keywords(
    hardware_items: list[dict[str, Any]],
    keywords: list[str],
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    lowered_keywords = [keyword.lower() for keyword in keywords]
    for item in hardware_items:
        name = str(item.get("item") or "").lower()
        if any(keyword in name for keyword in lowered_keywords):
            matched.append(item)
    return matched


def _compare_memory_item(
    expected_item: dict[str, Any],
    memory_probe: dict[str, Any],
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    expected_qty = _parse_int(expected_item.get("qty"))
    expected_module_gib = _parse_capacity_gib(str(expected_item.get("value") or ""))
    actual_qty = _parse_int(memory_probe.get("populated_dimms"))
    actual_dimms = [int(value) for value in memory_probe.get("dimm_sizes_gib", []) if isinstance(value, int)]
    actual_module_gib = actual_dimms[0] if actual_dimms and len(set(actual_dimms)) == 1 else None
    actual_total_gib = _parse_int(memory_probe.get("total_gib"))

    if expected_qty and actual_qty and expected_qty != actual_qty:
        mismatches.append(
            {
                "field": "hardware.memory.qty",
                "component": "MEMORY",
                "expected": f"{expected_qty} DIMMs",
                "actual": f"{actual_qty} DIMMs",
                "severity": "medium",
            }
        )

    if expected_module_gib and actual_module_gib and expected_module_gib != actual_module_gib:
        mismatches.append(
            {
                "field": "hardware.memory.module_size",
                "component": "MEMORY",
                "expected": f"{expected_module_gib} GiB DIMM",
                "actual": f"{actual_module_gib} GiB DIMM",
                "severity": "medium",
            }
        )

    expected_total_gib = expected_qty * expected_module_gib if expected_qty and expected_module_gib else None
    if expected_total_gib and actual_total_gib:
        if abs(expected_total_gib - actual_total_gib) >= 64:
            mismatches.append(
                {
                    "field": "hardware.memory.total_capacity",
                    "component": "MEMORY",
                    "expected": f"{expected_total_gib} GiB",
                    "actual": f"{actual_total_gib} GiB",
                    "severity": "medium",
                }
            )

    return mismatches


def _compare_cpu_item(
    expected_item: dict[str, Any],
    cpu_probe: dict[str, Any],
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    expected_qty = _parse_int(expected_item.get("qty"))
    actual_sockets = _parse_int(cpu_probe.get("sockets"))
    if expected_qty and actual_sockets and expected_qty != actual_sockets:
        mismatches.append(
            {
                "field": "hardware.cpu.socket_count",
                "component": "CPU",
                "expected": f"{expected_qty} sockets",
                "actual": f"{actual_sockets} sockets",
                "severity": "medium",
            }
        )

    expected_model = _extract_cpu_model_number(str(expected_item.get("value") or ""))
    actual_model = _extract_cpu_model_number(str(cpu_probe.get("model_name") or ""))
    if expected_model and actual_model and expected_model != actual_model:
        mismatches.append(
            {
                "field": "hardware.cpu.model",
                "component": "CPU",
                "expected": str(expected_item.get("value") or ""),
                "actual": str(cpu_probe.get("model_name") or ""),
                "severity": "medium",
            }
        )

    return mismatches


def _compare_gpu_item(
    expected_item: dict[str, Any],
    tracking_probe: dict[str, Any],
    pcie_probe: dict[str, Any],
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    expected_qty = _parse_int(expected_item.get("qty"))
    expected_value = str(expected_item.get("value") or "")
    actual_gpu = tracking_probe.get("gpu") or {}
    actual_qty = _parse_int(actual_gpu.get("gpu_count"))
    actual_models = [str(model) for model in actual_gpu.get("models", []) if str(model).strip()]

    if expected_qty and actual_qty and expected_qty != actual_qty:
        mismatches.append(
            {
                "field": "hardware.gpu.qty",
                "component": "GPU",
                "expected": f"{expected_qty} GPUs",
                "actual": f"{actual_qty} GPUs",
                "severity": "medium",
            }
        )

    expected_gpu_token = _preferred_model_token(expected_value)
    actual_tokens = {_preferred_model_token(model) for model in actual_models if _preferred_model_token(model)}
    if expected_gpu_token and actual_tokens and expected_gpu_token not in actual_tokens:
        mismatches.append(
            {
                "field": "hardware.gpu.model",
                "component": "GPU",
                "expected": expected_value,
                "actual": ", ".join(actual_models) or "N/A",
                "severity": "medium",
            }
        )

    if not mismatches and (pcie_probe.get("attention_items") or []):
        mixed_gpu = next(
            (item for item in pcie_probe.get("attention_items", []) if "GPU models" in item),
            "",
        )
        if mixed_gpu and expected_gpu_token:
            mismatches.append(
                {
                    "field": "hardware.gpu.inventory_shape",
                    "component": "GPU",
                    "expected": expected_value,
                    "actual": mixed_gpu.replace("Mixed GPU models were detected: ", "").rstrip("."),
                    "severity": "medium",
                }
            )

    return mismatches


def _compare_storage_items(
    expected_items: list[dict[str, Any]],
    storage_probe: dict[str, Any],
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    actual_models = [
        str(device.get("model") or "").strip()
        for device in storage_probe.get("devices", [])
        if str(device.get("model") or "").strip()
    ]
    actual_tokens = {_preferred_model_token(model) for model in actual_models if _preferred_model_token(model)}

    for item in expected_items:
        expected_value = str(item.get("value") or "").strip()
        if not expected_value or expected_value.upper() in {"N.A.", "N.A", "NA"}:
            continue
        expected_token = _preferred_model_token(expected_value)
        if not expected_token or expected_token in actual_tokens:
            continue
        mismatches.append(
            {
                "field": "hardware.storage.model",
                "component": "STORAGE",
                "expected": expected_value,
                "actual": ", ".join(actual_models[:4]) or "N/A",
                "severity": "medium",
            }
        )
        break

    return mismatches


def _compare_nic_items(
    expected_items: list[dict[str, Any]],
    pcie_probe: dict[str, Any],
) -> list[dict[str, Any]]:
    actual_labels = sorted(
        {
            str(device.get("label") or "").strip()
            for device in pcie_probe.get("nic_devices", [])
            if str(device.get("label") or "").strip()
        }
    )
    if not actual_labels:
        return []

    expected_hints: list[str] = []
    for item in expected_items:
        expected_hints.extend(_bom_expected_hints(str(item.get("value") or "")))

    if not expected_hints:
        return []

    normalized_actual = {normalize_part_number(label) for label in actual_labels}
    missing_expected = [
        hint
        for hint in expected_hints
        if normalize_part_number(hint) not in normalized_actual
    ]

    if missing_expected or len(actual_labels) > len(expected_hints):
        return [
            {
                "field": "hardware.nic.inventory",
                "component": "NIC",
                "expected": ", ".join(expected_hints),
                "actual": ", ".join(actual_labels[:4]),
                "severity": "medium",
            }
        ]

    return []


def _parse_int(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"\d+", text)
    return int(match.group(0)) if match else None


def _parse_capacity_gib(value: str) -> int | None:
    text = str(value or "").strip().upper()
    match = re.search(r"(\d+)\s*G(?:B)?", text)
    return int(match.group(1)) if match else None


def _preferred_model_token(value: str) -> str:
    text = str(value or "").upper()
    for pattern in [r"\bH\d{3}\b", r"\bL\d{2,3}[A-Z]?\b", r"\bRTX\d{4,5}\b", r"\bA\d{2,3}\b"]:
        match = re.search(pattern, text)
        if match:
            return match.group(0)

    tokens = re.findall(r"[A-Z0-9]+", text)
    for token in tokens:
        if len(token) >= 6:
            return token
    return ""


def _extract_cpu_model_number(value: str) -> str:
    matches = re.findall(r"\b(\d{4})\b", str(value or ""))
    if matches:
        return matches[-1]
    compact = normalize_part_number(value)
    compact_match = re.search(r"(\d{4})", compact)
    return compact_match.group(1) if compact_match else ""


def _bom_expected_hints(value: str) -> list[str]:
    normalized_value = normalize_part_number(value)
    hints = list(BOM_MODEL_HINTS.get(normalized_value, []))

    if "MCX7" in normalized_value or "MCX75" in normalized_value:
        hints.append("CONNECTX-7")
    if "MCX6" in normalized_value:
        hints.append("CONNECTX-6")
    if "L20" in normalized_value:
        hints.append("L20")

    deduped: list[str] = []
    for hint in hints:
        if hint and hint not in deduped:
            deduped.append(hint)
    return deduped


def make_decision(
    expected: dict[str, Any],
    actual: dict[str, Any],
    mismatches: list[dict[str, Any]],
    matched_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    actions: list[str] = []
    risk_level = "Low"
    recommendation = "Go"
    reasons: list[str] = []

    if not actual:
        risk_level = "High"
        recommendation = "No-Go"
        reasons.append("No actual system or firmware evidence was available for shipment review.")
        actions.append("Collect actual DUT evidence before making any shipment decision.")

    open_major_issues = [
        issue
        for issue in matched_issues
        if issue.get("level", "").lower() in {"major", "critical", "high"}
    ]
    open_minor_issues = [
        issue for issue in matched_issues if issue.get("level", "").lower() == "minor"
    ]
    probe_attention = collect_probe_attention_items(actual)
    hardware_mismatches = [
        item for item in mismatches if classify_mismatch_category(item) == "hardware"
    ]
    firmware_mismatches = [
        item for item in mismatches if classify_mismatch_category(item) == "firmware"
    ]

    if mismatches:
        risk_level = "Medium"
        recommendation = "Conditional Go"
        reasons.append(f"Detected {len(mismatches)} expected-vs-actual mismatch item(s).")
        actions.append("Review mismatched fields with PM/AE before shipment.")

    bios_or_bmc_mismatch = any(
        item.get("component") in {"BIOS", "BMC"} for item in mismatches
    )
    major_bios_or_bmc_issue = any(
        canonical_component_name(token.strip()) in {"BIOS", "BMC"}
        for issue in open_major_issues
        for token in re.split(r"[,/]", issue.get("type", ""))
    )

    if open_major_issues:
        risk_level = "High"
        recommendation = "No-Go"
        reasons.append(
            f"Open major issue(s) remain: {', '.join(issue['item'] for issue in open_major_issues)}."
        )
        actions.append("Resolve or waive major open issues before ES/sample shipment.")

    if open_minor_issues and recommendation == "Go":
        risk_level = "Medium"
        recommendation = "Conditional Go"
        reasons.append("Open minor issues still require visibility before shipment.")
        actions.append("Share known issue list and workaround with stakeholders.")

    if bios_or_bmc_mismatch and major_bios_or_bmc_issue:
        risk_level = "High"
        recommendation = "No-Go"
        reasons.append("BIOS/BMC mismatch overlaps with an open major firmware issue.")
        actions.append("Align BIOS/BMC versions with tracking sheet or update release decision.")

    if len(hardware_mismatches) >= 3:
        risk_level = "High"
        recommendation = "No-Go"
        reasons.append(
            "Detected significant hardware BOM divergence from the PM tracking sheet."
        )
        actions.append("Stop shipment review and verify the DUT build configuration against the PM tracking sheet.")
    elif hardware_mismatches and recommendation == "Go":
        risk_level = "Medium"
        recommendation = "Conditional Go"
        reasons.append("Detected hardware configuration differences that still require review.")
        actions.append("Review hardware configuration differences with PM / AE / DQA.")

    if probe_attention:
        if recommendation == "Go":
            risk_level = "Medium"
            recommendation = "Conditional Go"
        reasons.append("Agent-executed probe scripts found attention items that still need human review.")
        actions.append("Review the agent-executed probe findings before shipment.")

    if not reasons:
        reasons.append("No critical mismatch or blocking known issue was found in version 1 rules.")

    return {
        "risk_level": risk_level,
        "recommendation": recommendation,
        "decision_reasons": reasons,
        "action_items": actions,
        "mismatch_category_counts": {
            "firmware": len(firmware_mismatches),
            "hardware": len(hardware_mismatches),
            "other": max(len(mismatches) - len(firmware_mismatches) - len(hardware_mismatches), 0),
        },
    }


def build_explainability(
    report: dict[str, Any],
    mismatches: list[dict[str, Any]],
    matched_issues: list[dict[str, Any]],
    decision: dict[str, Any],
) -> dict[str, Any]:
    parsed = report.get("parsed", {})
    expected = parsed.get("expected_config") or {}
    actual = parsed.get("actual_config") or {}
    known_issues = parsed.get("known_issues") or []
    mapping = report.get("role_candidates", {})
    probe_plan = actual.get("probe_plan") or build_probe_plan(expected, known_issues)
    probe_attention = collect_probe_attention_items(actual)
    executed_probe_summary = collect_probe_execution_summary(actual)

    open_major_issues = [
        issue
        for issue in matched_issues
        if issue.get("status", "").lower() == "open"
        and issue.get("level", "").lower() in {"major", "critical", "high"}
    ]
    open_minor_issues = [
        issue
        for issue in matched_issues
        if issue.get("status", "").lower() == "open"
        and issue.get("level", "").lower() == "minor"
    ]

    data_gaps = detect_data_gaps(report)
    problem_details = build_problem_details(
        mismatches,
        matched_issues,
        data_gaps,
        probe_attention,
    )
    risk_breakdown = build_risk_breakdown(
        mismatches,
        open_major_issues,
        open_minor_issues,
        data_gaps,
        probe_attention,
    )
    evidence_summary = build_evidence_summary(
        report,
        expected=expected,
        actual=actual,
        known_issues=known_issues,
        matched_issues=matched_issues,
        data_gaps=data_gaps,
        probe_plan=probe_plan,
        executed_probe_summary=executed_probe_summary,
        probe_attention=probe_attention,
        mismatch_category_counts=decision.get("mismatch_category_counts", {}),
    )
    recommended_owner = recommend_owner(
        mismatches=mismatches,
        open_major_issues=open_major_issues,
        open_minor_issues=open_minor_issues,
        data_gaps=data_gaps,
    )
    suggested_next_step = suggest_next_step(
        decision=decision,
        mismatches=mismatches,
        open_major_issues=open_major_issues,
        open_minor_issues=open_minor_issues,
        data_gaps=data_gaps,
    )
    summary_text = summarize_outcome(
        decision=decision,
        mismatches=mismatches,
        open_major_issues=open_major_issues,
        open_minor_issues=open_minor_issues,
        data_gaps=data_gaps,
    )

    return {
        "summary_text": summary_text,
        "problem_details": problem_details,
        "risk_breakdown": risk_breakdown,
        "recommended_owner": recommended_owner,
        "suggested_next_step": suggested_next_step,
        "evidence_summary": evidence_summary,
        "data_gaps": data_gaps,
        "probe_plan": probe_plan,
        "probe_attention_items": probe_attention,
        "executed_probe_summary": executed_probe_summary,
        "selected_sources": {
            "expected_configuration": mapping.get("expected_configuration"),
            "actual_configuration": mapping.get("actual_configuration"),
            "known_issues": mapping.get("known_issues"),
        },
    }


def _compare_identity_field(
    mismatches: list[dict[str, Any]],
    field: str,
    expected_value: str,
    actual_candidates: list[str],
) -> None:
    if not expected_value:
        return

    expected_norm = normalize_part_number(expected_value)
    actual_norms = [normalize_part_number(candidate) for candidate in actual_candidates if candidate]
    if not actual_norms:
        return

    if not any(_identity_values_match(expected_norm, actual_norm) for actual_norm in actual_norms):
        mismatches.append(
            {
                "field": field,
                "component": "",
                "expected": expected_value,
                "actual": actual_candidates[0],
                "severity": "medium",
            }
        )


def _identity_values_match(expected_norm: str, actual_norm: str) -> bool:
    if not expected_norm or not actual_norm:
        return False
    if expected_norm == actual_norm:
        return True

    shorter, longer = sorted([expected_norm, actual_norm], key=len)
    # Treat product-family style matches as aligned, for example:
    # SKY642E3 <-> SKY642E32501ES or SKY642E3STANDARD.
    if len(shorter) >= 7 and longer.startswith(shorter):
        return True
    return False


def detect_data_gaps(report: dict[str, Any]) -> list[str]:
    parsed = report.get("parsed", {})
    mapping = report.get("role_candidates", {})
    expected = parsed.get("expected_config") or {}
    actual = parsed.get("actual_config") or {}
    known_issues = parsed.get("known_issues") or []

    gaps: list[str] = []
    if not mapping.get("expected_configuration") or not expected:
        gaps.append("Expected configuration evidence missing.")
    if not mapping.get("actual_configuration") or not actual:
        gaps.append("Actual system / firmware evidence missing.")
    if not mapping.get("known_issues"):
        gaps.append("Known issue evidence missing.")

    expected_fw = expected.get("firmware_versions", {})
    actual_fw = actual.get("firmware_versions", {})
    missing_fw = sorted(component for component in expected_fw if component not in actual_fw)
    if missing_fw:
        gaps.append(
            "Actual firmware evidence missing for: {}.".format(", ".join(missing_fw))
        )

    if actual and "bmc_ip_address" not in actual:
        gaps.append("BMC IP evidence missing from actual system data.")

    return gaps


def build_problem_details(
    mismatches: list[dict[str, Any]],
    matched_issues: list[dict[str, Any]],
    data_gaps: list[str],
    probe_attention: list[str],
) -> list[str]:
    details: list[str] = []
    for item in mismatches:
        component = item.get("component") or item.get("field")
        details.append(
            "Agent detected a mismatch in {}: expected {}, actual {}.".format(
                component,
                item.get("expected", "N/A"),
                item.get("actual", "N/A"),
            )
        )

    for issue in matched_issues:
        if issue.get("status", "").lower() != "open":
            continue
        details.append(
            "Agent detected open {} issue {} affecting {}: {}.".format(
                issue.get("level", "unknown").lower(),
                issue.get("item", "N/A"),
                issue.get("type", "unspecified component"),
                issue.get("description", "No description"),
            )
        )

    for gap in data_gaps:
        details.append(f"Agent found missing evidence: {gap}")

    for item in probe_attention:
        details.append(f"Agent probe attention: {item}")

    if not details:
        details.append(
            "Agent did not detect blocking problems from the currently available evidence."
        )

    return details


def build_risk_breakdown(
    mismatches: list[dict[str, Any]],
    open_major_issues: list[dict[str, Any]],
    open_minor_issues: list[dict[str, Any]],
    data_gaps: list[str],
    probe_attention: list[str],
) -> list[dict[str, str]]:
    mismatch_components = [item.get("component") or item.get("field") for item in mismatches]
    hardware_mismatches = [item for item in mismatches if classify_mismatch_category(item) == "hardware"]
    firmware_mismatches = [item for item in mismatches if classify_mismatch_category(item) == "firmware"]

    items = [
        {
            "title": "Configuration Alignment",
            "level": "high" if mismatches else "low",
            "detail": (
                "Agent compared expected and actual values and found mismatch(es) in {}. Firmware mismatch count: {}. Hardware mismatch count: {}.".format(
                    ", ".join(mismatch_components),
                    len(firmware_mismatches),
                    len(hardware_mismatches),
                )
                if mismatches
                else "Agent compared expected and actual values and did not detect parsed mismatches."
            ),
        },
        {
            "title": "Known Issue Exposure",
            "level": (
                "high"
                if open_major_issues
                else "medium"
                if open_minor_issues
                else "low"
            ),
            "detail": (
                "Agent found {} open major issue(s) and {} open minor issue(s).".format(
                    len(open_major_issues),
                    len(open_minor_issues),
                )
                if (open_major_issues or open_minor_issues)
                else "Agent did not find matched open known issues from the current evidence."
            ),
        },
        {
            "title": "Evidence Completeness",
            "level": "medium" if data_gaps else "low",
            "detail": (
                "Agent found evidence gaps: {}.".format("; ".join(data_gaps))
                if data_gaps
                else "Agent had the expected evidence sources needed for this version-1 review."
            ),
        },
    ]
    if probe_attention:
        items.append(
            {
                "title": "Agent Probe Signals",
                "level": "medium",
                "detail": "Agent-executed probe scripts found attention item(s): {}.".format(
                    "; ".join(probe_attention[:3])
                ),
            }
        )
    return items


def build_evidence_summary(
    report: dict[str, Any],
    expected: dict[str, Any],
    actual: dict[str, Any],
    known_issues: list[dict[str, Any]],
    matched_issues: list[dict[str, Any]],
    data_gaps: list[str],
    probe_plan: dict[str, Any],
    executed_probe_summary: list[str],
    probe_attention: list[str],
    mismatch_category_counts: dict[str, int],
) -> list[str]:
    summary = [
        "Agent inspected {} source item(s).".format(len(report.get("sheet_names", []))),
        "Agent selected expected source: {}.".format(
            report.get("role_candidates", {}).get("expected_configuration") or "none"
        ),
        "Agent selected actual source: {}.".format(
            report.get("role_candidates", {}).get("actual_configuration") or "none"
        ),
        "Agent selected known issue source: {}.".format(
            report.get("role_candidates", {}).get("known_issues") or "none"
        ),
        "Agent extracted {} expected firmware value(s).".format(
            len(expected.get("firmware_versions", {}))
        ),
        "Agent extracted {} actual firmware value(s).".format(
            len(actual.get("firmware_versions", {}))
        ),
        "Agent reviewed {} known issue record(s), with {} matched open issue(s).".format(
            len(known_issues),
            len(matched_issues),
        ),
    ]
    if mismatch_category_counts:
        counts = mismatch_category_counts
        summary.append(
            "Agent categorized mismatches as firmware={}, hardware={}, other={}.".format(
                counts.get("firmware", 0),
                counts.get("hardware", 0),
                counts.get("other", 0),
            )
        )
    if probe_plan.get("selected_probe_ids"):
        summary.append(
            "Agent planned {} repo-defined probe script(s): {}.".format(
                len(probe_plan["selected_probe_ids"]),
                ", ".join(probe_plan["selected_probe_ids"]),
            )
        )
    summary.extend(executed_probe_summary[:4])
    if probe_attention:
        summary.append(
            "Agent probe scripts surfaced {} attention item(s) for human review.".format(
                len(probe_attention)
            )
        )
    if data_gaps:
        summary.append(
            "Agent found {} evidence gap(s) that reduce decision confidence.".format(
                len(data_gaps)
            )
        )
    return summary


def recommend_owner(
    mismatches: list[dict[str, Any]],
    open_major_issues: list[dict[str, Any]],
    open_minor_issues: list[dict[str, Any]],
    data_gaps: list[str],
) -> str:
    components = {item.get("component") for item in mismatches if item.get("component")}
    hardware_heavy = bool({"CPU", "MEMORY", "GPU", "NIC", "STORAGE"} & components)
    issue_text = " ".join(issue.get("type", "") for issue in open_major_issues + open_minor_issues)
    fw_heavy = bool({"BIOS", "BMC", "FPGA", "NVRAM", "BMCONF"} & components) or any(
        token in issue_text.upper() for token in ["BIOS", "BMC", "FPGA", "NVRAM", "BMCONF"]
    )

    if hardware_heavy and fw_heavy:
        return "AE / DQA / RD"
    if hardware_heavy:
        return "AE / DQA"
    if open_major_issues and fw_heavy:
        return "AE / Firmware RD"
    if open_major_issues:
        return "AE / RD"
    if mismatches and fw_heavy:
        return "AE / Firmware RD"
    if data_gaps and "Actual system / firmware evidence missing." in data_gaps:
        return "AE"
    if data_gaps and "Known issue evidence missing." in data_gaps:
        return "PM / AE"
    if open_minor_issues:
        return "PM / AE"
    if mismatches:
        return "PM / AE"
    return "PM"


def suggest_next_step(
    decision: dict[str, Any],
    mismatches: list[dict[str, Any]],
    open_major_issues: list[dict[str, Any]],
    open_minor_issues: list[dict[str, Any]],
    data_gaps: list[str],
) -> str:
    hardware_mismatches = [item for item in mismatches if classify_mismatch_category(item) == "hardware"]
    if open_major_issues:
        return "Stop shipment review, resolve or waive the major issue, then rerun the agent assessment."
    if len(hardware_mismatches) >= 3:
        return "Stop shipment review, verify the DUT hardware build against the PM tracking sheet, then rerun the agent comparison."
    if mismatches:
        return "Align the mismatched configuration items with PM and AE, then rerun the comparison."
    if data_gaps:
        return "Collect the missing evidence, update the case data, and rerun the agent review."
    if open_minor_issues:
        return "Proceed with controlled follow-up, share the workaround, and track closure before shipment."
    if decision.get("action_items"):
        return decision["action_items"][0]
    return "Proceed with the current shipment workflow and keep monitoring for new issues."


def summarize_outcome(
    decision: dict[str, Any],
    mismatches: list[dict[str, Any]],
    open_major_issues: list[dict[str, Any]],
    open_minor_issues: list[dict[str, Any]],
    data_gaps: list[str],
) -> str:
    recommendation = decision.get("recommendation")
    hardware_mismatches = [item for item in mismatches if classify_mismatch_category(item) == "hardware"]
    if recommendation == "No-Go":
        if data_gaps and "Actual system / firmware evidence missing." in data_gaps:
            return "Agent could not make a shipment decision because actual DUT evidence is missing."
        if len(hardware_mismatches) >= 3:
            return "Agent found significant hardware BOM divergence from the PM tracking sheet, so shipment should stop."
        if open_major_issues and mismatches:
            return "Agent found blocking mismatches together with open major issues, so shipment should stop."
        if open_major_issues:
            return "Agent found an open major issue that blocks shipment."
        return "Agent found blocking evidence and recommended stopping shipment."

    if recommendation == "Conditional Go":
        if mismatches and data_gaps:
            return "Agent found expected-vs-actual mismatches together with evidence gaps, so follow-up review is required before shipment."
        if mismatches:
            return "Agent found non-blocking mismatches that require review before shipment."
        if data_gaps:
            return "Agent found missing evidence and recommends follow-up review before shipment."
        if open_minor_issues:
            return "Agent found open minor issues that require controlled follow-up before shipment."
        return "Agent recommended a cautious shipment decision with follow-up actions."

    return "Agent found aligned evidence with no open blocking issue and recommended shipment can proceed."


def collect_probe_attention_items(actual: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for key in ["tracking_probe", "pcie_probe", "operational_probe"]:
        probe = actual.get(key) or {}
        for item in probe.get("attention_items", []) or []:
            if item and item not in items:
                items.append(str(item))
    return items


def collect_probe_execution_summary(actual: dict[str, Any]) -> list[str]:
    summary: list[str] = []
    for key in ["tracking_probe", "pcie_probe", "operational_probe"]:
        probe = actual.get(key) or {}
        for item in probe.get("summary", []) or []:
            if item and item not in summary:
                summary.append(str(item))
    return summary


def classify_mismatch_category(item: dict[str, Any]) -> str:
    field = str(item.get("field") or "").lower()
    component = str(item.get("component") or "").upper()
    if field.startswith("firmware_versions.") or component in {"BIOS", "BMC", "FPGA", "NVRAM", "BMCONF", "BL", "CPLD", "BSP"}:
        return "firmware"
    if field.startswith("hardware.") or component in {"CPU", "MEMORY", "GPU", "NIC", "STORAGE"}:
        return "hardware"
    return "other"
