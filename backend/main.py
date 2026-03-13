from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import uvicorn
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv
load_dotenv(override=True)
from voice_assistant import VoiceAssistant
from fastapi import UploadFile, File, Form
from fastapi.responses import FileResponse
import shutil
from google.oauth2 import id_token
from google.auth.transport import requests
import secrets
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

assistant = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global assistant
    print("Initializing Voice Assistant...")
    assistant = VoiceAssistant(mode="api")
    
    # Check/Add profile_image, is_verified, otp columns safely
    try:
        conn = connect_db()
        cur = conn.cursor()
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_image TEXT;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT TRUE;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS otp VARCHAR(10);")
        conn.commit()
        cur.close()
        conn.close()
        print("DB Schema verified: profile_image, is_verified, otp columns exist.")
    except Exception as e:
        print("Error updating schema:", e)
        
    yield
    print("Shutting down Voice Assistant...")

app = FastAPI(title="Conversational AI Powered by Google Gemini", lifespan=lifespan)

# Ensure static/profiles exists for image uploads
os.makedirs("static/profiles", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup CORS to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production, e.g. ["http://localhost:5173"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class create_user(BaseModel):
    first_name: str 
    last_name: str
    phone_number: int
    email: EmailStr
    password: str

class login_request(BaseModel):
    email: EmailStr
    password: str

class GoogleLoginRequest(BaseModel):
    token: str
    login_type: str = "login"
    
class GooglePhoneUpdateRequest(BaseModel):
    email: EmailStr
    phone: str

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str

# Imported Celery Task for Sending Emails
from celery_worker import send_otp_email_task

# Profile & Address schemas
class AddressBase(BaseModel):
    address1: Optional[str] = None
    address2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[int] = None
    country: Optional[str] = None

class AddressCreate(AddressBase):
    email: EmailStr
    address1: str
    city: str
    state: str
    pincode: int
    country: str

class FullProfileUpdate(AddressBase):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    
# Replace this with your actual Google Client ID
# Google Client ID from environment or fallback
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "82095107124-aifr2eqrljqgsh9m4kmga7ubdtr08ga8.apps.googleusercontent.com")

    
def connect_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "Registrations"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "Postgres@123"),
    )

@app.get("/")
def greet():
    return {"message": "Welcome to the Registration Page"}

@app.post("/register")
def register_user(user: create_user):
    generated_username = user.email.split("@")[0]
    generated_otp = str(random.randint(100000, 999999))

    try:
        conn = connect_db()
        cur = conn.cursor()

        # Check if user already exists
        cur.execute("SELECT is_verified FROM users WHERE email = %s", (user.email,))
        existing_user = cur.fetchone()

        if existing_user:
            if existing_user[0] is True:
                raise HTTPException(status_code=400, detail="Email already registered and verified.")
            else:
                # Update existing unverified user with new details and new OTP
                cur.execute("""
                    UPDATE users SET first_name=%s, last_name=%s, password=%s, username=%s, phone=%s, otp=%s
                    WHERE email=%s
                """, (user.first_name, user.last_name, user.password, generated_username, str(user.phone_number), generated_otp, user.email))
        else:
            query = """
            INSERT INTO users (first_name, last_name, email, password, username, phone, is_verified, otp)
            VALUES (%s, %s, %s, %s, %s, %s, FALSE, %s)
            """
            values = (
                user.first_name,
                user.last_name,
                user.email,
                user.password,
                generated_username,
                str(user.phone_number),
                generated_otp
            )
            cur.execute(query, values)

        conn.commit()
        cur.close()
        conn.close()

        # Try to send email asynchronously using Celery
        try:
            send_otp_email_task.delay(user.email, generated_otp)
            print(f"Enqueued email task to {user.email}")
        except Exception as celery_err:
            print(f"Warning: Could not connect to celery broker: {celery_err}")

        return {
            "message": "OTP generated. Please check your email.",
            "requires_otp": True,
            "email": user.email
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.post("/verify-otp")
def verify_otp(request: VerifyOTPRequest):
    try:
        conn = connect_db()
        cur = conn.cursor()
        cur.execute("SELECT otp FROM users WHERE email = %s AND is_verified = FALSE", (request.email,))
        record = cur.fetchone()
        
        if not record:
            cur.close()
            conn.close()
            raise HTTPException(status_code=400, detail="User not found or already verified.")
            
        if record[0] == request.otp:
            cur.execute("UPDATE users SET is_verified = TRUE, otp = NULL WHERE email = %s", (request.email,))
            
            # Fetch user details to log them in directly
            cur.execute("SELECT password, username, first_name, last_name, role, profile_image FROM users WHERE email = %s", (request.email,))
            user_record = cur.fetchone()
            
            conn.commit()
            cur.close()
            conn.close()
            
            return {
                "message": "Verification and Login Successful",
                "username": user_record[1],
                "first_name": user_record[2],
                "last_name": user_record[3],
                "role": user_record[4],
                "profile_image": user_record[5],
                "email": request.email
            }
        else:
            cur.close()
            conn.close()
            raise HTTPException(status_code=400, detail="Invalid OTP.")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@app.post("/login")
def login_user(credential: login_request):
    try:
        conn = connect_db()
        cur = conn.cursor()

        cur.execute("SELECT password, username, first_name, last_name, role, profile_image, is_verified FROM users WHERE email = %s", (credential.email,))
        user_record = cur.fetchone()

        cur.close()
        conn.close()

        if user_record is None:
            raise HTTPException(status_code=404, detail="No user found with this email")
            
        if not user_record[6]: # is_verified
            raise HTTPException(status_code=403, detail="Email not verified. Please complete OTP verification first.")
            
        # Check password against database
        if user_record[0] == credential.password:
            return {
                "message": "Login Successful",
                "username": user_record[1],
                "first_name": user_record[2],
                "last_name": user_record[3],
                "role": user_record[4], # Send the role back to React
                "profile_image": user_record[5],
                "email": credential.email
            }
        else:
            raise HTTPException(status_code=401, detail="Incorrect password, please try again")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"server error: {str(e)}")

