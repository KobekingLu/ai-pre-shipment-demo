from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any


def main() -> None:
    print(json.dumps(collect_pcie_device_inventory(), indent=2, ensure_ascii=False))


def collect_pcie_device_inventory() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "collector": "pcie_device_inventory_v1",
        "commands_ran": [],
        "summary": [],
        "attention_items": [],
    }

    lspci_output = _run(["lspci", "-nn"])
    payload["commands_ran"].append("lspci -nn")
    if not lspci_output:
        payload["attention_items"].append("PCIe inventory command 'lspci -nn' was not available or returned no data.")
        return payload

    devices = _parse_lspci(lspci_output)
    payload["gpu_devices"] = devices["gpu"]
    payload["nic_devices"] = devices["nic"]
    payload["storage_devices"] = devices["storage"]

    payload["summary"].append(
        "Collected PCIe inventory: {} GPU device(s), {} NIC device(s), {} storage-controller device(s).".format(
            len(devices["gpu"]),
            len(devices["nic"]),
            len(devices["storage"]),
        )
    )

    gpu_models = sorted({device["label"] for device in devices["gpu"] if device.get("label")})
    nic_models = sorted({device["label"] for device in devices["nic"] if device.get("label")})

    if len(gpu_models) > 1:
        payload["attention_items"].append(
            "Mixed GPU models were detected: {}.".format(", ".join(gpu_models))
        )
    if len(nic_models) > 1:
        payload["attention_items"].append(
            "Multiple NIC controller models were detected: {}.".format(", ".join(nic_models[:4]))
        )

    nvidia_details = _collect_nvidia_details()
    payload["commands_ran"].extend(nvidia_details.pop("commands_ran", []))
    if nvidia_details:
        payload["nvidia_gpu_details"] = nvidia_details
        if nvidia_details.get("summary"):
            payload["summary"].append(nvidia_details["summary"])

    return payload


def _collect_nvidia_details() -> dict[str, Any]:
    result: dict[str, Any] = {"commands_ran": []}
    if not shutil.which("nvidia-smi"):
        return result

    output = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total",
            "--format=csv,noheader",
        ]
    )
    result["commands_ran"].append(
        "nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader"
    )
    if not output:
        return result

    gpus: list[dict[str, str]] = []
    models: list[str] = []
    drivers: list[str] = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        gpu = {
            "name": parts[0],
            "driver_version": parts[1],
            "memory_total": parts[2],
        }
        gpus.append(gpu)
        if gpu["name"] not in models:
            models.append(gpu["name"])
        if gpu["driver_version"] not in drivers:
            drivers.append(gpu["driver_version"])

    if not gpus:
        return result

    result["gpus"] = gpus
    result["summary"] = "Collected NVIDIA details: {} GPU entries, driver {}.".format(
        len(gpus),
        ", ".join(drivers),
    )
    return result


def _run(argv: list[str]) -> str:
    completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    return completed.stdout if completed.returncode == 0 else ""


def _parse_lspci(text: str) -> dict[str, list[dict[str, str]]]:
    devices = {"gpu": [], "nic": [], "storage": []}
    for line in text.splitlines():
        lowered = line.lower()
        bdf_match = re.match(r"(?P<bdf>[0-9a-fA-F:.]+)\s+(?P<rest>.+)$", line)
        if not bdf_match:
            continue
        bdf = bdf_match.group("bdf")
        rest = bdf_match.group("rest").strip()
        label = _device_label(rest)

        device = {"bdf": bdf, "model": rest, "label": label}
        if "3d controller" in lowered or "vga compatible controller" in lowered:
            if "nvidia" in lowered or "amd/ati" in lowered:
                devices["gpu"].append(device)
            continue

        if "ethernet controller" in lowered or "network controller" in lowered:
            devices["nic"].append(device)
            continue

        if any(token in lowered for token in ["non-volatile memory controller", "raid bus controller", "sata controller"]):
            devices["storage"].append(device)

    return devices


def _device_label(raw_model: str) -> str:
    text = re.sub(r"\(rev [^)]+\)", "", raw_model).strip()
    text = re.sub(r"\[[0-9a-fA-F]{4}:[0-9a-fA-F]{4}\]", "", text).strip()
    text = re.sub(
        r"^(?:3D controller \[[^\]]+\]:|VGA compatible controller \[[^\]]+\]:|Ethernet controller \[[^\]]+\]:|Network controller \[[^\]]+\]:|Non-Volatile memory controller \[[^\]]+\]:|RAID bus controller \[[^\]]+\]:|SATA controller \[[^\]]+\]:)\s*",
        "",
        text,
    ).strip()
    text = re.sub(
        r"^(?:NVIDIA Corporation|Intel Corporation|Mellanox Technologies|Broadcom Inc\. and subsidiaries)\s+",
        "",
        text,
    ).strip()

    friendly_tokens = [
        token
        for token in re.findall(r"\[([^\]]+)\]", text)
        if not re.fullmatch(r"[0-9a-fA-F]{4}:[0-9a-fA-F]{4}", token)
        and not re.fullmatch(r"[0-9a-fA-F]{4}", token)
    ]
    if friendly_tokens:
        return friendly_tokens[0].strip()

    text = re.sub(r"\[[^\]]+\]", "", text).strip()
    return " ".join(text.split())


if __name__ == "__main__":
    main()
