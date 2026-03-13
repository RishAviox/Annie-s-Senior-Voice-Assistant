# 📝 Setup & Deployment Notes

This document provides essential instructions for anyone who wants to demo, test, or deploy this project. 

> [!IMPORTANT]
> This project was developed and tested on **Windows**. 

---

### 🗄️ 1. Database Setup (PostgreSQL)

The project uses PostgreSQL for user management and role-based access control.

#### **A. Create the Database**
1. Open your PostgreSQL terminal (psql) or a tool like pgAdmin 4.
2. Create a new database named `Registrations`:
   ```sql
   CREATE DATABASE "Registrations";
   ```

#### **B. Connection Configuration**
The backend now connects using environment variables defined in `backend/.env`.
- **DB_HOST:** `127.0.0.1` (Recommended over `localhost` on Windows)
- **DB_NAME:** `Registrations`
- **DB_USER:** `postgres`
- **DB_PASSWORD:** `Postgres@123` (Change in `.env` if different)

#### **C. Create Tables**
Run the following SQL commands to set up the necessary tables:

```sql
-- Create Users Table
CREATE TABLE users (
    email VARCHAR(255) PRIMARY KEY,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    username VARCHAR(100),
    password VARCHAR(255),
    phone VARCHAR(20),
    role VARCHAR(20) DEFAULT 'user',
    profile_image TEXT,
    is_verified BOOLEAN DEFAULT TRUE,
    otp VARCHAR(10)
);

-- Create Addresses Table
CREATE TABLE addresses (
    email VARCHAR(255) REFERENCES users(email) ON DELETE CASCADE,
    address1 TEXT,
    address2 TEXT,
    city VARCHAR(100),
    state VARCHAR(100),
    pincode VARCHAR(20),
    country VARCHAR(100)
);
```

#### **D. Creating an Admin User**
To access the Admin Dashboard, at least one user must have the `admin` role. You can manually set this in the database:
```sql
UPDATE users SET role = 'admin' WHERE email = 'your-email@example.com';
```

---

### 🎙️ 2. Voice Assistant Hardware (Windows)
The voice assistant requires **PortAudio** for microphone and speaker interaction. On Windows, if you encounter `PyAudio` installation errors, you may need to install the **Visual Studio Build Tools** (Select "Desktop development with C++").

---

### 🛠️ 3. Environment Variables
Ensure you have a `.env` file inside the `backend/` folder with the following:
```env
# LLM Provider Selection (choose 'google' or 'groq')
LLM_PROVIDER=google

# API Keys
GOOGLE_API_KEY=your_google_gemini_api_key
GROQ_API_KEY=your_groq_api_key

# Database (use 127.0.0.1 for faster connections on Windows)
DB_HOST=127.0.0.1
DB_NAME=Registrations
DB_USER=postgres
DB_PASSWORD=Postgres@123

# Piper TTS Paths
PIPER_EXE=C:\piper\piper.exe
PIPER_MODEL=C:\piper\en_US-lessac-high.onnx
PIPER_LIB_PATH=C:\piper

# Celery & Redis
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0

# Email (for OTP)
SENDER_EMAIL=your_email@gmail.com
SENDER_PASSWORD=your_app_password
```

---

### 🚀 4. Running the Demo
1. **Start Redis server** (standard port 6379).
2. **Start Backend:** `cd backend && python main.py`
3. **Start Celery:** `cd backend && celery -A celery_worker.celery_app worker --loglevel=info -P solo`
4. **Start Frontend:** `cd frontend && npm run dev`
