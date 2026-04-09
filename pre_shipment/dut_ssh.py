"""Restricted SSH collection helpers for DUT evidence gathering.

This module is intentionally small and demo-friendly:
- commands must come from a checked-in command profile
- only a small read-only command allowlist is accepted
- optional scripts can only be staged into a remote /tmp sandbox
- the collector writes all outputs locally as JSON and text artifacts
"""

from __future__ import annotations

import json
import ipaddress
import re
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pre_shipment.mapping import canonical_component_name

SAFE_REMOTE_ROOTS = ("/tmp/", "/var/tmp/")
SAFE_COMMANDS = {
    "cat",
    "dmidecode",
    "ethtool",
    "free",
    "hostnamectl",
    "ip",
    "ipmitool",
    "lsblk",
    "lscpu",
    "python3",
    "uname",
}
SAFE_SCRIPT_INTERPRETERS = {"python3"}
DISALLOWED_TOKEN_PATTERN = re.compile(r"[;&|><`$\\\n\r]")
IPV4_PATTERN = re.compile(r"\binet (?P<ip>\d+\.\d+\.\d+\.\d+)/")


def load_command_profile(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_command_profile(profile: dict[str, Any], profile_path: Path) -> list[str]:
    errors: list[str] = []
    case_id = str(profile.get("case_id") or "").strip()
    if not case_id:
        errors.append("Profile missing case_id.")

    sandbox_root = str(profile.get("remote_sandbox_root") or "").strip()
    if not sandbox_root:
        errors.append("Profile missing remote_sandbox_root.")
    elif not sandbox_root.endswith("/"):
        errors.append("remote_sandbox_root must end with '/'.")
    elif not sandbox_root.startswith(SAFE_REMOTE_ROOTS):
        errors.append("remote_sandbox_root must stay under /tmp/ or /var/tmp/.")

    commands = profile.get("commands")
    if not isinstance(commands, list) or not commands:
        errors.append("Profile must contain at least one command entry.")
        return errors

    seen_ids: set[str] = set()
    for index, entry in enumerate(commands, start=1):
        entry_id = str(entry.get("id") or "").strip()
        if not entry_id:
            errors.append(f"Command #{index} is missing id.")
            continue
        if entry_id in seen_ids:
            errors.append(f"Duplicate command id '{entry_id}'.")
        seen_ids.add(entry_id)

        entry_type = entry.get("type", "command")
        if entry_type not in {"command", "script"}:
            errors.append(f"Command '{entry_id}' has unsupported type '{entry_type}'.")
            continue

        if entry_type == "command":
            argv = entry.get("argv")
            errors.extend(_validate_command_argv(entry_id, argv))
            continue

        interpreter = str(entry.get("interpreter") or "").strip()
        if interpreter not in SAFE_SCRIPT_INTERPRETERS:
            errors.append(
                f"Script '{entry_id}' must use one of: {', '.join(sorted(SAFE_SCRIPT_INTERPRETERS))}."
            )

        local_script = str(entry.get("local_script") or "").strip()
        if not local_script:
            errors.append(f"Script '{entry_id}' is missing local_script.")
            continue

        try:
            script_path = _resolve_script_path(profile_path, local_script)
        except ValueError:
            errors.append(
                f"Script '{entry_id}' points outside the allowed script folders."
            )
            continue

        if script_path.suffix.lower() != ".py":
            errors.append(f"Script '{entry_id}' must point to a .py file.")

        if not script_path.exists():
            errors.append(f"Script '{entry_id}' file does not exist: {script_path}")

        args = entry.get("args", [])
        if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            errors.append(f"Script '{entry_id}' args must be a list of strings.")
        else:
            for arg in args:
                if DISALLOWED_TOKEN_PATTERN.search(arg):
                    errors.append(f"Script '{entry_id}' has unsafe argument '{arg}'.")

    return errors


def run_collection(
    *,
    profile_path: Path,
    host: str,
    output_dir: Path,
    dry_run: bool = False,
    identity_file: Path | None = None,
    port: int = 22,
    connect_timeout: int = 10,
    keep_remote_sandbox: bool = False,
) -> dict[str, Any]:
    profile = load_command_profile(profile_path)
    validation_errors = validate_command_profile(profile, profile_path)
    if validation_errors:
        raise ValueError("Invalid command profile:\n- " + "\n- ".join(validation_errors))

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    case_id = str(profile["case_id"])
    remote_sandbox_dir = f"{profile['remote_sandbox_root']}{case_id}-{run_id}"
    local_run_dir = output_dir / case_id / run_id
    local_run_dir.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "case_id": case_id,
        "profile_path": str(profile_path),
        "host": host,
        "run_id": run_id,
        "dry_run": dry_run,
        "remote_sandbox_dir": remote_sandbox_dir,
        "started_at_utc": datetime.now(UTC).isoformat(),
        "commands": [],
        "parsed_actual_config": {},
        "safety_notes": [
            "Only profile-defined commands are executed by this collector.",
            "Only a small read-only command allowlist is accepted.",
            "Optional scripts may only run from a remote /tmp sandbox.",
            "This reduces risk, but true non-destructive guarantees still require a restricted SSH account on the DUT.",
        ],
    }
    if profile.get("probe_plan"):
        payload["probe_plan"] = profile["probe_plan"]

    if dry_run:
        for entry in profile["commands"]:
            payload["commands"].append(_planned_command_entry(entry, remote_sandbox_dir))
        payload["parsed_actual_config"] = _build_actual_config(
            profile,
            payload["commands"],
            host=host,
        )
        _write_collection_json(local_run_dir / "collection_result.json", payload)
        return payload

    ssh_base = _build_ssh_base_command(
        host=host,
        identity_file=identity_file,
        port=port,
        connect_timeout=connect_timeout,
    )
    scp_base = _build_scp_base_command(
        identity_file=identity_file,
        port=port,
        connect_timeout=connect_timeout,
    )

    _ensure_remote_sandbox(ssh_base, remote_sandbox_dir)
    try:
        for entry in profile["commands"]:
            result = _run_profile_entry(
                entry=entry,
                profile_path=profile_path,
                ssh_base=ssh_base,
                scp_base=scp_base,
                remote_sandbox_dir=remote_sandbox_dir,
                local_run_dir=local_run_dir,
            )
            payload["commands"].append(result)
    finally:
        if not keep_remote_sandbox:
            _cleanup_remote_sandbox(ssh_base, remote_sandbox_dir)

    payload["parsed_actual_config"] = _build_actual_config(
        profile,
        payload["commands"],
        host=host,
    )
    payload["finished_at_utc"] = datetime.now(UTC).isoformat()
    _write_collection_json(local_run_dir / "collection_result.json", payload)
    return payload


