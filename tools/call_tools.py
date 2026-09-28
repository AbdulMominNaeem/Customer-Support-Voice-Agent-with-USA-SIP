import asyncio
import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import aiohttp

from livekit import rtc
from livekit.agents import RunContext, function_tool, get_job_context

from database import (
    appointments_collection,
    messages_collection,
)


DATA_DIR = Path(__file__).parent.parent / "data"

# Optional: every booking and message is POSTed here as JSON, so the owner
# gets it instantly (Zapier, Make, n8n, or a Slack/Discord webhook)
NOTIFY_WEBHOOK_URL = os.getenv("NOTIFY_WEBHOOK_URL")


def _save_record(collection, filename: str, record: dict) -> None:
    if collection is not None:
        # insert_one adds an ObjectId to the dict, so give it a copy
        collection.insert_one(dict(record))
        return

    # No MongoDB configured: append to a local JSON Lines file
    DATA_DIR.mkdir(exist_ok=True)

    with open(DATA_DIR / filename, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


async def _notify(kind: str, record: dict) -> None:
    if not NOTIFY_WEBHOOK_URL:
        return

    payload = {
        "kind": kind,
        "business": os.getenv("BUSINESS_NAME", ""),
        # Plain-text summary, so Slack/Discord webhooks show something readable
        "text": f"New {kind} for {os.getenv('BUSINESS_NAME', 'the business')}: "
        + ", ".join(f"{k}: {v}" for k, v in record.items() if v not in ("", None)),
        "record": record,
    }

    try:
        async with aiohttp.ClientSession() as http:
            async with http.post(
                NOTIFY_WEBHOOK_URL,
                data=json.dumps(payload, default=str),
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status >= 400:
                    print("Notify webhook returned", resp.status)

    except Exception as e:
        # The record is already saved, so a failed notification isn't fatal
        print("Notify webhook failed:", e)


def _sip_participant() -> rtc.RemoteParticipant | None:
    room = get_job_context().room

    for participant in room.remote_participants.values():
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            return participant

    return None


def _caller_number() -> str | None:
    participant = _sip_participant()
    return participant.attributes.get("sip.phoneNumber") if participant else None


@function_tool()
async def book_appointment(
    context: RunContext,
    appointment_type: str,
    customer_name: str,
    preferred_date: str,
    preferred_time: str,
    phone_number: str = "",
    address: str = "",
    notes: str = "",
    caller_language: str = "English",
) -> str:
    """
    Book an appointment, service visit, estimate, consultation, or reservation.

    Only call this after collecting the caller's name and their preferred
    date and time, and after confirming the details with the caller.

    Args:
        appointment_type: What is being booked, in English, e.g. "AC repair visit",
            "teeth cleaning", "oil change", "table for 4", "haircut with Maria".
        customer_name: The caller's full name.
        preferred_date: The preferred date, e.g. "Tuesday, October 6".
        preferred_time: The preferred time, e.g. "10 AM" or "afternoon".
        phone_number: Contact number, only if the caller gave a different one.
        address: Service address, if the visit is at the caller's home or business.
        notes: Other details in English, e.g. the problem, vehicle, insurance, party size.
        caller_language: The language the caller spoke, e.g. "Spanish".
    """

    appointment = {
        "type": appointment_type,
        "customer_name": customer_name,
        "phone_number": phone_number or _caller_number(),
        "preferred_date": preferred_date,
        "preferred_time": preferred_time,
        "address": address,
        "notes": notes,
        "caller_language": caller_language,
        "status": "pending_confirmation",
        "room": get_job_context().room.name,
        "created_at": datetime.now(timezone.utc),
    }

    print("NEW APPOINTMENT:", appointment)

    try:
        await asyncio.to_thread(
            _save_record,
            appointments_collection,
            "appointments.jsonl",
            appointment,
        )

    except Exception as e:
        print("Failed to save appointment:", e)

        return json.dumps({
            "success": False,
            "error": "Unable to save the booking right now. Offer to take a message instead.",
        })

    await _notify("appointment", appointment)

    return json.dumps({
        "success": True,
        "message": "Appointment request saved. The team will call or text to confirm the exact time.",
    })


@function_tool()
async def take_message(
    context: RunContext,
    message_type: Literal[
        "urgent",
        "quote_request",
        "callback_request",
        "complaint",
        "order",
        "other",
    ],
    customer_name: str,
    description: str,
    phone_number: str = "",
    address: str = "",
    urgent: bool = False,
    caller_language: str = "English",
) -> str:
    """
    Take a message for the team and return a reference number.

    Use this for urgent problems, quote requests, callback requests,
    complaints, orders, or anything you can't answer yourself.

    Args:
        message_type: The kind of message.
        customer_name: The caller's full name.
        description: A clear summary of what the caller needs, written in English.
        phone_number: Contact number, only if the caller gave a different one.
        address: The caller's address, if relevant (e.g. for a service call).
        urgent: True if it can't wait, like a leak, no heat, no AC, or severe pain.
        caller_language: The language the caller spoke, e.g. "Mandarin".
    """

    reference_number = str(random.randint(100000, 999999))

    message = {
        "reference_number": reference_number,
        "type": message_type,
        "customer_name": customer_name,
        "phone_number": phone_number or _caller_number(),
        "description": description,
        "address": address,
        "urgent": urgent or message_type == "urgent",
        "caller_language": caller_language,
        "status": "open",
        "room": get_job_context().room.name,
        "created_at": datetime.now(timezone.utc),
    }

    print("NEW MESSAGE:", message)

    try:
        await asyncio.to_thread(
            _save_record,
            messages_collection,
            "messages.jsonl",
            message,
        )

    except Exception as e:
        print("Failed to save message:", e)

        return json.dumps({
            "success": False,
            "error": "Unable to save the message right now.",
        })

    await _notify("message", message)

    return json.dumps({
        "success": True,
        "reference_number": reference_number,
    })


@function_tool()
async def transfer_to_human(
    context: RunContext,
) -> str:
    """
    Transfer the call to a person at the business.

    Use this when the caller asks to speak to a person, is very upset,
    or needs help you can't provide. Tell the caller you're connecting
    them before calling this.
    """

    transfer_to = os.getenv("HUMAN_TRANSFER_NUMBER", "").strip()
    participant = _sip_participant()

    if not transfer_to or participant is None:
        return json.dumps({
            "success": False,
            "error": "Transfer isn't available right now. Offer to take a message instead.",
        })

    # A plain number like +15125550198 goes to the provider as a tel: URI
    if not transfer_to.startswith(("tel:", "sip:")):
        transfer_to = "tel:" + transfer_to

    # Let the "connecting you" message finish before transferring
    await context.wait_for_playout()

    try:
        await get_job_context().transfer_sip_participant(
            participant.identity,
            transfer_to,
            play_dialtone=True,
        )

    except Exception as e:
        print("Transfer failed:", e)

        return json.dumps({
            "success": False,
            "error": "The transfer failed. Offer to take a message instead.",
        })

    return json.dumps({
        "success": True,
    })


@function_tool()
async def end_call(
    context: RunContext,
) -> str:
    """
    Hang up the call.

    Use this only after the caller has said goodbye or the conversation
    is clearly finished. Say a short goodbye before calling this.
    """

    # Let the goodbye finish before hanging up
    await context.wait_for_playout()

    await get_job_context().delete_room()

    return json.dumps({
        "success": True,
    })
