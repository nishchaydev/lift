"""
Demo Data Seeder for SmartLift Competition
Generates realistic users, access logs, and visitor passes
"""
import random
from datetime import datetime, timedelta
from app import app, db
from models import Tenant, User, AccessLog, FloorRequest, VisitorPass, Lift
from werkzeug.security import generate_password_hash
import uuid

# Sample data
DEPARTMENTS = ['Computer Science', 'Electrical Engineering', 'Mechanical Engineering', 'Civil Engineering', 
               'Business Administration', 'Mathematics', 'Physics', 'Chemistry', 'Biology', 'Architecture']

COURSES = ['B.Tech', 'M.Tech', 'PhD', 'MBA', 'B.Sc', 'M.Sc']

BATCHES = ['2021', '2022', '2023', '2024']

FACULTY_NAMES = [
    'Dr. Rajesh Kumar', 'Prof. Anjali Sharma', 'Dr. Vikram Singh', 'Prof. Priya Patel',
    'Dr. Amit Verma', 'Prof. Sneha Gupta', 'Dr. Rahul Mehta', 'Prof. Kavita Reddy',
    'Dr. Arjun Nair', 'Prof. Deepika Joshi', 'Dr. Sanjay Desai', 'Prof. Neha Kapoor'
]

STUDENT_FIRST_NAMES = [
    'Aarav', 'Vivaan', 'Aditya', 'Vihaan', 'Arjun', 'Sai', 'Krishna', 'Shaurya',
    'Aarohi', 'Ananya', 'Diya', 'Ishita', 'Kavya', 'Priya', 'Riya', 'Sara',
    'Rohan', 'Aryan', 'Kartik', 'Harsh', 'Tanvi', 'Meera', 'Pooja', 'Sanya'
]

STUDENT_LAST_NAMES = [
    'Sharma', 'Patel', 'Kumar', 'Singh', 'Gupta', 'Reddy', 'Verma', 'Mehta',
    'Joshi', 'Nair', 'Desai', 'Shah', 'Rao', 'Pillai', 'Agarwal', 'Kapoor'
]

OPERATOR_NAMES = [
    'Ravi Maintenance', 'Security Chief Mohan', 'Janitor Suresh', 'Guard Prakash',
    'Facility Manager Deepak', 'Cleaner Sunita'
]

VISITOR_NAMES = [
    'Amazon Delivery', 'Zomato Partner', 'Guest - John Wilson', 'Vendor - TechCorp',
    'Parent - Mrs. Desai', 'Alumni - Rajat Khanna', 'Interview Candidate', 'Swiggy Delivery',
    'BlueDart Courier', 'Guest Lecturer - Dr. Thompson', 'Contractor - BuildRight',
    'Maintenance - AC Services'
]

VISITOR_PURPOSES = [
    'Package Delivery', 'Food Delivery', 'Guest Visit', 'Vendor Meeting',
    'Parent-Teacher Meeting', 'Alumni Networking', 'Job Interview', 'Courier Service',
    'Campus Tour', 'Guest Lecture', 'Maintenance Work', 'Equipment Installation'
]