@app.post("/google-login")
def google_login(credential: GoogleLoginRequest):
    try:
        # Verify the token with Google
        idinfo = id_token.verify_oauth2_token(credential.token, requests.Request(), GOOGLE_CLIENT_ID)
        
        email = idinfo.get("email")
        first_name = idinfo.get("given_name", "")
        last_name = idinfo.get("family_name", "")
        
        conn = connect_db()
        cur = conn.cursor()

        # Check if user already exists
        # Check if user already exists
        cur.execute("SELECT username, first_name, last_name, role, phone, profile_image, is_verified FROM users WHERE email = %s", (email,))
        user_record = cur.fetchone()

        profile_image = None

        if user_record:
            # User exists, log them in
            username = user_record[0]
            role = user_record[3]
            phone = user_record[4]
            profile_image = user_record[5]
            is_verified = user_record[6]
            
            # If they had an unverified regular account but logged in via Google, verify them!
            if not is_verified:
                 cur.execute("UPDATE users SET is_verified = TRUE, otp = NULL WHERE email = %s", (email,))
                 conn.commit()
                 
        else:
            # User doesn't exist
            if credential.login_type == "login":
                # They pressed Google Sign IN, but don't have an account
                raise HTTPException(status_code=404, detail="Account not found. Please sign up first.")
                
            # Otherwise, they are pressing Google Sign UP
            username = email.split("@")[0]
            # Generate a random password since they use Google Login
            random_password = secrets.token_hex(8) 
            role = "user" # default role
            
            # Note: We are setting phone to empty or a default since Google doesn't provide it by default
            cur.execute("""
            INSERT INTO users (first_name, last_name, email, password, username, phone, role, is_verified)
            VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
            """, (first_name, last_name, email, random_password, username, "", role))
            conn.commit()

        cur.close()
        conn.close()

        return {
            "message": "Login Successful",
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "role": role,
            "email": email,
            "requires_phone": False,
            "profile_image": profile_image
        }

    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Google token")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@app.post("/update-google-phone")
