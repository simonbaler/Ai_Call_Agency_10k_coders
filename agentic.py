"""Small, deterministic agent layer for lead import and sequential call orchestration."""
import csv
import os
import threading
import time
import json
from datetime import datetime


class LeadOperationsAgent:
    def __init__(self, csv_path, call_lead):
        self.csv_path = csv_path
        self.call_lead = call_lead
        self._lock = threading.Lock()
        self.queue = []
        self.running = False
        self.completed = 0
        self.last_error = ""
        self.stop_requested = False
        self.leads_file = os.path.join(os.path.dirname(csv_path), "automation_leads.json")
        self.leads = []
        self._load_leads()

    def _load_leads(self):
        try:
            with open(self.leads_file, "r", encoding="utf-8") as file:
                leads = json.load(file)
            self.leads = leads
            self.queue = [lead for lead in leads if lead.get("status") == "queued"]
            self.completed = sum(1 for lead in leads if lead.get("status") == "completed")
        except (FileNotFoundError, json.JSONDecodeError):
            self.leads = []
            self.queue = []

    def _save_leads(self):
        with open(self.leads_file, "w", encoding="utf-8") as file:
            json.dump(self.leads, file, ensure_ascii=False, indent=2)

    def import_csv(self, file_object):
        rows = list(csv.DictReader(file_object.stream.read().decode("utf-8-sig").splitlines()))
        leads = []
        for row in rows:
            name = (row.get("name") or row.get("customer_name") or row.get("student_name") or "").strip()
            phone = (row.get("phone") or row.get("mobile") or row.get("mobile_number") or row.get("student_phone") or "").strip()
            age = (row.get("age") or "").strip()
            college = (row.get("college") or row.get("university") or "").strip()
            language = (row.get("language") or row.get("preferred_language") or "en-IN").strip()
            if name and phone:
                leads.append({"name": name, "age": age, "college": college, "phone": phone, "language": language, "status": "queued"})
        with self._lock:
            self.queue = leads
            self.leads = leads
            self.completed = 0
            self.last_error = ""
            self._save_leads()
        return leads

    def snapshot(self):
        with self._lock:
            return {"queued": len(self.queue), "completed": self.completed, "running": self.running, "last_error": self.last_error}

    def start(self):
        with self._lock:
            if self.running or not self.queue:
                return False
            self.running = True
            self.stop_requested = False
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def _run(self):
        while True:
            with self._lock:
                if self.stop_requested or not self.queue:
                    self.running = False
                    return
                lead = self.queue.pop(0)
                lead["status"] = "calling"
                self._save_leads()
            try:
                self.call_lead(lead)
                lead["status"] = "completed"
            except Exception as exc:
                lead["status"] = "failed"
                lead["error"] = str(exc)
                with self._lock:
                    self.last_error = str(exc)
            finally:
                with self._lock:
                    self.completed += 1
                    self._save_leads()
            time.sleep(1)

    def stop(self):
        with self._lock:
            self.stop_requested = True


def normalize_call_status(payload):
    return {
        "event": "call_completed",
        "call_sid": payload.get("CallSid", ""),
        "status": payload.get("CallStatus", "unknown"),
        "duration": payload.get("CallDuration", "0"),
    }
