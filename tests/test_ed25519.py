"""RFC 8032 §7.1 test vectors pin the dependency-free reference Ed25519 (casl.ed25519)."""
import pytest

from casl import ed25519

VECTORS = [  # (secret seed, public key, message, signature) — RFC 8032 §7.1 TEST 1, TEST 2
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
     "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
     "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
     "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
     "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
]


@pytest.mark.parametrize("sk,pk,msg,sig", VECTORS)
def test_rfc8032_vectors(sk, pk, msg, sig):
    sk, pk, msg, sig = (bytes.fromhex(x) for x in (sk, pk, msg, sig))
    assert ed25519.public_key(sk) == pk
    assert ed25519.sign(sk, msg) == sig
    assert ed25519.verify(pk, msg, sig)


def test_verify_rejects_tampering_and_garbage():
    sk = bytes(range(32))
    pk, sig = ed25519.public_key(sk), ed25519.sign(sk, b"approve")
    assert ed25519.verify(pk, b"approve", sig)
    assert not ed25519.verify(pk, b"approve!", sig)                       # other message
    assert not ed25519.verify(pk, b"approve", sig[:-1] + bytes([sig[-1] ^ 1]))   # flipped bit
    assert not ed25519.verify(ed25519.public_key(b"\x01" * 32), b"approve", sig)  # other key
    assert not ed25519.verify(pk, b"approve", b"")                        # never raises
    assert not ed25519.verify(b"\xff" * 32, b"approve", sig)
