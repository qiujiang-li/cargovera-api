import httpx
import os
from app.schemas.label import ShipmentRatesRequest, BuyLabelRequest
from app.models.label import Label
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.async_cache import async_cache
from app.api.deps import get_db
import httpx
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from urllib.parse import urlencode
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from decimal import Decimal, InvalidOperation
from app.core.exceptions import ExternalServiceException,ExternalServiceClientError, ExternalServiceServerError
from app.utils.mist import parse_name, parse_zipcode

logger = logging.getLogger(__name__)
class USPSService:
    _signature_options_map = {
        "PRIORITY_MAIL_EXPRESS": {
            'carrier_default': [],
            'none': [920],
            'direct': [981],
            'indirect': [986],
            'adult': [922],
        },
        "PRIORITY_MAIL": {
            'carrier_default': [],
            'none': [920],
            'direct': [921],
            'indirect': [924],
            'adult': [922],
        },
        "USPS_GROUND_ADVANTAGE": {
            'carrier_default': [],
            'none': [920],
            'direct': [921],
            'indirect': [921],
            'adult': [922],
        }
    }

    def __init__(self):
        self.base_url = os.getenv("USPS_BASE_URL")
        self.account_number = os.getenv("USPS_ACCOUNT_NUMBER")
        self.client_id = os.getenv("USPS_CLIENT_ID")
        self.client_secret = os.getenv("USPS_CLIENT_SECRET")
        self.default_contact_phone = os.getenv("DEFAULT_CONTACT_PHONE")
    
    @async_cache(ttl=3500)
    async def _get_usps_access_token(self) -> str:
        logger.debug("Fetching new USPS access token" )
        payload = {
            "grant_type": "client_credentials", 
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{self.base_url}/oauth2/v3/token",
                data=payload,   # data= sends form-encoded body
            )
            response.raise_for_status()
            data = response.json()
            return data["access_token"]
    

    def get_usps_signature_code(self, option: str, mailClass: str = "USPS_GROUND_ADVANTAGE") -> List[int]:
        """
        Returns the USPS extra service codes for a given signature option and shipping method.

        Args:
            option (str): Custom signature option (e.g., 'direct', 'none', 'adult')
            mailClass (str): Shipping method (e.g., 'USPS_GROUND_ADVANTAGE', 'PRIORITY_MAIL')

        Returns:
            List[int]: USPS extra service code list for the requested option.

        Raises:
            ValueError: If option or shipping method is invalid
        """
        try:
            codes = self._signature_options_map[mailClass][option]
        except KeyError:
            raise ValueError(f"Invalid combination: shipping_method='{mailClass}', option='{option}'")

        logger.debug(
            "Resolved USPS signature option '%s' for %s to extra services %s",
            option,
            mailClass,
            codes,
        )
        return codes

    

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make authenticated request to USPS API with support for GET, POST, DELETE"""
        token = await self._get_usps_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}{endpoint}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method.upper() == "GET":
                    response = await client.get(url, params=data, headers=headers)
                elif method.upper() == "DELETE":
                    response = await client.delete(url, params=data, headers=headers)
                elif method.upper() == "POST":
                    response = await client.post(url, json=data, headers=headers)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                logger.debug(
                    "USPS response (%s) from %s: status=%s body=%s",
                    method,
                    url,
                    response.status_code,
                    response.text,
                )

                try:
                    result = response.json()
                except ValueError:
                    result = {}

                if 200 <= response.status_code < 300:
                    return result

                errors = self._extract_usps_errors(result)
                message = ""
                if errors:
                    message = "; ".join(
                        self._format_usps_error(error) for error in errors
                    )
                elif isinstance(result, dict):
                    message = (
                        result.get("message")
                        or result.get("detail")
                        or result.get("description")
                        or result.get("error")
                        or result.get("title")
                        or ""
                    )

                if 400 <= response.status_code < 500:
                    logger.warning(
                        "USPS client error (%s %s): %s", method, endpoint, message or response.text
                    )
                    raise ExternalServiceClientError(
                        message or f"Client error: {response.text}"
                    )

                logger.error(
                    "USPS server error (%s %s): %s", method, endpoint, message or response.text
                )
                raise ExternalServiceServerError(
                    message or f"Server error: {response.text}"
                )
        except httpx.RequestError as e:
            logger.exception(f"Request error for {method} {endpoint}")
            raise ExternalServiceException(f"Request failed: {str(e)}")
        
    async def get_rates(self, 
                        pickup_postal_code: str,
                        destination_postal_code: str,
                        packages: List[Dict[str, Any]]) -> List[Dict]:
        """Get shipping rates from USPS"""
        #if len(packages) != 1
        package = packages[0]
        weight = package.get("weight", {}).get("value")
        length = package.get("dimensions",{}).get("length")
        ship_date = datetime.now().strftime("%Y-%m-%d")
        request_data = {
            "originZIPCode": pickup_postal_code,
            "destinationZIPCode": destination_postal_code,
            "weight": package.get("weight", {}).get("value"),
            "length": package.get("dimensions",{}).get("length"),
            "width": package.get("dimensions",{}).get("width"),
            "height": package.get("dimensions",{}).get("height"),
            "mailClasses": [
                "USPS_GROUND_ADVANTAGE",
                "PRIORITY_MAIL_EXPRESS",
                "PRIORITY_MAIL"
            ],
            "priceType": "COMMERCIAL",
            "mailingDate": ship_date,
            "accountType": "EPS",
            "accountNumber": self.account_number,
            "hasNonstandardCharacteristics": False
        }
        
    
        result = await self._make_request("POST", "/prices/v3/base-rates-list/search", request_data)
        # Process USPS response format
        logger.debug(f"response from usps rates search {result}")
        rates_options = result.get("rateOptions",[])
        rates = [
            rate
            for opt in rates_options
            for rate in opt.get("rates", [])
        ]

        lowest_rates = self._filter_lowest_rates(rates)
        return lowest_rates

    async def buy_label(
        self,
        shipper_address: Any,
        recipient_address: Any,
        serviceType: str,
        packages: List[Dict[str, Any]],
        signature_option: str,
        ship_date: Optional[str],
    ) -> Dict[str, Any]:
        """Purchase a shipping label from USPS."""

        if not packages:
            raise ExternalServiceException("USPS requires at least one package to create a label.")

        shipper_contact = self._get_address_field(shipper_address, "contact_name", "") or ""
        recipient_contact = self._get_address_field(recipient_address, "contact_name", "") or ""

        from_first_name, from_last_name = parse_name(shipper_contact)
        to_first_name, to_last_name = parse_name(recipient_contact)

        shipper_postal_code = self._get_address_field(
            shipper_address, "postal_code", "", aliases=("zip_code",)
        ) or ""
        recipient_postal_code = self._get_address_field(
            recipient_address, "postal_code", "", aliases=("zip_code",)
        ) or ""

        from_zip_code, from_zip_code_plus = parse_zipcode(str(shipper_postal_code))
        to_zip_code, to_zip_code_plus = parse_zipcode(str(recipient_postal_code))

        logger.debug(
            "Parsed shipper postal code '%s' into ZIP='%s' plus4='%s'",
            shipper_postal_code,
            from_zip_code,
            from_zip_code_plus,
        )
        logger.debug(
            "Parsed recipient postal code '%s' into ZIP='%s' plus4='%s'",
            recipient_postal_code,
            to_zip_code,
            to_zip_code_plus,
        )

        extra_services = self.get_usps_signature_code(signature_option, serviceType)
        package = packages[0]

        if ship_date is None:
            ship_date = datetime.now().strftime("%Y-%m-%d")

        from_address_payload = self._build_address_payload(
            shipper_address,
            first_name=from_first_name,
            last_name=from_last_name,
            zip_code=from_zip_code,
            zip_plus4=from_zip_code_plus,
        )
        to_address_payload = self._build_address_payload(
            recipient_address,
            first_name=to_first_name,
            last_name=to_last_name,
            zip_code=to_zip_code,
            zip_plus4=to_zip_code_plus,
        )

        request_data: Dict[str, Any] = {
            "accountNumber": self.account_number,
            "mailClass": serviceType,
            "mailingDate": ship_date,
            "rateIndicator": "SP",
            "priceType": "COMMERCIAL",
            "extraServices": extra_services,
            "references": self._collect_usps_references(
                package,
                service_type=serviceType,
                ship_date=ship_date,
                shipper=shipper_address,
                recipient=recipient_address,
            ),
            "fromAddress": from_address_payload,
            "toAddress": to_address_payload,
            "packageDescription": self._build_package_description(package),
        }

        if not request_data["references"]:
            request_data["references"].append({
                "name": "SERVICE",
                "value": serviceType,
            })

        logger.debug("Submitting USPS label request: %s", request_data)
        result = await self._make_request("POST", "/labels/v3/label", request_data)
        logger.debug("USPS label raw response: %s", result)

        errors = self._extract_usps_errors(result)
        if errors:
            formatted = "; ".join(self._format_usps_error(err) for err in errors)
            if any(self._is_server_error(err) for err in errors):
                logger.error("USPS label creation server error: %s", formatted)
                raise ExternalServiceServerError(formatted)
            logger.warning("USPS label creation client error: %s", formatted)
            raise ExternalServiceClientError(formatted)

        aggregate_charges = self._extract_charges(result)
        label_payloads = self._extract_label_payloads(result)
        if not label_payloads and isinstance(result, dict):
            label_payloads = [result]

        normalized_labels: List[Dict[str, Any]] = []
        for payload in label_payloads:
            item_charges = self._merge_charge_details(
                aggregate_charges,
                self._extract_charges(payload),
            )
            normalized_labels.append(
                self._build_label_record(payload, item_charges)
            )

        tracking_numbers = [
            label.get("trackingNumber")
            for label in normalized_labels
            if label.get("trackingNumber")
        ]

        logger.info(
            "USPS label created successfully for %s (total=%s)",
            ", ".join(tracking_numbers) if tracking_numbers else "unknown tracking",
            aggregate_charges.get("total") or "unknown",
        )

        response_payload: Dict[str, Any] = {
            "labels": normalized_labels,
            "charges": aggregate_charges,
        }

        if normalized_labels:
            response_payload["output"] = {
                "transactionShipments": [
                    {"pieceResponses": normalized_labels}
                ]
            }

        return response_payload

    def _get_address_field(
        self,
        address: Any,
        field: str,
        default: Any = None,
        *,
        aliases: Tuple[str, ...] = (),
    ) -> Any:
        """Safely retrieve an address attribute whether the input is an object or dict."""

        if address is None:
            return default

        candidate_fields = (field, *aliases)

        for candidate in candidate_fields:
            value: Any
            if isinstance(address, dict):
                value = address.get(candidate, None)
            else:
                value = getattr(address, candidate, None)

            if value is not None:
                return value

        if isinstance(address, dict):
            return address.get(field, default)

        return getattr(address, field, default)

    def _build_address_payload(
        self,
        address: Any,
        *,
        first_name: str,
        last_name: str,
        zip_code: str,
        zip_plus4: str,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "firstName": first_name,
            "lastName": last_name,
            "companyName": self._get_address_field(address, "company_name"),
            "streetAddress": self._get_address_field(address, "street_line1"),
            "secondaryAddress": self._get_address_field(address, "street_line2"),
            "city": self._get_address_field(address, "city"),
            "state": self._get_address_field(address, "state"),
            "ZIPCode": zip_code,
        }

        if zip_plus4:
            payload["ZIPPlus4"] = zip_plus4

        phone = self._get_address_field(address, "phone") or self.default_contact_phone
        if phone:
            payload["phoneNumber"] = phone

        email = self._get_address_field(address, "email")
        if email:
            payload["email"] = email

        return {k: v for k, v in payload.items() if v not in (None, "")}

    def _build_package_description(self, package: Dict[str, Any]) -> Dict[str, Any]:
        weight = package.get("weight", {}) if isinstance(package, dict) else {}
        dimensions = package.get("dimensions", {}) if isinstance(package, dict) else {}

        weight_unit = (weight.get("unit") or weight.get("unitOfMeasure") or "OZ").upper()
        dimension_unit = (dimensions.get("unit") or dimensions.get("unitOfMeasure") or "IN").upper()

        description: Dict[str, Any] = {
            "packageId": package.get("packageId")
            or package.get("id")
            or "PKG1",
            "weightUOM": weight_unit,
            "weight": weight.get("value"),
            "dimensionsUOM": dimension_unit,
            "length": dimensions.get("length"),
            "width": dimensions.get("width"),
            "height": dimensions.get("height"),
        }

        girth = package.get("girth")
        if girth is not None:
            description["girth"] = girth

        insured = (
            package.get("insuredValue")
            or package.get("insured_value")
            or package.get("declaredValue")
        )
        insured_amount = self._parse_charge_amount(insured)
        if insured_amount is not None:
            description["insuredValue"] = {
                "amount": str(insured_amount),
                "currencyCode": self._infer_currency(insured) or "USD",
            }

        return {k: v for k, v in description.items() if v not in (None, "")}

    def _collect_usps_references(
        self,
        package: Dict[str, Any],
        *,
        service_type: str,
        ship_date: str,
        shipper: Dict[str, Any],
        recipient: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        references: List[Dict[str, str]] = []

        def _add_reference(name: Optional[str], value: Optional[Any]) -> None:
            if not name or value in (None, ""):
                return
            references.append({"name": str(name), "value": str(value)})

        package_references = package.get("references")
        if isinstance(package_references, list):
            for ref in package_references:
                if isinstance(ref, dict):
                    _add_reference(ref.get("name") or ref.get("type"), ref.get("value") or ref.get("number"))
                else:
                    _add_reference("REFERENCE", ref)
        elif isinstance(package_references, dict):
            _add_reference(
                package_references.get("name") or package_references.get("type"),
                package_references.get("value") or package_references.get("number"),
            )

        for key in ("reference", "customerReference", "customerReferenceNumber"):
            if package.get(key):
                _add_reference(key.upper(), package.get(key))

        _add_reference("SERVICE", service_type)
        _add_reference("SHIP_DATE", ship_date)
        shipper_name = self._get_address_field(shipper, "company_name") or self._get_address_field(
            shipper, "contact_name"
        )
        recipient_name = self._get_address_field(recipient, "company_name") or self._get_address_field(
            recipient, "contact_name"
        )

        _add_reference("SHIPPER", shipper_name)
        _add_reference("RECIPIENT", recipient_name)

        seen = set()
        unique_refs: List[Dict[str, str]] = []
        for ref in references:
            key = (ref["name"], ref["value"])
            if key in seen:
                continue
            seen.add(key)
            unique_refs.append(ref)

        return unique_refs

    def _extract_usps_errors(self, payload: Any) -> List[Dict[str, Any]]:
        if payload is None:
            return []

        errors: List[Dict[str, Any]] = []

        def _normalize(value: Any) -> List[Dict[str, Any]]:
            if value is None:
                return []
            if isinstance(value, list):
                normalized: List[Dict[str, Any]] = []
                for item in value:
                    if isinstance(item, dict):
                        normalized.append(item)
                    elif isinstance(item, str):
                        normalized.append({"message": item})
                return normalized
            if isinstance(value, dict):
                return [value]
            if isinstance(value, str):
                return [{"message": value}]
            return []

        if isinstance(payload, dict):
            for key in ("errors", "error", "errorList", "errorResponse"):
                if payload.get(key) is not None:
                    errors.extend(_normalize(payload.get(key)))

            for wrapper_key in ("data", "result", "response"):
                if wrapper_key in payload:
                    errors.extend(self._extract_usps_errors(payload[wrapper_key]))

        elif isinstance(payload, list):
            for item in payload:
                errors.extend(self._extract_usps_errors(item))

        return errors

    def _format_usps_error(self, error: Dict[str, Any]) -> str:
        parts: List[str] = []
        code = error.get("code") or error.get("errorCode") or error.get("error")
        if code:
            parts.append(str(code))

        message = error.get("message") or error.get("detail") or error.get("description")
        if message:
            parts.append(str(message))

        status = self._error_status_code(error)
        if status:
            parts.append(f"status={status}")

        return ": ".join(parts) if parts else str(error)

    def _error_status_code(self, error: Dict[str, Any]) -> Optional[int]:
        for key in ("status", "statusCode", "httpStatus", "httpStatusCode"):
            if error.get(key) is not None:
                try:
                    return int(error[key])
                except (TypeError, ValueError):
                    continue
        return None

    def _is_server_error(self, error: Dict[str, Any]) -> bool:
        status = self._error_status_code(error)
        if status is not None:
            return status >= 500

        code = (error.get("code") or error.get("errorCode") or "").upper()
        return code.startswith("SVC") or code.startswith("SERVER")

    def _extract_label_payloads(self, payload: Any) -> List[Dict[str, Any]]:
        if payload is None:
            return []

        if isinstance(payload, list):
            result: List[Dict[str, Any]] = []
            for item in payload:
                result.extend(self._extract_label_payloads(item))
            return result

        if not isinstance(payload, dict):
            return []

        for key in (
            "labels",
            "label",
            "labelDetails",
            "labelResponses",
            "labelList",
            "shippingLabels",
            "labelData",
            "labelResponse",
            "pieces",
            "pieceResponses",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                return [value]

        for wrapper in ("data", "result", "response", "output"):
            if wrapper in payload:
                return self._extract_label_payloads(payload[wrapper])

        if any(
            key in payload
            for key in ("trackingNumber", "trackingId", "labelUrl", "labelDownload")
        ):
            return [payload]

        return []

    def _parse_charge_amount(self, value: Any) -> Optional[Decimal]:
        if value is None:
            return None

        if isinstance(value, Decimal):
            return value

        if isinstance(value, dict):
            for key in ("amount", "value", "price", "total", "netCharge"):
                if value.get(key) is not None:
                    parsed = self._parse_charge_amount(value[key])
                    if parsed is not None:
                        return parsed
            return None

        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None

    def _infer_currency(self, value: Any) -> Optional[str]:
        if isinstance(value, dict):
            for key in ("currencyCode", "currency", "currencySymbol"):
                if value.get(key):
                    return str(value[key])
        return None

    def _extract_charges(self, payload: Any) -> Dict[str, Any]:
        charges: Dict[str, Any] = {
            "currency": "USD",
            "breakdown": [],
            "total": None,
        }

        if not isinstance(payload, dict):
            return charges

        currency = (
            self._infer_currency(payload.get("price"))
            or self._infer_currency(payload.get("postage"))
            or payload.get("currency")
        )
        if currency:
            charges["currency"] = currency

        base_amount = self._parse_charge_amount(
            payload.get("postage")
            or payload.get("price")
            or payload.get("amount")
        )
        if base_amount is not None:
            charges["breakdown"].append({"type": "POSTAGE", "amount": str(base_amount)})

        for key in ("fees", "extraServices", "surcharges", "additionalFees", "addOnCharges"):
            extra = payload.get(key)
            if isinstance(extra, list):
                for item in extra:
                    amount = self._parse_charge_amount(item)
                    if amount is None:
                        continue
                    description = (
                        item.get("description")
                        or item.get("name")
                        or item.get("serviceDescription")
                        or item.get("code")
                        or key[:-1].upper()
                    )
                    charges["breakdown"].append(
                        {"type": str(description), "amount": str(amount)}
                    )
                    if not currency:
                        inferred = self._infer_currency(item)
                        if inferred:
                            currency = inferred
            elif isinstance(extra, dict):
                amount = self._parse_charge_amount(extra)
                if amount is not None:
                    description = (
                        extra.get("description")
                        or extra.get("name")
                        or key[:-1].upper()
                    )
                    charges["breakdown"].append(
                        {"type": str(description), "amount": str(amount)}
                    )
                    if not currency:
                        inferred = self._infer_currency(extra)
                        if inferred:
                            currency = inferred

        total_amount = self._parse_charge_amount(
            payload.get("totalPrice")
            or payload.get("totalPostage")
            or payload.get("total")
            or payload.get("amountDue")
        )

        if total_amount is None and charges["breakdown"]:
            total_value = Decimal("0")
            for entry in charges["breakdown"]:
                try:
                    total_value += Decimal(entry["amount"])
                except (InvalidOperation, TypeError, ValueError):
                    continue
            total_amount = total_value

        if total_amount is not None:
            charges["total"] = str(total_amount)

        if currency:
            charges["currency"] = currency

        return charges

    def _merge_charge_details(
        self,
        aggregate: Dict[str, Any],
        item: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not item["breakdown"] and not item["total"]:
            return aggregate

        merged_breakdown = item["breakdown"] or aggregate["breakdown"]
        merged_total = item["total"] or aggregate["total"]
        merged_currency = item.get("currency") or aggregate.get("currency") or "USD"

        if not merged_total and merged_breakdown:
            total_value = Decimal("0")
            for entry in merged_breakdown:
                try:
                    total_value += Decimal(entry["amount"])
                except (InvalidOperation, TypeError, ValueError):
                    continue
            merged_total = str(total_value)

        return {
            "currency": merged_currency,
            "breakdown": merged_breakdown,
            "total": merged_total,
        }

    def _extract_label_document(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for key in (
            "labelDownload",
            "labelDocument",
            "labelFile",
            "document",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        return item
            elif isinstance(value, dict):
                return value
            elif isinstance(value, str):
                return {"data": value}
        return None

    def _extract_label_url(
        self,
        payload: Dict[str, Any],
        label_document: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        if label_document:
            for key in ("url", "href", "labelUrl", "downloadUrl"):
                if label_document.get(key):
                    return label_document[key]

        for key in ("labelUrl", "labelURL", "url", "downloadUrl", "downloadURL", "href"):
            if payload.get(key):
                return payload[key]

        links = payload.get("links")
        if isinstance(links, list):
            for link in links:
                if isinstance(link, dict) and link.get("href"):
                    return link["href"]

        return None

    def _build_label_record(
        self,
        payload: Dict[str, Any],
        charges: Dict[str, Any],
    ) -> Dict[str, Any]:
        record = dict(payload)
        tracking_number = (
            record.get("trackingNumber")
            or record.get("trackingId")
            or record.get("labelId")
        )
        if tracking_number:
            record["trackingNumber"] = tracking_number

        label_document = self._extract_label_document(record)
        label_url = self._extract_label_url(record, label_document)

        if label_url:
            record["labelUrl"] = label_url
            if not label_document:
                label_document = {"url": label_url}
            record["labelDocument"] = label_document

            existing_docs = record.get("packageDocuments")
            docs: List[Dict[str, Any]]
            if isinstance(existing_docs, list):
                docs = [dict(doc) if isinstance(doc, dict) else doc for doc in existing_docs]
            else:
                docs = []

            if label_url and not any(
                isinstance(doc, dict) and doc.get("url") == label_url for doc in docs
            ):
                docs.append(
                    {
                        "url": label_url,
                        "documentType": label_document.get("documentType")
                        or label_document.get("type")
                        or "LABEL",
                        "contentType": label_document.get("contentType")
                        or label_document.get("mimeType")
                        or "application/pdf",
                    }
                )

            record["packageDocuments"] = docs

        if charges.get("total") is not None:
            record["price"] = charges["total"]
            record["totalPrice"] = charges["total"]
        else:
            price_amount = self._parse_charge_amount(
                record.get("price") or record.get("postage")
            )
            if price_amount is not None:
                record["price"] = str(price_amount)

        record["charges"] = charges

        return record
    
            
    async def cancel_label(self, tracking_number: str) -> Dict:
        """Cancel a shipping label"""

        response = await self._make_request("DELETE", f"/labels/v3/label/{tracking_number}")
        
        return {
            "message": "Label cancelled successfully",
            "refund_amount": response.get("refundAmount")
        }

    def _filter_lowest_rates(self, rate_items: List[Dict]) -> List[Dict]:
        """
        Keep only the lowest rate per mail class.
        """
        best_rates = {}
        for item in rate_items:
            mail_class = item.get("mailClass")
            price = float(item.get("price", 0))

            if mail_class and (
                mail_class not in best_rates or price < best_rates[mail_class]["price"]
            ):
                # Keep as best rate
                best_rates[mail_class] = {
                    **item,
                    "price": price  # make sure it's numeric
                }
        return list(best_rates.values())

