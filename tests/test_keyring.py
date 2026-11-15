"""Attestation key lifecycle — keyring validity windows + opt-in policy (D4 / CEP-0072, LH-Q-018)."""
import datetime

from casl import keyring as kr


def test_validity_windows():
    ks = kr.parse_keyring("cur added:2026-01-01\n"
                          "old added:2025-01-01 retired:2026-01-01\n"
                          "bad added:2025-06-01 revoked:2026-03-15 reason:theft\n")
    d = datetime.date.fromisoformat
    assert ks["cur"].valid_at(d("2026-06-01"))
    assert not ks["cur"].valid_at(d("2025-12-31"))      # before added
    assert ks["old"].valid_at(d("2025-06-01"))          # within window — old sigs still verify
    assert not ks["old"].valid_at(d("2026-06-01"))      # after retired — cannot make new sigs
    assert ks["bad"].valid_at(d("2026-03-14"))          # before revocation
    assert not ks["bad"].valid_at(d("2026-03-15"))      # at/after revocation — re-review


def test_authorized_policy_and_opt_in(tmp_path):
    casl = tmp_path / ".casl"
    casl.mkdir()
    (casl / "attest_keys").write_text("cur added:2026-01-01\nold added:2025-01-01 retired:2026-01-01\n")
    assert kr.authorized(str(tmp_path), "cur", "2026-06-24")[0]
    assert not kr.authorized(str(tmp_path), "old", "2026-06-24")[0]       # retired before ts
    assert kr.authorized(str(tmp_path), "old", "2025-06-01")[0]           # within the old key's window
    assert not kr.authorized(str(tmp_path), "unknown", "2026-06-24")[0]   # not in the keyring
    assert kr.authorized(str(tmp_path / "nokeyring"), "anyone")[0]        # opt-in: no file ⇒ policy off
