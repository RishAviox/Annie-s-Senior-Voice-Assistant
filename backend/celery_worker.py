import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from celery import Celery
from dotenv import load_dotenv

load_dotenv(override=True)

# Celery Configuration
BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

celery_app = Celery("voice_assistant_celery", broker=BROKER_URL, backend=RESULT_BACKEND)

# Email Sending configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

@celery_app.task
def send_otp_email_task(receiver_email: str, otp: str):
    print(f"Starting Celery task to send OTP to {receiver_email}")
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = receiver_email
        msg['Subject'] = "Your Verification OTP for Annie's UI"
        
        body = f"Hello,\n\nYour One Time Password (OTP) for registration is: {otp}\n\nPlease enter this on the website to complete your sign-up."
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        text = msg.as_string()
        server.sendmail(SENDER_EMAIL, receiver_email, text)
        server.quit()
        print(f"DEBUG: Sent OTP {otp} to {receiver_email}")
        return True
    except Exception as e:
        print(f"Warning: Failed to actually send email in Celery task. Details: {e}")
        return False
