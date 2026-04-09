from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any


def main() -> None:
    payload = collect_tracking_relevant_inventory()
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def collect_tracking_relevant_inventory() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "collector": "tracking_relevant_inventory_v1",
        "commands_ran": [],
        "summary": [],
    }

    lscpu = _run(["lscpu"])
    payload["commands_ran"].append("lscpu")
    payload["cpu"] = _parse_lscpu(lscpu)
    if payload["cpu"]:
        payload["summary"].append(
            "Collected CPU inventory: {} socket(s), model {}.".format(
                payload["cpu"].get("sockets", "N/A"),
                payload["cpu"].get("model_name", "unknown"),
            )
        )

    memory = _collect_memory()
    payload["commands_ran"].extend(memory.pop("commands_ran", []))
    payload["memory"] = memory
    if memory:
        payload["summary"].append(
            "Collected memory inventory: {} populated DIMM(s), total {} GiB.".format(
                memory.get("populated_dimms", 0),
                memory.get("total_gib", "N/A"),
            )
        )

    storage = _collect_storage()
    payload["commands_ran"].extend(storage.pop("commands_ran", []))
    payload["storage"] = storage
    if storage:
        payload["summary"].append(
            "Collected storage inventory: {} block device(s).".format(
                storage.get("device_count", 0)
            )
        )

    gpu = _collect_gpu()
    payload["commands_ran"].extend(gpu.pop("commands_ran", []))
    payload["gpu"] = gpu
    if gpu:
        payload["summary"].append(
            "Collected GPU inventory: {} GPU(s) {}.".format(
                gpu.get("gpu_count", 0),
                ", ".join(gpu.get("models", [])) or "unknown",
            )
        )

    return payload


def _collect_memory() -> dict[str, Any]:
    result: dict[str, Any] = {"commands_ran": []}

    free_output = _run(["free", "-g"])
    result["commands_ran"].append("free -g")
    total_gib = _parse_total_memory_gib(free_output)

    dmidecode_output = _run(["dmidecode", "-t", "memory"])
    result["commands_ran"].append("dmidecode -t memory")
    dimm_sizes = _parse_memory_dimms(dmidecode_output)

    if total_gib is not None:
        result["total_gib"] = total_gib
    if dimm_sizes:
        result["populated_dimms"] = len(dimm_sizes)
        result["dimm_sizes_gib"] = dimm_sizes
        result["dimm_size_summary"] = _count_values(dimm_sizes)

    return result


def _collect_storage() -> dict[str, Any]:
    result: dict[str, Any] = {"commands_ran": []}
    lsblk_output = _run(["lsblk", "-J", "-o", "NAME,SIZE,MODEL,TYPE,MOUNTPOINT"])
    result["commands_ran"].append("lsblk -J -o NAME,SIZE,MODEL,TYPE,MOUNTPOINT")
    try:
        parsed = json.loads(lsblk_output)
    except json.JSONDecodeError:
        return result

    devices: list[dict[str, str]] = []
    for item in parsed.get("blockdevices", []):
        if item.get("type") != "disk":
            continue
        devices.append(
            {
                "name": str(item.get("name", "")),
                "size": str(item.get("size", "")),
                "model": str(item.get("model", "")).strip(),
                "mountpoint": str(item.get("mountpoint", "")),
            }
        )
    result["devices"] = devices
    result["device_count"] = len(devices)
    return result


def _collect_gpu() -> dict[str, Any]:
    result: dict[str, Any] = {"commands_ran": []}
    models: list[str] = []
    gpu_count = 0

    if shutil.which("nvidia-smi"):
        output = _run(["nvidia-smi", "-L"])
        result["commands_ran"].append("nvidia-smi -L")
        for line in output.splitlines():
            match = re.match(r"GPU \d+:\s*(?P<model>.+?)\s*\(UUID:", line.strip())
            if not match:
                continue
            gpu_count += 1
            model = match.group("model").strip()
            if model not in models:
                models.append(model)

    if not gpu_count:
        lspci_output = _run(["lspci", "-nn"])
        result["commands_ran"].append("lspci -nn")
        seen_bdfs: set[str] = set()
        for line in lspci_output.splitlines():
            if "NVIDIA" not in line:
                continue
            match = re.match(r"(?P<bdf>[0-9a-fA-F:.]+)\s+.+?NVIDIA Corporation\s+(?P<model>.+)", line)
            if not match:
                continue
            bdf = match.group("bdf")
            if bdf in seen_bdfs:
                continue
            seen_bdfs.add(bdf)
            gpu_count += 1
            model = match.group("model").strip()
            if model not in models:
                models.append(model)

    result["gpu_count"] = gpu_count
    result["models"] = models
    return result


def _run(argv: list[str]) -> str:
    completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    return completed.stdout if completed.returncode == 0 else ""


def _parse_lscpu(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    alias_map = {
        "model name": "model_name",
        "socket(s)": "sockets",
        "core(s) per socket": "cores_per_socket",
        "thread(s) per core": "threads_per_core",
        "cpu(s)": "cpu_count",
    }
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        mapped = alias_map.get(key.lower())
        if mapped:
            fields[mapped] = value
    return fields


def _parse_total_memory_gib(text: str) -> int | None:
    for line in text.splitlines():
        if not line.startswith("Mem:"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            try:
                return int(parts[1])
            except ValueError:
                return None
    return None


def _parse_memory_dimms(text: str) -> list[int]:
    dimm_sizes: list[int] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("Size:"):
            continue
        if "No Module Installed" in stripped:
            continue
        match = re.search(r"Size:\s*(?P<size>\d+)\s*GB", stripped, flags=re.IGNORECASE)
        if match:
            dimm_sizes.append(int(match.group("size")))
    return dimm_sizes


def _count_values(values: list[int]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


if __name__ == "__main__":
    main()
