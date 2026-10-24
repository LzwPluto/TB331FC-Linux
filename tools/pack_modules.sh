#!/bin/bash
set +e
cd /mnt/d/TB331FCLinux/build/modroot || exit 1
echo "modroot size: $(du -sh . | cut -f1)"
rm -f /mnt/d/TB331FCLinux/build/modules-6.14.tar.gz
tar czf /mnt/d/TB331FCLinux/build/modules-6.14.tar.gz lib
ls -lh /mnt/d/TB331FCLinux/build/modules-6.14.tar.gz
echo "ko count in tar: $(tar tzf /mnt/d/TB331FCLinux/build/modules-6.14.tar.gz | grep -c '\.ko$')"
