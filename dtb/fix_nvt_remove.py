#!/usr/bin/env python3
"""fix_nvt_remove.py

nvt_ts_remove() never destroys ts->event_wq even though nvt_ts_probe() creates it
and nvt_ts_shutdown() does destroy it.  After remove frees ts, the still-running
event workqueue dereferences the freed struct -> use-after-free, which is the
oops we hit on every unbind (and it makes driver reload testing impossible).

Also make free_irq conditional so a partially-probed device can be removed.
"""
import os
import sys

P = os.path.expanduser(
    '~/kbuild/linux-next-tb128fu-hx83102-panel-port/drivers/input/touchscreen/nt36523_ts.c')
s = open(P, encoding='utf-8').read()

if 'TS331FC fix: destroy event_wq' in s:
    print('already patched')
    sys.exit(0)

# 1) destroy the event workqueue before tearing the rest down
old_fwu = '''#if BOOT_UPDATE_FIRMWARE
	if (nvt_fwu_wq) {
		cancel_delayed_work_sync(&ts->nvt_fwu_work);
		destroy_workqueue(nvt_fwu_wq);
		nvt_fwu_wq = NULL;
	}
#endif

	nvt_irq_enable(false);
	free_irq(client->irq, ts);'''

new_fwu = '''#if BOOT_UPDATE_FIRMWARE
	if (nvt_fwu_wq) {
		cancel_delayed_work_sync(&ts->nvt_fwu_work);
		destroy_workqueue(nvt_fwu_wq);
		nvt_fwu_wq = NULL;
	}
#endif

	/* TB331FC fix: destroy event_wq here too - probe creates it and shutdown
	 * destroys it, but remove never did, so its worker kept running with a
	 * freed ts after kfree(ts) below. */
	if (ts->event_wq) {
		destroy_workqueue(ts->event_wq);
		ts->event_wq = NULL;
	}

	if (client->irq > 0) {
		nvt_irq_enable(false);
		free_irq(client->irq, ts);
		client->irq = 0;
	}'''

if old_fwu not in s:
    sys.exit('remove anchor not found')
s = s.replace(old_fwu, new_fwu, 1)

open(P, 'w', encoding='utf-8', newline='\n').write(s)
print('patched: remove() destroys event_wq and frees the IRQ conditionally')
