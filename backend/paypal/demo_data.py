"""Demo and fallback PayPal datasets for ResolveIQ.

When PayPal sandbox credentials (PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET) are not
configured or when sandbox API calls fail, ResolveIQ provides clearly labelled
demo data that mirrors the official PayPal REST API schema.
Every demo record is explicitly flagged with `is_sandbox=False` and `source='demo'`.
"""
from __future__ import annotations

from typing import Any

DEMO_DISPUTES: list[dict[str, Any]] = [
    {
        "dispute_id": "PP-D-849201",
        "create_time": "2026-10-15T09:20:00.000Z",
        "update_time": "2026-10-18T14:45:00.000Z",
        "dispute_amount": {"currency_code": "USD", "value": "189.50"},
        "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "status": "WAITING_FOR_SELLER_RESPONSE",
        "dispute_state": "REQUIRED_ACTION",
        "dispute_life_cycle_stage": "CHARGEBACK",
        "dispute_channel": "INTERNAL",
        "allowed_response_options": ["PROVIDE_EVIDENCE", "ACCEPT_CLAIM", "MAKE_OFFER_TO_RESOLVE"],
        "seller_response_due_date": "2026-11-20T23:59:59.000Z",
        "customer_complaint": "Ordered an ergonomic mechanical keyboard on Oct 10 (Order #ORD-77410). The tracking number was never updated and the parcel was never delivered to my address.",
        "merchant_context": "Item was shipped on Oct 11 via FedEx Home Delivery with signature service under tracking 789456123012. Carrier confirms delivery on Oct 14.",
        "disputed_transactions": [
            {
                "seller_transaction_id": "7TY9843219084321",
                "buyer_transaction_id": "9LK8392018374829",
                "create_time": "2026-10-10T14:12:00.000Z",
                "gross_amount": {"currency_code": "USD", "value": "189.50"},
                "buyer": {"name": "Eleanor Vance", "email": "eleanor.vance@example.com"},
                "seller": {"email": "orders@apexhardware.io"},
                "items": [
                    {
                        "item_name": "Apex Pro Split Ergonomic Keyboard (Titanium Grey)",
                        "item_description": "Wireless Mechanical Keyboard",
                        "item_quantity": "1",
                        "item_unit_price": {"currency_code": "USD", "value": "189.50"},
                    }
                ],
            }
        ],
        "is_sandbox": False,
        "source": "demo",
    },
    {
        "dispute_id": "PP-D-910482",
        "create_time": "2026-10-22T11:15:00.000Z",
        "update_time": "2026-10-24T16:00:00.000Z",
        "dispute_amount": {"currency_code": "USD", "value": "450.00"},
        "reason": "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED",
        "status": "WAITING_FOR_SELLER_RESPONSE",
        "dispute_state": "REQUIRED_ACTION",
        "dispute_life_cycle_stage": "INQUIRY",
        "dispute_channel": "INTERNAL",
        "allowed_response_options": ["PROVIDE_EVIDENCE", "ACCEPT_CLAIM", "MAKE_OFFER_TO_RESOLVE"],
        "seller_response_due_date": "2026-11-25T23:59:59.000Z",
        "customer_complaint": "Received model X100 instead of the Pro Edition with titanium switches described on the listing. Missing promised wireless dongle.",
        "merchant_context": "The order was fulfilled per SKU-990-PRO. The buyer opened inquiry before contacting support for the packaged dongle located under base tray.",
        "disputed_transactions": [
            {
                "seller_transaction_id": "8UU1029384756102",
                "buyer_transaction_id": "3FF8472910394821",
                "create_time": "2026-10-18T18:04:00.000Z",
                "gross_amount": {"currency_code": "USD", "value": "450.00"},
                "buyer": {"name": "Marcus Aurelius Vance", "email": "marcus.v@example.org"},
                "seller": {"email": "support@techcraft-audio.com"},
                "items": [
                    {
                        "item_name": "Studio Master Reference Audio Monitor Pair",
                        "item_description": "Active Nearfield Studio Monitors",
                        "item_quantity": "1",
                        "item_unit_price": {"currency_code": "USD", "value": "450.00"},
                    }
                ],
            }
        ],
        "is_sandbox": False,
        "source": "demo",
    },
    {
        "dispute_id": "PP-D-739104",
        "create_time": "2026-10-28T08:00:00.000Z",
        "update_time": "2026-10-29T10:30:00.000Z",
        "dispute_amount": {"currency_code": "USD", "value": "75.25"},
        "reason": "UNAUTHORISED",
        "status": "UNDER_REVIEW",
        "dispute_state": "UNDER_REVIEW",
        "dispute_life_cycle_stage": "CHARGEBACK",
        "dispute_channel": "EXTERNAL",
        "allowed_response_options": ["PROVIDE_EVIDENCE"],
        "seller_response_due_date": "2026-11-18T23:59:59.000Z",
        "customer_complaint": "Cardholder flagged transaction as fraudulent unauthorized card activity.",
        "merchant_context": "Order placed with matching billing and shipping address, verified with 3D Secure and completed from customer's regular IP.",
        "disputed_transactions": [
            {
                "seller_transaction_id": "9JJ2837461928374",
                "buyer_transaction_id": "1AA9384726154829",
                "create_time": "2026-10-26T07:22:00.000Z",
                "gross_amount": {"currency_code": "USD", "value": "75.25"},
                "buyer": {"name": "Sarah Connor", "email": "sarah.c@skytech.net"},
                "seller": {"email": "billing@cloudservices-corp.net"},
                "items": [
                    {
                        "item_name": "Pro Developer Annual Subscription Renewal",
                        "item_description": "Cloud hosting annual tier",
                        "item_quantity": "1",
                        "item_unit_price": {"currency_code": "USD", "value": "75.25"},
                    }
                ],
            }
        ],
        "is_sandbox": False,
        "source": "demo",
    },
    {
        "dispute_id": "PP-D-628405",
        "create_time": "2026-11-01T10:14:00.000Z",
        "update_time": "2026-11-02T12:00:00.000Z",
        "dispute_amount": {"currency_code": "USD", "value": "120.00"},
        "reason": "DUPLICATE_TRANSACTION",
        "status": "WAITING_FOR_SELLER_RESPONSE",
        "dispute_state": "REQUIRED_ACTION",
        "dispute_life_cycle_stage": "INQUIRY",
        "dispute_channel": "INTERNAL",
        "allowed_response_options": ["PROVIDE_EVIDENCE", "ACCEPT_CLAIM"],
        "seller_response_due_date": "2026-11-28T23:59:59.000Z",
        "customer_complaint": "I was billed twice on the same day for a single software subscription order.",
        "merchant_context": "Customer placed two distinct orders for two separate user seats (License A and License B). Two separate confirmation emails and activation keys were delivered.",
        "disputed_transactions": [
            {
                "seller_transaction_id": "4KK7765123498123",
                "buyer_transaction_id": "8ZZ5541234567890",
                "create_time": "2026-11-01T09:40:00.000Z",
                "gross_amount": {"currency_code": "USD", "value": "120.00"},
                "buyer": {"name": "Jordan Bell", "email": "jordan.bell@cyberlog.io"},
                "seller": {"email": "billing@saastoolkit.com"},
                "items": [
                    {
                        "item_name": "Enterprise Seat License #2 (Additional Team Seat)",
                        "item_description": "Multi-user annual add-on seat",
                        "item_quantity": "1",
                        "item_unit_price": {"currency_code": "USD", "value": "120.00"},
                    }
                ],
            }
        ],
        "is_sandbox": False,
        "source": "demo",
    },
    {
        "dispute_id": "PP-D-517392",
        "create_time": "2026-11-04T15:30:00.000Z",
        "update_time": "2026-11-05T09:15:00.000Z",
        "dispute_amount": {"currency_code": "USD", "value": "95.00"},
        "reason": "CREDIT_NOT_PROCESSED",
        "status": "WAITING_FOR_SELLER_RESPONSE",
        "dispute_state": "REQUIRED_ACTION",
        "dispute_life_cycle_stage": "CHARGEBACK",
        "dispute_channel": "INTERNAL",
        "allowed_response_options": ["PROVIDE_EVIDENCE", "ACCEPT_CLAIM"],
        "seller_response_due_date": "2026-11-22T23:59:59.000Z",
        "customer_complaint": "Merchant agreed to provide refund for returned goods, but refund was never processed to my account.",
        "merchant_context": "Store credit voucher #SC-9500 was issued immediately upon return receipt per customer agreement and terms of service. Voucher is active and available in customer account.",
        "disputed_transactions": [
            {
                "seller_transaction_id": "2MM9988776655443",
                "buyer_transaction_id": "5PP1122334455667",
                "create_time": "2026-10-20T16:20:00.000Z",
                "gross_amount": {"currency_code": "USD", "value": "95.00"},
                "buyer": {"name": "Clara Oswald", "email": "clara.o@timetravel.org"},
                "seller": {"email": "returns@vintagestore.com"},
                "items": [
                    {
                        "item_name": "Vintage Wool Overcoat (Size M)",
                        "item_description": "Pre-owned wool coat",
                        "item_quantity": "1",
                        "item_unit_price": {"currency_code": "USD", "value": "95.00"},
                    }
                ],
            }
        ],
        "is_sandbox": False,
        "source": "demo",
    },
]

