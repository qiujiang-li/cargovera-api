import sys
from pathlib import Path
import os
import logging

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("SMTP_PASSWORD", "smtp-secret")
os.environ.setdefault("DEFAULT_CONTACT_PHONE", "5125550100")

from app.external.usps import USPSService
from app.schemas.label import AddressSchema
from app.core.exceptions import (
    ExternalServiceClientError,
    ExternalServiceServerError,
)


@pytest.fixture
def shipper_address() -> AddressSchema:
    return AddressSchema(
        contact_name="Sender One",
        company_name="Sender LLC",
        street_line1="123 Sender St",
        street_line2="Suite 100",
        city="Austin",
        state="TX",
        postal_code="73301",
        country_code="US",
        phone="5125550101",
        email="shipper@example.com",
    )


@pytest.fixture
def recipient_address() -> AddressSchema:
    return AddressSchema(
        contact_name="Receiver Two",
        company_name="Receiver Corp",
        street_line1="456 Receiver Ave",
        street_line2="Apt 2",
        city="Dallas",
        state="TX",
        postal_code="75201",
        country_code="US",
        phone="2145550102",
        email="recipient@example.com",
    )


@pytest.fixture
def usps_packages() -> list[dict]:
    return [
        {
            "packageId": "PKG1",
            "weight": {"value": 32, "unit": "OZ"},
            "dimensions": {"length": 10, "width": 8, "height": 4, "unit": "IN"},
            "insuredValue": {"amount": "20.00", "currencyCode": "USD"},
            "references": [{"name": "ORDER", "value": "ORDER-123"}],
        }
    ]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


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


@pytest.mark.anyio
async def test_buy_label_success(monkeypatch, caplog, shipper_address, recipient_address, usps_packages):
    service = USPSService()

    sample_response = {
        "labelId": "LBL123456",
        "trackingNumber": "9400100000000000000000",
        "labelDownload": {
            "url": "https://example.com/label.pdf",
            "contentType": "application/pdf",
        },
        "postage": {"amount": "8.95", "currencyCode": "USD"},
        "fees": [
            {
                "description": "Signature Confirmation",
                "amount": {"value": "2.10", "currencyCode": "USD"},
            }
        ],
    }

    recorded: dict[str, object] = {}

    async def fake_make_request(method: str, endpoint: str, data: dict | None = None):
        recorded["method"] = method
        recorded["endpoint"] = endpoint
        recorded["data"] = data
        return sample_response

    monkeypatch.setattr(service, "_make_request", fake_make_request)

    caplog.set_level(logging.INFO)

    result = await service.buy_label(
        shipper_address=shipper_address,
        recipient_address=recipient_address,
        serviceType="USPS_GROUND_ADVANTAGE",
        packages=usps_packages,
        signature_option="none",
        ship_date="2024-09-19",
    )

    assert recorded["method"] == "POST"
    assert recorded["endpoint"] == "/labels/v3/label"

    payload = recorded["data"]
    assert isinstance(payload, dict)
    assert payload["mailClass"] == "USPS_GROUND_ADVANTAGE"
    assert payload["extraServices"] == [920]
    assert payload["packageDescription"]["weight"] == 32
    assert payload["packageDescription"]["weightUOM"] == "OZ"
    assert {"name": "ORDER", "value": "ORDER-123"} in payload["references"]
    assert any(ref["name"] == "SERVICE" for ref in payload["references"])

    labels = result["labels"]
    assert isinstance(labels, list)
    assert len(labels) == 1
    label = labels[0]
    assert label["trackingNumber"] == "9400100000000000000000"
    assert label["labelUrl"] == "https://example.com/label.pdf"
    assert label["charges"]["total"] == "11.05"
    assert label["price"] == "11.05"
    assert label["packageDocuments"][0]["url"] == "https://example.com/label.pdf"
    assert label["charges"]["breakdown"] == [
        {"type": "POSTAGE", "amount": "8.95"},
        {"type": "Signature Confirmation", "amount": "2.10"},
    ]

    assert result["charges"]["total"] == "11.05"
    assert result["charges"]["currency"] == "USD"
    assert result["output"]["transactionShipments"][0]["pieceResponses"] == labels

    assert any("USPS label created successfully" in record.message for record in caplog.records)


