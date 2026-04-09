#!/bin/bash
set -u

# =========================
# Required tools (hard requirement)
# =========================
required_tools=("smartctl" "lsblk" "nvme" "dd" "dmesg" "lshw")
for tool in "${required_tools[@]}"; do
    if ! command -v "$tool" &>/dev/null; then
        echo "Error: Required tool '$tool' is not installed. Please install it and rerun the script." >&2
        exit 1
    fi
done

# Optional tools (best effort)
optional_tools=("lspci" "dmidecode")
for tool in "${optional_tools[@]}"; do
    if ! command -v "$tool" &>/dev/null; then
        echo "WARN: Optional tool '$tool' is not installed. Some info may be skipped." >&2
    fi
done

# =========================
# Output files
# =========================
timestamp=$(date "+%Y%m%d_%H%M%S")
report_file="storage_test_report_${timestamp}.html"
log_file="storage_test_log_${timestamp}.log"

# =========================
# Init report/log
# =========================
cat <<EOF > "$report_file"
<html><body><h1>Storage Test Report</h1>
<style>
details summary {font-weight: bold; cursor: pointer;}
details {margin-bottom: 10px;}
table {border-collapse: collapse; width: 100%; margin-top: 20px;}
table, th, td {border: 1px solid black;}
th, td {padding: 8px; text-align: left;}
th {background-color: #f2f2f2;}
</style>
<table>
<tr><th>Device</th><th>Test Type</th><th>Status</th><th>Fail Reason</th><th>Timestamp</th></tr>
EOF
echo "=== Storage Test Log ===" > "$log_file"

# =========================
# Utils
# =========================
log_section() {
    echo -e "\n=== $1 ===" | tee -a "$log_file"
}

append_html_detail() {
    local title="$1"
    local body="$2"
    # minimal HTML escape
    body="${body//&/&amp;}"
    body="${body//</&lt;}"
    body="${body//>/&gt;}"
    echo "<details><summary>${title}</summary><pre>${body}</pre></details>" >> "$report_file"
}

# =========================
# Device helpers
# =========================
list_available_devices() {
    # Only disks with no mountpoint (avoid touching OS disk in normal cases)
    lsblk -dn -o NAME,TYPE,MOUNTPOINT | awk '$2 == "disk" && $3 == "" {print $1}'
}

is_valid_device() {
    local device="$1"
    list_available_devices | grep -qw "$device"
}

# =========================
# Result logging (FIXED)
# device, test_type, status, reason
# =========================
log_test_result() {
    local device="$1"
    local test_type="$2"
    local status="$3"
    local reason="${4:-N/A}"

    if [[ "$device" =~ ^[a-zA-Z0-9]+$ && -n "$status" && -n "$test_type" ]]; then
        echo "<tr><td>/dev/$device</td><td>${test_type}</td><td>${status}</td><td>${reason}</td><td>$(date "+%Y-%m-%d %H:%M:%S")</td></tr>" >> "$report_file"
    else
        echo "Skipping invalid device entry or incomplete result: /dev/$device" >> "$log_file"
    fi
}

# =========================
# LinkCheck: SATA + NVMe PCIe speed/width
# + NVMe lspci -vv LnkSta/LnkCap
# + SATA dmesg "SATA link up"
# =========================
pcie_speed_to_gen() {
    local s="$1"
    case "$s" in
        2.5*|2.5)   echo "Gen1" ;;
        5.0*|5*|5.0) echo "Gen2" ;;
        8.0*|8*|8.0) echo "Gen3" ;;
        16.0*|16*|16.0) echo "Gen4" ;;
        32.0*|32*|32.0) echo "Gen5" ;;
        64.0*|64*|64.0) echo "Gen6" ;;
        *) echo "Unknown" ;;
    esac
}

pcie_gen_rank() {
    local gen="$1"
    case "$gen" in
        Gen1) echo 1 ;;
        Gen2) echo 2 ;;
        Gen3) echo 3 ;;
        Gen4) echo 4 ;;
        Gen5) echo 5 ;;
        Gen6) echo 6 ;;
        *) echo 0 ;;
    esac
}

