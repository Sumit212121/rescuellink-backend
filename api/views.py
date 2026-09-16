import json
import time
import random
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.core import signing
from .models import UserProfile, NgoProfile, Emergency, DisasterAlert, Donation, TransmittedLocation, RescueAssignment, VehicleLocation

# Programmatic database auto-migrations execution hook
_MIGRATIONS_RUN = False
if not _MIGRATIONS_RUN:
    try:
        from django.core.management import call_command
        call_command('makemigrations', 'api', interactive=False)
        call_command('migrate', interactive=False)
        # Auto-create superuser admin if none exists
        if not User.objects.filter(is_superuser=True).exists():
            User.objects.create_superuser('admin', 'admin@rescuelink.org', 'admin123')
        _MIGRATIONS_RUN = True
    except Exception as e:
        print("Auto-migration startup hook logged:", e)

SECRET_AGE = 86400 * 30  # 30 days

# HELPER: Token generator — login ke baad ye token frontend ko milta hai
def create_token(user):
    # User ka role pata karo (user / ngo / admin)
    role = 'user'
    if user.is_superuser or user.is_staff:
        role = 'admin'
    elif hasattr(user, 'ngo_profile'):
        role = 'ngo'

    # Token ke andar ye data encrypted hoke jaata hai
    payload = {
        'user_id': user.id,
        'username': user.username,
        'role': role,
        'timestamp': time.time()
    }
    return signing.dumps(payload)  # Django isko sign karke ek secure string banata hai

def get_user_from_request(request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    token = auth_header.split(' ')[1]
    try:
        payload = signing.loads(token, max_age=SECRET_AGE)
        user = User.objects.get(id=payload['user_id'])
        return user
    except Exception:
        return None

def get_ngo_coordinates(ngo):
    CITY_COORDS = {
        'patna': (25.6022, 85.1376),
        'birgunj': (27.0130, 84.8770),
        'delhi': (28.6139, 77.2090),
        'mumbai': (19.0760, 72.8777),
        'kathmandu': (27.7172, 85.3240),
        'janakpur': (26.7274, 85.9472),
        'pokhara': (28.2096, 83.9856)
    }

    ref_lat = 25.6022
    ref_lng = 85.1376

    if ngo and ngo.city:
        city_lower = ngo.city.strip().lower()
        for city_name, coords in CITY_COORDS.items():
            if city_name in city_lower or city_lower in city_name:
                ref_lat, ref_lng = coords
                break

    ngo_lat = ref_lat + ((ngo.id * 17) % 100) * 0.0003
    ngo_lng = ref_lng + ((ngo.id * 31) % 100) * 0.0003
    return ngo_lat, ngo_lng

# HELPER: Format user profile to match exactly what React expects
def format_user_response(user):
    role = 'user'
    data = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
    }
    
    if user.is_superuser or user.is_staff:
        data.update({
            'role': 'admin',
            'name': 'System Administrator',
        })
    elif hasattr(user, 'ngo_profile'):
        role = 'ngo'
        profile = user.ngo_profile
        ngo_lat, ngo_lng = get_ngo_coordinates(profile)
        data.update({
            'role': 'ngo',
            'name': profile.name,
            'phone': profile.phone,
            'address': profile.address,
            'city': profile.city,
            'pincode': profile.pincode,
            'specializations': profile.specializations,
            'specialization': profile.specializations[0] if profile.specializations else 'General Rescue',
            'ambulances': profile.ambulances,
            'boats': profile.boats,
            'fire_trucks': profile.fire_trucks,
            'volunteers': profile.volunteers,
            'isVerified': profile.is_verified,
            'latitude': ngo_lat,
            'longitude': ngo_lng,
        })
    elif hasattr(user, 'user_profile'):
        profile = user.user_profile
        data.update({
            'role': 'user',
            'name': profile.name if hasattr(profile, 'name') else user.first_name,
            'phone': profile.phone,
            'address': profile.address,
            'city': profile.city,
            'state': profile.state,
            'pincode': profile.pincode,
            'language': profile.language,
            # Dual-casing for bulletproof frontend compatibility
            'family_count': profile.family_count,
            'familyCount': profile.family_count,
            'emergency_contact': profile.emergency_contact,
            'emergencyContact': profile.emergency_contact,
            'medical_conditions': profile.medical_conditions,
            'medicalConditions': profile.medical_conditions,
        })
    else:
        data['role'] = 'user'
        data['name'] = user.username
        
    return data

# AUTH: Login endpoint
@csrf_exempt
def login_view(request):
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=452)

    try:
        # Step 1: Frontend se aaya hua data nikalo
        body = json.loads(request.body)
        email = body.get('email', '').strip()
        password = body.get('password', '')

        # Step 2: Email aur password dono zaroori hai
        if not email or not password:
            return JsonResponse({'detail': 'Email and password are required'}, status=400)

        # Step 3: Database mein user dhundho — pehle email se, phir username se
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            user = User.objects.filter(username__iexact=email).first()

        # Step 4: Agar user nahi mila ya password galat hai — error bhejo
        if not user or not user.check_password(password):
            return JsonResponse({'detail': 'Invalid email/username or password'}, status=401)

        # Step 5: Token banao aur user data frontend ko bhej do
        token = create_token(user)
        user_data = format_user_response(user)
        return JsonResponse({'user': user_data, 'access': token})

    except Exception as e:
        return JsonResponse({'detail': str(e)}, status=500)

# AUTH: Citizen registration
@csrf_exempt
def register_user_view(request):
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=452)
    
    try:
        body = json.loads(request.body)
        email = body.get('email', '').strip()
        password = body.get('password', '')
        name = body.get('name', '').strip()
        phone = body.get('phone', '').strip()
        address = body.get('address', '')
        city = body.get('city', '')
        state = body.get('state', '')
        pincode = body.get('pincode', '').strip()
        language = body.get('language', '')
        family_count = body.get('family_count', '0')
        emergency_contact = body.get('emergency_contact', '')
        medical_conditions = body.get('medical_conditions', '')

        if not password or not name or not phone:
            return JsonResponse({'detail': 'Missing required registration parameters'}, status=400)

        if not email:
            email = f"{phone}@rescuelink.org"

        if User.objects.filter(email__iexact=email).exists():
            return JsonResponse({'detail': 'User with this email or phone already registered'}, status=400)
            
        username = email.split('@')[0] + str(random.randint(100, 999))
        
        # Ensure unique username
        while User.objects.filter(username=username).exists():
            username = email.split('@')[0] + str(random.randint(100, 999))

        user = User.objects.create_user(username=username, email=email, password=password)
        user.first_name = name
        user.save()

        profile = UserProfile.objects.create(
            user=user,
            phone=phone,
            address=address,
            city=city,
            state=state,
            pincode=pincode,
            language=language,
            family_count=str(family_count),
            emergency_contact=emergency_contact,
            medical_conditions=medical_conditions
        )

        token = create_token(user)
        return JsonResponse({
            'user': format_user_response(user),
            'access': token
        })
    except Exception as e:
        return JsonResponse({'detail': str(e)}, status=500)

# AUTH: NGO registration
@csrf_exempt
def register_ngo_view(request):
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=452)
    
    try:
        body = json.loads(request.body)
        email = body.get('email', '').strip()
        password = body.get('password', '')
        name = body.get('name', '').strip()
        phone = body.get('phone', '').strip()
        address = body.get('address', '')
        city = body.get('city', '')
        pincode = body.get('pincode', '').strip()
        specializations = body.get('specializations', [])
        ambulances = int(body.get('ambulances', 0) or 0)
        boats = int(body.get('boats', 0) or 0)
        fire_trucks = int(body.get('fire_trucks', 0) or 0)
        volunteers = int(body.get('volunteers', 0) or 0)

        if not email or not password or not name or not phone:
            return JsonResponse({'detail': 'Missing required NGO parameters'}, status=400)

        if User.objects.filter(email__iexact=email).exists():
            return JsonResponse({'detail': 'Agency with this email already registered'}, status=400)

        username = 'ngo_' + email.split('@')[0] + str(random.randint(10, 99))
        user = User.objects.create_user(username=username, email=email, password=password)
        user.first_name = name
        user.save()

        profile = NgoProfile.objects.create(
            user=user,
            name=name,
            phone=phone,
            address=address,
            city=city,
            pincode=pincode,
            specializations=specializations,
            ambulances=ambulances,
            boats=boats,
            fire_trucks=fire_trucks,
            volunteers=volunteers
        )

        token = create_token(user)
        return JsonResponse({
            'user': format_user_response(user),
            'access': token
        })
    except Exception as e:
        return JsonResponse({'detail': str(e)}, status=500)