DEMO_TRANSACTIONS: list[dict[str, Any]] = [
    {
        "transaction_info": {
            "paypal_account_id": "W9R8K7L6M5N4P",
            "transaction_id": "7TY9843219084321",
            "transaction_event_code": "T0000",
            "transaction_initiation_date": "2026-10-10T14:12:00.000Z",
            "transaction_updated_date": "2026-10-10T14:12:05.000Z",
            "transaction_amount": {"currency_code": "USD", "value": "189.50"},
            "fee_amount": {"currency_code": "USD", "value": "-5.80"},
            "net_amount": {"currency_code": "USD", "value": "183.70"},
            "transaction_status": "S",
            "protection_eligibility": "ELIGIBLE",
        },
        "payer_info": {
            "account_id": "CUST-883921",
            "email_address": "eleanor.vance@example.com",
            "payer_name": {"given_name": "Eleanor", "surname": "Vance"},
            "country_code": "US",
        },
        "shipping_info": {
            "name": "Eleanor Vance",
            "address": {
                "line1": "742 Evergreen Terrace",
                "city": "Springfield",
                "state": "OR",
                "postal_code": "97477",
                "country_code": "US",
            },
        },
        "cart_info": {
            "item_details": [
                {
                    "item_name": "Apex Pro Split Ergonomic Keyboard (Titanium Grey)",
                    "item_quantity": "1",
                    "item_unit_price": {"currency_code": "USD", "value": "189.50"},
                    "item_amount": {"currency_code": "USD", "value": "189.50"},
                }
            ]
        },
        "is_sandbox": False,
        "source": "demo",
    },
    {
        "transaction_info": {
            "paypal_account_id": "W9R8K7L6M5N4P",
            "transaction_id": "8UU1029384756102",
            "transaction_event_code": "T0000",
            "transaction_initiation_date": "2026-10-18T18:04:00.000Z",
            "transaction_updated_date": "2026-10-18T18:04:08.000Z",
            "transaction_amount": {"currency_code": "USD", "value": "450.00"},
            "fee_amount": {"currency_code": "USD", "value": "-13.35"},
            "net_amount": {"currency_code": "USD", "value": "436.65"},
            "transaction_status": "S",
            "protection_eligibility": "ELIGIBLE",
        },
        "payer_info": {
            "account_id": "CUST-390481",
            "email_address": "marcus.v@example.org",
            "payer_name": {"given_name": "Marcus", "surname": "Vance"},
            "country_code": "US",
        },
        "shipping_info": {
            "name": "Marcus Aurelius Vance",
            "address": {
                "line1": "100 Market St Suite 400",
                "city": "San Francisco",
                "state": "CA",
                "postal_code": "94105",
                "country_code": "US",
            },
        },
        "cart_info": {
            "item_details": [
                {
                    "item_name": "Studio Master Reference Audio Monitor Pair",
                    "item_quantity": "1",
                    "item_unit_price": {"currency_code": "USD", "value": "450.00"},
                    "item_amount": {"currency_code": "USD", "value": "450.00"},
                }
            ]
        },
        "is_sandbox": False,
        "source": "demo",
    },
]
