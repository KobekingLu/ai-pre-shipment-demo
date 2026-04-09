#!/bin/bash

# ========== CONFIG ==========
# Define your Ethernet-BDF pairs here
ETH_NAMES=("b06p0" "b07p0" "b08p0" "b09p0")
BDFS=("06:00.0" "07:00.1" "08:00.2" "09:00.3")
LAN_INFO="FWA-4134_NMC1_NMC-0808_PLX8716"
OUTPUT="${LAN_INFO}.txt"

# ========== Start ==========
echo "======================== Start ========================" | tee $OUTPUT
echo "==== Intel Corporation Ethernet Controller I226-LM ====" | tee -a $OUTPUT

for ((i=0; i<${#ETH_NAMES[@]}; i++)); do
  eth=${ETH_NAMES[$i]}
  bdf=${BDFS[$i]}

  echo "[INFO] Processing $eth ($bdf)" | tee -a $OUTPUT

  {
    echo "--------- Transceiver_INFO ($eth) ---------"
    ethtool -m $eth
    sleep 2
    
    echo "--------- Transceiver_INFO Hex ($eth) ---------"
    ethtool -m $eth hex on
    sleep 2
	
    echo "--------- ethtool ($eth) ---------"
    ethtool $eth

    echo "--------- ifconfig ($eth) ---------"
    ifconfig $eth

    echo "--------- ethtool -i ($eth) ---------"
    ethtool -i $eth

    echo "--------- lspci ($bdf) ---------"
    lspci -vvv -nn -s $bdf
  } >> $OUTPUT 2>&1
     sleep 2
done

echo "--------- modinfo igb ---------" >> $OUTPUT
modinfo igb >> $OUTPUT 2>&1

echo "--------- dmesg ---------" >> $OUTPUT
dmesg >> $OUTPUT 2>&1

#echo "--------- ipmitool fru ---------" >> $OUTPUT
#ipmitool fru >> $OUTPUT 2>&1

echo "--------- lseth Detail ---------" >> $OUTPUT
lseth Detail >> tmp.txt
sed -r "s/\x1B\[([0-9]{1,2}(;[0-9]{1,2})?)?[m|K]//g" tmp.txt >> $OUTPUT
rm tmp.txt

echo "--------- apdi -a ---------" >> $OUTPUT
apdi -a >> tmp_apdi.txt
sed -r "s/\x1B\[([0-9]{1,2}(;[0-9]{1,2})?)?[m|K]//g" tmp_apdi.txt >> $OUTPUT
rm tmp_apdi.txt

echo "--------- CPU&OS Info---------" >> $OUTPUT
lscpu | tee -a $OUTPUT 2>&1
echo "---" | tee -a $OUTPUT 2>&1
uname -a | tee -a $OUTPUT 2>&1
echo "---" | tee -a $OUTPUT 2>&1
cat /etc/os-release | tee -a $OUTPUT 2>&1

echo "======================== END ========================" | tee -a $OUTPUT
