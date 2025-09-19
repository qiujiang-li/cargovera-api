import sys
from pathlib import Path
import os

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("SMTP_PASSWORD", "smtp-secret")

from app.external.usps import USPSService


@pytest.mark.parametrize(
    "mail_class, option, expected_codes",
    [
        ("PRIORITY_MAIL_EXPRESS", "carrier_default", []),
        ("PRIORITY_MAIL_EXPRESS", "none", [920]),
        ("PRIORITY_MAIL_EXPRESS", "direct", [981]),
        ("PRIORITY_MAIL_EXPRESS", "indirect", [986]),
        ("PRIORITY_MAIL_EXPRESS", "adult", [922]),
        ("PRIORITY_MAIL", "carrier_default", []),
        ("PRIORITY_MAIL", "none", [920]),
        ("PRIORITY_MAIL", "direct", [921]),
        ("PRIORITY_MAIL", "indirect", [924]),
        ("PRIORITY_MAIL", "adult", [922]),
        ("USPS_GROUND_ADVANTAGE", "carrier_default", []),
        ("USPS_GROUND_ADVANTAGE", "none", [920]),
        ("USPS_GROUND_ADVANTAGE", "direct", [921]),
        ("USPS_GROUND_ADVANTAGE", "indirect", [921]),
        ("USPS_GROUND_ADVANTAGE", "adult", [922]),
    ],
)
def test_get_usps_signature_code_expected_results(mail_class, option, expected_codes):
    service = USPSService()

    result = service.get_usps_signature_code(option, mail_class)

    assert result == expected_codes


def test_get_usps_signature_code_invalid_combination():
    service = USPSService()

    with pytest.raises(ValueError):
        service.get_usps_signature_code("unknown", "PRIORITY_MAIL")

    with pytest.raises(ValueError):
        service.get_usps_signature_code("direct", "UNKNOWN_SERVICE")
