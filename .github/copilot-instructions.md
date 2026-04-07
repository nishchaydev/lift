# SmartLift - Multi-Tenant SaaS Lift Access Control System

## Overview

SmartLift is a comprehensive lift access control system with multi-tenant architecture, supporting biometric authentication (facial recognition), QR-based visitor passes, and voice commands. The system operates in two modes:
1. **Web Admin Portal** (`app.py`) - Flask application for multi-tenant management
2. **Edge Node OS** (`main.py`) - Physical lift controller running on Raspberry Pi devices

## Module Structure (Renamed for Raspberry Pi Deployment)

### Core Modules:
- `camera_face_recognition.py` - Fast face recognition using face_recognition library (PRIMARY)
- `camera_face_recognition_old.py` - Legacy DeepFace version (backup)
- `voice_control_module.py` - Voice command processing and TTS
- `lift_hardware_controller.py` - Arduino/Serial hardware control

## Running the Application

### Web Admin Portal
```bash
python app.py
# Runs on http://0.0.0.0:8000
```

**Default Credentials:**
- SuperAdmin: `founder@smartlift.com` / `founder123`
- Demo Tenant Admin: `admin@demo.com` / `admin123`

### Edge Node (Lift Controller)
```bash
python main.py
```
**Note:** Configure `LOCAL_EDGE_TENANT_ID` in `main.py` (line 53) to match the tenant ID before running.

## Architecture

### Multi-Tenant Isolation
The system enforces strict tenant isolation at the database level. Each institution (tenant) has:
- Isolated users, lifts, access logs, and visitor passes
- Subscription-based access control (Active/Suspended status gates edge node boot)
- Independent admin accounts per tenant
- One superadmin (`SuperAdmin` model) can manage all tenants

### Edge Node Tethering (Phase 11)
Physical edge devices (laptops/Raspberry Pi) are **permanently tethered** to a single tenant via `LOCAL_EDGE_TENANT_ID`. This ID must match a valid tenant in the database or the node will refuse to boot. Subscription status is checked at boot time.

### Authentication Flow (Multi-Modal)
The vision engine (`vision.py`) supports three authentication modes:
1. **QR Code** - Scanned continuously in background, triggers `VisitorPass` validation
2. **Face Recognition** - Triggered by pressing 's', uses FAISS vector similarity search
3. **Exit** - Press 'q' to shut down

Face recognition uses:
- DeepFace with Facenet model for embedding extraction
- FAISS IndexFlatIP for cosine similarity search
- Liveness detection via Laplacian blur analysis (threshold: 35)
- Match threshold: 0.40 similarity score

### Database Models (SQLAlchemy)

**Hierarchy:**
```
Tenant (institution)
├── Admin (tenant-scoped admin accounts)
├── User (authorized personnel with face vectors)
├── Lift (physical lift units)
├── VisitorPass (QR-based temporary access)
└── AccessLog (audit trail, linked via User or guest status string)
```

**Key Relationships:**
- `FloorRequest` has one `AccessLog` (one-to-one via `uselist=False`)
- `User.allowed_floors` and `VisitorPass.allowed_floors` are comma-separated strings (e.g., "0,1,2")
- Face vectors are stored as JSON-serialized float arrays in `User.face_vector`

### Flask Routes

**SuperAdmin Routes:** (prefix `/superadmin`)
- `GET /superadmin` - View all tenants
- `POST /superadmin/add_tenant` - Onboard new institution with admin account
- `GET /superadmin/toggle_tenant/<id>` - Toggle subscription Active/Suspended

**Tenant Admin Routes:** (require `session['admin_id']`)
- `GET /dashboard` - Analytics dashboard with date filtering
- `GET /export_logs` - CSV export of access logs
- `POST /users` - User registration with face image upload
- `POST /visitor_passes` - Generate QR passes with expiry dates
- `GET /approval_queue` - Public access requests (Phase 10)
- `POST /approve_request/<id>` - Approve and auto-email QR code
- `POST /api/panic/<lift_id>` - Emergency panic button endpoint

## Key Conventions

### Floor Number Mapping
Voice commands (`audio.py`) map natural language to floor numbers:
```python
{'one': 1, 'two': 2, 'ground': 0, 'first': 1, 'second': 2, 'third': 3}
```

### RBAC Time Restrictions (Phase 5)
Users can have `access_start_time` and `access_end_time` constraints. Edge node checks current time against this range before allowing access.

### Casual Conversation Handling
The edge node responds to casual voice inputs ("how are you", "tell me a joke") via `get_casual_response()` in `main.py` before processing floor commands.

### Hardware Simulation
`HardwareController` defaults to `simulate=True`. Set to `False` and configure COM port for real serial communication to Arduino/PLC units.

### QR Code Generation
QR passes are synthesized with metadata overlay (name, role, expiry) using `synthesize_custom_qr()`. Images saved to `static/qr_passes/`.

### Email Notifications (Phase 11 SMTP)
Email dispatch configured in `app.py` lines 39-83. **Requires Google App Password** in `SENDER_PASSWORD` variable for production use.

### Face Enrollment
Face images uploaded via `/users` route are:
1. Saved to `static/registered_faces/`
2. Processed with DeepFace to extract 128-dim embedding
3. L2-normalized and stored as JSON in `User.face_vector`

### Logging Pattern
All access attempts (successful or denied) create:
1. `FloorRequest` entry with status (Completed/Rejected)
2. `AccessLog` entry linked to request via `Request_ID`

For visitors, `log_visitor()` creates logs with `User_id=None` and embeds visitor name in status string.

## Database Initialization

Database auto-initializes on first run with:
- SuperAdmin account: `founder@smartlift.com`
- Demo tenant: "Demo University"
- Demo tenant admin: `admin@demo.com`
- One lift assigned to demo tenant

## Dependencies

Core libraries (inferred from imports):
- Flask + Flask-SQLAlchemy
- Werkzeug (password hashing)
- OpenCV (`cv2`) - Camera and QR detection
- DeepFace - Face recognition
- FAISS - Vector similarity search
- pyttsx3 - Text-to-speech
- SpeechRecognition - Google speech API
- pyserial - Arduino/hardware communication
- Pillow - QR code image generation
- qrcode - QR code library
- smtplib - Email notifications

## Environment Variables

No environment variables currently used. Sensitive data (SMTP credentials) are hardcoded in `app.py` lines 51-52. Consider moving to environment variables for production.

## Static File Structure

```
static/
├── registered_faces/    # User face enrollment photos
├── qr_passes/          # Generated QR code images
└── style.css           # Frontend styles
```

## Tenant-Scoped Queries

Always filter by `session['tenant_id']` when querying users, lifts, or logs in admin routes to enforce isolation:
```python
users = User.query.filter_by(tenant_id=session['tenant_id']).all()
```

For access logs that may include guests, use outer join:
```python
AccessLog.query.join(User, AccessLog.User_id == User.user_id, isouter=True).filter(
    db.or_(User.tenant_id == t_id, AccessLog.status.like('%Guest%'))
)
```
