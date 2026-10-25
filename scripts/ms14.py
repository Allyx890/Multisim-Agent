"""Multisim .ms14 <-> XML (pure Python, no dependencies).

Layout (first documented by barncastle's MultiSimConverter.cs gist):
  "MSMCompressedElectronicsWorkbenchXML" (36 bytes)
  u32 total uncompressed length, u32 0
  blocks: u32 length, u32 compressed length, PKWARE DCL "implode" data
The DCL decoder is a Python port of blast.c by Mark Adler (zlib/contrib/blast,
Copyright (C) 2003, 2012, 2013 Mark Adler, zlib license; full notice in ../LICENSE).
This Python port is an altered version. The encoder is an original greedy LZ77.

Usage:
  python ms14.py x FILE.ms14 [OUT.xml]     unpack
  python ms14.py c FILE.xml  [OUT.ms14]    pack
"""
import struct
import sys

SIG = b"MSMCompressedElectronicsWorkbenchXML"
MAXBITS = 13
BLOCK = 900000

LITLEN = [11, 124, 8, 7, 28, 7, 188, 13, 76, 4, 10, 8, 12, 10, 12, 10, 8, 23, 8,
          9, 7, 6, 7, 8, 7, 6, 55, 8, 23, 24, 12, 11, 7, 9, 11, 12, 6, 7, 22, 5,
          7, 24, 6, 11, 9, 6, 7, 22, 7, 11, 38, 7, 9, 8, 25, 11, 8, 11, 9, 12,
          8, 12, 5, 38, 5, 38, 5, 11, 7, 5, 6, 21, 6, 10, 53, 8, 7, 24, 10, 27,
          44, 253, 253, 253, 252, 252, 252, 13, 12, 45, 12, 45, 12, 61, 12, 45,
          44, 173]
LENLEN = [2, 35, 36, 53, 38, 23]
DISTLEN = [2, 20, 53, 230, 247, 151, 248]
BASE = [3, 2, 4, 5, 6, 7, 8, 9, 10, 12, 16, 24, 40, 72, 136, 264]
EXTRA = [0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8]


def _lengths(rep):
    out = []
    for b in rep:
        out += [b & 15] * ((b >> 4) + 1)
    return out


def _canon(rep):
    """返回 (解码表 {(len, code): sym}, 编码表 [(code, len)])，code 为 MSB 先、未取反。"""
    lens = _lengths(rep)
    enc = [None] * len(lens)
    dec = {}
    code = 0
    for L in range(1, MAXBITS + 1):
        for sym, l in enumerate(lens):
            if l == L:
                enc[sym] = (code, L)
                dec[(L, code)] = sym
                code += 1
        code <<= 1
    return dec, enc


LIT_DEC, LIT_ENC = _canon(LITLEN)
LEN_DEC, LEN_ENC = _canon(LENLEN)
DIST_DEC, DIST_ENC = _canon(DISTLEN)


class _BitReader:
    def __init__(self, data):
        self.d, self.p, self.buf, self.cnt = data, 0, 0, 0

    def bits(self, n):
        while self.cnt < n:
            if self.p >= len(self.d):
                raise EOFError("compressed data ended early")
            self.buf |= self.d[self.p] << self.cnt
            self.p += 1
            self.cnt += 8
        v = self.buf & ((1 << n) - 1)
        self.buf >>= n
        self.cnt -= n
        return v

    def huff(self, table):
        code = 0
        for L in range(1, MAXBITS + 1):
            code = (code << 1) | (self.bits(1) ^ 1)   # 码字按位取反存储
            s = table.get((L, code))
            if s is not None:
                return s
        raise ValueError("invalid Huffman code")


def explode(data):
    r = _BitReader(data)
    lit = r.bits(8)
    dict_bits = r.bits(8)
    if lit > 1 or not 4 <= dict_bits <= 6:
        raise ValueError(f"bad DCL header lit={lit} dict={dict_bits}")
    out = bytearray()
    while True:
        if r.bits(1):
            sym = r.huff(LEN_DEC)
            ln = BASE[sym] + r.bits(EXTRA[sym])
            if ln == 519:
                break
            sh = 2 if ln == 2 else dict_bits
            dist = (r.huff(DIST_DEC) << sh) + r.bits(sh) + 1
            start = len(out) - dist
            if start < 0:
                raise ValueError("distance beyond decoded data")
            for i in range(ln):
                out.append(out[start + i])
        else:
            out.append(r.huff(LIT_DEC) if lit else r.bits(8))
    return bytes(out), r.p