def create_demo_data():
    """Create comprehensive demo data for competition showcase"""
    
    with app.app_context():
        print("=" * 60)
        print("SmartLift Demo Data Seeder - Competition Edition")
        print("=" * 60)
        
        # Get or create demo tenant
        tenant = Tenant.query.filter_by(name="Demo University").first()
        if not tenant:
            tenant = Tenant(
                name="Demo University",
                clg_id="DU2024",
                No_Floor=10,
                max_lifts=5,
                primary_color="#6366f1",
                subscription_type="Enterprise",
                subscription_status="Active"
            )
            db.session.add(tenant)
            db.session.commit()
            print(f"✓ Created tenant: {tenant.name}")
        
        tenant_id = tenant.id
        
        # Ensure lift exists
        lift = Lift.query.filter_by(tenant_id=tenant_id).first()
        if not lift:
            lift = Lift(name="Main Building Lift A", status="Online", tenant_id=tenant_id)
            db.session.add(lift)
            db.session.commit()
        
        lift_id = lift.Lift_id
        
        # Clear old demo data (optional - comment out to preserve existing)
        # User.query.filter_by(tenant_id=tenant_id).delete()
        # AccessLog.query.delete()
        # FloorRequest.query.delete()
        # VisitorPass.query.filter_by(tenant_id=tenant_id).delete()
        # db.session.commit()
        
        print("\n[1/4] Creating Faculty Members...")
        faculty_users = []
        for i, name in enumerate(FACULTY_NAMES, 1):
            user = User(
                name=name,
                email=f"{name.lower().replace(' ', '.').replace('dr.', '').replace('prof.', '')}@demo.edu",
                access_type="Faculty",
                allowed_floors="0,1,2,3,4,5,6,7",
                enrollment_id=f"FAC{2020 + i}",
                department=random.choice(DEPARTMENTS),
                tenant_id=tenant_id,
                face_vector="[]"  # Empty for demo
            )
            faculty_users.append(user)
            db.session.add(user)
        
        db.session.commit()
        print(f"✓ Created {len(FACULTY_NAMES)} faculty members")
        
        print("\n[2/4] Creating Students...")
        student_users = []
        for i in range(40):
            first = random.choice(STUDENT_FIRST_NAMES)
            last = random.choice(STUDENT_LAST_NAMES)
            name = f"{first} {last}"
            batch = random.choice(BATCHES)
            course = random.choice(COURSES)
            dept = random.choice(DEPARTMENTS)
            
            # Students have limited floor access based on department
            floors = "0,1,2,3" if 'Engineering' in dept else "0,1,2"
            
            user = User(
                name=name,
                email=f"{first.lower()}.{last.lower()}@student.demo.edu",
                access_type="Temporary",
                allowed_floors=floors,
                enrollment_id=f"{batch}CS{1000 + i}",
                department=dept,
                course=course,
                batch=batch,
                tenant_id=tenant_id,
                face_vector="[]"
            )
            student_users.append(user)
            db.session.add(user)
        
        db.session.commit()
        print(f"✓ Created 40 students across different batches")
        
        print("\n[3/4] Creating Support Staff...")
        operator_users = []
        for i, name in enumerate(OPERATOR_NAMES, 1):
            user = User(
                name=name,
                email=f"{name.lower().replace(' ', '.')}@demo.edu",
                access_type="Operator",
                allowed_floors="0,1,2,3,4,5,6,7,8,9",
                enrollment_id=f"OPR{2020 + i}",
                department="Facilities",
                tenant_id=tenant_id,
                face_vector="[]"
            )
            operator_users.append(user)
            db.session.add(user)
        
        db.session.commit()
        print(f"✓ Created {len(OPERATOR_NAMES)} operators/staff")
        
        print("\n[4/4] Generating Access Logs (Last 30 Days)...")
        all_users = faculty_users + student_users + operator_users
        
        # Generate logs for past 30 days
        start_date = datetime.now() - timedelta(days=30)
        log_count = 0
        
        for day in range(30):
            current_date = start_date + timedelta(days=day)
            
            # Skip weekends (less activity)
            if current_date.weekday() >= 5:
                num_logs = random.randint(10, 30)
            else:
                num_logs = random.randint(40, 80)
            
            for _ in range(num_logs):
                user = random.choice(all_users)
                
                # Generate realistic time patterns (peak hours 9-11am, 2-5pm)
                hour = random.choices(
                    range(7, 20),
                    weights=[5, 10, 15, 12, 8, 5, 3, 8, 12, 15, 10, 7, 5],
                    k=1
                )[0]
                minute = random.randint(0, 59)
                
                timestamp = current_date.replace(hour=hour, minute=minute)
                
                # Parse allowed floors
                allowed = [int(f) for f in user.allowed_floors.split(',')]
                source_floor = 0 if random.random() < 0.7 else random.choice(allowed)
                target_floor = random.choice(allowed)
                
                # 95% success rate
                if random.random() < 0.95:
                    status = "Granted"
                    req_status = "Completed"
                else:
                    status = "Denied - Out of Hours"
                    req_status = "Rejected"
                
                # Create request and log
                req = FloorRequest(
                    User_id=user.user_id,
                    Floor_number=target_floor,
                    Status=req_status,
                    Lift_id=lift_id
                )
                db.session.add(req)
                db.session.flush()
                
                log = AccessLog(
                    User_id=user.user_id,
                    timestlap=timestamp,
                    Source_floor=source_floor,
                    Floor_selection=target_floor,
                    status=status,
                    Request_ID=req.Request_ID
                )
                db.session.add(log)
                log_count += 1
        
        db.session.commit()
        print(f"✓ Generated {log_count} access logs over 30 days")
        
        print("\n[Bonus] Creating Visitor Passes...")
        visitor_count = 0
        for i in range(15):
            name = random.choice(VISITOR_NAMES)
            purpose = random.choice(VISITOR_PURPOSES)
            
            # Mix of active and expired passes
            if i < 10:
                valid_from = datetime.now() - timedelta(hours=random.randint(1, 24))
                valid_until = datetime.now() + timedelta(hours=random.randint(2, 48))
                status = 'Active'
            else:
                valid_from = datetime.now() - timedelta(days=random.randint(2, 10))
                valid_until = datetime.now() - timedelta(days=random.randint(1, 5))
                status = 'Expired'
            
            qr_hash = str(uuid.uuid4())
            floors = "0,1,2" if 'Delivery' in name else "0,1"
            
            pass_obj = VisitorPass(
                visitor_name=name,
                purpose=purpose,
                qr_hash=qr_hash,
                allowed_floors=floors,
                valid_from=valid_from,
                valid_until=valid_until,
                status=status,
                tenant_id=tenant_id,
                created_by_admin_id=1  # Assuming admin exists
            )
            db.session.add(pass_obj)
            visitor_count += 1
            
            # Add some visitor access logs
            if status == 'Active' and random.random() < 0.6:
                req = FloorRequest(
                    User_id=None,
                    Floor_number=random.choice([0, 1, 2]),
                    Status="Completed",
                    Lift_id=lift_id
                )
                db.session.add(req)
                db.session.flush()
                
                log = AccessLog(
                    User_id=None,
                    timestlap=datetime.now() - timedelta(hours=random.randint(1, 12)),
                    Source_floor=0,
                    Floor_selection=random.choice([0, 1, 2]),
                    status=f"QR Guest [{name}] - Granted",
                    Request_ID=req.Request_ID
                )
                db.session.add(log)
        
        db.session.commit()
        print(f"✓ Created {visitor_count} visitor passes (10 active, 5 expired)")
        
        print("\n" + "=" * 60)
        print("DEMO DATA CREATION COMPLETE!")
        print("=" * 60)
        print(f"\n📊 Summary:")
        print(f"   - Faculty: {len(FACULTY_NAMES)}")
        print(f"   - Students: 40")
        print(f"   - Staff: {len(OPERATOR_NAMES)}")
        print(f"   - Total Users: {len(all_users)}")
        print(f"   - Access Logs: {log_count}")
        print(f"   - Visitor Passes: {visitor_count}")
        print(f"\n🎯 Competition Ready!")
        print(f"   - Login at: http://localhost:8000")
        print(f"   - Admin: admin@demo.com / admin123")
        print("\n")

if __name__ == "__main__":
    create_demo_data()
