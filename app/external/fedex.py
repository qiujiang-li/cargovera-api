# app/services/fedex_service.py
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

logger = logging.getLogger(__name__)

class FedExService:
    _signature_options_map = {
        'carrier_default': 'SERVICE_DEFAULT',
        'none': 'NO_SIGNATURE_REQUIRED',
        'direct': 'DIRECT',
        'indirect': 'INDIRECT',
        'adult': 'ADULT',
    }
    def __init__(self):
        self.base_url = os.getenv("FEDEX_BASE_URL")
        self.account_number = os.getenv("FEDEX_ACCOUNT_NUMBER")
        self.client_id = os.getenv("FEDEX_CLIENT_ID")
        self.client_secret = os.getenv("FEDEX_CLIENT_SECRET")
        self.default_contact_phone = os.getenv("DEFAULT_CONTACT_PHONE")
    
    def get_signature_option(self, signature_option: str) -> str:
        try:
            return self._signature_options_map[signature_option]
        except KeyError:
            raise ValueError(f"Unsupported FedEx signature option: '{signature_option}'")

    @async_cache(ttl=3500)
    async def _get_fedex_access_token(self) -> str:
        logger.debug("Fetching new FedEx access token" )
        payload = {
            "grant_type": "client_credentials",  # <- or 'client_credentials' if that's correct for your app
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{self.base_url}/oauth/token",
                data=payload,   # data= sends form-encoded body
            )
            response.raise_for_status()
            data = response.json()
            return data["access_token"]

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, ExternalServiceServerError, httpx.ReadTimeout)),  # retry on HTTP exceptions
        wait=wait_exponential(multiplier=1, min=3, max=10),  # exponential backoff: 2s, 4s, 8s, ...
        stop=stop_after_attempt(3),  # retry up to 3 times
        reraise=True
    )
    async def get_rates(self,
                    ship_date: str,
                    shipper_address: Dict[str, str],
                    recipient_address: Dict[str, str],
                    packages: List[Dict[str, Any]],
                    pickup_type: Optional[str] = "DROPOFF_AT_FEDEX_LOCATION",
                    packaging_type: str = "YOUR_PACKAGING",
                    rate_request_type: List[str] = None,
                    return_transit_times: bool = True) -> Dict[str, Any]:
            """
            Get rate quotes from FedEx.
            
            Args:
                account_number: Your FedEx account number
                ship_date: Ship date in YYYY-MM-DD format
                shipper_address: Shipper address dictionary
                recipient_address: Recipient address dictionary
                packages: List of package dictionaries with dimensions and weight
                service_type: Specific service type (optional, returns all if not specified)
                packaging_type: Packaging type (default: "YOUR_PACKAGING")
                rate_request_type: List of rate types to request (default: ["LIST", "ACCOUNT"])
                return_transit_times: Whether to include transit times (default: True)
                
            Returns:
                dict: Rate response from FedEx API
                
            Example:
                shipper = {
                    "streetLines": ["123 Main St"],
                    "city": "Memphis",
                    "stateOrProvinceCode": "TN",
                    "postalCode": "38115",
                    "countryCode": "US"
                }
                
                recipient = {
                    "streetLines": ["456 Oak Ave"],
                    "city": "Los Angeles", 
                    "stateOrProvinceCode": "CA",
                    "postalCode": "90210",
                    "countryCode": "US"
                }
                
                packages = [{
                    "weight": {"units": "LB", "value": 5.0},
                    "dimensions": {
                        "length": 10,
                        "width": 8,
                        "height": 6,
                        "units": "IN"
                    }
                }]
            """
            # Get valid access token
            token = await self._get_fedex_access_token()
            
            # Prepare request headers
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-locale": "en_US"
            }
            
            # Set default rate request types
            if rate_request_type is None:
                rate_request_type = ["ACCOUNT", "LIST"]
            
            # Prepare request body
            request_body = {
                "accountNumber": {
                    "value": self.account_number
                },
                "rateRequestControlParameters": {
                    "returnTransitTimes": return_transit_times,
                    "servicesNeededOnRateFailure": True,
                    "variableOptions": "FREIGHT_GUARANTEE",
                    "rateSortOrder": "SERVICENAMETRADITIONAL"
                },
                "requestedShipment": {
                    "shipper": {
                        "address": shipper_address
                    },
                    "recipient": {
                        "address": recipient_address
                    },
                    "shipDateStamp": ship_date,
                    "pickupType": pickup_type,
                    "rateRequestType": rate_request_type,
                    "requestedPackageLineItems": []
                }
            }
            
            # Add service type if specified
            # if service_type:
            #     print(f"service_type: {service_type}")
            #     request_body["requestedShipment"]["serviceType"] = service_type
                
            # Add packaging type
            request_body["requestedShipment"]["packagingType"] = packaging_type
            
            # Process packages
            for i, package in enumerate(packages):
                package_item = {
                    "sequenceNumber": i + 1,
                    "weight": package["weight"]
                }
                
                # Add dimensions if provided
                if "dimensions" in package:
                    package_item["dimensions"] = package["dimensions"]
                    
                # Add declared value if provided
                if "declared_value" in package:
                    package_item["declaredValue"] = package["declared_value"]
                    
                request_body["requestedShipment"]["requestedPackageLineItems"].append(package_item)
            
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.post(
                            f"{self.base_url}/rate/v1/rates/quotes",
                            json=request_body,
                            headers= headers
                        )
                        result = response.json()
                        logger.debug(f"resonse get rates from fedex: {result}")
                        if response.status_code == 200:
                            return result.get("output", {}).get("rateReplyDetails", [])
                        elif 400 <= response.status_code < 500:
                            raise ExternalServiceClientError(f"Failed to get rates from FedEx.")
                        else:
                            raise ExternalServiceServerError(f"Failed to get rates from FedEx.")
            except  httpx.RequestError as e:
                logger.exception(f"failed to get rates from FedEx {e}")
                raise ExternalServiceException(f"Request failed: {str(e)}")

    async def get_quick_rates(self,
                        pickup_postal_code: str,
                        pickup_country_code: str,
                        destination_postal_code: str,
                        destination_country_code: str,
                        packages: List[Dict[str, Any]]):

        """
        Get quick rate quotes without detailed package information.
        
        Args:
            pickup_postal_code: Origin postal code
            pickup_country_code: Origin country code (e.g., "US")
            destination_postal_code: Destination postal code
            destination_country_code: Destination country code
            weight_value: Package weight value
            weight_units: Weight units ("LB" or "KG")
            
        Returns:
            dict: Quick rate response from FedEx API
        """
        # Use minimal address information for quick rates
        shipper_address = {
            "postalCode": pickup_postal_code,
            "countryCode": pickup_country_code
        }
        
        recipient_address = {
            "postalCode": destination_postal_code,
            "countryCode": destination_country_code
        }
        # Use today's date for ship date
        ship_date = datetime.now().strftime("%Y-%m-%d")
        
        # For quick rates, we typically don't need an account number
        # Use "123456789" as a placeholder for testing
        return await self.get_rates(
            ship_date=ship_date,
            shipper_address=shipper_address,
            recipient_address=recipient_address,
            packages=packages,
            rate_request_type=["ACCOUNT", "LIST"]
        )

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, ExternalServiceServerError,httpx.ReadTimeout)),  # retry on HTTP exceptions
        wait=wait_exponential(multiplier=1, min=3, max=10),  # exponential backoff: 2s, 4s, 8s, ...
        stop=stop_after_attempt(3),  # retry up to 3 times
        reraise=True
    )
    async def buy_label(self,                  
                    shipper_address: Dict[str, str],
                    recipient_address: Dict[str, str],
                    serviceType: str,
                    total_weight: float,
                    packages: List[Dict[str, Any]],
                    ship_date: str,
                    pickup_type: str,
                    labelStockType: str,
                    mergeLabelDocOption: str,
                    ):
        # Get valid access token
        token = await self._get_fedex_access_token()
            
        # Prepare request headers
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-locale": "en_US"
        }

      # Use today's date for ship date
        if ship_date is None:
            ship_date = datetime.now().strftime("%Y-%m-%d")
        # Prepare request body
        request_body = self._create_request_body(shipper_address, recipient_address, serviceType, total_weight, 
                                                packages, ship_date, pickup_type, labelStockType, mergeLabelDocOption)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/ship/v1/shipments",
                    json=request_body,
                    headers={"Authorization": f"Bearer {token}"}
                )
                result = response.json()
                logger.debug(f"FedEx buy label response: status={response.status_code}, body={result}")
                if response.status_code == 200:
                    return result
                elif 400 <= response.status_code < 500:
                    raise ExternalServiceClientError(f"Failed to buy label from FedEx.")
                else:
                    raise ExternalServiceServerError(f"Failed to buy label from FedEx.")
        except httpx.RequestError as e:
            logger.exception(f"Request to FedEx failed.")
            raise ExternalServiceException(f"Request failed: {str(e)}")
        except Exception as e:
            logger.exception(f"Unexpected error when buying label from FedEx.")
            raise ExternalServiceException(f"Unexpected FedEx error: {str(e)}")

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, ExternalServiceServerError,httpx.ReadTimeout)),  # retry on HTTP exceptions
        wait=wait_exponential(multiplier=1, min=3, max=10),  # exponential backoff: 2s, 4s, 8s, ...
        stop=stop_after_attempt(3),  # retry up to 3 times
        reraise=True
    )
    async def cancel_label(self,
                    tracking_number: str):
                # Get valid access token
        token = await self._get_fedex_access_token()
            
        # Prepare request headers
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-locale": "en_US"
        }

        request_body = {
            "accountNumber": {
                "value": self.account_number
            },
            "emailShipment": "false",
            "senderCountryCode": "US",
            "deletionControl": "DELETE_ALL_PACKAGES",
            "trackingNumber": tracking_number
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.put(
                    f"{self.base_url}/ship/v1/shipments/cancel",
                    json=request_body,
                    headers={"Authorization": f"Bearer {token}"}
                )
                result = response.json()
                logger.debug(f"response from cancel shipment from fedex: {result}")
                if response.status_code == 200:
                    return result.get("output", {}).get("message","") == "Shipment is successfully cancelled"
                elif 400 <= response.status_code < 500:
                    raise ExternalServiceClientError(f"Failed to cancel label from FedEx.")
                else:
                    raise ExternalServiceServerError(f"Failed to cancel label from FedEx.")
        except  httpx.RequestError as e:
            logger.exception(f"failed to cancel label from FedEx.")
            raise ExternalServiceException(f"Request failed: {str(e)}")
        except Exception as e:
            logger.exception(f"Unexpected excepion when cancel label from FedEx.")
            raise ExternalServiceException(f"Unexpected FedEx error: {str(e)}")



    @retry(
        retry=retry_if_exception_type((httpx.HTTPError,ExternalServiceServerError,httpx.ReadTimeout)),  # retry on HTTP exceptions
        wait=wait_exponential(multiplier=1, min=3, max=10),  # exponential backoff: 2s, 4s, 8s, ...
        stop=stop_after_attempt(3),  # retry up to 3 times
        reraise=True
    )
    async def validate_shipment(self,
                    shipper_address: Dict[str, str],
                    recipient_address: Dict[str, str],
                    serviceType: str,
                    total_weight: float,
                    packages: List[Dict[str, Any]],
                    ship_date: str,
                    pickup_type: str,
                    labelStockType: str,
                    mergeLabelDocOption: str):

                # Get valid access token
                token = await self._get_fedex_access_token()
                    
                # Prepare request headers
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "X-locale": "en_US"
                }

                if ship_date is None:
                    ship_date = datetime.now().strftime("%Y-%m-%d")
                request_body = self._create_request_body(shipper_address, recipient_address, serviceType, total_weight, 
                    packages, ship_date, pickup_type, labelStockType, mergeLabelDocOption)
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:                 
                            response = await client.post(
                            f"{self.base_url}/ship/v1/shipments/packages/validate",
                            json=request_body,
                            headers={"Authorization": f"Bearer {token}"}
                        )
                            result = response.json()
                            logger.debug(f"fedex validation response {result}")
                            if response.status_code == 200:
                                return {"error": None, "success": True}
                            elif response.status_code == 400:
                                return {"error": result.get("errors", [])[0].get("code", ""), "success": False}
                            else: 
                                raise ExternalServiceServerError(f"Failed validate shipment with FedEx.")
                except httpx.HTTPError as e:
                    logger.exception(f"failed to validate shipment.")
                    raise ExternalServiceException(f"Request failed: {str(e)}")
                except Exception as e:
                    logger.exception(f"Unexpected exceion when validate shipment.")
                    raise ExternalServiceException(f"Unexcepted exception: {str(e)}")


    def _create_request_body(self,
                    shipper_address: Dict[str, str],
                    recipient_address: Dict[str, str],
                    serviceType: str,
                    total_weight: float,
                    packages: List[Dict[str, Any]],
                    ship_date: str,
                    pickup_type: str,
                    labelStockType: str,
                    mergeLabelDocOption: str):
            return {
                "accountNumber": {
                    "value": self.account_number
                },
                "labelResponseOptions": "URL_ONLY",
                "shipAction": "CONFIRM",
                "mergeLabelDocOption": mergeLabelDocOption,
                "requestedShipment": {
                    "shipper": {
                        "address": {
                            "streetLines": [shipper_address.street_line1, shipper_address.street_line2 if shipper_address.street_line2 is not None else ""],
                            "city": shipper_address.city,
                            "stateOrProvinceCode": shipper_address.state,
                            "postalCode": shipper_address.postal_code,
                            "countryCode": shipper_address.country_code
                        },
                        "contact": {
                            "personName": shipper_address.contact_name,
                            "phoneNumber": shipper_address.phone or self.default_contact_phone
                        }
                    },
                    "recipients":[{
                        "address": {
                            "streetLines": [recipient_address.street_line1, recipient_address.street_line2 if recipient_address.street_line2 is not None else ""],
                            "city": recipient_address.city,
                            "stateOrProvinceCode": recipient_address.state,
                            "postalCode": recipient_address.postal_code,
                            "countryCode": recipient_address.country_code
                        },
                        "contact": {
                            "personName": recipient_address.contact_name,
                            "phoneNumber": recipient_address.phone or self.default_contact_phone
                        }
                    }],
                    "pickupType": "DROPOFF_AT_FEDEX_LOCATION",
                    "serviceType": serviceType,
                    "packagingType": "YOUR_PACKAGING",
                    "totalWeight": total_weight,
                    "shippingChargesPayment": {
                        "paymentType": "SENDER",
                        "payor": {
                            "responsibleParty": {
                                "accountNumber": {
                                    "value": self.account_number
                                }}}
                    },
                    "labelSpecification": {
                        "labelFormatType": "COMMON2D",
                        "imageType": "PDF",
                        "labelStockType": labelStockType,
                        "labelStockSize": "4X6"
                    },
                    "shipDatestamp": ship_date,
                    "requestedPackageLineItems": packages
                }
        }

