from __future__ import annotations

import json
import re
import subprocess
from typing import Any


def main() -> None:
    print(json.dumps(collect_operational_attention(), indent=2, ensure_ascii=False))


def collect_operational_attention() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "collector": "operational_attention_v1",
        "commands_ran": [],
        "summary": [],
        "attention_items": [],
    }

    failed_services_output = _run(["systemctl", "--failed", "--no-legend", "--plain"])
    payload["commands_ran"].append("systemctl --failed --no-legend --plain")
    failed_services = _parse_failed_services(failed_services_output)
    payload["failed_services"] = failed_services
    if failed_services:
        payload["summary"].append(
            "Detected {} failed systemd unit(s).".format(len(failed_services))
        )
        payload["attention_items"].append(
            "Failed services detected: {}.".format(", ".join(service["unit"] for service in failed_services[:5]))
        )
    else:
        payload["summary"].append("No failed systemd units were detected.")

    dmesg_output = _run(["dmesg", "--level=err,crit,alert,emerg"])
    payload["commands_ran"].append("dmesg --level=err,crit,alert,emerg")
    dmesg_lines = _sample_lines(dmesg_output, limit=12)
    payload["kernel_error_lines"] = dmesg_lines
    if dmesg_lines:
        payload["summary"].append(
            "Detected {} recent kernel error line(s) from dmesg.".format(len(dmesg_lines))
        )
        payload["attention_items"].append(
            "Kernel error signals were present in dmesg; review the captured lines for device or driver issues."
        )

    sel_output = _run(["ipmitool", "sel", "elist"])
    payload["commands_ran"].append("ipmitool sel elist")
    sel_lines = _sample_lines(sel_output, limit=12)
    payload["bmc_sel_lines"] = sel_lines
    if sel_lines:
        payload["summary"].append(
            "BMC SEL returned {} sampled record line(s).".format(len(sel_lines))
        )
        if _contains_sel_attention(sel_lines):
            payload["attention_items"].append(
                "BMC SEL contains non-empty event records; review BMC event history before shipment."
            )

    return payload


def _run(argv: list[str]) -> str:
    completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    return completed.stdout if completed.returncode == 0 else ""


def _parse_failed_services(text: str) -> list[dict[str, str]]:
    services: list[dict[str, str]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        services.append(
            {
                "unit": parts[0],
                "load": parts[1],
                "active": parts[2],
                "sub": parts[3],
                "description": " ".join(parts[4:]).strip(),
            }
        )
    return services


def _sample_lines(text: str, *, limit: int) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[:limit]


def _contains_sel_attention(lines: list[str]) -> bool:
    joined = " ".join(lines).lower()
    return any(token in joined for token in ["assert", "critical", "failure", "deassert", "oem"])


if __name__ == "__main__":
    main()
