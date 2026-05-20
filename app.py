from flask import Flask, Response, render_template, request, redirect, url_for, session, flash, jsonify
from software.models import db, SuperAdmin, Admin, Tenant, User, Lift, FloorRequest, AccessLog, VisitorPass, EmergencyEvent, AccessRequest
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
import re
import uuid
import qrcode
import secrets
from datetime import datetime, timedelta
from collections import Counter
from sqlalchemy import text
import PIL.Image as PIL_Image
from PIL import ImageDraw
from dotenv import load_dotenv

load_dotenv()

def synthesize_custom_qr(qr_hash, name, role, valid_until, ID=""):
    import qrcode
    from PIL import Image, ImageDraw
    import os
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_hash)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    canvas_w = qr_img.width + 40
    canvas_h = qr_img.height + 120
    canvas = Image.new('RGB', (canvas_w, canvas_h), 'white')
    canvas.paste(qr_img, (20, 20))
    
    draw = ImageDraw.Draw(canvas)
    y = qr_img.height + 25
    id_str = f" | ID: {ID}" if ID else ""
    draw.text((25, y), f"IDENTITY: {name}", fill="black")
    draw.text((25, y+20), f"ROLE: {role}{id_str}", fill="black")
    draw.text((25, y+40), f"EXPIRES: {valid_until.strftime('%Y-%m-%d %H:%M UTC')}", fill="red")
    
    safe_name = name.replace(" ", "_")
    filename = f"{valid_until.strftime('%Y%m%d')}_{ID or 'NA'}_{safe_name}.png"
    filepath = os.path.join('static', 'qr_passes', filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    canvas.save(filepath)
    return filepath

# =========================================================
# RESEND EMAIL ENGINE (mail.emitra.dev)
# Uses Resend HTTP API — zero external dependencies needed.
# =========================================================
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
RESEND_FROM = os.environ.get("RESEND_FROM", "SmartLift <noreply@mail.emitra.dev>")

def _resend_send(to_email, subject, html_body, attachment_path=None):
    """Low-level Resend HTTP API call using only stdlib."""
    if not RESEND_API_KEY:
        print(f"[RESEND] Skipped (no API key): {to_email}")
        return False
    import urllib.request
    import json as _json
    import base64
    import os

    payload_dict = {
        "from": RESEND_FROM,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }

    if attachment_path and os.path.exists(attachment_path):
        try:
            with open(attachment_path, "rb") as f:
                b64_content = base64.b64encode(f.read()).decode("utf-8")
            payload_dict["attachments"] = [
                {
                    "filename": os.path.basename(attachment_path),
                    "content": b64_content
                }
            ]
        except Exception as e:
            print(f"[RESEND ATTACHMENT ERROR] {e}")

    payload = _json.dumps(payload_dict).encode("utf-8")

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = _json.loads(resp.read().decode())
            print(f"---> [RESEND 200 OK] Email sent to {to_email} | id={body.get('id')}")
            return True
    except urllib.error.HTTPError as e:
        err_body = e.read().decode() if e.fp else ""
        print(f"[RESEND HTTP {e.code}] {err_body}")
        return False
    except Exception as e:
        print(f"[RESEND ERROR] {e}")
        return False


def send_welcome_email(recipient_email, recipient_name, role, allowed_floors, tenant_name, qr_path=None):
    """Send a welcome email when a new user is added to the system."""
    if not recipient_email:
        print("[EMAIL] No email provided for new user. Skipping welcome email.")
        return False

    html = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:600px;margin:auto;background:#0f172a;color:#e2e8f0;border-radius:12px;overflow:hidden;">
      <div style="background:linear-gradient(135deg,#3b82f6,#8b5cf6);padding:32px 24px;text-align:center;">
        <h1 style="margin:0;font-size:28px;color:#fff;">🏢 SmartLift</h1>
        <p style="margin:8px 0 0;font-size:14px;color:#e0e7ff;">Intelligent Building Access System</p>
      </div>
      <div style="padding:28px 24px;">
        <h2 style="color:#60a5fa;margin-top:0;">Welcome aboard, {recipient_name}!</h2>
        <p>You have been successfully registered in the <strong style="color:#a78bfa;">{tenant_name}</strong> SmartLift system.</p>
        <table style="width:100%;border-collapse:collapse;margin:20px 0;">
          <tr><td style="padding:8px 12px;color:#94a3b8;">Role</td><td style="padding:8px 12px;color:#f1f5f9;font-weight:600;">{role}</td></tr>
          <tr><td style="padding:8px 12px;color:#94a3b8;">Allowed Floors</td><td style="padding:8px 12px;color:#f1f5f9;font-weight:600;">{allowed_floors}</td></tr>
        </table>
        <p style="color:#94a3b8;font-size:13px;">Your face has been enrolled in our biometric database. Simply approach any Edge Node scanner on-site to authenticate and operate the lift.</p>
        {"<p style='color:#94a3b8;font-size:13px;'>A QR-based Visitor Pass is also attached for your convenience. You can scan it as an alternative way to access the building.</p>" if qr_path else ""}
        <div style="margin-top:24px;padding:16px;background:#1e293b;border-radius:8px;border-left:4px solid #3b82f6;">
          <p style="margin:0;font-size:13px;color:#cbd5e1;">🔒 Your biometric data is securely encrypted and never leaves the institution's local network.</p>
        </div>
      </div>
      <div style="padding:16px 24px;background:#1e293b;text-align:center;font-size:11px;color:#64748b;">
        SmartLift Security Engine &middot; Powered by eMitra
      </div>
    </div>
    """
    return _resend_send(recipient_email, f"Welcome to SmartLift — {tenant_name}", html, attachment_path=qr_path)


def send_update_email(recipient_email, recipient_name, role, allowed_floors, tenant_name):
    """Send an update email when user details are changed."""
    if not recipient_email:
        return False

    html = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:600px;margin:auto;background:#0f172a;color:#e2e8f0;border-radius:12px;overflow:hidden;">
      <div style="background:linear-gradient(135deg,#3b82f6,#8b5cf6);padding:32px 24px;text-align:center;">
        <h1 style="margin:0;font-size:28px;color:#fff;">🏢 SmartLift</h1>
        <p style="margin:8px 0 0;font-size:14px;color:#e0e7ff;">Access Profile Updated</p>
      </div>
      <div style="padding:28px 24px;">
        <h2 style="color:#60a5fa;margin-top:0;">Hello, {recipient_name}!</h2>
        <p>Your access profile in the <strong style="color:#a78bfa;">{tenant_name}</strong> SmartLift system has been updated by an administrator.</p>
        <table style="width:100%;border-collapse:collapse;margin:20px 0;">
          <tr><td style="padding:8px 12px;color:#94a3b8;">Role</td><td style="padding:8px 12px;color:#f1f5f9;font-weight:600;">{role}</td></tr>
          <tr><td style="padding:8px 12px;color:#94a3b8;">Allowed Floors</td><td style="padding:8px 12px;color:#f1f5f9;font-weight:600;">{allowed_floors}</td></tr>
        </table>
        <p style="color:#94a3b8;font-size:13px;">If you have any questions about these changes, please contact your building administrator.</p>
      </div>
      <div style="padding:16px 24px;background:#1e293b;text-align:center;font-size:11px;color:#64748b;">
        SmartLift Security Engine &middot; Powered by eMitra
      </div>
    </div>
    """
    return _resend_send(recipient_email, f"SmartLift Access Updated — {tenant_name}", html)


def send_approval_email(recipient_email, recipient_name, role, floors, valid_until, tenant_name, qr_path=None):
    """Send an approval notification email when an access request is approved."""
    if not recipient_email:
        print("[EMAIL] No email for approved request. Skipping.")
        return False

    expiry_str = valid_until.strftime('%B %d, %Y at %I:%M %p UTC') if valid_until else 'N/A'

    html = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:600px;margin:auto;background:#0f172a;color:#e2e8f0;border-radius:12px;overflow:hidden;">
      <div style="background:linear-gradient(135deg,#10b981,#3b82f6);padding:32px 24px;text-align:center;">
        <h1 style="margin:0;font-size:28px;color:#fff;">✅ Access Approved</h1>
        <p style="margin:8px 0 0;font-size:14px;color:#d1fae5;">SmartLift Security Clearance</p>
      </div>
      <div style="padding:28px 24px;">
        <h2 style="color:#34d399;margin-top:0;">Hello {recipient_name},</h2>
        <p>Your access request has been <strong style="color:#10b981;">approved</strong> by the administration at <strong style="color:#a78bfa;">{tenant_name}</strong>.</p>
        <table style="width:100%;border-collapse:collapse;margin:20px 0;">
          <tr><td style="padding:8px 12px;color:#94a3b8;">Role</td><td style="padding:8px 12px;color:#f1f5f9;font-weight:600;">{role}</td></tr>
          <tr><td style="padding:8px 12px;color:#94a3b8;">Allowed Floors</td><td style="padding:8px 12px;color:#f1f5f9;font-weight:600;">{floors}</td></tr>
          <tr><td style="padding:8px 12px;color:#94a3b8;">Valid Until</td><td style="padding:8px 12px;color:#fbbf24;font-weight:600;">{expiry_str}</td></tr>
        </table>
        <p style="color:#94a3b8;font-size:13px;">A QR-based Visitor Pass has been generated. {"You will find it attached to this email. " if qr_path else ""}You can scan it at any SmartLift Edge Node scanner on-site to access the building.</p>
        <div style="margin-top:24px;padding:16px;background:#1e293b;border-radius:8px;border-left:4px solid #10b981;">
          <p style="margin:0;font-size:13px;color:#cbd5e1;">📍 Please carry a valid photo ID when visiting the institution premises.</p>
        </div>
      </div>
      <div style="padding:16px 24px;background:#1e293b;text-align:center;font-size:11px;color:#64748b;">
        SmartLift Security Engine &middot; Powered by eMitra
      </div>
    </div>
    """
    return _resend_send(recipient_email, f"Access Approved — {tenant_name} SmartLift", html, attachment_path=qr_path)


def dispatch_email(recipient_email, recipient_name, qr_path):
    """Legacy-compatible wrapper — sends approval email via Resend."""
    if not recipient_email:
        print("[EMAIL] No recipient email. Skipping.")
        return False
    return send_approval_email(recipient_email, recipient_name, 'Visitor', 'As assigned', None, 'SmartLift', qr_path=qr_path)


app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-only-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URI', 'sqlite:///smartlift_saas.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False

@app.context_processor
def inject_csrf():
    def generate_csrf_token():
        return session.get('_csrf_token', '')
    return dict(csrf_token=generate_csrf_token)

EXEMPT_CSRF_ENDPOINTS = {'api_faiss_verify', 'api_lift_request', 'api_voice_command', 'request_access'}

@app.before_request
def csrf_protect():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(16)
        session.permanent = True
        session.modified = True

    if request.method == "POST":
        if request.endpoint in EXEMPT_CSRF_ENDPOINTS or request.path.startswith('/api/'):
            return
            
        token = session.get('_csrf_token', None)
        
        if request.is_json or request.content_type == 'application/json':
            if not token or token != request.headers.get('X-CSRFToken'):
                print(f"[CSRF ERROR JSON] session_token={token}, header={request.headers.get('X-CSRFToken')}")
                return jsonify({"error": "CSRF token missing or invalid."}), 403
            return
            
        form_token = request.form.get('csrf_token')
        if not token or token != form_token:
            print(f"[CSRF ERROR FORM] session_token={token}, form_token={form_token}, endpoint={request.endpoint}")
            flash("CSRF token missing or invalid. Please reload the page and try again.", "danger")
            # If there's no referrer and it's the login page, redirect back to login
            if request.endpoint == 'login':
                return redirect(url_for('login'))
            return redirect(request.referrer or url_for('superadmin_dashboard'))

os.makedirs('static/registered_faces', exist_ok=True)

db.init_app(app)
EDGE_BIND_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "edge_node_config.json")


def _sync_local_edge_tenant_binding(tenant_id):
    """Persist tenant binding for local edge runtime (main.py)."""
    try:
        payload = {
            "tenant_id": int(tenant_id),
            "source": "web-login",
            "updated_at": datetime.utcnow().isoformat() + "Z"
        }
        with open(EDGE_BIND_FILE, "w", encoding="utf-8") as fp:
            json.dump(payload, fp)
        print(f"[EDGE SYNC] Local edge tenant binding updated to Tenant #{tenant_id}.")
    except Exception as err:
        print(f"[EDGE SYNC] Failed to update local edge binding: {err}")


def ensure_access_request_review_columns():
    """Backfill review metadata columns for existing databases."""
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    if not inspector.has_table('access_request'):
        return
    existing_cols = {col['name'] for col in inspector.get_columns('access_request')}
    with db.engine.begin() as conn:
        if 'admin_decision_note' not in existing_cols:
            conn.execute(text("ALTER TABLE access_request ADD COLUMN admin_decision_note TEXT"))
        if 'reviewed_at' not in existing_cols:
            conn.execute(text("ALTER TABLE access_request ADD COLUMN reviewed_at DATETIME"))
        if 'reviewed_by_admin_id' not in existing_cols:
            conn.execute(text("ALTER TABLE access_request ADD COLUMN reviewed_by_admin_id INTEGER"))

with app.app_context():
    db.create_all()
    ensure_access_request_review_columns()
    # 1. Create Root SuperAdmin (Mohit & Team)
    if not SuperAdmin.query.filter_by(email="founder@smartlift.com").first():
        pw = generate_password_hash("founder123", method='pbkdf2:sha256')
        db.session.add(SuperAdmin(email="founder@smartlift.com", password=pw))
        db.session.commit()
    
    # 2. Create Demo Tenant if none
    if not Tenant.query.first():
        demo_tenant = Tenant(name="Demo University", subscription_type="Enterprise", max_lifts=10)
        db.session.add(demo_tenant)
        db.session.commit()
        # Create Demo Admin associated with this tenant
        admin_pw = generate_password_hash("admin123", method='pbkdf2:sha256')
        db.session.add(Admin(email="admin@demo.com", password=admin_pw, tenant_id=demo_tenant.id))
        # Create Demo Lift associated with this tenant
        db.session.add(Lift(name="Main Building Lift", status="Online", tenant_id=demo_tenant.id))
        db.session.commit()

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # 1. Check SuperAdmin First
        super_admin = SuperAdmin.query.filter_by(email=email).first()
        if super_admin and check_password_hash(super_admin.password, password):
            session['superadmin_id'] = super_admin.id
            return redirect(url_for('superadmin_dashboard'))
            
        # 2. Check Local Tenant Admin Second
        tenant_admin = Admin.query.filter_by(email=email).first()
        if tenant_admin and check_password_hash(tenant_admin.password, password):
            # Check Subscription Rules
            if tenant_admin.tenant.subscription_status != 'Active':
                flash("Your institution's subscription is suspended. Please contact SmartLift Founders.", "danger")
                return redirect(url_for('login'))
                 
            session['admin_id'] = tenant_admin.admin_id
            session['tenant_id'] = tenant_admin.tenant_id
            _sync_local_edge_tenant_binding(tenant_admin.tenant_id)
            return redirect(url_for('dashboard'))
            
        flash("Invalid Credentials. Access Denied.", "danger")
    return render_template('login.html')

# --------------------------
# SUPERADMIN ROUTES
# --------------------------
@app.route('/superadmin')
def superadmin_dashboard():
    if 'superadmin_id' not in session: return redirect(url_for('login'))
    tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
    active_tenants = sum(1 for t in tenants if t.subscription_status == 'Active')
    tenant_metrics = {}
    for t in tenants:
        tenant_metrics[t.id] = {
            'users': User.query.filter_by(tenant_id=t.id).count(),
            'lifts': Lift.query.filter_by(tenant_id=t.id).count()
        }
    return render_template(
        'superadmin_dashboard.html',
        tenants=tenants,
        total_tenants=len(tenants),
        active_tenants=active_tenants,
        suspended_tenants=(len(tenants) - active_tenants),
        tenant_metrics=tenant_metrics
    )

@app.route('/superadmin/add_tenant', methods=['POST'])
def add_tenant():
    if 'superadmin_id' not in session: return redirect(url_for('login'))
    name = request.form.get('name')
    sub_type = request.form.get('subscription_type')
    max_lifts = request.form.get('max_lifts')
    admin_email = request.form.get('admin_email')
    admin_pass = request.form.get('admin_pass')
    
    new_tenant = Tenant(name=name, subscription_type=sub_type, max_lifts=int(max_lifts))
    db.session.add(new_tenant)
    db.session.commit()
    
    hashed_pw = generate_password_hash(admin_pass, method='pbkdf2:sha256')
    db.session.add(Admin(email=admin_email, password=hashed_pw, tenant_id=new_tenant.id))
    db.session.commit()
    
    flash(f"Tenant '{name}' onboarded successfully!", "success")
    return redirect(url_for('superadmin_dashboard'))

@app.route('/superadmin/toggle_tenant/<int:id>', methods=['POST'])
def toggle_tenant(id):
    if 'superadmin_id' not in session: return redirect(url_for('login'))
    tenant = Tenant.query.get(id)
    if tenant:
        tenant.subscription_status = 'Suspended' if tenant.subscription_status == 'Active' else 'Active'
        db.session.commit()
        flash(f"Tenant '{tenant.name}' status changed to {tenant.subscription_status}", "success")
    return redirect(url_for('superadmin_dashboard'))


@app.route('/superadmin/api/tenant/<int:tenant_id>')
def superadmin_get_tenant(tenant_id):
    if 'superadmin_id' not in session:
        return {'error': 'Unauthorized'}, 401

    tenant = Tenant.query.get(tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    tenant_admin = Admin.query.filter_by(tenant_id=tenant.id).order_by(Admin.admin_id.asc()).first()
    return {
        'id': tenant.id,
        'name': tenant.name,
        'clg_id': tenant.clg_id or '',
        'no_floor': tenant.No_Floor or 0,
        'subscription_type': tenant.subscription_type or 'Premium',
        'subscription_status': tenant.subscription_status or 'Active',
        'max_lifts': tenant.max_lifts or 0,
        'primary_color': tenant.primary_color or '#3b82f6',
        'admin_email': tenant_admin.email if tenant_admin else ''
    }


@app.route('/superadmin/edit_tenant/<int:tenant_id>', methods=['POST'])
def edit_tenant(tenant_id):
    if 'superadmin_id' not in session: return redirect(url_for('login'))

    tenant = Tenant.query.get(tenant_id)
    if not tenant:
        flash("Tenant not found.", "danger")
        return redirect(url_for('superadmin_dashboard'))

    name = (request.form.get('name') or '').strip()
    subscription_type = (request.form.get('subscription_type') or '').strip()
    subscription_status = (request.form.get('subscription_status') or '').strip()
    primary_color = (request.form.get('primary_color') or '').strip()
    clg_id = (request.form.get('clg_id') or '').strip()
    admin_email = (request.form.get('admin_email') or '').strip().lower()
    admin_password = (request.form.get('admin_password') or '').strip()

    if not name:
        flash("Institution name is required.", "danger")
        return redirect(url_for('superadmin_dashboard'))

    try:
        max_lifts = int(request.form.get('max_lifts', tenant.max_lifts))
    except ValueError:
        flash("Max lifts must be a valid number.", "danger")
        return redirect(url_for('superadmin_dashboard'))
    if max_lifts < 1:
        flash("Max lifts must be at least 1.", "danger")
        return redirect(url_for('superadmin_dashboard'))

    try:
        no_floor = int(request.form.get('no_floor', tenant.No_Floor or 5))
    except ValueError:
        flash("Floor count must be a valid number.", "danger")
        return redirect(url_for('superadmin_dashboard'))
    if no_floor < 1:
        flash("Floor count must be at least 1.", "danger")
        return redirect(url_for('superadmin_dashboard'))

    tenant.name = name
    tenant.subscription_type = subscription_type or tenant.subscription_type
    tenant.subscription_status = subscription_status if subscription_status in ('Active', 'Suspended') else tenant.subscription_status
    tenant.max_lifts = max_lifts
    tenant.No_Floor = no_floor
    tenant.clg_id = clg_id or None
    if primary_color:
        tenant.primary_color = primary_color

    tenant_admin = Admin.query.filter_by(tenant_id=tenant.id).order_by(Admin.admin_id.asc()).first()
    if admin_email:
        existing_email_admin = Admin.query.filter_by(email=admin_email).first()
        if existing_email_admin and (not tenant_admin or existing_email_admin.admin_id != tenant_admin.admin_id):
            flash(f"Admin email '{admin_email}' is already linked to another tenant.", "danger")
            return redirect(url_for('superadmin_dashboard'))
        if tenant_admin:
            tenant_admin.email = admin_email
        else:
            if not admin_password:
                flash("Provide admin password when creating a missing tenant admin account.", "danger")
                return redirect(url_for('superadmin_dashboard'))
            tenant_admin = Admin(
                email=admin_email,
                password=generate_password_hash(admin_password, method='pbkdf2:sha256'),
                tenant_id=tenant.id
            )
            db.session.add(tenant_admin)

    if admin_password:
        if not tenant_admin:
            flash("Admin email is required to set password.", "danger")
            return redirect(url_for('superadmin_dashboard'))
        tenant_admin.password = generate_password_hash(admin_password, method='pbkdf2:sha256')

    db.session.commit()
    flash(f"Tenant '{tenant.name}' updated successfully.", "success")
    return redirect(url_for('superadmin_dashboard'))


def _parse_iso_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return None


def _tenant_accesslog_query(tenant_id):
    return AccessLog.query.join(
        User, AccessLog.User_id == User.user_id, isouter=True
    ).join(
        FloorRequest, AccessLog.Request_ID == FloorRequest.Request_ID, isouter=True
    ).join(
        Lift, FloorRequest.Lift_id == Lift.Lift_id, isouter=True
    ).filter(
        db.or_(User.tenant_id == tenant_id, Lift.tenant_id == tenant_id)
    )


def _apply_status_role_filters(query, status_filter, role_filter):
    if status_filter == 'granted':
        query = query.filter(
            db.or_(
                AccessLog.status.ilike('%Granted%'),
                AccessLog.status.ilike('%Confirmed%')
            )
        )
    elif status_filter == 'denied':
        query = query.filter(
            db.or_(
                AccessLog.status.ilike('%Denied%'),
                AccessLog.status.ilike('%Rejected%')
            )
        )
    elif status_filter == 'alerts':
        query = query.filter(AccessLog.status.ilike('%Alert%'))

    if role_filter == 'Guests':
        query = query.filter(AccessLog.User_id.is_(None))
    elif role_filter and role_filter != 'all':
        query = query.filter(User.access_type == role_filter)

    return query


def _is_denied_status(status):
    return any(marker in status for marker in ('Denied', 'Rejected', 'Alert'))


def _denial_reason(status):
    status_lower = status.lower()
    if 'out of hours' in status_lower:
        return 'Out of Hours'
    if 'role constraint' in status_lower:
        return 'Role Restriction'
    if 'invalid qr' in status_lower:
        return 'Invalid QR'
    if 'expired' in status_lower:
        return 'Expired Pass'
    if 'spoof' in status_lower:
        return 'Liveness/Spoof'
    if 'unknown' in status_lower or 'mismatch' in status_lower:
        return 'Unknown Identity'
    if 'denied' in status_lower:
        return 'General Denied'
    if 'rejected' in status_lower:
        return 'General Rejected'
    return 'Other'


def _get_tenant_primary_lift_id(tenant_id):
    lift = Lift.query.filter_by(tenant_id=tenant_id).order_by(Lift.Lift_id.asc()).first()
    if lift:
        return lift.Lift_id
    lift = Lift(name="Main Building Lift", status="Online", tenant_id=tenant_id)
    db.session.add(lift)
    db.session.commit()
    return lift.Lift_id


def _create_floor_request_and_log(user_id, floor_selection, status, lift_id, source_floor=0):
    req = FloorRequest(
        User_id=user_id,
        Floor_number=floor_selection,
        Status='Completed' if 'Granted' in status else 'Rejected',
        Lift_id=lift_id
    )
    db.session.add(req)
    db.session.flush()
    log = AccessLog(
        User_id=user_id,
        Floor_selection=floor_selection,
        Source_floor=source_floor,
        status=status,
        Request_ID=req.Request_ID
    )
    db.session.add(log)


def _parse_floor_list(floors_text):
    floors = []
    for token in str(floors_text or '').split(','):
        token = token.strip()
        if not token:
            continue
        try:
            floors.append(int(token))
        except ValueError:
            continue
    unique = sorted(set(floors))
    return unique if unique else [0]


def _extract_floor_number_from_text(text_value):
    if not text_value:
        return None

    text_lower = str(text_value).strip().lower()
    mapping = {
        'ground': 0,
        'zero': 0,
        'lobby': 0,
        'one': 1,
        'first': 1,
        'two': 2,
        'second': 2,
        'three': 3,
        'third': 3,
        'four': 4,
        'fourth': 4,
        'five': 5,
        'fifth': 5,
        'six': 6,
        'sixth': 6,
        'seven': 7,
        'seventh': 7,
        'eight': 8,
        'eighth': 8,
        'nine': 9,
        'ninth': 9,
        'ten': 10,
        'tenth': 10,
    }

    for key, floor_num in mapping.items():
        if re.search(rf'\b{re.escape(key)}\b', text_lower):
            return floor_num

    numeric_match = re.search(r'\d+', text_lower)
    if numeric_match:
        return int(numeric_match.group())
    return None


def _current_verified_access():
    verified = session.get('verified_access')
    if not verified:
        return None
    if verified.get('tenant_id') != session.get('tenant_id'):
        return None
    return verified

# --------------------------
# TENANT ROUTES (Strict Isolation)
# --------------------------
@app.route('/dashboard')
def dashboard():
    if 'admin_id' not in session: return redirect(url_for('login'))
    t_id = session['tenant_id']
    tenant = Tenant.query.get(t_id)
    
    # Only fetch users and lifts for this specific tenant
    users = User.query.filter_by(tenant_id=t_id).all()
    active_lifts = Lift.query.filter_by(tenant_id=t_id, status="Online").count()

    # Dashboard filters
    filter_date = request.args.get('date', '').strip()
    start_date_raw = request.args.get('start_date', '').strip()
    end_date_raw = request.args.get('end_date', '').strip()
    status_filter = request.args.get('status', 'all')
    role_filter = request.args.get('role', 'all')

    if filter_date and not start_date_raw and not end_date_raw:
        start_date_raw = filter_date
        end_date_raw = filter_date

    start_date = _parse_iso_date(start_date_raw)
    end_date = _parse_iso_date(end_date_raw)
    if start_date and end_date and start_date > end_date:
        start_date, end_date = end_date, start_date

    query = _tenant_accesslog_query(t_id)
    query = _apply_status_role_filters(query, status_filter, role_filter)
    if start_date:
        query = query.filter(db.func.date(AccessLog.timestlap) >= start_date)
    if end_date:
        query = query.filter(db.func.date(AccessLog.timestlap) <= end_date)

    logs = query.order_by(AccessLog.timestlap.desc()).limit(200).all()
    
    # Phase 7: Real Data Mapping for Identity Distributions
    dist = {'Operator': 0, 'Faculty': 0, 'Disability': 0, 'Temporary': 0, 'Guests': 0, 'Alerts': 0}
    for log in logs:
        if _is_denied_status(log.status):
            dist['Alerts'] += 1
        elif log.user:
            role = log.user.access_type
            if role in dist: dist[role] += 1
            else: dist['Temporary'] += 1
        else:
            dist['Guests'] += 1
    chart_data = [dist['Operator'], dist['Faculty'], dist['Disability'], dist['Temporary'], dist['Guests'], dist['Alerts']]

    denied_count = sum(1 for log in logs if _is_denied_status(log.status))
    peak_hour = "N/A"
    hours = [log.timestlap.hour for log in logs]
    if hours:
        peak_hour = f"{Counter(hours).most_common(1)[0][0]}:00"
    
    # ============================================
    # ADVANCED ANALYTICS: 7-Day Access Trend
    # ============================================
    trend_labels = []
    trend_values = []
    for i in range(6, -1, -1):
        day = datetime.utcnow().date() - timedelta(days=i)
        day_name = day.strftime('%a %d')
        trend_labels.append(day_name)
        day_query = _tenant_accesslog_query(t_id)
        day_query = _apply_status_role_filters(day_query, status_filter, role_filter)
        count = day_query.filter(db.func.date(AccessLog.timestlap) == day).count()
        trend_values.append(count)

    # ============================================
    # ADVANCED ANALYTICS: Floor Usage Distribution
    # ============================================
    floor_labels = []
    floor_values = []
    floor_counts = {}
    for log in logs:
        f = log.Floor_selection
        floor_counts[f] = floor_counts.get(f, 0) + 1
    for floor_num in sorted(floor_counts.keys()):
        floor_labels.append(f"Floor {floor_num}")
        floor_values.append(floor_counts[floor_num])
    if not floor_labels:
        floor_labels = ['Floor 0', 'Floor 1', 'Floor 2']
        floor_values = [0, 0, 0]

    denial_reason_counter = Counter()
    for log in logs:
        if _is_denied_status(log.status):
            denial_reason_counter[_denial_reason(log.status)] += 1
    top_denial_reasons = denial_reason_counter.most_common(5)

    unresolved_panic_count = EmergencyEvent.query.filter_by(tenant_id=t_id, resolved=False).count()
    latest_panic_events = EmergencyEvent.query.filter_by(tenant_id=t_id).order_by(EmergencyEvent.timestamp.desc()).limit(5).all()
    
    return render_template('dashboard.html', tenant=tenant, total_users=len(users), logs=logs, 
                           active_lifts=active_lifts, peak_hour=peak_hour, chart_data=chart_data,
                           trend_labels=trend_labels, trend_values=trend_values,
                           floor_labels=floor_labels, floor_values=floor_values,
                           denied_count=denied_count, top_denial_reasons=top_denial_reasons,
                           unresolved_panic_count=unresolved_panic_count, latest_panic_events=latest_panic_events,
                           start_date=(start_date.isoformat() if start_date else ''),
                           end_date=(end_date.isoformat() if end_date else ''),
                           status_filter=status_filter, role_filter=role_filter)

@app.route('/export_logs')
def export_logs():
    if 'admin_id' not in session: return redirect(url_for('login'))
    t_id = session['tenant_id']

    logs = _tenant_accesslog_query(t_id).order_by(AccessLog.timestlap.desc()).all()
    
    def generate():
        yield "Timestamp,Identity,Target_Floor,Status\n"
        for log in logs:
            name = log.user.name if log.user else "Unregistered/Guest"
            status = log.status.replace(',', '')
            yield f"{log.timestlap.strftime('%Y-%m-%d %H:%M:%S')},{name},{log.Floor_selection},{status}\n"
            
    return Response(generate(), mimetype='text/csv', headers={"Content-Disposition": f"attachment;filename=Tenant_{t_id}_logs.csv"})

@app.route('/users', methods=['GET', 'POST'])
def manage_users():
    if 'admin_id' not in session: return redirect(url_for('login'))
    t_id = session['tenant_id']
    
    if request.method == 'POST':
        name = request.form.get('name')
        access_role = request.form.get('access_role')
        floors = request.form.get('allowed_floors')
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        email = request.form.get('email') or None
        enrollment_id = request.form.get('enrollment_id') or None
        department = request.form.get('department') or None
        course = request.form.get('course') or None
        batch = request.form.get('batch') or None
        start_time = datetime.strptime(start_time_str, '%H:%M').time() if start_time_str else None
        end_time = datetime.strptime(end_time_str, '%H:%M').time() if end_time_str else None
        file = request.files.get('face_image')
        camera_data = request.form.get('camera_image_data')  # Base64 from webcam
        
        filepath = ""
        face_vector_cache = ""
        
        # Handle camera capture (base64 image from webcam)
        if camera_data and camera_data.startswith('data:image'):
            import base64
            header, data = camera_data.split(',', 1)
            img_bytes = base64.b64decode(data)
            filename = f"t{t_id}_{name.replace(' ', '_')}_cam.jpg"
            filepath = os.path.join('static', 'registered_faces', filename)
            with open(filepath, 'wb') as f:
                f.write(img_bytes)
        elif file and file.filename != '':
            # Standard file upload
            filename = f"t{t_id}_{name.replace(' ', '_')}.jpg"
            filepath = os.path.join('static', 'registered_faces', filename)
            file.save(filepath)
        
        # Extract face vector if we have an image
        if filepath:
            try:
                from hardware.camera_face_recognition import VisionEngine
                import json
                v = VisionEngine()
                vec = v.extract_vector(filepath)
                if vec is not None:
                    face_vector_cache = json.dumps(vec if isinstance(vec, list) else vec.tolist())
                else:
                    flash("AI warning: No clear face detected in the photo. Please re-upload.", "danger")
            except Exception as e:
                print(f"Extraction Error: {e}")
                
        existing = None
        if enrollment_id:
            existing = User.query.filter_by(tenant_id=t_id, enrollment_id=enrollment_id).first()
            
        if existing:
            # Upsert an existing user instead of blocking
            existing.name = name
            if email: existing.email = email
            existing.access_type = access_role
            existing.allowed_floors = floors
            existing.department = department
            existing.course = course
            existing.batch = batch
            if start_time: existing.access_start_time = start_time
            if end_time: existing.access_end_time = end_time
            if filepath:
                existing.Face_encoding = filepath
                existing.face_vector = face_vector_cache
            
            db.session.commit()
            
            try:
                faiss_engine.build_index(User.query.filter_by(tenant_id=t_id).all())
            except Exception as e:
                print(f"[FAISS] Index rebuild skipped: {e}")
                
            tenant = Tenant.query.get(t_id)
            tenant_name = tenant.name if tenant else 'SmartLift'
            if existing.email:
                send_update_email(existing.email, existing.name, existing.access_type, existing.allowed_floors, tenant_name)
                
            flash(f"User {existing.name} (Enrollment {enrollment_id}) updated successfully! Email notification sent.", "success")
            return redirect(url_for('manage_users'))

        new_user = User(
            name=name, email=email, access_type=access_role, allowed_floors=floors, 
            Face_encoding=filepath, face_vector=face_vector_cache, 
            access_start_time=start_time, access_end_time=end_time, tenant_id=t_id,
            enrollment_id=enrollment_id, department=department, course=course, batch=batch
        )
        db.session.add(new_user)
        db.session.commit()
        try:
            faiss_engine.build_index(User.query.filter_by(tenant_id=t_id).all())
        except Exception as e:
            print(f"[FAISS] Index rebuild skipped: {e}")
        
        # Send welcome email to newly added user
        tenant = Tenant.query.get(t_id)
        tenant_name = tenant.name if tenant else 'SmartLift'
        
        qr_image_path = None
        if email:
            try:
                # Generate a long-term QR pass for the enrolled user
                qr_hash = f"SL-{uuid.uuid4().hex}"
                valid_until = datetime.utcnow() + timedelta(days=365) # 1 year validity for internal users
                qr_image_path = synthesize_custom_qr(qr_hash, name, access_role, valid_until, enrollment_id)
                
                new_pass = VisitorPass(
                    visitor_name=name,
                    purpose="User QR Backup",
                    qr_hash=qr_hash,
                    qr_image_path=qr_image_path,
                    allowed_floors=floors,
                    valid_until=valid_until,
                    tenant_id=t_id,
                    created_by_admin_id=session.get('admin_id', 1)
                )
                db.session.add(new_pass)
                db.session.commit()
            except Exception as e:
                print(f"[QR GEN ERROR] Could not generate QR for user {name}: {e}")
                
            send_welcome_email(email, name, access_role, floors, tenant_name, qr_path=qr_image_path)
        
        flash(f"User {name} enrolled successfully!", "success")
        return redirect(url_for('manage_users'))
        
    users = User.query.filter_by(tenant_id=t_id).all()
    return render_template('users.html', users=users)

# --------------------------
# USER API (JSON for modals)
# --------------------------
@app.route('/api/user/<int:user_id>')
def api_get_user(user_id):
    if 'admin_id' not in session: return {'error': 'Unauthorized'}, 401
    t_id = session['tenant_id']
    u = User.query.filter_by(user_id=user_id, tenant_id=t_id).first()
    if not u: return {'error': 'Not found'}, 404
    return {
        'user_id': u.user_id,
        'name': u.name,
        'email': u.email or '',
        'role': u.access_type,
        'floors': u.allowed_floors,
        'enrollment_id': u.enrollment_id or '',
        'department': u.department or '',
        'course': u.course or '',
        'batch': u.batch or '',
        'start_time': u.access_start_time.strftime('%H:%M') if u.access_start_time else '',
        'end_time': u.access_end_time.strftime('%H:%M') if u.access_end_time else '',
        'face_path': u.Face_encoding or ''
    }

# --------------------------
# EDIT USER
# --------------------------
@app.route('/edit_user/<int:user_id>', methods=['POST'])
def edit_user(user_id):
    if 'admin_id' not in session: return redirect(url_for('login'))
    t_id = session['tenant_id']
    u = User.query.filter_by(user_id=user_id, tenant_id=t_id).first()
    if not u:
        flash("User not found.", "danger")
        return redirect(url_for('manage_users'))
    
    u.name = request.form.get('name', u.name)
    u.email = request.form.get('email', u.email)
    u.access_type = request.form.get('access_role', u.access_type)
    u.allowed_floors = request.form.get('allowed_floors', u.allowed_floors)
    # Prevent unique constraint errors on edit
    if u.enrollment_id != request.form.get('enrollment_id'):
        new_enroll_id = request.form.get('enrollment_id')
        if new_enroll_id:
            dup = User.query.filter_by(tenant_id=t_id, enrollment_id=new_enroll_id).first()
            if dup:
                flash(f"Cannot update: Enrollment ID '{new_enroll_id}' belongs to {dup.name}.", "danger")
                return redirect(url_for('manage_users'))
    
    u.enrollment_id = request.form.get('enrollment_id') or None
    u.department = request.form.get('department') or None
    u.course = request.form.get('course') or None
    u.batch = request.form.get('batch') or None
    
    start_time_str = request.form.get('start_time')
    end_time_str = request.form.get('end_time')
    u.access_start_time = datetime.strptime(start_time_str, '%H:%M').time() if start_time_str else None
    u.access_end_time = datetime.strptime(end_time_str, '%H:%M').time() if end_time_str else None
    
    # Handle face photo update
    file = request.files.get('face_image')
    if file and file.filename != '':
        filename = f"t{t_id}_{u.name.replace(' ', '_')}.jpg"
        filepath = os.path.join('static', 'registered_faces', filename)
        file.save(filepath)
        u.Face_encoding = filepath
        try:
            from hardware.camera_face_recognition import VisionEngine
            import json
            v = VisionEngine()
            vec = v.extract_vector(filepath)
            if vec is not None:
                u.face_vector = json.dumps(vec if isinstance(vec, list) else vec.tolist())
        except Exception as e:
            print(f"Face update error: {e}")
    
    db.session.commit()
    try:
        faiss_engine.build_index(User.query.filter_by(tenant_id=t_id).all())
    except Exception as e:
        print(f"[FAISS] Index rebuild skipped: {e}")
        
    # Send update email
    if u.email:
        tenant = Tenant.query.get(t_id)
        tenant_name = tenant.name if tenant else 'SmartLift'
        send_update_email(u.email, u.name, u.access_type, u.allowed_floors, tenant_name)
        
    flash(f"User {u.name} updated successfully! Email notification sent.", "success")
    return redirect(url_for('manage_users'))

# --------------------------
# DELETE USER
# --------------------------
@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if 'admin_id' not in session: return redirect(url_for('login'))
    t_id = session['tenant_id']
    u = User.query.filter_by(user_id=user_id, tenant_id=t_id).first()
    if not u:
        flash("User not found.", "danger")
        return redirect(url_for('manage_users'))
    
    user_name = u.name
    
    # Delete face image file if exists
    if u.Face_encoding and os.path.exists(u.Face_encoding):
        try:
            os.remove(u.Face_encoding)
        except OSError as e:
            print(f"Failed to delete face image for user {u.user_id}: {e}")
    
    # Delete associated access logs
    AccessLog.query.filter_by(User_id=user_id).delete()
    
    # Delete the user
    db.session.delete(u)
    db.session.commit()
    flash(f"User {user_name} and all associated records permanently deleted.", "danger")
    return redirect(url_for('manage_users'))

@app.route('/visitor_passes', methods=['GET', 'POST'])
def manage_visitor_passes():
    if 'admin_id' not in session: return redirect(url_for('login'))
    t_id = session['tenant_id']
    admin_id = session['admin_id']
    
    if request.method == 'POST':
        role = request.form.get('role', 'Guest')
        name = request.form.get('visitor_name')
        purpose = request.form.get('purpose')
        floors = request.form.get('allowed_floors')
        email = request.form.get('email')
        valid_until_str = request.form.get('valid_until') # Expected format YYYY-MM-DDTHH:MM
        
        qr_hash = f"SL-{uuid.uuid4().hex}"
        try:
            valid_until = datetime.strptime(valid_until_str, '%Y-%m-%dT%H:%M')
        except:
            valid_until = datetime.utcnow() + timedelta(hours=2) # safety fallback
        
        # Phase 10 PIL Canvas Instantiation
        filepath = synthesize_custom_qr(qr_hash, name, role, valid_until)
        
        if email:
            dispatch_email(email, name, filepath)
        
        new_pass = VisitorPass(
            visitor_name=f"[{role}] {name}", purpose=purpose, qr_hash=qr_hash,
            qr_image_path=filepath, allowed_floors=floors,
            valid_until=valid_until, tenant_id=t_id,
            created_by_admin_id=admin_id
        )
        db.session.add(new_pass)
        db.session.commit()
        flash(f"Temporary {role} Pass deployed manually for {name}.", "success")
        return redirect(url_for('manage_visitor_passes'))
        
    # Phase 4 Auto-expire logic (basic sweep of DB)
    now = datetime.utcnow()
    VisitorPass.query.filter(VisitorPass.valid_until < now, VisitorPass.status == 'Active').update({'status':'Expired'})
    db.session.commit()
    
    passes = VisitorPass.query.filter_by(tenant_id=t_id).order_by(VisitorPass.valid_until.desc()).all()
    return render_template('visitor_passes.html', passes=passes)

@app.route('/revoke_pass/<int:pass_id>', methods=['POST'])
def revoke_pass(pass_id):
    if 'admin_id' not in session: return redirect(url_for('login'))
    t_id = session['tenant_id']
    p = VisitorPass.query.get(pass_id)
    if p and p.tenant_id == t_id:
        p.status = 'Revoked'
        db.session.commit()
        flash(f"Access rights fundamentally severed for {p.visitor_name}.", "danger")
    return redirect(url_for('manage_visitor_passes'))

@app.route('/delete_pass/<int:pass_id>', methods=['POST'])
def delete_pass(pass_id):
    if 'admin_id' not in session: return redirect(url_for('login'))
    t_id = session['tenant_id']
    p = VisitorPass.query.get(pass_id)
    if p and p.tenant_id == t_id:
        db.session.delete(p)
        db.session.commit()
        flash(f"SQL Identity Record critically erased from existence.", "danger")
    return redirect(url_for('manage_visitor_passes'))

@app.route('/hardware')
def hardware():
    if 'admin_id' not in session: return redirect(url_for('login'))
    lifts = Lift.query.filter_by(tenant_id=session['tenant_id']).all()
    return render_template('hardware.html', lifts=lifts)

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if 'admin_id' not in session: return redirect(url_for('login'))
    t_id = session['tenant_id']
    tenant = Tenant.query.get(t_id)
    admin = Admin.query.get(session['admin_id'])
    
    if request.method == 'POST':
        new_pass = request.form.get('new_password')
        if new_pass:
            admin.password = generate_password_hash(new_pass, method='pbkdf2:sha256')
            db.session.commit()
            flash("Administrator security token successfully rotated. Use this password upon next authorization.", "success")
            
    return render_template('settings.html', tenant=tenant, admin=admin)

@app.route('/api/panic/<int:lift_id>', methods=['POST'])
def api_panic(lift_id):
    if 'admin_id' not in session:
        return {'status': 'unauthorized'}, 401

    t_id = session['tenant_id']
    lift = Lift.query.filter_by(Lift_id=lift_id, tenant_id=t_id).first()
    if not lift:
        return {'status': 'error'}, 404

    ev = EmergencyEvent(tenant_id=t_id, lift_id=lift_id)
    db.session.add(ev)
    db.session.commit()
    return {'status': 'alert_logged'}, 200

@app.route('/emergency')
def emergency_dashboard():
    if 'admin_id' not in session: return redirect(url_for('login'))
    t_id = session['tenant_id']
    events = EmergencyEvent.query.filter_by(tenant_id=t_id).order_by(EmergencyEvent.timestamp.desc()).all()
    lifts = Lift.query.filter_by(tenant_id=t_id).order_by(Lift.Lift_id.asc()).all()
    default_lift_id = lifts[0].Lift_id if lifts else None
    
    # Phase 8: Forensic Suspect Mapping
    forensics = []
    for e in events:
        # Find logs +/- 5 minutes
        start_bound = e.timestamp - timedelta(minutes=5)
        end_bound = e.timestamp + timedelta(minutes=5)
        suspects = _tenant_accesslog_query(t_id).filter(
            AccessLog.timestlap >= start_bound,
            AccessLog.timestlap <= end_bound
        ).all()
        forensics.append({'event': e, 'suspects': suspects})
        
    return render_template('emergency.html', forensics=forensics, lifts=lifts, default_lift_id=default_lift_id)

@app.route('/request_access', methods=['GET', 'POST'])
def public_request():
    if request.method == 'POST':
        tenant_id = request.form.get('tenant_id')
        name = request.form.get('name')
        email = request.form.get('email')
        role = request.form.get('role')
        enrollment_id = request.form.get('enrollment_id')
        department = request.form.get('department')
        reason = request.form.get('reason')
        hours = request.form.get('requested_duration_hours', 24)
        floors = request.form.get('floors', '0')
        
        # Verify enrollment_id duplicate externally if requested
        if enrollment_id:
            existing = User.query.filter_by(tenant_id=tenant_id, enrollment_id=enrollment_id).first()
            if existing and existing.name.lower() != name.lower():
                return f"Constraint Error: Enrollment ID officially registered to distinct identity ({existing.name}). Return and correct parameters.", 403
        
        req = AccessRequest(
            tenant_id=tenant_id, name=name, email=email, role=role, enrollment_id=enrollment_id,
            department=department, reason=reason, requested_duration_hours=int(hours), floors=floors
        )
        db.session.add(req)
        db.session.commit()
        return render_template('request_success.html')
        
    tenants = Tenant.query.filter_by(subscription_status='Active').all()
    return render_template('public_request.html', tenants=tenants)

@app.route('/approval_queue')
def approval_queue():
    if 'admin_id' not in session: return redirect(url_for('login'))
    t_id = session['tenant_id']
    reqs = AccessRequest.query.filter_by(tenant_id=t_id, status='Pending').order_by(AccessRequest.created_at.asc()).all()
    reviewed_reqs = AccessRequest.query.filter(
        AccessRequest.tenant_id == t_id,
        AccessRequest.status != 'Pending'
    ).order_by(AccessRequest.created_at.desc()).limit(10).all()
    return render_template('approval_queue.html', reqs=reqs, reviewed_reqs=reviewed_reqs)


def _issue_visitor_pass_from_request(access_request, tenant_id, admin_id):
    qr_hash = f"SL-{uuid.uuid4().hex}"
    valid_until = datetime.utcnow() + timedelta(hours=access_request.requested_duration_hours)
    filepath = synthesize_custom_qr(qr_hash, access_request.name, access_request.role, valid_until, access_request.enrollment_id)
    
    # Send approval email via Resend (mail.emitra.dev)
    tenant = Tenant.query.get(tenant_id)
    tenant_name = tenant.name if tenant else 'SmartLift'
    dispatched = send_approval_email(
        access_request.email,
        access_request.name,
        access_request.role,
        access_request.floors,
        valid_until,
        tenant_name,
        qr_path=filepath
    )
    
    new_pass = VisitorPass(
        visitor_name=f"[{access_request.role} Approved] {access_request.name}",
        purpose=access_request.reason,
        qr_hash=qr_hash,
        qr_image_path=filepath,
        allowed_floors=access_request.floors,
        valid_until=valid_until,
        tenant_id=tenant_id,
        created_by_admin_id=admin_id
    )
    db.session.add(new_pass)
    return dispatched


@app.route('/review_request/<int:req_id>', methods=['POST'])
def review_request(req_id):
    if 'admin_id' not in session: return redirect(url_for('login'))
    t_id = session['tenant_id']
    admin_id = session['admin_id']
    action = (request.form.get('action') or '').strip().lower()
    admin_note = (request.form.get('admin_note') or '').strip()

    r = AccessRequest.query.get(req_id)
    if not r or r.tenant_id != t_id:
        flash("Request not found.", "danger")
        return redirect(url_for('approval_queue'))
    if r.status != 'Pending':
        flash(f"Request for {r.name} is already {r.status}.", "danger")
        return redirect(url_for('approval_queue'))

    if action == 'approve':
        r.status = 'Approved'
        r.reviewed_at = datetime.utcnow()
        r.reviewed_by_admin_id = admin_id
        r.admin_decision_note = admin_note or None
        dispatched = _issue_visitor_pass_from_request(r, t_id, admin_id)
        db.session.commit()
        if dispatched:
            flash(f"Approved {r.name}. Visitor pass generated and emailed.", "success")
        else:
            flash(f"Approved {r.name}. Visitor pass generated, but email dispatch is not configured.", "success")
    elif action == 'reject':
        r.status = 'Rejected'
        r.reviewed_at = datetime.utcnow()
        r.reviewed_by_admin_id = admin_id
        r.admin_decision_note = admin_note or None
        db.session.commit()
        flash(f"Rejected request for {r.name}.", "danger")
    else:
        flash("Invalid review action.", "danger")

    return redirect(url_for('approval_queue'))


@app.route('/approve_request/<int:req_id>', methods=['POST'])
def approve_request(req_id):
    # Backward-compatible endpoint for older templates/forms.
    if 'admin_id' not in session: return redirect(url_for('login'))
    t_id = session['tenant_id']
    admin_id = session['admin_id']
    r = AccessRequest.query.get(req_id)
    if r and r.tenant_id == t_id and r.status == 'Pending':
        r.status = 'Approved'
        r.reviewed_at = datetime.utcnow()
        r.reviewed_by_admin_id = admin_id
        r.admin_decision_note = (request.form.get('admin_note') or '').strip() or None
        dispatched = _issue_visitor_pass_from_request(r, t_id, admin_id)
        db.session.commit()
        if dispatched:
            flash(f"Public request approved for {r.name}. QR code automatically synthesized and routed to Visitor Passes.", "success")
        else:
            flash(f"Approved {r.name}. QR code generated, but email dispatch is not configured.", "success")
    return redirect(url_for('approval_queue'))

@app.route('/verify')
def verify_scanner():
    """ Renders the Edge Node Facial Scanner """
    if 'admin_id' not in session: return redirect(url_for('login'))
    session.pop('verified_access', None)
    t_id = session['tenant_id']
    _sync_local_edge_tenant_binding(t_id)
    users = User.query.filter_by(tenant_id=t_id).all()
    return render_template('verify_scanner.html', users=users)


@app.route('/lift_control')
def lift_control():
    if 'admin_id' not in session: return redirect(url_for('login'))
    verified = _current_verified_access()
    if not verified:
        flash("Verify identity first at the scanner terminal.", "danger")
        return redirect(url_for('verify_scanner'))
    return render_template(
        'lift_control.html',
        identity_name=verified.get('name', 'Verified User'),
        identity_role=verified.get('role', 'User'),
        allowed_floors=verified.get('allowed_floors', [0]),
    )


@app.route('/api/lift_request', methods=['POST'])
def api_lift_request():
    if 'admin_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    verified = _current_verified_access()
    if not verified:
        return jsonify({'status': 'error', 'message': 'Verification session expired. Please verify again.'}), 400

    payload = request.get_json(silent=True) or {}
    floor_raw = payload.get('floor')
    voice_command = payload.get('voice_command', '')

    target_floor = None
    if floor_raw is not None and str(floor_raw).strip() != '':
        try:
            target_floor = int(str(floor_raw).strip())
        except ValueError:
            target_floor = None
    if target_floor is None and voice_command:
        target_floor = _extract_floor_number_from_text(voice_command)

    if target_floor is None:
        return jsonify({'status': 'failed', 'message': 'No valid floor detected. Choose a floor or use a clearer voice command.'}), 400

    allowed_floors = [int(f) for f in verified.get('allowed_floors', [0])]
    lift_id = int(verified.get('lift_id', _get_tenant_primary_lift_id(session['tenant_id'])))
    user_id = verified.get('user_id')
    identity_name = verified.get('name', 'Guest')

    if target_floor not in allowed_floors:
        denied_status = (
            f"QR Guest [{identity_name}] - Denied - Unauthorized Floor"
            if user_id is None else "Denied - Unauthorized Floor (Web Panel)"
        )
        _create_floor_request_and_log(user_id, target_floor, denied_status, lift_id)
        db.session.commit()
        return jsonify({'status': 'failed', 'message': f'Access denied for floor {target_floor}.'}), 403

    granted_status = (
        f"QR Guest [{identity_name}] - Granted - Web Panel"
        if user_id is None else "Granted - Web Panel"
    )
    _create_floor_request_and_log(user_id, target_floor, granted_status, lift_id)
    db.session.commit()
    print(f"[WEB DISPATCH] Lift #{lift_id} dispatched to floor {target_floor} for {identity_name}")

    session.pop('verified_access', None)
    return jsonify({
        'status': 'success',
        'message': f'Lift dispatched to floor {target_floor}.',
        'next_url': url_for('verify_scanner'),
        'floor': target_floor
    }), 200

# --------------------------
# FAISS BIOMETRIC API
# --------------------------
from software.faiss_engine import FaissBiometricEngine
faiss_engine = FaissBiometricEngine(model_name="Facenet")
faiss_index_built = False
faiss_index_tenant_id = None

@app.route('/api/faiss_verify', methods=['POST'])
def api_faiss_verify():
    global faiss_index_built, faiss_index_tenant_id
    if 'admin_id' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    t_id = session['tenant_id']
    lift_id = _get_tenant_primary_lift_id(t_id)

    # Lazy load the FAISS index and rebuild when tenant context changes.
    if (not faiss_index_built) or (faiss_index_tenant_id != t_id):
        print("[FAISS] Initializing Vector Index...")
        users = User.query.filter(
            User.tenant_id == t_id,
            User.Face_encoding != None,  # noqa: E711
            User.Face_encoding != ''
        ).all()
        faiss_engine.build_index(users)
        faiss_index_built = True
        faiss_index_tenant_id = t_id

    tmp_path = None
    try:
        data = request.get_json(silent=True) or {}
        image_data = data.get('image')
        if not image_data or "," not in image_data:
            return jsonify({"status": "error", "message": "Missing image payload"}), 400

        import base64
        import tempfile
        import cv2
        _header, encoded = image_data.split(",", 1)
        img_bytes = base64.b64decode(encoded)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(img_bytes)
            tmp_path = tmp.name

        img = cv2.imread(tmp_path)
        data_qr = None
        if img is not None:
            detector = cv2.QRCodeDetector()
            try:
                data_qr, bbox, _ = detector.detectAndDecode(img)
            except Exception as e:
                print(f"[QR Decode Error] {e}")
        
        if data_qr:
            visitor = VisitorPass.query.filter_by(qr_hash=data_qr, tenant_id=t_id).first()
            if visitor and visitor.status == "Active" and visitor.valid_until > datetime.utcnow():
                allowed_floors = _parse_floor_list(visitor.allowed_floors)
                session['verified_access'] = {
                    'tenant_id': t_id,
                    'lift_id': lift_id,
                    'user_id': None,
                    'name': visitor.visitor_name,
                    'role': 'Visitor',
                    'allowed_floors': allowed_floors,
                    'verified_at': datetime.utcnow().isoformat()
                }

                return jsonify({
                    "status": "success",
                    "user": visitor.visitor_name,
                    "floor": visitor.allowed_floors,
                    "role": "Visitor",
                    "msg": "Verified. Select floor on lift panel.",
                    "next_url": url_for('lift_control')
                })
            _create_floor_request_and_log(None, 0, "Denied - Invalid QR", lift_id)
            db.session.commit()
            return jsonify({"status": "failed", "message": "Invalid/Expired QR"})
                
        user, msg = faiss_engine.verify_subject(tmp_path) # Uses default 0.75 threshold for normalized vectors

        if user and user.tenant_id == t_id:
            allowed_floors = _parse_floor_list(user.allowed_floors)
            session['verified_access'] = {
                'tenant_id': t_id,
                'lift_id': lift_id,
                'user_id': user.user_id,
                'name': user.name,
                'role': user.access_type,
                'allowed_floors': allowed_floors,
                'verified_at': datetime.utcnow().isoformat()
            }
            
            return jsonify({
                "status": "success", 
                "user": user.name, 
                "floor": user.allowed_floors, 
                "role": user.access_type,
                "msg": "Verified. Select floor on lift panel.",
                "next_url": url_for('lift_control')
            })
        _create_floor_request_and_log(None, 0, "Denied - Face Unknown", lift_id)
        db.session.commit()
        return jsonify({"status": "failed", "message": msg})
    except Exception as e:
        print(f"[FAISS ERROR] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, port=8000, host='0.0.0.0')

