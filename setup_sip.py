"""
One-time setup: connects your US SIP phone number(s) to this agent on LiveKit.

It creates (or updates):
  1. An inbound SIP trunk that accepts calls to SIP_PHONE_NUMBERS
  2. A dispatch rule that puts each call in its own room with the agent

Works with any US SIP provider (Twilio, Telnyx, SignalWire, Plivo,
Vonage, Bandwidth...). See README.md for provider-specific steps.

Run it once:  python setup_sip.py
Run it again after changing SIP_* values in .env.local to update everything.
"""

import asyncio
import os
import re

from dotenv import load_dotenv
from livekit import api


load_dotenv(".env.local")


# Must match AGENT_DISPATCH_NAME in agent.py
AGENT_DISPATCH_NAME = os.getenv("AGENT_DISPATCH_NAME", "front-desk")

TRUNK_NAME = "front-desk-inbound"
DISPATCH_RULE_NAME = "front-desk-dispatch"

# Trunks made by earlier versions of this script, updated in place instead of duplicated
LEGACY_TRUNK_NAMES = ("car-support-inbound",)

E164 = re.compile(r"^\+[1-9]\d{7,14}$")
US_E164 = re.compile(r"^\+1[2-9]\d{2}[2-9]\d{6}$")


def _env_list(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def _phone_numbers() -> list[str]:
    # SIP_PHONE_NUMBER is the older single-number setting
    numbers = _env_list("SIP_PHONE_NUMBERS") or _env_list("SIP_PHONE_NUMBER")

    if not numbers:
        raise ValueError(
            "SIP_PHONE_NUMBERS is missing from .env.local (e.g. +15125550198)"
        )

    for number in numbers:
        if not E164.match(number):
            raise ValueError(
                f"{number!r} isn't in E.164 format. US numbers look like +15125550198"
            )

        if not US_E164.match(number):
            print(f"Note: {number} isn't a US/Canada number, continuing anyway.")

    return numbers


async def main():

    phone_numbers = _phone_numbers()

    lkapi = api.LiveKitAPI()

    try:

        # ==========================================
        # INBOUND TRUNK
        # ==========================================

        trunk_info = api.SIPInboundTrunkInfo(
            name=TRUNK_NAME,
            numbers=phone_numbers,
            # Only accept calls from your provider's IPs, if set
            allowed_addresses=_env_list("SIP_ALLOWED_ADDRESSES"),
            # Digest auth, if your provider uses a username/password
            auth_username=os.getenv("SIP_AUTH_USERNAME", ""),
            auth_password=os.getenv("SIP_AUTH_PASSWORD", ""),
            # Telephony noise cancellation
            krisp_enabled=True,
        )

        all_trunks = await lkapi.sip.list_inbound_trunk(
            api.ListSIPInboundTrunkRequest()
        )

        existing = [
            t for t in all_trunks.items
            if t.name in (TRUNK_NAME, *LEGACY_TRUNK_NAMES)
        ]

        if existing:
            # Re-running after changing .env.local updates the same trunk,
            # e.g. a new phone number or credentials
            trunk = await lkapi.sip.update_inbound_trunk(
                existing[0].sip_trunk_id,
                trunk_info,
            )
            print("Updated inbound trunk:", trunk.sip_trunk_id, list(trunk.numbers))

        else:
            trunk = await lkapi.sip.create_inbound_trunk(
                api.CreateSIPInboundTrunkRequest(trunk=trunk_info)
            )
            print("Created inbound trunk:", trunk.sip_trunk_id, list(trunk.numbers))

        # ==========================================
        # DISPATCH RULE
        # ==========================================

        rule_info = api.SIPDispatchRuleInfo(
            name=DISPATCH_RULE_NAME,
            trunk_ids=[trunk.sip_trunk_id],
            # Each caller gets their own room, e.g. call-+15125550198_abc
            rule=api.SIPDispatchRule(
                dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                    room_prefix="call-",
                )
            ),
            room_config=api.RoomConfiguration(
                agents=[
                    api.RoomAgentDispatch(
                        agent_name=AGENT_DISPATCH_NAME,
                    )
                ]
            ),
        )

        existing_rules = await lkapi.sip.list_dispatch_rule(
            api.ListSIPDispatchRuleRequest(trunk_ids=[trunk.sip_trunk_id])
        )

        if existing_rules.items:
            # Keeps the rule pointed at the current AGENT_DISPATCH_NAME
            rule = await lkapi.sip.update_dispatch_rule(
                existing_rules.items[0].sip_dispatch_rule_id,
                rule_info,
            )
            print("Updated dispatch rule:", rule.sip_dispatch_rule_id)

        else:
            rule = await lkapi.sip.create_dispatch_rule(
                api.CreateSIPDispatchRuleRequest(dispatch_rule=rule_info)
            )
            print("Created dispatch rule:", rule.sip_dispatch_rule_id)

    finally:
        await lkapi.aclose()

    print()
    print("Done. Last step: point your SIP provider's trunk at your LiveKit SIP URI")
    print("(LiveKit Cloud dashboard > Settings > SIP URI). See README.md.")


if __name__ == "__main__":
    asyncio.run(main())
