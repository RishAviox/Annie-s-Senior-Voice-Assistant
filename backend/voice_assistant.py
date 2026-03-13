import os
import time
import wave
import subprocess
import traceback
import numpy as np
import uuid
from datetime import datetime
import collections
import re

import torch
import whisper
import pyaudio

# LangChain & Gemini
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq

# Qdrant
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue
)
from dotenv import load_dotenv
load_dotenv(override=True)

# ===================== CONFIG =====================

# SYSTEM SETTINGS
OUTPUT_WAV = "output.wav"
MIC_SAMPLE_RATE = 16000
PLAYBACK_CHUNK = 4096
MIC_CHUNK = 512

# VAD SENSITIVITY
VAD_THRESHOLD = 0.6
SILENCE_LIMIT = 2.0
SPEECH_LIMIT = 15.0
PRE_RECORD_BUFFER = 0.5
MIN_SPEECH_DURATION = 0.5

# AUDIO SENSITIVITY (Interruption)
INTERRUPT_SENSITIVITY = 0.03

# PATHS
PIPER_EXE = os.getenv("PIPER_EXE", r"C:\piper\piper.exe")
PIPER_MODEL = os.getenv("PIPER_MODEL", r"C:\piper\en_US-lessac-high.onnx")
PIPER_LIB_PATH = os.getenv("PIPER_LIB_PATH", r"C:\piper")

# QDRANT
QDRANT_PATH = "./qdrant_storage"
QDRANT_COLLECTION = "voice_assistant_memory"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# FIX 3a: File that stores the persistent session ID across restarts
SESSION_ID_FILE = "./session_id.txt"

# MEMORY TUNING
RECENT_TURNS_TO_INJECT = 6       # How many recent turns to always include in context
QDRANT_SEARCH_LIMIT = 8          # Increased to fetch more candidates before re-ranking
QDRANT_SCORE_THRESHOLD = 0.2     # FIX 5: Lowered from 0.3 — catches food/location/preference memories
RECENCY_WEIGHT = 0.01            # FIX 4: Bonus per turn_index to prefer newer memories over older ones


GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")

# ===================== HELPERS =====================

def log(msg, important=False):
    if important:
        print(f"\033[96m{msg}\033[0m")
    else:
        print(f"\033[90m{msg}\033[0m")

def check_piper_paths():
    if not os.path.exists(PIPER_EXE):
        raise FileNotFoundError(f"Piper executable not found at {PIPER_EXE}")
    if not os.path.exists(PIPER_MODEL):
        raise FileNotFoundError(f"Piper model not found at {PIPER_MODEL}")

# ===================== MEMORY MANAGER =====================