get_nvme_bdf() {
    # Input: nvme controller name like nvme0
    local ctrl="$1"
    local devpath
    devpath=$(readlink -f "/sys/class/nvme/${ctrl}/device" 2>/dev/null || true)
    # devpath usually includes 0000:xx:yy.z
    echo "$devpath" | grep -oE '[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9]' | head -n1
}

collect_lspci_link_info() {
    local bdf="$1"
    if command -v lspci &>/dev/null && [[ -n "$bdf" ]]; then
        # Only keep key lines RD cares: LnkCap, LnkSta (and sometimes LnkSta2)
        lspci -s "$bdf" -vv 2>/dev/null | grep -E "LnkCap:|LnkSta:|LnkSta2:" || true
    else
        echo "(lspci not available or BDF not found)"
    fi
}

collect_sata_linkup_dmesg() {
    # best effort: show recent SATA negotiation lines
    dmesg 2>/dev/null | grep -i "SATA link up" | tail -n 30 || true
}

check_link_info() {
    local dev="$1"
    local devnode="/dev/${dev}"
    local tran
    tran=$(lsblk -dn -o TRAN "${devnode}" 2>/dev/null | head -n1)

    # -------- NVMe --------
    if [[ "$tran" == "nvme" || "$dev" =~ ^nvme[0-9]+n[0-9]+$ ]]; then
        local p ctrl
        p=$(readlink -f "/sys/block/${dev}/device" 2>/dev/null || true)
        ctrl=$(echo "$p" | grep -oE 'nvme[0-9]+' | head -n1 || true)

        if [[ -n "$ctrl" && -r "/sys/class/nvme/${ctrl}/device/current_link_speed" ]]; then
            local cur_spd cur_w max_spd max_w
            cur_spd=$(cat "/sys/class/nvme/${ctrl}/device/current_link_speed" 2>/dev/null || true)
            cur_w=$(cat  "/sys/class/nvme/${ctrl}/device/current_link_width" 2>/dev/null || true)
            max_spd=$(cat "/sys/class/nvme/${ctrl}/device/max_link_speed" 2>/dev/null || true)
            max_w=$(cat  "/sys/class/nvme/${ctrl}/device/max_link_width" 2>/dev/null || true)

            local cur_gen max_gen
            cur_gen=$(pcie_speed_to_gen "$cur_spd")
            max_gen=$(pcie_speed_to_gen "$max_spd")

            local bdf lspci_link
            bdf=$(get_nvme_bdf "$ctrl")
            lspci_link=$(collect_lspci_link_info "$bdf")

            local detail
            detail=$(
                cat <<EOF
Device: ${devnode}
Type: NVMe (PCIe)
Sysfs Current: ${cur_gen} (${cur_spd}), x${cur_w}
Sysfs Max:     ${max_gen} (${max_spd}), x${max_w}

PCI BDF: ${bdf:-N/A}
lspci -vv (Link):
${lspci_link}
EOF
            )

            echo -e "\n[LinkCheck] ${devnode}\n${detail}" | tee -a "$log_file"
            append_html_detail "Link Info - ${devnode}" "$detail"

            # Downgrade 판단（速度或寬度任一低於 max）
            local cur_rank max_rank
            cur_rank=$(pcie_gen_rank "$cur_gen")
            max_rank=$(pcie_gen_rank "$max_gen")

            if [[ "$cur_rank" -gt 0 && "$max_rank" -gt 0 && "$cur_rank" -lt "$max_rank" ]]; then
                log_test_result "$dev" "LinkCheck" "WARN" "PCIe speed downgraded (current < max)"
            elif [[ -n "${cur_w:-}" && -n "${max_w:-}" && "$cur_w" != "$max_w" ]]; then
                log_test_result "$dev" "LinkCheck" "WARN" "PCIe width downgraded (current < max)"
            else
                log_test_result "$dev" "LinkCheck" "PASS" ""
            fi
            return 0
        else
            log_test_result "$dev" "LinkCheck" "WARN" "Cannot read NVMe PCIe link info from sysfs"
            return 0
        fi
    fi

    # -------- SATA / ATA --------
    if [[ "$tran" == "sata" || "$tran" == "ata" || "$dev" =~ ^sd[a-z]+$ ]]; then
        local info line max_g cur_g
        info=$(smartctl -i "${devnode}" 2>/dev/null || true)

        # Example:
        # SATA Version is:  SATA 3.3, 6.0 Gb/s (current: 6.0 Gb/s)
        line=$(echo "$info" | grep -iE 'SATA Version is:' | head -n1 || true)

        max_g=$(echo "$line" | grep -oE '[0-9]+\.[0-9]+ Gb/s' | head -n1 | awk '{print $1}' || true)
        cur_g=$(echo "$line" | grep -oE 'current: *[0-9]+\.[0-9]+ Gb/s' | head -n1 | awk '{print $2}' || true)

        local sata_linkup
        sata_linkup=$(collect_sata_linkup_dmesg)

        local detail
        detail=$(
            cat <<EOF
Device: ${devnode}
Type: SATA
smartctl Raw: ${line:-"(no SATA Version line from smartctl -i)"}
Parsed:
  Max:     ${max_g:-N/A} Gb/s
  Current: ${cur_g:-N/A} Gb/s

dmesg (SATA link up, recent):
${sata_linkup:-"(no SATA link up lines found)"}
EOF
        )

        echo -e "\n[LinkCheck] ${devnode}\n${detail}" | tee -a "$log_file"
        append_html_detail "Link Info - ${devnode}" "$detail"

        # If parsable, check downgrade and Gen3 6G expectation
        if [[ -n "${cur_g:-}" && -n "${max_g:-}" ]]; then
            # normalize like "6.0" -> "60" for compare (avoid bc)
            local cur_i max_i
            cur_i=$(echo "$cur_g" | awk -F. '{printf "%d%d", $1, $2}')
            max_i=$(echo "$max_g" | awk -F. '{printf "%d%d", $1, $2}')

            if [[ "$cur_i" -lt "$max_i" ]]; then
                log_test_result "$dev" "LinkCheck" "WARN" "SATA link downgraded (current < max)"
            elif [[ "$cur_i" -lt 60 ]]; then
                log_test_result "$dev" "LinkCheck" "WARN" "SATA link < 6.0 Gb/s (not Gen3 6G)"
            else
                log_test_result "$dev" "LinkCheck" "PASS" ""
            fi
        else
            log_test_result "$dev" "LinkCheck" "WARN" "SATA link speed not parsable (bridge/unsupported?)"
        fi
        return 0
    fi

    # -------- Others --------
    log_test_result "$dev" "LinkCheck" "WARN" "Unknown transport type: ${tran:-N/A}"
    return 0
}