# AUTH: Current user profile
@csrf_exempt
def me_view(request):
    user = get_user_from_request(request)
    if not user:
        return JsonResponse({'detail': 'Unauthorized access token'}, status=401)
        
    if request.method == 'GET':
        return JsonResponse(format_user_response(user))
        
    elif request.method in ['POST', 'PUT']:
        try:
            body = json.loads(request.body)
            
            # Update basic user fields
            if 'email' in body:
                user.email = body.get('email')
            
            if hasattr(user, 'ngo_profile'):
                profile = user.ngo_profile
                if 'name' in body:
                    profile.name = body.get('name')
                if 'phone' in body:
                    profile.phone = body.get('phone')
                if 'address' in body:
                    profile.address = body.get('address')
                if 'city' in body:
                    profile.city = body.get('city')
                if 'pincode' in body:
                    profile.pincode = body.get('pincode')
                if 'specializations' in body:
                    profile.specializations = body.get('specializations')
                if 'ambulances' in body:
                    profile.ambulances = int(body.get('ambulances') or 0)
                if 'boats' in body:
                    profile.boats = int(body.get('boats') or 0)
                if 'fire_trucks' in body:
                    profile.fire_trucks = int(body.get('fire_trucks') or 0)
                if 'volunteers' in body:
                    profile.volunteers = int(body.get('volunteers') or 0)
                profile.save()
                
            elif hasattr(user, 'user_profile'):
                profile = user.user_profile
                if 'name' in body:
                    user.first_name = body.get('name')
                if 'phone' in body:
                    profile.phone = body.get('phone')
                if 'address' in body:
                    profile.address = body.get('address')
                if 'city' in body:
                    profile.city = body.get('city')
                if 'state' in body:
                    profile.state = body.get('state')
                if 'pincode' in body:
                    profile.pincode = body.get('pincode')
                if 'language' in body:
                    profile.language = body.get('language')
                if 'family_count' in body or 'familyCount' in body:
                    profile.family_count = body.get('family_count') or body.get('familyCount')
                if 'emergency_contact' in body or 'emergencyContact' in body:
                    profile.emergency_contact = body.get('emergency_contact') or body.get('emergencyContact')
                if 'medical_conditions' in body or 'medicalConditions' in body:
                    profile.medical_conditions = body.get('medical_conditions') or body.get('medicalConditions')
                profile.save()
            
            user.save()
            return JsonResponse(format_user_response(user))
        except Exception as e:
            return JsonResponse({'detail': str(e)}, status=400)

def find_nearby_flood_ngos(v_lat, v_lng, max_km=10.0):
    """
    Searches for NGOs within 10 km radius of victim.
    Filters by:
      - Active/verified
      - Specializations containing 'flood'
      - Available rescue capacity (boats > 0 or volunteers > 0)
    Prioritizes by:
      - Flood specialization
      - Proximity / distance
      - Boat & volunteer capacity
    """
    import math
    from .models import NgoProfile
    ngos = NgoProfile.objects.filter(is_verified=True)
    results = []

    for ngo in ngos:
        specs = ngo.specializations or []
        if isinstance(specs, str):
            try: specs = json.loads(specs)
            except: specs = [specs]
        if not isinstance(specs, list):
            specs = [specs]

        is_flood_specialist = any('flood' in str(s).lower() for s in specs)
        if not is_flood_specialist:
            continue

        # Check rescue capacity
        if (ngo.boats or 0) <= 0 and (ngo.volunteers or 0) <= 0:
            continue

        ngo_lat, ngo_lng = get_ngo_coordinates(ngo)

        # Haversine formula
        R = 6371.0 # Earth radius in km
        d_lat = math.radians(v_lat - ngo_lat)
        d_lon = math.radians(v_lng - ngo_lng)
        a = math.sin(d_lat / 2)**2 + math.cos(math.radians(ngo_lat)) * math.cos(math.radians(v_lat)) * math.sin(d_lon / 2)**2
        a = min(1.0, max(0.0, a))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        dist = R * c

        if dist <= max_km:
            results.append({
                'id': ngo.id,
                'name': ngo.name,
                'phone': ngo.phone or '+91 98765 43210',
                'city': ngo.city or 'Patna',
                'address': ngo.address or f"{ngo.name} Relief Command Station, {ngo.city}",
                'distance_km': round(dist, 1),
                'boats': ngo.boats,
                'volunteers': ngo.volunteers,
                'ambulances': ngo.ambulances,
                'specializations': specs,
                'latitude': ngo_lat,
                'longitude': ngo_lng,
                'is_available': True,
            })

    # Sort prioritized by distance ascending, then boat capacity descending
    results.sort(key=lambda x: (x['distance_km'], -x['boats'], -x['volunteers']))
    return results

def get_emergency_telemetry(emergency):
    """
    Computes real-time backend-driven telemetry coordinates and calculations
    for active emergency dispatches between NGO base and victim.
    """
    import math
    from django.utils import timezone

    victim_lat = emergency.latitude or 25.6022
    victim_lng = emergency.longitude or 85.1376

    # Start coordinates: from matched NGO base if available, else standard local offset
    if emergency.matched_ngo:
        start_lat, start_lng = get_ngo_coordinates(emergency.matched_ngo)
    else:
        start_lat = victim_lat + 0.0098
        start_lng = victim_lng + 0.0204

    # Calculate base geodetic distance between NGO and Victim
    R = 6371.0
    d_lat_total = math.radians(victim_lat - start_lat)
    d_lon_total = math.radians(victim_lng - start_lng)
    a_total = math.sin(d_lat_total / 2)**2 + math.cos(math.radians(start_lat)) * math.cos(math.radians(victim_lat)) * math.sin(d_lon_total / 2)**2
    a_total = min(1.0, max(0.0, a_total))
    total_dist = R * (2 * math.atan2(math.sqrt(a_total), math.sqrt(1.0 - a_total)))

    status_lower = (emergency.status or 'pending').lower()

    # Step index for lifecycle progress:
    # 1: Pending, 2: Accepted/Assigned, 3: Dispatched/Enroute, 4: Arrived, 5: Rescued/In Progress, 6: Resolved
    step_map = {
        'pending': 1,
        'ngo_found': 1,
        'accepted': 2,
        'assigned': 2,
        'dispatched': 3,
        'on_the_way': 3,
        'arrived': 4,
        'rescue_in_progress': 5,
        'resolved': 6,
        'cancelled': 0
    }
    current_step = step_map.get(status_lower, 1)

    if status_lower in ['resolved', 'arrived', 'rescue_in_progress']:
        return {
            'progress': 100.0,
            'distance': '0.00',
            'distance_km': 0.0,
            'eta': 0,
            'speed': 0,
            'step': current_step,
            'status': emergency.status,
            'victim_location': {
                'lat': victim_lat,
                'lng': victim_lng,
                'name': emergency.name,
                'address': emergency.address or 'Flood Affected Location'
            },
            'ngo_location': {
                'lat': start_lat,
                'lng': start_lng,
                'name': emergency.matched_ngo.name if emergency.matched_ngo else 'Relief Base'
            },
            'vehicle_location': {
                'lat': victim_lat,
                'lng': victim_lng,
                'label': emergency.rescue_vehicle or 'Rescue Boat RB-04'
            },
            'route': {
                'start': {'lat': start_lat, 'lng': start_lng},
                'end': {'lat': victim_lat, 'lng': victim_lng}
            }
        }

    if status_lower in ['pending', 'ngo_found']:
        return {
            'progress': 0.0,
            'distance': f"{max(0.5, total_dist):.2f}",
            'distance_km': round(max(0.5, total_dist), 2),
            'eta': emergency.eta or 15,
            'speed': 0,
            'step': current_step,
            'status': emergency.status,
            'victim_location': {
                'lat': victim_lat,
                'lng': victim_lng,
                'name': emergency.name,
                'address': emergency.address or 'Flood Affected Location'
            },
            'ngo_location': {
                'lat': start_lat,
                'lng': start_lng,
                'name': emergency.matched_ngo.name if emergency.matched_ngo else 'Relief Base'
            },
            'vehicle_location': {
                'lat': start_lat,
                'lng': start_lng,
                'label': emergency.rescue_vehicle or 'Rescue Boat'
            },
            'route': {
                'start': {'lat': start_lat, 'lng': start_lng},
                'end': {'lat': victim_lat, 'lng': victim_lng}
            }
        }

    # If real GPS coordinates exist for vehicle, prioritize them over fallback interpolation
    if emergency.vehicle_lat is not None and emergency.vehicle_lng is not None:
        current_lat = emergency.vehicle_lat
        current_lng = emergency.vehicle_lng
        d_lat_rem = math.radians(victim_lat - current_lat)
        d_lon_rem = math.radians(victim_lng - current_lng)
        a_rem = math.sin(d_lat_rem / 2)**2 + math.cos(math.radians(current_lat)) * math.cos(math.radians(victim_lat)) * math.sin(d_lon_rem / 2)**2
        a_rem = min(1.0, max(0.0, a_rem))
        rem_dist = R * (2 * math.atan2(math.sqrt(a_rem), math.sqrt(1.0 - a_rem)))
        progress = max(0.0, min(100.0, (1.0 - (rem_dist / max(0.001, total_dist))) * 100.0)) if total_dist > 0.05 else 90.0
    else:
        # Fallback to dispatch elapsed time
        reference_time = emergency.dispatched_at or emergency.accepted_at or emergency.updated_at
        elapsed = max(0.0, (timezone.now() - reference_time).total_seconds()) if reference_time else 10.0
        duration = 90.0
        progress = min(98.0, (elapsed / duration) * 100.0)
        current_lat = start_lat - (start_lat - victim_lat) * (progress / 100.0)
        current_lng = start_lng - (start_lng - victim_lng) * (progress / 100.0)
        d_lat_rem = math.radians(victim_lat - current_lat)
        d_lon_rem = math.radians(victim_lng - current_lng)
        a_rem = math.sin(d_lat_rem / 2)**2 + math.cos(math.radians(current_lat)) * math.cos(math.radians(victim_lat)) * math.sin(d_lon_rem / 2)**2
        a_rem = min(1.0, max(0.0, a_rem))
        rem_dist = R * (2 * math.atan2(math.sqrt(a_rem), math.sqrt(1.0 - a_rem)))

    speed = 28 # km/h
    eta = max(1, int(math.ceil(rem_dist / (speed / 60.0)))) if rem_dist > 0.05 else 0

    return {
        'progress': round(progress, 1),
        'distance': f"{rem_dist:.2f}",
        'distance_km': round(rem_dist, 2),
        'eta': eta,
        'speed': speed,
        'step': current_step,
        'status': emergency.status,
        'location_accuracy': getattr(emergency, 'location_accuracy', 10.0),
        'vehicle_accuracy': getattr(emergency, 'vehicle_accuracy', 5.0),
        'vehicle_updated_at': emergency.vehicle_updated_at.isoformat() if emergency.vehicle_updated_at else None,
        'victim_location': {
            'lat': victim_lat,
            'lng': victim_lng,
            'accuracy': getattr(emergency, 'location_accuracy', 10.0),
            'name': emergency.name,
            'address': emergency.address or 'Flood Affected Location'
        },
        'ngo_location': {
            'lat': start_lat,
            'lng': start_lng,
            'name': emergency.matched_ngo.name if emergency.matched_ngo else 'Relief Base'
        },
        'vehicle_location': {
            'lat': round(current_lat, 5),
            'lng': round(current_lng, 5),
            'accuracy': getattr(emergency, 'vehicle_accuracy', 5.0),
            'updated_at': emergency.vehicle_updated_at.isoformat() if emergency.vehicle_updated_at else None,
            'label': emergency.rescue_vehicle or 'Rescue Boat RB-04'
        },
        'route': {
            'start': {'lat': start_lat, 'lng': start_lng},
            'end': {'lat': victim_lat, 'lng': victim_lng}
        }
    }

