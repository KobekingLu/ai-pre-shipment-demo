#!/bin/bash

if [ $# -eq 0 ]; then
  echo "Usage: $0 [FilenamePrefix]"
  exit 1
fi

set -e
OUTDIR="meminfo_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTDIR"
OUTFILE="$OUTDIR/$1.txt"

echo "=================Start======================" | tee -a "$OUTFILE"
echo "MEM_INFO" | tee -a "$OUTFILE"

function section() {
  echo "==================================" | tee -a "$OUTFILE"
  echo "$1" | tee -a "$OUTFILE"
}

section "CPU & OS & BIOS Info"
lscpu | tee -a "$OUTFILE"
echo "---" | tee -a "$OUTFILE"
uname -a | tee -a "$OUTFILE"
echo "---" | tee -a "$OUTFILE"
cat /etc/os-release | tee -a "$OUTFILE"
echo "---" | tee -a "$OUTFILE"
dmidecode -t bios | tee -a "$OUTFILE"

section "Memory Slot Physical Layout Summary"
# 這是新加入的區塊，提供最直觀的表格
sudo dmidecode -t 17 | awk -F': ' '
BEGIN { printf "%-20s | %-15s | %-5s | %-12s | %s\n", "Locator", "Size", "Type", "Manufacturer", "Part Number" }
/Handle / { 
    if (loc != "") { 
        if (size == "No Module Installed") printf "%-20s | %-15s | %-5s | %-12s | %s\n", loc, "--", "--", "--", "--";
        else printf "%-20s | %-15s | %-5s | %-12s | %s\n", loc, size, type, man, part;
    } 
    loc=size=type=man=part="" 
}
# 使用 $1 的精確比對，避免抓到 Volatile Size 或 Bank Locator
$1 ~ /^[[:space:]]*Locator$/ { loc=$2 }
$1 ~ /^[[:space:]]*Size$/ { size=$2 }
$1 ~ /^[[:space:]]*Type$/ { type=$2 }
$1 ~ /^[[:space:]]*Manufacturer$/ { man=$2 }
$1 ~ /^[[:space:]]*Part Number$/ { part=$2 }
END { 
    if (loc != "") { 
        if (size == "No Module Installed") printf "%-20s | %-15s | %-5s | %-12s | %s\n", loc, "--", "--", "--", "--";
        else printf "%-20s | %-15s | %-5s | %-12s | %s\n", loc, size, type, man, part;
    }
}' | column -t -s '|' | tee -a "$OUTFILE"

section "dmidecode -t Memory (Raw)"
dmidecode -t Memory >> "$OUTFILE"

section "Summary: Total Installed Memory (from dmidecode)"
dmidecode -t Memory | grep -i "Size:" | grep -v "No Module Installed" >> "$OUTFILE"

section "lsmem"
lsmem >> "$OUTFILE"

section "free -m"
free -m >> "$OUTFILE"

section "top -b | head -n 6"
top -b | head -n 6 >> "$OUTFILE"

section "cat /proc/meminfo"
cat /proc/meminfo >> "$OUTFILE"

section "cat /proc/cmdline"
cat /proc/cmdline >> "$OUTFILE"

section "numactl --hardware"
numactl --hardware >> "$OUTFILE" 2>/dev/null || echo "numactl not found or not supported" >> "$OUTFILE"

section "lshw -class memory"
lshw -class memory >> "$OUTFILE" 2>/dev/null || echo "lshw not installed" >> "$OUTFILE"

section "PRE-STRESS: dmesg memory errors"
dmesg | grep -iE "ecc|edac|mce|error" > "$OUTDIR/dmesg_before.txt"
cat "$OUTDIR/dmesg_before.txt" >> "$OUTFILE"

section "PRE-STRESS: rasdaemon error count"
if command -v ras-mc-ctl &>/dev/null; then
  sudo ras-mc-ctl --errors > "$OUTDIR/ras_before.txt"
  cat "$OUTDIR/ras_before.txt" >> "$OUTFILE"
else
  echo "rasdaemon not installed." >> "$OUTFILE"
fi

section "PRE-STRESS: edac-util"
if command -v edac-util &>/dev/null; then
  edac-util -v > "$OUTDIR/edac_before.txt"
  cat "$OUTDIR/edac_before.txt" >> "$OUTFILE"
else
  echo "edac-utils not installed." >> "$OUTFILE"
fi

section "Stress Test (stress-ng)"
if command -v stress-ng &>/dev/null; then
  echo "--- stress-ng output ---" | tee -a "$OUTFILE"
  # 執行 Stress Test
  stress-ng --vm 2 --vm-bytes 80% --timeout 300s --verbose --metrics-brief > "$OUTDIR/stress_output.txt" 2>&1
  cat "$OUTDIR/stress_output.txt" | tee -a "$OUTFILE"
else
  echo "stress-ng not installed. Please run: sudo apt install stress-ng" | tee -a "$OUTFILE"
fi

section "POST-STRESS: dmesg memory errors"
dmesg | grep -iE "ecc|edac|mce|error" > "$OUTDIR/dmesg_after.txt"
cat "$OUTDIR/dmesg_after.txt" >> "$OUTFILE"

section "POST-STRESS: rasdaemon error count"
if command -v ras-mc-ctl &>/dev/null; then
  sudo ras-mc-ctl --errors > "$OUTDIR/ras_after.txt"
  cat "$OUTDIR/ras_after.txt" >> "$OUTFILE"
fi

section "POST-STRESS: edac-util"
if command -v edac-util &>/dev/null; then
  edac-util -v > "$OUTDIR/edac_after.txt"
  cat "$OUTDIR/edac_after.txt" >> "$OUTFILE"
fi

section "ECC ERROR DIFF ANALYSIS"
# 比對測試前後的錯誤差異
echo "--- dmesg diff ---" >> "$OUTFILE"
if diff -q "$OUTDIR/dmesg_before.txt" "$OUTDIR/dmesg_after.txt" >/dev/null; then
  echo "✅ No new memory-related messages in dmesg after stress test." | tee -a "$OUTFILE"
else
  diff -u "$OUTDIR/dmesg_before.txt" "$OUTDIR/dmesg_after.txt" | grep -v ^@ | tee -a "$OUTFILE"
fi

echo "--- rasdaemon diff ---" >> "$OUTFILE"
if diff -q "$OUTDIR/ras_before.txt" "$OUTDIR/ras_after.txt" >/dev/null; then
  echo "✅ No new RAS memory errors detected." | tee -a "$OUTFILE"
else
  diff -u "$OUTDIR/ras_before.txt" "$OUTDIR/ras_after.txt" | grep -v ^@ | tee -a "$OUTFILE"
fi

echo "--- edac-util diff ---" >> "$OUTFILE"
if diff -q "$OUTDIR/edac_before.txt" "$OUTDIR/edac_after.txt" >/dev/null; then
  echo "✅ No new EDAC memory errors detected." | tee -a "$OUTFILE"
else
  diff -u "$OUTDIR/edac_before.txt" "$OUTDIR/edac_after.txt" | grep -v ^@ | tee -a "$OUTFILE"
fi

echo "=================END======================" | tee -a "$OUTFILE"
echo "Output saved to: $OUTFILE"