# =========================
# R/W test
# =========================
perform_rw_test() {
    local device="$1"
    local test_file="/tmp/test_file_${device}"
    echo "Performing read/write test on /dev/$device..." | tee -a "$log_file"

    echo "Write test on /dev/$device in progress..." | tee -a "$log_file"
    if ! dd if=/dev/zero of="${test_file}" bs=1M count=100 conv=fdatasync status=progress 2>&1 | tee -a "$log_file"; then
        log_test_result "$device" "Read/Write" "FAIL" "Write error"
        return 1
    fi

    echo "Read test on /dev/$device in progress..." | tee -a "$log_file"
    if ! dd if="${test_file}" of=/dev/null bs=1M count=100 status=progress 2>&1 | tee -a "$log_file"; then
        log_test_result "$device" "Read/Write" "FAIL" "Read error"
        return 1
    fi

    rm -f "${test_file}"
    log_test_result "$device" "Read/Write" "PASS" ""
    return 0
}

# =========================
# dmesg error check helper
# =========================
check_test_pass() {
    local device="$1"
    local rw_errors
    rw_errors=$(dmesg | grep -i "error" | grep "$device" || true)
    if [[ -z "$rw_errors" ]]; then
        echo "PASS"
    else
        echo "FAIL"
        echo "Read/Write errors detected for $device" | tee -a "$log_file"
    fi
}

