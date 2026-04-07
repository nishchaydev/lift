"""
Fast Vision Engine using face_recognition library (10x faster than DeepFace)
Falls back gracefully if dependencies are missing (demo mode)
"""
import os
import json
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
        
        if CV2_AVAILABLE:
            self.qr_detector = cv2.QRCodeDetector()
        else:
            self.qr_detector = None

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
        
        for user in users_list:
            if user.face_vector and len(user.face_vector) > 5:
                try:
                    # Parse JSON-stored encoding
                    encoding = json.loads(user.face_vector) if isinstance(user.face_vector, str) else user.face_vector
                    self.known_encodings.append(np.array(encoding))
                    self.known_names.append(user)
                except Exception as e:
                    print(f"Error loading vector for User ID {user.user_id}: {e}")
        
        return len(self.known_encodings) > 0

    def scan_for_user(self, active_tenant_users):
        """
        Multi-modal scanner: Supports QR codes and face recognition
        Returns: (auth_type, identifier, status)
        """
        if not self.build_known_faces(active_tenant_users):
            print("[Vision] CRITICAL: No active face encodings for this Tenant.")
            return "ERROR", "NO_DB", "No face data configured."

        if not CV2_AVAILABLE:
            print("[Vision] Running in DEMO MODE - OpenCV not available")
            print("Simulating face recognition...")
            # Return first user for demo purposes
            if len(active_tenant_users) > 0:
                return "FACE", active_tenant_users[0].name, "Demo Mode"
            return "ERROR", None, "No users in database"

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("[Vision] WARNING: Camera not available. Using demo mode.")
            if len(active_tenant_users) > 0:
                return "FACE", active_tenant_users[0].name, "Demo Mode (No Camera)"
            return "ERROR", None, "No camera available"
        
        print("\n" + "="*50)
        print("[Vision MULTI-MODAL SCANNER]")
        print("-> Action 1: Show QR Code (Seamless Scan)")
        print("-> Action 2: Press 's' (Face Authentication)")
        print("-> Action 3: Press 'q' (Power Down)")
        print("="*50 + "\n")
        
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
                        cap.release()
                        cv2.destroyAllWindows()
                        return "QR", data, "Token Discovered"
                except Exception:
                    pass  # Suppress OpenCV errors
            
            # Display video feed with UI overlay
            h, w = frame.shape[:2]
            cv2.rectangle(frame, (w//2 - 100, h//2 - 120), (w//2 + 100, h//2 + 120), (56, 189, 248), 2)
            cv2.putText(frame, "SMART LIFT NODE", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (56, 189, 248), 2)
            cv2.putText(frame, "[QR/FACE ONLINE]", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (16, 185, 129), 1)
            cv2.imshow("SmartLift Security Scanner", frame)
            
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('s'):
                print("\n> [Vision] Initiating face scan...")
                
                # Liveness detection
                is_live, msg = self.spoofer.check_liveness(frame)
                if not is_live:
                    print(f"> [SECURITY ALERT] {msg}")
                    cap.release()
                    cv2.destroyAllWindows()
                    return "ERROR", None, "Spoof Attack Blocked"
                
                if not FACE_REC_AVAILABLE:
                    print("> [DEMO MODE] Face recognition library not available")
                    cap.release()
                    cv2.destroyAllWindows()
                    if len(active_tenant_users) > 0:
                        return "FACE", active_tenant_users[0].name, "Demo Mode"
                    return "ERROR", None, "No face recognition available"
                
                # Fast face recognition
                live_encoding, bbox = self.extract_vector_and_bbox(frame)
                
                if live_encoding is not None and len(self.known_encodings) > 0:
                    # Compare against known faces
                    matches = face_recognition.compare_faces(self.known_encodings, np.array(live_encoding), tolerance=0.6)
                    face_distances = face_recognition.face_distance(self.known_encodings, np.array(live_encoding))
                    
                    if len(face_distances) > 0:
                        best_match_index = np.argmin(face_distances)
                        
                        if matches[best_match_index]:
                            matched_user = self.known_names[best_match_index]
                            confidence = (1 - face_distances[best_match_index]) * 100
                            
                            print(f"> [ACCESS GRANTED] Identity: {matched_user.name.upper()}")
                            print(f"  └─ Confidence: {confidence:.1f}%\n")
                            
                            # Draw success box
                            if bbox:
                                x, y, w, h = bbox['x'], bbox['y'], bbox['w'], bbox['h']
                                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                                cv2.putText(frame, f"{matched_user.name}", (x, y-10), 
                                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
                                cv2.imshow("SmartLift Security Scanner", frame)
                                cv2.waitKey(1500)
                            
                            cap.release()
                            cv2.destroyAllWindows()
                            return "FACE", matched_user.name, "Verified"
                    
                    # No match found
                    print("> [ACCESS DENIED] Face not recognized")
                    if bbox:
                        x, y, w, h = bbox['x'], bbox['y'], bbox['w'], bbox['h']
                        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 0, 255), 2)
                        cv2.putText(frame, "DENIED", (x, y-10), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)
                        cv2.imshow("SmartLift Security Scanner", frame)
                        cv2.waitKey(1500)
                    
                    cap.release()
                    cv2.destroyAllWindows()
                    return "ERROR", None, "Face Mismatch"
                else:
                    print("> [WARN] No face detected clearly. Please face the camera.")
            
            elif key == ord('q'):
                print("System shutting down...")
                break
        
        cap.release()
        cv2.destroyAllWindows()
        return "EXIT", None, "Cancelled"
