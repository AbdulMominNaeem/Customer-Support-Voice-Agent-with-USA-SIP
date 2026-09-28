# AI Front Desk: multilingual phone agent for US local businesses

An AI receptionist that answers a business's phone line 24/7 and speaks with
callers in their own language (English, Spanish, Mandarin, Cantonese, Korean,
Vietnamese, Arabic, Russian and more). It answers questions, books appointments,
takes messages, handles urgent calls and transfers callers to a person.

It runs on LiveKit Agents with Gemini Live and connects to any US phone number
over SIP (Twilio, Telnyx, SignalWire, Plivo, Vonage, Bandwidth...).

## How it works

```
Caller -> US phone number -> SIP provider -> LiveKit SIP -> agent.py (Gemini Live)
                                                                |
                    bookings / messages -> MongoDB or data/*.jsonl -> optional webhook to the owner
```

- `agent.py`: the agent. Its personality, rules and language behaviour are in its prompt.
- `knowledge/industries/*.md`: industry templates (services, booking questions,
  urgent-call rules, things not to guess). `{{BUSINESS_NAME}}` and the other
  placeholders are filled from `.env.local`.
- `knowledge/business.md` (optional): a real client's own facts (prices, staff,
  offers). These override the template. Start from `business.example.md`.
- `tools/call_tools.py`: `book_appointment`, `take_message`, `transfer_to_human`, `end_call`.
- `setup_sip.py`: connects your US number(s) to the agent on LiveKit.

