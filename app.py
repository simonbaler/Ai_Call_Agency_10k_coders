from flask import Flask, request, render_template, jsonify, session, redirect, url_for, Response
from werkzeug.exceptions import HTTPException
from twilio.twiml.voice_response import VoiceResponse, Gather
from dotenv import load_dotenv
import os
import csv
from datetime import datetime
from urllib.parse import urlencode
from urllib.parse import urlparse

# Import our custom systems
from knowledge_base import COURSE_INFO, FAQS
from question_answerer import detect_question_type, generate_answer
from sales_intelligence import (
    get_intro_message, get_interest_check, get_yes_response, get_no_response,
    get_answer_intro, get_after_answer, get_demo_message, get_close, handle_objection
)
from course_booking import (
    get_course_selection, get_course_confirmation, get_demo_booking,
    get_demo_time, get_booking_confirmation, get_closing,
    extract_course, extract_day, extract_time, extract_slots
)
from booking_system import COURSES, create_booking, load_bookings, update_booking
from agentic import LeadOperationsAgent, normalize_call_status

app = Flask(__name__)
load_dotenv()
app.secret_key = os.getenv("FLASK_SECRET_KEY", "1000-coders-local-development-key")


@app.after_request
def mark_twiml_response(response):
    if request.path in ("/voice", "/process") and response.status_code == 200:
        response.headers["Content-Type"] = "application/xml; charset=utf-8"
    return response

print("=" * 70)
print("[*] 10,000 CODERS ADVANCED AI ADMISSIONS DESK & DEMO BOOKING")
print("[+] Speaks like experienced Admissions Officer")
print("[+] Automatic slot booking & live call telemetry")
print("=" * 70)

# =============================
# CALL STATE TRACKING & LIVE HUD
# =============================
call_state = {}
conversation_history = {}
turn_count = {}
student_interest = {}
student_phone = {}
CUSTOMER_CSV = os.path.join(os.path.dirname(__file__), "customer_data.csv")
automation_agent = None

# Real-time telemetry dictionary consumed by the dashboard
active_call_session = {
    "active": False,
    "call_sid": "",
    "student_name": "",
    "student_phone": "",
    "student_college": "",
    "student_age": "",
    "language": "en-IN",
    "stage": "idle",
    "stage_title": "Standby / Monitoring",
    "progress_pct": 0,
    "course_selected": "",
    "demo_date": "",
    "demo_time": "",
    "booking_status": "unbooked",
    "start_time": None,
    "duration_seconds": 0,
    "latest_utterance": "Standing by for calls",
    "transcript": []
}

def get_state(call_id):
    return call_state.get(call_id, {
        "stage": "intro",
        "preferred_language": "en-IN",
        "questions_asked": 0,
        "demo_offered": False,
        "course_selected": None,
        "demo_date": None,
        "demo_time": None,
        "student_name": "",
        "student_mobile": "",
        "college": ""
    })

def update_state(call_id, state):
    call_state[call_id] = state

def is_affirmative(text):
    text_lower = (text or "").lower()
    return any(word in text_lower for word in ["yes", "ya", "yup", "sure", "okay", "of course", "absolutely", "want", "i do", "interested", "హా", "అవును", "సరే", "haan", "theek hai"])

def is_negative(text):
    text_lower = (text or "").lower()
    return any(word in text_lower for word in ["no", "don't", "dont", "nah", "not interested", "కాదు", "లేదు", "nahi"])

def add_to_history(call_id, role, text):
    if call_id not in conversation_history:
        conversation_history[call_id] = []
    entry = {
        "role": role,
        "text": text,
        "time": datetime.now().strftime("%H:%M:%S")
    }
    conversation_history[call_id].append(entry)
    
    # Mirror into live call session for dashboard
    active_call_session["transcript"].append(entry)
    active_call_session["latest_utterance"] = f"{role}: {text}"


def get_turn(call_id):
    return turn_count.get(call_id, 0)


def increment_turn(call_id):
    turn_count[call_id] = get_turn(call_id) + 1


def save_customer_event(customer, event, call_sid=""):
    fields = ["timestamp", "event", "call_sid", "name", "age", "college", "phone", "language", "status", "duration"]
    file_exists = os.path.exists(CUSTOMER_CSV)
    existing_rows = []
    if file_exists:
        with open(CUSTOMER_CSV, newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            existing_rows = list(reader)
        if reader.fieldnames != fields:
            file_exists = False
            with open(CUSTOMER_CSV, "w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=fields)
                writer.writeheader()
                for row in existing_rows:
                    writer.writerow({field: row.get(field, "") for field in fields})
            file_exists = True
    with open(CUSTOMER_CSV, "a", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fields)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            "call_sid": call_sid,
            "name": customer.get("name", ""),
            "age": customer.get("age", ""),
            "college": customer.get("college", ""),
            "phone": customer.get("phone", ""),
            "language": customer.get("language", ""),
            "status": customer.get("status", "initiated"),
            "duration": customer.get("duration", ""),
        })


def read_customer_events():
    if not os.path.exists(CUSTOMER_CSV):
        return []
    with open(CUSTOMER_CSV, newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))[-40:][::-1]


def call_lead_from_agent(lead):
    from twilio.rest import Client
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    from_number = os.getenv("TWILIO_FROM_NUMBER", "").strip()
    webhook_url = os.getenv("VOICE_WEBHOOK_URL", "").strip()
    if os.getenv("SIMULATE_MODE", "").lower() in ("1", "true", "yes"):
        save_customer_event(lead, "automation_call_started", "SIMULATED_AUTOMATION")
        return
    if not all([account_sid, auth_token, from_number, webhook_url]):
        raise RuntimeError("Twilio configuration is incomplete")
    callback_url = f"{webhook_url.rsplit('/', 1)[0]}/call_status"
    call = Client(account_sid, auth_token).calls.create(
        to=lead["phone"], from_=from_number,
        url=f"{webhook_url}?{urlencode(lead)}",
        status_callback=callback_url,
        status_callback_method="POST",
        status_callback_event=["initiated", "ringing", "answered", "completed"],
    )
    save_customer_event(lead, "automation_call_started", call.sid)


