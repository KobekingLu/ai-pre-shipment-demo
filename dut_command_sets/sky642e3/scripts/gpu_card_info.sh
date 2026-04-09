#!/bin/bash

# Usage:
#   ./gpu_card_info.sh
#   ./gpu_card_info.sh MY_GPU_INFO.txt

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
HOST=$(hostname)
OUTFILE="${1:-${HOST}_GPU_CARD_INFO_${TIMESTAMP}.txt}"

TMPFILE=$(mktemp)

# Collect NVIDIA BDF list
NVIDIA_BDFS=$(lspci | grep -i nvidia | awk '{print $1}')

{
    echo "======================================================================"
    echo " GPU CARD INFO"
    echo "======================================================================"
    echo "Date      : $(date)"
    echo "Hostname  : $(hostname)"
    echo "User      : $(whoami)"
    echo "Kernel    : $(uname -a)"
    echo "Output    : $OUTFILE"
    echo
} > "$TMPFILE"

{
    echo "======================================================================"
    echo " [1] NVIDIA CARD SUMMARY (PCIe level)"
    echo "======================================================================"
    if lspci | grep -qi nvidia; then
        lspci | grep -i nvidia
    else
        echo "No NVIDIA device found in lspci."
    fi
    echo
} >> "$TMPFILE"

{
    echo "======================================================================"
    echo " [2] NVIDIA CARD SUMMARY (-nn)"
    echo "======================================================================"
    if lspci -nn | grep -qi nvidia; then
        lspci -nn | grep -i nvidia
    else
        echo "No NVIDIA device found in lspci -nn."
    fi
    echo
} >> "$TMPFILE"

{
    echo "======================================================================"
    echo " [3] NVIDIA-SMI SUMMARY"
    echo "======================================================================"
    if command -v nvidia-smi >/dev/null 2>&1; then
        nvidia-smi
    else
        echo "nvidia-smi command not found"
    fi
    echo
} >> "$TMPFILE"

{
    echo "======================================================================"
    echo " [4] NVIDIA-SMI GPU LIST"
    echo "======================================================================"
    if command -v nvidia-smi >/dev/null 2>&1; then
        nvidia-smi -L
    else
        echo "nvidia-smi command not found"
    fi
    echo
} >> "$TMPFILE"

{
    echo "======================================================================"
    echo " [5] NVIDIA GPU INVENTORY (CSV)"
    echo "======================================================================"
    if command -v nvidia-smi >/dev/null 2>&1; then
        nvidia-smi --query-gpu=index,name,uuid,serial,pci.bus_id,vbios_version,driver_version,memory.total,power.limit \
                   --format=csv
    else
        echo "nvidia-smi command not found"
    fi
    echo
} >> "$TMPFILE"

{
    echo "======================================================================"
    echo " [6] PER-CARD QUICK VIEW"
    echo "======================================================================"

    if [ -z "$NVIDIA_BDFS" ]; then
        echo "No NVIDIA device found."
        echo
    else
        for BDF in $NVIDIA_BDFS; do
            CARD_NAME=$(lspci -s "$BDF" | sed "s/^$BDF[[:space:]]*//")
            PCI_NN=$(lspci -nn -s "$BDF")
            LINK_INFO=$(lspci -vv -s "$BDF" 2>/dev/null | grep -E "LnkCap:|LnkSta:")

            echo "----------------------------------------------------------------------"
            echo "BDF       : $BDF"
            echo "CARD NAME : $CARD_NAME"
            echo "PCI ID    : $PCI_NN"
            if [ -n "$LINK_INFO" ]; then
                echo "$LINK_INFO"
            else
                echo "Link Info : N/A"
            fi
            echo
        done
    fi
} >> "$TMPFILE"

{
    echo "======================================================================"
    echo " [7] NVIDIA DRIVER INFO"
    echo "======================================================================"
    if command -v modinfo >/dev/null 2>&1; then
        modinfo nvidia 2>/dev/null | head -20
    else
        echo "modinfo command not found"
    fi
    echo
} >> "$TMPFILE"

{
    echo "======================================================================"
    echo " [8] PER-CARD DETAIL : lspci -vv -s"
    echo "======================================================================"

    if [ -z "$NVIDIA_BDFS" ]; then
        echo "No NVIDIA device found."
        echo
    else
        for BDF in $NVIDIA_BDFS; do
            CARD_NAME=$(lspci -s "$BDF" | sed "s/^$BDF[[:space:]]*//")
            echo "----------------------------------------------------------------------"
            echo "DETAIL FOR : $BDF"
            echo "CARD NAME  : $CARD_NAME"
            echo "----------------------------------------------------------------------"
            lspci -vv -s "$BDF"
            echo
        done
    fi
} >> "$TMPFILE"

{
    echo "======================================================================"
    echo " [9] NVIDIA-SMI FULL QUERY"
    echo "======================================================================"
    if command -v nvidia-smi >/dev/null 2>&1; then
        nvidia-smi -q
    else
        echo "nvidia-smi command not found"
    fi
    echo
} >> "$TMPFILE"

mv "$TMPFILE" "$OUTFILE"
echo "GPU information has been saved to: $OUTFILE"