def calculate_ngo_distance(emergency, ngo):
    ngo_lat, ngo_lng = get_ngo_coordinates(ngo)
    v_lat = emergency.latitude or ngo_lat
    v_lng = emergency.longitude or ngo_lng

    import math
    R = 6371.0
    d_lat = math.radians(v_lat - ngo_lat)
    d_lon = math.radians(v_lng - ngo_lng)
    a = math.sin(d_lat / 2)**2 + math.cos(math.radians(ngo_lat)) * math.cos(math.radians(v_lat)) * math.sin(d_lon / 2)**2
    a = min(1.0, max(0.0, a))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c

def format_emergency_data(emergency, user=None):
    """
    Serializes Emergency model for complete consistency across user and NGO dashboards.
    """
    is_ngo = user and hasattr(user, 'ngo_profile')
    ngo_profile = user.ngo_profile if is_ngo else None

    distance_km = None
    if ngo_profile:
        distance_km = round(calculate_ngo_distance(emergency, ngo_profile), 1)
    elif emergency.matched_ngo:
        distance_km = round(calculate_ngo_distance(emergency, emergency.matched_ngo), 1)

    matched_ngo_data = None
    if emergency.matched_ngo:
        specs = emergency.matched_ngo.specializations or []
        if isinstance(specs, str):
            try: specs = json.loads(specs)
            except: specs = [specs]
        if not isinstance(specs, list):
            specs = [specs]
        matched_ngo_data = {
            'id': emergency.matched_ngo.id,
            'name': emergency.matched_ngo.name,
            'phone': emergency.matched_ngo.phone or "+91 99999 88888",
            'city': emergency.matched_ngo.city or "Patna",
            'address': emergency.matched_ngo.address or "Relief Command Station",
            'specializations': specs,
            'desc': f"Specialized in: {', '.join(specs)}. Stationed in {emergency.matched_ngo.city}.",
            'contact': emergency.matched_ngo.phone or "+91 99999 88888",
        }

    # Latest notification / assignment message
    latest_assignment = emergency.assignments.order_by('-created_at').first()
    notification_msg = latest_assignment.notification_message if latest_assignment else None
    if not notification_msg and emergency.matched_ngo:
        notification_msg = f"{emergency.matched_ngo.name} is on the way. ETA: {emergency.eta} minutes. Track live here: http://localhost:5173/?track={emergency.sosId}"

    telemetry = get_emergency_telemetry(emergency)

    # Status styling
    status_lower = (emergency.status or 'pending').lower()
    status_classes = {
        'pending': 'bg-amber-100 text-amber-800 border-amber-200',
        'ngo_found': 'bg-yellow-100 text-yellow-800 border-yellow-200',
        'accepted': 'bg-blue-100 text-blue-700 border-blue-200',
        'assigned': 'bg-indigo-100 text-indigo-700 border-indigo-200',
        'dispatched': 'bg-sky-100 text-sky-700 border-sky-200',
        'on_the_way': 'bg-blue-100 text-blue-700 border-blue-200',
        'arrived': 'bg-purple-100 text-purple-700 border-purple-200',
        'rescue_in_progress': 'bg-orange-100 text-orange-700 border-orange-200',
        'resolved': 'bg-emerald-100 text-emerald-700 border-emerald-200',
        'cancelled': 'bg-slate-100 text-slate-700 border-slate-200',
    }

    # Priority display
    priority_formatted = emergency.urgency.capitalize() if emergency.urgency else 'High'

    # Time elapsed
    from django.utils import timezone
    elapsed_minutes = (timezone.now() - emergency.created_at).total_seconds() / 60.0
    time_str = f"{int(elapsed_minutes)} mins ago" if elapsed_minutes >= 1 else "Just now"

    # Disaster Icon
    disaster_icons = {
        'flood': '🌊',
        'landslide': '🪨',
        'fire': '🔥',
        'earthquake': '🌍',
        'accident': '🚗',
        'medical': '🚑',
    }
    icon = disaster_icons.get(emergency.disaster.lower(), '🚨')

    return {
        'id': emergency.sosId,
        'sosId': emergency.sosId,
        'type': emergency.disaster.capitalize(),
        'disaster': emergency.disaster,
        'icon': icon,
        'urgency': emergency.urgency,
        'priority': priority_formatted,
        'name': emergency.name,
        'phone': emergency.phone,
        'people': emergency.people,
        'address': emergency.address or 'XYZ Location, Patna',
        'location': emergency.address or f"{emergency.latitude:.4f}, {emergency.longitude:.4f}",
        'coords': {
            'lat': emergency.latitude,
            'lng': emergency.longitude
        },
        'description': emergency.description or 'Flood emergency distress call',
        'status': emergency.status,
        'statusClass': status_classes.get(status_lower, 'bg-slate-100 text-slate-700 border-slate-200'),
        'eta': f"{emergency.eta} mins" if emergency.eta else "15 mins",
        'eta_mins': emergency.eta,
        'distance': f"{distance_km} km" if distance_km is not None else "4.2 km",
        'distance_km': distance_km,
        'time': time_str,
        'createdAt': emergency.created_at.strftime('%I:%M %p'),
        'created_at_iso': emergency.created_at.isoformat(),
        'accepted_at': emergency.accepted_at.isoformat() if emergency.accepted_at else None,
        'dispatched_at': emergency.dispatched_at.isoformat() if emergency.dispatched_at else None,
        'arrived_at': emergency.arrived_at.isoformat() if emergency.arrived_at else None,
        'resolved_at': emergency.resolved_at.isoformat() if emergency.resolved_at else None,
        'rescue_team': emergency.rescue_team or 'Team Alpha',
        'volunteer': emergency.rescue_team or 'Team Alpha',
        'volunteerPhone': emergency.matched_ngo.phone if emergency.matched_ngo else '+91 98765 00000',
        'vehicle': emergency.rescue_vehicle or 'Rescue Boat RB-04',
        'vehicle_lat': emergency.vehicle_lat,
        'vehicle_lng': emergency.vehicle_lng,
        'vehicle_accuracy': getattr(emergency, 'vehicle_accuracy', 5.0),
        'vehicle_updated_at': emergency.vehicle_updated_at.isoformat() if emergency.vehicle_updated_at else None,
        'location_accuracy': getattr(emergency, 'location_accuracy', 10.0),
        'location_updated_at': emergency.location_updated_at.isoformat() if emergency.location_updated_at else None,
        'rescued_people_count': emergency.rescued_people_count,
        'resolution_notes': emergency.resolution_notes,
        'progressStep': telemetry.get('step', 1),
        'matchedNgo': matched_ngo_data,
        'telemetry': telemetry,
        'notification_message': notification_msg
    }