def meeting_message(booking):
    language = booking.get("language", "en-IN")
    course = booking.get("course_name", "Full Stack program")
    day = booking.get("demo_date", "the scheduled date")
    time = booking.get("demo_time", "the scheduled time")
    messages = {
        "hi-IN": f"Namaste {booking.get('student_name', 'Student')}, 10,000 Coders ne aapka {course} mentor meeting confirm kiya hai. Date: {day}. Time: {time}. Hamare mentor-led, project-based programs mein AI, Full Stack development aur placement preparation shamil hai. Kripya samay par join karein. Dhanyavaad.",
        "te-IN": f"Namaskaram {booking.get('student_name', 'Student')}, 10,000 Coders mee {course} mentor meeting ni confirm chesindi. Date: {day}. Time: {time}. Maa mentor-led project-based program lo AI, Full Stack development mariyu placement preparation untayi. Dayachesi samayaniki join avvandi. Dhanyavadalu.",
        "ta-IN": f"Vanakkam {booking.get('student_name', 'Student')}, 10,000 Coders ungal {course} mentor meeting-ai uruthi seithullathu. Date: {day}. Time: {time}. Engal mentor-led, project-based program-il AI, Full Stack development matrum placement preparation ullana. Dayavuseithu nerathirkku seravum. Nandri.",
        "kn-IN": f"Namaskara {booking.get('student_name', 'Student')}, 10,000 Coders nimma {course} mentor meeting annu confirm madide. Date: {day}. Time: {time}. Namma mentor-led project-based program nalli AI, Full Stack development mattu placement preparation ide. Dayavittu samayakke join agi. Dhanyavadagalu.",
    }
    return messages.get(language, f"Dear {booking.get('student_name', 'Student')}, your {course} mentor meeting with 10,000 Coders is confirmed. Date: {day}. Time: {time}. Our mentor-led, project-based programs cover AI, Full Stack development, and placement preparation. Please join on time. We look forward to welcoming you.")
@app.errorhandler(Exception)
def voice_safe_error(error):
    if isinstance(error, HTTPException):
        return error
    app.logger.exception("Unhandled request error: %s", error)
    if request.path in ("/voice", "/process"):
        response = VoiceResponse()
        response.say("We are sorry, our voice assistant needs a moment. Please stay on the line and try again.", voice="Polly.Aditi", language="en-IN")
        response.redirect("/voice", method="POST")
        return str(response), 200, {"Content-Type": "text/xml"}
    if request.path.startswith("/") and request.accept_mimetypes.best == "application/json":
        return jsonify({"error": "The request could not be completed"}), 500
    return "The request could not be completed", 500


@app.route("/favicon.ico")
def favicon():
    return Response(status=204)


def customer_from_payload(payload):
    return {
        "name": (payload.get("name") or "").strip(),
        "age": (payload.get("age") or "").strip(),
        "college": (payload.get("college") or "").strip(),
        "phone": (payload.get("phone") or "").strip(),
        "language": payload.get("language", "en-IN"),
        "status": "initiated",
    }


LANGUAGE_CONFIG = {
    "en-IN": {"name_prompt": "Welcome to 10,000 Coders. May I know your name?", "college_prompt": "Which college or university are you studying at?", "language_prompt": "Welcome to 10,000 Coders. We help learners build real AI and full-stack applications with experienced mentors, practical projects, and placement support. Are you interested in becoming a software engineer? Please say yes or no.", "course_prompt": "We offer Python Full Stack and Java Full Stack. Which path sounds right for you?", "demo_prompt": "Great choice. I can reserve a free, no-pressure demo with a mentor. Would you like me to book it?", "time_prompt": "Which day works best for your demo: Monday, Tuesday, Wednesday, Thursday or Friday?", "objection_prompt": "I understand. One useful thing about 10,000 Coders is that you can experience a real mentor-led class and projects before deciding. There is no pressure. Would a free demo help you evaluate it?", "closing_prompt": "No problem at all. Thank you for your time, and I wish you the very best.", "voice": "Polly.Aditi"},
    "hi-IN": {"name_prompt": "10,000 Coders mein aapka swagat hai. Aapka naam kya hai?", "college_prompt": "Aap kis college ya university mein padh rahe hain?", "language_prompt": "10,000 Coders mein aapka swagat hai. Hum experienced mentors, practical projects aur placement support ke saath AI aur full-stack applications banana sikhate hain. Kya aap software engineer banna chahte hain? Haan ya nahi boliye.", "course_prompt": "Hum Python Full Stack aur Java Full Stack offer karte hain. Aapko kaunsa path pasand hai?", "demo_prompt": "Bahut achha. Main aapke liye mentor ke saath free demo reserve kar sakta hoon. Kya main book kar doon?", "time_prompt": "Aapke demo ke liye kaunsa din theek rahega: Monday, Tuesday, Wednesday, Thursday ya Friday?", "objection_prompt": "Main samajh sakta hoon. 10,000 Coders mein aap decision lene se pehle real mentor-led class aur projects dekh sakte hain. Koi pressure nahi hai. Kya free demo se aapko help milegi?", "closing_prompt": "Koi baat nahi. Aapke samay ke liye dhanyavaad. Aapke bhavishya ke liye shubhkamnayein.", "voice": "Google.hi-IN-Standard-A"},
    "te-IN": {"name_prompt": "10,000 Coders కు స్వాగతం. మీ పేరు చెప్పగలరా?", "college_prompt": "మీరు ఏ college లేదా university లో చదువుతున్నారు?", "language_prompt": "10,000 Coders కు స్వాగతం. Experienced mentors, practical projects మరియు placement support తో AI మరియు full-stack applications నిర్మించడం నేర్పిస్తాము. మీరు software engineer అవ్వాలనుకుంటున్నారా? అవును లేదా కాదు చెప్పండి.", "course_prompt": "మా దగ్గర Python Full Stack మరియు Java Full Stack ఉన్నాయి. మీకు ఏ path ఇష్టం?", "demo_prompt": "చాలా బాగుంది. Mentor తో free, no-pressure demo reserve చేయగలను. Book చేయనా?", "time_prompt": "మీ demo కి ఏ రోజు convenient: Monday, Tuesday, Wednesday, Thursday లేదా Friday?", "objection_prompt": "మీ మాట అర్థమైంది. 10,000 Coders లో decision తీసుకునే ముందు real mentor-led class మరియు projects చూడవచ్చు. ఎలాంటి pressure లేదు. Free demo మీకు సహాయపడుతుందా?", "closing_prompt": "పర్లేదు. మీ సమయానికి ధన్యవాదాలు. మీ భవిష్యత్తుకు శుభాకాంక్షలు.", "voice": "Google.te-IN-Standard-A"},
    "ta-IN": {"name_prompt": "10,000 Coders-க்கு வரவேற்கிறோம். உங்கள் பெயர் என்ன?", "college_prompt": "நீங்கள் எந்த கல்லூரி அல்லது பல்கலைக்கழகத்தில் படிக்கிறீர்கள்?", "language_prompt": "10,000 Coders-க்கு வரவேற்கிறோம். அனுபவமுள்ள mentors, practical projects மற்றும் placement support மூலம் AI மற்றும் full-stack applications உருவாக்க கற்றுக்கொடுக்கிறோம். நீங்கள் software engineer ஆக விரும்புகிறீர்களா? ஆம் அல்லது இல்லை என்று சொல்லுங்கள்.", "course_prompt": "Python Full Stack மற்றும் Java Full Stack ஆகியவற்றை வழங்குகிறோம். உங்களுக்கு எந்த பாதை விருப்பம்?", "demo_prompt": "மிகவும் நல்லது. Mentor உடன் free demo-வை reserve செய்யலாம். Book செய்யவா?", "time_prompt": "உங்கள் demo-க்கு எந்த நாள் வசதியாக இருக்கும்: Monday, Tuesday, Wednesday, Thursday அல்லது Friday?", "objection_prompt": "புரிகிறது. 10,000 Coders-ல் முடிவு எடுப்பதற்கு முன் real mentor-led class மற்றும் projects-ஐ பார்க்கலாம். எந்த pressure-மும் இல்லை. Free demo உதவுமா?", "closing_prompt": "பரவாயில்லை. உங்கள் நேரத்திற்கு நன்றி. உங்கள் எதிர்காலத்திற்கு வாழ்த்துகள்.", "voice": "Google.ta-IN-Standard-A"},
    "kn-IN": {"name_prompt": "10,000 Coders ge swagata. Nimma hesaru enu?", "college_prompt": "Neevu yaava college athava university alli oduttiddira?", "language_prompt": "10,000 Coders ge swagata. Anubhavi mentors, practical projects mattu placement support jothe AI mattu full-stack applications nirmisalu kalisutteve. Neevu software engineer agalu bayasutteera? Howdu athava illa heli.", "course_prompt": "Python Full Stack mattu Java Full Stack nammalli ive. Nimge yaava path ishta?", "demo_prompt": "Chennagide. Mentor jothe free demo reserve madabahudu. Book madona?", "time_prompt": "Nimma demo ge yaava dina anukoola: Monday, Tuesday, Wednesday, Thursday athava Friday?", "objection_prompt": "Nimma maatu artha ayitu. 10,000 Coders nalli nirnaya maduva modalu real mentor-led class mattu projects nodabahudu. Yavude pressure illa. Free demo sahaya maduttadeye?", "closing_prompt": "Parvagilla. Nimma samayakke dhanyavadagalu. Nimma bhavishyakkagi shubhashayagalu.", "voice": "Google.kn-IN-Standard-A"},
}