class _BitWriter:
    def __init__(self):
        self.out, self.buf, self.cnt = bytearray(), 0, 0

    def bits(self, v, n):
        self.buf |= v << self.cnt
        self.cnt += n
        while self.cnt >= 8:
            self.out.append(self.buf & 255)
            self.buf >>= 8
            self.cnt -= 8

    def huff(self, enc):
        code, L = enc
        for i in range(L - 1, -1, -1):
            self.bits(((code >> i) & 1) ^ 1, 1)

    def flush(self):
        if self.cnt:
            self.out.append(self.buf & 255)
        return bytes(self.out)


def _len_sym(ln):
    for s in range(15, -1, -1):
        if s == 0 and ln != 3:
            continue
        if BASE[s] <= ln < BASE[s] + (1 << EXTRA[s]):
            return s
    raise ValueError(ln)


def implode(data, lit=1, dict_bits=6):
    w = _BitWriter()
    w.bits(lit, 8)
    w.bits(dict_bits, 8)
    win = 1 << (6 + dict_bits)
    head = {}
    prev = [0] * len(data)
    n = len(data)

    def insert(i):
        if i + 2 < n:
            k = data[i:i + 3]
            prev[i] = head.get(k, -1)
            head[k] = i

    i = 0
    while i < n:
        best_len, best_d = 0, 0
        if i + 2 < n:
            j = head.get(data[i:i + 3], -1)
            tries = 64
            maxl = min(518, n - i)
            while j >= 0 and i - j <= win and tries:
                if data[j + best_len] == data[i + best_len] if best_len < maxl else False:
                    l = 0
                    while l < maxl and data[j + l] == data[i + l]:
                        l += 1
                    if l > best_len:
                        best_len, best_d = l, i - j
                        if l == maxl:
                            break
                j = prev[j]
                tries -= 1
        # 长度 2 的匹配：距离 ≤ 256
        if best_len < 3 and i + 1 < n:
            best_len = 0
            lo = max(0, i - 256)
            k = data.rfind(data[i:i + 2], lo, i + 1)
            if 0 <= k < i:
                best_len, best_d = 2, i - k
        if best_len >= 2:
            w.bits(1, 1)
            s = _len_sym(best_len)
            w.huff(LEN_ENC[s])
            w.bits(best_len - BASE[s], EXTRA[s])
            d = best_d - 1
            sh = 2 if best_len == 2 else dict_bits
            w.huff(DIST_ENC[d >> sh])
            w.bits(d & ((1 << sh) - 1), sh)
            for t in range(i, i + best_len):
                insert(t)
            i += best_len
        else:
            w.bits(0, 1)
            if lit:
                w.huff(LIT_ENC[data[i]])
            else:
                w.bits(data[i], 8)
            insert(i)
            i += 1
    w.bits(1, 1)                       # 结束码：长度 519
    w.huff(LEN_ENC[15])
    w.bits(519 - BASE[15], EXTRA[15])
    return w.flush()


def decompress_ms14(raw):
    if not raw.startswith(SIG):
        raise ValueError("not an MSMCompressedElectronicsWorkbenchXML (.ms14) file")
    p = len(SIG)
    total, _ = struct.unpack_from("<II", raw, p)
    p += 8
    out = bytearray()
    while p < len(raw) and len(out) < total:
        usz, csz = struct.unpack_from("<II", raw, p)
        p += 8
        blk, _ = explode(raw[p:p + csz])
        if len(blk) != usz:
            raise ValueError(f"block length mismatch {len(blk)} != {usz}")
        out += blk
        p += csz
    return bytes(out)


def compress_ms14(xml):
    body = bytearray()
    for k in range(0, len(xml), BLOCK):
        blk = xml[k:k + BLOCK]
        c = implode(blk)
        body += struct.pack("<II", len(blk), len(c)) + c
    return SIG + struct.pack("<II", len(xml), 0) + bytes(body)


if __name__ == "__main__":
    mode, src = sys.argv[1], sys.argv[2]
    data = open(src, "rb").read()
    if mode == "x":
        dst = sys.argv[3] if len(sys.argv) > 3 else src.rsplit(".", 1)[0] + ".xml"
        open(dst, "wb").write(decompress_ms14(data))
    else:
        dst = sys.argv[3] if len(sys.argv) > 3 else src.rsplit(".", 1)[0] + ".ms14"
        open(dst, "wb").write(compress_ms14(data))
    print(dst)
