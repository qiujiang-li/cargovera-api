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
from typing import Dict, Any, List, Optional
from datetime import datetime
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
    

    def get_usps_signature_code(option: str, mailClass: str = "USPS_GROUND_ADVANTAGE") -> int:
        """
        Returns the USPS extra service code for a given signature option and shipping method.

        Args:
            option (str): Custom signature option (e.g., 'direct', 'none', 'adult')
            shipping_method (str): Shipping method (e.g., 'USPS_GROUND_ADVANTAGE', 'express')

        Returns:
            int: USPS extra service code

        Raises:
            ValueError: If option or shipping method is invalid
        """
        try:
            return _signature_options_map[mailClass][option]
        except KeyError:
            raise ValueError(f"Invalid combination: shipping_method='{mailClass}', option='{option}'")

    

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

                logger.debug(f"USPS response ({method}) from {url}: {response.text}")

                result = response.json()
                if response.status_code == 200:
                    return result
                elif 400 <= response.status_code < 500:
                    raise ExternalServiceClientError(f"Client error: {response.text}")
                else:
                    raise ExternalServiceServerError(f"Server error: {response.text}")
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

    async def buy_label(self,                  
                    shipper_address: Dict[str, str],
                    recipient_address: Dict[str, str],
                    serviceType: str,
                    packages: List[Dict[str, Any]],
                    signature_option: str,
                    ship_date: Optional[str]
                    ):

        """Purchase a shipping label from USPS"""
        from_first_name, from_last_name = parse_name(shipper_address.contact_name)
        from_zip_code, from_zip_code_plus = parse_zipcode(shipper_address.zip_code)
        to_first_name, to_last_name = parse_name(recipient_address.contact_name)
        to_zip_code, to_zip_code_plus = parse_zipcode(recipient_address.zip_code)
        extra_services = get_usps_signature_code(signature_option, serviceType)
        package = packages[0]
        if ship_date is None:
            ship_date = datetime.now().strftime("%Y-%m-%d")
        request_data = {
            "toAddress": {
                "firstName": to_first_name,
                "lastName": to_last_name,
                "streetAddress": recipient_address.street_line1,
                "secondaryAddress": recipient_address.street_line2,
                "city": recipient_address.city,
                "state": recipient_address.state,
                "ZIPCode": to_zip_code,
                "ZIPPlus4": to_zip_code_plus
            },
            "fromAddress": {
                "firstName": from_first_name,
                "lastName": from_last_name,
                "streetAddress": shipper_address.street_line1,
                "secondaryAddress": shipper_address.street_line2,
                "city": shipper_address.city,
                "state": shipper_address.state,
                "ZIPCode": from_zip_code
            },
            "packageDescription": {
                "mailClass": serviceType,
                "rateIndicator": "SP",
                "weightUOM": "lb",
                "weight": package.get("weight", {}).get("value"),
                "dimensionsUOM": "in",
                "length": package.get("dimensions",{}).get("length"),
                "height": package.get("dimensions",{}).get("height"),
                "width": package.get("dimensions",{}).get("width"),
                "processingCategory": "NONSTANDARD",
                "mailingDate": ship_date,
                "extraServices": extra_services,
                "destinationEntryFacilityType": "NONE"
            }
        }

        result = await self._make_request("POST", "/prices/v3/base-rates-list/search", request_data)
        # Process USPS response format
        logger.debug(f"response from usps rates search {result}")
    
            
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