def get_language_config(state):
    return LANGUAGE_CONFIG.get(state.get("preferred_language"), LANGUAGE_CONFIG["en-IN"])


def localized_course_confirmation(state, course_key):
    from booking_system import get_course_info
    course = get_course_info(course_key)
    if not course:
        return get_language_config(state)["course_prompt"]
    config = get_language_config(state)
    return f"Excellent choice. {course['name']} runs for {course['duration']} and covers {', '.join(course['topics'])}. The fee is {course['fee']}. {config['demo_prompt']}"

def detect_course(value):
    value = (value or "").lower().strip()
    if value == "1" or "python" in value:
        return "python"
    if value == "2" or "java" in value:
        return "java"
    return None


def detect_demo_day(value):
    value = (value or "").lower().strip()
    numbered_days = {"1": "Monday", "2": "Tuesday", "3": "Wednesday", "4": "Thursday", "5": "Friday"}
    if value in numbered_days:
        return numbered_days[value]
    return extract_day(value)

def course_selection_prompt(state):
    prompts = {
        "en-IN": "Please choose a course. Press 1 for Python Full Stack, or press 2 for Java Full Stack. You can also say Python or Java.",
        "hi-IN": "Course choose kijiye. Python Full Stack ke liye 1 dabaiye, Java Full Stack ke liye 2 dabaiye. Aap Python ya Java bhi bol sakte hain.",
        "te-IN": "Course ఎంచుకోండి. Python Full Stack కోసం 1 నొక్కండి, Java Full Stack కోసం 2 నొక్కండి. Python లేదా Java అని కూడా చెప్పవచ్చు.",
        "ta-IN": "Course தேர்வு செய்யவும். Python Full Stackக்கு 1 அழுத்தவும், Java Full Stackக்கு 2 அழுத்தவும். Python அல்லது Java என்றும் சொல்லலாம்.",
        "kn-IN": "Course ಆಯ್ಕೆ ಮಾಡಿ. Python Full Stack ಗೆ 1 ಒತ್ತಿ, Java Full Stack ಗೆ 2 ಒತ್ತಿ. Python ಅಥವಾ Java ಎಂದೂ ಹೇಳಬಹುದು.",
    }
    return prompts.get(state.get("preferred_language"), prompts["en-IN"])


def interest_prompt(state):
    prompts = {
        "en-IN": "Are you interested in becoming a software engineer? Please say yes or no.",
        "hi-IN": "Kya aap software engineer banna chahte hain? Haan ya nahi boliye.",
        "te-IN": "మీరు software engineer అవ్వాలనుకుంటున్నారా? అవును లేదా కాదు చెప్పండి.",
        "ta-IN": "நீங்கள் software engineer ஆக விரும்புகிறீர்களா? ஆம் அல்லது இல்லை என்று சொல்லுங்கள்.",
        "kn-IN": "Neevu software engineer agalu bayasutteera? Howdu athava illa heli.",
    }
    return prompts.get(state.get("preferred_language"), prompts["en-IN"])


def detect_language(value):
    value = (value or "").lower().strip()
    choices = {"1": "en-IN", "2": "hi-IN", "3": "te-IN", "4": "ta-IN", "5": "kn-IN"}
    if value in choices:
        return choices[value]
    for language, code in [("english", "en-IN"), ("hindi", "hi-IN"), ("हिंदी", "hi-IN"), ("telugu", "te-IN"), ("తెలుగు", "te-IN"), ("tamil", "ta-IN"), ("தமிழ்", "ta-IN"), ("kannada", "kn-IN"), ("ಕನ್ನಡ", "kn-IN")]:
        if language in value:
            return code
    return None


def language_selection_prompt():
    return (
        "Welcome to 10,000 Coders. Please choose your preferred language. "
        "Say English, Hindi, Telugu, Tamil, or Kannada. "
        "You may also press 1 for English, 2 for Hindi, 3 for Telugu, "
        "4 for Tamil, or 5 for Kannada."
    )


