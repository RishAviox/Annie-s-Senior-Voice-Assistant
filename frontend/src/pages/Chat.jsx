import { useState, useRef, useEffect } from 'react'
import hark from 'hark'
import './Chat.css'

const PLACEHOLDER_RESPONSE = "This is a demo response. Connect your backend API to get real replies from Conversational AI."

export default function Chat({ user }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [sessionId] = useState(() => crypto.randomUUID()) // Unique ID sequence for guest sessions

  // Recording states
  const [isRecording, setIsRecording] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false) // VAD state
  const [isContinuousVoice, setIsContinuousVoice] = useState(false)

  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  const mediaRecorderRef = useRef(null)
  const audioChunksRef = useRef([])
  const streamRef = useRef(null)
  const speechEventsRef = useRef(null)
  const currentAudioRef = useRef(null)
  const isContinuousVoiceRef = useRef(false)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (speechEventsRef.current) speechEventsRef.current.stop()
      if (streamRef.current) streamRef.current.getTracks().forEach(track => track.stop())
    }
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    const text = input.trim()
    if (!text || isLoading) return

    const userMessage = { id: crypto.randomUUID(), role: 'user', content: text }
    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setIsLoading(true)

    try {
      const response = await fetch('http://localhost:8000/chat/text', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ text, user_id: user ? user.email : sessionId }),
      })

      if (!response.ok) {
        throw new Error('Network response was not ok')
      }

      const data = await response.json()

      const assistantMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: data.response_text || "I didn't catch that. Could you try again?",
        audio_url: data.audio_url
      }
      setMessages((prev) => [...prev, assistantMessage])

      // Check for exit phrases to stop continuous mode if active
      const exitPhrases = ["exit", "stop", "quit", "goodbye", "good bye", "bye bye", "talk to you later"]
      if (exitPhrases.some(phrase => text.toLowerCase().includes(phrase))) {
        setIsContinuousVoice(false)
        isContinuousVoiceRef.current = false
      }

      // Auto-play response audio if available
      if (data.audio_url) {
        const audio = new Audio(`http://localhost:8000${data.audio_url}?t=${Date.now()}`);
        audio.play().catch(e => console.error("Could not play audio:", e));
      }

    } catch (error) {
      console.error('Error fetching chat response:', error)
      const errorMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: "Sorry, I had trouble connecting to the backend. Is it running?",
      }
      setMessages((prev) => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
      inputRef.current?.focus()
    }
  }

  const toggleVoiceMode = () => {
    if (isContinuousVoice) {
      setIsContinuousVoice(false)
      isContinuousVoiceRef.current = false
      stopListening()
      if (currentAudioRef.current) {
        currentAudioRef.current.pause()
        currentAudioRef.current.currentTime = 0
      }
    } else {
      setIsContinuousVoice(true)
      isContinuousVoiceRef.current = true
      startListening()
    }
  }

  const startListening = async () => {
    if (isRecording || isLoading) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true }
      })
      streamRef.current = stream

      const mediaRecorder = new MediaRecorder(stream)
      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
        // Submit the audio after it's fully packaged
        await handleAudioSubmit(audioBlob)
      }

      mediaRecorder.start()
      setIsRecording(true)

      // Initialize Voice Activity Detection (VAD) with Hark
      const speechEvents = hark(stream, {
        threshold: -50, // Decibel threshold for speech (adjust if needed)
        play: false
      })
      speechEventsRef.current = speechEvents

      let silenceTimeout = null;

      speechEvents.on('speaking', () => {
        setIsSpeaking(true)
        if (silenceTimeout) {
          clearTimeout(silenceTimeout)
          silenceTimeout = null
        }

        // Voice Interruption: Stop AI if it's talking
        if (currentAudioRef.current && !currentAudioRef.current.paused) {
          currentAudioRef.current.pause()
          console.log("🗣️ User interrupted AI!")
        }
      })

      speechEvents.on('stopped_speaking', () => {
        setIsSpeaking(false)
        // Auto-stop recording after 3 seconds of silence (increased from 1.5s to prevent cutoffs)
        silenceTimeout = setTimeout(() => {
          stopListening()
        }, 2500)
      })

    } catch (error) {
      console.error('Error accessing microphone:', error)
      alert("Could not access microphone.")
    }
  }

  const stopListening = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop() // Triggers mediaRecorder.onstop

      if (speechEventsRef.current) {
        speechEventsRef.current.stop()
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop())
      }

      setIsRecording(false)
      setIsSpeaking(false)
    }
  }

  const handleAudioSubmit = async (audioBlob) => {
    // Show a temporary user message
    const userMessageId = crypto.randomUUID()
    const userMessage = { id: userMessageId, role: 'user', content: "🎙️ (Processing Audio...)" }
    setMessages((prev) => [...prev, userMessage])
    setIsLoading(true)

    const formData = new FormData()
    formData.append("file", audioBlob, "recording.webm")
    formData.append("user_id", user ? user.email : sessionId)

    try {
      const response = await fetch('http://localhost:8000/chat/audio', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        throw new Error('Network response was not ok')
      }

      const data = await response.json()

      // Update the user message to show the transcribed text
      setMessages((prev) =>
        prev.map(msg => msg.id === userMessageId ? { ...msg, content: `🎙️ ${data.user_text || '(Audio message)'}` } : msg)
      )

      if (data.user_text) {
        const assistantMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: data.response_text || "I didn't catch that. Could you try again?",
          audio_url: data.audio_url
        }
        setMessages((prev) => [...prev, assistantMessage])

        // Check for exit phrases to stop continuous mode
        const exitPhrases = ["exit", "stop", "quit", "goodbye", "good bye", "bye bye", "talk to you later"]
        if (exitPhrases.some(phrase => data.user_text.toLowerCase().includes(phrase))) {
          setIsContinuousVoice(false)
          isContinuousVoiceRef.current = false
        }

        if (data.audio_url) {
          const audio = new Audio(`http://localhost:8000${data.audio_url}?t=${Date.now()}`);
          currentAudioRef.current = audio;
          audio.play().catch(e => console.error("Could not play audio:", e));
        }
      }

    } catch (error) {
      console.error('Error fetching chat audio response:', error)
      const errorMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: "Sorry, I had trouble processing your voice message.",
      }
      setMessages((prev) => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
      inputRef.current?.focus()

      // Auto-restart listening if Continuous Voice Mode wasn't turned off
      if (isContinuousVoiceRef.current) {
        setTimeout(() => {
          if (isContinuousVoiceRef.current) startListening()
        }, 100)
      }
    }
  }

  const isEmpty = messages.length === 0

  return (
    <div className="chat-page">
      <div className="chat-messages">
        {isEmpty && (
          <div className="chat-welcome">
            <h2 className="chat-welcome-title">Conversational AI</h2>
            <p className="chat-welcome-subtitle">Start a conversation—ask anything.</p>
            <div className="chat-suggestions">
              <button
                type="button"
                className="chat-suggestion"
                onClick={() => setInput('What can you help me with?')}
              >
                What can you help me with?
              </button>
              <button
                type="button"
                className="chat-suggestion"
                onClick={() => setInput('Summarize this for me')}
              >
                Summarize this for me
              </button>
              <button
                type="button"
                className="chat-suggestion"
                onClick={() => setInput('Explain in simple terms')}
              >
                Explain in simple terms
              </button>
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`chat-message chat-message--${msg.role}`}>
            <div className="chat-message-avatar">
              {msg.role === 'user' ? (
                <span className="chat-avatar-user">U</span>
              ) : (
                <span className="chat-avatar-assistant">SV</span>
              )}
            </div>
            <div className="chat-message-content">
              <div className="chat-message-text">{msg.content}</div>
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="chat-message chat-message--assistant">
            <div className="chat-message-avatar">
              <span className="chat-avatar-assistant">SV</span>
            </div>
            <div className="chat-message-content">
              <div className="chat-typing">
                <span></span><span></span><span></span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      <div className="chat-input-wrap">
        <form className="chat-form" onSubmit={handleSubmit}>
          <textarea
            ref={inputRef}
            className="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSubmit(e)
              }
            }}
            placeholder="Message Conversational AI…"
            rows={1}
            disabled={isLoading || isRecording}
          />
          {input.trim() ? (
            <button
              type="submit"
              className="chat-send"
              disabled={isLoading}
              aria-label="Send"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 2L11 13" />
                <path d="M22 2L15 22L11 13L2 9L22 2Z" />
              </svg>
            </button>
          ) : (
            <button
              type="button"
              className={`chat-send chat-mic ${isContinuousVoice ? 'recording' : ''} ${isSpeaking ? 'speaking' : ''}`}
              onClick={toggleVoiceMode}
              disabled={isLoading && !isContinuousVoice}
              aria-label={isContinuousVoice ? "Stop Continuous Mode" : "Start Continuous Mode"}
            >
              {isContinuousVoice ? (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                </svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" />
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                  <line x1="12" y1="19" x2="12" y2="23" />
                  <line x1="8" y1="23" x2="16" y2="23" />
                </svg>
              )}
            </button>
          )}
        </form>
        {isContinuousVoice && (
          <p className="chat-recording-indicator">
            {isSpeaking ? "🗣️ Listening..." : isRecording ? "🎙️ Waiting for speech... (Auto-sends when you stop)" : "⏳ Processing AI response..."}
          </p>
        )}
        <p className="chat-disclaimer">Conversational AI can make mistakes. Check important info.</p>
      </div>
    </div>
  )
}

