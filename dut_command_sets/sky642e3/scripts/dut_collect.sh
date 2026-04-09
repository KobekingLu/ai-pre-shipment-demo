#!/bin/bash

# =============================
# DUT Comprehensive Collection Script
# Version: Pro (Enhanced with Timestamps, Command Labels, Error Highlighting)
# =============================

# Output files
TS="$(date +%Y%m%d_%H%M%S)"
RAW="/tmp/DUT_full_report_${TS}.txt"
HTML="/tmp/DUT_fancy_report_${TS}.html"
PDF="/tmp/DUT_fancy_report_${TS}.pdf"

# Create temporary markdown-like file to convert to HTML later
MD="/tmp/DUT_fancy_content_${TS}.md"
echo "<a name=\"top\"></a>" > $MD

# Track section titles for TOC
TOC=""
function section() {
  local title="$1"
  local cmd="$2"
  local anchor=$(echo "$title" | tr '[:upper:]' '[:lower:]' | tr -dc 'a-z0-9' | tr ' ' '-')
  local start_time=$(date +%s)
  TOC+=$'\n'"<li><a href=\"#$anchor\">$title</a></li>"

  echo -e "\n<a name=\"$anchor\"></a>" >> $MD
  echo -e "<details open><summary><strong>$title</strong></summary><pre>" >> $MD
  echo "# Command: $cmd" >> $MD
  echo "# Timestamp: $(date '+%Y-%m-%d %H:%M:%S')" >> $MD

  if output=$(eval "$cmd" 2>&1); then
    echo "$output" | tee -a $RAW | sed 's/</\</g; s/>/\>/g' >> $MD
  else
    echo "$output" | tee -a $RAW | sed 's/</\</g; s/>/\>/g' | sed 's/^/[ERROR] /' >> $MD
  fi

  local end_time=$(date +%s)
  local duration=$((end_time - start_time))
  echo "\n# Duration: ${duration} sec" >> $MD
  echo -e "</pre><div style=\"text-align:right\"><a href=\"#top\">[Top]</a></div></details>\n" >> $MD
}

# Rewritten sections with full command strings
section "OS & Kernel Info" "uname -a && cat /etc/os-release"
section "CPU & Memory" "lscpu && free -h && dmidecode -t processor && dmidecode -t memory"
section "System / Motherboard Info" "dmidecode -t system && dmidecode -t baseboard && dmidecode -t chassis"
section "Block Devices" "lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT,MODEL && df -hT && mount | grep ^/"

# SMART Health
if command -v smartctl &> /dev/null; then
  for dev in /dev/sd[a-z]; do
    section "SMART Health: $dev" "smartctl -H $dev 2>/dev/null"
  done
else
  section "SMART Health" "echo '[smartctl not installed]'"
fi

# PCI & USB Devices
section "PCI & USB Devices" "lspci -nn && lsusb"

# Network Interfaces
section "Network Interfaces" "ip link show && ip addr show && ss -tulpn"

# Ethernet Driver & Statistics
for iface in $(ls /sys/class/net | grep -v lo); do
  section "Ethernet Interface: $iface" "ethtool -i $iface 2>/dev/null && ethtool $iface 2>/dev/null && ip -s link show $iface"
done

# IRQ / NUMA
section "IRQ & NUMA" "cat /proc/interrupts && lscpu | grep 'NUMA node' && numactl --hardware"

# Services
section "Running Services" "systemctl list-units --type=service --state=running"

# Kernel Logs
section "Kernel Logs" "dmesg | grep -iE 'error|fail|warn|iommu|dmar'"

# Boot Parameters
section "Boot Parameters" "cat /proc/cmdline && cat /etc/default/grub"

# System Load
section "System Load Snapshot" "uptime && top -bn1 | head -20"

# lshw
if command -v lshw &> /dev/null; then
  section "lshw Short Info" "lshw -short"
else
  section "lshw Short Info" "echo '[lshw not installed]'"
fi

# BMC / IPMI
if command -v ipmitool &> /dev/null; then
  section "BMC / IPMI Info" "ipmitool chassis power status && ipmitool sensor && ipmitool sel list && ipmitool fru"
else
  section "BMC / IPMI Info" "echo '[ipmitool not installed]'"
fi

# Finalize HTML
cat <<EOF > $HTML
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>DUT Report</title>
<style>
body { font-family: monospace; background: #f7f7f7; padding: 20px; }
details { margin-bottom: 10px; }
summary { font-size: 1.1em; cursor: pointer; background: #ddd; padding: 5px; border-radius: 5px; }
pre { background: #fff; padding: 10px; border: 1px solid #ccc; border-radius: 5px; overflow-x: auto; white-space: pre-wrap; }
nav { margin-bottom: 20px; padding: 10px; background: #eef; border-radius: 5px; }
nav ul { list-style-type: none; padding-left: 0; }
nav li { margin-bottom: 5px; }
button { margin-bottom: 20px; padding: 5px 10px; }
[ERROR] { color: red; }
</style>
<script>
function toggleAll(open) {
  document.querySelectorAll('details').forEach(d => d.open = open);
}
</script>
</head>
<body>
<h1>DUT Report</h1>
<nav>
<strong>Table of Contents</strong>
<ul>
$TOC
</ul>
</nav>
<button onclick="toggleAll(true)">Expand All</button>
<button onclick="toggleAll(false)">Collapse All</button>
EOF

cat $MD >> $HTML

echo "</body></html>" >> $HTML

# Optional PDF Export (requires wkhtmltopdf)
if command -v wkhtmltopdf &> /dev/null; then
  wkhtmltopdf --enable-local-file-access $HTML $PDF
  echo "[INFO] PDF report: $PDF"
else
  echo "[INFO] wkhtmltopdf not installed, skipping PDF generation."
fi

# Done
echo -e "\n[INFO] Collection complete."
echo "[INFO] Plaintext report: $RAW"
echo "[INFO] HTML report: $HTML"
exit 0

