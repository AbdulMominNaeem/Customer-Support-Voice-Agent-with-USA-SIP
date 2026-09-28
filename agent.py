import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from livekit import agents, rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
)

from livekit.plugins import (
    google,
    deepgram,
    cartesia,
)

from tools.call_tools import (
    book_appointment,
    take_message,
    transfer_to_human,
    end_call,
)


load_dotenv(".env.local")


# Must match AGENT_DISPATCH_NAME in setup_sip.py
AGENT_DISPATCH_NAME = os.getenv("AGENT_DISPATCH_NAME", "front-desk")

AGENT_NAME = os.getenv("AGENT_NAME", "Nova")

# Which industry template in knowledge/industries/ to use, e.g. home_services, dental
BUSINESS_TYPE = os.getenv("BUSINESS_TYPE", "home_services")

# These fill the {{PLACEHOLDERS}} in the knowledge files, so the same
# agent sounds custom-built for whichever business you set here
BUSINESS_PROFILE = {
    "BUSINESS_NAME": os.getenv("BUSINESS_NAME", "Summit Home Services"),
    "BUSINESS_CITY": os.getenv("BUSINESS_CITY", "Houston, Texas"),
    "SERVICE_AREA": os.getenv("SERVICE_AREA", "the greater Houston area"),
    "BUSINESS_ADDRESS": os.getenv("BUSINESS_ADDRESS", ""),
    "BUSINESS_PHONE": os.getenv("BUSINESS_PHONE", ""),
    "BUSINESS_WEBSITE": os.getenv("BUSINESS_WEBSITE", ""),
    "BUSINESS_HOURS": os.getenv(
        "BUSINESS_HOURS",
        "Monday to Friday 8 AM to 6 PM, Saturday 9 AM to 2 PM, closed Sunday",
    ),
}

BUSINESS_NAME = BUSINESS_PROFILE["BUSINESS_NAME"]
BUSINESS_TIMEZONE = os.getenv("BUSINESS_TIMEZONE", "America/Chicago")

# "realtime": Gemini Live speech-to-speech, hears and speaks dozens of languages
# "pipeline": Deepgram + Gemini + Cartesia, fewer languages (see README)
VOICE_MODE = os.getenv("VOICE_MODE", "realtime")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025")
GEMINI_VOICE = os.getenv("GEMINI_VOICE", "Aoede")
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "multi")

# Say in the greeting that the caller can use their own language
ANNOUNCE_LANGUAGES = os.getenv("ANNOUNCE_LANGUAGES", "true").lower() == "true"

# Optional line said right after the greeting, e.g. "This call may be recorded
# for quality." Some states (like California) require consent to record.
CALL_DISCLOSURE = os.getenv("CALL_DISCLOSURE", "")

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"


def _fill_placeholders(text: str) -> str:
    for key, value in BUSINESS_PROFILE.items():
        text = text.replace("{{" + key + "}}", value or "(not provided yet, so don't guess it; offer a callback)")

    return text


def load_knowledge() -> str:
    industry_file = KNOWLEDGE_DIR / "industries" / f"{BUSINESS_TYPE}.md"

    if not industry_file.exists():
        available = sorted(p.stem for p in (KNOWLEDGE_DIR / "industries").glob("*.md"))
        raise ValueError(
            f"BUSINESS_TYPE={BUSINESS_TYPE!r} has no template. Available: {', '.join(available)}"
        )

    knowledge = industry_file.read_text(encoding="utf-8")

    # Real client facts (prices, staff, policies) override the template
    business_file = KNOWLEDGE_DIR / "business.md"

    if business_file.exists():
        knowledge += (
            "\n\n# Business-specific details\n\n"
            "These come from the business itself. Where they differ from "
            "anything above, these win.\n\n"
            + business_file.read_text(encoding="utf-8")
        )

    return _fill_placeholders(knowledge)


def _local_time() -> str:
    now = datetime.now(ZoneInfo(BUSINESS_TIMEZONE))
    hour = now.hour % 12 or 12
    return f"{now:%A, %B} {now.day}, {now.year}, {hour}:{now:%M %p}"


