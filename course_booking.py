# Course Selection and Slot Booking Intelligence
# Handles course selection, slot booking, and confirmation with fuzzy speech matching
import re
from booking_system import (
    COURSES, DEMO_SLOTS, get_course_info, 
    create_booking, get_booking_confirmation_message
)

class CourseBookingManager:
    """Manages course selection and demo slot booking with fuzzy speech tolerance"""
    
    def get_course_selection_message(self, language="en-IN"):
        """Ask student which course they want"""
        if language == "te-IN":
            return (
                "మన దగ్గర two flagship programs ఉన్నాయి: "
                "1. Python Full Stack (8 weeks, live Django & React projects) "
                "2. Java Full Stack (10 weeks, Spring Boot & Microservices). "
                "మీకు Python Full Stack ఇష్టమా లేదా Java Full Stack ఇష్టమా?"
            )
        elif language == "hi-IN":
            return (
                "Humare paas do main job-oriented courses hain: "
                "1. Python Full Stack - 8 weeks, React aur Django ke live projects "
                "2. Java Full Stack - 10 weeks, Spring Boot aur Microservices ke saath. "
                "Aap Python Full Stack karna chahenge ya Java Full Stack?"
            )
        return (
            "We offer two high-demand programs with placement support: "
            "1. Python Full Stack - 8 weeks with Django, React, and real projects. "
            "2. Java Full Stack - 10 weeks with Spring Boot and Microservices. "
            "Which one would you like to explore: Python or Java?"
        )
    
    def get_course_confirmation(self, course_key, language="en-IN"):
        """Confirm course selection and offer demo"""
        course = get_course_info(course_key)
        if not course:
            course = COURSES.get("python")
        
        c_name = course["name"]
        duration = course["duration"]
        
        if language == "te-IN":
            return (
                f"చాలా మంచి choice! {c_name} లో practical coding, live projects, మరియు 100% placement assistance ఉంటాయి. "
                f"దీని గురించి ఒక 1-hour free live demo class attend అవ్వగలరా? "
                f"Monday నుండి Friday వరకు morning 10 AM, afternoon 2 PM, evening 4 PM slots ఉన్నాయి. "
                f"మీకు ఏ day మరియు time convenient?"
            )
        elif language == "hi-IN":
            return (
                f"Bahut badhiya choice! {c_name} {duration} ka program hai, real projects aur placement assistance ke saath. "
                f"Iske liye ek free 1-hour live demo class available hai. "
                f"Monday se Friday tak 10 AM, 2 PM, ya 4 PM mein se kaunsa time aapke liye best rahega?"
            )
        return (
            f"Excellent choice! Our {c_name} is an intensive {duration} program with live industry projects and dedicated placement assistance. "
            f"We have a free 1-hour interactive demo class where you code live with our senior mentors. "
            f"Slots are open Monday through Friday at 10:00 AM, 2:00 PM, and 4:00 PM. Which day and time works best for you?"
        )
    
    def get_demo_booking_message(self, course_key, language="en-IN"):
        """Offer to book demo slot"""
        if language == "te-IN":
            return "మీ demo slot book చేయడానికి Monday నుండి Friday లో ఏ రోజు convenient అంటారు? 10 AM, 2 PM లేదా 4 PM?"
        elif language == "hi-IN":
            return "Aapka demo slot book karne ke liye Monday se Friday mein kaunsa din aur time theek rahega? 10 AM, 2 PM ya 4 PM?"
        return "To confirm your demo slot, which day works best from Monday to Friday? We have slots at 10:00 AM, 2:00 PM, and 4:00 PM."
    
    def get_demo_time_message(self, language="en-IN"):
        """Ask for preferred demo time"""
        if language == "te-IN":
            return "Available times: Morning 10:00 AM, Afternoon 2:00 PM, Evening 4:00 PM. మీకు ఏ time convenient?"
        elif language == "hi-IN":
            return "Available slots hain 10:00 AM, 2:00 PM, aur 4:00 PM. Aap kis time join kar sakte hain?"
        return "Available times are 10:00 AM, 2:00 PM, and 4:00 PM. Which time suits your schedule?"
    
    def get_closing_message(self, booking, language="en-IN"):
        """Professional closing with booking details"""
        if not booking:
            return "Thank you for speaking with 10,000 Coders. Have a wonderful day!"
        
        c_name = booking.get("course_name", "Full Stack")
        d_day = booking.get("demo_date", "upcoming batch")
        d_time = booking.get("demo_time", "10:00 AM")
        
        if language == "te-IN":
            return (
                f"ధన్యవాదాలు! మీ {c_name} demo slot {d_day} రోజున {d_time} కి confirm అయ్యింది. "
                f"Zoom link మరియు batch details మీ WhatsApp number కి పంపిస్తున్నాము. "
                f"Demo session లో కలుద్దాం, all the best!"
            )
        elif language == "hi-IN":
            return (
                f"Dhanyavaad! Aapka {c_name} demo slot {d_day} ko {d_time} par confirm ho gaya hai. "
                f"Zoom link aur details aapke WhatsApp par send kar di gayi hain. All the best!"
            )
        return (
            f"Wonderful! Your demo session for {c_name} is confirmed for {d_day} at {d_time}. "
            f"We are sending the meeting link and orientation details directly to your WhatsApp. "
            f"Thank you for choosing 10,000 Coders, and see you in the demo class!"
        )
    
    def get_course_name_from_input(self, user_input):
        """
        Extract course name from user input with high tolerance for speech recognition errors:
        - pythofull stack, pytho full stack, pythofull, python fullstack, python, py
        - java fullstack, java full stack, java, spring boot
        """
        if not user_input:
            return None
        text = str(user_input).lower().strip()
        
        # Check Python variations
        python_patterns = [
            r"\bpython\b", r"\bpythofull\b", r"\bpytho\b", r"\bpy\b", 
            r"\bpython\s*full\s*stack\b", r"\bpython\s*fullstack\b",
            r"\bfull\s*stack\s*python\b", r"\bdjango\b"
        ]
        for pattern in python_patterns:
            if re.search(pattern, text):
                return "python"
        
        # Check Java variations
        java_patterns = [
            r"\bjava\b", r"\bjava\s*full\s*stack\b", r"\bjava\s*fullstack\b",
            r"\bfull\s*stack\s*java\b", r"\bspring\s*boot\b", r"\bspring\b"
        ]
        for pattern in java_patterns:
            if re.search(pattern, text):
                return "java"
        
        # DTMF digit checks
        if text == "1":
            return "python"
        if text == "2":
            return "java"
            
        return None
    
    def get_day_from_input(self, user_input):
        """Extract day from user input with word and digit mapping"""
        if not user_input:
            return None
        text = str(user_input).lower().strip()
        
        day_map = {
            "monday": ["monday", "mon", "somvar", "1"],
            "tuesday": ["tuesday", "tue", "mangalvar", "2"],
            "wednesday": ["wednesday", "wed", "budhvar", "3"],
            "thursday": ["thursday", "thu", "guruvar", "4"],
            "friday": ["friday", "fri", "shukravar", "5"]
        }
        
        for standard_day, aliases in day_map.items():
            for alias in aliases:
                # Match word boundary or standalone digit
                if re.search(r"\b" + re.escape(alias) + r"\b", text):
                    return standard_day.capitalize()
                    
        return None
    
    def get_time_from_input(self, user_input):
        """Extract time from user input with AM/PM & colloquial recognition"""
        if not user_input:
            return None
        text = str(user_input).lower().strip()
        
        # Morning / 10 AM
        if any(term in text for term in ["10 am", "10am", "10:00 am", "10:00am", "10 o'clock", "morning", "10"]):
            return "10:00 AM"
            
        # Afternoon / 2 PM
        if any(term in text for term in ["2 pm", "2pm", "2:00 pm", "2:00pm", "afternoon", "2 o'clock", "2"]):
            return "2:00 PM"
            
        # Evening / 4 PM
        if any(term in text for term in ["4 pm", "4pm", "4:00 pm", "4:00pm", "evening", "4 o'clock", "4"]):
            return "4:00 PM"
            
        return None
        
    def extract_slots(self, user_input):
        """Extract course, day, and time in a single utterance if present"""
        return {
            "course": self.get_course_name_from_input(user_input),
            "day": self.get_day_from_input(user_input),
            "time": self.get_time_from_input(user_input)
        }

# Global singleton instance
booking_manager = CourseBookingManager()

def get_course_selection(language="en-IN"):
    return booking_manager.get_course_selection_message(language)

def get_course_confirmation(course_name, language="en-IN"):
    return booking_manager.get_course_confirmation(course_name, language)

def get_demo_booking(course_name, language="en-IN"):
    return booking_manager.get_demo_booking_message(course_name, language)

def get_demo_time(language="en-IN"):
    return booking_manager.get_demo_time_message(language)

def get_booking_confirmation(booking):
    return get_booking_confirmation_message(booking)

def get_closing(booking, language="en-IN"):
    return booking_manager.get_closing_message(booking, language)

def extract_course(user_input):
    return booking_manager.get_course_name_from_input(user_input)

def extract_day(user_input):
    return booking_manager.get_day_from_input(user_input)

def extract_time(user_input):
    return booking_manager.get_time_from_input(user_input)

def extract_slots(user_input):
    return booking_manager.extract_slots(user_input)