class QdrantMemoryManager:
    """
    Manages both short-term (in-process cache) and long-term (Qdrant on-disk) memory.
    Shared between voice and text modes.
    """

    def __init__(self):
        log("🗄️  Initializing Memory...", True)
        self.client = QdrantClient(path=QDRANT_PATH)
        self.embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )

        # We will no longer rely on a single global session ID file.
        # Instead, turn indices and recent turns are tracked per-user.
        self.user_turn_index = collections.defaultdict(int)
        self.user_recent_turns = collections.defaultdict(list)
        self._setup_collection()

    def _setup_collection(self):
        collections = self.client.get_collections().collections
        if QDRANT_COLLECTION not in [c.name for c in collections]:
            self.client.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )

    def add_turn(self, user_text, ai_text, user_id="anonymous"):
        text = f"User: {user_text}\nAI: {ai_text}"
        vector = self.embeddings.embed_query(text)

        self.user_turn_index[user_id] += 1
        current_turn = self.user_turn_index[user_id]

        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "user": user_text,
                "ai": ai_text,
                "full_text": text,
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id,
                "turn_index": current_turn
            }
        )
        self.client.upsert(collection_name=QDRANT_COLLECTION, points=[point])

        self.user_recent_turns[user_id].append({
            "user": user_text,
            "ai": ai_text,
            "full_text": text,
            "turn_index": current_turn
        })
        
        # Keep only the N most recent turns per user
        if len(self.user_recent_turns[user_id]) > RECENT_TURNS_TO_INJECT:
            self.user_recent_turns[user_id].pop(0)

        log(f"💾 Memory saved (user: {user_id}, turn: {current_turn})")

    def _expand_query(self, query, user_id="anonymous"):
        words = query.strip().split()
        if len(words) <= 4 and self.user_recent_turns[user_id]:
            last = self.user_recent_turns[user_id][-1]
            enriched = f"{query} {last['user']} {last['ai']}"
            log(f"🔍 Query expanded for search: '{enriched[:80]}...'")
            return enriched
        return query

    def search(self, query, limit=QDRANT_SEARCH_LIMIT, user_id="anonymous"):
        context_parts = []
        recent_turns = self.user_recent_turns[user_id]

        if recent_turns:
            context_parts.append("=== Recent Conversation ===")
            for turn in recent_turns:
                context_parts.append(turn["full_text"])

        try:
            expanded_query = self._expand_query(query, user_id)
            vector = self.embeddings.embed_query(expanded_query)
            
            # Filter results by specific user_id
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="user_id",
                        match=MatchValue(value=user_id)
                    )
                ]
            )

            results = self.client.query_points(
                collection_name=QDRANT_COLLECTION,
                query=vector,
                limit=limit,
                query_filter=query_filter,
                score_threshold=QDRANT_SCORE_THRESHOLD
            ).points

            recent_indices = {t["turn_index"] for t in recent_turns}

            older_results = [
                r for r in results
                if r.payload.get("turn_index", -1) not in recent_indices
            ]

            older_results.sort(
                key=lambda r: r.score + (r.payload.get("turn_index", 0) * RECENCY_WEIGHT),
                reverse=True
            )

            if older_results:
                context_parts.append("\n=== Related Past Context (Long-Term Memory) ===")
                for r in older_results:
                    ts = r.payload.get("timestamp", "")[:10]
                    context_parts.append(f"[{ts}] {r.payload['full_text']}")

        except Exception as e:
            log(f"Memory Search Error: {e}")

        if not context_parts:
            return "No previous context."

        return "\n".join(context_parts)


# ===================== ASSISTANT CLASS =====================

class VoiceAssistant:
    def __init__(self, mode="voice"):
        """
        mode: "voice" or "text"
        In text mode, audio components (PyAudio, Whisper, Piper) are skipped.
        """
        self.mode = mode

        # Always initialize memory and LLM regardless of mode
        self.memory = QdrantMemoryManager()

        provider = os.getenv("LLM_PROVIDER", "google").lower()
        if provider == "groq":
            log("🤖 Initializing Brain (Groq - Llama 3.3 70B)...", True)
            self.llm = ChatGroq(
                groq_api_key=os.getenv("GROQ_API_KEY"),
                model_name="llama-3.3-70b-versatile",
                temperature=0.6
            )
        else:
            log("🤖 Initializing Brain (Google Gemini)...", True)
            self.llm = ChatGoogleGenerativeAI(
                google_api_key=GEMINI_API_KEY,
                model="gemini-2.0-flash",
                temperature=0.6
            )

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a caring, patient companion and voice assistant designed specifically for older adults. You have memory of past conversations and build a genuine relationship with the user over time. Your primary purpose is companionship, support, and making daily life easier.

CORE IDENTITY & PERSONALITY:
- You are a warm, friendly companion - like a caring neighbor or trusted friend
- You speak with genuine warmth but NEVER in a condescending or infantilizing way
- You are patient, respectful, and treat the user with dignity they deserve
- You remember you're supporting someone who deserves respect and genuine care

COMMUNICATION PRINCIPLES:

1. NATURAL LANGUAGE & CLARITY:
   - Use everyday, conversational language - avoid medical jargon and technical terms
   - Keep sentences short and clear (10-15 words when possible)
   - One main idea per sentence
   - Pause naturally between thoughts (use periods, not run-on sentences)
   - If you must use a technical term, explain it simply
   - Example: Say "your blood pressure medicine" not "antihypertensive medication"

2. RESPONSE LENGTH & PACING:
   - Keep responses very brief: exactly 2-3 short sentences max.
   - For complex topics, pick the most important piece of info and explain it simply.
   - Users appreciate brevity and time to process.
   - One main idea per response is best.

3. MEMORY & RELATIONSHIP BUILDING:
{context}