def _validate_command_argv(entry_id: str, argv: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) for arg in argv):
        return [f"Command '{entry_id}' argv must be a non-empty list of strings."]

    command_name = argv[0]
    if command_name not in SAFE_COMMANDS:
        errors.append(
            f"Command '{entry_id}' uses '{command_name}', which is outside the allowlist."
        )

    for arg in argv:
        if DISALLOWED_TOKEN_PATTERN.search(arg):
            errors.append(f"Command '{entry_id}' has unsafe token '{arg}'.")

    return errors


def _planned_command_entry(entry: dict[str, Any], remote_sandbox_dir: str) -> dict[str, Any]:
    if entry.get("type", "command") == "script":
        remote_script = f"{remote_sandbox_dir}/{Path(entry['local_script']).name}"
        remote_argv = [entry["interpreter"], remote_script, *entry.get("args", [])]
    else:
        remote_argv = entry["argv"]

    return {
        "id": entry["id"],
        "type": entry.get("type", "command"),
        "planned_remote_command": shlex.join(remote_argv),
        "allow_failure": bool(entry.get("allow_failure", False)),
        "collect_as": entry.get("collect_as", {}),
        "status": "planned",
        "exit_code": None,
        "stdout_path": None,
        "stderr_path": None,
        "stdout": "",
        "stderr": "",
    }


def _build_ssh_base_command(
    *,
    host: str,
    identity_file: Path | None,
    port: int,
    connect_timeout: int,
) -> list[str]:
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"ConnectTimeout={connect_timeout}",
        "-p",
        str(port),
    ]
    if identity_file:
        cmd.extend(["-i", str(identity_file)])
    cmd.append(host)
    return cmd


def _build_scp_base_command(
    *,
    identity_file: Path | None,
    port: int,
    connect_timeout: int,
) -> list[str]:
    cmd = [
        "scp",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"ConnectTimeout={connect_timeout}",
        "-P",
        str(port),
    ]
    if identity_file:
        cmd.extend(["-i", str(identity_file)])
    return cmd


def _ensure_remote_sandbox(ssh_base: list[str], remote_sandbox_dir: str) -> None:
    _assert_safe_remote_sandbox(remote_sandbox_dir)
    remote_cmd = f"umask 077 && mkdir -p {shlex.quote(remote_sandbox_dir)}"
    completed = subprocess.run(
        [*ssh_base, remote_cmd],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Failed to prepare remote sandbox:\n"
            + completed.stderr.strip()
        )


def _cleanup_remote_sandbox(ssh_base: list[str], remote_sandbox_dir: str) -> None:
    _assert_safe_remote_sandbox(remote_sandbox_dir)
    remote_cmd = f"rm -rf {shlex.quote(remote_sandbox_dir)}"
    subprocess.run(
        [*ssh_base, remote_cmd],
        capture_output=True,
        text=True,
        check=False,
    )