## 1. Run it locally

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env.local        # then fill in the keys
python agent.py download-files
python agent.py console           # talk to it through your mic, no phone needed
```

Try it in Spanish, Chinese or Korean. It switches to the caller's language automatically.

## 2. Customize it for a business (or a demo)

Change these in `.env.local` and restart:

```ini
BUSINESS_TYPE=dental                  # home_services, dental, auto_repair, restaurant, salon_spa, law_firm
BUSINESS_NAME=Bright Smile Dental
BUSINESS_CITY=Irvine, California
SERVICE_AREA=Irvine and Orange County
BUSINESS_HOURS=Monday to Friday 8 AM to 5 PM
BUSINESS_TIMEZONE=America/Los_Angeles
BUSINESS_PHONE=+19495550123
BUSINESS_WEBSITE=brightsmileirvine.com
```

The agent now introduces itself as Bright Smile Dental's receptionist, knows
it's in Irvine, and follows the dental intake flow. When you sign the client,
copy `knowledge/business.example.md` to `knowledge/business.md` and put in
their real prices, staff and policies.

To add a new industry, copy any file in `knowledge/industries/` and edit it.
The filename becomes the `BUSINESS_TYPE` value.

## 3. Connect a US phone number (SIP)

You need a LiveKit Cloud project (or self-hosted LiveKit with SIP) and a US
number from any SIP provider.

**a. Register the number with LiveKit**

```ini
SIP_PHONE_NUMBERS=+15125550198        # E.164, comma separate for several numbers
SIP_AUTH_USERNAME=                     # if your provider uses credentials
SIP_AUTH_PASSWORD=
SIP_ALLOWED_ADDRESSES=                 # or restrict to your provider's IPs
```

```bash
python setup_sip.py
```

You can run it again at any time. It updates the same trunk and dispatch rule.

**b. Point your provider at LiveKit.** Find your SIP URI in LiveKit Cloud under
Settings > Project > SIP URI (it looks like `sip:xxxx.sip.livekit.cloud`).

- **Twilio**: Elastic SIP Trunking > create a trunk > Origination > add
  `sip:xxxx.sip.livekit.cloud;transport=tcp` > Numbers > attach your number.
  For call transfers, turn on *Call Transfer (SIP REFER)* under the trunk's
  Features and allow PSTN transfer. If you use credentials, match them to
  `SIP_AUTH_*`.
- **Telnyx**: create a SIP Connection of type *FQDN* pointing to
  `xxxx.sip.livekit.cloud`, assign your number to it, and set the inbound
  number format to `+E.164`.
- **Others** (SignalWire, Plivo, Vonage, Bandwidth): create a SIP trunk or
  endpoint whose destination is your LiveKit SIP URI, and send numbers in
  `+1XXXXXXXXXX` format.

LiveKit's provider guides: https://docs.livekit.io/sip/

**c. Deploy the agent** so it's online 24/7:

```bash
lk agent deploy          # LiveKit Cloud, uses the Dockerfile
# or anywhere with Docker:  python agent.py start
```

Call the number. The agent picks up.

### Optional features

- `HUMAN_TRANSFER_NUMBER=+15125550123`: "let me talk to someone" transfers
  here. Your provider must support SIP REFER (see Twilio note above).
- `NOTIFY_WEBHOOK_URL`: every booking and message is POSTed as JSON, with a
  readable `text` field. Point it at a Slack or Discord webhook, or at
  Zapier/Make/n8n to send the owner an SMS or email, or to add a row to a
  Google Sheet or CRM.
- `CALL_DISCLOSURE`: a sentence said after the greeting, e.g. *"This call may be
  recorded for quality."* Some states (California, Florida, Illinois,
  Washington and others) require all parties to consent to recording.
- `MONGODB_URI` / `MONGODB_DATABASE`: store records in MongoDB instead of `data/`.

## Languages

`VOICE_MODE=realtime` (the default) uses Gemini Live native audio. It
detects the caller's language by itself and replies in it, and callers can
switch mid-call. It works well for Spanish, Mandarin, Korean, Vietnamese,
Japanese, Arabic, Russian, Portuguese, French, Hindi/Urdu, Polish and many
others. Test less common languages such as Tagalog, Cantonese and Haitian
Creole before promising them to a client.

`VOICE_MODE=pipeline` (Deepgram + Cartesia) is cheaper to scale but supports
fewer languages. Deepgram's `multi` mode covers English, Spanish, French,
German, Hindi, Russian, Portuguese, Japanese, Italian and Dutch.

Bookings and messages are always saved in English, with a `caller_language`
field, so the owner can read them and knows to call back in that language.

## Who to sell this to

Ranked by how easily the agent pays for itself:

| # | Industry (`BUSINESS_TYPE`) | Why they buy |
|---|---|---|
| 1 | **Home services**: HVAC, plumbing, electrical, roofing (`home_services`) | Each missed call is a $300 to $15,000 job. Techs can't answer while on a roof or under a sink, and emergencies come in at night. The easiest ROI story. |
| 2 | **Dental, chiropractic, med spa** (`dental`) | A new patient is worth $1,000 or more over time. The front desk is overloaded, and many patients prefer Spanish, Chinese or Korean. |
| 3 | **Law firms**: immigration, personal injury (`law_firm`) | One signed case can be worth thousands. Immigration clients are overwhelmingly non-English speakers, and after-hours intake wins cases. |
| 4 | **Auto repair and body shops** (`auto_repair`) | Mechanics are under cars, not on the phone. Captures quote requests and bookings. |
| 5 | **Salons, nail salons, spas** (`salon_spa`) | Booking-heavy with lots of calls. Many are owned by and serve Korean, Vietnamese and Latino communities. |
| 6 | **Restaurants** (`restaurant`) | High call volume (hours, reservations, catering). Lower value per call, so pitch catering and large orders. |

**Target the multilingual angle first.** Businesses in Houston, Los Angeles,
the Bay Area, New York/Queens, Miami, Chicago, Dallas, Atlanta (Duluth), Orange
County and Seattle serve large Spanish, Chinese, Korean and Vietnamese
speaking populations. Most of them lose those calls today.

**Demo tip:** before a sales call, set `BUSINESS_NAME`, `BUSINESS_CITY`,
`BUSINESS_TYPE` and `BUSINESS_HOURS` to the prospect's details and restart. When
they call your demo number, it answers as *their* business. Call it yourself in
Spanish or Korean on the pitch.