def update_google_phone(request: GooglePhoneUpdateRequest):
    try:
        conn = connect_db()
        cur = conn.cursor()

        cur.execute("UPDATE users SET phone = %s WHERE email = %s", (request.phone, request.email))
        
        if cur.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="User not found")

        conn.commit()
        cur.close()
        conn.close()

        return {"message": "Phone number updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

# Profile & Address Endpoints

@app.post("/address", tags=["Address"])
def add_address(address: AddressCreate):
    try:
        conn = connect_db()
        cur = conn.cursor()
        
        query = """
        INSERT INTO addresses (email, address1, address2, city, state, pincode, country)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cur.execute(query, (
            address.email, address.address1, address.address2,
            address.city, address.state, str(address.pincode), address.country
        ))
        
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "Success", "message": f"Address saved for {address.email}"}
    
    except psycopg2.IntegrityError:
        raise HTTPException(status_code=400, detail="Foreign Key violation: User email not found in records.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/profile/{email}", tags=["Profile"])
def get_full_profile(email: EmailStr):
    try:
        conn = connect_db()
        cur = conn.cursor(cursor_factory=RealDictCursor) 
        
        query = """
        SELECT u.first_name, u.last_name, u.username, u.phone, u.email, u.profile_image,
               a.address1, a.address2, a.city, a.state, a.pincode, a.country
        FROM users u
        LEFT JOIN addresses a ON u.email = a.email
        WHERE u.email = %s
        """
        cur.execute(query, (email,))
        record = cur.fetchone()
        
        cur.close()
        conn.close()

        if not record:
            raise HTTPException(status_code=404, detail="User not found")
            
        return {"status": "success", "data": record}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/profile/{email}", tags=["Profile"])
def update_profile(email: EmailStr, data: FullProfileUpdate):
    conn = None
    try:
        conn = connect_db()
        cur = conn.cursor()

        cur.execute("""
            UPDATE users SET 
                first_name = COALESCE(%s, first_name), 
                last_name = COALESCE(%s, last_name), 
                phone = COALESCE(%s, phone) 
            WHERE email = %s
        """, (data.first_name, data.last_name, data.phone, email))

        cur.execute("""
            UPDATE addresses SET 
                address1 = COALESCE(%s, address1), 
                address2 = COALESCE(%s, address2), 
                city = COALESCE(%s, city), 
                state = COALESCE(%s, state), 
                pincode = COALESCE(%s, pincode::text), 
                country = COALESCE(%s, country) 
            WHERE email = %s
        """, (
            data.address1, 
            data.address2, 
            data.city, 
            data.state, 
            str(data.pincode) if data.pincode is not None else None, 
            data.country, 
            email
        ))

        # Check if the address was actually updated. If no rows affected, maybe address didn't exist?
        # A common fix is to do an INSERT ON CONFLICT or just insert if no row was updated.
        if cur.rowcount == 0 and data.address1:
             cur.execute("""
                 INSERT INTO addresses (email, address1, address2, city, state, pincode, country)
                 VALUES (%s, %s, %s, %s, %s, %s, %s)
             """, (email, data.address1, data.address2, data.city, data.state, str(data.pincode) if data.pincode else None, data.country))

        conn.commit()
        cur.close()
        conn.close()
        return {"message": "Profile updated successfully"}
        
    except Exception as e:
        if conn: 
            conn.rollback() 
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")

@app.delete("/profile/{email}", tags=["Profile"])
def delete_profile(email: EmailStr):
    conn = None
    try:
        conn = connect_db()
        cur = conn.cursor()

        cur.execute("DELETE FROM addresses WHERE email = %s", (email,))
        cur.execute("DELETE FROM users WHERE email = %s", (email,))

        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")

        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": f"User {email} deleted"}
        
    except Exception as e:
        if conn: conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/profile/{email}/image", tags=["Profile"])
async def upload_profile_image(email: EmailStr, file: UploadFile = File(...)):
    try:
        os.makedirs("static/profiles", exist_ok=True)
        ext = file.filename.split(".")[-1]
        filename = f"{email.split('@')[0]}_{secrets.token_hex(4)}.{ext}"
        filepath = f"static/profiles/{filename}"
        
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        image_url = f"http://localhost:8000/static/profiles/{filename}"
        
        conn = connect_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET profile_image = %s WHERE email = %s", (image_url, email))
        conn.commit()
        cur.close()
        conn.close()
        
        return {"status": "success", "image_url": image_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat/text")
async def chat_text(request: dict):
    """Chat endpoint for receiving text and returning a text + TTS response."""
    text_input = request.get("text")
    user_id = request.get("user_id", "anonymous")
    if not text_input:
        raise HTTPException(status_code=400, detail="Missing text input")
    
    try:
        user_text, response_text, wav_path = assistant.process_api(text_input=text_input, user_id=user_id, generate_audio=False)
        return {"user_text": user_text, "response_text": response_text, "audio_url": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat/audio")
async def chat_audio(file: UploadFile = File(...), user_id: str = Form("anonymous")):
    """Chat endpoint for receiving audio file and returning text + TTS response."""
    if not file.filename.endswith(('.wav', '.mp3', '.ogg', '.webm', '.m4a')):
        raise HTTPException(status_code=400, detail="Unsupported audio format")
    
    temp_file_path = f"temp_{file.filename}"
    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        user_text, response_text, wav_path = assistant.process_api(audio_file_path=temp_file_path, user_id=user_id)
        return {"user_text": user_text, "response_text": response_text, "audio_url": "/chat/audio/response"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

@app.get("/chat/audio/response")
async def get_audio_response():
    """Endpoint to retrieve generated TTS audio."""
    if os.path.exists("output.wav"):
        return FileResponse("output.wav", media_type="audio/wav")
    raise HTTPException(status_code=404, detail="Audio not found")

# Admin Endpoints
@app.get("/admin/users", tags=["Admin"])
def get_all_users():
    try:
        conn = connect_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT first_name, last_name, email, username, phone, role, is_verified FROM users ORDER BY first_name ASC")
        users = cur.fetchall()
        cur.close()
        conn.close()
        return {"status": "success", "users": users}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/admin/users/{email}", tags=["Admin"])
def admin_delete_user(email: EmailStr):
    conn = None
    try:
        conn = connect_db()
        cur = conn.cursor()
        # Prevent deleting admins
        cur.execute("SELECT role FROM users WHERE email = %s", (email,))
        user_record = cur.fetchone()
        if not user_record:
            raise HTTPException(status_code=404, detail="User not found")
        if user_record[0] == "admin":
            raise HTTPException(status_code=403, detail="Cannot delete an administrator account")
        
        cur.execute("DELETE FROM addresses WHERE email = %s", (email,))
        cur.execute("DELETE FROM users WHERE email = %s", (email,))
        
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
            
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": f"Successfully deleted user {email}"}
    except Exception as e:
        if conn: conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
