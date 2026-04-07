# 🔧 SmartLift Module Structure & Raspberry Pi Deployment Guide

## 📁 Project File Structure

```
SmartLift/
├── 📱 WEB APPLICATION (Flask Server)
│   ├── app.py                          # Main Flask web server (Admin Portal)
│   ├── models.py                       # Database models (Users, Tenants, Logs)
│   ├── database.py                     # Legacy DB manager (not used)
│   │
├── 🤖 AI/HARDWARE MODULES (For Edge Nodes)
│   ├── camera_face_recognition.py      # Fast face recognition (NEW - Use This!)
│   ├── camera_face_recognition_old.py  # Old DeepFace version (Backup)
│   ├── voice_control_module.py         # Voice commands & TTS
│   ├── lift_hardware_controller.py     # Arduino/Relay control via Serial
│   │
├── 🎯 EDGE NODE CONTROLLER
│   ├── main.py                         # Edge node OS (runs on Raspberry Pi)
│   │
├── 🌱 DEMO & SETUP
│   ├── seed_demo_data.py               # Generate demo data for testing
│   ├── requirements.txt                # Python dependencies
│   │
├── 📚 DOCUMENTATION
│   ├── README.md                       # Full project documentation
│   ├── QUICK_START_GUIDE.md           # Competition demo guide
│   ├── SETUP_PROGRESS.md              # Setup progress report
│   ├── .github/
│   │   └── copilot-instructions.md    # Development guidelines
│   │
├── 🎨 FRONTEND
│   ├── templates/                      # HTML templates
│   │   ├── base.html                  # Base template (Chart.js)
│   │   ├── login.html                 # Login page
│   │   ├── dashboard.html             # Analytics dashboard
│   │   ├── users.html                 # User management
│   │   ├── visitor_passes.html        # QR pass generation
│   │   └── ...
│   │
│   ├── static/
│   │   ├── style.css                  # Glassmorphism UI styles
│   │   ├── registered_faces/          # User face photos
│   │   └── qr_passes/                 # Generated QR codes
│   │
└── 💾 DATABASE
    └── instance/
        └── smartlift_saas.db          # SQLite database (auto-created)
```

---

## 🔧 Module Descriptions

### 📱 Web Application Modules

#### `app.py` - Flask Web Server
**Purpose**: Admin portal for managing users, tenants, and monitoring access  
**Runs On**: Central server (cloud or local)  
**Access**: http://localhost:8000  
**Key Features**:
- Multi-tenant management
- User enrollment with face photos
- QR visitor pass generation
- Analytics dashboard
- Access log viewing

**Usage**:
```bash
python app.py
```

#### `models.py` - Database Schema
**Purpose**: SQLAlchemy models for all database tables  
**Contains**:
- Tenant (institutions)
- User (authorized personnel)
- Admin (tenant admins)
- SuperAdmin (platform admin)
- VisitorPass (QR passes)
- AccessLog (audit trail)
- FloorRequest (lift requests)
- Lift (physical lifts)

---

### 🤖 AI & Hardware Modules (For Raspberry Pi Edge Nodes)

#### `camera_face_recognition.py` ⭐ **PRIMARY MODULE**
**Purpose**: Fast face recognition using face_recognition library  
**Use This For**: Production Raspberry Pi deployment  
**Speed**: <1 second per face match  
**Features**:
- Face encoding extraction (128-dimensional vectors)
- Fast face matching with similarity comparison
- QR code detection (seamless background scanning)
- Liveness detection (anti-spoofing)
- Graceful fallback to demo mode if camera unavailable

**Hardware Requirements**:
- USB webcam or Raspberry Pi Camera Module
- Minimum 1GB RAM (recommended 2GB+)

**Usage in Edge Node**:
```python
from camera_face_recognition import VisionEngine
vision = VisionEngine()
auth_type, identifier, status = vision.scan_for_user(active_users)
```

#### `camera_face_recognition_old.py` (Backup)
**Purpose**: Original DeepFace-based recognition (slower)  
**Use Only If**: face_recognition library won't install  
**Note**: Kept for backward compatibility

---

#### `voice_control_module.py`
**Purpose**: Voice command processing and text-to-speech feedback  
**Hardware**: USB microphone or built-in mic  
**Features**:
- Google Speech Recognition for voice commands
- pyttsx3 for offline text-to-speech
- Natural language floor number extraction
- Casual conversation handling
- Automatic fallback to text input if mic unavailable

**Voice Commands**:
- "Floor two" → Goes to floor 2
- "Take me to the third floor" → Floor 3
- "How are you?" → Casual response
- "What time is it?" → Current time

**Usage**:
```python
from voice_control_module import AudioEngine
audio = AudioEngine()
audio.speak("Welcome to SmartLift")
command = audio.listen_for_floor()
```

---

#### `lift_hardware_controller.py`
**Purpose**: Control physical lift via Arduino/PLC through serial port  
**Hardware**: 
- Arduino Uno/Mega with relay module
- USB-to-Serial adapter
- High-voltage relay board (for lift control)

**Communication Protocol**:
- Serial: 9600 baud, RS485/UART
- Command format: `GOTO:3\n` (go to floor 3)
- Automatic simulation mode if hardware unavailable

**Usage**:
```python
from lift_hardware_controller import HardwareController
hw = HardwareController(port='COM3', simulate=False)
hw.dispatch_lift(floor=3)  # Send lift to floor 3
```

**Raspberry Pi Serial Ports**:
- `/dev/ttyUSB0` - USB-to-Serial adapter
- `/dev/ttyACM0` - Arduino via USB
- `/dev/ttyAMA0` - GPIO UART pins

---

### 🎯 Edge Node Controller

