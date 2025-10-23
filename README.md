http://dashboard.heroku.com/new?template=https://github.com/hkmusic/otpbot

# Telegram Virtual-Number Shop Bot (Safe base)

## What this repo includes
- Telegram bot with:
  - /start menu with inline buttons (Balance, Account Details, Recharge, Support, Buy Account).
  - Country selection and buy flow (quantity, stock checks, balance checks).
  - Admin `/addstock` flow to add numbers to stock per country.
  - MongoDB store for users, stock, transactions.
  - Heroku-ready Procfile.

## **VERY IMPORTANT — REFUSAL**
This project intentionally **does not** include any code that:
- Automatically retrieves Telegram login codes (one-time passwords) from networks or from Telegram servers;
- Produces Telethon string sessions by programmatically intercepting login codes.

I cannot provide code to automate OTP interception or session-creation because that enables unauthorized access to accounts and violates legal/ethical rules.

## Safe alternatives / how to extend legally
1. **Manual buyer flow (current)**: buyer purchases a number; we provide number; buyer requests OTP in their client and either enters code manually or follows your support process. This is implemented already.

2. **Legitimate SMS provider integration**:
   - If the numbers you sell are owned by you and your SMS provider provides an API to retrieve incoming SMS for those numbers (and you have the lawful right and user consent to forward codes), you can implement a server-side integration to fetch SMS messages from that provider and forward them to buyers.
   - *Do not* use provider APIs to fetch SMS for numbers you don't own or without user consent.
   - If you want help integrating a specific **legal** SMS API (e.g., Twilio for numbers you control), say the provider and share the API docs; I can help write an integration that polls or receives webhooks **only** for numbers you own. (This is allowed only when used lawfully.)

3. **Telethon / sessions**:
   - I will not provide code to create string sessions by intercepting codes on behalf of buyers.
   - If your business model requires provisioning a ready-to-use Telegram session for buyers, implement that with explicit consent and legal vetting; integrate only using official APIs and audit logs.

## Deployment
- Set env vars: `BOT_TOKEN`, `MONGODB_URI`, `ADMIN_IDS` (comma-separated), `CURRENCY_SYMBOL` (optional), `DEFAULT_PRICE`.
- Deploy to Heroku by pushing this repo and setting configs.

## Next steps you may request
- Add recharge flow (I can implement storing pending recharges and admin verification).
- Add web dashboard (Flask / FastAPI) for admin to manage stock (web UI).
- Add logging, metrics, and rate limits.

**If you still want me to**: I can now implement the recharge logic you promised to send, admin web UI, or a safe SMS-provider integration for numbers you own. Tell me which of those you want next and provide the provider name / API docs if applicable.
