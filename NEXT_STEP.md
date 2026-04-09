# NEXT_STEP.md

## Current Project
AI Pre-Shipment Risk Decision Agent

## Current Status
The project already has a working demo foundation.

### Completed
- Real workbook parsing from `input_data/`
- Fake demo case support from `demo_cases/`
- Rule-based risk evaluation
- JSON outputs
- Bilingual HTML overview page
- Bilingual HTML detail pages
- Demo scenarios for:
  - Go
  - Conditional Go
  - No-Go

### Current Demo Output
The current demo can show:
1. Real workbook review results
2. Fake demo scenario results
3. Agent workflow explanation
4. Risk level and recommendation
5. Problem details
6. Recommended owner
7. Suggested next step

## Current Strength
The demo already shows agent-like behavior:
- inspects available data sources
- selects usable evidence
- detects missing evidence
- compares expected vs actual
- evaluates known issues
- recommends next workflow action

## Known Gaps
### Real workbook data gaps
- Some real workbooks still do not contain actual system / firmware data
- Some real workbooks do not contain known issue data
- PM workbook detail page still shows very long evidence-gap text and could be simplified later

### Logic gaps
- Current decision logic is still version-1 rule-based logic
- Risk explanation can still become more role-oriented for PM / AE / RD / DQA
- Recommended owner logic is still simple

### Integration gaps
- Not yet connected to live DUT command collection
- Not yet generating an actual execution sheet from DUT
- Not yet connected to Redmine / release note / MCP-based tools

### New scaffold now available
- Restricted SSH collection entry point: `collect_dut.py`
- Guardrail module: `pre_shipment/dut_ssh.py`
- SKY642E3 sample command-set: `dut_command_sets/sky642e3/allowed_commands.json`
- Safety note: repo-side restrictions reduce risk, but near-sandbox protection still requires a low-privilege SSH account on the DUT

## Next Main Goal
Move from:
- workbook-based review demo

To:
- PM tracking sheet as expected input
- DUT-collected actual data as actual input
- agent-generated actual execution sheet
- automatic compare and shipment review output

## Next Practical Steps
1. Find a real PM / AE tracking sheet for one target system
   - preferred: SKY-642E3 if available

2. Prepare a minimal DUT collection flow
   - BIOS
   - BMC
   - CPU
   - Memory
   - optionally FPGA / BL / BMCONF / storage

3. Define `actual_execution_sheet` or `agent_collected_system_info` format

4. Let the agent:
   - read PM tracking sheet
   - collect DUT data
   - generate actual execution sheet
   - compare expected vs actual
   - render review result

## If Continuing on Another Computer
When reopening this project on another machine:
1. read `AGENTS.md`
2. read `README.md`
3. read this file (`NEXT_STEP.md`)
4. inspect current project structure
5. summarize current project state before making changes

## Short Handoff Prompt
Use this when continuing with Codex:

This project is AI Pre-Shipment Risk Decision Agent.

Please first read AGENTS.md, README.md, and NEXT_STEP.md.
Then inspect the current project folder and summarize:
- what is already completed
- what the current demo can show
- what the next main implementation goal should be

The next goal is to connect:
- PM tracking sheet
- DUT-collected actual system data
- agent-generated actual execution sheet
- compare + shipment decision output
