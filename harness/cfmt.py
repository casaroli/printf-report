"""Reference model of ISO C / POSIX printf, derived from the standard text.

Everything here is computed from first principles with exact rational
arithmetic.  No C library (and not Python's own %-formatting) is used to
produce expected results, so the model can serve as an independent oracle.

The model is parameterised by the target ABI (integer widths, floating
formats, DECIMAL_DIG, locale data reported by the target), because the
correct output of e.g. "%ld" or "%La" depends on it.

Where the standard leaves a choice to the implementation (leading hex digit
of %a, "inf" vs "infinity", NaN payload text, %p text, ...) the oracle does
not produce a single string but a *validator* that accepts every allowed
output.  Floating decimal conversions are checked at three levels:

  req     what the normative text demands ("shall"): correct shape and a
          value rounded "to the appropriate number of digits" (we accept a
          result within one unit of the last printed digit).
  rec     the Recommended Practice of C99 7.19.6.1p13 / C23 7.23.6.1p13:
          correctly rounded up to DECIMAL_DIG significant digits, bounded
          beyond that.  Required by Annex F when __STDC_IEC_559__ is set.
  strict  bit-exact correctly rounded result at every precision (what
          IEEE 754-2008 and C23 F.5 with CR_DECIMAL_DIG == UINTMAX_MAX give).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional, Union

import sys as _sys

if hasattr(_sys, "set_int_max_str_digits"):
    _sys.set_int_max_str_digits(0)  # exact expansions of LDBL_MAX etc. exceed 4300 digits

LEVELS = ("req", "rec", "strict")


# --------------------------------------------------------------------------
# numeric helpers
# --------------------------------------------------------------------------
def floor_log2(x: Fraction) -> int:
    """e such that 2**e <= x < 2**(e+1), x > 0."""
    n, d = x.numerator, x.denominator
    e = n.bit_length() - d.bit_length()
    while Fraction(2) ** e > x:
        e -= 1
    while Fraction(2) ** (e + 1) <= x:
        e += 1
    return e


def floor_log10(x: Fraction) -> int:
    """e such that 10**e <= x < 10**(e+1), x > 0."""
    n, d = x.numerator, x.denominator
    e = len(str(n)) - len(str(d))
    while Fraction(10) ** e > x:
        e -= 1
    while Fraction(10) ** (e + 1) <= x:
        e += 1
    return e


def round_int(q: Fraction, mode: str, neg: bool) -> int:
    """Round the non-negative magnitude q to an integer.

    mode: 'N' nearest/ties-to-even, 'Z' toward zero, 'U' toward +inf,
    'D' toward -inf.  neg tells whether the real value is negative (the
    directed modes act on the signed value)."""
    fl = q.numerator // q.denominator
    if fl == q:
        return fl
    if mode == "N":
        r = q - fl
        if r > Fraction(1, 2) or (r == Fraction(1, 2) and fl % 2 == 1):
            return fl + 1
        return fl
    if mode == "Z":
        return fl
    if mode == "U":
        return fl if neg else fl + 1
    if mode == "D":
        return fl + 1 if neg else fl
    raise ValueError(mode)


def to_bits(v: int, bits: int, signed: bool) -> int:
    v &= (1 << bits) - 1
    if signed and v >= 1 << (bits - 1):
        v -= 1 << bits
    return v


# --------------------------------------------------------------------------
# ABI description (filled from the header the C driver prints)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class FloatFormat:
    mant_dig: int  # p, including the implicit bit
    min_exp: int   # C *_MIN_EXP: smallest normal = 2**(min_exp-1)
    max_exp: int   # C *_MAX_EXP: largest finite < 2**max_exp

    def representable(self, a: Fraction) -> bool:
        a = abs(a)
        if a == 0:
            return True
        if a >= Fraction(2) ** self.max_exp:
            return False
        e = max(floor_log2(a) + 1, self.min_exp)
        return (a / Fraction(2) ** (e - self.mant_dig)).denominator == 1

    def is_normal(self, a: Fraction) -> bool:
        return abs(a) >= Fraction(2) ** (self.min_exp - 1)

    @property
    def max(self) -> Fraction:
        return (1 - Fraction(1, 2 ** self.mant_dig)) * Fraction(2) ** self.max_exp

    @property
    def min_normal(self) -> Fraction:
        return Fraction(2) ** (self.min_exp - 1)

    @property
    def true_min(self) -> Fraction:
        return Fraction(2) ** (self.min_exp - self.mant_dig)

    @property
    def epsilon(self) -> Fraction:
        return Fraction(2) ** (1 - self.mant_dig)


BINARY32 = FloatFormat(24, -125, 128)
BINARY64 = FloatFormat(53, -1021, 1024)
X87 = FloatFormat(64, -16381, 16384)
BINARY128 = FloatFormat(113, -16381, 16384)


@dataclass
class LocaleInfo:
    name: str                 # logical name used by tests (C, utf8, en_US, de_DE)
    actual: Optional[str]     # what setlocale() returned; None = unavailable
    decimal_point: bytes = b"."
    thousands_sep: bytes = b""
    grouping: bytes = b""
    codeset: str = "ANSI_X3.4-1968"
    mb_cur_max: int = 1

    @property
    def utf8(self) -> bool:
        cs = self.codeset.replace("-", "").upper()
        if cs in ("?", ""):
            # codeset unknown (no nl_langinfo, e.g. bare metal / Windows): fall back to the
            # locale name the target accepted and its MB_CUR_MAX
            name = (self.actual or "").replace("-", "").upper()
            return self.mb_cur_max >= 4 and ("UTF8" in name or name.endswith(".65001"))
        return cs == "UTF8"


@dataclass
class Abi:
    bits: dict = field(default_factory=dict)  # 'char','short','int','long','llong',
                                              # 'size','ptrdiff','intmax','ptr','wchar','wint',
                                              # 'least8'.. 'fast64'
    wchar_signed: bool = True
    dbl: FloatFormat = BINARY64
    ldbl: FloatFormat = BINARY64
    decimal_dig: int = 17
    iec559: bool = False          # __STDC_IEC_559__ defined
    nl_argmax: Optional[int] = None
    locales: dict = field(default_factory=dict)  # logical name -> LocaleInfo
    bufsize: int = 1 << 20
    info: dict = field(default_factory=dict)

    def locale(self, name: str) -> Optional[LocaleInfo]:
        li = self.locales.get(name)
        if name == "C" and li is None:
            return LocaleInfo("C", "C")
        return li


# --------------------------------------------------------------------------
# argument values
# --------------------------------------------------------------------------
# Integer types: (oracle width key, signed)
INT_TYPES = {
    "int": ("int", True), "uint": ("int", False),
    "long": ("long", True), "ulong": ("long", False),
    "llong": ("llong", True), "ullong": ("llong", False),
    "intmax": ("intmax", True), "uintmax": ("intmax", False),
    "size": ("size", False), "ssize": ("size", True),
    "ptrdiff": ("ptrdiff", True), "uptrdiff": ("ptrdiff", False),
    "wint": ("wint", False),
}
for _n in (8, 16, 32, 64):
    INT_TYPES[f"int{_n}"] = (f"exact{_n}", True)
    INT_TYPES[f"uint{_n}"] = (f"exact{_n}", False)
    INT_TYPES[f"least{_n}"] = (f"least{_n}", True)
    INT_TYPES[f"uleast{_n}"] = (f"least{_n}", False)
    INT_TYPES[f"fast{_n}"] = (f"fast{_n}", True)
    INT_TYPES[f"ufast{_n}"] = (f"fast{_n}", False)

INT_SYMBOLS = {
    # name -> (width key, kind) ; kind: max/min/umax
    "SCHAR_MAX": ("char", "max"), "SCHAR_MIN": ("char", "min"), "UCHAR_MAX": ("char", "umax"),
    "SHRT_MAX": ("short", "max"), "SHRT_MIN": ("short", "min"), "USHRT_MAX": ("short", "umax"),
    "INT_MAX": ("int", "max"), "INT_MIN": ("int", "min"), "UINT_MAX": ("int", "umax"),
    "LONG_MAX": ("long", "max"), "LONG_MIN": ("long", "min"), "ULONG_MAX": ("long", "umax"),
    "LLONG_MAX": ("llong", "max"), "LLONG_MIN": ("llong", "min"), "ULLONG_MAX": ("llong", "umax"),
    "INTMAX_MAX": ("intmax", "max"), "INTMAX_MIN": ("intmax", "min"), "UINTMAX_MAX": ("intmax", "umax"),
    "SIZE_MAX": ("size", "umax"), "PTRDIFF_MAX": ("ptrdiff", "max"), "PTRDIFF_MIN": ("ptrdiff", "min"),
    "SSIZE_MAX": ("size", "max"),
}
for _n in (8, 16, 32, 64):
    INT_SYMBOLS[f"INT{_n}_MAX"] = (f"exact{_n}", "max")
    INT_SYMBOLS[f"INT{_n}_MIN"] = (f"exact{_n}", "min")
    INT_SYMBOLS[f"UINT{_n}_MAX"] = (f"exact{_n}", "umax")
    INT_SYMBOLS[f"INT_LEAST{_n}_MAX"] = (f"least{_n}", "max")
    INT_SYMBOLS[f"INT_LEAST{_n}_MIN"] = (f"least{_n}", "min")
    INT_SYMBOLS[f"UINT_LEAST{_n}_MAX"] = (f"least{_n}", "umax")
    INT_SYMBOLS[f"INT_FAST{_n}_MAX"] = (f"fast{_n}", "max")
    INT_SYMBOLS[f"INT_FAST{_n}_MIN"] = (f"fast{_n}", "min")
    INT_SYMBOLS[f"UINT_FAST{_n}_MAX"] = (f"fast{_n}", "umax")


def width_of(abi: Abi, key: str) -> int:
    if key.startswith("exact"):
        return int(key[5:])
    return abi.bits[key]


def resolve_int(abi: Abi, v) -> int:
    """v: python int, a symbol name, or (symbol, offset) tuple."""
    if isinstance(v, int):
        return v
    off = 0
    if isinstance(v, tuple):
        v, off = v
    key, kind = INT_SYMBOLS[v]
    b = width_of(abi, key)
    base = {"max": (1 << (b - 1)) - 1, "min": -(1 << (b - 1)), "umax": (1 << b) - 1}[kind]
    return base + off


@dataclass(frozen=True)
class FVal:
    """A floating value: kind 'num' | 'inf' | 'nan'; neg = sign bit.

    For 'num', either mag is an exact Fraction, or sym names a <float.h>
    quantity resolved against the target format ('MAX', 'MIN', 'TRUE_MIN',
    'EPSILON', 'ONE_MINUS_HALF_ULP' ...)."""
    kind: str = "num"
    neg: bool = False
    mag: Optional[Fraction] = None
    sym: Optional[str] = None
    payload: Optional[str] = None  # NaN payload string given to nan()

    def value(self, fmt: FloatFormat) -> Fraction:
        if self.mag is not None:
            return self.mag
        s = self.sym
        if s == "MAX":
            return fmt.max
        if s == "MIN":
            return fmt.min_normal
        if s == "TRUE_MIN":
            return fmt.true_min
        if s == "EPSILON":
            return fmt.epsilon
        if s == "MAX_SUBNORMAL":
            return fmt.min_normal - fmt.true_min
        if s == "ONE_MINUS_ULP":  # nextafter(1, 0)
            return 1 - fmt.epsilon / 2
        if s == "ONE_PLUS_ULP":
            return 1 + fmt.epsilon
        raise ValueError(s)

    def signed(self, fmt: FloatFormat) -> Fraction:
        v = self.value(fmt)
        return -v if self.neg else v


def F(x, neg=None) -> FVal:
    """Convenience constructor: F(1.5), F('0x1.8p3'), F(Fraction(1,3))..."""
    if isinstance(x, FVal):
        return x
    if isinstance(x, str):
        s = x.strip()
        sign = s.startswith("-")
        if s[0] in "+-":
            s = s[1:]
        low = s.lower()
        if low in ("inf", "infinity"):
            return FVal("inf", sign)
        if low.startswith("nan"):
            pl = None
            m = re.fullmatch(r"nan(?:\((.*)\))?", low)
            if m and m.group(1) is not None:
                pl = m.group(1)
            return FVal("nan", sign, payload=pl)
        if low in ("max", "min", "true_min", "epsilon", "max_subnormal", "one_minus_ulp", "one_plus_ulp"):
            return FVal("num", sign, sym=low.upper())
        if low.startswith("0x"):
            m = re.fullmatch(r"0x([0-9a-f]*)(?:\.([0-9a-f]*))?p([-+]?\d+)", low)
            if not m:
                raise ValueError(x)
            ip, fp, e = m.group(1) or "0", m.group(2) or "", int(m.group(3))
            mant = Fraction(int(ip + fp or "0", 16), 16 ** len(fp))
            return FVal("num", sign, mag=mant * Fraction(2) ** e)
        return FVal("num", sign, mag=Fraction(s))  # exact decimal string
    if isinstance(x, float):
        import math
        if math.isinf(x):
            return FVal("inf", x < 0)
        if math.isnan(x):
            return FVal("nan", False)
        sign = math.copysign(1.0, x) < 0
        return FVal("num", sign, mag=abs(Fraction(x)))
    if isinstance(x, (int, Fraction)):
        return FVal("num", x < 0, mag=abs(Fraction(x)))
    raise TypeError(x)


@dataclass(frozen=True)
class NArg:
    """Argument for %n: pointer to an integer of the given C type key."""
    ctype: str  # 'int','schar','short','long','llong','intmax','ssize','ptrdiff','int8'..


# --------------------------------------------------------------------------
# format-string parser
# --------------------------------------------------------------------------
SPEC_RE = re.compile(
    rb"%(?:(?P<pos>[1-9][0-9]*)\$)?"
    rb"(?P<flags>[-+ #0']*)"
    rb"(?P<width>\*(?:[1-9][0-9]*\$)?|[0-9]+)?"
    rb"(?:\.(?P<prec>\*(?:[1-9][0-9]*\$)?|[0-9]*))?"
    rb"(?P<len>hh|h|ll|l|j|z|t|L|wf[1-9][0-9]*|w[1-9][0-9]*|DD|D|H)?"
    rb"(?P<conv>[diouxXbBfFeEgGaAcspnCS%])"
)


@dataclass
class Spec:
    raw: bytes
    pos: Optional[int]
    flags: str
    width: Union[None, int, str]  # int, '*', or '*m$' -> ('*', m)
    prec: Union[None, int, str]
    length: str
    conv: str


def parse_format(fmt: bytes):
    """Split into a list of bytes literals and Spec objects."""
    out, i = [], 0
    lit = bytearray()
    while i < len(fmt):
        c = fmt[i]
        if c != 0x25:
            lit.append(c)
            i += 1
            continue
        m = SPEC_RE.match(fmt, i)
        if not m:
            raise ValueError(f"unparseable conversion at {fmt[i:]!r}")
        if lit:
            out.append(bytes(lit))
            lit = bytearray()

        def wp(s):
            if s is None:
                return None
            s = s.decode()
            if s.startswith("*"):
                return ("*", int(s[1:-1])) if s.endswith("$") else "*"
            return int(s) if s else 0

        out.append(Spec(m.group(0), int(m.group("pos")) if m.group("pos") else None,
                        m.group("flags").decode(), wp(m.group("width")), wp(m.group("prec")),
                        (m.group("len") or b"").decode(), m.group("conv").decode()))
        i = m.end()
    if lit:
        out.append(bytes(lit))
    return out


# --------------------------------------------------------------------------
# expectation objects
# --------------------------------------------------------------------------
class Part:
    """A piece of expected output."""
    canonical: bytes = b""

    def check(self, text: bytes) -> dict:
        raise NotImplementedError

    def regex(self) -> bytes:
        return rb"(.*?)"


class Lit(Part):
    def __init__(self, b: bytes):
        self.canonical = b

    def regex(self):
        return re.escape(self.canonical)


class Choice(Part):
    """One of several exact alternatives (implementation-defined choice)."""
    def __init__(self, options, canonical=None, strict=None, label=""):
        self.options = list(options)
        self.canonical = canonical if canonical is not None else self.options[0]
        self.strict = strict  # subset acceptable at strict level (None = all)
        self.label = label

    def check(self, text):
        ok = text in self.options
        st = ok and (self.strict is None or text in self.strict)
        return {"req": ok, "rec": ok, "strict": st}


class AnyText(Part):
    """Unspecified / implementation-defined text: record only."""
    def __init__(self, canonical=b"<any>", printable=False):
        self.canonical = canonical
        self.printable = printable

    def check(self, text):
        ok = True
        if self.printable:
            ok = len(text) > 0 and all(0x20 <= c < 0x7F for c in text)
        return {"req": ok, "rec": ok, "strict": ok}


@dataclass
class Expect:
    parts: list
    nvals: list = field(default_factory=list)  # expected %n values in order
    ret: Optional[int] = None                  # expected return value (None = len(output))
    na: Optional[str] = None                   # not applicable on this target (reason)

    @property
    def canonical(self) -> bytes:
        return b"".join(p.canonical for p in self.parts)

    def check(self, out: bytes) -> dict:
        res = {lv: True for lv in LEVELS}
        if all(isinstance(p, Lit) for p in self.parts):
            ok = out == self.canonical
            return {lv: ok for lv in LEVELS}
        rx = b"".join(p.regex() for p in self.parts)
        m = re.fullmatch(rx, out, re.S)
        if not m:
            return {lv: False for lv in LEVELS}
        gi = 1
        for p in self.parts:
            if isinstance(p, Lit):
                continue
            r = p.check(m.group(gi))
            gi += 1
            for lv in LEVELS:
                res[lv] = res[lv] and r[lv]
        return res


# --------------------------------------------------------------------------
# field layout
# --------------------------------------------------------------------------
def layout(sign: bytes, prefix: bytes, body: bytes, width: int, flags: str, zero_ok: bool) -> bytes:
    natural = len(sign) + len(prefix) + len(body)
    pad = max(0, width - natural)
    if "-" in flags:
        return sign + prefix + body + b" " * pad
    if "0" in flags and zero_ok:
        return sign + prefix + b"0" * pad + body
    return b" " * pad + sign + prefix + body


def group_digits(digits: bytes, sep: bytes, grouping: bytes) -> bytes:
    """Insert thousands separators per localeconv() grouping rules."""
    if not sep or not grouping:
        return digits
    groups, i = [], len(digits)
    gi, size = 0, None
    while i > 0:
        if gi < len(grouping):
            g = grouping[gi]
            if g == 0:  # repeat previous
                g = size
            else:
                gi += 1
        else:
            g = size
        if g is None or g >= 127 or g <= 0:  # CHAR_MAX: no more grouping
            groups.append(digits[:i])
            i = 0
            break
        size = g
        groups.append(digits[max(0, i - g):i])
        i -= g
    return sep.join(reversed(groups))


# --------------------------------------------------------------------------
# integer conversions
# --------------------------------------------------------------------------
LEN_KEY = {"": "int", "hh": "char", "h": "short", "l": "long", "ll": "llong",
           "j": "intmax", "z": "size", "t": "ptrdiff"}


def int_len_bits(abi: Abi, length: str) -> int:
    if length.startswith("wf"):
        return abi.bits[f"fast{length[2:]}"]
    if length.startswith("w"):
        return int(length[1:])
    return abi.bits[LEN_KEY[length]]


def fmt_int(abi, loc: LocaleInfo, sp: Spec, flags: str, v: int, width, prec) -> bytes:
    conv = sp.conv
    bits = int_len_bits(abi, sp.length)
    signed = conv in "di"
    v = to_bits(v, bits, signed)
    neg = v < 0
    a = -v if neg else v
    base = {"d": 10, "i": 10, "u": 10, "o": 8, "x": 16, "X": 16, "b": 2, "B": 2}[conv]
    if a == 0:
        digits = b"0"
    else:
        ds, n = [], a
        alph = b"0123456789ABCDEF" if conv == "X" else b"0123456789abcdef"
        while n:
            ds.append(alph[n % base])
            n //= base
        digits = bytes(reversed(ds))
    p = 1 if prec is None else prec
    if p == 0 and a == 0:
        digits = b""
    elif len(digits) < p:
        digits = b"0" * (p - len(digits)) + digits
    if "#" in flags and conv == "o" and not digits.startswith(b"0"):
        digits = b"0" + digits
    if "'" in flags and conv in "diu":
        digits = group_digits(digits, loc.thousands_sep, loc.grouping)
    prefix = b""
    if "#" in flags and a != 0:
        prefix = {"x": b"0x", "X": b"0X", "b": b"0b", "B": b"0B"}.get(conv, b"")
    sign = b""
    if signed:
        sign = b"-" if neg else b"+" if "+" in flags else b" " if " " in flags else b""
    return layout(sign, prefix, digits, width, flags, zero_ok=prec is None)


# --------------------------------------------------------------------------
# floating conversions
# --------------------------------------------------------------------------
def dec_fixed(x: Fraction, p: int, mode: str, neg: bool):
    """Correctly rounded fixed notation: returns (intdigits, fracdigits)."""
    n = round_int(x * Fraction(10) ** p, mode, neg)
    s = str(n).rjust(p + 1, "0")
    return (s[:-p] if p else s), (s[-p:] if p else "")


def dec_exp(x: Fraction, p: int, mode: str, neg: bool):
    """Correctly rounded scientific: returns (digits[p+1], exponent)."""
    if x == 0:
        return "0" * (p + 1), 0
    e = floor_log10(x)
    n = round_int(x / Fraction(10) ** (e - p), mode, neg)
    if n >= 10 ** (p + 1):
        n //= 10
        e += 1
    return str(n), e


def exp_str(e: int, mindigits: int) -> str:
    return ("-" if e < 0 else "+") + str(abs(e)).rjust(mindigits, "0")


def float_sign(neg: bool, flags: str) -> bytes:
    return b"-" if neg else b"+" if "+" in flags else b" " if " " in flags else b""


def fmt_dec_exact(conv, flags, prec, x: Fraction, neg: bool, mode, radix: bytes, loc) -> bytes:
    """Body (no sign/padding) of the correctly rounded e/f/g conversion."""
    up = conv.isupper()
    c = conv.lower()
    alt = "#" in flags
    if c == "f":
        p = 6 if prec is None else prec
        ip, fp = dec_fixed(x, p, mode, neg)
        ipb = ip.encode()
        if "'" in flags:
            ipb = group_digits(ipb, loc.thousands_sep, loc.grouping)
        return ipb + (radix + fp.encode() if (p > 0 or alt) else b"")
    if c == "e":
        p = 6 if prec is None else prec
        ds, e = dec_exp(x, p, mode, neg)
        body = ds[0] + ("." + ds[1:] if (p > 0 or alt) else "") + ("E" if up else "e") + exp_str(e, 2)
        return body.encode().replace(b".", radix)
    if c == "g":
        P = 6 if prec is None else (1 if prec == 0 else prec)
        _, X = dec_exp(x, P - 1, mode, neg)
        if P > X >= -4:
            ip, fp = dec_fixed(x, P - (X + 1), mode, neg)
            if not alt:
                fp = fp.rstrip("0")
            ipb = ip.encode()
            if "'" in flags:
                ipb = group_digits(ipb, loc.thousands_sep, loc.grouping)
            return ipb + (radix + fp.encode() if (fp or alt) else b"")
        ds, e = dec_exp(x, P - 1, mode, neg)
        fp = ds[1:]
        if not alt:
            fp = fp.rstrip("0")
        body = ds[0] + ("." + fp if (fp or alt) else "") + ("E" if up else "e") + exp_str(e, 2)
        return body.encode().replace(b".", radix)
    raise ValueError(conv)


def sig_digits(conv: str, prec, x: Fraction) -> int:
    c = conv.lower()
    if c == "e":
        return (6 if prec is None else prec) + 1
    if c == "g":
        return 6 if prec is None else (1 if prec == 0 else prec)
    p = 6 if prec is None else prec
    if x == 0:
        return p + 1
    return floor_log10(x) + 1 + p


def round_sig(x: Fraction, M: int, mode: str, neg: bool) -> Fraction:
    if x == 0:
        return x
    e = floor_log10(x)
    scale = Fraction(10) ** (e - M + 1)
    return round_int(x / scale, mode, neg) * scale


class FloatDec(Part):
    """Validator for e/E/f/F/g/G of a finite value."""

    def __init__(self, sp, flags, width, prec, x: Fraction, neg, mode, abi: Abi, loc: LocaleInfo,
                 fmt: FloatFormat = BINARY64):
        self.sp, self.flags, self.width, self.prec = sp, flags, width, prec
        self.fmt = fmt
        self.x, self.neg, self.mode, self.abi, self.loc = x, neg, mode, abi, loc
        self.radix = loc.decimal_point
        body = fmt_dec_exact(sp.conv, flags, prec, x, neg, mode, self.radix, loc)
        self.canonical = layout(float_sign(neg, flags), b"", body, width, flags, zero_ok=True)

    def _parse(self, text: bytes):
        """Parse a candidate field.

        Returns (style, value, intdigits, fracdigits, has_radix, exp) or None
        if the text is malformed (bad padding, sign, digits, exponent form)."""
        conv = self.sp.conv
        c, up = conv.lower(), conv.isupper()
        R = re.escape(self.radix)
        sign = re.escape(float_sign(self.neg, self.flags))
        E = b"E" if up else b"e"
        fbody = rb"(?P<i>[0-9]+)(?:(?P<r>" + R + rb")(?P<f>[0-9]*))?"
        ebody = (rb"(?P<i>[0-9])(?:(?P<r>" + R + rb")(?P<f>[0-9]*))?" + E +
                 rb"(?P<es>[-+])(?P<ed>[0-9]+)")
        bodies = {"f": [("f", fbody)], "e": [("e", ebody)], "g": [("e", ebody), ("f", fbody)]}[c]
        for style, body in bodies:
            z = rb"(?P<z>0*)" if style == "e" else rb"(?P<z>)"
            rx = rb"(?P<lead> *)" + sign + z + body + rb"(?P<trail> *)"
            m = re.fullmatch(rx, text)
            if m:
                break
        else:
            return None
        lead, trail, ip = m.group("lead"), m.group("trail"), m.group("z") + m.group("i")
        padded = bool(lead or trail or (len(ip) > 1 and ip.startswith(b"0")))
        if padded and len(text) != self.width:
            return None
        if len(text) < self.width:
            return None
        if "-" in self.flags:
            if lead or (len(ip) > 1 and ip.startswith(b"0")):
                return None
        elif "0" in self.flags:
            if lead or trail:
                return None
        else:
            if trail or (len(ip) > 1 and ip.startswith(b"0")):
                return None
        fp = m.group("f") or b""
        has_r = m.group("r") is not None
        ipn = ip.lstrip(b"0") or b"0"
        val = Fraction(int(ipn + fp), 10 ** len(fp))
        ex = None
        if style == "e":
            ed = m.group("ed")
            if len(ed) < 2 or (len(ed) > 2 and ed.startswith(b"0")):
                return None
            ex = int(ed) * (-1 if m.group("es") == b"-" else 1)
            val *= Fraction(10) ** ex
        return (style, val, ipn, fp, has_r, ex)

    def check(self, text: bytes) -> dict:
        strict = text == self.canonical
        if "'" in self.flags and self.loc.thousands_sep:
            return {"req": strict, "rec": strict, "strict": strict}
        r = self._parse(text)
        bad = {"req": False, "rec": False, "strict": False}
        if r is None:
            return bad
        style, D, ip, fp, has_r, ex = r
        conv, prec, alt = self.sp.conv.lower(), self.prec, "#" in self.flags
        x = self.x
        # ---- shape -------------------------------------------------------
        if conv in "fe":
            p = 6 if prec is None else prec
            if len(fp) != p or has_r != (p > 0 or alt):
                return bad
            if conv == "e" and ((D != 0 and ip == b"0") or (D == 0 and ex != 0)):
                return bad
        else:
            P = 6 if prec is None else (1 if prec == 0 else prec)
            X = 0 if D == 0 else (ex if style == "e" else floor_log10(D))
            if style != ("f" if P > X >= -4 else "e"):
                return bad
            fprec = P - (X + 1) if style == "f" else P - 1
            if alt:
                if len(fp) != fprec or not has_r:
                    return bad
            else:
                if len(fp) > fprec or fp.endswith(b"0") or has_r != bool(fp):
                    return bad
            if style == "e" and D != 0 and ip == b"0":
                return bad
        # ---- value -------------------------------------------------------
        sd = sig_digits(self.sp.conv, prec, x)
        M = self.abi.decimal_dig
        exact_val = self._parse(self.canonical)[1]
        if sd <= M:
            rec = D == exact_val
        elif x == 0 or round_sig(x, M, "Z", False) == x:
            rec = D == x
        else:
            L = round_sig(x, M, "Z", False)
            U = L + Fraction(10) ** (floor_log10(x) - M + 1)
            rec = L <= D <= U
            if self.mode == "U":
                rec = rec and (D <= x if self.neg else D >= x)
            elif self.mode == "D":
                rec = rec and (D >= x if self.neg else D <= x)
            elif self.mode == "Z":
                rec = rec and D <= x
        ulp = Fraction(1, 10 ** len(fp)) if style == "f" else Fraction(10) ** (ex - len(fp))
        if x != 0 and sd > M:
            ulp = max(ulp, Fraction(10) ** (floor_log10(x) - M + 1))
        # 'req': the printed value must at least denote the argument: either it is
        # within one unit of the last printed digit, or it converts back to the same
        # binary value (round-trips).  Anything closer is an accuracy question,
        # which the standard leaves to Recommended Practice / Annex F ('rec').
        req = rec or abs(D - x) <= ulp or self._roundtrips(D)
        return {"req": req, "rec": rec and req, "strict": strict}

    def _roundtrips(self, D: Fraction) -> bool:
        x = self.x
        if x == 0:
            return D == 0
        e = max(floor_log2(x), self.fmt.min_exp - 1)
        half_ulp = Fraction(2) ** (e - self.fmt.mant_dig + 1) / 2
        # nearest-even: the boundary itself belongs to the even neighbour; accept '<='
        return abs(D - x) <= half_ulp


class FloatHex(Part):
    """Validator for a/A of a finite value."""

    def __init__(self, sp, flags, width, prec, x: Fraction, neg, mode, fmt: FloatFormat, radix: bytes):
        self.sp, self.flags, self.width, self.prec = sp, flags, width, prec
        self.x, self.neg, self.mode, self.fmt, self.radix = x, neg, mode, fmt, radix
        self.canonical = self._canonical()

    def _canonical(self) -> bytes:
        up = self.sp.conv == "A"
        x, prec, alt = self.x, self.prec, "#" in self.flags
        if x == 0:
            E, mant = 0, Fraction(0)
        else:
            E = floor_log2(x)
            mant = x / Fraction(2) ** E  # in [1,2)
        if prec is None:
            # minimal exact hex digits
            n, p = mant, 0
            while (n * 16 ** p).denominator != 1:
                p += 1
            N = int(n * 16 ** p)
        else:
            p = prec
            N = round_int(mant * 16 ** p, self.mode, self.neg)
            if N >= 2 * 16 ** p:  # renormalise 2.000 -> 1.000p+1
                N //= 2
                E += 1
                if (N * 2) != round_int(mant * 16 ** p, self.mode, self.neg):
                    pass
        h = N >> (4 * p) if p else N
        frac = N - (h << (4 * p)) if p else 0
        digs = "0123456789ABCDEF" if up else "0123456789abcdef"
        fs = ""
        for i in range(p - 1, -1, -1):
            fs += digs[(frac >> (4 * i)) & 15]
        body = digs[h] + ("." + fs if (p > 0 or alt) else "") + ("P" if up else "p") + ("-" if E < 0 else "+") + str(abs(E))
        body = body.encode().replace(b".", self.radix)
        return layout(float_sign(self.neg, self.flags), b"0X" if up else b"0x", body, self.width, self.flags, True)

    def check(self, text: bytes) -> dict:
        up = self.sp.conv == "A"
        sign = float_sign(self.neg, self.flags)
        X, P = (b"X", b"P") if up else (b"x", b"p")
        hexd = rb"[0-9A-F]" if up else rb"[0-9a-f]"
        R = re.escape(self.radix)
        rx = (rb"(?P<lead> *)" + re.escape(sign) + rb"0" + X + rb"(?P<z>0*)(?P<h>" + hexd + rb")"
              rb"(?:(?P<r>" + R + rb")(?P<f>" + hexd + rb"*))?" + P + rb"(?P<es>[-+])(?P<e>[0-9]+)(?P<trail> *)")
        m = re.fullmatch(rx, text)
        bad = {"req": False, "rec": False, "strict": False}
        if not m:
            return bad
        lead, z, trail = m.group("lead"), m.group("z"), m.group("trail")
        if "-" in self.flags:
            if lead or z:
                return bad
            if trail and len(text) != self.width:
                return bad
        elif "0" in self.flags:
            if lead or trail:
                return bad
            if z and len(text) != self.width:
                return bad
        else:
            if z or trail:
                return bad
            if lead and len(text) != self.width:
                return bad
        if len(text) < self.width:
            return bad
        e = m.group("e")
        if len(e) > 1 and e.startswith(b"0"):
            return bad
        E = int(e) * (-1 if m.group("es") == b"-" else 1)
        h = int(m.group("h"), 16)
        fs = m.group("f") or b""
        has_r = m.group("r") is not None
        alt = "#" in self.flags
        if self.prec is not None:
            if len(fs) != self.prec or has_r != (self.prec > 0 or alt):
                return bad
        else:
            if alt and not has_r:
                return bad
            if has_r and not fs and not alt:
                return bad
        val = (h + Fraction(int(fs or b"0", 16), 16 ** len(fs))) * Fraction(2) ** E
        x = self.x
        if x == 0:
            ok = val == 0 and E == 0
        else:
            if self.fmt.is_normal(x) and h == 0:
                return bad
            # Leading digit h = floor(x / 2^E') must be one nonzero hex digit, so the
            # rounding exponent E' lies in [fl-3, fl].  The printed value must be the
            # correct rounding of x on the grid of one of those E'; the printed E may be
            # E' or, after a carry, the renormalised fl+1.  A leading 0 (subnormal,
            # possibly nibble-aligned as on x87) puts E in [min-3, min].
            fl = floor_log2(x)
            if self.prec is None:
                ok = val == x
                if h == 0:
                    ok = ok and self.fmt.min_exp - 4 <= E <= self.fmt.min_exp - 1
                else:
                    ok = ok and fl - 3 <= E <= fl
            elif h == 0:
                grid = Fraction(2) ** (E - 4 * self.prec)
                ok = (self.fmt.min_exp - 4 <= E <= self.fmt.min_exp - 1 and
                      val == round_int(x / grid, self.mode, self.neg) * grid)
            else:
                ok = False
                cands = list(range(fl - 3, fl + 1))
                if not self.fmt.is_normal(x):  # pre-rounding leading digit may be 0
                    cands += list(range(self.fmt.min_exp - 4, self.fmt.min_exp))
                if fl - 3 <= E <= fl + 1 or (not self.fmt.is_normal(x) and E in cands):
                    for Ep in cands:
                        grid = Fraction(2) ** (Ep - 4 * self.prec)
                        if val == round_int(x / grid, self.mode, self.neg) * grid:
                            ok = True
                            break
        strict = ok
        if self.prec is None and fs.endswith(b"0"):
            strict = False  # exact but with superfluous trailing zeros
        if x == 0 and m.group("es") == b"-":
            strict = False
        return {"req": ok, "rec": ok, "strict": strict}


def nonfinite(sp, flags, width, v: FVal, c23: bool = True) -> Part:
    up = sp.conv.isupper()
    if v.kind == "inf":
        words = [b"inf", b"infinity"]
    else:
        words = [b"nan"]
    if up:
        words = [w.upper() for w in words]
    if v.kind == "inf":
        signs = [float_sign(v.neg, flags)]
    else:
        # C99/POSIX: "[-]nan" -- whether a NaN's sign bit is shown is not pinned
        # down.  C23 ("a value with a negative sign") requires it.
        s = float_sign(v.neg, flags)
        signs = [s] if not v.neg else [s, float_sign(False, flags)]
    fl = flags.replace("0", "").replace("#", "")
    opts = []
    for s in signs:
        for w in words:
            opts.append(layout(s, b"", w, width, fl, False))
    strict_opts = [layout(float_sign(v.neg, flags), b"", w, width, fl, False) for w in words]
    canon = strict_opts[0]
    if v.kind == "nan":
        return NanPart(signs, up, width, fl, canon, float_sign(v.neg, flags))
    return Choice(opts, canonical=canon, strict=strict_opts, label="inf-style")


class NanPart(Part):
    def __init__(self, signs, up, width, flags, canon, strict_sign):
        self.signs, self.up, self.width, self.flags = signs, up, width, flags
        self.canonical = canon
        self.strict_sign = strict_sign

    def check(self, text):
        word = b"NAN" if self.up else b"nan"
        body = word + rb"(?:\([0-9A-Za-z_]*\))?"
        best = None
        for s in self.signs:  # try every permitted sign explicitly (space flag vs padding)
            if "-" in self.flags:
                rx = re.escape(s) + body + rb"(?P<pad> *)"
            else:
                rx = rb"(?P<pad> *)" + re.escape(s) + body
            m = re.fullmatch(rx, text)
            if not m:
                continue
            if m.group("pad") and len(text) != self.width:
                continue
            if len(text) < self.width:
                continue
            ok = {"req": True, "rec": True, "strict": s == self.strict_sign}
            if best is None or ok["strict"]:
                best = ok
        return best or {"req": False, "rec": False, "strict": False}


# --------------------------------------------------------------------------
# main entry: compute the expectation of one call
# --------------------------------------------------------------------------
@dataclass
class Arg:
    ctype: str
    value: object


def utf8_encode_wc(c: int):
    if c < 0 or c > 0x10FFFF or 0xD800 <= c <= 0xDFFF:
        return None
    return chr(c).encode("utf-8")


def expect(fmt: bytes, args: list, abi: Abi, locale: str = "C", mode: str = "N",
           c23_lc: bool = False) -> Expect:
    """Compute the expectation for printf(fmt, args...) on the given ABI.

    args: list of Arg(ctype, value)."""
    loc = abi.locale(locale)
    if loc is None or loc.actual is None:
        return Expect([], na=f"locale {locale} unavailable")
    items = parse_format(fmt)
    specs = [it for it in items if isinstance(it, Spec)]
    positional = any(s.pos is not None for s in specs if s.conv != "%")

    # resolve integer symbols and check float representability
    vals = []
    for a in args:
        if a.ctype in INT_TYPES:
            vals.append(resolve_int(abi, a.value))
        elif a.ctype in ("double", "ldouble"):
            fmtf = abi.dbl if a.ctype == "double" else abi.ldbl
            v = F(a.value)
            if v.kind == "num" and not fmtf.representable(v.value(fmtf)):
                return Expect([], na=f"value not representable in {a.ctype}")
            vals.append(v)
        else:
            vals.append(a.value)

    seq = iter(range(len(args)))

    def fetch(ref=None):
        if positional:
            if ref is None or ref > len(args):
                raise ValueError(f"positional reference {ref} out of range in {fmt!r}")
            return ref - 1
        try:
            return next(seq)
        except StopIteration:
            raise ValueError(f"insufficient arguments for {fmt!r}") from None

    out_parts = []
    nvals = []
    produced = 0  # characters so far (for %n); uses canonical lengths

    def emit(p: Part):
        nonlocal produced
        out_parts.append(p)
        produced += len(p.canonical)

    for it in items:
        if isinstance(it, bytes):
            emit(Lit(it))
            continue
        sp = it
        flags = sp.flags
        width = 0
        prec = None
        if sp.width == "*" or isinstance(sp.width, tuple):
            w = vals[fetch(sp.width[1] if isinstance(sp.width, tuple) else None)]
            w = to_bits(w, abi.bits["int"], True)
            if w < 0:
                flags += "-"
                w = -w
            width = w
        elif sp.width is not None:
            width = sp.width
        if sp.prec == "*" or isinstance(sp.prec, tuple):
            pv = vals[fetch(sp.prec[1] if isinstance(sp.prec, tuple) else None)]
            pv = to_bits(pv, abi.bits["int"], True)
            prec = None if pv < 0 else pv
        elif sp.prec is not None:
            prec = sp.prec
        conv = sp.conv
        if conv == "%":
            emit(Lit(b"%"))
            continue
        idx = fetch(sp.pos)
        a, v = args[idx], vals[idx]
        if conv in "diouxXbB":
            emit(Lit(fmt_int(abi, loc, sp, flags, v, width, prec)))
        elif conv in "fFeEgGaA":
            fv: FVal = v
            fmtf = abi.ldbl if sp.length == "L" else abi.dbl
            if fv.kind != "num":
                emit(nonfinite(sp, flags, width, fv))
                continue
            x = fv.value(fmtf)
            if conv in "aA":
                emit(FloatHex(sp, flags, width, prec, x, fv.neg, mode, fmtf, loc.decimal_point))
            else:
                emit(FloatDec(sp, flags, width, prec, x, fv.neg, mode, abi, loc, fmtf))
        elif conv == "c" and sp.length == "" :
            emit(Lit(layout(b"", b"", bytes([v & 0xFF]), width, flags, False)))
        elif conv == "C" or (conv == "c" and sp.length == "l"):
            wc = v
            if wc == 0:
                # POSIX.1-2024 and C23: as if by wcrtomb -> one null byte.
                # C99/C11 (strict reading: as %ls of L"\0") -> no bytes.
                body = b"\0" if c23_lc else b""
            elif wc < 0x80:
                body = bytes([wc])
            elif loc.utf8:
                body = utf8_encode_wc(wc)
                if body is None:
                    return Expect([], ret=-1)  # EILSEQ
            else:
                return Expect([AnyText()], na="non-ASCII %lc outside UTF-8 locale")
            emit(Lit(layout(b"", b"", body, width, flags, False)))
        elif conv == "s" and sp.length == "":
            s: bytes = v
            if b"\0" in s:
                s = s[: s.index(b"\0")]
            if prec is not None:
                s = s[:prec]
            emit(Lit(layout(b"", b"", s, width, flags, False)))
        elif conv == "S" or (conv == "s" and sp.length == "l"):
            ws = list(v)
            if 0 in ws:
                ws = ws[: ws.index(0)]
            body = b""
            for wc in ws:
                if wc < 0x80:
                    enc = bytes([wc])
                elif loc.utf8:
                    enc = utf8_encode_wc(wc)
                    if enc is None:
                        if prec is not None and len(body) >= prec:
                            break
                        return Expect([], ret=-1)
                else:
                    return Expect([AnyText()], na="non-ASCII %ls outside UTF-8 locale")
                if prec is not None and len(body) + len(enc) > prec:
                    break
                body += enc
            emit(Lit(layout(b"", b"", body, width, flags, False)))
        elif conv == "p":
            emit(PtrPart(v, width, flags))
        elif conv == "n":
            bits_key = {"": "int", "hh": "char", "h": "short", "l": "long", "ll": "llong",
                        "j": "intmax", "z": "size", "t": "ptrdiff"}
            if sp.length.startswith("wf"):
                b = abi.bits[f"fast{sp.length[2:]}"]
            elif sp.length.startswith("w"):
                b = int(sp.length[1:])
            else:
                b = abi.bits[bits_key[sp.length]]
            nvals.append(to_bits(produced, b, True))
        else:
            raise ValueError(f"unsupported conversion {sp.raw!r}")
    return Expect(out_parts, nvals=nvals)


class PtrPart(Part):
    def __init__(self, v, width, flags):
        self.v, self.width, self.flags = v, width, flags
        self.canonical = layout(b"", b"", b"<ptr>", width, flags, False)

    def check(self, text):
        bad = {"req": False, "rec": False, "strict": False}
        if len(text) < self.width:
            return bad
        if "-" in self.flags:
            body = text.rstrip(b" ")
            if text != body and len(text) != self.width:
                return bad
        else:
            body = text.lstrip(b" ")
            if text != body and len(text) != self.width:
                return bad
        ok = len(body) > 0 and all(0x20 < c < 0x7F for c in body)
        return {"req": ok, "rec": ok, "strict": ok}
