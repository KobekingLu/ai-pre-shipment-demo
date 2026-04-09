# AI Pre-Shipment Risk Decision Agent

## Project Overview
This project is a demo prototype for an internal AI competition.

The goal is to build an AI agent that helps review shipment readiness before ES / sample shipment.

The agent is designed to:
- inspect available data sources
- identify usable evidence
- compare expected configuration with actual system information
- check known issues
- assess shipment risk
- recommend next workflow actions

---

## What the Demo Can Do Now
The current demo already supports:

### 1. Real workbook review
The agent can inspect real Excel workbooks placed under `input_data/` and try to identify:
- expected configuration source
- actual system / firmware source
- known issue source

Then it generates:
- mismatch findings
- known issue findings
- risk level
- recommendation
- next action guidance

### 2. Fake demo scenario review
The agent also supports simplified demo cases under `demo_cases/` to clearly show:
- Go
- Conditional Go
- No-Go

### 3. Bilingual HTML output
The current output includes bilingual English / Traditional Chinese HTML pages:
- overview page
- detail pages for each real workbook
- detail pages for each fake demo case

### 4. Restricted DUT SSH collection scaffold
The repo now also includes a minimal next-step scaffold for live DUT collection:
- command-set based SSH collection
- read-only command allowlist validation
- remote `/tmp` sandbox convention for optional staged scripts
- local JSON artifacts under `output/dut_runs/`
- PM-tracking driven probe planning for repo-defined common scripts

---

## Current Demo Output
The current HTML demo can show:

- agent workflow explanation
- real workbook review results
- fake demo scenario results
- risk level and recommendation
- data completeness check
- evidence summary
- risk breakdown
- problem details
- recommended owner
- suggested next step

---

## Current Project Structure
Typical project structure:

- `AGENTS.md`  
  Project-level working rules for Codex

- `README.md`  
  Project overview and current status

- `NEXT_STEP.md`  
  Current handoff and next implementation direction

- `input_data/`  
  Real workbook inputs from PM / AE

- `demo_cases/`  
  Simplified fake cases for Go / Conditional Go / No-Go

- `output/`  
  Generated JSON and HTML outputs

- parser / decision / HTML generation code  
  Core logic for current version

---

## Current Modes
### Mode A: Real workbook review
Used for PM / AE real files.

Typical flow:
1. inspect workbook
2. identify sheet roles
3. extract expected / actual / known issue evidence
4. evaluate risk
5. generate review result

### Mode B: Fake demo scenario review
Used for richer presentation during demo recording.

Typical flow:
1. load simplified expected / actual / known issue files
2. normalize them into the same analysis structure
3. evaluate risk
4. generate review result

---

## Recommendation Meanings
- **Go（可放行）**  
  Current evidence is aligned and no blocking issue is detected.

- **Conditional Go（有條件放行）**  
  Shipment may proceed only after follow-up review, missing evidence collection, or condition confirmation.

- **No-Go（不建議放行）**  
  Blocking mismatch, blocking issue, or critical risk was detected.

---

## Current Limitations
The current project is still a demo prototype.

### Current limitations include:
- rule-based decision logic only
- some real workbook inputs still have incomplete evidence
- not yet connected to live DUT collection
- not yet connected to Redmine / release notes / MCP-based tools
- recommended owner and next-step logic is still simple

The restricted SSH collector is a scaffold for the next step, not yet a fully integrated end-to-end compare flow.

---

## Next Main Direction
The next important upgrade is:

### From:
- workbook-based review demo

### To:
- PM tracking sheet as expected input
- DUT-collected actual system data as actual input
- agent-generated actual execution sheet
- automatic compare + shipment review output

In other words, the next phase is to let the agent:
1. read a PM tracking sheet
2. collect data from DUT
3. generate actual execution data
4. compare expected vs actual
5. produce shipment review result

---

## Suggested Next Inputs
To make the demo stronger, the most useful next inputs are:

- one real PM / AE tracking sheet for a target system
- actual DUT-collected system data
- clearer known issue conditions
- clearer shipment decision rules
- release note / fix version reference if available

---

## How to Continue This Project
If continuing with Codex or on another machine:

1. read `AGENTS.md`
2. read this file
3. read `NEXT_STEP.md`
4. inspect the current project structure
5. summarize current project state before making changes

---

## Short Project Summary
This is not just a static report generator.

The project is becoming an AI agent demo that:
- inspects available evidence
- selects usable data sources
- detects missing evidence
- explains shipment risk
- proposes next workflow action
