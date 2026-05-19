"""
Fast Vision Engine using face_recognition library (10x faster than DeepFace)
Falls back gracefully if dependencies are missing (demo mode)
"""
import os
import json
import time
import numpy as np

# Graceful imports for optional dependencies
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    print("[WARN] OpenCV not installed. Vision features will use demo mode.")
    CV2_AVAILABLE = False

try:
    import face_recognition
    FACE_REC_AVAILABLE = True
except ImportError:
    print("[WARN] face_recognition not installed. Using mock recognition for demo.")
    FACE_REC_AVAILABLE = False

try:
    from software.faiss_engine import FaissBiometricEngine
    DEEPFACE_FALLBACK_AVAILABLE = True
except Exception as e:
    print(f"[WARN] DeepFace/FAISS fallback unavailable: {e}")
    DEEPFACE_FALLBACK_AVAILABLE = False


class SpooferEngine:
    """Liveness detection to prevent photo spoofing"""
    def check_liveness(self, frame):
        if not CV2_AVAILABLE:
            return True, "Liveness check skipped (demo mode)"
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur_val = cv2.Laplacian(gray, cv2.CV_64F).var()
        if blur_val < 35: 
            return False, "Spoof Detected (Unnatural Surface Texture)"
        return True, "Live Organism Detected"


