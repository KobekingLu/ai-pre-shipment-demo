"""Human-readable bilingual HTML reports for demo use."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any


FIXED_SUMMARY_TRANSLATIONS = {
    "Agent found aligned evidence with no open blocking issue and recommended shipment can proceed.": "Agent 找到一致的證據，且沒有開啟中的阻擋性議題，因此建議可以放行出貨。",
    "Agent found missing evidence and recommends follow-up review before shipment.": "Agent 發現關鍵證據不足，因此建議在出貨前先做後續人工確認。",
    "Agent found blocking mismatches together with open major issues, so shipment should stop.": "Agent 發現阻擋性不一致與開啟中的重大議題同時存在，因此建議停止出貨。",
    "Agent found an open major issue that blocks shipment.": "Agent 發現一項會阻擋出貨的重大已知議題。",
    "Agent found blocking evidence and recommended stopping shipment.": "Agent 發現足以阻擋出貨的證據，因此建議停止出貨。",
    "Agent could not make a shipment decision because actual DUT evidence is missing.": "Agent 目前無法做出出貨判斷，因為缺少 actual DUT 證據。",
    "Agent found expected-vs-actual mismatches together with evidence gaps, so follow-up review is required before shipment.": "Agent 發現 expected 與 actual 不一致，且同時存在證據缺口，因此出貨前需要進一步複核。",
    "Agent found non-blocking mismatches that require review before shipment.": "Agent 發現非阻擋性的差異，但仍需要在出貨前進一步審查。",
    "Agent found open minor issues that require controlled follow-up before shipment.": "Agent 發現開啟中的次要議題，因此建議在受控條件下完成後續追蹤後再出貨。",
    "Agent found significant hardware BOM divergence from the PM tracking sheet, so shipment should stop.": "Agent 發現 DUT 與 PM tracking sheet 之間有明顯的硬體 BOM 偏差，因此建議停止出貨。",
}


def generate_html_reports(
    reports: list[dict[str, Any]],
    output_dir: Path,
    project_name: str,
) -> dict[str, Path]:
    report_dir = output_dir / "html"
    report_dir.mkdir(parents=True, exist_ok=True)

    detail_paths: dict[str, Path] = {}
    for report in reports:
        filename = f"{_slugify(Path(report['workbook_name']).stem)}.html"
        target_path = report_dir / filename
        target_path.write_text(_build_detail_html(report, project_name), encoding="utf-8")
        detail_paths[report["workbook_name"]] = target_path

    overview_path = report_dir / "index.html"
    overview_path.write_text(
        _build_overview_html(reports, project_name, detail_paths),
        encoding="utf-8",
    )

    return {"overview": overview_path, **{name: path for name, path in detail_paths.items()}}


def _build_overview_html(
    reports: list[dict[str, Any]],
    project_name: str,
    detail_paths: dict[str, Path],
) -> str:
    real_reports = [r for r in reports if r.get("source_type") == "real_workbook"]
    demo_reports = [r for r in reports if r.get("source_type") == "demo_case"]

    body = """
    <section class="hero">
      <div class="eyebrow">AI Agent Workflow Demo / AI Agent 工作流程示意</div>
      <h1>{project_name}</h1>
      <p class="hero-summary">AI Pre-Shipment Risk Decision Agent for ES / Sample shipment and test-entry review.</p>
      <p class="zh-note">這是一個用於 ES / Sample 出貨前與進測前風險判斷的 AI Agent demo。</p>
      <p>The agent inspects available data sources, selects usable evidence, compares expected and actual data, detects missing evidence, reviews known issues, and recommends next shipment actions.</p>
      <p class="zh-note">Agent 會先盤點可用資料來源，選出可用證據，比對 expected 與 actual，檢查證據缺口與已知議題，最後提出下一步出貨建議。</p>
      {competition_snapshot}
    </section>
    <section class="panel narrative">
      <h2>Demo Narrative / Demo 說明</h2>
      <p>This demo shows a practical AI-agent review loop: PM tracking sheet as expected input, DUT-collected facts as actual input, known issues as risk context, and an explainable shipment recommendation as output.</p>
      <p class="zh-note">這個 demo 展示的是一個可說明的 AI Agent review flow：以 PM tracking sheet 作為 expected input，以 DUT 實際蒐集結果作為 actual input，以 known issues 作為風險背景，最後輸出可解釋的 shipment recommendation。</p>
    </section>
    <section class="panel">
      <h2>Business Pain Points / 業務痛點</h2>
      {pain_points}
    </section>
    <section class="panel">
      <h2>Why This Is an AI Agent / 為何這是 AI Agent</h2>
      {agent_capabilities}
    </section>
    <section class="panel">
      <h2>Cross-Function Value / 跨部門價值</h2>
      {cross_function_value}
    </section>
    <section class="panel">
      <h2>Safety Boundary / 安全邊界</h2>
      {safety_boundary}
    </section>
    <section class="panel">
      <h2>Agent Workflow / Agent 工作流程</h2>
      {workflow}
    </section>
    <section class="panel">
      <h2>Real Workbook Reviews / 真實資料案例</h2>
      {real_table}
    </section>
    <section class="panel">
      <h2>Demo Scenario Cases / 模擬案例</h2>
      <p class="section-note">These fake cases keep the three target outcomes visible in one demo flow: Go, Conditional Go, and No-Go.</p>
      <p class="zh-note">這些模擬案例用來穩定展示三種目標結果：Go、Conditional Go、No-Go。</p>
      {demo_table}
    </section>
    """.format(
        project_name=html.escape(project_name),
        competition_snapshot=_overview_competition_snapshot(reports),
        pain_points=_overview_business_pain_points(),
        agent_capabilities=_overview_agent_capabilities(),
        cross_function_value=_overview_cross_function_value(),
        safety_boundary=_overview_safety_boundary(),
        workflow=_workflow_steps(),
        real_table=_overview_table(real_reports, detail_paths, "No real workbook reports found."),
        demo_table=_overview_table(demo_reports, detail_paths, "No fake demo cases found."),
    )
    return _wrap_html("AI Agent Workflow Demo / AI Agent 工作流程示意", body)


def _build_detail_html(report: dict[str, Any], project_name: str) -> str:
    analysis = report.get("analysis", {}) or {}
    mapping = report.get("role_candidates", {}) or {}

    body = """
    <nav class="back-link"><a href="index.html">Back to agent overview / 返回 Agent 總覽</a></nav>
    <section class="hero">
      <div class="eyebrow">Agent Decision Detail / Agent 決策細節</div>
      <h1>{workbook_name}</h1>
      <p>{project_name}</p>
      <div class="hero-metrics">
        <div class="metric">
          <span class="label">Data Source / 資料類型</span>
          <span class="badge">{source_label}</span>
        </div>
        <div class="metric">
          <span class="label">Risk Level / 風險等級</span>
          <span class="pill {risk_class}">{risk}</span>
        </div>
        <div class="metric">
          <span class="label">Recommendation / 建議結論</span>
          <span class="pill {rec_class}">{recommendation}</span>
        </div>
      </div>
      <p class="hero-summary">{summary_text}</p>
      <p class="zh-note hero-zh-summary">{summary_zh}</p>
    </section>
    <section class="panel">
      <h2>Agent Decision Snapshot / Agent 決策快照</h2>
      {decision_snapshot}
    </section>
    <section class="panel">
      <h2>Agent Actions Taken / Agent 執行步驟</h2>
      {actions_taken}
    </section>
    <section class="panel">
      <h2>Data Completeness Check / 資料完整度檢查</h2>
      {completeness_check}
    </section>
    <section class="panel">
      <h2>Why This Is an Agent Decision / 為什麼這是 Agent 決策</h2>
      {agent_reasoning}
    </section>
    <section class="panel">
      <h2>Evidence Summary / 證據摘要</h2>
      {evidence_summary}
    </section>
    <section class="panel">
      <h2>Agent-Executed Probes / Agent 執行探測</h2>
      {execution_evidence}
    </section>
    <section class="panel">
      <h2>Risk Breakdown / 風險拆解</h2>
      {risk_breakdown}
    </section>
    <section class="panel">
      <h2>Problem Details / 問題細節</h2>
      {problem_details}
    </section>
    <section class="panel split-panel">
      <div>
        <h2>Recommended Owner / 建議處理單位</h2>
        <p class="key-callout">{recommended_owner}</p>
      </div>
      <div>
        <h2>Suggested Next Step / 建議下一步</h2>
        <p class="key-callout">{suggested_next_step}</p>
      </div>
    </section>
    <section class="panel">
      <h2>Sheet Mapping / 資料來源映射</h2>
      {mapping_table}
    </section>
    <section class="panel">
      <h2>Mismatch Items / 不一致項目</h2>
      {mismatch_table}
    </section>
    <section class="panel">
      <h2>Matched Known Issues / 命中的已知議題</h2>
      {issues_table}
    </section>
    <section class="panel">
      <h2>Decision Reasons / 決策原因</h2>
      {reasons_list}
    </section>
    <section class="panel">
      <h2>Action Items / 後續處置</h2>
      {actions_list}
    </section>
    """.format(
        workbook_name=html.escape(report["workbook_name"]),
        project_name=html.escape(project_name),
        source_label=html.escape(_bilingual_source_label(report.get("source_label", "Unknown Source"))),
        risk=html.escape(_bilingual_risk(analysis.get("risk_level", "N/A"))),
        recommendation=html.escape(_bilingual_recommendation(analysis.get("recommendation", "N/A"))),
        summary_text=html.escape(analysis.get("summary_text", "")),
        summary_zh=html.escape(_summary_translation(analysis.get("summary_text", ""))),
        risk_class=_risk_class(analysis.get("risk_level", "")),
        rec_class=_recommendation_class(analysis.get("recommendation", "")),
        decision_snapshot=_decision_snapshot(report),
        actions_taken=_agent_actions_taken(report),
        completeness_check=_completeness_check(report),
        agent_reasoning=_agent_decision_explainer(report),
        evidence_summary=_bullet_list(analysis.get("evidence_summary", []), "Agent did not record an evidence summary."),
        execution_evidence=_execution_evidence(report),
        risk_breakdown=_risk_breakdown_cards(analysis.get("risk_breakdown", [])),
        problem_details=_bullet_list(analysis.get("problem_details", []), "Agent did not record problem details."),
        recommended_owner=html.escape(analysis.get("recommended_owner", "N/A")),
        suggested_next_step=html.escape(analysis.get("suggested_next_step", "N/A")),
        mapping_table=_mapping_table(mapping),
        mismatch_table=_mismatch_table(analysis.get("mismatch_items", [])),
        issues_table=_issues_table(analysis.get("matched_known_issues", [])),
        reasons_list=_bullet_list(analysis.get("decision_reasons", []), "The agent did not record decision reasons."),
        actions_list=_bullet_list(analysis.get("action_items", []), "The agent did not record additional action items."),
    )
    return _wrap_html(f"Agent Decision Detail / Agent 決策細節 - {report['workbook_name']}", body)


def _overview_table(reports: list[dict[str, Any]], detail_paths: dict[str, Path], empty_text: str) -> str:
    rows = []
    for report in reports:
        analysis = report.get("analysis", {}) or {}
        detail_name = detail_paths[report["workbook_name"]].name
        rows.append(
            """
            <tr>
              <td><a href="{detail_name}">{name}</a></td>
              <td><span class="badge">{source_label}</span></td>
              <td>{expected}</td>
              <td>{actual}</td>
              <td>{issues}</td>
              <td><span class="pill {risk_class}">{risk}</span></td>
              <td><span class="pill {rec_class}">{recommendation}</span></td>
              <td>{summary}</td>
              <td>{completeness}</td>
            </tr>
            """.format(
                detail_name=html.escape(detail_name),
                name=html.escape(report["workbook_name"]),
                source_label=html.escape(_bilingual_source_label(report.get("source_label", "Unknown Source"))),
                expected=_safe_text(report.get("role_candidates", {}).get("expected_configuration")),
                actual=_safe_text(report.get("role_candidates", {}).get("actual_configuration")),
                issues=_safe_text(report.get("role_candidates", {}).get("known_issues")),
                risk=html.escape(_bilingual_risk(analysis.get("risk_level", "N/A"))),
                recommendation=html.escape(_bilingual_recommendation(analysis.get("recommendation", "N/A"))),
                summary=_bilingual_summary_html(analysis.get("summary_text", "N/A")),
                completeness=html.escape(_bilingual_completeness(_data_completeness_summary(report))),
                risk_class=_risk_class(analysis.get("risk_level", "")),
                rec_class=_recommendation_class(analysis.get("recommendation", "")),
            )
        )

    return """
    <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Case / 案例</th>
          <th>Data Type / 資料類型</th>
          <th>Expected Source / Expected 來源</th>
          <th>Actual Source / Actual 來源</th>
          <th>Known Issue Source / 已知議題來源</th>
          <th>Risk Level / 風險等級</th>
          <th>Recommendation / 建議結論</th>
          <th>Why / 判斷摘要</th>
          <th>Completeness / 完整度</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
    </div>
    """.format(rows="".join(rows) or _empty_table_row(9, empty_text))


def _workflow_steps() -> str:
    steps = [
        ("1. Inspect Inputs / 盤點輸入資料", "The agent scans workbook files and demo cases to identify which data sources are available for this review."),
        ("2. Select Roles / 指派資料角色", "The agent decides which source should be treated as expected configuration, actual DUT evidence, and known issue context."),
        ("3. Extract Expected Data / 解析 Expected", "The agent reads project, BOM, and firmware targets from the selected PM or tracking-sheet source."),
        ("4. Collect Actual Evidence / 蒐集 Actual 證據", "The agent reads DUT facts and may run repo-defined probe scripts to collect additional evidence needed for comparison."),
        ("5. Check Known Issues / 對照已知議題", "The agent matches open issues against components or firmware areas when supporting evidence exists."),
        ("6. Evaluate Risk / 評估出貨風險", "The agent applies the current rule-based logic to mismatches, issue exposure, evidence gaps, and probe signals."),
        ("7. Recommend Next Action / 建議下一步", "The agent recommends Go, Conditional Go, or No-Go and points to the owner who should follow up next."),
    ]
    cards = []
    for title, text in steps:
        cards.append("""
            <div class="step-card">
              <h3>{title}</h3>
              <p>{text}</p>
            </div>
            """.format(title=html.escape(title), text=html.escape(text)))
    return '<div class="step-grid">{}</div>'.format("".join(cards))


def _overview_business_pain_points() -> str:
    items = [
        "Data is fragmented across PM tracking sheets, DUT OS/BMC facts, firmware evidence, and known issue records.",
        "Manual expected-vs-actual comparison is time-consuming and hard to keep consistent under schedule pressure.",
        "Teams may have evidence, but still lack a fast, explainable answer to whether a sample should ship or enter test.",
    ]
    cards = []
    for item in items:
        cards.append(
            """
            <div class="step-card">
              <h3>Pain Point</h3>
              <p>{text}</p>
            </div>
            """.format(text=html.escape(item))
        )
    return '<div class="step-grid">{}</div><p class="zh-note">這個 Agent 的目標，是把原本分散且仰賴人工的檢核流程，收斂成可重複、可追溯、可解釋的 review workflow。</p>'.format(
        "".join(cards)
    )


def _overview_competition_snapshot(reports: list[dict[str, Any]]) -> str:
    total_cases = len(reports)
    real_cases = sum(1 for report in reports if report.get("source_type") == "real_workbook")
    dut_cases = sum(
        1
        for report in reports
        if "DUT collection" in str(report.get("role_candidates", {}).get("actual_configuration") or "")
    )
    nogo_cases = sum(
        1
        for report in reports
        if str(report.get("analysis", {}).get("recommendation", "")).lower() == "no-go"
    )
    cards = [
        ("Use Case", "Pre-shipment and pre-test risk review across ES / sample systems."),
        ("Live DUT Cases", f"{dut_cases} DUT-connected review case(s) are currently demonstrated."),
        ("Decision Output", f"{total_cases} total case(s), including {real_cases} real workbook review case(s) and {nogo_cases} No-Go outcome(s)."),
    ]
    rendered = []
    for title, text in cards:
        rendered.append(
            """
            <div class="metric">
              <span class="label">{title}</span>
              <span>{text}</span>
            </div>
            """.format(title=html.escape(title), text=html.escape(text))
        )
    return '<div class="hero-metrics">{}</div>'.format("".join(rendered))


def _overview_agent_capabilities() -> str:
    cards = [
        (
            "Autonomous Decision-Making",
            "The agent selects usable evidence, compares expected and actual values, classifies risk signals, and recommends Go, Conditional Go, or No-Go.",
        ),
        (
            "Environment Interaction",
            "The agent connects to the DUT, reads system facts, and executes repo-defined probe scripts to collect additional evidence from the environment.",
        ),
        (
            "Workflow Execution",
            "The agent does not stop at a single check. It performs a full loop of inspect, compare, scan, judge, and summarize next actions.",
        ),
    ]
    rendered = []
    for title, text in cards:
        rendered.append(
            """
            <div class="step-card">
              <h3>{title}</h3>
              <p>{text}</p>
            </div>
            """.format(title=html.escape(title), text=html.escape(text))
        )
    return '<div class="step-grid">{}</div><p class="zh-note">也就是說，這不只是靜態報表或腳本集合，而是會主動選證據、主動互動、主動輸出建議的 Agent workflow。</p>'.format(
        "".join(rendered)
    )


def _overview_cross_function_value() -> str:
    roles = [
        ("AE", "Starts the review, connects the DUT, and gets an early signal on whether the machine is safe to ship or enter test."),
        ("PM", "Checks whether the real hardware and firmware still align with the original tracking-sheet expectation."),
        ("RD", "Quickly sees whether current versions and components overlap with known issues or risk areas."),
        ("DQA", "Gets clearer visibility before test entry, reducing time spent on wrong builds or unstable baselines."),
    ]
    rendered = []
    for role, text in roles:
        rendered.append(
            """
            <div class="step-card">
              <h3>{role}</h3>
              <p>{text}</p>
            </div>
            """.format(role=html.escape(role), text=html.escape(text))
        )
    return '<div class="step-grid">{}</div><p class="zh-note">這個 demo 的價值不只在自動化比對，而是在 AE、PM、RD、DQA 之間建立一個共享且可追溯的決策摘要。</p>'.format(
        "".join(rendered)
    )


def _overview_safety_boundary() -> str:
    items = [
        "The current demo uses read-focused collection and repo-defined probe scripts instead of arbitrary remote commands.",
        "The agent does not need to change system settings, install packages, or reboot the DUT to produce a useful review.",
        "This keeps the demo explainable and safer while still showing environment interaction and autonomous evidence gathering.",
    ]
    return _bullet_list(items, "")


def _decision_snapshot(report: dict[str, Any]) -> str:
    analysis = report.get("analysis", {}) or {}
    mismatches = analysis.get("mismatch_items", []) or []
    issue_count = len(analysis.get("matched_known_issues", []) or [])
    category_counts = analysis.get("mismatch_category_counts", {}) or {}
    actual_source = report.get("role_candidates", {}).get("actual_configuration") or "N/A"
    snapshot_items = [
        "Recommendation: {}.".format(analysis.get("recommendation", "N/A")),
        "Risk level: {}.".format(analysis.get("risk_level", "N/A")),
        "Mismatch count: {} total, with firmware={}, hardware={}, other={}.".format(
            len(mismatches),
            category_counts.get("firmware", 0),
            category_counts.get("hardware", 0),
            category_counts.get("other", 0),
        ),
        "Matched known issues: {}.".format(issue_count),
        "Actual evidence source: {}.".format(actual_source),
        "Next action owner: {}.".format(analysis.get("recommended_owner", "N/A")),
    ]
    return _bullet_list(snapshot_items, "Agent snapshot was not recorded.")


def _agent_actions_taken(report: dict[str, Any]) -> str:
    analysis = report.get("analysis", {}) or {}
    probe_plan = analysis.get("probe_plan", {}) or {}
    actions = [
        "Agent inspected '{}' and found {} source item(s).".format(report.get("workbook_name", "N/A"), len(report.get("sheet_names", []))),
        _selection_action("expected configuration source", report.get("role_candidates", {}).get("expected_configuration")),
        _selection_action("actual system / firmware source", report.get("role_candidates", {}).get("actual_configuration")),
        _selection_action("known issue source", report.get("role_candidates", {}).get("known_issues")),
        "Agent compared expected and actual evidence and found {} mismatch item(s).".format(len(analysis.get("mismatch_items", []))),
        "Agent evaluated {} matched open issue(s).".format(len(analysis.get("matched_known_issues", []))),
        "Agent planned {} repo-defined probe script(s): {}.".format(len(probe_plan.get("selected_probe_ids", [])), ", ".join(probe_plan.get("selected_probe_ids", [])) or "none"),
        "Agent produced recommendation '{}' with risk level '{}'.".format(analysis.get("recommendation", "N/A"), analysis.get("risk_level", "N/A")),
    ]
    return _bullet_list(actions, "Agent actions were not recorded.")


def _completeness_check(report: dict[str, Any]) -> str:
    cards = []
    for item in _data_completeness_items(report):
        cards.append("""
            <div class="status-card {css_class}">
              <div class="status-title">{title}</div>
              <p>{message}</p>
            </div>
            """.format(css_class=html.escape(item["css_class"]), title=html.escape(item["title"]), message=html.escape(item["message"])))
    return '<div class="status-grid">{}</div>'.format("".join(cards))


def _agent_decision_explainer(report: dict[str, Any]) -> str:
    analysis = report.get("analysis", {}) or {}
    reasons = [
        "The agent selected available data sources instead of assuming every evidence set already existed.",
        "The agent used the current rule-based evaluation to compare configuration values and review known issues.",
    ]
    if analysis.get("data_gaps"):
        reasons.append("The agent found data gaps and reduced confidence instead of pretending the missing evidence was known.")
    if analysis.get("mismatch_items"):
        reasons.append("The agent detected mismatches and carried them into shipment risk evaluation.")
    if analysis.get("matched_known_issues"):
        reasons.append("The agent checked matched known issues before recommending the shipment outcome.")
    reasons.append("The agent recommended the next workflow action and highlighted which team should handle follow-up.")
    return _bullet_list(reasons, "Agent decision explanation was not recorded.")


def _execution_evidence(report: dict[str, Any]) -> str:
    actual = report.get("parsed", {}).get("actual_config", {}) or {}
    analysis = report.get("analysis", {}) or {}
    parts: list[str] = []
    probe_plan = analysis.get("probe_plan") or actual.get("probe_plan") or {}
    if probe_plan.get("selected_probe_ids"):
        lines = [
            "Agent selected probe scripts: {}.".format(", ".join(probe_plan.get("selected_probe_ids", []))),
            *[f"Planner rationale: {reason}" for reason in probe_plan.get("rationale", [])],
        ]
        parts.append(_bullet_list(lines, ""))

    tracking_probe = actual.get("tracking_probe") or {}
    if tracking_probe:
        parts.append(_tracking_probe_summary(tracking_probe))
    pcie_probe = actual.get("pcie_probe") or {}
    if pcie_probe:
        parts.append(_generic_probe_summary("PCIe Device Probe / PCIe 裝置探測", pcie_probe))
    operational_probe = actual.get("operational_probe") or {}
    if operational_probe:
        parts.append(_generic_probe_summary("Operational Attention Probe / 操作風險探測", operational_probe))

    return "".join(parts) or _empty_state("Agent did not execute additional probe scripts for this review.")


def _tracking_probe_summary(probe: dict[str, Any]) -> str:
    parts: list[str] = []
    summary = probe.get("summary") or []
    if summary:
        parts.append(_bullet_list(summary, ""))

    rows = []
    cpu = probe.get("cpu") or {}
    memory = probe.get("memory") or {}
    storage = probe.get("storage") or {}
    gpu = probe.get("gpu") or {}
    probe_rows = [
        ("CPU / 處理器", _format_probe_value(cpu.get("model_name")), _format_probe_value(cpu.get("sockets"), suffix=" sockets")),
        ("Memory / 記憶體", _format_probe_value(memory.get("total_gib"), suffix=" GiB"), _format_probe_value(memory.get("populated_dimms"), suffix=" DIMMs")),
        ("Storage / 儲存", _format_probe_value(storage.get("device_count"), suffix=" disks"), _format_probe_models(storage.get("devices") or [], value_key="model")),
        ("GPU / 顯示卡", _format_probe_value(gpu.get("gpu_count"), suffix=" GPUs"), _format_probe_models(gpu.get("models") or [])),
    ]
    for category, primary, notes in probe_rows:
        if primary == "N/A" and notes == "N/A":
            continue
        rows.append("""
            <tr>
              <td>{category}</td>
              <td>{primary}</td>
              <td>{notes}</td>
            </tr>
            """.format(category=html.escape(category), primary=html.escape(primary), notes=html.escape(notes)))

    if rows:
        parts.append("""
            <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Probe Area / 探測範圍</th>
                  <th>Primary Result / 主要結果</th>
                  <th>Notes / 備註</th>
                </tr>
              </thead>
              <tbody>{rows}</tbody>
            </table>
            </div>
            """.format(rows="".join(rows)))

    commands = probe.get("commands_ran") or []
    if commands:
        parts.append("<p><strong>Commands / 指令:</strong> {}</p>".format(html.escape(", ".join(str(c) for c in commands))))

    return "".join(parts) or _empty_state("Agent executed probe scripts, but the returned payload did not contain displayable results.")


def _generic_probe_summary(title: str, probe: dict[str, Any]) -> str:
    parts: list[str] = [f"<p><strong>{html.escape(title)}</strong></p>"]
    summary = probe.get("summary") or []
    if summary:
        parts.append(_bullet_list([str(item) for item in summary], ""))
    attention_items = probe.get("attention_items") or []
    if attention_items:
        parts.append(_bullet_list([f"Attention: {item}" for item in attention_items], ""))
    commands = probe.get("commands_ran") or []
    if commands:
        parts.append("<p><strong>Commands / 指令:</strong> {}</p>".format(html.escape(", ".join(str(c) for c in commands))))
    return "".join(parts)


def _risk_breakdown_cards(items: list[dict[str, str]]) -> str:
    if not items:
        return _empty_state("Agent did not record a risk breakdown.")
    cards = []
    for item in items:
        cards.append("""
            <div class="status-card {level}">
              <div class="status-title">{title}</div>
              <p>{detail}</p>
            </div>
            """.format(level=html.escape(_risk_class(item.get("level", ""))), title=html.escape(item.get("title", "Risk Item")), detail=html.escape(item.get("detail", ""))))
    return '<div class="status-grid">{}</div>'.format("".join(cards))


def _mapping_table(mapping: dict[str, Any]) -> str:
    labels = {
        "expected_configuration": "Expected Configuration / Expected 設定",
        "actual_configuration": "Actual System / Firmware / Actual 系統與韌體",
        "known_issues": "Known Issues / 已知議題",
    }
    rows = []
    for key, label in labels.items():
        rows.append("<tr><th>{label}</th><td>{value}</td></tr>".format(label=html.escape(label), value=_safe_text(mapping.get(key))))
    return '<div class="table-wrap"><table><tbody>{}</tbody></table></div>'.format("".join(rows))


def _mismatch_table(items: list[dict[str, Any]]) -> str:
    if not items:
        return _empty_state("Agent did not detect mismatch items.")
    rows = []
    for item in items:
        rows.append("""
            <tr>
              <td>{field}</td>
              <td>{component}</td>
              <td>{category}</td>
              <td>{expected}</td>
              <td>{actual}</td>
              <td>{severity}</td>
            </tr>
            """.format(
                field=_safe_text(item.get("field")),
                component=_safe_text(item.get("component")),
                category=_safe_text(item.get("category")),
                expected=_safe_text(item.get("expected")),
                actual=_safe_text(item.get("actual")),
                severity=_safe_text(item.get("severity")),
            ))
    return """
    <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Field / 欄位</th>
          <th>Component / 元件</th>
          <th>Category / 類別</th>
          <th>Expected / 預期值</th>
          <th>Actual / 實際值</th>
          <th>Severity / 嚴重度</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    </div>
    """.format(rows="".join(rows))


def _issues_table(items: list[dict[str, Any]]) -> str:
    if not items:
        return _empty_state("Agent did not match open known issues for this review.")
    rows = []
    for item in items:
        rows.append("""
            <tr>
              <td>{issue_id}</td>
              <td>{issue_type}</td>
              <td>{description}</td>
              <td>{status}</td>
              <td>{level}</td>
              <td>{resolution}</td>
            </tr>
            """.format(
                issue_id=_safe_text(item.get("item")),
                issue_type=_safe_text(item.get("type")),
                description=_safe_text(item.get("description")),
                status=_safe_text(item.get("status")),
                level=_safe_text(item.get("level")),
                resolution=_safe_text(item.get("resolution")),
            ))
    return """
    <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Item / 項次</th>
          <th>Type / 類型</th>
          <th>Description / 描述</th>
          <th>Status / 狀態</th>
          <th>Level / 等級</th>
          <th>Resolution / Workaround / 處置方式</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    </div>
    """.format(rows="".join(rows))


def _bullet_list(items: list[str], empty_text: str) -> str:
    if not items:
        return _empty_state(empty_text)
    rendered = "".join(f"<li>{html.escape(item)}</li>" for item in items if item)
    return f"<ul>{rendered}</ul>" if rendered else _empty_state(empty_text)


def _empty_table_row(colspan: int, text: str) -> str:
    return '<tr><td colspan="{}" class="empty">{}</td></tr>'.format(colspan, html.escape(text))


def _empty_state(text: str) -> str:
    return f'<p class="empty">{html.escape(text)}</p>'


def _safe_text(value: Any) -> str:
    if value in (None, ""):
        return '<span class="muted">N/A</span>'
    return html.escape(str(value))


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return slug or "report"


def _selection_action(label: str, selected_source: str | None) -> str:
    if selected_source:
        return "Agent selected '{}' as the {}.".format(selected_source, label)
    return "Agent did not find a usable {}.".format(label)


def _data_completeness_items(report: dict[str, Any]) -> list[dict[str, str]]:
    analysis = report.get("analysis", {}) or {}
    data_gaps = analysis.get("data_gaps", [])
    expected_ok = not any("Expected configuration evidence missing" in gap for gap in data_gaps)
    actual_ok = not any("Actual system / firmware evidence missing" in gap for gap in data_gaps)
    issues_ok = not any("Known issue evidence missing" in gap for gap in data_gaps)
    confidence_ok = not data_gaps
    return [
        {"title": "Expected configuration / Expected 設定", "message": "Expected configuration evidence was available." if expected_ok else "Expected configuration evidence was missing.", "css_class": "ok" if expected_ok else "warn"},
        {"title": "Actual system data / Actual 系統資料", "message": "Actual system / firmware evidence was available." if actual_ok else "Actual system / firmware evidence was missing.", "css_class": "ok" if actual_ok else "warn"},
        {"title": "Known issue evidence / 已知議題證據", "message": "Known issue evidence was available." if issues_ok else "Known issue evidence was missing.", "css_class": "ok" if issues_ok else "warn"},
        {"title": _bilingual_confidence_title("Normal confidence" if confidence_ok else "Reduced confidence"), "message": "Agent had the main evidence sources needed for the current review." if confidence_ok else "Agent found missing or incomplete evidence, so the final recommendation should be reviewed with caution.", "css_class": "ok" if confidence_ok else "warn"},
    ]


def _data_completeness_summary(report: dict[str, Any]) -> str:
    data_gaps = report.get("analysis", {}).get("data_gaps", [])
    if not data_gaps:
        return "Complete"
    if len(data_gaps) == 1:
        return "Partial"
    return "Limited"


def _bilingual_recommendation(value: str) -> str:
    return {"Go": "Go / 可放行", "Conditional Go": "Conditional Go / 條件式放行", "No-Go": "No-Go / 不建議放行"}.get(value, value)


def _bilingual_risk(value: str) -> str:
    return {"Low": "Low / 低", "Medium": "Medium / 中", "High": "High / 高"}.get(value, value)


def _bilingual_completeness(value: str) -> str:
    return {"Complete": "Complete / 完整", "Partial": "Partial / 部分完整", "Limited": "Limited / 受限"}.get(value, value)


def _bilingual_source_label(value: str) -> str:
    return {
        "Real Workbook Data": "Real Workbook Data / 真實 workbook 資料",
        "Fake Demo Data": "Fake Demo Data / 模擬 demo 資料",
        "Unknown Source": "Unknown Source / 未知來源",
    }.get(value, value)


def _bilingual_confidence_title(value: str) -> str:
    return {"Normal confidence": "Normal confidence / 正常信心", "Reduced confidence": "Reduced confidence / 降低信心"}.get(value, value)


def _summary_translation(text: str) -> str:
    return FIXED_SUMMARY_TRANSLATIONS.get(text, "")


def _bilingual_summary_html(text: str) -> str:
    english = html.escape(text)
    zh = html.escape(_summary_translation(text))
    return f'<div>{english}</div><div class="zh-inline">{zh}</div>' if zh else english


def _format_probe_value(value: Any, *, suffix: str = "") -> str:
    if value in (None, "", [], {}):
        return "N/A"
    return f"{value}{suffix}"


def _format_probe_models(values: list[Any], *, value_key: str | None = None) -> str:
    normalized: list[str] = []
    for item in values[:4]:
        candidate = str(item.get(value_key) if isinstance(item, dict) and value_key else item).strip()
        if candidate and candidate not in normalized:
            normalized.append(candidate)
    return ", ".join(normalized) if normalized else "N/A"


def _risk_class(value: str) -> str:
    lowered = value.lower()
    if lowered == "high":
        return "high"
    if lowered == "medium":
        return "medium"
    return "low"


def _recommendation_class(value: str) -> str:
    lowered = value.lower()
    if lowered == "no-go":
        return "high"
    if lowered == "conditional go":
        return "medium"
    return "low"


def _wrap_html(title: str, body: str) -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      --bg: #f4f6f8;
      --panel: #ffffff;
      --text: #1f2933;
      --muted: #6b7280;
      --line: #d7dde4;
      --low: #1f7a4c;
      --low-bg: #e7f5ec;
      --medium: #9a6700;
      --medium-bg: #fff3d6;
      --high: #b42318;
      --high-bg: #fde7e5;
      --link: #0f4c81;
      --accent: #174e70;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: linear-gradient(180deg, #eef3f7 0%, var(--bg) 100%); color: var(--text); font: 15px/1.55 "Segoe UI", "Microsoft JhengHei", Tahoma, sans-serif; }}
    .page {{ max-width: 1160px; margin: 0 auto; padding: 32px 20px 48px; }}
    .hero {{ background: linear-gradient(135deg, #ffffff 0%, #f6fbff 100%); border: 1px solid var(--line); border-radius: 14px; padding: 24px; margin-bottom: 20px; box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05); }}
    .eyebrow {{ margin-bottom: 8px; color: var(--accent); font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; }}
    .hero h1, .panel h2 {{ margin: 0 0 8px; }}
    .hero p {{ margin: 0; color: var(--muted); max-width: 920px; }}
    .hero-summary {{ margin-top: 16px !important; color: var(--text) !important; font-weight: 700; }}
    .hero-zh-summary, .zh-note, .zh-inline {{ color: var(--muted) !important; }}
    .zh-note {{ margin-top: 8px !important; }}
    .zh-inline {{ margin-top: 6px; }}
    .hero-metrics {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 16px; }}
    .metric {{ min-width: 180px; padding: 12px 14px; background: #f9fbfc; border: 1px solid var(--line); border-radius: 10px; }}
    .label {{ display: block; margin-bottom: 8px; font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }}
    .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 20px; margin-bottom: 20px; box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05); }}
    .split-panel {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 24px; }}
    .narrative {{ border-left: 5px solid var(--accent); }}
    .section-note {{ margin: 0 0 14px; color: var(--muted); }}
    .step-grid, .status-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .step-card, .status-card {{ padding: 14px; border: 1px solid var(--line); border-radius: 12px; background: #fbfdff; }}
    .step-card h3 {{ margin: 0 0 8px; font-size: 15px; }}
    .step-card p, .status-card p {{ margin: 0; color: var(--muted); }}
    .status-card.low, .status-card.ok {{ background: #f8fcf9; border-color: #cfe8d8; }}
    .status-card.medium, .status-card.warn {{ background: #fffaf0; border-color: #efd9a7; }}
    .status-card.high {{ background: #fff3f1; border-color: #f0b7b0; }}
    .status-title {{ margin-bottom: 8px; font-weight: 700; }}
    .key-callout {{ margin: 0; padding: 14px; border-radius: 12px; background: #f9fbfc; border: 1px solid var(--line); font-weight: 600; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 980px; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; overflow-wrap: anywhere; word-break: break-word; }}
    th {{ font-size: 13px; color: var(--muted); background: #f8fafb; }}
    .pill, .badge {{ display: inline-block; padding: 4px 10px; border-radius: 999px; font-weight: 600; font-size: 13px; }}
    .badge {{ color: var(--accent); background: #eaf4fb; }}
    .pill.low {{ color: var(--low); background: var(--low-bg); }}
    .pill.medium {{ color: var(--medium); background: var(--medium-bg); }}
    .pill.high {{ color: var(--high); background: var(--high-bg); }}
    .muted, .empty {{ color: var(--muted); }}
    ul {{ margin: 0; padding-left: 20px; }}
    li + li {{ margin-top: 6px; }}
    a {{ color: var(--link); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .back-link {{ margin-bottom: 12px; }}
    .table-wrap {{ width: 100%; overflow-x: auto; overflow-y: hidden; -webkit-overflow-scrolling: touch; }}
    @media (max-width: 720px) {{ body {{ font-size: 14px; }} .page {{ padding: 18px 12px 32px; }} table {{ min-width: 860px; }} th, td {{ padding: 8px 10px; }} }}
  </style>
</head>
<body>
  <main class="page">
    {body}
  </main>
</body>
</html>
""".format(title=html.escape(title), body=body)
