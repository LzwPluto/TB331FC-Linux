#!/bin/bash
cd ~/kbuild/linux-next-tb128fu-hx83102-panel-port || exit 1
for o in QCOM_ZAP_SHADER QCOM_MDT_LOADER QCOM_SCM QCOM_PIL_INFO DRM_MSM \
         DRM_MSM_GPU_STATE XZ_DEC QCOM_OCMEM; do
    v=$(grep -E "^CONFIG_${o}=" .config)
    if [ -z "$v" ]; then printf "  %-24s NOT SET\n" "$o"; else printf "  %-24s %s\n" "$o" "$v"; fi
done
