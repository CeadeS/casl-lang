"""The living audit is the authority gate: it must pass (exit 0). Running it as a test makes
CI fail loudly on any authority/traceability/feature regression."""
import io
from contextlib import redirect_stdout

from casl import audit


def test_audit_passes():
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = audit.main()
    assert rc == 0, "living audit failed:\n" + buf.getvalue()[-2000:]
