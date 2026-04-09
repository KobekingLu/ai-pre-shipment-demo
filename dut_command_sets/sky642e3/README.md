# SKY642E3 Command Set

This folder is the command boundary for restricted DUT collection.

`allowed_commands.json` defines:
- which commands the collector may execute
- how each command output should be normalized into `actual_config`
- which commands are optional

Safety intent:
- read-only commands only
- no `sudo`
- no package install
- no service start/stop
- no firmware flash
- no disk write
- optional scripts, if ever needed, must stay in this folder and are staged only into a remote `/tmp` sandbox

Example:

```powershell
python collect_dut.py `
  --profile dut_command_sets/sky642e3/allowed_commands.json `
  --host labuser@192.0.2.10 `
  --dry-run
```