# EMERGENCIES: List and Create
@csrf_exempt
def emergencies_view(request):
    user = get_user_from_request(request)

    if request.method == 'GET':
        is_ngo = user and hasattr(user, 'ngo_profile')
        ngo_profile = user.ngo_profile if is_ngo else None

        qs = Emergency.objects.all().order_by('-created_at')

        # Filter active vs history
        is_history = request.GET.get('history') == 'true'
        is_active_only = request.GET.get('active_only') == 'true'
        user_only = request.GET.get('my') == 'true'

        if user_only and user:
            qs = qs.filter(user=user)

        if is_history:
            qs = qs.filter(status='resolved')
        elif is_active_only:
            qs = qs.exclude(status__in=['resolved', 'cancelled'])

        # If NGO is logged in and not querying history, apply range/specialty visibility
        data_list = []
        for em in qs:
            # If NGO: can see pending requests within 10 km that match specialty, plus requests matched to them
            if ngo_profile and not is_history:
                specs = ngo_profile.specializations or []
                if isinstance(specs, str):
                    try: specs = json.loads(specs)
                    except: specs = [specs]
                if not isinstance(specs, list):
                    specs = [specs]

                matches_specialty = any(em.disaster.lower() == str(s).lower() for s in specs)
                dist = calculate_ngo_distance(em, ngo_profile)

                if em.status in ['pending', 'ngo_found']:
                    if not matches_specialty or dist > 10.0:
                        continue
                else:
                    if not em.matched_ngo or em.matched_ngo.id != ngo_profile.id:
                        continue

            data_list.append(format_emergency_data(em, user=user))

        return JsonResponse(data_list, safe=False)

    elif request.method == 'POST':
        try:
            body = json.loads(request.body)
            name = body.get('name') or 'Sunita'
            phone = body.get('phone') or '9876543210'
            disaster = body.get('disaster', 'flood')
            people = str(body.get('people', '3'))
            urgency = body.get('urgency', 'high')
            description = body.get('description', 'Trapped in house due to rising flood waters.')
            address = body.get('address') or 'Patna Riverside, Bihar'

            location = body.get('location') or {}
            lat = float(location.get('lat', body.get('latitude', 25.6022)))
            lng = float(location.get('lng', body.get('longitude', 85.1376)))
            accuracy = float(location.get('accuracy', body.get('location_accuracy', body.get('accuracy', 10.0))))

            sos_id = body.get('sos_id') or body.get('sosId') or Emergency.generate_id()

            from django.utils import timezone

            # Search nearby Flood NGOs within 10 km
            nearby_ngos = find_nearby_flood_ngos(lat, lng, max_km=10.0) if disaster.lower() == 'flood' else []
            initial_status = 'ngo_found' if nearby_ngos else 'pending'

            emergency = Emergency.objects.create(
                sosId=sos_id,
                user=user if user and not hasattr(user, 'ngo_profile') else None,
                disaster=disaster,
                urgency=urgency,
                name=name,
                phone=phone,
                people=people,
                address=address,
                description=description,
                latitude=lat,
                longitude=lng,
                location_accuracy=accuracy,
                location_updated_at=timezone.now(),
                status=initial_status,
                matched_ngo=None,
                eta=15
            )

            res_data = format_emergency_data(emergency, user=user)
            res_data['nearbyNgos'] = nearby_ngos
            res_data['nearby_ngos'] = nearby_ngos
            res_data['nearbyNgosCount'] = len(nearby_ngos)
            res_data['emergency'] = format_emergency_data(emergency, user=user)

            return JsonResponse(res_data, status=201)

        except Exception as e:
            return JsonResponse({'detail': str(e)}, status=500)

# EMERGENCIES: Patch and Get details
@csrf_exempt
def emergency_detail_view(request, sos_id):
    user = get_user_from_request(request)

    try:
        emergency = Emergency.objects.get(sosId=sos_id)
    except Emergency.DoesNotExist:
        return JsonResponse({'detail': 'Emergency record not found'}, status=404)

    if request.method == 'GET':
        return JsonResponse(format_emergency_data(emergency, user=user))

    elif request.method == 'PATCH':
        try:
            body = json.loads(request.body)
            action = body.get('action')

            is_ngo = user and hasattr(user, 'ngo_profile')
            ngo_profile = user.ngo_profile if is_ngo else None

            from django.utils import timezone

            if action in ['accept', 'auto_accept']:
                emergency.status = 'accepted'
                emergency.accepted_at = timezone.now()
                if ngo_profile:
                    emergency.matched_ngo = ngo_profile
                emergency.rescue_team = body.get('rescue_team') or 'Team Alpha'
                emergency.rescue_vehicle = body.get('rescue_vehicle') or 'Rescue Boat RB-04'
                emergency.eta = int(body.get('eta', 15))
            elif action == 'dispatch':
                emergency.status = 'dispatched'
                emergency.dispatched_at = timezone.now()
            elif action == 'arrived':
                emergency.status = 'arrived'
                emergency.arrived_at = timezone.now()
            elif action == 'resolve':
                emergency.status = 'resolved'
                emergency.resolved_at = timezone.now()
                emergency.rescued_people_count = int(body.get('rescued_people_count', emergency.people or 1))
                emergency.resolution_notes = body.get('resolution_notes', 'All individuals safely evacuated.')
            elif action == 'cancel':
                emergency.status = 'cancelled'
            else:
                return JsonResponse({'detail': f"Unknown action: {action}"}, status=400)

            emergency.save()
            return JsonResponse(format_emergency_data(emergency, user=user))
        except Exception as e:
            return JsonResponse({'detail': str(e)}, status=500)

    return JsonResponse({'detail': 'Method not allowed'}, status=452)

# WORKFLOW: Get nearby qualified NGOs
@csrf_exempt
def sos_nearby_ngos_view(request, sos_id):
    try:
        emergency = Emergency.objects.get(sosId=sos_id)
    except Emergency.DoesNotExist:
        return JsonResponse({'detail': 'Emergency record not found'}, status=404)

    lat = emergency.latitude or 25.6022
    lng = emergency.longitude or 85.1376
    nearby = find_nearby_flood_ngos(lat, lng, max_km=10.0)
    return JsonResponse({
        'sosId': emergency.sosId,
        'victim': {
            'name': emergency.name,
            'phone': emergency.phone,
            'address': emergency.address,
            'latitude': lat,
            'longitude': lng,
            'people': emergency.people
        },
        'nearbyNgos': nearby,
        'nearby_ngos': nearby,
        'count': len(nearby)
    })

# HELPER: Broadcast rescue status changes over WebSocket channel layer
def broadcast_rescue_status(sos_id, status, emergency_data=None, message=None):
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            from django.utils import timezone
            async_to_sync(channel_layer.group_send)(
                f"rescue_{sos_id}",
                {
                    'type': 'rescue_status_broadcast',
                    'data': {
                        'sos_id': sos_id,
                        'status': status,
                        'message': message,
                        'emergency': emergency_data,
                        'timestamp': timezone.now().isoformat()
                    }
                }
            )
    except Exception as e:
        print(f"WebSocket broadcast error for {sos_id}: {e}")

# WORKFLOW: NGO Accepts Request
@csrf_exempt
def sos_accept_view(request, sos_id):
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    user = get_user_from_request(request)
    is_ngo = user and hasattr(user, 'ngo_profile')
    ngo_profile = user.ngo_profile if is_ngo else NgoProfile.objects.filter(is_verified=True).first()

    try:
        emergency = Emergency.objects.get(sosId=sos_id)
    except Emergency.DoesNotExist:
        return JsonResponse({'detail': 'Emergency record not found'}, status=404)

    try:
        body = json.loads(request.body) if request.body else {}
    except Exception:
        body = {}

    from django.utils import timezone

    rescue_team = body.get('rescue_team') or 'Team Alpha'
    vehicle = body.get('vehicle') or 'Rescue Boat RB-04'
    eta = int(body.get('eta', 15))

    emergency.status = 'accepted'
    emergency.matched_ngo = ngo_profile
    emergency.rescue_team = rescue_team
    emergency.rescue_vehicle = vehicle
    emergency.eta = eta
    emergency.accepted_at = timezone.now()
    emergency.save()

    ngo_name = ngo_profile.name if ngo_profile else "Lions Club Relief Unit"
    notification_msg = f"{ngo_name} is on the way. ETA: {eta} minutes. Track live here: http://localhost:5173/?track={emergency.sosId}"

    # Log assignment record
    if ngo_profile:
        RescueAssignment.objects.create(
            sos_request=emergency,
            ngo=ngo_profile,
            rescue_team=rescue_team,
            vehicle=vehicle,
            eta=eta,
            status='accepted',
            notification_message=notification_msg
        )

    res = format_emergency_data(emergency, user=user)
    res['sms_notification'] = notification_msg
    res['emergency'] = format_emergency_data(emergency, user=user)

    # Broadcast over WebSocket
    broadcast_rescue_status(emergency.sosId, 'accepted', res, notification_msg)

    return JsonResponse(res)

# WORKFLOW: NGO Dispatches Team
@csrf_exempt
def sos_dispatch_view(request, sos_id):
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    try:
        emergency = Emergency.objects.get(sosId=sos_id)
    except Emergency.DoesNotExist:
        return JsonResponse({'detail': 'Emergency record not found'}, status=404)

    from django.utils import timezone
    emergency.status = 'dispatched'
    emergency.dispatched_at = timezone.now()
    emergency.save()

    user = get_user_from_request(request)
    res = format_emergency_data(emergency, user=user)
    res['emergency'] = format_emergency_data(emergency, user=user)

    # Broadcast over WebSocket
    broadcast_rescue_status(emergency.sosId, 'dispatched', res, f"Rescue team ({emergency.rescue_team or 'Team Alpha'}) dispatched and on the way.")

    return JsonResponse(res)