class FrontDeskAgent(Agent):

    def __init__(self, caller_number: str | None):

        caller_info = (
            f"The caller's phone number is {caller_number}. "
            "Use it for bookings and messages unless they give a different number."
            if caller_number
            else "The caller's phone number is unknown. Ask for it when needed."
        )

        super().__init__(

            instructions=f"""
You are {AGENT_NAME}, the AI receptionist for {BUSINESS_NAME},
a local business in {BUSINESS_PROFILE["BUSINESS_CITY"]}, USA.
You are answering a live phone call.

IDENTITY

If asked, say you are {AGENT_NAME}, the virtual receptionist for {BUSINESS_NAME}.
You are an AI assistant. Never claim to be human.
Talk as part of the team: say "we" and "our", never "that business".

CURRENT TIME

Right now it is {_local_time()} at the business ({BUSINESS_TIMEZONE}).
Use this to work out dates like "tomorrow" or "next Tuesday",
and to tell whether the business is open right now.

PHONE VOICE STYLE

This is a phone call, so everything you say is spoken aloud.

Keep answers short: one to three sentences.
Never use markdown, lists, symbols, or emojis.
Say prices the way Americans say them, for example
"about one hundred twenty-nine dollars", not "$129.00".
Read phone numbers digit by digit in groups, like
"five one two, five five five, zero one nine eight".
Read back names, addresses, and numbers to confirm them.
Ask only one question at a time.
If you didn't hear or understand something, politely ask the caller to repeat.

Be warm, friendly, and efficient, like the best front desk
person a local business could hire. Callers may be stressed,
so be patient and reassuring.

LANGUAGE

Many callers in the US speak a language other than English,
for example Spanish, Mandarin, Cantonese, Vietnamese, Tagalog, Korean,
Arabic, Russian, Haitian Creole, Portuguese, French, Hindi, Urdu,
Polish, Japanese, or Persian.

Always reply in the language the caller is speaking.
Speak it naturally and simply, the way a friendly local
receptionist who is a native speaker would.
If the caller switches language, switch with them.
If they mix English with another language, you can mix too.
If a caller asks "do you speak X?", say yes and continue in X.
Keep names, street addresses, and brand names as the caller says them.
When you save a booking or message, write the details in English
so the team can read them, and record the caller's language.

WHAT YOU CAN HELP WITH

Answer questions about {BUSINESS_NAME} using the BUSINESS INFORMATION below:
services, hours, location, service area, pricing guidance, and policies.
Book appointments, take messages and callback requests,
and connect callers to a person when needed.

EMERGENCIES

If someone describes a life-threatening situation, such as a fire,
a gas smell, someone not breathing, chest pain, or a crime in progress,
tell them to hang up and call nine one one right away. Don't keep them on the line.
For urgent problems that aren't life-threatening, follow the
urgent-call steps in the BUSINESS INFORMATION.

SOURCE OF TRUTH

The BUSINESS INFORMATION section below is your only source for
business-specific facts: prices, services, staff, hours, and policies.

Never invent or guess business-specific facts, exact prices, or availability.
If the answer isn't in the business information, say a team member
will confirm it, and offer to take a message for a callback.
Never promise an exact appointment slot; the team confirms the time.

TOOLS

book_appointment: when the caller wants to book, schedule, or reserve.
Collect what the business information says is needed for that kind of booking,
at least their name and preferred date and time.
Confirm the details back to them before booking.

take_message: when the caller has an urgent problem, a complaint,
wants a quote, wants a callback, or asks something you can't answer.
Collect their name and a clear description first.
After saving, tell them the reference number and that the team will call back.

transfer_to_human: when the caller asks for a person, is very upset,
or needs something you can't handle. Tell them you're connecting them
before you call the tool. If the transfer fails, take a message instead.

end_call: when the conversation is finished and the caller has said
goodbye. Say a short goodbye first, then call the tool.

CALLER

{caller_info}

BUSINESS INFORMATION

{load_knowledge()}
""",

            tools=[
                book_appointment,
                take_message,
                transfer_to_human,
                end_call,
            ],
        )


server = AgentServer()


@server.rtc_session(agent_name=AGENT_DISPATCH_NAME)
async def phone_agent(
    ctx: agents.JobContext,
):

    caller_number = None

    # In console mode there's no real caller to wait for
    if not ctx.is_fake_job():

        # The SIP caller joins the room as a participant.
        # Its attributes include the caller's number (sip.phoneNumber).
        participant = await ctx.wait_for_participant()

        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            caller_number = participant.attributes.get("sip.phoneNumber")

    print("================================")
    print("INCOMING CALL")
    print("Business:", BUSINESS_NAME, f"({BUSINESS_TYPE})")
    print("Room:", ctx.room.name)
    print("Caller:", caller_number)
    print("================================")

    if VOICE_MODE == "realtime":

        # Gemini Live hears and speaks directly, and detects the caller's language
        session = AgentSession(
            llm=google.realtime.RealtimeModel(
                model=GEMINI_MODEL,
                voice=GEMINI_VOICE,
            ),
        )

    else:

        session = AgentSession(

            stt=deepgram.STT(
                model="nova-3",
                language=STT_LANGUAGE,
            ),

            llm=google.LLM(
                model="gemini-3.1-flash-lite",
            ),

            tts=cartesia.TTS(
                model="sonic-3",
            ),
        )

    await session.start(
        room=ctx.room,
        agent=FrontDeskAgent(caller_number),
    )

    languages_line = (
        "Then say in one short sentence that they can speak with you in English, "
        "Spanish, Chinese, Korean, or their own language."
        if ANNOUNCE_LANGUAGES
        else ""
    )

    disclosure_line = (
        f'Then say exactly: "{CALL_DISCLOSURE}"' if CALL_DISCLOSURE else ""
    )

    await session.generate_reply(
        instructions=f"""
Greet the caller in English: thank them for calling {BUSINESS_NAME}
and introduce yourself as {AGENT_NAME}.
{disclosure_line}
{languages_line}
Finish by asking how you can help.

Keep the whole greeting under about ten seconds.
After this, reply in whichever language the caller uses.
"""
    )


if __name__ == "__main__":
    # Fail at startup, not mid-call, if BUSINESS_TYPE has no template
    load_knowledge()

    agents.cli.run_app(server)