CRITICAL MEMORY USAGE:
- When past conversations are provided above, actively USE them
- Remember: names (theirs, family members, pets), health concerns, preferences, routines, important dates
- Build continuity: "How did your doctor's appointment go?" "Is your knee feeling better?"
- Reference shared history naturally: "Last week you mentioned..." "As you told me before..."
- NEVER make them repeat information they've already shared
- Remember their communication preferences (do they prefer formal or casual?)

4. COMPANIONSHIP & EMOTIONAL SUPPORT:
   - Many seniors experience loneliness - be a genuine friendly presence
   - Show interest in their lives, family, memories, daily experiences
   - Listen to stories without rushing them
   - Acknowledge feelings: "That sounds difficult" or "I'm so glad to hear that!"
   - Celebrate small wins: "That's wonderful!" "You're doing great!"
   - Remember important personal details and ask about them later
   - Be proactive: "Good morning! How are you feeling today?"

5. PATIENCE WITH REPETITION:
   - If they ask the same question again, answer warmly and completely
   - Never say "you already asked this" or sound impatient
   - They may not remember, or may need reassurance
   - Confusion or repetition is normal - handle with grace
   - If asked 3+ times in one session, gently offer: "Would you like me to help you save this information?"

6. HEALTH & MEDICATION AWARENESS:
   - Take health concerns seriously - never dismiss symptoms
   - For medical questions: provide helpful general information BUT always say "Please check with your doctor about this"
   - Remember medication names, schedules, and side effects they mention
   - Gently remind them of medications or appointments they've mentioned
   - Watch for signs of confusion or distress - be extra gentle
   - If they mention severe symptoms (chest pain, difficulty breathing, falls), ask if they need emergency help

7. COGNITIVE SUPPORT & ADAPTATION:
   - If they seem confused, rephrase more simply without mentioning confusion
   - Watch for signs: repeated questions, word-finding difficulty, unusual statements
   - Be extra patient with word-finding difficulties - give them time
   - If they use filler words (um, uh), that's normal - don't rush them
   - Adapt to their cognitive state - simpler responses if needed
   - Celebrate their memories and cognitive engagement

8. PRACTICAL DAILY SUPPORT:
   - Help with daily planning: weather, appointments, tasks, medications
   - Remind them of things they've asked you to remember
   - Break complex tasks into simple, clear steps
   - Offer to repeat: "Would you like me to go over that again?"
   - Be encouraging with technology: "You're doing great with this"
   - NEVER use words like "just" or "simply" - they can sound condescending

9. COMMUNICATION STYLE CUSTOMIZATION:
   - Pay attention to how they speak to you (formal vs. casual)
   - Mirror their preferred communication style
   - Some prefer "Mr./Mrs.", others prefer first names
   - Adjust your tone to match their comfort level
   - Remember their preference across conversations

10. EMERGENCY AWARENESS:
   - Watch for keywords: "can't breathe", "chest pain", "fell", "can't get up", "dizzy", "need help"
   - If detected, immediately ask: "This sounds urgent. Do you need me to call for help?"
   - Be ready to guide them to emergency services if needed
   - Take any mention of harm seriously

CONVERSATIONAL EXAMPLES:
❌ WRONG (Too clinical, rushed): "Your antihypertensive medication is scheduled for 0800 hours. Compliance is important for cardiovascular health."
✅ CORRECT (Warm, clear, supportive): "Good morning! Time for your blood pressure medicine. It's important to take it around 8 AM. Would you like me to remind you tomorrow too?"

❌ WRONG (Condescending): "As I already explained, you just need to press the red button."
✅ CORRECT (Patient, respectful): "No problem at all! To turn it on, press the round red button on top. Take your time, and let me know if you need any help."

❌ WRONG (Dismissive of emotion): "Loneliness is common in seniors. Consider social activities."
✅ CORRECT (Empathetic, supportive): "I'm sorry you're feeling lonely. That's really hard. Would you like to talk about it? We could also think together about people you might enjoy calling."

REMEMBER YOUR PURPOSE:
You're not just a voice assistant - you're a companion who provides emotional support, makes technology accessible, and treats users with dignity and patience.

