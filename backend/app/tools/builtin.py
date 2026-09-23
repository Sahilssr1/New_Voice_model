"""Built-in demo tools registered on the global ToolRegistry.

These use fake in-memory data so the MVP works without external systems.
Each tool is a plain function with an OpenAI-style JSON schema; swap the
function bodies for real integrations later without touching the pipeline.
"""

from __future__ import annotations

import time
import uuid

from .registry import ToolRegistry

# -- fake demo data ---------------------------------------------------------
_ORDERS = {
    "12345": {
        "order_id": "12345",
        "status": "out_for_delivery",
        "status_label": "Out for delivery",
        "eta": "tomorrow by 6 PM",
        "items": ["Wireless headphones", "USB-C cable"],
        "total": "₹2,499",
    },
    "67890": {
        "order_id": "67890",
        "status": "delivered",
        "status_label": "Delivered",
        "eta": "delivered yesterday",
        "items": ["Coffee mug"],
        "total": "₹499",
    },
}

_CUSTOMERS = {
    "C1001": {
        "customer_id": "C1001",
        "name": "Aarav Sharma",
        "email": "aarav.sharma@example.com",
        "phone": "+91-98765-43210",
        "tier": "gold",
    },
}


def get_order_status(order_id: str) -> dict:
    """Look up the status of an order."""
    order = _ORDERS.get(str(order_id))
    if order is None:
        return {"found": False, "order_id": str(order_id)}
    return {"found": True, **order}


def get_customer_details(customer_id: str) -> dict:
    """Look up customer details by customer id."""
    customer = _CUSTOMERS.get(str(customer_id))
    if customer is None:
        return {"found": False, "customer_id": str(customer_id)}
    return {"found": True, **customer}


def create_support_ticket(subject: str, description: str = "") -> dict:
    """Create a support ticket."""
    ticket_id = f"TKT-{int(time.time()) % 100000:05d}"
    return {
        "ticket_id": ticket_id,
        "subject": subject,
        "description": description,
        "status": "open",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def schedule_callback(phone: str, time: str) -> dict:
    """Schedule a callback to a phone number at the given time."""
    return {
        "scheduled": True,
        "callback_id": f"CB-{uuid.uuid4().hex[:8]}",
        "phone": phone,
        "time": time,
    }


def transfer_to_human(reason: str = "") -> dict:
    """Transfer the call to a human agent."""
    return {
        "transferred": True,
        "queue_position": 3,
        "estimated_wait_min": 5,
        "reason": reason,
    }


def register_builtin_tools(registry: ToolRegistry) -> ToolRegistry:
    """Register the 5 built-in demo tools on a registry."""
    registry.register(
        "get_order_status",
        "Look up the current status of a customer order by order id.",
        {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The order ID, e.g. '12345'"}
            },
            "required": ["order_id"],
        },
        get_order_status,
    )
    registry.register(
        "get_customer_details",
        "Look up customer details by customer id.",
        {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "The customer ID, e.g. 'C1001'"}
            },
            "required": ["customer_id"],
        },
        get_customer_details,
    )
    registry.register(
        "create_support_ticket",
        "Create a customer support ticket with a subject and description.",
        {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["subject"],
        },
        create_support_ticket,
    )
    registry.register(
        "schedule_callback",
        "Schedule a callback to a phone number at a given time.",
        {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "time": {"type": "string", "description": "When to call back, e.g. 'tomorrow 10am'"},
            },
            "required": ["phone", "time"],
        },
        schedule_callback,
    )
    registry.register(
        "transfer_to_human",
        "Transfer the conversation to a human agent.",
        {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why the transfer is needed"}
            },
            "required": [],
        },
        transfer_to_human,
    )
    return registry


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    return register_builtin_tools(registry)


# Global registry with built-ins, shared by the voice gateway.
default_registry = build_default_registry()


def get_registry(names: list[str] | None = None) -> ToolRegistry:
    """Return a registry of built-in tools, optionally filtered by name."""
    return default_registry.subset(names)
