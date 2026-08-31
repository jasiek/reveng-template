/* Decode C-SKY V2 instructions at arbitrary addresses using binutils libopcodes.
   usage: cskydis <raw.bin> <base_vma_hex>   ; addresses (hex, one per line) on stdin
   prints: <addr> <len> <text>   (len 0 = undecodable) */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include "sysdep.h"
#include "bfd.h"
#include "dis-asm.h"
extern int print_insn_csky (bfd_vma, struct disassemble_info *);

static unsigned char *buf; static long buflen; static unsigned long base;
static char out[512]; static int outn;

static int rd(bfd_vma memaddr, bfd_byte *b, unsigned int len, struct disassemble_info *info){
  (void)info;
  if (memaddr < base || memaddr + len > base + (unsigned long)buflen) return -1;
  memcpy(b, buf + (memaddr - base), len); return 0;
}
static void merr(int st, bfd_vma a, struct disassemble_info *i){(void)st;(void)a;(void)i;}
static void paddr(bfd_vma a, struct disassemble_info *i){(void)a;(void)i;}
static int pr(void *s, const char *fmt, ...){
  (void)s; va_list ap; va_start(ap, fmt);
  int n = vsnprintf(out + outn, sizeof(out) - outn, fmt, ap); va_end(ap);
  if (n > 0) outn += n; return n;
}
static int prs(void *s, enum disassembler_style st, const char *fmt, ...){
  (void)s;(void)st; va_list ap; va_start(ap, fmt);
  int n = vsnprintf(out + outn, sizeof(out) - outn, fmt, ap); va_end(ap);
  if (n > 0) outn += n; return n;
}

int main(int argc, char **argv){
  if (argc < 3) { fprintf(stderr, "usage: cskydis raw.bin base_hex\n"); return 2; }
  FILE *f = fopen(argv[1], "rb"); if(!f){perror("open");return 2;}
  fseek(f,0,SEEK_END); buflen = ftell(f); fseek(f,0,SEEK_SET);
  buf = malloc(buflen); if (fread(buf,1,buflen,f) != (size_t)buflen) return 2; fclose(f);
  base = strtoul(argv[2], NULL, 16);

  struct disassemble_info info;
  init_disassemble_info(&info, NULL, pr, prs);
  info.arch = bfd_arch_csky;
  info.mach = 0x22000009;          /* CSKY_ABI_V2 | CSKY_VERSION_V2 | CSKY_ARCH_803 */
  info.endian = BFD_ENDIAN_LITTLE;
  info.read_memory_func = rd;
  info.memory_error_func = merr;
  info.print_address_func = paddr;
  info.buffer = NULL; info.buffer_length = 0;
  disassemble_init_for_target(&info);

  char line[64];
  while (fgets(line, sizeof line, stdin)) {
    unsigned long a = strtoul(line, NULL, 16);
    if (!a) continue;
    outn = 0; out[0] = 0;
    int n = print_insn_csky((bfd_vma)a, &info);
    if (n <= 0) printf("%08lx 0 <fail>\n", a);
    else {
      for (char *p = out; *p; p++) if (*p=='\t') *p=' ';
      printf("%08lx %d %s\n", a, n, out);
    }
  }
  return 0;
}
