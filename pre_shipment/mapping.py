"""Field aliases and sheet-role hints for version 1."""

from __future__ import annotations

import re

SHEET_ROLE_HINTS = {
    "expected_configuration": ["ms1", "schedule", "tracking"],
    "actual_configuration": ["sysinfo", "system info", "ms4"],
    "known_issues": ["known issue", "known issues"],
}

COMPONENT_ALIASES = {
    "bios": "BIOS",
    "bios nvram": "NVRAM",
    "nvram": "NVRAM",
    "bmc": "BMC",
    "bmconf": "BMCONF",
    "fpga": "FPGA",
    "bl": "BL",
    "cpld": "CPLD",
    "bsp": "BSP",
    "bypass fw.": "BYPASS_FW",
    "bypass fw": "BYPASS_FW",
    "bypass utility ver.": "BYPASS_UTILITY",
    "bypass utility ver": "BYPASS_UTILITY",
    "nic drivers": "NIC_DRIVERS",
    "nic firmware": "NIC_FIRMWARE",
    "firmware": "FIRMWARE",
    "me": "ME",
}

HARDWARE_FIELD_ALIASES = {
    "system level": "system_level",
    "cpu board": "cpu_board",
    "cpu": "cpu",
    "memory": "memory",
    "ssd": "ssd",
    "hdd": "hdd",
    "nvme": "nvme",
    "pcie card": "pcie_card",
    "gpu card": "gpu_card",
    "raid module": "raid_module",
    "tpm": "tpm",
    "npi phase": "npi_phase",
}

ACTUAL_INFO_ALIASES = {
    "product name": "product_name",
    "product part number": "product_part_number",
    "product version": "product_version",
    "product serial": "product_serial",
    "board part number": "board_part_number",
    "board product": "board_product",
    "board serial": "board_serial",
    "chassis part number": "chassis_part_number",
    "chassis serial": "chassis_serial",
    "ip address": "bmc_ip_address",
    "mac address": "bmc_mac_address",
}

EXPECTED_FIRMWARE_COMPONENTS = {
    "BIOS",
    "NVRAM",
    "FPGA",
    "CPLD",
    "BL",
    "BMC",
    "BMCONF",
    "BSP",
    "BYPASS_FW",
    "BYPASS_UTILITY",
    "NIC_DRIVERS",
    "NIC_FIRMWARE",
    "ME",
}


def canonical_component_name(value: str) -> str:
    key = " ".join((value or "").strip().lower().split())
    return COMPONENT_ALIASES.get(key, key.upper().replace(" ", "_"))


def normalize_version(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    text = text.split()[0].strip()
    text = re.sub(r"^[vV]", "", text)
    if re.fullmatch(r"\d+(\.\d+)?", text):
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"
    return text.lower()


def normalize_part_number(value: str) -> str:
    text = re.sub(r"[^A-Z0-9]", "", (value or "").upper())
    if text.endswith("ES"):
        return text[:-2]
    return text
