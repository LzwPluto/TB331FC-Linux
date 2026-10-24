#!/bin/bash
cd ~/kbuild/linux-next-tb128fu-hx83102-panel-port || exit 1
echo "=== WiFi / BT 相关内核配置 ==="
for o in ATH10K ATH10K_SNOC ATH10K_SDIO CFG80211 MAC80211 RFKILL \
         BT BT_HCIUART BT_HCIUART_QCA BT_QCA QCOM_WCNSS; do
    v=$(grep -E "^CONFIG_${o}=" .config)
    if [ -z "$v" ]; then printf "  %-24s NOT SET\n" "$o"; else printf "  %-24s %s\n" "$o" "$v"; fi
done
