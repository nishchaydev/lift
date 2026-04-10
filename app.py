from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from models import db, SuperAdmin, Admin, Tenant, User, Lift, AccessLog, VisitorPass, EmergencyEvent, AccessRequest
from werkzeug.security import generate_password_hash, check_password_hash
import os
import uuid
import qrcode
from datetime import datetime, timedelta
import PIL.Image as PIL_Image
from PIL import ImageDraw

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

def dispatch_email(recipient_email, recipient_name, qr_path):
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.image import MIMEImage
    import os
    
    # =========================================================
    # PHASE 11 SMTP: YOU MUST FILL THESE OUT FOR LIVE EMAILS!
    # Generate an "App Password" from your Google Account settings 
    # Do NOT put your normal Google password here.
    # =========================================================
    SENDER_EMAIL = "smartlift.notifications@gmail.com" 
    SENDER_PASSWORD = "sdda ergt iwen hnxj"
    
    try:
        msg = MIMEMultipart()
        msg['Subject'] = 'SmartLift: Institutional Lift Access Approved'
        msg['From'] = f"SmartLift Security <{SENDER_EMAIL}>"
        msg['To'] = recipient_email
        
        email_body = f"Hello {recipient_name},\n\nYour Temporary Lift Pass request has been manually Approved by your local Administration.\n\nThe customized QR Cryptographic Identity Token is attached to this email. You may scan this barcode directly at any Edge Node scanner on-site.\n\nRegards,\nSmartLift Backend Service Engine"
        body = MIMEText(email_body)
        msg.attach(body)
        
        with open(qr_path, 'rb') as f:
            img = MIMEImage(f.read())
            img.add_header('Content-Disposition', 'attachment', filename=os.path.basename(qr_path))
            msg.attach(img)
            
        print(f"--> [SMTP ENGINE] Connecting to TLS Gateway smtp.gmail.com:587...")
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        print(f"--> [SMTP 250 OK] Successfully relayed payload to {recipient_email}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("\n[SMTP AUTH ERROR] Authentication failed! Did you remember to use a 16-digit Google App Password?")
        return False
    except Exception as e:
        print(f"\n[SMTP FATAL ERROR]: {e}")
        return False


app = Flask(__name__)
app.config['SECRET_KEY'] = 'premium-saas-jwt-super-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smartlift_saas.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

os.makedirs('static/registered_faces', exist_ok=True)

db.init_app(app)

with app.app_context():
    db.create_all()
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
    return render_template('superadmin_dashboard.html', tenants=tenants, total_tenants=len(tenants))

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

@app.route('/superadmin/toggle_tenant/<int:id>')
def toggle_tenant(id):
    if 'superadmin_id' not in session: return redirect(url_for('login'))
    tenant = Tenant.query.get(id)
    if tenant:
        tenant.subscription_status = 'Suspended' if tenant.subscription_status == 'Active' else 'Active'
        db.session.commit()
        flash(f"Tenant '{tenant.name}' status changed to {tenant.subscription_status}", "success")
    return redirect(url_for('superadmin_dashboard'))

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
    
    # Phase 7: Functional SQLite Date Filtering
    filter_date = request.args.get('date')
    query = AccessLog.query.join(User, AccessLog.User_id == User.user_id, isouter=True).filter(
        db.or_(User.tenant_id == t_id, AccessLog.status.like('%Guest%'))
    )
    if filter_date:
        try:
            target_date = datetime.strptime(filter_date, '%Y-%m-%d').date()
            query = query.filter(db.func.date(AccessLog.timestlap) == target_date)
        except: pass
        
    logs = query.order_by(AccessLog.timestlap.desc()).limit(150).all()
    
    # Phase 7: Real Data Mapping for Identity Distributions
    dist = {'Operator': 0, 'Faculty': 0, 'Disability': 0, 'Temporary': 0, 'Guests': 0, 'Alerts': 0}
    for log in logs:
        if 'Alert' in log.status or 'Denied' in log.status or 'Rejected' in log.status:
            dist['Alerts'] += 1
        elif log.user:
            role = log.user.access_type
            if role in dist: dist[role] += 1
            else: dist['Temporary'] += 1
        elif 'Guest' in log.status:
            dist['Guests'] += 1
    chart_data = [dist['Operator'], dist['Faculty'], dist['Disability'], dist['Temporary'], dist['Guests'], dist['Alerts']]
    
    peak_hour = "N/A"
    try:
        from collections import Counter
        hours = [log.timestlap.hour for log in logs]
        if hours: peak_hour = f"{Counter(hours).most_common(1)[0][0]}:00"
    except: pass
    
    # ============================================
    # ADVANCED ANALYTICS: 7-Day Access Trend
    # ============================================
    trend_labels = []
    trend_values = []
    try:
        for i in range(6, -1, -1):
            day = datetime.utcnow().date() - timedelta(days=i)
            day_name = day.strftime('%a %d')
            trend_labels.append(day_name)
            count = AccessLog.query.join(User, AccessLog.User_id == User.user_id, isouter=True).filter(
                db.or_(User.tenant_id == t_id, AccessLog.status.like('%Guest%')),
                db.func.date(AccessLog.timestlap) == day
            ).count()
            trend_values.append(count)
    except:
        trend_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        trend_values = [0, 0, 0, 0, 0, 0, 0]

    # ============================================
    # ADVANCED ANALYTICS: Floor Usage Distribution
    # ============================================
    floor_labels = []
    floor_values = []
    try:
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
    except:
        floor_labels = ['Floor 0', 'Floor 1', 'Floor 2']
        floor_values = [0, 0, 0]
    
    return render_template('dashboard.html', tenant=tenant, total_users=len(users), logs=logs, 
                           active_lifts=active_lifts, peak_hour=peak_hour, chart_data=chart_data,
                           trend_labels=trend_labels, trend_values=trend_values,
                           floor_labels=floor_labels, floor_values=floor_values)

@app.route('/export_logs')
def export_logs():
    if 'admin_id' not in session: return redirect(url_for('login'))
    t_id = session['tenant_id']
    from flask import Response
    
    logs = AccessLog.query.join(User, AccessLog.User_id == User.user_id, isouter=True).filter(
        db.or_(User.tenant_id == t_id, AccessLog.status.like('%Guest%'))
    ).order_by(AccessLog.timestlap.desc()).all()
    
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
                from camera_face_recognition import VisionEngine
                import json
                v = VisionEngine()
                vec = v.extract_vector(filepath)
                if vec is not None:
                    face_vector_cache = json.dumps(vec if isinstance(vec, list) else vec.tolist())
                else:
                    flash("AI warning: No clear face detected in the photo. Please re-upload.", "danger")
            except Exception as e:
                print(f"Extraction Error: {e}")
                
        if enrollment_id:
            existing = User.query.filter_by(tenant_id=t_id, enrollment_id=enrollment_id).first()
            if existing:
                flash(f"Transaction Blocked: Enrollment ID '{enrollment_id}' officially belongs to {existing.name}.", "danger")
                return redirect(url_for('manage_users'))
            
        new_user = User(
            name=name, email=email, access_type=access_role, allowed_floors=floors, 
            Face_encoding=filepath, face_vector=face_vector_cache, 
            access_start_time=start_time, access_end_time=end_time, tenant_id=t_id,
            enrollment_id=enrollment_id, department=department, course=course, batch=batch
        )
        db.session.add(new_user)
        db.session.commit()
        faiss_engine.build_index(User.query.all())
        flash(f"User {name} enrolled successfully and Edge AI updated!", "success")
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
            from camera_face_recognition import VisionEngine
            import json
            v = VisionEngine()
            vec = v.extract_vector(filepath)
            if vec is not None:
                u.face_vector = json.dumps(vec if isinstance(vec, list) else vec.tolist())
        except Exception as e:
            print(f"Face update error: {e}")
    
    db.session.commit()
    faiss_engine.build_index(User.query.all())
    flash(f"User {u.name} updated successfully and Edge AI resynced!", "success")
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
        try: os.remove(u.Face_encoding)
        except: pass
    
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

@app.route('/revoke_pass/<int:pass_id>')
def revoke_pass(pass_id):
    if 'admin_id' not in session: return redirect(url_for('login'))
    t_id = session['tenant_id']
    p = VisitorPass.query.get(pass_id)
    if p and p.tenant_id == t_id:
        p.status = 'Revoked'
        db.session.commit()
        flash(f"Access rights fundamentally severed for {p.visitor_name}.", "danger")
    return redirect(url_for('manage_visitor_passes'))

@app.route('/delete_pass/<int:pass_id>')
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
    # Simulated Edge Node hardware panic trigger
    lift = Lift.query.get(lift_id)
    if lift:
        ev = EmergencyEvent(tenant_id=lift.tenant_id, lift_id=lift_id)
        db.session.add(ev)
        db.session.commit()
        return {'status': 'alert_logged'}, 200
    return {'status': 'error'}, 404

@app.route('/emergency')
def emergency_dashboard():
    if 'admin_id' not in session: return redirect(url_for('login'))
    t_id = session['tenant_id']
    events = EmergencyEvent.query.filter_by(tenant_id=t_id).order_by(EmergencyEvent.timestamp.desc()).all()
    
    # Phase 8: Forensic Suspect Mapping
    forensics = []
    for e in events:
        # Find logs +/- 5 minutes
        start_bound = e.timestamp - timedelta(minutes=5)
        end_bound = e.timestamp + timedelta(minutes=5)
        suspects = AccessLog.query.join(User, AccessLog.User_id == User.user_id, isouter=True).filter(
            db.or_(User.tenant_id == t_id, AccessLog.status.like('%Guest%')),
            AccessLog.timestlap >= start_bound,
            AccessLog.timestlap <= end_bound
        ).all()
        forensics.append({'event': e, 'suspects': suspects})
        
    return render_template('emergency.html', forensics=forensics)

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
    reqs = AccessRequest.query.filter_by(tenant_id=t_id, status='Pending').all()
    return render_template('approval_queue.html', reqs=reqs)

@app.route('/approve_request/<int:req_id>')
def approve_request(req_id):
    if 'admin_id' not in session: return redirect(url_for('login'))
    t_id = session['tenant_id']
    r = AccessRequest.query.get(req_id)
    if r and r.tenant_id == t_id and r.status == 'Pending':
        r.status = 'Approved'
        # Generate physical QR via Phase 10 PIL Graphic Engine
        qr_hash = f"SL-{uuid.uuid4().hex}"
        valid_until = datetime.utcnow() + timedelta(hours=r.requested_duration_hours)
        
        filepath = synthesize_custom_qr(qr_hash, r.name, r.role, valid_until, r.enrollment_id)
        
        # Phase 10: Launch SMTP Sequence
        dispatch_email(r.email, r.name, filepath)
        
        new_pass = VisitorPass(
            visitor_name=f"[{r.role} Approved] {r.name}", purpose=r.reason, qr_hash=qr_hash,
            qr_image_path=filepath, allowed_floors=r.floors, valid_until=valid_until,
            tenant_id=t_id, created_by_admin_id=session['admin_id']
        )
        db.session.add(new_pass)
        db.session.commit()
        flash(f"Public request approved for {r.name}. QR code automatically synthesized and routed to Visitor Passes.", "success")
    return redirect(url_for('approval_queue'))

@app.route('/verify')
def verify_scanner():
    """ Renders the Edge Node Facial Scanner """
    users = User.query.all()
    return render_template('verify_scanner.html', users=users)

# --------------------------
# FAISS BIOMETRIC API
# --------------------------
from faiss_engine import FaissBiometricEngine
faiss_engine = FaissBiometricEngine(model_name="Facenet")
faiss_index_built = False

@app.route('/api/faiss_verify', methods=['POST'])
def api_faiss_verify():
    global faiss_index_built
    
    # Lazy load the FAISS index on first scan (keeps server boot fast)
    if not faiss_index_built:
        print("[FAISS] Initializing Vector Index...")
        with app.app_context():
            users = User.query.filter(User.Face_encoding != None, User.Face_encoding != '').all()
            faiss_engine.build_index(users)
            faiss_index_built = True

    try:
        data = request.get_json()
        image_data = data.get('image')
        
        import base64
        import tempfile
        header, encoded = image_data.split(",", 1)
        img_bytes = base64.b64decode(encoded)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(img_bytes)
            tmp_path = tmp.name

        import cv2
        img = cv2.imread(tmp_path)
        data_qr = None
        if img is not None:
            detector = cv2.QRCodeDetector()
            try:
                data_qr, bbox, _ = detector.detectAndDecode(img)
            except Exception as e:
                print(f"[QR Decode Error] {e}")
        
        if data_qr:
            visitor = VisitorPass.query.filter_by(qr_hash=data_qr).first()
            if visitor and visitor.status == "Active" and visitor.valid_until > datetime.utcnow():
                try: floor = int(visitor.allowed_floors.split(',')[0])
                except: floor = 0
                log = AccessLog(User_id=None, Floor_selection=floor, status="Granted - Guest QR")
                db.session.add(log)
                db.session.commit()
                
                print(f"[IoT MQTT] Physical Dispatch Sent: Lift to Floor {visitor.allowed_floors} for Guest: {visitor.visitor_name}")
                
                try: os.remove(tmp_path)
                except: pass
                
                return jsonify({
                    "status": "success",
                    "user": visitor.visitor_name,
                    "floor": visitor.allowed_floors,
                    "role": "Visitor",
                    "msg": "QR Passed"
                })
            else:
                log = AccessLog(User_id=None, Floor_selection=0, status="Denied - Invalid QR")
                db.session.add(log)
                db.session.commit()
                try: os.remove(tmp_path)
                except: pass
                
                return jsonify({"status": "failed", "message": "Invalid/Expired QR"})
                
        user, msg = faiss_engine.verify_subject(tmp_path) # Uses default 0.75 threshold for normalized vectors
        
        import os
        try: os.remove(tmp_path)
        except: pass
        
        if user:
            try: floor = int(user.allowed_floors.split(',')[0])
            except: floor = 0
            log = AccessLog(User_id=user.user_id, Floor_selection=floor, status="Granted")
            db.session.add(log)
            db.session.commit()
            
            print(f"[IoT MQTT] Physical Dispatch Sent: Lift to Floor {user.allowed_floors} for User: {user.name}")
            
            return jsonify({
                "status": "success", 
                "user": user.name, 
                "floor": user.allowed_floors, 
                "role": user.access_type,
                "msg": msg
            })
        else:
            log = AccessLog(User_id=None, Floor_selection=0, status=f"Denied")
            db.session.add(log)
            db.session.commit()
            return jsonify({"status": "failed", "message": msg})
    except Exception as e:
        print(f"[FAISS ERROR] {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, port=8000, host='0.0.0.0')