#### `main.py` - Edge Node Operating System
**Purpose**: Main controller running on Raspberry Pi at each lift  
**Runs On**: Raspberry Pi 3B+/4 (one per lift)  
**Features**:
- Multi-modal authentication (Face + QR + Voice)
- Tenant tethering (one Pi = one institution)
- Subscription status validation
- Offline operation with local database
- Hardware integration (camera + mic + serial)

**Raspberry Pi Setup**:
```bash
# 1. Configure tenant ID (line 53 in main.py)
LOCAL_EDGE_TENANT_ID = 2  # Match your tenant ID

# 2. Run edge node
python main.py

# 3. Node boots, connects to database, validates subscription
# 4. Camera opens, ready to scan QR or faces
```

**Boot Sequence**:
1. Load tenant configuration from database
2. Validate subscription status (Active/Suspended)
3. Initialize camera, microphone, serial port
4. Build face recognition index from users
5. Enter main loop (QR scan + face detection + voice)

---

## 🍓 Raspberry Pi Deployment Guide

### Hardware Setup

**Required Components**:
- Raspberry Pi 4 (2GB+ RAM recommended)
- Raspberry Pi Camera Module or USB Webcam
- USB Microphone (or USB headset)
- Arduino Uno + 8-channel Relay Module
- USB-to-Serial cable
- Power supply (5V 3A for Pi, separate for Arduino)

**Wiring Diagram**:
```
Raspberry Pi
├── Camera Module → CSI Port (ribbon cable)
├── USB Mic → USB Port
├── Arduino → USB Port
│   └── Relay Module → GPIO Pins
│       ├── Relay 1-8 → Lift Floor Buttons (0-7)
│       └── GND → Common Ground
└── Network → Ethernet or WiFi
```

### Software Installation on Raspberry Pi

```bash
# 1. Update system
sudo apt update && sudo apt upgrade -y

# 2. Install Python dependencies
sudo apt install python3-pip python3-opencv libatlas-base-dev

# 3. Install Python packages
pip3 install -r requirements.txt

# 4. Enable camera
sudo raspi-config
# Interface Options → Camera → Enable

# 5. Grant serial port access
sudo usermod -a -G dialout pi
sudo chmod 666 /dev/ttyUSB0

# 6. Test camera
python3 -c "import cv2; print('Camera OK' if cv2.VideoCapture(0).isOpened() else 'Camera FAIL')"

# 7. Run edge node
python3 main.py
```

### Configuration for Multiple Raspberry Pis

**Scenario**: 3 lifts in one building

**Raspberry Pi 1** (Main Building Lift):
```python
# main.py line 53
LOCAL_EDGE_TENANT_ID = 2  # Demo University
```

**Raspberry Pi 2** (Annex Lift):
```python
# main.py line 53
LOCAL_EDGE_TENANT_ID = 2  # Same tenant, different lift
```

**Raspberry Pi 3** (Different Institution):
```python
# main.py line 53
LOCAL_EDGE_TENANT_ID = 3  # Different tenant entirely
```

---

## 🔄 Data Flow Architecture

### User Enrollment (Web Portal)
```
Admin uploads photo → app.py
  ↓
camera_face_recognition.py extracts encoding
  ↓
Saved to database (User.face_vector)
  ↓
Edge nodes fetch updated user list
```

### Access Control (Edge Node)
```
User approaches lift
  ↓
camera_face_recognition.py scans QR/Face
  ↓
Match found in database
  ↓
voice_control_module.py asks "Which floor?"
  ↓
User says "Floor 3"
  ↓
Check permissions (allowed_floors)
  ↓
lift_hardware_controller.py sends signal
  ↓
Arduino triggers relay 3
  ↓
Lift goes to floor 3
  ↓
AccessLog saved to database
```

---

## 🚀 Quick Start Commands

### For Competition Demo (No Hardware):
```bash
python app.py
# Visit http://localhost:8000
```

### For Raspberry Pi Edge Node:
```bash
python3 main.py
# Camera opens, ready for authentication
```

### For Demo Data:
```bash
python seed_demo_data.py
# Creates 61 users + 1895 logs
```

---

## 📊 Module Dependencies

| Module | Requires | Optional |
|--------|----------|----------|
| app.py | Flask, SQLAlchemy | camera_face_recognition |
| camera_face_recognition.py | opencv-python, face_recognition | dlib |
| voice_control_module.py | pyttsx3, SpeechRecognition | PyAudio |
| lift_hardware_controller.py | pyserial | Arduino |
| main.py | All above modules | - |

---

## 🔧 Troubleshooting

### Camera not detected on Raspberry Pi:
```bash
# Check camera status
vcgencmd get_camera

# Enable camera
sudo raspi-config

# Test camera
raspistill -o test.jpg
```

### Serial port permission denied:
```bash
sudo chmod 666 /dev/ttyUSB0
# Or add user to dialout group
sudo usermod -a -G dialout $USER
```

### face_recognition library won't install:
```bash
# Install dependencies first
sudo apt install cmake libboost-all-dev
pip3 install dlib --no-cache-dir
pip3 install face_recognition
```

---

## 📝 File Naming Rationale

| Old Name | New Name | Reason |
|----------|----------|--------|
| vision.py | camera_face_recognition_old.py | Legacy backup |
| vision_fast.py | camera_face_recognition.py | Primary module (fast) |
| audio.py | voice_control_module.py | Descriptive for Pi |
| hardware.py | lift_hardware_controller.py | Clear hardware purpose |

---

**For Raspberry Pi deployment, focus on these 3 files:**
1. `camera_face_recognition.py` - Face/QR scanning
2. `voice_control_module.py` - Voice commands
3. `lift_hardware_controller.py` - Physical control
4. `main.py` - Edge node orchestrator

All modules have demo mode fallbacks for testing without hardware! 🎉
