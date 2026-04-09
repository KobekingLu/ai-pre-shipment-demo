# Optional Scripts

Place optional helper scripts here only when a plain read-only command is not enough.

Rules:
- keep scripts read-focused
- prefer parsing or formatting helpers, not system-changing logic
- collector will only stage these scripts into a remote `/tmp` sandbox
- scripts must be referenced explicitly from `allowed_commands.json`