# =========================
# System info (BIOS version added)
# =========================
get_bios_version() {
    if [[ -r /sys/class/dmi/id/bios_version ]]; then
        cat /sys/class/dmi/id/bios_version 2>/dev/null || true
    elif command -v dmidecode &>/dev/null; then
        dmidecode -s bios-version 2>/dev/null || true
    else
        echo "(bios version unavailable: no /sys/class/dmi/id/bios_version and dmidecode not installed)"
    fi
}

record_system_info() {
    read -p "Do you want to record system information? (y/n): " record_choice
    if [[ "$record_choice" == "y" || "$record_choice" == "Y" ]]; then
        log_section "System Information Log"

        echo "Recording hardware information..." | tee -a "$log_file"
        system_info=$(lshw -short 2>&1 || true)
        echo "$system_info" | tee -a "$log_file"
        append_html_detail "Hardware Information" "$system_info"

        echo "Recording OS information..." | tee -a "$log_file"
        os_info=$(cat /etc/os-release 2>/dev/null || uname -a)
        echo "$os_info" | tee -a "$log_file"
        append_html_detail "OS Version" "$os_info"

        echo "Recording BIOS version..." | tee -a "$log_file"
        bios_ver=$(get_bios_version)
        echo "BIOS Version: $bios_ver" | tee -a "$log_file"
        append_html_detail "BIOS Version" "BIOS Version: $bios_ver"

        echo "Scanning disks with smartctl..." | tee -a "$log_file"
        smartctl_scan=$(smartctl --scan 2>&1 || true)
        echo "$smartctl_scan" | tee -a "$log_file"
        append_html_detail "Disk Scanning" "$smartctl_scan"

        devices=$(echo "$smartctl_scan" | awk '{print $1}')
        for devpath in $devices; do
            echo "Recording SMART information for $devpath..." | tee -a "$log_file"
            smartctl_info=$(smartctl -a "$devpath" 2>&1 || true)
            echo "$smartctl_info" | tee -a "$log_file"
            append_html_detail "SMART Info for $devpath" "$smartctl_info"
        done

        echo "Scanning NVMe devices with nvme list..." | tee -a "$log_file"
        nvme_list=$(nvme list 2>&1 || true)
        echo "$nvme_list" | tee -a "$log_file"
        append_html_detail "NVMe Devices" "$nvme_list"

        nvme_devices=$(echo "$nvme_list" | awk '/\/dev\// {print $1}')
        for nvme_device in $nvme_devices; do
            echo "Recording NVMe information for $nvme_device..." | tee -a "$log_file"
            nvme_info=$(nvme id-ctrl "$nvme_device" 2>&1 || true)
            echo "$nvme_info" | tee -a "$log_file"
            append_html_detail "NVMe Info for $nvme_device" "$nvme_info"
        done

        echo "System information recording completed." | tee -a "$log_file"
    fi
}

# =========================
# Existing devices check (FIXED)
# =========================
check_existing_devices() {
    read -p "Do you want to check existing devices? (y/n): " check_choice
    if [[ "$check_choice" != "y" && "$check_choice" != "Y" ]]; then
        return 0
    fi

    log_section "Existing Devices Check Log"

    local available_devices
    available_devices=$(list_available_devices | sort | uniq)

    echo "Available devices (unmounted disks):"
    echo "$available_devices"
    echo "Available devices: $available_devices" | tee -a "$log_file"

    read -p "Enter device names (e.g., sda nvme0n1) or 'all': " device_choices

    # keep raw "all" if user typed all
    if [[ "$device_choices" == "all" ]]; then
        selected_devices="$available_devices"
    else
        device_choices=$(echo "$device_choices" | tr ' ' '\n' | grep -E "^[a-zA-Z0-9]+$" | sort | uniq)
        selected_devices=""
        for device in $device_choices; do
            if is_valid_device "$device"; then
                selected_devices="${selected_devices} ${device}"
            else
                echo "Invalid device: $device" | tee -a "$log_file"
            fi
        done
        selected_devices=$(echo "$selected_devices" | tr -s ' ' | sed 's/^ *//;s/ *$//')
    fi

    if [[ -z "${selected_devices:-}" ]]; then
        echo "No valid devices selected. Exiting..."
        exit 1
    fi

    echo "Final selected devices:"
    echo "$selected_devices"

    for device in $selected_devices; do
        echo "Testing device: $device" | tee -a "$log_file"
        check_link_info "$device"
        perform_rw_test "$device"

        status=$(check_test_pass "$device")
        if [[ "$status" == "FAIL" ]]; then
            log_test_result "$device" "dmesgCheck" "WARN" "dmesg contains error for this device"
        else
            log_test_result "$device" "dmesgCheck" "PASS" ""
        fi
    done
}

