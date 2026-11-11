#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Execute production power-off with shared suppliers held, and retry failures."""
import pathlib
import subprocess
import tempfile

source = pathlib.Path(__file__).with_name("apple.c").read_text()
a = source.index("static int apple_cio_power_off(")
b = source.index("\nstatic void apple_cio_stop(", a)
code = r"""
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#define min(a,b) ((a)<(b)?(a):(b))
#define dev_err(...) ((void)0)
#define dev_dbg(...) ((void)0)
struct device { int id; };
struct dev_pm_domain_list { unsigned int num_pds; struct device **pd_devs; void **pd_links; };
struct apple_cio { void *hw, *dev; struct dev_pm_domain_list *pd_list; bool *pd_owned; bool reset_pending; };
static int apple_cio_t6050_hw;
static unsigned int held, checked;
static void device_link_del(void *p) {}
static void dev_pm_syscore_device(struct device *d, bool b) {}
static void dev_pm_genpd_synced_poweroff(struct device *d) {}
static int pm_runtime_put_sync_suspend(struct device *d) { return 0; }
static void pm_runtime_get_noresume(struct device *d) {}
static int apple_pmgr_verify_off(struct device *d) {
 checked |= 1U << d->id;
 return held & (1U << d->id) ? -11 : 0;
}
""" + source[a:b] + r"""
int main(void) {
 struct device d[5], *pd[5]; void *links[5] = {0}; bool owned[5];
 struct dev_pm_domain_list list = {5, pd, links};
 struct apple_cio a = {&apple_cio_t6050_hw, NULL, &list, owned, false};
 for (int i = 0; i < 5; i++) { d[i].id = i; pd[i] = &d[i]; }
 for (held = 0; held < 32; held++) {
  checked = 0;
  for (int i = 0; i < 5; i++) owned[i] = true;
  int ret = apple_cio_power_off(&a);
  assert(checked == 14);
  assert(!!ret == !!(held & 14));
  assert(a.reset_pending == !!ret);
  for (int i = 0; i < 5; i++) assert(!owned[i]);
 }
 held = 2; assert(apple_cio_power_off(&a) == -11);
 held = 17; assert(apple_cio_power_off(&a) == 0);
 assert(!a.reset_pending);
 return 0;
}
"""
with tempfile.TemporaryDirectory() as tmp:
    c = pathlib.Path(tmp) / "test.c"
    c.write_text(code)
    subprocess.run(["cc", "-o", tmp + "/test", str(c)], check=True)
    subprocess.run([tmp + "/test"], check=True)
print("PASS: 32 supplier combinations and failed-boundary retry (34 cases)")