def _assert_safe_remote_sandbox(remote_sandbox_dir: str) -> None:
    if not remote_sandbox_dir.startswith(SAFE_REMOTE_ROOTS):
        raise ValueError("Remote sandbox path must stay under /tmp/ or /var/tmp/.")
    stripped = remote_sandbox_dir.rstrip("/")
    if stripped.count("/") < 3:
        raise ValueError("Remote sandbox path is too broad to clean up safely.")


def _run_profile_entry(
    *,
    entry: dict[str, Any],
    profile_path: Path,
    ssh_base: list[str],
    scp_base: list[str],
    remote_sandbox_dir: str,
    local_run_dir: Path,
) -> dict[str, Any]:
    entry_type = entry.get("type", "command")
    if entry_type == "script":
        local_script = _resolve_script_path(profile_path, entry["local_script"])
        remote_script = f"{remote_sandbox_dir}/{local_script.name}"
        _upload_script(
            scp_base=scp_base,
            local_script=local_script,
            remote_target=f"{ssh_base[-1]}:{remote_script}",
        )
        remote_argv = [entry["interpreter"], remote_script, *entry.get("args", [])]
    else:
        remote_argv = list(entry["argv"])

    completed = subprocess.run(
        [*ssh_base, shlex.join(remote_argv)],
        capture_output=True,
        text=True,
        check=False,
    )

    stdout_path = local_run_dir / f"{entry['id']}.stdout.txt"
    stderr_path = local_run_dir / f"{entry['id']}.stderr.txt"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")

    success = completed.returncode == 0 or bool(entry.get("allow_failure", False))
    result = {
        "id": entry["id"],
        "type": entry_type,
        "planned_remote_command": shlex.join(remote_argv),
        "allow_failure": bool(entry.get("allow_failure", False)),
        "collect_as": entry.get("collect_as", {}),
        "status": "ok" if success else "failed",
        "exit_code": completed.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    if completed.returncode != 0 and not entry.get("allow_failure", False):
        raise RuntimeError(
            "Remote command failed for '{}': {}".format(
                entry["id"],
                completed.stderr.strip() or "no stderr",
            )
        )
    return result


def _upload_script(*, scp_base: list[str], local_script: Path, remote_target: str) -> None:
    completed = subprocess.run(
        [*scp_base, str(local_script), remote_target],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Failed to upload script '{}': {}".format(
                local_script.name,
                completed.stderr.strip() or "no stderr",
            )
        )


def _resolve_script_path(profile_path: Path, local_script: str) -> Path:
    script_path = (profile_path.parent / local_script).resolve()
    allowed_roots = [
        profile_path.parent.resolve(),
        profile_path.parent.parent.resolve(),
    ]
    for allowed_root in allowed_roots:
        try:
            script_path.relative_to(allowed_root)
            return script_path
        except ValueError:
            continue
    raise ValueError("Script path is outside the allowed roots.")