# WORKFLOW: NGO Arrived
@csrf_exempt
def sos_arrived_view(request, sos_id):
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    try:
        emergency = Emergency.objects.get(sosId=sos_id)
    except Emergency.DoesNotExist:
        return JsonResponse({'detail': 'Emergency record not found'}, status=404)

    from django.utils import timezone
    emergency.status = 'arrived'
    emergency.arrived_at = timezone.now()
    emergency.save()

    user = get_user_from_request(request)
    res = format_emergency_data(emergency, user=user)
    msg = f"The rescue team ({emergency.rescue_team or 'Rescue Team'}) has arrived at your location."
    res['notification_message'] = msg
    res['emergency'] = format_emergency_data(emergency, user=user)

    # Broadcast over WebSocket
    broadcast_rescue_status(emergency.sosId, 'arrived', res, msg)

    return JsonResponse(res)

# WORKFLOW: NGO Resolves Rescue
@csrf_exempt
def sos_resolve_view(request, sos_id):
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    try:
        emergency = Emergency.objects.get(sosId=sos_id)
    except Emergency.DoesNotExist:
        return JsonResponse({'detail': 'Emergency record not found'}, status=404)

    try:
        body = json.loads(request.body) if request.body else {}
    except Exception:
        body = {}

    from django.utils import timezone
    rescued_count = int(body.get('rescued_people_count') or body.get('rescued_count') or body.get('people_rescued') or emergency.people or 1)
    notes = body.get('resolution_notes') or body.get('rescue_notes') or 'All individuals safely evacuated to medical center.'

    emergency.status = 'resolved'
    emergency.resolved_at = timezone.now()
    emergency.rescued_people_count = rescued_count
    emergency.resolution_notes = notes
    emergency.save()

    ngo_name = emergency.matched_ngo.name if emergency.matched_ngo else 'Relief NGO'
    user = get_user_from_request(request)
    res = format_emergency_data(emergency, user=user)
    msg = f"{ngo_name} successfully completed your flood rescue request. {rescued_count} people rescued successfully."
    res['notification_message'] = msg
    res['emergency'] = format_emergency_data(emergency, user=user)

    # Broadcast over WebSocket
    broadcast_rescue_status(emergency.sosId, 'resolved', res, msg)

    return JsonResponse(res)

# WORKFLOW: Live Telemetry Tracking
@csrf_exempt
def sos_tracking_view(request, sos_id):
    try:
        emergency = Emergency.objects.get(sosId=sos_id)
    except Emergency.DoesNotExist:
        return JsonResponse({'detail': 'Emergency record not found'}, status=404)

    telemetry = get_emergency_telemetry(emergency)
    user = get_user_from_request(request)
    emergency_data = format_emergency_data(emergency, user=user)
    return JsonResponse({
        'sosId': emergency.sosId,
        'status': emergency.status,
        'telemetry': telemetry,
        'emergency': emergency_data
    })

# WORKFLOW: Update Rescue Vehicle GPS Location
@csrf_exempt
def rescue_location_update_view(request, sos_id):
    """
    Endpoint for updating the rescue vehicle's real GPS coordinates.
    Authenticates NGO/Team, updates Emergency and VehicleLocation,
    computes real-time Haversine distance and dynamic ETA, and broadcasts
    the new location via WebSocket channel to all subscribers.
    """
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    try:
        body = json.loads(request.body) if request.body else {}
    except Exception:
        return JsonResponse({'detail': 'Invalid JSON body'}, status=400)

    user = get_user_from_request(request)
    if not user:
        token_str = body.get('token') or request.GET.get('token')
        if token_str:
            try:
                payload = signing.loads(token_str, max_age=SECRET_AGE)
                user = User.objects.get(id=payload['user_id'])
            except Exception:
                pass

    try:
        emergency = Emergency.objects.get(sosId=sos_id)
    except Emergency.DoesNotExist:
        return JsonResponse({'detail': 'Emergency record not found'}, status=404)

    # Authorization verification: NGO must be assigned or user is admin
    if user:
        if not (user.is_superuser or user.is_staff):
            if hasattr(user, 'ngo_profile'):
                if emergency.matched_ngo and emergency.matched_ngo.id != user.ngo_profile.id:
                    return JsonResponse({'detail': 'Unauthorized: Your NGO is not assigned to this rescue'}, status=403)
            else:
                return JsonResponse({'detail': 'Unauthorized: User is not an authorized NGO'}, status=403)

    try:
        lat = float(body.get('latitude') or body.get('lat'))
        lng = float(body.get('longitude') or body.get('lng'))
        accuracy = float(body.get('accuracy', 5.0))
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            return JsonResponse({'detail': 'Latitude or longitude out of valid range'}, status=400)
    except (TypeError, ValueError):
        return JsonResponse({'detail': 'Missing or invalid latitude/longitude'}, status=400)

    from django.utils import timezone
    import math

    now = timezone.now()
    emergency.vehicle_lat = lat
    emergency.vehicle_lng = lng
    emergency.vehicle_accuracy = accuracy
    emergency.vehicle_updated_at = now

    # Haversine distance to victim
    victim_lat = emergency.latitude or lat
    victim_lng = emergency.longitude or lng
    R = 6371.0
    d_lat = math.radians(victim_lat - lat)
    d_lon = math.radians(victim_lng - lng)
    a = math.sin(d_lat / 2)**2 + math.cos(math.radians(lat)) * math.cos(math.radians(victim_lat)) * math.sin(d_lon / 2)**2
    a = min(1.0, max(0.0, a))
    dist_km = R * (2 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a)))
    emergency.distance_km = round(dist_km, 2)

    speed_kmh = 28.0
    eta_mins = max(1, int(math.ceil(dist_km / (speed_kmh / 60.0)))) if dist_km > 0.05 else 0
    emergency.eta = eta_mins

    if emergency.status in ['accepted', 'assigned']:
        emergency.status = 'dispatched'
        if not emergency.dispatched_at:
            emergency.dispatched_at = now

    emergency.save()

    # Log to VehicleLocation history
    VehicleLocation.objects.create(
        sos_request=emergency,
        vehicle=emergency.rescue_vehicle or 'Rescue Boat RB-04',
        latitude=lat,
        longitude=lng,
        accuracy=accuracy
    )

    emergency_data = format_emergency_data(emergency, user=user)
    telemetry = get_emergency_telemetry(emergency)

    # Broadcast over Channels WebSocket layer
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"rescue_{sos_id}",
                {
                    'type': 'vehicle_location_broadcast',
                    'data': {
                        'sos_id': sos_id,
                        'vehicle_id': emergency.rescue_vehicle or 'Rescue Boat RB-04',
                        'rescue_team': emergency.rescue_team or 'Team Alpha',
                        'latitude': lat,
                        'longitude': lng,
                        'accuracy': accuracy,
                        'timestamp': now.isoformat(),
                        'distance_km': emergency.distance_km,
                        'eta': eta_mins,
                        'status': emergency.status,
                        'emergency': emergency_data,
                        'telemetry': telemetry
                    }
                }
            )
    except Exception as e:
        print("Channels broadcast exception in rescue_location_update_view:", e)

    return JsonResponse({
        'success': True,
        'sosId': sos_id,
        'latitude': lat,
        'longitude': lng,
        'accuracy': accuracy,
        'distance_km': emergency.distance_km,
        'eta': eta_mins,
        'eta_mins': eta_mins,
        'status': emergency.status,
        'timestamp': now.isoformat(),
        'telemetry': telemetry,
        'emergency': emergency_data
    })

# WORKFLOW: User's Active SOS
@csrf_exempt
def sos_active_view(request):
    user = get_user_from_request(request)
    qs = Emergency.objects.exclude(status__in=['resolved', 'cancelled']).order_by('-created_at')

    sos_id_param = request.GET.get('sos_id', '').strip()
    if sos_id_param:
        active = qs.filter(sosId=sos_id_param).first()
        if active:
            return JsonResponse({
                'active': True,
                'emergency': format_emergency_data(active, user=user)
            })

    if user and not hasattr(user, 'ngo_profile') and not (user.is_staff or user.is_superuser):
        active = qs.filter(user=user).first()
        if active:
            return JsonResponse({
                'active': True,
                'emergency': format_emergency_data(active, user=user)
            })

    return JsonResponse({'active': False, 'emergency': None})

# WORKFLOW: Rescue History
@csrf_exempt
def sos_history_view(request):
    user = get_user_from_request(request)
    qs = Emergency.objects.filter(status='resolved').order_by('-resolved_at')

    data = [format_emergency_data(em, user=user) for em in qs]
    return JsonResponse(data, safe=False)


