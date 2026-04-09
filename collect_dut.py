from __future__ import annotations

import argparse
import json
from pathlib import Path

from pre_shipment.dut_ssh import run_collection
from pre_shipment.probe_planner import (
    apply_probe_plan_to_profile,
    build_probe_plan,
    load_expected_report_from_workbook,
    write_planned_profile,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect DUT evidence through a restricted SSH command profile."
    )
    parser.add_argument("--profile", required=True, help="Path to allowed_commands.json")
    parser.add_argument("--host", required=True, help="SSH target, for example user@10.0.0.8")
    parser.add_argument(
        "--expected-workbook",
        help="Optional PM tracking workbook used to let the agent select additional repo-defined probes.",
    )
    parser.add_argument(
        "--output-dir",
        default="output/dut_runs",
        help="Local folder used to save collection outputs",
    )
    parser.add_argument("--identity-file", help="Optional SSH private key")
    parser.add_argument("--port", type=int, default=22, help="SSH port")
    parser.add_argument(
        "--connect-timeout",
        type=int,
        default=10,
        help="SSH connection timeout in seconds",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the profile and write a planned command manifest without connecting",
    )
    parser.add_argument(
        "--keep-remote-sandbox",
        action="store_true",
        help="Do not remove the remote /tmp sandbox after the run",
    )
    args = parser.parse_args()

    profile_path = Path(args.profile).resolve()
    output_dir = Path(args.output_dir).resolve()

    planned_profile_path = profile_path
    probe_plan: dict | None = None
    if args.expected_workbook:
        expected_report = load_expected_report_from_workbook(Path(args.expected_workbook).resolve())
        probe_plan = build_probe_plan(
            expected_report.get("parsed", {}).get("expected_config", {}),
            expected_report.get("parsed", {}).get("known_issues", []),
        )
        base_profile = json.loads(profile_path.read_text(encoding="utf-8"))
        planned_profile = apply_probe_plan_to_profile(base_profile, probe_plan)
        planned_profile_path = write_planned_profile(
            planned_profile,
            output_dir=profile_path.parent.parent / "_planned_profiles",
            workbook_path=Path(args.expected_workbook).resolve(),
        )

    payload = run_collection(
        profile_path=planned_profile_path,
        host=args.host,
        output_dir=output_dir,
        dry_run=args.dry_run,
        identity_file=Path(args.identity_file).resolve() if args.identity_file else None,
        port=args.port,
        connect_timeout=args.connect_timeout,
        keep_remote_sandbox=args.keep_remote_sandbox,
    )

    print("=" * 72)
    print("Restricted DUT SSH Collection")
    print("=" * 72)
    print(f"Case: {payload['case_id']}")
    print(f"Host: {payload['host']}")
    print(f"Run ID: {payload['run_id']}")
    print(f"Dry run: {payload['dry_run']}")
    print(f"Remote sandbox: {payload['remote_sandbox_dir']}")
    if probe_plan:
        print()
        print("Agent probe plan:")
        print(f"  Planned profile: {planned_profile_path}")
        for probe_id in probe_plan.get("selected_probe_ids", []):
            print(f"  - {probe_id}")
        for reason in probe_plan.get("rationale", []):
            print(f"    reason: {reason}")
    print()
    print("Parsed actual config:")
    actual = payload.get("parsed_actual_config", {})
    print(f"  Product name: {actual.get('product_name', 'N/A')}")
    print(f"  Product part number: {actual.get('product_part_number', 'N/A')}")
    print(f"  Board part number: {actual.get('board_part_number', 'N/A')}")
    print(f"  Product version: {actual.get('product_version', 'N/A')}")
    print(f"  BMC IP address: {actual.get('bmc_ip_address', 'N/A')}")
    print(f"  Firmware items: {len(actual.get('firmware_versions', {}))}")
    print()
    print("Commands:")
    for command in payload.get("commands", []):
        print(f"  - {command['id']}: {command['planned_remote_command']}")
        print(f"    status={command['status']} exit_code={command['exit_code']}")


if __name__ == "__main__":
    main()