def get_stage_followup_prompt(state):
    stage = state.get("stage", "intro")
    if stage == "intro":
        return interest_prompt(state)
    elif stage == "course_selection":
        return course_selection_prompt(state)
    elif stage == "demo_interest":
        return get_language_config(state)["demo_prompt"]
    elif stage == "demo_date_selection":
        return demo_date_prompt(state)
    elif stage == "demo_time_selection":
        return get_language_config(state)["time_prompt"]
    elif stage == "collect_student_details":
        if state.get("student_name") is None:
            return "నీ పేరు చెప్పు బ్రో, please."
        elif state.get("student_mobile") is None:
            return "నీ mobile number ఇవ్వండి బ్రో."
        else:
            return "ఇది correct కాదా బ్రో? yes or no చెప్పు బ్రో."
    elif stage == "collect_college":
        return get_language_config(state)["college_prompt"]
    return get_after_answer()


def demo_date_prompt(state):
    prompts = {
        "en-IN": "Choose your demo day: press 1 for Monday, 2 for Tuesday, 3 for Wednesday, 4 for Thursday, or 5 for Friday. You can also say the day.",
        "hi-IN": "Demo ka din chuniye: Monday ke liye 1, Tuesday ke liye 2, Wednesday ke liye 3, Thursday ke liye 4, ya Friday ke liye 5 dabaiye. Aap din bol bhi sakte hain.",
        "te-IN": "Demo రోజు ఎంచుకోండి: Monday కోసం 1, Tuesday కోసం 2, Wednesday కోసం 3, Thursday కోసం 4, Friday కోసం 5 నొక్కండి. మీరు రోజు పేరు కూడా చెప్పవచ్చు.",
        "ta-IN": "Demo நாளை தேர்வு செய்யவும்: Mondayக்கு 1, Tuesdayக்கு 2, Wednesdayக்கு 3, Thursdayக்கு 4, Fridayக்கு 5 அழுத்தவும். நாளை சொல்லவும்லாம்.",
        "kn-IN": "Demo dina aayke maadi: Monday ge 1, Tuesday ge 2, Wednesday ge 3, Thursday ge 4, Friday ge 5 otti. Dina hesarannu helabahudu.",
    }
    return prompts.get(state.get("preferred_language"), prompts["en-IN"])


def try_general_question_response(response, call_id, user_input, state):
    question_type, direct_answer = detect_question_type(user_input)
    if question_type == "unclear":
        return False

    if direct_answer:
        ai_response = direct_answer
    else:
        ai_response = generate_answer(question_type, user_input)

    if question_type not in ["who_are_you", "what_can_you_do"]:
        ai_response = get_answer_intro(question_type) + " " + ai_response

    response.say(ai_response, voice=get_language_config(state)["voice"], language=state.get("preferred_language", "en-IN"))
    add_to_history(call_id, "Agent", ai_response)

    follow_up = get_stage_followup_prompt(state)
    gather = Gather(
        input="dtmf speech" if state.get("stage") == "collect_language" else "speech",
        action="/process",
        method="POST",
        timeout=10,
        speechTimeout="auto",
        language=state.get("preferred_language", "en-IN")
    )
    gather.say(follow_up, voice=get_language_config(state)["voice"], language=state.get("preferred_language", "en-IN"))
    response.append(gather)
    return True

# =============================
# HEALTH CHECK
# =============================
@app.route("/", methods=["GET"])
def welcome():
    return render_template("welcome.html")


@app.route("/auth", methods=["GET", "POST"])
def auth():
    if request.method == "POST":
        session["user"] = {
            "name": request.form.get("name", "").strip(),
            "email": request.form.get("email", "").strip(),
            "mode": request.form.get("mode", "register"),
        }
        return redirect(url_for("dashboard"))
    return render_template("auth.html")


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("welcome"))


@app.route("/assistant", methods=["POST"])
def assistant():
    if "user" not in session:
        return jsonify({"error": "Sign in required"}), 401
    question = (request.json or {}).get("message", "").strip()
    if not question:
        return jsonify({"error": "Message required"}), 400
    question_type, direct_answer = detect_question_type(question)
    answer = direct_answer or generate_answer(question_type, question)
    if question_type == "unclear":
        answer = "I can help with course tracks, fees, placements, projects, demo sessions, call activity, and automation. What would you like to explore?"
    return jsonify({"answer": answer, "intent": question_type})


# =============================
# SIMPLE WEB DASHBOARD
# =============================
@app.route("/dashboard", methods=["GET"])
def dashboard():
    if "user" not in session:
        return redirect(url_for("auth"))
    return render_template("index.html", user=session["user"], call_logs=read_customer_events(), agent_status=automation_agent.snapshot() if automation_agent else {"queued": 0, "completed": 0, "running": False, "last_error": ""})


@app.route("/call_logs", methods=["GET"])
def call_logs():
    return jsonify({"logs": read_customer_events(), "agent": automation_agent.snapshot() if automation_agent else {"queued": 0, "completed": 0, "running": False}})


@app.route("/selected_courses", methods=["GET"])
def selected_courses():
    bookings = load_bookings()
    return jsonify({"courses": bookings[::-1]})


@app.route("/bookings/<booking_id>/accept", methods=["POST"])
def accept_booking(booking_id):
    """Approve a demo and send its confirmation by SMS."""
    booking = next((item for item in load_bookings() if item.get("booking_id") == booking_id), None)
    if not booking:
        return jsonify({"error": "Booking not found"}), 404
    if booking.get("admin_status") == "accepted" and booking.get("notification_status") == "sent":
        return jsonify({"booking": booking, "message": "This meeting was already accepted and notified."})

    recipient = (booking.get("student_phone") or "").strip()
    sender = os.getenv("TWILIO_FROM_NUMBER", "").strip()
    if not recipient:
        update_booking(booking_id, notification_status="failed", notification_error="Student phone number is missing")
        return jsonify({"error": "Add the student's phone number before accepting this meeting."}), 400
    if recipient.lstrip("+").replace(" ", "") == sender.lstrip("+").replace(" ", ""):
        update_booking(booking_id, notification_status="failed", notification_error="Student phone matches Twilio sender number")
        return jsonify({"error": "The student's phone number cannot be the same as the Twilio sender number. Correct the booking phone number and retry."}), 400

    message = meeting_message(booking)
    try:
        from twilio.rest import Client
        from twilio.http.http_client import TwilioHttpClient
        account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
        auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        from_number = sender
        if not all((account_sid, auth_token, from_number, booking.get("student_phone"))):
            raise RuntimeError("Twilio SMS configuration or student phone is missing")
        client = Client(account_sid, auth_token, http_client=TwilioHttpClient(timeout=float(os.getenv("TWILIO_REQUEST_TIMEOUT", "12"))))
        sms = client.messages.create(body=message, from_=from_number, to=booking["student_phone"])
        booking = update_booking(booking_id, admin_status="accepted", notification_status="sent", notification_sid=sms.sid, notification_message=message)
        return jsonify({"booking": booking, "message": "Meeting accepted and confirmation sent."})
    except Exception as exc:
        update_booking(booking_id, admin_status="pending", notification_status="failed", notification_error=str(exc))
        return jsonify({"error": f"Meeting was not notified: {str(exc)}"}), 502


