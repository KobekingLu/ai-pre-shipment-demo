from __future__ import annotations

import json
from pathlib import Path

from pre_shipment.demo_case_parser import inspect_demo_cases
from pre_shipment.decision import analyze_workbook_report
from pre_shipment.dut_adapter import apply_dut_actuals_to_workbook_reports
from pre_shipment.html_report import generate_html_reports
from pre_shipment.parser import inspect_input_folder


def main() -> None:
    project_root = Path(__file__).resolve().parent
    input_dir = project_root / "input_data"
    demo_cases_dir = project_root / "demo_cases"
    output_dir = project_root / "output"
    dut_runs_dir = output_dir / "dut_runs"
    project_name = "AI Pre-Shipment Risk Decision Agent"
    output_dir.mkdir(parents=True, exist_ok=True)

    workbook_reports = inspect_input_folder(input_dir)
    workbook_reports = apply_dut_actuals_to_workbook_reports(workbook_reports, dut_runs_dir)
    demo_case_reports = inspect_demo_cases(demo_cases_dir) if demo_cases_dir.exists() else []
    raw_reports = workbook_reports + demo_case_reports
    analyzed_reports = [analyze_workbook_report(report) for report in raw_reports]

    inventory = [
        {
            "workbook_name": report["workbook_name"],
            "sheet_names": report["sheet_names"],
            "role_candidates": report["role_candidates"],
            "source_type": report.get("source_type", "real_workbook"),
            "source_label": report.get("source_label", "Real Workbook Data"),
        }
        for report in analyzed_reports
    ]

    workbook_inventory = [
        item for item in inventory if item["source_type"] == "real_workbook"
    ]
    demo_case_inventory = [
        item for item in inventory if item["source_type"] == "demo_case"
    ]

    summary = {
        "project_name": project_name,
        "input_folder": str(input_dir),
        "demo_cases_folder": str(demo_cases_dir),
        "inventory": inventory,
        "real_workbook_inventory": workbook_inventory,
        "demo_case_inventory": demo_case_inventory,
        "reports": analyzed_reports,
        "notes": [
            "Version 1 analyzes each workbook independently.",
            "The PM and AE workbooks currently appear to belong to different projects, so no cross-file merge is forced.",
            "The parser intentionally uses partial parsing and simple assumptions to stay easy to modify.",
            "Fake demo cases under demo_cases are normalized into the same analysis flow for presentation.",
        ],
    }

    _write_json(output_dir / "workbook_inventory.json", inventory)
    _write_json(output_dir / "demo_case_inventory.json", demo_case_inventory)
    _write_json(output_dir / "shipment_risk_summary.json", summary)

    for report in analyzed_reports:
        filename = f"{Path(report['workbook_name']).stem}_analysis.json"
        _write_json(output_dir / filename, report)

    html_outputs = generate_html_reports(analyzed_reports, output_dir, project_name)
    _print_summary(analyzed_reports, output_dir, html_outputs["overview"])


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _print_summary(reports: list[dict], output_dir: Path, overview_html: Path) -> None:
    print("=" * 72)
    print("AI Pre-Shipment Risk Decision Agent Demo")
    print("=" * 72)
    print()
    for report in reports:
        analysis = report.get("analysis", {})
        parsed = report.get("parsed", {})
        expected = parsed.get("expected_config", {})
        actual = parsed.get("actual_config", {})
        print("-" * 72)
        print(f"Workbook: {report['workbook_name']}")
        print(f"Source: {report.get('source_label', 'Real Workbook Data')}")
        print(f"Project: {expected.get('project_name') or actual.get('product_name') or 'N/A'}")
        print(f"Sheets: {', '.join(report['sheet_names'])}")
        print("Mapping:")
        print(f"  Expected: {report['role_candidates'].get('expected_configuration') or 'N/A'}")
        print(f"  Actual: {report['role_candidates'].get('actual_configuration') or 'N/A'}")
        print(f"  Known issues: {report['role_candidates'].get('known_issues') or 'N/A'}")
        print(f"Risk: {analysis.get('risk_level', 'N/A')}")
        print(f"Recommendation: {analysis.get('recommendation', 'N/A')}")
        print(f"Summary: {analysis.get('summary_text', 'N/A')}")
        print(f"Mismatch items: {len(analysis.get('mismatch_items', []))}")
        print(f"Matched known issues: {len(analysis.get('matched_known_issues', []))}")
        if analysis.get("decision_reasons"):
            print("Decision reasons:")
            for reason in analysis["decision_reasons"]:
                print(f"  - {reason}")
        print()

    print("-" * 72)
    print(f"JSON output: {output_dir}")
    print(f"HTML overview: {overview_html}")


if __name__ == "__main__":
    main()
