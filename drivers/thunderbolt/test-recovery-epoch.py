#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compile the production stop admission block; exercise completed/failed epochs."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent
s=(root/'apple.c').read_text();start=s.index('static void apple_cio_stop(struct apple_cio *acio)\n{');end=s.index('\tapple_cio_remove_children(acio);',start)
stop=s[start:end]+'}\n'
pre=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdint.h>
typedef uint64_t u64;
#include "apple-recovery.h"
#define WRITE_ONCE(x,y) ((x)=(y))
#define lockdep_assert_held(x) ((void)0)
#define dev_dbg(...) ((void)0)
static bool j775c, peer;
static u64 activity;
struct apple_cio {int lock,current_cable_info,reset_pending,dev; unsigned link_lost_cycles; u64 link_lost_cycle_activity;};
static bool of_machine_is_compatible(const char *s) {return j775c;}
static void apple_cio_power_off(struct apple_cio *a) {}
static bool apple_cio_has_peer(struct apple_cio *a,u64 *out) {*out=activity;return peer;}
'''
post=r'''
int main(void) {
 struct apple_cio a={.current_cable_info=1};
 unsigned checks=0;
 for (int board=0;board<2;board++) for (int seen=0;seen<2;seen++) for (int active=0;active<2;active++) for(unsigned cycles=0;cycles<=3;cycles++) {
  j775c=board;peer=seen;activity=active;a.link_lost_cycles=cycles;a.link_lost_cycle_activity=7;
  apple_cio_stop(&a);
  assert(a.link_lost_cycles==((board&&seen&&active)?0:cycles));
  assert(a.link_lost_cycle_activity==((board&&seen&&active)?0:7));checks++;
 }
 j775c=true;peer=true;activity=1;
 for(int session=0;session<10;session++) {
  assert(apple_cio_recovery_action(a.link_lost_cycles,false,false,true));
  a.link_lost_cycles=2;apple_cio_stop(&a);assert(a.link_lost_cycles==0);checks++;
 }
 peer=false;activity=0;
 for(unsigned cycle=0;cycle<3;cycle++) {
  a.link_lost_cycles=cycle;apple_cio_stop(&a);assert(a.link_lost_cycles==cycle);checks++;
 }
 a.link_lost_cycles=3;apple_cio_stop(&a);assert(apple_cio_recovery_action(a.link_lost_cycles,false,false,true)==0);checks++;
 printf("%u production epoch cases passed\n",checks);return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 f=Path(d)/'test.c';binary=Path(d)/'test';f.write_text(pre+stop+post)
 subprocess.run(['cc','-std=gnu11','-I',str(root),str(f),'-o',str(binary)],check=True)
 subprocess.run([str(binary)],check=True)
 # The old code must fail the ten completed-session regression.
 f.write_text(pre+stop.replace('WRITE_ONCE(acio->link_lost_cycles, 0);',';')+post)
 subprocess.run(['cc','-std=gnu11','-I',str(root),str(f),'-o',str(binary)],check=True)
 assert subprocess.run([str(binary)],capture_output=True).returncode!=0
 print('stale-budget mutation rejected')
