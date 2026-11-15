"""casl.ed25519 — a dependency-free Ed25519 (RFC 8032) for the Python REFERENCE broker.

The signed-approval check (`casl.approval`) needs a signature primitive, and the reference keeps its
zero-dependency rule (stdlib only). This is the RFC 8032 §6 reference algorithm, pinned by the RFC test
vectors (tests/test_ed25519.py) and cross-checked against the Rust broker (ed25519-dalek) by the signed
conformance corpus (tests/test_approval_signed.py): a signature made here must verify there.

Scope + honesty: NOT constant-time. `verify` handles only public data, so that is harmless; `sign` is for
tests and tooling, never for a long-lived production secret. The production verifier is the Rust broker.
"""
from __future__ import annotations

import hashlib

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _inv(x: int) -> int:
    return pow(x, _P - 2, _P)


def _add(a, b):
    A = (a[1] - a[0]) * (b[1] - b[0]) % _P
    B = (a[1] + a[0]) * (b[1] + b[0]) % _P
    C = 2 * a[3] * b[3] * _D % _P
    D = 2 * a[2] * b[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _mul(s: int, pt):
    q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _add(q, pt)
        pt = _add(pt, pt)
        s >>= 1
    return q


def _eq(a, b) -> bool:
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _recover_x(y: int, sign: int):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_GY = 4 * _inv(5) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _compress(pt) -> bytes:
    zinv = _inv(pt[2])
    x, y = pt[0] * zinv % _P, pt[1] * zinv % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s: bytes):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _h(data: bytes) -> int:
    return int.from_bytes(hashlib.sha512(data).digest(), "little") % _L


def _expand(secret: bytes):
    h = hashlib.sha512(secret).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(secret: bytes) -> bytes:
    """The 32-byte public key of a 32-byte secret seed."""
    if len(secret) != 32:
        raise ValueError("ed25519 secret seed must be 32 bytes")
    a, _ = _expand(secret)
    return _compress(_mul(a, _G))


def sign(secret: bytes, msg: bytes) -> bytes:
    """RFC 8032 signature (64 bytes). Tests/tooling only — not constant-time."""
    if len(secret) != 32:
        raise ValueError("ed25519 secret seed must be 32 bytes")
    a, prefix = _expand(secret)
    pub = _compress(_mul(a, _G))
    r = _h(prefix + msg)
    rs = _compress(_mul(r, _G))
    k = _h(rs + pub + msg)
    s = (r + k * a) % _L
    return rs + int.to_bytes(s, 32, "little")


def verify(public: bytes, msg: bytes, signature: bytes) -> bool:
    """True iff `signature` is a valid Ed25519 signature of `msg` under `public`. Never raises."""
    try:
        if len(public) != 32 or len(signature) != 64:
            return False
        a = _decompress(public)
        r = _decompress(signature[:32])
        if a is None or r is None:
            return False
        s = int.from_bytes(signature[32:], "little")
        if s >= _L:
            return False
        k = _h(signature[:32] + public + msg)
        return _eq(_mul(s, _G), _add(r, _mul(k, a)))
    except Exception:  # noqa: BLE001 — a verifier fails closed
        return False