@app.route("/api/live_call", methods=["GET"])
def api_live_call():
    """Live call telemetry stream endpoint for real-time dashboard monitoring."""
    bookings = load_bookings()
    python_count = sum(1 for b in bookings if "python" in (b.get("course_name") or "").lower())
    java_count = sum(1 for b in bookings if "java" in (b.get("course_name") or "").lower())
    logs = read_customer_events()
    
    call_snapshot = dict(active_call_session)
    if call_snapshot.get("active") and call_snapshot.get("start_time"):
        try:
            started = datetime.fromisoformat(call_snapshot["start_time"])
            call_snapshot["duration_seconds"] = int((datetime.now() - started).total_seconds())
        except Exception:
            call_snapshot["duration_seconds"] = 0
            
    return jsonify({
        "active_call": call_snapshot,
        "recent_bookings": bookings[-6:][::-1],
        "stats": {
            "total_calls": len(logs),
            "booked_demos": len(bookings),
            "python_leads": python_count,
            "java_leads": java_count,
            "active_calls_count": 1 if call_snapshot.get("active") else 0
        }
    })


@app.route("/upload_customers", methods=["POST"])
def upload_customers():
    global automation_agent
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename.lower().endswith(".csv"):
        return jsonify({"error": "Upload a CSV file"}), 400
    if automation_agent is None:
        automation_agent = LeadOperationsAgent(CUSTOMER_CSV, call_lead_from_agent)
    leads = automation_agent.import_csv(uploaded)
    return jsonify({"imported": len(leads), "agent": automation_agent.snapshot()})


@app.route("/automation", methods=["POST"])
def automation():
    global automation_agent
    if automation_agent is None:
        automation_agent = LeadOperationsAgent(CUSTOMER_CSV, call_lead_from_agent)
    enabled = request.json.get("enabled", True) if request.is_json else True
    if not enabled:
        automation_agent.stop()
        return jsonify({"started": False, "agent": automation_agent.snapshot()})
    started = automation_agent.start()
    return jsonify({"started": started, "agent": automation_agent.snapshot()})


@app.route("/call_status", methods=["POST"])
def call_status():
    status = normalize_call_status(request.form)
    matching = next((row for row in reversed(read_customer_events()) if row.get("call_sid") == status["call_sid"]), {})
    customer = {
        "name": matching.get("name", ""),
        "age": matching.get("age", ""),
        "college": matching.get("college", ""),
        "phone": matching.get("phone", ""),
        "language": matching.get("language", ""),
        "status": status["status"],
        "duration": status.get("duration", "")
    }
    save_customer_event(customer, status["event"], status["call_sid"])
    if status["status"] in ["completed", "busy", "no-answer", "canceled", "failed"]:
        active_call_session["active"] = False
        active_call_session["stage"] = "completed"
        active_call_session["stage_title"] = f"Call Ended ({status['status']})"
        active_call_session["progress_pct"] = 100
    return "", 204


@app.route("/trigger_call", methods=["POST"])
def trigger_call():
    """Trigger an outbound call via Twilio (uses same env vars as call.py).
    Expects JSON: { "phone": "+123...", "name": "...", ... }
    """
    from twilio.rest import Client
    payload = request.json if request.is_json else request.form
    phone = payload.get("phone")
    customer = customer_from_payload(payload)
    preferred_language = customer["language"]
    if preferred_language not in LANGUAGE_CONFIG:
        preferred_language = "en-IN"
        customer["language"] = preferred_language
    if not phone:
        return jsonify({"error": "Phone number required"}), 400
    if not customer["name"]:
        return jsonify({"error": "Customer name is required"}), 400

    # Initialize live telemetry for dashboard
    active_call_session.update({
        "active": True,
        "call_sid": "PENDING",
        "student_name": customer["name"],
        "student_phone": phone,
        "student_college": customer.get("college", ""),
        "student_age": customer.get("age", ""),
        "language": preferred_language,
        "stage": "connecting",
        "stage_title": "Connecting Voice Channel",
        "progress_pct": 10,
        "course_selected": "",
        "demo_date": "",
        "demo_time": "",
        "booking_status": "in-progress",
        "start_time": datetime.now().isoformat(timespec="seconds"),
        "latest_utterance": f"Dialing {customer['name']} ({phone})...",
        "transcript": [{"role": "System", "text": f"Connecting voice call to {customer['name']} at {phone}", "time": datetime.now().strftime("%H:%M:%S")}]
    })

    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "").strip()
    VOICE_WEBHOOK_URL = os.getenv("VOICE_WEBHOOK_URL", "").strip()
    SIMULATE_MODE = os.getenv("SIMULATE_MODE", "").strip().lower() in ("1", "true", "yes")

    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, VOICE_WEBHOOK_URL]):
        active_call_session.update({
            "active": False,
            "stage": "error",
            "stage_title": "Call Setup Failed",
            "booking_status": "failed",
            "latest_utterance": "Twilio configuration is incomplete"
        })
        return jsonify({"error": "Missing Twilio configuration in environment"}), 500

    webhook = urlparse(VOICE_WEBHOOK_URL)
    if not SIMULATE_MODE and (webhook.scheme != "https" or not webhook.netloc):
        active_call_session.update({
            "active": False,
            "stage": "error",
            "stage_title": "Call Setup Failed",
            "booking_status": "failed",
            "latest_utterance": "VOICE_WEBHOOK_URL must be a public HTTPS URL"
        })
        return jsonify({"error": "VOICE_WEBHOOK_URL must be a public HTTPS URL reachable by Twilio"}), 500

    if SIMULATE_MODE or os.getenv("SIMULATE_MODE", "").lower() in ("1", "true", "yes"):
        import urllib.parse, urllib.request
        form_data = urllib.parse.urlencode({
            "CallSid": "SIMULATED_CALL_SID",
            "From": phone,
            "To": TWILIO_FROM_NUMBER,
            "CallStatus": "in-progress",
        }).encode("utf-8")
        webhook_url = f"{VOICE_WEBHOOK_URL}?{urlencode(customer)}"
        req = urllib.request.Request(webhook_url, data=form_data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req) as resp:
                body = resp.read().decode("utf-8")
            save_customer_event(customer, "call_started", "SIMULATED_CALL_SID")
            active_call_session["call_sid"] = "SIMULATED_CALL_SID"
            return jsonify({"status": "simulated", "webhook_response": body})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # Real call via Twilio
    try:
        from twilio.http.http_client import TwilioHttpClient

        twilio_timeout = float(os.getenv("TWILIO_REQUEST_TIMEOUT", "12"))
        client = Client(
            TWILIO_ACCOUNT_SID,
            TWILIO_AUTH_TOKEN,
            http_client=TwilioHttpClient(timeout=twilio_timeout),
        )
        webhook_url = f"{VOICE_WEBHOOK_URL}?{urlencode(customer)}"
        callback_url = f"{VOICE_WEBHOOK_URL.rsplit('/', 1)[0]}/call_status"
        call = client.calls.create(
            to=phone,
            from_=TWILIO_FROM_NUMBER,
            url=webhook_url,
            status_callback=callback_url,
            status_callback_method="POST",
            status_callback_event=["initiated", "ringing", "answered", "completed"]
        )
        active_call_session["call_sid"] = call.sid
        save_customer_event(customer, "call_started", call.sid)
        return jsonify({"status": "started", "call_sid": call.sid})
    except Exception as exc:
        error_text = str(exc).strip() or exc.__class__.__name__
        error_code = getattr(exc, "code", None)
        if error_code == 20003 or "Authenticate" in error_text:
            error_text = "Twilio authentication failed (error 20003). Generate a new Auth Token for this Account SID, update .env, and restart Flask."
        active_call_session.update({
            "active": False,
            "stage": "error",
            "stage_title": "Call Setup Failed",
            "booking_status": "failed",
            "latest_utterance": f"Twilio error: {error_text}"
        })
        return jsonify({"error": f"Twilio could not start the call: {error_text}"}), 502