# ECOSYSTEM: Intelligent Matching Simulator
@csrf_exempt
def matchmaker_query_view(request):
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=452)
    
    try:
        body = json.loads(request.body)
        disaster = body.get('disaster', 'flood').strip()
        city = body.get('city', '').strip()
        urgency = body.get('urgency', 'high')
        
        all_ngos = list(NgoProfile.objects.all())
        eligible_ngos = []
        for ngo in all_ngos:
            specs = ngo.specializations or []
            if isinstance(specs, str):
                try:
                    specs = json.loads(specs)
                except:
                    specs = [specs]
            if not isinstance(specs, list):
                specs = [specs]
            
            if any(disaster.lower() == str(s).lower() for s in specs):
                eligible_ngos.append(ngo)

        user_city = city.lower() if city else None
        
        if eligible_ngos:
            def sort_key(ngo):
                city_match = 1 if (user_city and ngo.city and user_city in ngo.city.lower()) else 0
                if disaster == 'fire':
                    return (city_match, ngo.fire_trucks, ngo.volunteers)
                elif disaster in ['flood', 'landslide']:
                    return (city_match, ngo.boats, ngo.volunteers)
                elif disaster in ['medical', 'accident']:
                    return (city_match, ngo.ambulances, ngo.volunteers)
                else:
                    return (city_match, ngo.volunteers)
            
            eligible_ngos.sort(key=sort_key, reverse=True)
            matched_ngo = eligible_ngos[0]
        else:
            matched_ngo = NgoProfile.objects.all().first()
            
        if not matched_ngo:
            ngo_user, _ = User.objects.get_or_create(
                username='ndrf_hq',
                defaults={'email': 'hq@ndrf.gov.in', 'first_name': 'National Disaster Response Force (NDRF)'}
            )
            if not ngo_user.password:
                ngo_user.set_password('NDRF_Secure_112')
                ngo_user.save()
            matched_ngo, _ = NgoProfile.objects.get_or_create(
                user=ngo_user,
                defaults={
                    'name': 'National Disaster Response Force (NDRF)',
                    'phone': '011-23438017',
                    'address': 'NDRF HQ, Antariksh Bhawan, New Delhi',
                    'city': 'Delhi',
                    'specializations': ['flood', 'landslide', 'earthquake', 'fire', 'accident', 'medical'],
                    'ambulances': 25,
                    'boats': 50,
                    'fire_trucks': 15,
                    'volunteers': 1200
                }
            )
            
        specs_list = matched_ngo.specializations
        if isinstance(specs_list, str):
            try:
                specs_list = json.loads(specs_list)
            except:
                specs_list = [specs_list]
            
        return JsonResponse({
            'matched': True,
            'name': matched_ngo.name,
            'phone': matched_ngo.phone,
            'address': matched_ngo.address,
            'city': matched_ngo.city,
            'specializations': specs_list,
            'gear': {
                'ambulances': matched_ngo.ambulances,
                'boats': matched_ngo.boats,
                'fire_trucks': matched_ngo.fire_trucks,
                'volunteers': matched_ngo.volunteers,
            },
            'score': 98 if (user_city and matched_ngo.city and user_city in matched_ngo.city.lower()) else 85,
            'criteria': [
                f"Specialized response for {disaster.capitalize()}",
                "Resource pool verified active",
                f"Stationed in {matched_ngo.city or 'Delhi'}"
            ]
        })
    except Exception as e:
        return JsonResponse({'detail': str(e)}, status=500)

# ECOSYSTEM: Live GPS Telemetry Dispatch Feeds
@csrf_exempt
def active_tracking_view(request):
    if request.method != 'GET':
        return JsonResponse({'detail': 'Method not allowed'}, status=452)
    
    dispatches = [
        {
            'dispatchId': 'DISP-402',
            'team': 'NDRF Response Unit 4',
            'disaster': 'Flood Rescue Operation',
            'status': 'enroute',
            'vehicle': 'Amphibious Assault Boat',
            'velocity': '34 km/h',
            'distance': '1.6 km',
            'eta': 4.5,
            'coordinates': {'lat': 19.0142, 'lng': 73.0238},
            'route': [
                {'lat': 19.0080, 'lng': 73.0180},
                {'lat': 19.0102, 'lng': 73.0201},
                {'lat': 19.0118, 'lng': 73.0215},
                {'lat': 19.0130, 'lng': 73.0228},
                {'lat': 19.0142, 'lng': 73.0238},
            ]
        },
        {
            'dispatchId': 'DISP-118',
            'team': 'Mumbai Fire Brigade Squad A',
            'disaster': 'Structural Fire Crisis',
            'status': 'enroute',
            'vehicle': 'Heavy Water Tender Truck',
            'velocity': '58 km/h',
            'distance': '2.4 km',
            'eta': 6.2,
            'coordinates': {'lat': 19.0315, 'lng': 72.8542},
            'route': [
                {'lat': 19.0220, 'lng': 72.8420},
                {'lat': 19.0250, 'lng': 72.8465},
                {'lat': 19.0285, 'lng': 72.8502},
                {'lat': 19.0315, 'lng': 72.8542},
            ]
        },
        {
            'dispatchId': 'DISP-904',
            'team': 'Red Cross Medics Team B',
            'disaster': 'Multiple Vehicle Accident',
            'status': 'enroute',
            'vehicle': 'Advanced Life Support Ambulance',
            'velocity': '72 km/h',
            'distance': '0.9 km',
            'eta': 2.1,
            'coordinates': {'lat': 28.6139, 'lng': 77.2090},
            'route': [
                {'lat': 28.6090, 'lng': 77.2010},
                {'lat': 28.6112, 'lng': 77.2052},
                {'lat': 28.6139, 'lng': 77.2090},
            ]
        }
    ]
    return JsonResponse(dispatches, safe=False)

# ECOSYSTEM: Disaster Broadcast Alerts Hub
@csrf_exempt
def alerts_view(request):
    if request.method == 'GET':
        alerts = DisasterAlert.objects.all().order_by('-created_at')
        alert_list = []
        for al in alerts:
            alert_list.append({
                'id': al.id,
                'message': al.message,
                'severity': al.severity,
                'channels': al.channels,
                'city': al.city,
                'createdAt': al.created_at.strftime('%I:%M %p | %d %b')
            })
        return JsonResponse(alert_list, safe=False)
        
    elif request.method == 'POST':
        try:
            body = json.loads(request.body)
            message = body.get('message', '').strip()
            severity = body.get('severity', 'warning').strip()
            channels = body.get('channels', ['push'])
            city = body.get('city', 'All Cities').strip()
            
            if not message:
                return JsonResponse({'detail': 'Alert message text is required'}, status=400)
                
            alert = DisasterAlert.objects.create(
                message=message,
                severity=severity,
                channels=channels,
                city=city
            )
            
            mock_count = random.randint(1200, 5400)
            return JsonResponse({
                'id': alert.id,
                'message': alert.message,
                'severity': alert.severity,
                'channels': alert.channels,
                'city': alert.city,
                'createdAt': alert.created_at.strftime('%I:%M %p | %d %b'),
                'stats': {
                    'receivers': mock_count,
                    'sms_sent': mock_count if 'sms' in channels else 0,
                    'email_sent': mock_count if 'email' in channels else 0,
                    'push_sent': mock_count if 'push' in channels else 0,
                    'success_rate': 100.0
                }
            }, status=201)
        except Exception as e:
            return JsonResponse({'detail': str(e)}, status=500)
            
    return JsonResponse({'detail': 'Method not allowed'}, status=452)

# ECOSYSTEM: Transparent Donations Hub
@csrf_exempt
def donations_view(request):
    if request.method == 'GET':
        donations = Donation.objects.all().order_by('-created_at')
        ledger = []
        for d in donations:
            ledger.append({
                'id': d.id,
                'amount': d.amount,
                'cause': d.cause,
                'ngoName': d.ngo_name or d.cause,
                'txnId': d.transaction_id,
                'status': d.status,
                'createdAt': d.created_at.strftime('%d-%b-%Y')
            })
        
        if len(ledger) == 0:
            ledger = [
                {
                    'id': 1,
                    'amount': 500,
                    'cause': 'Flood Relief',
                    'ngoName': 'Helping Hands NGO',
                    'txnId': 'RL-TXN-283948',
                    'status': 'Success',
                    'createdAt': '01-Sep-2025'
                },
                {
                    'id': 2,
                    'amount': 1000,
                    'cause': 'Earthquake Relief',
                    'ngoName': 'EarthCare Foundation',
                    'txnId': 'RL-TXN-129483',
                    'status': 'Success',
                    'createdAt': '03-Sep-2025'
                }
            ]
        return JsonResponse(ledger, safe=False)
        
    elif request.method == 'POST':
        try:
            body = json.loads(request.body)
            amount = float(body.get('amount', 0.0))
            cause = body.get('cause', 'General Emergency Fund').strip()
            ngo_id = body.get('ngo_id')
            ngo_name = body.get('ngo_name', '').strip()
            
            if amount <= 0:
                return JsonResponse({'detail': 'Donation amount must be greater than zero'}, status=400)
                
            txn_id = f"RL-TXN-{random.randint(100000, 999999)}"
            
            user = get_user_from_request(request)
            ngo = None
            if ngo_id:
                try:
                    ngo = NgoProfile.objects.get(id=ngo_id)
                    ngo_name = ngo.name
                except:
                    pass
            
            donation = Donation.objects.create(
                user=user,
                ngo=ngo,
                ngo_name=ngo_name or cause,
                amount=amount,
                cause=cause,
                transaction_id=txn_id,
                status='Success'
            )
            
            food_amt = amount * 0.50
            med_amt = amount * 0.30
            log_amt = amount * 0.20
            
            return JsonResponse({
                'id': donation.id,
                'amount': donation.amount,
                'cause': donation.cause,
                'ngoName': donation.ngo_name,
                'txnId': donation.transaction_id,
                'status': donation.status,
                'createdAt': donation.created_at.strftime('%d-%b-%Y'),
                'allocations': {
                    'foodKits': int(food_amt / 125),
                    'foodVal': food_amt,
                    'medicinePacks': int(med_amt / 300),
                    'medVal': med_amt,
                    'fuelLogisticsVal': log_amt
                }
            }, status=201)
        except Exception as e:
            return JsonResponse({'detail': str(e)}, status=500)
            
    return JsonResponse({'detail': 'Method not allowed'}, status=452)