# =========================
# Hot-Plug test (LinkCheck added)
# =========================
perform_hot_plug_test() {
    read -p "Do you want to perform Hot-Plug testing? (y/n): " hot_plug_choice
    if [[ "$hot_plug_choice" != "y" && "$hot_plug_choice" != "Y" ]]; then
        return 0
    fi

    log_section "Hot-Plug Test Log"
    dmesg -C

    local devices_before devices_after new_devices
    devices_before=$(list_available_devices | sort)

    read -p "Insert a new device and press Enter when ready..."

    echo "=== dmesg after device insertion ===" >> "$log_file"
    dmesg | tail -n 80 >> "$log_file"

    # Extra: SATA negotiated speed lines (common RD check)
    sata_linkup=$(dmesg | grep -i "SATA link up" | tail -n 30 || true)
    if [[ -n "$sata_linkup" ]]; then
        append_html_detail "Hot-Plug dmesg SATA link up (recent)" "$sata_linkup"
    fi

    devices_after=$(list_available_devices | sort)
    new_devices=$(comm -13 <(echo "$devices_before") <(echo "$devices_after"))

    if [[ -z "$new_devices" ]]; then
        echo "No new device detected." | tee -a "$log_file"
        return 0
    fi

    for device in $new_devices; do
        if is_valid_device "$device"; then
            check_link_info "$device"
            perform_rw_test "$device"
            status=$(check_test_pass "$device")
            log_test_result "$device" "Hot-Plug" "$status" ""
        else
            log_test_result "$device" "Hot-Plug" "FAIL" "Invalid device"
        fi
    done
}

# =========================
# Hot-Swap test (LinkCheck added)
# =========================
perform_hot_swap_test() {
    read -p "Do you want to perform Hot-Swap testing? (y/n): " hot_swap_choice
    if [[ "$hot_swap_choice" != "y" && "$hot_swap_choice" != "Y" ]]; then
        return 0
    fi

    log_section "Hot-Swap Test Log"
    dmesg -C

    local devices_before devices_after_removal devices_after_replacement swapped_devices
    devices_before=$(list_available_devices | sort)

    read -p "Remove a device and press Enter when ready..."
    devices_after_removal=$(list_available_devices | sort)

    echo "=== dmesg after device removal ===" >> "$log_file"
    dmesg | tail -n 80 >> "$log_file"

    dmesg -C
    read -p "Replace the device and press Enter when ready..."
    devices_after_replacement=$(list_available_devices | sort)

    echo "=== dmesg after device replacement ===" >> "$log_file"
    dmesg | tail -n 80 >> "$log_file"

    sata_linkup=$(dmesg | grep -i "SATA link up" | tail -n 30 || true)
    if [[ -n "$sata_linkup" ]]; then
        append_html_detail "Hot-Swap dmesg SATA link up (recent)" "$sata_linkup"
    fi

    swapped_devices=$(comm -13 <(echo "$devices_after_removal") <(echo "$devices_after_replacement"))

    if [[ -z "$swapped_devices" ]]; then
        echo "No swapped device detected." | tee -a "$log_file"
        return 0
    fi

    for device in $swapped_devices; do
        if is_valid_device "$device"; then
            check_link_info "$device"
            perform_rw_test "$device"
            status=$(check_test_pass "$device")
            log_test_result "$device" "Hot-Swap" "$status" ""
        else
            log_test_result "$device" "Hot-Swap" "FAIL" "Invalid device"
        fi
    done
}

# =========================
# Main
# =========================
record_system_info
check_existing_devices
perform_hot_plug_test
perform_hot_swap_test

echo "</table></body></html>" >> "$report_file"
echo "Testing complete. Report saved to $report_file, log saved to $log_file." | tee -a "$log_file"