# =============================
# INITIAL VOICE CALL ENDPOINT
# =============================
@app.route("/voice", methods=["POST"])
def voice():
    """
    When the student answers the call, an experienced 10,000 Coders Admissions
    Officer warmly introduces the institute and engages in natural dialogue.
    """
    call_id = request.form.get("CallSid", "default")
    phone = request.form.get("From", "unknown")
    customer_name = request.args.get("name", "").strip()
    college = request.args.get("college", "").strip()
    age = request.args.get("age", "").strip()
    preferred_language = request.args.get("language", "en-IN").strip()
    if preferred_language not in LANGUAGE_CONFIG:
        preferred_language = "en-IN"
    
    student_phone[call_id] = phone
    
    call_state[call_id] = {
        "stage": "language_selection",
        "preferred_language": preferred_language,
        "questions_asked": 0,
        "demo_offered": False,
        "course_selected": None,
        "demo_date": None,
        "demo_time": None,
        "student_name": customer_name,
        "student_mobile": phone,
        "college": college,
        "customer_age": age
    }
    
    active_call_session.update({
        "active": True,
        "call_sid": call_id,
        "student_name": customer_name or "Prospective Student",
        "student_phone": phone,
        "student_college": college,
        "student_age": age,
        "language": preferred_language,
        "stage": "language_selection",
        "stage_title": "Language Selection",
        "progress_pct": 10,
        "course_selected": "",
        "demo_date": "",
        "demo_time": "",
        "booking_status": "in-progress",
        "start_time": datetime.now().isoformat(timespec="seconds")
    })
    
    response = VoiceResponse()
    language_prompt = language_selection_prompt()
    add_to_history(call_id, "Officer", language_prompt)

    gather = Gather(
        input="speech dtmf",
        action="/process",
        method="POST",
        timeout=8,
        speechTimeout="auto",
        language="en-IN"
    )
    gather.say(language_prompt, voice="Polly.Aditi", language="en-IN")
    response.append(gather)
    return str(response)