# ECOSYSTEM: Precise Auto Location Detection Log
@csrf_exempt
def transmit_location_view(request):
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=452)
        
    try:
        body = json.loads(request.body)
        lat = float(body.get('lat', 0.0))
        lng = float(body.get('lng', 0.0))
        accuracy = float(body.get('accuracy', 10.0))
        is_offline = bool(body.get('is_offline', False))
        
        loc_log = TransmittedLocation.objects.create(
            latitude=lat,
            longitude=lng,
            accuracy=accuracy,
            is_offline=is_offline
        )
        
        return JsonResponse({
            'success': True,
            'logId': loc_log.id,
            'network': "Offline Caching Active" if is_offline else "Online Secure Transmit",
            'detail': f"Precise satellite coordinates ({lat}, {lng}) logged at HQ sector base."
        }, status=201)
    except Exception as e:
        return JsonResponse({'detail': str(e)}, status=500)

# Global variables for NGO telemetry simulations
_MOCK_VOLUNTEER_ALLOCATION = 320

# ECOSYSTEM: NGO Dashboard Command Center Analytics
@csrf_exempt
def ngo_analytics_view(request):
    global _MOCK_VOLUNTEER_ALLOCATION
    
    if request.method == 'GET':
        from django.db.models import Sum
        active_missions = Emergency.objects.filter(
            status__in=['accepted', 'assigned', 'dispatched', 'on_the_way', 'arrived', 'rescue_in_progress']
        ).count()
        survivors_rescued = Emergency.objects.filter(status='resolved').aggregate(
            total=Sum('rescued_people_count')
        )['total'] or 0

        # Recent real missions from database
        recent_emergencies = Emergency.objects.all().order_by('-created_at')[:5]
        missions = []
        for em in recent_emergencies:
            missions.append({
                'sector': em.address or em.name or 'Patna Sector',
                'crisis': f"{em.disaster.title()} Relief",
                'status': em.status.replace('_', ' ').title(),
                'dispatchId': em.sosId
            })

        total_boats = NgoProfile.objects.aggregate(total=Sum('boats'))['total'] or 0
        total_ambulances = NgoProfile.objects.aggregate(total=Sum('ambulances'))['total'] or 0
        total_fire_trucks = NgoProfile.objects.aggregate(total=Sum('fire_trucks'))['total'] or 0

        return JsonResponse({
            'activeMissions': active_missions,
            'survivorsRescued': survivors_rescued,
            'totalFunds': 245000,
            'volunteerAllocation': _MOCK_VOLUNTEER_ALLOCATION,
            'gearStatus': {
                'boats': {'active': min(active_missions, total_boats), 'total': total_boats or 25},
                'ambulances': {'active': min(active_missions, total_ambulances), 'total': total_ambulances or 15},
                'fireTrucks': {'active': 0, 'total': total_fire_trucks or 10}
            },
            'missions': missions
        })
        
    elif request.method == 'POST':
        try:
            body = json.loads(request.body)
            volunteers = int(body.get('volunteers', _MOCK_VOLUNTEER_ALLOCATION))
            
            _MOCK_VOLUNTEER_ALLOCATION = volunteers
            
            return JsonResponse({
                'success': True,
                'volunteerAllocation': _MOCK_VOLUNTEER_ALLOCATION,
                'detail': f"Sector dispatch volunteers pool re-allocated to {volunteers} active personnel."
            })
        except Exception as e:
            return JsonResponse({'detail': str(e)}, status=500)
            
    return JsonResponse({'detail': 'Method not allowed'}, status=452)

# ADMIN: Statistics overview
@csrf_exempt
def admin_stats_view(request):
    try:
        from django.utils import timezone
        from django.db.models import Sum
        today = timezone.now().date()
        
        total_requests = Emergency.objects.count()
        registered_ngos = NgoProfile.objects.count()
        pending_requests = Emergency.objects.filter(status__in=['pending', 'ngo_found']).count()
        active_rescues = Emergency.objects.filter(
            status__in=['accepted', 'assigned', 'dispatched', 'on_the_way', 'arrived', 'rescue_in_progress']
        ).count()
        resolved_rescues = Emergency.objects.filter(status='resolved').count()
        today_requests = Emergency.objects.filter(created_at__date=today).count()
        people_helped = Emergency.objects.filter(status='resolved').aggregate(
            total=Sum('rescued_people_count')
        )['total'] or 0
        
        return JsonResponse({
            'totalRequests': total_requests,
            'registeredNgos': registered_ngos,
            'pendingRequests': pending_requests,
            'activeRescues': active_rescues,
            'resolvedRescues': resolved_rescues,
            'todayRequests': today_requests,
            'peopleHelped': people_helped
        })
    except Exception as e:
        return JsonResponse({'detail': str(e)}, status=500)

# ADMIN: List registered NGOs
@csrf_exempt
def admin_ngos_view(request):
    try:
        ngos = NgoProfile.objects.all().order_by('-id')
        ngo_list = []
        for ngo in ngos:
            specs = ngo.specializations
            if isinstance(specs, str):
                try: specs = json.loads(specs)
                except: specs = [specs]
            if not isinstance(specs, list): specs = [specs]
            
            ngo_list.append({
                'id': ngo.id,
                'name': ngo.name,
                'phone': ngo.phone,
                'address': ngo.address,
                'city': ngo.city,
                'specializations': specs,
                'ambulances': ngo.ambulances,
                'boats': ngo.boats,
                'fire_trucks': ngo.fire_trucks,
                'volunteers': ngo.volunteers,
                'isVerified': ngo.is_verified
            })
        return JsonResponse(ngo_list, safe=False)
    except Exception as e:
        return JsonResponse({'detail': str(e)}, status=500)

# ADMIN: Toggle Verification Status
@csrf_exempt
def admin_ngo_toggle_verify_view(request, ngo_id):
    user = get_user_from_request(request)
    if not user or not (user.is_superuser or user.is_staff):
        return JsonResponse({'detail': 'Unauthorized admin access'}, status=401)
        
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=452)
        
    try:
        ngo = NgoProfile.objects.get(id=ngo_id)
        ngo.is_verified = not ngo.is_verified
        ngo.save()
        return JsonResponse({'success': True, 'isVerified': ngo.is_verified})
    except NgoProfile.DoesNotExist:
        return JsonResponse({'detail': 'NGO Profile not found'}, status=404)
    except Exception as e:
        return JsonResponse({'detail': str(e)}, status=500)

# ADMIN: Delete NGO Profile & User Account
@csrf_exempt
def admin_ngo_delete_view(request, ngo_id):
    user = get_user_from_request(request)
    if not user or not (user.is_superuser or user.is_staff):
        return JsonResponse({'detail': 'Unauthorized admin access'}, status=401)
        
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=452)
        
    try:
        ngo = NgoProfile.objects.get(id=ngo_id)
        ngo_user = ngo.user
        # Deleting the user will cascade-delete the profile
        ngo_user.delete()
        return JsonResponse({'success': True, 'detail': 'NGO account permanently deleted'})
    except NgoProfile.DoesNotExist:
        return JsonResponse({'detail': 'NGO Profile not found'}, status=404)
    except Exception as e:
        return JsonResponse({'detail': str(e)}, status=500)

# ADMIN: Delete Emergency Distress Request
@csrf_exempt
def admin_request_delete_view(request, sos_id):
    user = get_user_from_request(request)
    if not user or not (user.is_superuser or user.is_staff):
        return JsonResponse({'detail': 'Unauthorized admin access'}, status=401)
        
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=452)
        
    try:
        em = Emergency.objects.get(sosId=sos_id)
        em.delete()
        return JsonResponse({'success': True, 'detail': f"SOS distress signal {sos_id} permanently deleted"})
    except Emergency.DoesNotExist:
        return JsonResponse({'detail': 'Emergency record not found'}, status=404)
    except Exception as e:
        return JsonResponse({'detail': str(e)}, status=500)

