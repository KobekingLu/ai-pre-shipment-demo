# Restricted DUT Collection / 受限 DUT 蒐集

This repo now includes a minimal restricted SSH collector for the next demo step:

- `collect_dut.py`
- `pre_shipment/dut_ssh.py`
- `dut_command_sets/sky642e3/allowed_commands.json`

## What it is for

Use this flow when we want the agent to collect actual system evidence from a live DUT over SSH without giving it a wide shell.

The current design keeps the existing workbook demo intact and adds a separate, incremental path for DUT collection.

## Safety model / 安全模型

The collector reduces risk through several layers:

1. Only commands listed in the command-set JSON are allowed.
2. The collector rejects commands outside a small read-only allowlist.
3. Optional uploaded scripts can only be staged into a remote `/tmp` or `/var/tmp` sandbox.
4. The collector does not use `sudo`, package install, service control, firmware flash, or disk write operations.
5. Local outputs are written into `output/dut_runs/`.

Important boundary:

This does **not** create a perfect guarantee by itself.  
If we want near-real sandbox behavior, the DUT should also provide:

- a dedicated low-privilege SSH account
- no sudo permission
- forced command or wrapper entrypoint if possible
- restricted writable directories
- ideally a lab-only account for the demo

In other words, the repo-side collector can be strict, but true non-destructive protection must be completed on the DUT side too.

## Current SKY642E3 profile / 目前 SKY642E3 設定

The included `sky642e3` command set focuses on read-oriented evidence:

- DMI product name / SKU / version
- board name
- BIOS version
- optional BMC firmware and BMC LAN info through `ipmitool`
- host IPv4
- CPU / memory / OS summary notes

This is enough to start building `actual_config` from a real machine without changing the existing workbook parser.

The repo now also supports a minimal agent-side probe planner:

1. read a PM tracking workbook
2. decide which repo-defined common scripts are worth running
3. write a planned profile under `dut_command_sets/_planned_profiles/`
4. execute only those scripts plus the base read-only commands

Current common scripts include:

- `collect_tracking_relevant_inventory.py`
- `collect_pcie_device_inventory.py`
- `collect_operational_attention.py`

## Example usage / 使用方式

Dry run first:

```powershell
python collect_dut.py `
  --profile dut_command_sets/sky642e3/allowed_commands.json `
  --host labuser@192.0.2.10 `
  --expected-workbook input_data\PM_ES_Tracking_SKY642E3.xlsx `
  --dry-run
```

Actual collection:

```powershell
python collect_dut.py `
  --profile dut_command_sets/sky642e3/allowed_commands.json `
  --host labuser@192.0.2.10 `
  --identity-file C:\keys\lab_id_ed25519
```

Outputs will be saved under:

- `output/dut_runs/SKY642E3/<run_id>/collection_result.json`
- per-command stdout / stderr text files

## Next integration step / 下一步

Recommended next step is:

1. Run `collect_dut.py` against the real SKY642E3 DUT.
2. Review the generated `parsed_actual_config`.
3. Map that structure into the same analysis path used by the workbook and demo-case flows.
4. Render the collected actual evidence into the existing bilingual HTML demo.