class VisionEngine:
    """Fast face recognition using face_recognition library"""
    
    def __init__(self, model_name="hog"):
        self.model_name = model_name  # "hog" for speed, "cnn" for accuracy
        self.spoofer = SpooferEngine()
        self.known_encodings = []
        self.known_names = []
        self.preview_enabled = CV2_AVAILABLE
        self.deepface_fallback = None
        self._last_identity_signature = None
        self.face_cascade = None
        self._face_presence_prev = False
        
        if CV2_AVAILABLE:
            self.qr_detector = cv2.QRCodeDetector()
            try:
                cascade_path = os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')
                self.face_cascade = cv2.CascadeClassifier(cascade_path)
                if self.face_cascade.empty():
                    self.face_cascade = None
            except Exception:
                self.face_cascade = None
        else:
            self.qr_detector = None

        if DEEPFACE_FALLBACK_AVAILABLE:
            try:
                self.deepface_fallback = FaissBiometricEngine(model_name="Facenet")
            except Exception as e:
                print(f"[WARN] Failed to initialize DeepFace/FAISS fallback: {e}")
                self.deepface_fallback = None

    def extract_vector(self, img_path):
        """Extract face encoding from image file (for enrollment)"""
        if not FACE_REC_AVAILABLE:
            # Return mock encoding for demo mode
            return np.random.rand(128).tolist()
        
        try:
            image = face_recognition.load_image_file(img_path)
            encodings = face_recognition.face_encodings(image, model=self.model_name)
            if len(encodings) > 0:
                return encodings[0].tolist()  # Return as list for JSON serialization
        except Exception as e:
            print(f"Error extracting face from {img_path}: {e}")
        return None

    def extract_vector_and_bbox(self, img_path_or_frame):
        """Extract face encoding and bounding box"""
        if not FACE_REC_AVAILABLE:
            return np.random.rand(128).tolist(), {'x': 100, 'y': 100, 'w': 200, 'h': 200}
        
        try:
            # Handle both file paths and numpy arrays
            if isinstance(img_path_or_frame, str):
                image = face_recognition.load_image_file(img_path_or_frame)
            else:
                image = img_path_or_frame
            
            face_locations = face_recognition.face_locations(image, model=self.model_name)
            encodings = face_recognition.face_encodings(image, face_locations, model=self.model_name)
            
            if len(encodings) > 0 and len(face_locations) > 0:
                # Convert location format: (top, right, bottom, left) to bbox dict
                top, right, bottom, left = face_locations[0]
                bbox = {
                    'x': left,
                    'y': top,
                    'w': right - left,
                    'h': bottom - top
                }
                return encodings[0].tolist(), bbox
        except Exception as e:
            print(f"Error processing image: {e}")
        return None, None

    def build_known_faces(self, users_list):
        """Build index of known faces from user database"""
        self.known_encodings = []
        self.known_names = []

        if FACE_REC_AVAILABLE:
            for user in users_list:
                if user.face_vector and len(user.face_vector) > 5:
                    try:
                        # Parse JSON-stored encoding
                        encoding = json.loads(user.face_vector) if isinstance(user.face_vector, str) else user.face_vector
                        self.known_encodings.append(np.array(encoding))
                        self.known_names.append(user)
                    except Exception as e:
                        print(f"Error loading vector for User ID {user.user_id}: {e}")
            loaded = len(self.known_encodings) > 0
            signature = tuple(u.user_id for u in self.known_names)
            if signature != self._last_identity_signature:
                self._last_identity_signature = signature
                names = [u.name for u in self.known_names]
                print(f"[Vision] Loaded {len(names)} identities for matching: {names if names else '[]'}")
            return loaded

        # Fallback path when face_recognition is unavailable: use DeepFace + FAISS index on enrolled images.
        if self.deepface_fallback is not None:
            indexed_users = [
                user for user in users_list
                if user.Face_encoding and os.path.exists(user.Face_encoding)
            ]
            signature = tuple(u.user_id for u in indexed_users)
            missing_users = [
                user.name for user in users_list
                if not user.Face_encoding or not os.path.exists(user.Face_encoding)
            ]
            if not indexed_users:
                if missing_users:
                    print(f"[Vision] No indexable face images found. Re-enroll photos for: {', '.join(missing_users)}")
                return False
            if (
                signature == self._last_identity_signature
                and getattr(self.deepface_fallback.index, 'ntotal', 0) > 0
            ):
                return True
            try:
                loaded = self.deepface_fallback.build_index(indexed_users)
                if signature != self._last_identity_signature:
                    self._last_identity_signature = signature
                    loaded_names = [u.name for u in indexed_users]
                    print(f"[Vision] Loaded {len(loaded_names)} identity images for matching: {loaded_names}")
                    if missing_users:
                        print(f"[Vision] Missing/invalid face image files for: {', '.join(missing_users)}")
                return loaded
            except Exception as e:
                print(f"[Vision] DeepFace/FAISS fallback index error: {e}")
                return False

        return False

    def _close_camera_session(self, cap):
        if cap is not None:
            cap.release()
        if CV2_AVAILABLE:
            try:
                cv2.destroyAllWindows()
            except cv2.error:
                pass

    def _safe_show_frame(self, frame):
        if not self.preview_enabled:
            return False
        try:
            cv2.imshow("SmartLift Security Scanner", frame)
            return True
        except cv2.error as err:
            self.preview_enabled = False
            print("[Vision] GUI preview unavailable in current OpenCV build. Switching to headless mode.")
            print(f"[Vision] Preview error: {err}")
            return False

    def _authenticate_face(self, frame, active_tenant_users, show_feedback=False):
        print("\n> [Vision] Initiating face scan...")

        # Liveness detection
        is_live, msg = self.spoofer.check_liveness(frame)
        if not is_live:
            print(f"> [SECURITY ALERT] {msg}")
            return "ERROR", None, "Spoof Attack Blocked"

        if not FACE_REC_AVAILABLE:
            if self.deepface_fallback is not None:
                import tempfile
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                        if not cv2.imwrite(tmp.name, frame):
                            return "ERROR", None, "Frame capture failed"
                        tmp_path = tmp.name

                    user, msg = self.deepface_fallback.verify_subject(tmp_path)
                    if user:
                        print(f"> [ACCESS GRANTED] Identity: {user.name.upper()}")
                        return "FACE", user.name, "Verified"
                    if "No Face Detected" in str(msg):
                        return None
                    print(f"> [ACCESS DENIED] {msg}")
                    return "ERROR", None, msg
                except Exception as e:
                    print(f"[Vision] DeepFace fallback verify error: {e}")
                    return "ERROR", None, "DeepFace fallback failed"
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        os.remove(tmp_path)

            print("> [ERROR] No face-recognition backend available on this machine.")
            return "ERROR", None, "Face engine unavailable"

        live_encoding, bbox = self.extract_vector_and_bbox(frame)
        if live_encoding is None or len(self.known_encodings) == 0:
            print("> [WARN] No face detected clearly. Please face the camera.")
            return None

        matches = face_recognition.compare_faces(self.known_encodings, np.array(live_encoding), tolerance=0.6)
        face_distances = face_recognition.face_distance(self.known_encodings, np.array(live_encoding))
        if len(face_distances) == 0:
            print("> [ACCESS DENIED] Face not recognized")
            return "ERROR", None, "Face Mismatch"

        best_match_index = np.argmin(face_distances)
        if matches[best_match_index]:
            matched_user = self.known_names[best_match_index]
            confidence = (1 - face_distances[best_match_index]) * 100
            print(f"> [ACCESS GRANTED] Identity: {matched_user.name.upper()}")
            print(f"  └─ Confidence: {confidence:.1f}%\n")

            if show_feedback and bbox and self.preview_enabled:
                x, y, w, h = bbox['x'], bbox['y'], bbox['w'], bbox['h']
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                cv2.putText(frame, f"{matched_user.name}", (x, y-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                if self._safe_show_frame(frame):
                    cv2.waitKey(1500)

            return "FACE", matched_user.name, "Verified"

        print("> [ACCESS DENIED] Face not recognized")
        if show_feedback and bbox and self.preview_enabled:
            x, y, w, h = bbox['x'], bbox['y'], bbox['w'], bbox['h']
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 0, 255), 2)
            cv2.putText(frame, "DENIED", (x, y-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            if self._safe_show_frame(frame):
                cv2.waitKey(1500)
        return "ERROR", None, "Face Mismatch"

    def _has_face_candidate(self, frame):
        if not CV2_AVAILABLE or self.face_cascade is None:
            return True
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=4,
                minSize=(70, 70)
            )
            has_face = len(faces) > 0
            if has_face != self._face_presence_prev:
                self._face_presence_prev = has_face
                if has_face:
                    print("[Vision] Subject detected in frame. Starting authentication.")
                else:
                    print("[Vision] Frame is clear. Waiting for subject.")
            return has_face
        except Exception:
            return True

    def scan_for_user(self, active_tenant_users):
        """
        Multi-modal scanner: Supports QR codes and face recognition
        Returns: (auth_type, identifier, status)
        """
        if not self.build_known_faces(active_tenant_users):
            print("[Vision] CRITICAL: No active face encodings for this Tenant.")
            return "ERROR", "NO_DB", "No face data configured."

        if not CV2_AVAILABLE:
            print("[Vision] OpenCV not available. Camera scanner cannot start.")
            return "ERROR", None, "OpenCV camera backend unavailable"

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("[Vision] WARNING: Camera not available. Using demo mode.")
            return "ERROR", None, "No camera available"
        
        print("\n" + "="*50)
        print("[Vision MULTI-MODAL SCANNER]")
        if self.preview_enabled:
            print("-> Action 1: Show QR Code (Seamless Scan)")
            print("-> Action 2: Step into frame to auto-authenticate (press 's' to force scan)")
            print("-> Action 3: Press 'q' (Power Down)")
        else:
            print("-> Headless mode: window preview unavailable.")
            print("-> QR scan continues in background.")
            print("-> Face authentication auto-attempts every 3 seconds.")
            print("-> Use Ctrl+C in terminal to stop edge node.")
        print("="*50 + "\n")

        last_auth_attempt = 0.0
        while True:
            ret, frame = cap.read()
            if not ret:
                continue
            
            # QR Code Detection (seamless background scanning)
            if self.qr_detector:
                try:
                    data, bbox, _ = self.qr_detector.detectAndDecode(frame)
                    if data:
                        print(f"\n> [QR DETECTED] Token: {data}")
                        self._close_camera_session(cap)
                        return "QR", data, "Token Discovered"
                except Exception:
                    pass  # Suppress OpenCV errors

            if self.preview_enabled:
                h, w = frame.shape[:2]
                cv2.rectangle(frame, (w//2 - 100, h//2 - 120), (w//2 + 100, h//2 + 120), (56, 189, 248), 2)
                cv2.putText(frame, "SMART LIFT NODE", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (56, 189, 248), 2)
                cv2.putText(frame, "[QR/FACE ONLINE]", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (16, 185, 129), 1)
                if not self._safe_show_frame(frame):
                    print("[Vision] Headless mode active: no GUI preview. Continuing scanner loop.")
                    continue

                key = cv2.waitKey(1) & 0xFF
                now = time.time()
                if key == ord('s'):
                    last_auth_attempt = now
                    result = self._authenticate_face(frame, active_tenant_users, show_feedback=True)
                    if result is not None:
                        self._close_camera_session(cap)
                        return result
                elif key == ord('q'):
                    print("System shutting down...")
                    break
                elif now - last_auth_attempt >= 3.0:
                    last_auth_attempt = now
                    if not self._has_face_candidate(frame):
                        continue
                    result = self._authenticate_face(frame, active_tenant_users, show_feedback=True)
                    if result is not None:
                        self._close_camera_session(cap)
                        return result
            else:
                now = time.time()
                if now - last_auth_attempt >= 3.0:
                    last_auth_attempt = now
                    if not self._has_face_candidate(frame):
                        continue
                    result = self._authenticate_face(frame, active_tenant_users, show_feedback=False)
                    if result is not None:
                        self._close_camera_session(cap)
                        return result

        self._close_camera_session(cap)
        return "EXIT", None, "Cancelled"
