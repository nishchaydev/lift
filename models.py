from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# -----------------
# SAAS / COLLEGE LAYER
# -----------------
class Tenant(db.Model):
    """Represents a Collage/Institution from the ER Diagram"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False) # Equivalent to clg_name
    clg_id = db.Column(db.String(50), nullable=True) # ER Mapping: cfg_id
    No_Floor = db.Column(db.Integer, default=5) # ER Mapping: No_Floor
    max_lifts = db.Column(db.Integer, default=5) # Subscription hardware capacity
    
    # Phase 6 Tenant Customization
    primary_color = db.Column(db.String(20), default='#3b82f6')
    logo_path = db.Column(db.String(255), nullable=True)
    
    subscription_status = db.Column(db.String(50), default='Active') 
    subscription_type = db.Column(db.String(50), default='Premium') 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    admins = db.relationship('Admin', backref='tenant', lazy=True)
    users = db.relationship('User', backref='tenant', lazy=True)
    lifts = db.relationship('Lift', backref='tenant', lazy=True)

class SuperAdmin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Admin(db.Model):
    admin_id = db.Column(db.Integer, primary_key=True) # ER Mapping: admin_id
    email = db.Column(db.String(120), unique=True, nullable=False) # ER Mapping: email
    password = db.Column(db.String(200), nullable=False) # ER Mapping: password
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)

# -----------------
# USER LAYER
# -----------------
class User(db.Model):
    __table_args__ = (db.UniqueConstraint('enrollment_id', 'tenant_id', name='_tenant_enrollment_uc'),)
    
    user_id = db.Column(db.Integer, primary_key=True) # ER Mapping: User_id
    name = db.Column(db.String(100), nullable=False) # ER Mapping: name
    Face_encoding = db.Column(db.Text, nullable=True) # ER Mapping: Face_encording
    face_vector = db.Column(db.Text, nullable=True) # Mathematical DB representation
    access_type = db.Column(db.String(50), default='temporary') # ER Mapping: acess type
    
    # Phase 5 Advanced Time Restrictions
    access_start_time = db.Column(db.Time, nullable=True)
    access_end_time = db.Column(db.Time, nullable=True)
    
    # Phase 7 & 10 Identity Enrichment
    email = db.Column(db.String(120), nullable=True) # Extended Comm Parameter
    enrollment_id = db.Column(db.String(50), nullable=True) # For Students/Faculty
    department = db.Column(db.String(100), nullable=True)
    course = db.Column(db.String(100), nullable=True)
    batch = db.Column(db.String(50), nullable=True)
    
    allowed_floors = db.Column(db.String(100), default='0')
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)

class VisitorPass(db.Model):
    """Temporary High-Security QR Pass for Deliveries/Guests"""
    id = db.Column(db.Integer, primary_key=True)
    visitor_name = db.Column(db.String(100), nullable=False)
    purpose = db.Column(db.String(200), nullable=True)
    qr_hash = db.Column(db.String(255), unique=True, nullable=False) # Cryptographic signature
    qr_image_path = db.Column(db.String(255), nullable=True)
    
    allowed_floors = db.Column(db.String(100), default='0')
    valid_from = db.Column(db.DateTime, default=datetime.utcnow)
    valid_until = db.Column(db.DateTime, nullable=False) # Expiry constraint Limit
    status = db.Column(db.String(50), default='Active') # Active/Expired/Revoked
    
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    created_by_admin_id = db.Column(db.Integer, db.ForeignKey('admin.admin_id'), nullable=False)

# -----------------
# LIFT & REQUEST LAYER
# -----------------
class Lift(db.Model):
    Lift_id = db.Column(db.Integer, primary_key=True) # ER Mapping: Lift_id
    name = db.Column(db.String(50), default='Main Lobby Lift')
    status = db.Column(db.String(50), default='Idle') # ER Mapping: status
    
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    floor_requests = db.relationship('FloorRequest', backref='lift', lazy=True)

class FloorRequest(db.Model):
    Request_ID = db.Column(db.Integer, primary_key=True) # ER Mapping: Request ID
    User_id = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=True) # ER Mapping: User id
    Floor_number = db.Column(db.Integer, nullable=False) # ER Mapping: Floor number
    Status = db.Column(db.String(50), default='Pending') # ER Mapping: Status
    Lift_id = db.Column(db.Integer, db.ForeignKey('lift.Lift_id'), nullable=False) 
    
    access_log = db.relationship('AccessLog', backref='floor_request', uselist=False)

class AccessLog(db.Model):
    Log_id = db.Column(db.Integer, primary_key=True) # ER Mapping: Log_id
    User_id = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=True) # ER Mapping: User_id (Nullable for strangers/spoofs)
    timestlap = db.Column(db.DateTime, default=datetime.utcnow) # ER Mapping: timestlap
    
    Source_floor = db.Column(db.Integer, default=0) # Phase 7: Node Invocation Origin
    Floor_selection = db.Column(db.Integer, nullable=False) # Destination
    
    Request_ID = db.Column(db.Integer, db.ForeignKey('floor_request.Request_ID'), nullable=True)
    status = db.Column(db.String(100), default='Granted') # Log everything: Mismatches, Denials, Successes
    
    user = db.relationship('User')

class EmergencyEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    lift_id = db.Column(db.Integer, db.ForeignKey('lift.Lift_id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    resolved = db.Column(db.Boolean, default=False)
    lift = db.relationship('Lift')

class AccessRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False) # Phase 10 Requirement
    role = db.Column(db.String(50), nullable=False)
    enrollment_id = db.Column(db.String(50), nullable=True)
    department = db.Column(db.String(100), nullable=True)
    reason = db.Column(db.Text, nullable=False)
    requested_duration_hours = db.Column(db.Integer, default=24)
    floors = db.Column(db.String(50), default='0')
    status = db.Column(db.String(50), default='Pending') # Pending, Approved, Rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
