#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Execute the production PD helper and retry admission with mocked transport."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
s = (ROOT / 'drivers/usb/typec/tipd/core.c').read_text()
f = s[s.index('static int cd321x_reset_inherited_connection('):]
f = f[:f.index('\n}\n') + 3]
base = r'''
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <assert.h>
#include <errno.h>
typedef uint8_t u8;
typedef uint32_t u32;
struct tps6598x { void *dev; bool dbma_at_probe; u32 status; };
static const char *board;
static bool property = true, chip = true;
static unsigned long jiffies;
static int commands, reads, unlocks, disconnects, relocks;
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define TPS_STATUS_PLUG_PRESENT 1
#define TPS_STATUS_TO_TYPEC_DATAROLE(s) (!!((s)&2))
#define TPS_MODE_APP 1
#define TPS_MODE_APP1 2
#define msecs_to_jiffies(x) (x)
#define TPS_REG_CMD1 8
#define time_after_eq(a,b) ((long)((a)-(b))>=0)
static int tps6598x_read32(struct tps6598x *t, int reg, u32 *v) { *v=0; return 0; }
#define time_before(a,b) ((long)((a)-(b))<0)
#define dev_info(...) ((void)0)
static void msleep(int n) { jiffies += n; }
static bool of_machine_is_compatible(const char *s) { return !strcmp(s, board); }
static bool device_property_read_bool(void *d, const char *p) { return property; }
static bool device_is_compatible(void *d, const char *s) { return chip; }
static int tps6598x_check_mode(struct tps6598x *t) { return TPS_MODE_APP; }
static bool tps6598x_read_status(struct tps6598x *t, u32 *s) { reads++; *s=3; return true; }
static int tps6598x_exec_cmd_tmo(struct tps6598x *t, const char *c,
 size_t il, const u8 *in, size_t ol, u8 *out, unsigned int timeout, unsigned int delay) {
 commands++;
 if (!strcmp(c,"LOCK") && in[0]) {
  assert(commands == 1 && il == 4);
  assert(!memcmp(in, !strcmp(board,"apple,j716c") ? "617J" : "577J",4));
  unlocks++; if (out) *out=0;
 } else if (!strcmp(c,"DISC")) {
  assert(commands==2 && il==1 && in[0]==5 && timeout==5000);
  disconnects++;
 } else {
  assert(commands==3 && il==4 && !in[0] && !in[1] && !in[2] && !in[3]);
  relocks++;
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
 const char *boards[]={"apple,j716c","apple,j775c","apple,unknown"};
 for (unsigned int b=0;b<3;b++) for (int recovery=0;recovery<2;recovery++)
 for (int prop=0;prop<2;prop++) for (int dbma=0;dbma<2;dbma++)
 for (int connected=0;connected<2;connected++) for (int host=0;host<2;host++) {
  u32 status=connected | (host<<1);
  board=boards[b]; property=prop; t.dbma_at_probe=dbma;
  commands=reads=unlocks=disconnects=relocks=0; jiffies=0;
  assert(cd321x_reset_inherited_connection(&t,&status,recovery)==0);
  bool expected=b<2 && (recovery || prop) && !dbma && connected && (recovery || host);
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
 printf("PASS %u cases\n",cases);
}
'''
header = (ROOT / 'drivers/thunderbolt/apple-recovery.h').read_text()
with tempfile.TemporaryDirectory(prefix='t6050-recovery-') as d:
    src = Path(d) / 'test.c'
    binary = Path(d) / 'test'
    src.write_text(base + header + f + main)
    subprocess.run([os.environ.get('HOSTCC', 'cc'), '-std=gnu11', '-O2',
                    str(src), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
    for bad in [f.replace("'6', '1', '7', 'J'", "'5', '7', '7', 'J'"),
                f.replace('!key ||', 'false ||')]:
        src.write_text(base + header + bad + main)
        subprocess.run([os.environ.get('HOSTCC', 'cc'), '-std=gnu11', '-O2',
                        str(src), '-o', str(binary)], check=True)
        assert subprocess.run([str(binary)], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode != 0
print('PASS 2 rejected mutations')
