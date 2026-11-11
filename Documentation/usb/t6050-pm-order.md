# T6050 USB4 teardown and restore check

This branch contains synchronous PM/cold-off changes and teardown-order logging.
It has no board key, DISC recovery, device-tree enablement or throughput tuning.
Role-before-SAFE, XDomain unregister and TX quiescence already exist in integration.

Enable dynamic debug before a stop/start or sleep test (as root):

```sh
mount -t debugfs none /sys/kernel/debug # if not mounted already
printf '%s\n' 'file drivers/thunderbolt/apple.c +p' \
 'file drivers/thunderbolt/domain.c +p' \
 'file drivers/usb/typec/tipd/core.c +p' \
 'file drivers/phy/apple/atc-t6050* +p' \
 'file drivers/pmdomain/apple/pmgr-pwrstate.c +p' \
 > /sys/kernel/debug/dynamic_debug/control
dmesg -w | grep -E 'USB4 (teardown|restore):|hardware off confirmed|reset boundary'
```

For a session which actually goes OFF, inspect per-controller timestamps:

```text
USB4 teardown: XDomains unregistered
USB4 teardown: children removed
PS <domain>: hardware off confirmed target=0 actual=0 raw=<value>
CIO domains synchronously off; reset boundary established
USB4 teardown: USB role NONE
USB4 teardown: PHY part B complete
USB4 teardown: SAFE complete
USB4 restore: domains on
USB4 restore: NHI ready
```

The XDomain line precedes child removal even with no host peer. A dock alone
cannot prove thunderbolt-net teardown. Role NONE is logged only when changing an
active USB role; firmware-owned/no-op roles need not produce that line. The PHY
part B line is emitted inside SAFE, before SAFE completion. Domain lines repeat
for each domain. First attach has no preceding teardown. Existing sleep policy
remains opt-in (`thunderbolt_apple.s2idle_teardown=Y`); establish an unchanged daily
baseline first. No hardware success is claimed for this branch.
