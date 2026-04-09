from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Artifact:
    path: Path
    category: str


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize execution evidence from an existing DUT log folder."
    )
    parser.add_argument("--root", default="/root/Test_LOG", help="Execution log root folder")
    parser.add_argument(
        "--max-artifacts",
        type=int,
        default=12,
        help="Maximum artifact entries to emit",
    )
    args = parser.parse_args()

    root = Path(args.root)
    payload = collect_execution_evidence(root, max_artifacts=args.max_artifacts)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def collect_execution_evidence(root: Path, *, max_artifacts: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_dir": str(root),
        "available": root.exists(),
        "available_scripts": [],
        "artifacts": [],
        "summary": [],
    }
    if not root.exists():
        payload["summary"].append(f"Execution evidence directory not found: {root}")
        return payload

    files = sorted(
        [path for path in root.rglob("*") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    shell_scripts = [path for path in files if path.suffix.lower() == ".sh"]
    payload["available_scripts"] = [
        {
            "name": path.name,
            "path": str(path),
            "size_bytes": path.stat().st_size,
        }
        for path in shell_scripts[: max_artifacts // 2 or 1]
    ]

    categorized = _categorize_artifacts(files)
    payload["artifacts"] = [
        {
            "name": artifact.path.name,
            "path": str(artifact.path),
            "category": artifact.category,
            "size_bytes": artifact.path.stat().st_size,
        }
        for artifact in categorized[:max_artifacts]
    ]

    post_install = _parse_post_install(_latest_by_category(categorized, "post_install_log"))
    if post_install:
        payload["post_install"] = post_install
        boot_result = post_install.get("boot_result", "unknown")
        failed_units = post_install.get("failed_units", [])
        payload["summary"].append(
            "Post-install check: boot_result={} failed_units={}.".format(
                boot_result,
                len(failed_units),
            )
        )

    storage = _parse_storage_report(_latest_by_category(categorized, "storage_report"))
    if storage:
        payload["storage_test"] = storage
        payload["summary"].append(
            "Storage test report found with {} result row(s).".format(
                storage.get("result_count", 0)
            )
        )

    gpu = _parse_gpu_info(_latest_by_category(categorized, "gpu_info"))
    if gpu:
        payload["gpu_info"] = gpu
        payload["summary"].append(
            "GPU report found with {} detected GPU(s): {}.".format(
                gpu.get("gpu_count", 0),
                ", ".join(gpu.get("gpu_models", [])) or "unknown",
            )
        )

    senv = _parse_senv_html(_latest_by_category(categorized, "senv_html"))
    if senv:
        payload["senv"] = senv
        payload["summary"].append("sENV HTML report found: {}.".format(senv["name"]))

    if not payload["summary"]:
        payload["summary"].append("Execution artifacts were found, but no known summary patterns matched.")

    return payload


def _categorize_artifacts(files: list[Path]) -> list[Artifact]:
    artifacts: list[Artifact] = []
    for path in files:
        name = path.name.lower()
        category = "generic"
        if "post_install_report" in name and name.endswith(".log"):
            category = "post_install_log"
        elif "storage_test_report" in name and name.endswith(".html"):
            category = "storage_report"
        elif "gpu_card_info" in name and name.endswith(".txt"):
            category = "gpu_info"
        elif "senv" in name and name.endswith(".html"):
            category = "senv_html"
        elif path.suffix.lower() == ".sh":
            category = "script"
        artifacts.append(Artifact(path=path, category=category))
    return artifacts


def _latest_by_category(artifacts: list[Artifact], category: str) -> Path | None:
    for artifact in artifacts:
        if artifact.category == category:
            return artifact.path
    return None


def _parse_post_install(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    system_state = _search_value(text, r"systemctl is-system-running\s*:\s*(?P<value>\S+)")
    boot_result = _search_value(text, r"BOOT RESULT\s*:\s*(?P<value>\S+)")
    failed_units = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("● "):
            failed_units.append(stripped[2:])
    return {
        "path": str(path),
        "boot_result": boot_result or "",
        "system_state": system_state or "",
        "failed_units": failed_units,
    }


def _parse_storage_report(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    rows = re.findall(r"<tr><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td></tr>", text, flags=re.IGNORECASE | re.DOTALL)
    return {
        "path": str(path),
        "result_count": len(rows),
        "sample_rows": [
            {
                "device": _strip_html(device),
                "test_type": _strip_html(test_type),
                "status": _strip_html(status),
                "fail_reason": _strip_html(fail_reason),
                "timestamp": _strip_html(timestamp),
            }
            for device, test_type, status, fail_reason, timestamp in rows[:5]
        ],
    }


def _parse_gpu_info(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    gpu_lines = []
    seen_bdfs: set[str] = set()
    for line in text.splitlines():
        if "NVIDIA Corporation" not in line or "[10de:" not in line:
            continue
        match = re.match(r"^(?P<bdf>[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9])\s+", line.strip())
        if not match:
            continue
        bdf = match.group("bdf")
        if bdf in seen_bdfs:
            continue
        seen_bdfs.add(bdf)
        gpu_lines.append(line.strip())
    gpu_models: list[str] = []
    for line in gpu_lines:
        match = re.search(r"NVIDIA Corporation\s+(.+?)\s+\[10de:", line)
        if match:
            model = match.group(1).strip()
            if model not in gpu_models:
                gpu_models.append(model)
    return {
        "path": str(path),
        "gpu_count": len(gpu_lines),
        "gpu_models": gpu_models,
    }


def _parse_senv_html(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return {
        "path": str(path),
        "name": path.name,
    }


def _search_value(text: str, pattern: str) -> str:
    match = re.search(pattern, text, flags=re.MULTILINE)
    return match.group("value").strip() if match else ""


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value).strip()


if __name__ == "__main__":
    main()