@pytest.mark.anyio
async def test_buy_label_multiple_labels(monkeypatch, shipper_address, recipient_address, usps_packages):
    service = USPSService()

    sample_response = {
        "totalPrice": {"amount": "23.75", "currencyCode": "USD"},
        "fees": [
            {
                "description": "Insurance",
                "amount": {"value": "2.00", "currencyCode": "USD"},
            }
        ],
        "labels": [
            {
                "labelId": "LBL111111",
                "trackingNumber": "9400100000000000000001",
                "postage": {"amount": "10.00", "currencyCode": "USD"},
                "fees": [
                    {
                        "description": "Signature Confirmation",
                        "amount": {"value": "1.25", "currencyCode": "USD"},
                    }
                ],
                "labelDownload": {"url": "https://example.com/label1.pdf"},
            },
            {
                "labelId": "LBL222222",
                "trackingNumber": "9400100000000000000002",
                "postage": {"amount": "10.50", "currencyCode": "USD"},
                "labelDocument": {
                    "url": "https://example.com/label2.pdf",
                    "contentType": "application/pdf",
                },
            },
        ],
    }

    async def fake_make_request(method: str, endpoint: str, data: dict | None = None):
        return sample_response

    monkeypatch.setattr(service, "_make_request", fake_make_request)

    result = await service.buy_label(
        shipper_address=shipper_address,
        recipient_address=recipient_address,
        serviceType="PRIORITY_MAIL",
        packages=usps_packages,
        signature_option="direct",
        ship_date="2024-09-20",
    )

    assert result["charges"]["total"] == "23.75"
    assert result["charges"]["breakdown"] == [
        {"type": "Insurance", "amount": "2.00"},
    ]

    labels = result["labels"]
    assert len(labels) == 2
    first, second = labels

    assert first["trackingNumber"] == "9400100000000000000001"
    assert first["labelUrl"] == "https://example.com/label1.pdf"
    assert first["charges"]["total"] == "11.25"
    assert first["charges"]["breakdown"] == [
        {"type": "POSTAGE", "amount": "10.00"},
        {"type": "Signature Confirmation", "amount": "1.25"},
    ]

    assert second["trackingNumber"] == "9400100000000000000002"
    assert second["labelUrl"] == "https://example.com/label2.pdf"
    assert second["charges"]["total"] == "10.50"
    assert second["charges"]["breakdown"] == [
        {"type": "POSTAGE", "amount": "10.50"},
    ]

    assert result["output"]["transactionShipments"][0]["pieceResponses"] == labels


@pytest.mark.anyio
async def test_buy_label_raises_client_error(monkeypatch, shipper_address, recipient_address, usps_packages):
    service = USPSService()

    async def fake_make_request(method: str, endpoint: str, data: dict | None = None):
        return {
            "errors": [
                {"code": "API-400", "message": "Bad request", "status": 400},
            ]
        }

    monkeypatch.setattr(service, "_make_request", fake_make_request)

    with pytest.raises(ExternalServiceClientError) as excinfo:
        await service.buy_label(
            shipper_address=shipper_address,
            recipient_address=recipient_address,
            serviceType="USPS_GROUND_ADVANTAGE",
            packages=usps_packages,
            signature_option="none",
            ship_date="2024-09-19",
        )

    assert "Bad request" in str(excinfo.value)


@pytest.mark.anyio
async def test_buy_label_raises_server_error(monkeypatch, shipper_address, recipient_address, usps_packages):
    service = USPSService()

    async def fake_make_request(method: str, endpoint: str, data: dict | None = None):
        return {
            "errors": [
                {"code": "SVC-500", "message": "System failure", "status": 500},
            ]
        }

    monkeypatch.setattr(service, "_make_request", fake_make_request)

    with pytest.raises(ExternalServiceServerError) as excinfo:
        await service.buy_label(
            shipper_address=shipper_address,
            recipient_address=recipient_address,
            serviceType="USPS_GROUND_ADVANTAGE",
            packages=usps_packages,
            signature_option="none",
            ship_date="2024-09-19",
        )

    assert "System failure" in str(excinfo.value)
