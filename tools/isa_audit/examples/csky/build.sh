#!/bin/sh
# Build `cskydis`, the binutils-backed C-SKY V2 decoder used as the reference
# disassembler in the ISA audit.  Needs a binutils source tree configured for
# --target=csky-elf; everything here is offline once that exists.
#
#   curl -O https://ftp.gnu.org/gnu/binutils/binutils-2.47.tar.xz
#   tar xf binutils-2.47.tar.xz && mkdir build && cd build
#   ../binutils-2.47/configure --target=csky-elf --disable-nls --disable-gdb \
#       --disable-gdbserver --disable-sim --disable-werror --disable-gprofng
#   make -j8 all-binutils all-opcodes
#
# then:  ./build.sh <binutils-src-dir> <binutils-build-dir> [outfile]
set -e
S="$1"; B="$2"; OUT="${3:-./cskydis}"
[ -n "$S" ] && [ -n "$B" ] || { echo "usage: $0 <binutils-src> <binutils-build> [out]"; exit 2; }
cc -O2 -o "$OUT" "$(dirname "$0")/cskydis.c" \
  -I"$S/include" -I"$S/bfd" -I"$B/bfd" -I"$S/binutils" -I"$B" -I"$S/opcodes" \
  "$B/opcodes/.libs/libopcodes.a" "$B/bfd/.libs/libbfd.a" \
  "$B/libiberty/libiberty.a" "$B/libsframe/.libs/libsframe.a" "$B/zlib/libz.a" \
  -L/opt/homebrew/opt/zstd/lib -lzstd
echo "built $OUT"
