import os
import datetime
from openai import OpenAI
from agents import Agent, Runner  # Import from openai-agents
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv
import pytz  # Add this for timezone support

# Load environment variables from .env file
load_dotenv()

# Retrieve and validate OpenAI API key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in .env file. Please set it as OPENAI_API_KEY=your-api-key")

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Google Calendar setup
SCOPES = ['https://www.googleapis.com/auth/calendar']
CREDENTIALS_FILE = '/Users/../credentials.json'  # Must be for a Desktop app OAuth client

def get_calendar_service():
    creds = None
    token_path = '/Users/../token.json'
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
            except Exception as e:
                return f"Error authorizing Google Calendar: {str(e)}. Pre-authenticate by running option 3 once and approving the OAuth prompt."
    if not creds:
        return "Google Calendar authentication failed. Please ensure credentials.json is valid and pre-authenticate."
    return build('calendar', 'v3', credentials=creds)

# Define Task Agent
task_agent = Agent(
    name="TaskAgent",
    instructions="You are a task management assistant. Generate reminders and meeting summaries based on user input. For scheduling, return 'Handoff to SchedulingAgent'.",
    model="gpt-4o-mini"
)

# Define Scheduling Agent
scheduling_agent = Agent(
    name="SchedulingAgent",
    instructions="You are a scheduling assistant. Provide scheduling-related responses or confirmations. Do not generate reminders or briefs.",
    model="gpt-4o-mini"
)

# Function to create a reminder
def create_reminder(task_description):
    try:
        result = Runner.run_sync(task_agent, f"Create a reminder for: {task_description}")
        if "Handoff to SchedulingAgent" in result.final_output:
            return "Reminder creation requires scheduling, but this function is for reminders only."

        # Create calendar event
        service = get_calendar_service()
        if isinstance(service, str):  # Check if service is an error message
            return f"AI reminder created, but calendar integration failed: {service}"
        
        # Default to creating an all-day event today
        today = datetime.date.today()
        event = {
            'summary': task_description,
            'start': {'date': today.isoformat()},
            'end': {'date': (today + datetime.timedelta(days=1)).isoformat()},
            'description': result.final_output,
        }
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        return f"{result.final_output}\nReminder also added to Google Calendar on {today.strftime('%Y-%m-%d')}."
    except Exception as e:
        return f"Error creating reminder: {str(e)}"

# Function to generate meeting brief
def generate_meeting_brief(meeting_notes):
    try:
        result = Runner.run_sync(task_agent, f"Generate a meeting brief with key takeaways and action items from these notes: {meeting_notes}")
        if "Handoff to SchedulingAgent" in result.final_output:
            return "Meeting brief generation does not require scheduling."
        return result.final_output
    except Exception as e:
        return f"Error generating brief: {str(e)}"

# Function to schedule a meeting
def schedule_meeting(meeting_title, duration_minutes, date_str):
    service = get_calendar_service()
    if isinstance(service, str):  # Check if service is an error message
        return service
    try:
        # Set timezone to America/New_York (EST/EDT)
        est = pytz.timezone('America/New_York')
        start_date = datetime.datetime.strptime(date_str, '%Y-%m-%d')
        start_time = est.localize(start_date.replace(hour=9, minute=0, second=0, microsecond=0))
        end_time = start_time + datetime.timedelta(minutes=duration_minutes)
        # Check for conflicts in EST
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_time.isoformat(),
            timeMax=end_time.isoformat(),
            timeZone='America/New_York',
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        if events:
            return "Time slot is busy. Please choose another date."
        # Prompt for attendees
        attendees_input = input("Enter attendee email addresses (comma-separated, or press Enter to skip): ")
        attendees = []
        if attendees_input.strip():
            attendee_emails = [email.strip() for email in attendees_input.split(',')]
            attendees = [{'email': email} for email in attendee_emails if email and '@' in email]  # Basic email validation
        event = {
            'summary': meeting_title,
            'start': {'dateTime': start_time.isoformat(), 'timeZone': 'America/New_York'},
            'end': {'dateTime': end_time.isoformat(), 'timeZone': 'America/New_York'},
            'attendees': attendees
        }
        event = service.events().insert(calendarId='primary', body=event).execute()
        # Confirm with SchedulingAgent
        result = Runner.run_sync(scheduling_agent, f"Confirm a meeting titled '{meeting_title}' scheduled on {date_str} at 9:00 AM EST for {duration_minutes} minutes with attendees {', '.join(attendee_emails) if attendees else 'none'}.")
        return result.final_output
    except Exception as e:
        if hasattr(e, 'content'):
            import json
            error_details = json.loads(e.content.decode('utf-8'))
            return f"Error scheduling meeting: {str(e)} - Details: {error_details}"
        return f"Error scheduling meeting: {str(e)}"

# Main demo interface
def run_demo():
    print("=== AI-Powered Life Assistant Demo ===")
    print("1. Set a reminder")
    print("2. Generate a meeting brief")
    print("3. Schedule a meeting")
    print("4. Exit")
    while True:
        choice = input("\nEnter your choice (1-4): ")
        if choice == '1':
            task = input("Enter task description (e.g., 'Call client tomorrow'): ")
            print("\nResult:")
            print(create_reminder(task))
        elif choice == '2':
            notes = input("Enter meeting notes (e.g., 'Discussed project timeline, need to finalize budget'): ")
            print("\nResult:")
            print(generate_meeting_brief(notes))
        elif choice == '3':
            title = input("Enter meeting title: ")
            duration = int(input("Enter duration in minutes: "))
            date = input("Enter date (YYYY-MM-DD): ")
            print("\nResult:")
            print(schedule_meeting(title, duration, date))
        elif choice == '4':
            print("Demo ended. Thank you!")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    run_demo()