Keep all responses conversational and appropriate for voice interaction."""),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}"),
        ])

        self.histories = {}

        def get_session_history(session_id: str):
            if session_id not in self.histories:
                self.histories[session_id] = InMemoryChatMessageHistory()
            return self.histories[session_id]

        self.chain = RunnableWithMessageHistory(
            self.prompt | self.llm,
            get_session_history,
            input_messages_key="input",
            history_messages_key="history",
        )

        # Only initialize audio components in voice mode
        if self.mode == "voice":
            check_piper_paths()
            self._init_audio()
        elif self.mode == "api":
            check_piper_paths()
            self._init_audio_api()

    def _init_audio(self):
        """Initialize VAD, PyAudio, and Whisper for voice mode."""
        log("🎧 Initializing VAD (Silero)...", True)
        self.vad_model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False,
            trust_repo=True
        )
        self.get_speech_timestamps, _, self.read_audio, _, _ = utils
        self.vad_model.eval()

        log("🎤 Initializing PyAudio...", True)
        self.pa = pyaudio.PyAudio()

        device = "cuda" if torch.cuda.is_available() else "cpu"
        log(f"🚀 Loading Whisper Medium on {device.upper()}...", True)
        self.whisper = whisper.load_model("medium", device=device)

    def _init_audio_api(self):
        """Initialize models for API mode (no PyAudio)."""
        device = "cuda" if torch.cuda.is_available() else "cpu"
        log(f"🚀 Loading Whisper Medium on {device.upper()}...", True)
        self.whisper = whisper.load_model("medium", device=device)

    def is_speech(self, audio_chunk):
        audio_int16 = np.frombuffer(audio_chunk, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        tensor = torch.from_numpy(audio_float32)
        speech_prob = self.vad_model(tensor, MIC_SAMPLE_RATE).item()
        return speech_prob > VAD_THRESHOLD

    def _clean_transcription(self, text):
        """Helper to clean up common Whisper hallucinations"""
        if not text:
            return None
        # Remove repeated "you" words (case insensitive), commas, and periods
        cleaned = re.sub(r'(?i)^(?:you[\s,\.]*)+$', '', text).strip()
        # Remove common Whisper hallucinations when audio is silent
        hallucinations = [
            "Thank you.", "Thank you", "you", "You.", "You", "you you you", "You you you",
            "Thanks for watching!", "Thanks for watching.", "Thank you for watching!", "Thank you for watching.",
            "Subscribe.", "Subscribe!", "Please subscribe."
        ]
        if cleaned in hallucinations or not cleaned:
            return None
        return cleaned

    def listen(self):
        """Listens using VAD. Records only when speech is detected."""
        stream = self.pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=MIC_SAMPLE_RATE,
            input=True,
            frames_per_buffer=MIC_CHUNK
        )

        log(f"\n🎤 Listening (VAD Enabled)...", True)

        raw_audio_buffer = []
        pre_speech_buffer = collections.deque(
            maxlen=int(PRE_RECORD_BUFFER * MIC_SAMPLE_RATE / MIC_CHUNK)
        )

        recording = False
        silence_start_time = None
        speech_start_time = None

        try:
            while True:
                chunk = stream.read(MIC_CHUNK, exception_on_overflow=False)

                if self.is_speech(chunk):
                    if not recording:
                        log("🗣️  Speech Detected...", True)
                        recording = True
                        speech_start_time = time.time()
                        raw_audio_buffer.extend(pre_speech_buffer)

                    silence_start_time = None
                    raw_audio_buffer.append(chunk)

                elif recording:
                    raw_audio_buffer.append(chunk)
                    if silence_start_time is None:
                        silence_start_time = time.time()

                    if time.time() - silence_start_time > SILENCE_LIMIT:
                        log("✅ End of Speech (Silence Limit).", True)
                        break

                    if time.time() - speech_start_time > SPEECH_LIMIT:
                        log("⚠️  Max Speech Limit Reached.", True)
                        break

                else:
                    pre_speech_buffer.append(chunk)

            stream.stop_stream()
            stream.close()

            if not raw_audio_buffer:
                return None

            total_duration = len(raw_audio_buffer) * MIC_CHUNK / MIC_SAMPLE_RATE
            if total_duration < MIN_SPEECH_DURATION:
                log(f"📉 Ignored short audio ({total_duration:.2f}s < {MIN_SPEECH_DURATION}s)", True)
                return None

            full_audio = b''.join(raw_audio_buffer)
            audio_np = np.frombuffer(full_audio, dtype=np.int16).astype(np.float32) / 32768.0

            log("⚙️  Transcribing...")
            result = self.whisper.transcribe(
                audio_np,
                language="en",
                fp16=torch.cuda.is_available()
            )

            text = self._clean_transcription(result['text'].strip())
            if text:
                log(f"🗣️  You: {text}", True)
                return text
            return None

        except Exception as e:
            log(f"❌ Listen Error: {e}", True)
            if stream.is_active():
                stream.stop_stream()
                stream.close()
            return None

    def generate_speech(self, text):
        if os.path.exists(OUTPUT_WAV):
            os.remove(OUTPUT_WAV)

        env = os.environ.copy()
        env['LD_LIBRARY_PATH'] = f"{PIPER_LIB_PATH}:{env.get('LD_LIBRARY_PATH', '')}"
        env['ESPEAK_DATA_PATH'] = f"{PIPER_LIB_PATH}/espeak-ng-data"

        cmd = [PIPER_EXE, "-m", PIPER_MODEL, "-f", OUTPUT_WAV]

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                env=env,
                stderr=subprocess.DEVNULL
            )
            proc.communicate(input=text.encode('utf-8'))

            if os.path.exists(OUTPUT_WAV) and os.path.getsize(OUTPUT_WAV) > 0:
                return True
            return False

        except Exception as e:
            log(f"❌ TTS Error: {e}", True)
            return False

    def speak_with_interruption(self, text):
        if not self.generate_speech(text):
            return

        wf = wave.open(OUTPUT_WAV, 'rb')

        out_stream = self.pa.open(
            format=self.pa.get_format_from_width(wf.getsampwidth()),
            channels=wf.getnchannels(),
            rate=wf.getframerate(),
            output=True,
            frames_per_buffer=PLAYBACK_CHUNK
        )

        in_stream = self.pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=MIC_SAMPLE_RATE,
            input=True,
            frames_per_buffer=MIC_CHUNK
        )

        log(f"🔊 Assistant: {text}", True)

        data = wf.readframes(PLAYBACK_CHUNK)
        interrupted = False

        while len(data) > 0:
            if interrupted:
                break

            out_stream.write(data)

            try:
                if in_stream.get_read_available() >= MIC_CHUNK:
                    mic_data = in_stream.read(MIC_CHUNK, exception_on_overflow=False)
                    audio_chunk = np.frombuffer(mic_data, dtype=np.int16)
                    rms = np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2))
                    current_loudness = rms / 32768.0

                    if current_loudness > INTERRUPT_SENSITIVITY:
                        log("🛑 Interrupted!", True)
                        interrupted = True
            except Exception:
                pass

            data = wf.readframes(PLAYBACK_CHUNK)

        out_stream.stop_stream()
        out_stream.close()
        in_stream.stop_stream()
        in_stream.close()
        wf.close()

    # ===================== SHARED LLM LOGIC =====================

    def _process_input(self, user_input, user_id="anonymous"):
        """
        Core logic shared by both voice and text modes.
        Takes a user text string, retrieves memory context, calls the LLM,
        saves the turn, and returns the response string.
        """
        try:
            context = self.memory.search(user_input, user_id=user_id)
            log(f"🤔 Thinking for {user_id}...")

            response_msg = self.chain.invoke(
                {"input": user_input, "context": context},
                config={"configurable": {"session_id": user_id}}
            )
            response_text = response_msg.content
            self.memory.add_turn(user_input, response_text, user_id=user_id)
            return response_text
        except Exception as e:
            log(f"❌ LLM Error: {e}", True)
            traceback.print_exc()
            raise e

    def process_api(self, audio_file_path: str = None, text_input: str = None, user_id: str = "anonymous", generate_audio: bool = True):
        """
        For API usage. Accepts either an audio_file_path or text_input.
        Transcribes, gets LLM response, generates TTS, and returns (user_text, response_text, wav_path).
        """
        user_text = text_input
        if audio_file_path:
            log(f"⚙️  Transcribing API Audio: {audio_file_path}")
            result = self.whisper.transcribe(
                audio_file_path,
                language="en",
                fp16=torch.cuda.is_available()
            )
            user_text = self._clean_transcription(result['text'].strip())
            
        if not user_text:
            return "", "", ""
            
        response_text = self._process_input(user_text, user_id=user_id)
        
        # Generate speech
        wav_path = ""
        if generate_audio:
            success = self.generate_speech(response_text)
            wav_path = OUTPUT_WAV if success else ""
        
        return user_text, response_text, wav_path

    # ===================== RUN MODES =====================

    def run_voice(self):
        """Original voice interaction loop."""
        log("=" * 50, True)
        log("  MODE: VOICE  (Whisper + Piper TTS)", True)
        log("=" * 50, True)

        self.speak_with_interruption("Voice mode active. I am listening.")

        while True:
            user_input = self.listen()

            if not user_input:
                continue

            exit_phrases = ["exit", "stop", "quit", "goodbye", "good bye", "bye bye", "talk to you later"]
            if any(phrase in user_input.lower() for phrase in exit_phrases):
                self.speak_with_interruption("Goodbye! I'll be here if you need me.")
                log("⌛ Post-goodbye pause (3s)...")
                time.sleep(3)
                break

            try:
                response_text = self._process_input(user_input)
                self.speak_with_interruption(response_text)
            except Exception as e:
                log(f"Error: {e}", True)
                traceback.print_exc()
                self.speak_with_interruption("I encountered an error.")

    def run_text(self):
        """
        Text chat loop. No audio involved.
        Type your message and press Enter. Type 'exit' to quit.
        Responses are printed to the terminal with colour formatting.
        """
        log("=" * 50, True)
        log("  MODE: TEXT CHAT", True)
        log("  Type your message and press Enter.", True)
        log("  Type 'exit', 'quit', or 'stop' to end.", True)
        log("=" * 50, True)
        print()  # blank line for breathing room

        while True:
            try:
                # Coloured prompt so it's easy to spot where to type
                user_input = input("\033[93mYou: \033[0m").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 Goodbye.")
                break

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "stop"]:
                print("\033[96mAssistant: Goodbye!\033[0m")
                break

            try:
                response_text = self._process_input(user_input)
                # Print response with a distinct colour (cyan)
                print(f"\033[96mAssistant: {response_text}\033[0m\n")
            except Exception as e:
                log(f"Error: {e}", True)
                traceback.print_exc()
                print("\033[91mAssistant: I encountered an error.\033[0m\n")

    def run(self):
        """Entry point — lets user pick voice or text mode at startup."""
        if self.mode == "voice":
            self.run_voice()
        else:
            self.run_text()


# ===================== MAIN =====================

def pick_mode():
    """
    Prompts the user to choose between voice and text mode.
    Falls back to text if the choice is unrecognised.
    """
    print("\n\033[96m" + "=" * 50)
    print("  ASSISTANT STARTUP")
    print("=" * 50 + "\033[0m")
    print("\033[93mSelect mode:")
    print("  [1] Voice  (Microphone + Speaker)")
    print("  [2] Text   (Keyboard + Terminal)\033[0m")

    try:
        choice = input("\nEnter 1 or 2: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nDefaulting to text mode.")
        return "text"

    if choice == "1":
        return "voice"
    elif choice == "2":
        return "text"
    else:
        print("Unrecognized choice — defaulting to text mode.")
        return "text"

def pick_llm():
    """
    Prompts the user to choose between Google Gemini and Groq Llama.
    """
    print("\n\033[93mSelect LLM Provider:")
    print("  [1] Google Gemini")
    print("  [2] Groq (Llama 3.3 70B)\033[0m")

    try:
        choice = input("\nEnter 1 or 2 (Press Enter for .env default): ").strip()
    except (EOFError, KeyboardInterrupt):
        return os.getenv("LLM_PROVIDER", "google")

    if choice == "1":
        return "google"
    elif choice == "2":
        return "groq"
    else:
        return os.getenv("LLM_PROVIDER", "google")


if __name__ == "__main__":
    try:
        mode = pick_mode()
        # For terminal mode, we can pick the LLM too
        llm_choice = pick_llm()
        os.environ["LLM_PROVIDER"] = llm_choice
        
        bot = VoiceAssistant(mode=mode)
        bot.run()
    except KeyboardInterrupt:
        print("\n👋 Stopped by user.")
    except Exception as e:
        print(f"\n❌ Critical Error: {e}")
        traceback.print_exc()