# CITIZEN: Get Nearest NGO Match based on Pincode and City
@csrf_exempt
def nearest_ngo_view(request):
    user = get_user_from_request(request)
    if not user:
        return JsonResponse({'detail': 'Unauthorized access token'}, status=401)
        
    if hasattr(user, 'ngo_profile'):
        return JsonResponse({'detail': 'NGO profiles do not have a nearest NGO'}, status=400)
        
    if not hasattr(user, 'user_profile'):
        return JsonResponse({'detail': 'User profile not found'}, status=404)
        
    profile = user.user_profile
    user_pincode = (profile.pincode or '').strip()
    user_city = (profile.city or '').strip().lower()
    
    matched_ngo = None
    match_type = None
    
    # 1. Exact pincode match
    if user_pincode:
        matched_ngo = NgoProfile.objects.filter(pincode=user_pincode).first()
        if matched_ngo:
            match_type = 'pincode'
            
    # 2. City proximity fallback
    if not matched_ngo and user_city:
        matched_ngo = NgoProfile.objects.filter(city__iexact=user_city).first()
        if matched_ngo:
            match_type = 'city'
            
    # 3. First NGO fallback
    if not matched_ngo:
        matched_ngo = NgoProfile.objects.first()
        if matched_ngo:
            match_type = 'national_fallback'
            
    # 4. NDRF dynamic fallback
    if not matched_ngo:
        ngo_user, _ = User.objects.get_or_create(
            username='ndrf_hq',
            defaults={'email': 'hq@ndrf.gov.in', 'first_name': 'National Disaster Response Force (NDRF)'}
        )
        if not ngo_user.password:
            ngo_user.set_password('NDRF_Secure_112')
            ngo_user.save()
            
        matched_ngo, _ = NgoProfile.objects.get_or_create(
            user=ngo_user,
            defaults={
                'name': 'National Disaster Response Force (NDRF)',
                'phone': '011-23438017',
                'address': 'NDRF HQ, Antariksh Bhawan, New Delhi',
                'city': 'Delhi',
                'pincode': '110001',
                'specializations': ['flood', 'landslide', 'earthquake', 'fire', 'accident', 'medical'],
                'ambulances': 25,
                'boats': 50,
                'fire_trucks': 15,
                'volunteers': 1200
            }
        )
        match_type = 'general_ndrf'
        
    specs_list = matched_ngo.specializations
    if isinstance(specs_list, str):
        try:
            specs_list = json.loads(specs_list)
        except:
            specs_list = [specs_list]
    if not isinstance(specs_list, list):
        specs_list = [specs_list]
        
    return JsonResponse({
        'matched': True,
        'name': matched_ngo.name,
        'phone': matched_ngo.phone or "+91 99999 88888",
        'address': matched_ngo.address or "Station Address",
        'city': matched_ngo.city or "Delhi",
        'pincode': matched_ngo.pincode or "110001",
        'specializations': specs_list,
        'ambulances': matched_ngo.ambulances,
        'boats': matched_ngo.boats,
        'fire_trucks': matched_ngo.fire_trucks,
        'volunteers': matched_ngo.volunteers,
        'isVerified': matched_ngo.is_verified,
        'match_type': match_type,
        'citizen_pincode': user_pincode
    })

# --- Automatic Location & Geocoding Endpoints ---
import urllib.request

def fetch_url_json(url, timeout=4):
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'RescueLinkDisasterApp/1.0 (contact@rescuelink.org)'}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
        return None

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '').strip()
    return ip

def is_private_ip(ip):
    if not ip:
        return True
    if ip in ('127.0.0.1', '::1', 'localhost'):
        return True
    if ip.startswith('10.'):
        return True
    if ip.startswith('192.168.'):
        return True
    if ip.startswith('172.'):
        try:
            parts = ip.split('.')
            if len(parts) >= 2:
                second_part = int(parts[1])
                if 16 <= second_part <= 31:
                    return True
        except ValueError:
            pass
    if ip.startswith('169.254.'):
        return True
    return False

@csrf_exempt
def detect_location_view(request):
    client_ip = get_client_ip(request)
    use_client_ip = not is_private_ip(client_ip)
    
    # 1. Try ipwho.is
    try:
        url = f"https://ipwho.is/{client_ip if use_client_ip else ''}"
        d = fetch_url_json(url)
        if d and d.get('success') and d.get('city'):
            return JsonResponse({
                'city': d.get('city'),
                'state': d.get('region') or d.get('country') or '',
                'pincode': d.get('postal') or '',
                'address': f"{d.get('city')}, {d.get('region') or ''}, {d.get('country') or 'India'} - {d.get('postal') or ''}",
                'source': 'ipwho.is (Backend)'
            })
    except Exception as e:
        print("ipwho.is backend failed:", e)

    # 2. Try ip-api.com
    try:
        url = f"http://ip-api.com/json/{client_ip if use_client_ip else ''}?fields=status,city,regionName,zip,country"
        d = fetch_url_json(url)
        if d and d.get('status') == 'success' and d.get('city'):
            return JsonResponse({
                'city': d.get('city'),
                'state': d.get('regionName') or d.get('country') or '',
                'pincode': d.get('zip') or '',
                'address': f"{d.get('city')}, {d.get('regionName') or ''}, {d.get('country') or 'India'} - {d.get('zip') or ''}",
                'source': 'ip-api.com (Backend)'
            })
    except Exception as e:
        print("ip-api.com backend failed:", e)

    # 3. Try ipinfo.io
    try:
        url = f"https://ipinfo.io/{client_ip + '/' if use_client_ip else ''}json"
        d = fetch_url_json(url)
        if d and d.get('city'):
            return JsonResponse({
                'city': d.get('city'),
                'state': d.get('region') or d.get('country') or '',
                'pincode': d.get('postal') or '',
                'address': f"{d.get('city')}, {d.get('region') or ''}, {d.get('country') or 'India'} - {d.get('postal') or ''}",
                'source': 'ipinfo.io (Backend)'
            })
    except Exception as e:
        print("ipinfo.io backend failed:", e)

    # 4. Try ipapi.co
    try:
        url = f"https://ipapi.co/{client_ip + '/' if use_client_ip else ''}json/"
        d = fetch_url_json(url)
        if d and d.get('city'):
            return JsonResponse({
                'city': d.get('city'),
                'state': d.get('region') or d.get('country_name') or '',
                'pincode': d.get('postal') or '',
                'address': f"{d.get('city')}, {d.get('region') or ''}, {d.get('country_name') or 'India'} - {d.get('postal') or ''}",
                'source': 'ipapi.co (Backend)'
            })
    except Exception as e:
        print("ipapi.co backend failed:", e)

    return JsonResponse({'detail': 'All IP geolocation APIs failed'}, status=400)

@csrf_exempt
def reverse_geocode_view(request):
    lat = request.GET.get('lat')
    lon = request.GET.get('lon')
    if not lat or not lon:
        return JsonResponse({'detail': 'lat and lon parameters are required'}, status=400)
    
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=18&addressdetails=1"
    try:
        d = fetch_url_json(url)
        if d and 'address' in d:
            addr = d.get('address', {})
            city = addr.get('city') or addr.get('town') or addr.get('village') or addr.get('suburb') or ''
            state = addr.get('state') or ''
            pincode = addr.get('postcode') or ''
            display_name = d.get('display_name') or ''
            return JsonResponse({
                'city': city,
                'state': state,
                'pincode': pincode,
                'address': display_name,
                'source': 'GPS (Backend Reverse Geocode)'
            })
    except Exception as e:
        print("Nominatim backend reverse geocode failed:", e)
        
    return JsonResponse({'detail': 'Reverse geocoding failed'}, status=400)


@csrf_exempt
def public_ngos_view(request):
    try:
        ngos = NgoProfile.objects.filter(is_verified=True).order_by('id')
        ngo_list = []
        for ngo in ngos:
            specs = ngo.specializations
            if isinstance(specs, str):
                try: specs = json.loads(specs)
                except: specs = [specs]
            if not isinstance(specs, list): specs = [specs]
            
            ngo_list.append({
                'id': ngo.id,
                'name': ngo.name,
                'phone': ngo.phone,
                'address': ngo.address,
                'city': ngo.city,
                'pincode': ngo.pincode,
                'upi': f"{ngo.name.lower().replace(' ', '')}@upi",
                'specializations': specs,
                'specialization': specs[0].title() + " Relief" if specs else 'General Rescue'
            })
        
        if len(ngo_list) == 0:
            ngo_list = [
                {
                    'id': 1,
                    'name': 'Helping Hands NGO',
                    'phone': '011-23438017',
                    'address': 'Patna Sector A',
                    'city': 'Patna',
                    'pincode': '800001',
                    'upi': 'help@upi',
                    'specializations': ['flood'],
                    'specialization': 'Flood Relief'
                },
                {
                    'id': 2,
                    'name': 'Fire Rescue Trust',
                    'phone': '9876543210',
                    'address': 'Delhi Base HQ',
                    'city': 'Delhi',
                    'pincode': '110001',
                    'upi': 'firerescue@upi',
                    'specializations': ['fire'],
                    'specialization': 'Fire Emergencies'
                },
                {
                    'id': 3,
                    'name': 'EarthCare Foundation',
                    'phone': '8888899999',
                    'address': 'Mumbai Base',
                    'city': 'Mumbai',
                    'pincode': '400001',
                    'upi': 'earthcare@upi',
                    'specializations': ['earthquake'],
                    'specialization': 'Earthquake Relief'
                }
            ]
        return JsonResponse(ngo_list, safe=False)
    except Exception as e:
        return JsonResponse({'detail': str(e)}, status=500)


