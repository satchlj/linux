#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Execute the production mux registration with both board and combo choices."""
from pathlib import Path
import subprocess,tempfile
p=Path(__file__).parent
s=(p/'atc-t6050-dp.c').read_text();a=s.index('static int t6050_typec_register(');b=s.index('\nstatic int t6050_dp_probe(',a)
code=s[a:b]
pre=r'''
#include <stdbool.h>
#include <assert.h>
#include <string.h>
struct t6050_dp {void *dev;bool combo;};
struct typec_switch_dev {int x;}; struct typec_mux_dev {int x;};
struct typec_switch_desc {void *fwnode,*drvdata,*set;};
struct typec_mux_desc {void *fwnode,*drvdata,*set;bool safe_after_role;};
static bool j775c, observed;
static void t6050_typec_orientation(void) {}
static void t6050_typec_mode(void) {}
static void t6050_typec_switch_release(void *p) {}
static void t6050_typec_mux_release(void *p) {}
static void *dev_fwnode(void *p) {return p;}
static bool of_machine_is_compatible(const char *s) {return j775c;}
static struct typec_switch_dev *typec_switch_register(void *p,struct typec_switch_desc *d) {static struct typec_switch_dev sw;return &sw;}
static struct typec_mux_dev *typec_mux_register(void *p,struct typec_mux_desc *d) {static struct typec_mux_dev mux;observed=d->safe_after_role;return &mux;}
static int devm_add_action_or_reset(void *d,void (*f)(void*),void *p) {return 0;}
#define IS_ERR(p) false
#define PTR_ERR(p) (-1)
'''
post=r'''
int main(void) {
 for(int board=0;board<2;board++) for(int combo=0;combo<2;combo++) {
  struct t6050_dp dp={.combo=combo};j775c=board;
  assert(t6050_typec_register(&dp)==0);
  assert(observed==(board&&combo));
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 f=Path(d)/'test.c';exe=Path(d)/'test';f.write_text(pre+code+post)
 subprocess.run(['cc','-std=gnu11',str(f),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
 f.write_text(pre+code.replace('dp->combo && of_machine_is_compatible("apple,j775c")','false')+post)
 subprocess.run(['cc','-std=gnu11',str(f),'-o',str(exe)],check=True)
 assert subprocess.run([str(exe)],capture_output=True).returncode!=0
print('PASS 4 production role-policy cases; missing-policy mutation rejected')
