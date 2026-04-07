try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    print("[WARN] pyttsx3 not installed. Audio output disabled.")
    TTS_AVAILABLE = False

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    print("[WARN] SpeechRecognition not installed. Voice input disabled.")
    SR_AVAILABLE = False

class AudioEngine:
    def __init__(self):
        self.demo_mode = not (TTS_AVAILABLE and SR_AVAILABLE)
        
        if TTS_AVAILABLE:
            try:
                self.tts = pyttsx3.init()
                self.tts.setProperty('rate', 160)
            except Exception as e:
                print(f"[WARN] TTS initialization failed: {e}. Using print-only mode.")
                self.demo_mode = True
                self.tts = None
        else:
            self.tts = None
            
        if SR_AVAILABLE:
            self.recognizer = sr.Recognizer()
        else:
            self.recognizer = None

    def speak(self, text):
        print(f"[Assistant]: {text}")
        if self.tts and not self.demo_mode:
            try:
                self.tts.say(text)
                self.tts.runAndWait()
            except Exception as e:
                print(f"[WARN] TTS error: {e}")

    def listen_for_floor(self):
        if not SR_AVAILABLE or not self.recognizer:
            print("\n[DEMO MODE] Voice recognition not available.")
            print("Enter floor number manually (or 'q' to quit): ", end="")
            try:
                response = input().strip().lower()
                return response if response else ""
            except:
                return ""
        
        try:
            with sr.Microphone() as source:
                print("\n[Microphone] Listening for your command...")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                try:
                    audio = self.recognizer.listen(source, timeout=6, phrase_time_limit=5)
                    text = self.recognizer.recognize_google(audio).lower()
                    print(f"[User Said]: '{text}'")
                    return text
                except sr.UnknownValueError:
                    self.speak("Sorry, I didn't quite catch that. Could you repeat?")
                    return ""
                except sr.WaitTimeoutError:
                    self.speak("I didn't hear anything. Are you still there?")
                    return ""
                except Exception as e:
                    print(f"[Audio Error]: {e}")
                    return ""
        except Exception as e:
            print(f"[WARN] Microphone not available: {e}. Using text input.")
            print("Enter floor command: ", end="")
            return input().strip().lower()

