#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Execute the production PD helper and retry admission with mocked transport."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
s = (ROOT / 'drivers/usb/typec/tipd/core.c').read_text()
f = s[s.index('struct cd321x_disc_key {'):]
f = f[:f.index('\n}\n', f.index('static int cd321x_reset_inherited_connection(')) + 3]
base = r'''
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <assert.h>
#include <errno.h>
typedef uint8_t u8;
typedef uint32_t u32;
struct tps6598x { void *dev; bool dbma_at_probe; u32 status; int lock; bool disc_recovery_active; };
static const char *board;
static bool property = true, chip = true;
static unsigned long jiffies;
static int commands, reads, unlocks, disconnects, relocks;
static int fail_relocks, nak_reads, busy_reads, bad_results, irq_yields;
static bool never_idle, unlocked, idle_seen=true, recovering, slow_unlock;
static struct tps6598x *active;
static void mutex_unlock(int *p) { assert(!unlocked); unlocked=true; }
static void mutex_lock(int *p) { assert(unlocked); unlocked=false; }
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define TPS_STATUS_PLUG_PRESENT 1
#define TPS_STATUS_TO_TYPEC_DATAROLE(s) (!!((s)&2))
#define TPS_MODE_APP 1
#define TPS_MODE_APP1 2
#define msecs_to_jiffies(x) (x)
#define TPS_REG_CMD1 8
#define time_after_eq(a,b) ((long)((a)-(b))>=0)
static int tps6598x_read32(struct tps6598x *t, int reg, u32 *v) {
 if(nak_reads) {nak_reads--;return -EIO;}
 if(never_idle || busy_reads) {if(busy_reads)busy_reads--;*v=1;return 0;}
 *v=0;idle_seen=true;return 0;
}
#define time_before(a,b) ((long)((a)-(b))<0)
#define dev_info(...) ((void)0)
#define dev_dbg(...) ((void)0)
static void msleep(int n) { if(unlocked) {assert(active->disc_recovery_active);irq_yields++;} jiffies += n; }
static bool of_machine_is_compatible(const char *s) { return !strcmp(s, board); }
static bool device_property_read_bool(void *d, const char *p) { return property; }
static bool device_is_compatible(void *d, const char *s) { return chip; }
static int tps6598x_check_mode(struct tps6598x *t) { return TPS_MODE_APP; }
static bool tps6598x_read_status(struct tps6598x *t, u32 *s) { reads++; *s=3; return true; }
static int tps6598x_exec_cmd_tmo(struct tps6598x *t, const char *c,
 size_t il, const u8 *in, size_t ol, u8 *out, unsigned int timeout, unsigned int delay) {
 active=t; assert(!unlocked); commands++;
 if (!strcmp(c,"LOCK") && in[0]) {
  assert(commands == 1 && il == 4);
  assert(!memcmp(in, !strcmp(board,"apple,j716c") ? "617J" : "577J",4));
  assert(timeout==(recovering ? 5000:1000));
  if(slow_unlock) {if(timeout<2000)return -ETIMEDOUT;jiffies+=2000;}
  unlocks++; if (out) *out=0;
 } else if (!strcmp(c,"DISC")) {
  assert(commands==2 && il==1 && in[0]==5 && timeout==5000);
  disconnects++;
 } else {
  assert(commands>=3 && il==4 && !in[0] && !in[1] && !in[2] && !in[3]);
  if(relocks) assert(idle_seen);
  relocks++;
  if(fail_relocks) {fail_relocks--;idle_seen=false;return -EIO;}
  if(out) {*out=bad_results?1:0;if(bad_results)bad_results--;}
 }
 return 0;
}
static int tps6598x_exec_cmd(struct tps6598x *t, const char *c,
 size_t il, const u8 *in, size_t ol, u8 *out) {
 return tps6598x_exec_cmd_tmo(t,c,il,in,ol,out,1000,0);
}
'''
main = r'''
int main(void) {
 struct tps6598x t={0};
 unsigned int cases=0;
 board="apple,j775c"; recovering=true;
 u32 st=3;
 commands=reads=unlocks=disconnects=relocks=irq_yields=0;
 fail_relocks=1;nak_reads=2;busy_reads=2;idle_seen=true;
 assert(cd321x_reset_inherited_connection(&t,&st,true)==0);
 assert(disconnects==1 && relocks==2 && irq_yields>=5 && !unlocked && !t.disc_recovery_active);
 commands=reads=unlocks=disconnects=relocks=irq_yields=0;
 fail_relocks=1;never_idle=true;idle_seen=true;jiffies=0;
 assert(cd321x_reset_inherited_connection(&t,&st,true)==-EIO);
 assert(disconnects==1 && relocks==1 && jiffies<=20200 && !t.disc_recovery_active && !unlocked);
 never_idle=false;idle_seen=true;
 commands=reads=unlocks=disconnects=relocks=irq_yields=0;
 bad_results=1;jiffies=0;
 assert(cd321x_reset_inherited_connection(&t,&st,true)==0);
 assert(disconnects==1 && relocks==2 && !t.disc_recovery_active && !unlocked);
 puts("PASS 3 recovery transport/busy/result cases (single DISC, bounded, IRQ service)");
 commands=reads=unlocks=disconnects=relocks=irq_yields=0;idle_seen=true;jiffies=0;slow_unlock=true;
 assert(cd321x_reset_inherited_connection(&t,&st,true)==0);
 assert(unlocks==1 && disconnects==1 && relocks==1 && jiffies==7100);
 slow_unlock=false;
 puts("PASS delayed-unlock recovery budget case");
 const char *boards[]={"apple,j716c","apple,j775c","apple,unknown"};
 for (unsigned int b=0;b<3;b++) for (int recovery=0;recovery<2;recovery++)
 for (int prop=0;prop<2;prop++) for (int dbma=0;dbma<2;dbma++)
 for (int connected=0;connected<2;connected++) for (int host=0;host<2;host++) {
  u32 status=connected | (host<<1);
  recovering=recovery; board=boards[b]; property=prop; t.dbma_at_probe=dbma;
  commands=reads=unlocks=disconnects=relocks=0; jiffies=0;
  assert(cd321x_reset_inherited_connection(&t,&status,recovery)==0);
  bool expected=b<2 && (!recovery || b==1) && (recovery || prop) && !dbma && connected && (recovery || host);
  assert(!t.disc_recovery_active && !unlocked);
  assert(commands==(expected ? 3:0));
  if (expected) assert(unlocks==1 && disconnects==1 && relocks==1 && reads==1 && jiffies==5100);
  cases++;
 }
 for (unsigned int c=0;c<10;c++) for (int blocked=0;blocked<2;blocked++)
 for (int peer=0;peer<2;peer++) for (int t6050=0;t6050<2;t6050++) {
  unsigned int a=apple_cio_recovery_action(c,blocked,peer,t6050);
  assert(a==((blocked || peer || c>=3) ? 0 : (t6050 && c ? 2:1)));
  cases++;
 }
 for (unsigned int a=0;a<4;a++) for (unsigned int p=0;p<4;p++) {
  assert(apple_cio_recovery_progress(a,p)==(a && a!=p)); cases++;
 }
 for (unsigned int n=0;n<3;n++) {
  /* Peer appears after cycle N was admitted, before PD executes DISC. */
  assert(apple_cio_recovery_action(n,false,true,true)==0);
  cases++;
 }
 board="apple,j716c"; assert(!cd321x_disc_recovery_enabled()); cases++;
 board="apple,j775c"; assert(cd321x_disc_recovery_enabled()); cases++;
 printf("PASS %u cases\n",cases);
}
'''
header = (ROOT / 'drivers/thunderbolt/apple-recovery.h').read_text()
router = (ROOT / 'drivers/thunderbolt/apple.c').read_text()
check = router[router.index('\tif (data->state == TYPEC_THUNDERBOLT_SWITCH_CHECK_RECOVERY) {'):]
check = check[:check.index('\n\tswitch (data->state)')]
late = r'''
typedef uint64_t u64;
#define APPLE_CIO_SLEEP_OPEN 0
#define TYPEC_THUNDERBOLT_SWITCH_CHECK_RECOVERY 9
struct apple_cio { bool removing, recovering, sleep_restart_owed;
 int sleep_phase, current_cable_info, target_cable_info; bool peer; };
struct check_data { int state; };
static bool apple_cio_recovering(struct apple_cio *a) { return a->recovering; }
static bool apple_cio_has_peer(struct apple_cio *a, u64 *activity) { return a->peer; }
static int check_peer(struct apple_cio *acio, struct check_data *data) {
''' + check + r'''
 return -EINVAL;
}
static void late_peer_cases(void) {
 struct apple_cio a = {.current_cable_info=1, .target_cable_info=1};
 struct check_data d = {TYPEC_THUNDERBOLT_SWITCH_CHECK_RECOVERY};
 for (unsigned int n=0;n<3;n++) {
  a.peer=false;
  assert(apple_cio_recovery_action(n,false,false,true)==(n ? 2:1));
  assert(check_peer(&a,&d)==-ENOLINK);
  /* PD work was queued; the peer arrives before the final live check. */
  a.peer=true;
  assert(check_peer(&a,&d)==0);
 }
 puts("PASS 3 production late-peer recheck cases");
}
'''
connect = s[s.index('static int cd321x_connect('):]
connect = connect[:connect.index('\n\t/* Keep every local role')]
connect = connect.replace('struct cd321x *cd321x = container_of(tps, struct cd321x, tps);','') + '\n return 1;\n}\n'
base += connect
main = main.replace(' struct tps6598x t={0};', ' struct tps6598x t={0}; t.disc_recovery_active=true; assert(cd321x_connect(&t,3)==0); t.disc_recovery_active=false; assert(cd321x_connect(&t,3)==1);')
main = main.replace(' struct tps6598x t={0};', ' late_peer_cases();\n struct tps6598x t={0};')
with tempfile.TemporaryDirectory(prefix='t6050-recovery-') as d:
    src = Path(d) / 'test.c'
    binary = Path(d) / 'test'
    src.write_text(base + header + f + late + main)
    subprocess.run([os.environ.get('HOSTCC', 'cc'), '-std=gnu11', '-O2',
                    str(src), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
    for bad in [f.replace("'6', '1', '7', 'J'", "'5', '7', '7', 'J'"),
                f.replace('!key ||', 'false ||')]:
        src.write_text(base + header + bad + late + main)
        subprocess.run([os.environ.get('HOSTCC', 'cc'), '-std=gnu11', '-O2',
                        str(src), '-o', str(binary)], check=True)
        assert subprocess.run([str(binary)], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode != 0
print('PASS 2 rejected mutations')
