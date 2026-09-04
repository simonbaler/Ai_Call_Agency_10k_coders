# 10,000 Coders AI Admissions Desk

A Flask-based AI voice admissions desk for 10,000 Coders. It places outbound Twilio calls, conducts multilingual course conversations, captures demo preferences, stores bookings, provides live call telemetry, and supports sequential outreach from an uploaded CSV.

## Features

- Outbound Twilio voice calls through `/voice` and `/process`
- English, Hindi, Telugu, Tamil, and Kannada voice prompts
- Course detection for Python Full Stack and Java Full Stack
- Demo day and time extraction with persistent JSON booking storage
- Light professional admin dashboard with live call telemetry
- Meeting approval workflow: an administrator clicks **Accept & Notify**
- Professional multilingual SMS confirmation through Twilio
- CSV lead import with persistent queued, calling, completed, and failed states
- Sequential automation: one lead is called at a time
- Call status callbacks and customer activity audit records

## Project Structure

- `app.py`: Flask routes, Twilio voice workflow, dashboard APIs, and notification endpoint
- `call.py`: command-line outbound caller and simulation client
- `booking_system.py`: booking persistence and course catalog
- `agentic.py`: durable CSV lead queue and sequential automation worker
- `course_booking.py`: speech extraction and booking prompts
- `knowledge_base.py`: institution and course knowledge
- `templates/index.html`: admin dashboard markup
- `static/app.js`: dashboard interactions and live updates
- `static/style.css`: responsive light dashboard styling
- `student_bookings.json`: persisted demo bookings
- `customer_data.csv`: call and activity records
- `automation_leads.json`: created after CSV import; durable automation history

## Requirements

- Python 3.10+
- A Twilio account and Twilio phone number with voice capability
- A public HTTPS tunnel for local development, such as ngrok
- Optional Gemini API key for assistant features

Install dependencies:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Environment Configuration

Create or update `.env`:

```env
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_FROM_NUMBER=+1234567890
VOICE_WEBHOOK_URL=https://your-public-host.example/voice
TWILIO_REQUEST_TIMEOUT=12
FLASK_SECRET_KEY=replace-with-a-long-random-value
GEMINI_API_KEY=optional
```

Never commit `.env` or share credentials. Rotate any token that has been exposed.

## Run The Application

Start Flask on port 5050:

```powershell
.\venv\Scripts\Activate.ps1
python app.py
```

In a second terminal, start the tunnel:

```powershell
ngrok http 5050
```

Set `VOICE_WEBHOOK_URL` to the current HTTPS forwarding URL plus `/voice`, then restart Flask. Open `http://localhost:5050/`, sign in, and use the dashboard.

## Deploy On Render

This repository includes `render.yaml` for a Render Web Service.

1. Push the repository to GitHub, with `.env` excluded from the repository.
2. In Render, choose **New > Blueprint** and select the repository.
3. Confirm the service from `render.yaml`.
4. In the Render service environment, set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, and `GEMINI_API_KEY` when applicable.
5. After the first deploy, set `VOICE_WEBHOOK_URL` to the Render service URL plus `/voice`, for example `https://your-service.onrender.com/voice`.
6. Redeploy after changing `VOICE_WEBHOOK_URL`.

Render starts the app with Gunicorn using `app:app`. The service uses one worker because the live call telemetry and automation queue are currently process-local. For production scale-out, move bookings, lead queues, call state, and telemetry to a shared database/queue; local JSON files are not durable across Render instance replacement.

## Single Call Workflow

1. Enter the student name, full international phone number, college, and preferred language.
2. Submit the outbound call form.
3. Twilio requests `/voice`, then sends speech results to `/process`.
4. The assistant discusses the selected course and demo slot.
5. A confirmed demo appears under **Customer Selected Courses & Demo Bookings**.
6. The administrator clicks **Accept & Notify**.
7. The app sends a professional SMS with the date, time, institution overview, and course context.

The destination number must include a country code, for example `+919876543210`.

## Automation Workflow

Prepare a CSV with at least these columns:

```csv
name,phone,college,age,language
Asha Rao,+919876543210,ABC College,21,en-IN
Rahul Kumar,+919876543211,XYZ University,22,hi-IN
```

Accepted aliases include `student_name`, `customer_name`, `mobile`, `mobile_number`, `student_phone`, and `preferred_language`. Upload the CSV, enable **Autonomous Outreach Queue**, and leads are called sequentially. Queue state is saved in `automation_leads.json` so imported leads are not lost when the process restarts.

## Supported Languages

- `en-IN`: English
- `hi-IN`: Hindi
- `te-IN`: Telugu
- `ta-IN`: Tamil
- `kn-IN`: Kannada

The lead language determines the initial voice experience and the approval SMS language.

## Testing

Run syntax checks:

```powershell
python -m py_compile app.py call.py
node --check static/app.js
```

Test the voice webhook locally:

```powershell
python -c "import app; c=app.app.test_client(); print(c.post('/voice', data={'CallSid':'TEST','From':'+15550000000'}).status_code)"
```

Use `SIMULATE_MODE=true` only for local webhook testing. Real Twilio calls require valid credentials, a verified destination on trial accounts, and a public HTTPS webhook.

## Troubleshooting

- `20003 Authenticate`: the Account SID and Auth Token do not match, or the token was revoked. Generate a new token and restart Flask.
- Webhook timeout: confirm Flask is listening on port 5050, ngrok is running, and `.env` contains the current HTTPS tunnel URL.
- Trial call rejected: verify the destination number in Twilio or upgrade the account.
- Booking notification failed: verify the Twilio number supports SMS and that the destination number is valid for messaging.
- Dashboard stuck on connecting: inspect the `/trigger_call` response and Flask console; the app bounds Twilio requests using `TWILIO_REQUEST_TIMEOUT`.
