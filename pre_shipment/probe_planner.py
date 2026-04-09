"""Minimal probe planner for DUT collection based on PM tracking-sheet expectations."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from pre_shipment.parser import inspect_workbook
from pre_shipment.xlsx_reader import read_workbook

PROBE_LIBRARY: dict[str, dict[str, Any]] = {
    "tracking_probe": {
        "id": "tracking_probe",
        "description": "Collect CPU, memory, storage, and GPU inventory that is commonly needed for shipment review.",
        "local_script": "../common_scripts/collect_tracking_relevant_inventory.py",
        "collect_as": {"kind": "json_payload", "target": "tracking_probe"},
    },
    "pcie_probe": {
        "id": "pcie_probe",
        "description": "Collect PCIe-facing inventory for GPU, NIC, and storage controllers.",
        "local_script": "../common_scripts/collect_pcie_device_inventory.py",
        "collect_as": {"kind": "json_payload", "target": "pcie_probe"},
    },
    "operational_probe": {
        "id": "operational_probe",
        "description": "Collect readable operational attention signals such as failed services, kernel errors, and BMC SEL presence.",
        "local_script": "../common_scripts/collect_operational_attention.py",
        "collect_as": {"kind": "json_payload", "target": "operational_probe"},
    },
}


def load_expected_report_from_workbook(workbook_path: Path) -> dict[str, Any]:
    workbook = read_workbook(workbook_path)
    return inspect_workbook(workbook)


def build_probe_plan(
    expected_config: dict[str, Any],
    known_issues: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    known_issues = known_issues or []
    hardware_blob = " ".join(
        "{} {}".format(item.get("item", ""), item.get("value", ""))
        for item in expected_config.get("hardware_items", [])
    ).lower()
    firmware_components = sorted(expected_config.get("firmware_versions", {}).keys())

    selected_probe_ids = ["tracking_probe"]
    rationale = [
        "Selected tracking_probe as the baseline script for platform inventory needed by most PM tracking-sheet reviews."
    ]
    focus_areas = ["CPU", "memory", "storage", "GPU inventory"]

    if any(token in hardware_blob for token in ["gpu", "nic", "pcie", "ethernet", "network", "nvme", "ssd"]):
        selected_probe_ids.append("pcie_probe")
        rationale.append(
            "Selected pcie_probe because the expected hardware BOM includes PCIe-attached devices such as GPU, NIC, or NVMe items."
        )
        focus_areas.append("PCIe device inventory")

    if firmware_components or known_issues:
        selected_probe_ids.append("operational_probe")
        rationale.append(
            "Selected operational_probe because shipment review should surface readable health signals when firmware evidence or known issues are involved."
        )
        focus_areas.append("operational attention signals")

    expected_targets = _expected_targets(expected_config)
    return {
        "selected_probe_ids": selected_probe_ids,
        "selected_script_count": len(selected_probe_ids),
        "rationale": rationale,
        "focus_areas": focus_areas,
        "expected_targets": expected_targets,
        "probe_specs": [deepcopy(PROBE_LIBRARY[probe_id]) for probe_id in selected_probe_ids],
    }


def apply_probe_plan_to_profile(
    base_profile: dict[str, Any],
    probe_plan: dict[str, Any],
) -> dict[str, Any]:
    profile = deepcopy(base_profile)
    commands = list(profile.get("commands", []))
    existing_ids = {str(entry.get("id") or "") for entry in commands}

    for probe in probe_plan.get("probe_specs", []):
        if probe["id"] in existing_ids:
            continue
        commands.append(
            {
                "id": probe["id"],
                "type": "script",
                "interpreter": "python3",
                "local_script": probe["local_script"],
                "allow_failure": True,
                "collect_as": probe["collect_as"],
            }
        )

    profile["commands"] = commands
    profile["probe_plan"] = {
        key: value
        for key, value in probe_plan.items()
        if key != "probe_specs"
    }
    return profile


def write_planned_profile(
    planned_profile: dict[str, Any],
    *,
    output_dir: Path,
    workbook_path: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / f"{workbook_path.stem}_planned_profile.json"
    target_path.write_text(
        json.dumps(planned_profile, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return target_path


def _expected_targets(expected_config: dict[str, Any]) -> list[str]:
    targets: list[str] = []
    if expected_config.get("system_level"):
        targets.append(f"System level: {expected_config['system_level']}")
    for component in sorted(expected_config.get("firmware_versions", {})):
        targets.append(f"Firmware: {component}")
    for item in expected_config.get("hardware_items", []):
        name = str(item.get("item") or "").strip()
        value = str(item.get("value") or "").strip()
        qty = str(item.get("qty") or "").strip()
        if not name or name.startswith("Project Name:"):
            continue
        if value.upper() in {"N.A.", "N.A", "NA"}:
            value = ""
        target = name
        if value:
            target += f" = {value}"
        if qty:
            target += f" (qty {qty})"
        targets.append(target)
    return targets[:20]