def _build_actual_config(
    profile: dict[str, Any],
    command_results: list[dict[str, Any]],
    *,
    host: str | None = None,
) -> dict[str, Any]:
    actual: dict[str, Any] = {
        "source_sheet": f"SSH collection: {profile.get('profile_name', profile['case_id'])}",
        "firmware_versions": {},
        "lan_mac_addresses": [],
        "collection_method": "restricted_ssh",
        "nic_inventory": [],
    }
    if profile.get("probe_plan"):
        actual["probe_plan"] = profile["probe_plan"]
    notes: list[str] = []

    for result in command_results:
        collect_as = result.get("collect_as") or {}
        stdout = result.get("stdout", "")
        if result.get("status") not in {"ok", "planned"}:
            continue
        kind = collect_as.get("kind")
        if not kind:
            continue

        if kind == "single_line":
            value = _first_non_empty_line(stdout)
            if value:
                actual[str(collect_as["target"])] = value
            continue

        if kind == "firmware_version":
            value = _first_non_empty_line(stdout)
            if value:
                actual["firmware_versions"][str(collect_as["component"])] = value
            continue

        if kind == "ipmitool_mc_info_version":
            match = re.search(r"Firmware Revision\s*:\s*(?P<value>.+)", stdout)
            if match:
                actual["firmware_versions"][str(collect_as["component"])] = match.group(
                    "value"
                ).strip()
            continue

        if kind == "ipmitool_lan_ip":
            match = re.search(r"^\s*IP Address\s*:\s*(?P<value>\S+)", stdout, flags=re.MULTILINE)
            if match:
                ip_value = match.group("value").strip()
                if ip_value and ip_value.lower() != "0.0.0.0":
                    actual[str(collect_as["target"])] = ip_value
            continue

        if kind == "ipmitool_hpm_versions":
            _collect_hpm_versions(actual, stdout)
            continue

        if kind == "first_non_loopback_ipv4":
            for match in IPV4_PATTERN.finditer(stdout):
                ip_value = match.group("ip")
                if not ip_value.startswith("127."):
                    actual[str(collect_as["target"])] = ip_value
                    break
            continue

        if kind == "note":
            value = _first_non_empty_line(stdout)
            if value:
                notes.append("{}: {}".format(result["id"], value))
            continue

        if kind == "bsp_image":
            value = _extract_bsp_image(stdout)
            if value:
                actual["firmware_versions"]["BSP"] = value
                actual["bsp_image"] = value
            continue

        if kind == "nic_inventory":
            nic_item = _parse_ethtool_inventory(stdout, str(collect_as.get("interface") or result["id"]))
            if nic_item:
                actual["nic_inventory"].append(nic_item)
            continue

        if kind == "json_payload":
            target = str(collect_as.get("target") or "").strip()
            payload_value = _parse_json_stdout(stdout)
            if target and payload_value:
                actual[target] = payload_value
            continue

        if kind == "tracking_probe_json":
            tracking_probe = _parse_json_stdout(stdout)
            if tracking_probe:
                actual["tracking_probe"] = tracking_probe
            continue

        if kind == "execution_evidence_json":
            execution_evidence = _parse_json_stdout(stdout)
            if execution_evidence:
                actual["execution_evidence"] = execution_evidence
            continue

    if notes:
        actual["collection_notes"] = notes
    if not actual["nic_inventory"]:
        actual.pop("nic_inventory", None)
    _apply_preferred_host_ipv4(actual, command_results, host)
    return actual


def _apply_preferred_host_ipv4(
    actual: dict[str, Any],
    command_results: list[dict[str, Any]],
    host: str | None,
) -> None:
    ip_candidates = _extract_host_ipv4_candidates(command_results)
    if not ip_candidates:
        return

    selected_ip, note = _select_preferred_host_ipv4(
        ip_candidates=ip_candidates,
        ssh_target_host=host,
        bmc_ip=actual.get("bmc_ip_address", ""),
        bmc_lan_stdout=_find_command_stdout(command_results, "bmc_lan"),
    )
    actual["host_ipv4_candidates"] = ip_candidates
    if selected_ip:
        actual["host_ipv4_address"] = selected_ip
    elif "host_ipv4_address" in actual:
        actual.pop("host_ipv4_address", None)
    if note:
        actual["host_ipv4_selection_note"] = note


def _first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _extract_bsp_image(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if "Advantech Linux Image:" in stripped:
            return stripped.split("Advantech Linux Image:", 1)[1].strip()
    return _first_non_empty_line(text)


def _parse_ethtool_inventory(text: str, interface: str) -> dict[str, str]:
    fields: dict[str, str] = {"interface": interface}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        normalized_key = key.lower().replace("-", "_")
        if normalized_key in {"driver", "version", "firmware_version", "bus_info"} and value:
            fields[normalized_key] = value

    if len(fields) == 1:
        return {}
    return fields


def _collect_hpm_versions(actual: dict[str, Any], text: str) -> None:
    for line in text.splitlines():
        match = re.match(
            r"^\|\*?\s*\d+\|\s*(?P<name>[^|]+?)\s*\|\s*(?P<active>[^|]+?)\|",
            line,
        )
        if not match:
            continue
        component = canonical_component_name(match.group("name"))
        active_version = match.group("active").strip().split()[0]
        if component and active_version and active_version != "---.--":
            actual["firmware_versions"][component] = active_version


def _parse_json_stdout(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_host_ipv4_candidates(command_results: list[dict[str, Any]]) -> list[str]:
    stdout = _find_command_stdout(command_results, "host_ipv4")
    if not stdout:
        return []

    candidates: list[str] = []
    for match in IPV4_PATTERN.finditer(stdout):
        ip_value = match.group("ip")
        if ip_value.startswith("127."):
            continue
        if ip_value not in candidates:
            candidates.append(ip_value)
    return candidates


def _find_command_stdout(command_results: list[dict[str, Any]], command_id: str) -> str:
    for result in command_results:
        if result.get("id") == command_id:
            return str(result.get("stdout") or "")
    return ""


def _select_preferred_host_ipv4(
    *,
    ip_candidates: list[str],
    ssh_target_host: str | None,
    bmc_ip: str,
    bmc_lan_stdout: str,
) -> tuple[str, str]:
    ssh_target_ip = _extract_ip_from_host_target(ssh_target_host or "")
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


def _write_collection_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