# =============================
# MAIN CONVERSATIONAL ENGINE
# =============================
@app.route("/process", methods=["POST"])
def process():
    """
    MAIN ENGINE: Acts like an authentic Senior Admissions Officer from 10,000 Coders.
    Listens to student, detects course choices, days, times, handles career questions,
    and books live demo slots directly.
    """
    user_input = request.form.get("SpeechResult", "").strip()
    if not user_input:
        user_input = request.form.get("Digits", "").strip()
    call_id = request.form.get("CallSid", "default")
    
    response = VoiceResponse()
    state = get_state(call_id)
    lang_cfg = get_language_config(state)
    lang = state.get("preferred_language", "en-IN")

    if state.get("stage") == "language_selection":
        selected_language = detect_language(user_input)
        if not selected_language:
            prompt = language_selection_prompt() + " Please say one of those five languages."
            add_to_history(call_id, "Officer", prompt)
            gather = Gather(input="speech dtmf", action="/process", method="POST", timeout=8, speechTimeout="auto", language="en-IN")
            gather.say(prompt, voice="Polly.Aditi", language="en-IN")
            response.append(gather)
            return str(response)

        state["preferred_language"] = selected_language
        state["stage"] = "intro"
        update_state(call_id, state)
        lang_cfg = get_language_config(state)
        lang = selected_language
        active_call_session.update({
            "language": selected_language,
            "stage": "intro",
            "stage_title": "Greeting & Introduction",
            "progress_pct": 25
        })
        prompt = lang_cfg["name_prompt"]
        add_to_history(call_id, "Officer", prompt)
        gather = Gather(input="speech dtmf", action="/process", method="POST", timeout=8, speechTimeout="auto", language=lang)
        gather.say(prompt, voice=lang_cfg["voice"], language=lang)
        response.append(gather)
        return str(response)
    
    # Handle silence / no speech
    if not user_input:
        prompt = (
            "I could not hear you clearly. Please let me know if you would like to explore our Python Full Stack or Java Full Stack demo class."
            if lang != "te-IN" else
            "మీరు మాట్లాడింది నాకు స్పష్టంగా వినబడలేదు. మీకు Python Full Stack demo కావాలా లేదా Java Full Stack demo కావాలా చెప్పండి?"
        )
        add_to_history(call_id, "Officer", prompt)
        gather = Gather(input="speech dtmf", action="/process", method="POST", timeout=8, speechTimeout="auto", language=lang)
        gather.say(prompt, voice=lang_cfg["voice"], language=lang)
        response.append(gather)
        return str(response)

    # Record speech
    add_to_history(call_id, "Student", user_input)
    increment_turn(call_id)
    current_turn = get_turn(call_id)
    print(f"\n[Call {call_id} | Turn {current_turn}] Student: {user_input}")

    # Check for hard exit / disconnect request
    if any(word in user_input.lower() for word in ["stop calling", "don't call", "remove me", "not interested at all", "disconnect", "cut the call"]):
        farewell = "Thank you for your time. All the best for your career!" if lang != "te-IN" else "సరేనండి, మీ సమయానికి చాలా ధన్యవాదాలు. ఆల్ ది బెస్ట్!"
        add_to_history(call_id, "Officer", farewell)
        response.say(farewell, voice=lang_cfg["voice"], language=lang)
        response.hangup()
        active_call_session["active"] = False
        active_call_session["stage"] = "completed"
        active_call_session["stage_title"] = "Call Ended"
        active_call_session["progress_pct"] = 100
        return str(response)

    # Extract all relevant slots from the candidate's speech
    slots = extract_slots(user_input)
    detected_course = slots.get("course") or detect_course(user_input)
    detected_day = slots.get("day") or detect_demo_day(user_input)
    detected_time = slots.get("time") or extract_time(user_input)
    
    if detected_course:
        state["course_selected"] = detected_course
        course_title = COURSES.get(detected_course, {}).get("name", detected_course.capitalize())
        active_call_session["course_selected"] = course_title
    if detected_day:
        state["demo_date"] = detected_day
        active_call_session["demo_date"] = detected_day
    if detected_time:
        state["demo_time"] = detected_time
        active_call_session["demo_time"] = detected_time

    course_key = state.get("course_selected") or "python"
    course_meta = COURSES.get(course_key, COURSES["python"])
    course_display = course_meta["name"]

    # -------------------------------------------------------------
    # 1. IMMEDIATE DEMO BOOKING CHECK
    # Triggered when course + day + time are present, or when candidate confirms
    # -------------------------------------------------------------
    should_confirm_booking = False
    
    if state.get("course_selected") and (state.get("demo_date") or detected_day) and (state.get("demo_time") or detected_time):
        should_confirm_booking = True
    elif state.get("course_selected") and (state.get("demo_date") or detected_day) and is_affirmative(user_input):
        state["demo_time"] = state.get("demo_time") or "10:00 AM"
        should_confirm_booking = True
    elif state.get("course_selected") and state.get("stage") in ["demo_time_selection", "demo_interest"] and is_affirmative(user_input):
        state["demo_date"] = state.get("demo_date") or "Monday"
        state["demo_time"] = state.get("demo_time") or "10:00 AM"
        should_confirm_booking = True

    if should_confirm_booking:
        c_day = state.get("demo_date") or "Monday"
        c_time = state.get("demo_time") or "10:00 AM"
        student_dest_phone = state.get("student_mobile") or student_phone.get(call_id, "unknown")
        
        # Save confirmed booking to JSON database
        booking = create_booking(
            phone_number=student_dest_phone,
            course_name=course_display,
            demo_date=c_day,
            demo_time=c_time,
            student_name=state.get("student_name") or "Student",
            college=state.get("college") or "Engineering College",
            language=lang
        )
        
        state["stage"] = "booking_complete"
        update_state(call_id, state)
        
        active_call_session.update({
            "stage": "confirmed",
            "stage_title": "Demo Booking Confirmed",
            "progress_pct": 100,
            "course_selected": course_display,
            "demo_date": c_day,
            "demo_time": c_time,
            "booking_status": "confirmed"
        })
        
        closing_speech = get_closing(booking, lang)
        add_to_history(call_id, "Officer", closing_speech)
        response.say(closing_speech, voice=lang_cfg["voice"], language=lang)
        response.hangup()
        active_call_session["active"] = False
        return str(response)

    # -------------------------------------------------------------
    # 2. COURSE SELECTION (E.g. "Python", "pythofull stack", "Java", "Java Full Stack")
    # -------------------------------------------------------------
    if detected_course:
        state["course_selected"] = detected_course
        
        if detected_day and not detected_time:
            state["demo_date"] = detected_day
            state["stage"] = "demo_time_selection"
            update_state(call_id, state)
            active_call_session.update({
                "stage": "demo_time_selection",
                "stage_title": "Demo Time Selection",
                "progress_pct": 80,
                "course_selected": course_display,
                "demo_date": detected_day
            })
            speech = (
                f"Great choice! {detected_day} is reserved for your {course_display} demo class. "
                "Which time works best for you: morning 10:00 AM, afternoon 2:00 PM, or evening 4:00 PM?"
                if lang != "te-IN" else
                f"చాలా మంచిది! {detected_day} రోజున {course_display} demo కి ఉదయం 10:00 AM, మధ్యాహ్నం 2:00 PM, లేదా సాయంత్రం 4:00 PM లో ఏ సమయం అనుకూలం?"
            )
        else:
            state["stage"] = "demo_date_selection"
            update_state(call_id, state)
            active_call_session.update({
                "stage": "demo_date_selection",
                "stage_title": "Demo Scheduling",
                "progress_pct": 65,
                "course_selected": course_display
            })
            speech = get_course_confirmation(detected_course, lang)
            
        add_to_history(call_id, "Officer", speech)
        gather = Gather(input="speech dtmf", action="/process", method="POST", timeout=8, speechTimeout="auto", language=lang)
        gather.say(speech, voice=lang_cfg["voice"], language=lang)
        response.append(gather)
        return str(response)

    # -------------------------------------------------------------
    # 3. DEMO DAY PROVIDED (E.g. "Monday", "Tuesday", "Friday")
    # -------------------------------------------------------------
    if detected_day:
        state["demo_date"] = detected_day
        state["stage"] = "demo_time_selection"
        update_state(call_id, state)
        active_call_session.update({
            "stage": "demo_time_selection",
            "stage_title": "Demo Time Selection",
            "progress_pct": 80,
            "demo_date": detected_day
        })
        speech = (
            f"Perfect, {detected_day} is locked in! Would 10:00 AM in the morning, 2:00 PM afternoon, or 4:00 PM evening be more convenient?"
            if lang != "te-IN" else
            f"పర్ఫెక్ట్, {detected_day} రోజున demo కి Morning 10:00 AM, Afternoon 2:00 PM, లేదా Evening 4:00 PM లో ఏ time నచ్చుతుంది?"
        )
        add_to_history(call_id, "Officer", speech)
        gather = Gather(input="speech dtmf", action="/process", method="POST", timeout=8, speechTimeout="auto", language=lang)
        gather.say(speech, voice=lang_cfg["voice"], language=lang)
        response.append(gather)
        return str(response)

    # -------------------------------------------------------------
    # 4. DEMO TIME PROVIDED (E.g. "10 AM", "2 PM", "morning", "evening")
    # -------------------------------------------------------------
    if detected_time:
        state["demo_time"] = detected_time
        state["demo_date"] = state.get("demo_date") or "Monday"
        
        student_dest_phone = state.get("student_mobile") or student_phone.get(call_id, "unknown")
        booking = create_booking(
            phone_number=student_dest_phone,
            course_name=course_display,
            demo_date=state["demo_date"],
            demo_time=detected_time,
            student_name=state.get("student_name") or "Student",
            college=state.get("college") or "Engineering College",
            language=lang
        )
        state["stage"] = "booking_complete"
        update_state(call_id, state)
        active_call_session.update({
            "stage": "confirmed",
            "stage_title": "Demo Booking Confirmed",
            "progress_pct": 100,
            "course_selected": course_display,
            "demo_date": state["demo_date"],
            "demo_time": detected_time,
            "booking_status": "confirmed"
        })
        closing_speech = get_closing(booking, lang)
        add_to_history(call_id, "Officer", closing_speech)
        response.say(closing_speech, voice=lang_cfg["voice"], language=lang)
        response.hangup()
        active_call_session["active"] = False
        return str(response)

    # -------------------------------------------------------------
    # 5. GENERAL QUESTION / DOUBT HANDLING (Fees, Placements, Location, Curriculum)
    # -------------------------------------------------------------
    question_type, direct_answer = detect_question_type(user_input)
    if question_type != "unclear":
        answer = direct_answer or generate_answer(question_type, user_input)
        followup_cue = (
            "You can interact live with our senior mentors in a free 1-hour demo session. Would you prefer Python Full Stack or Java Full Stack?"
            if lang != "te-IN" else
            "ఈ వివరాలన్నీ మన 1-hour free live demo లో మీరు mentors తో direct గా discuss చేయవచ్చు. మీకు Python Full Stack ఇష్టమా లేదా Java Full Stack ఇష్టమా?"
        )
        full_reply = f"{answer} {followup_cue}"
        state["stage"] = "course_selection"
        update_state(call_id, state)
        active_call_session.update({
            "stage": "course_selection",
            "stage_title": f"Counseling Q&A ({question_type})",
            "progress_pct": 50
        })
        add_to_history(call_id, "Officer", full_reply)
        gather = Gather(input="speech dtmf", action="/process", method="POST", timeout=8, speechTimeout="auto", language=lang)
        gather.say(full_reply, voice=lang_cfg["voice"], language=lang)
        response.append(gather)
        return str(response)

    # -------------------------------------------------------------
    # 6. AFFIRMATIVE RESPONSES ("Yes", "Sure", "I am interested")
    # -------------------------------------------------------------
    if is_affirmative(user_input):
        if not state.get("course_selected"):
            state["stage"] = "course_selection"
            update_state(call_id, state)
            active_call_session.update({
                "stage": "course_selection",
                "stage_title": "Course Selection",
                "progress_pct": 45
            })
            speech = get_course_selection(lang)
        else:
            state["stage"] = "demo_date_selection"
            update_state(call_id, state)
            active_call_session.update({
                "stage": "demo_date_selection",
                "stage_title": "Demo Date Selection",
                "progress_pct": 65
            })
            speech = get_demo_booking(state["course_selected"], lang)
            
        add_to_history(call_id, "Officer", speech)
        gather = Gather(input="speech dtmf", action="/process", method="POST", timeout=8, speechTimeout="auto", language=lang)
        gather.say(speech, voice=lang_cfg["voice"], language=lang)
        response.append(gather)
        return str(response)

    # -------------------------------------------------------------
    # 7. NEGATIVE RESPONSES / OBJECTION HANDLING
    # -------------------------------------------------------------
    if is_negative(user_input):
        if not state.get("objection_offered"):
            state["objection_offered"] = True
            update_state(call_id, state)
            active_call_session.update({
                "stage": "objection_handling",
                "stage_title": "Addressing Doubts",
                "progress_pct": 35
            })
            speech = (
                "I completely understand. That's why we invite students to our 100% free live coding demo with zero commitment. "
                "You get to code live with senior mentors and see how placements work before making any decision. "
                "Would a free demo session on Monday or Tuesday help you evaluate?"
                if lang != "te-IN" else
                "మీ మాట అర్థమైందండి. ఎటువంటి ఫీజు లేకుండా మీరు మొదట 1-hour free demo class attend అయ్యి, mentor teaching మరియు placement stats స్వయంగా చూడవచ్చు. "
                "Monday లేదా Tuesday లో free demo reserve చేయమంటారా?"
            )
            add_to_history(call_id, "Officer", speech)
            gather = Gather(input="speech dtmf", action="/process", method="POST", timeout=8, speechTimeout="auto", language=lang)
            gather.say(speech, voice=lang_cfg["voice"], language=lang)
            response.append(gather)
            return str(response)
        else:
            farewell = "No problem at all. Thank you for your time, and all the best for your bright career!" if lang != "te-IN" else "పర్లేదండి, మీ సమయానికి చాలా ధన్యవాదాలు. మీ భవిష్యత్తుకు ఆల్ ది బెస్ట్!"
            add_to_history(call_id, "Officer", farewell)
            response.say(farewell, voice=lang_cfg["voice"], language=lang)
            response.hangup()
            active_call_session["active"] = False
            active_call_session["stage"] = "completed"
            active_call_session["stage_title"] = "Call Completed"
            active_call_session["progress_pct"] = 100
            return str(response)

    # -------------------------------------------------------------
    # 8. DEFAULT NATURAL RE-PROMPT
    # -------------------------------------------------------------
    speech = (
        "I'm here to help you get placed in top IT companies through our Python and Java Full Stack programs. "
        "Which course sounds more interesting to you: Python or Java?"
        if lang != "te-IN" else
        "టాప్ IT కంపెనీలలో సాఫ్ట్‌వేర్ ఉద్యోగం సాధించడానికి మన Python మరియు Java Full Stack ప్రోగ్రామ్స్ చాలా బాగుంటాయి. మీకు Python Full Stack ఇష్టమా లేదా Java Full Stack ఇష్టమా?"
    )
    add_to_history(call_id, "Officer", speech)
    gather = Gather(input="speech dtmf", action="/process", method="POST", timeout=8, speechTimeout="auto", language=lang)
    gather.say(speech, voice=lang_cfg["voice"], language=lang)
    response.append(gather)
    return str(response)

# =============================
# RUN THE APP
# =============================
if __name__ == "__main__":
    print("\n[*] Starting 10,000 Coders AI Admissions Desk (Senior Counselor Persona)...")
    print("[*] Webhook endpoint: POST /voice")
    print("[+] Human-like conversational intelligence")
    print("[+] Automatic demo slot booking")
    print("[+] Live dashboard telemetry enabled\n")
    port = int(os.getenv("PORT", "5050"))
    print(f"[*] Dashboard available at http://localhost:{port}/dashboard")
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "0").lower() in ("1", "true", "yes"))
