import json
import math
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from asgiref.sync import sync_to_async
from django.utils import timezone
from django.core import signing

def calculate_haversine_distance(lat1, lon1, lat2, lon2):
    """Computes great-circle distance between two points in kilometers."""
    R = 6371.0 # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    a = min(1.0, max(0.0, a))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c

def get_initial_emergency_data(sos_id):
    """Synchronous helper to fetch emergency details and telemetry for initial WebSocket handshake."""
    from .models import Emergency
    from .views import format_emergency_data, get_emergency_telemetry
    try:
        emergency = Emergency.objects.get(sosId=sos_id)
        telemetry = get_emergency_telemetry(emergency)
        emergency_data = format_emergency_data(emergency)
        return {
            'exists': True,
            'status': emergency.status,
            'telemetry': telemetry,
            'emergency': emergency_data
        }
    except Emergency.DoesNotExist:
        return {'exists': False}

def update_vehicle_position_db(sos_id, lat, lng, accuracy=5.0, user_token=None):
    """
    Synchronous helper to validate and update the rescue vehicle location in database,
    logging to VehicleLocation and calculating real-time Haversine distance and ETA.
    """
    from .models import Emergency, VehicleLocation, User
    from .views import format_emergency_data, SECRET_AGE

    try:
        emergency = Emergency.objects.get(sosId=sos_id)
    except Emergency.DoesNotExist:
        return {'success': False, 'error': 'Emergency not found'}

    # If user_token provided, verify user has rights
    if user_token:
        try:
            payload = signing.loads(user_token, max_age=SECRET_AGE)
            user = User.objects.get(id=payload['user_id'])
            # Superuser/staff or assigned NGO check
            if not (user.is_superuser or user.is_staff):
                if hasattr(user, 'ngo_profile'):
                    if emergency.matched_ngo and emergency.matched_ngo.id != user.ngo_profile.id:
                        return {'success': False, 'error': 'Unauthorized NGO for this rescue'}
                else:
                    return {'success': False, 'error': 'User is not an authorized NGO'}
        except Exception as e:
            return {'success': False, 'error': f'Auth validation error: {str(e)}'}

    # Validate coordinate bounds
    try:
        lat = float(lat)
        lng = float(lng)
        accuracy = float(accuracy) if accuracy is not None else 5.0
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            return {'success': False, 'error': 'Coordinates out of bounds'}
    except (ValueError, TypeError):
        return {'success': False, 'error': 'Invalid coordinate numbers'}

    now = timezone.now()
    emergency.vehicle_lat = lat
    emergency.vehicle_lng = lng
    emergency.vehicle_accuracy = accuracy
    emergency.vehicle_updated_at = now

    # Haversine distance to victim
    victim_lat = emergency.latitude or lat
    victim_lng = emergency.longitude or lng
    dist_km = calculate_haversine_distance(lat, lng, victim_lat, victim_lng)
    emergency.distance_km = round(dist_km, 2)

    # Dynamic ETA: assume ~28 km/h emergency response speed
    speed_kmh = 28.0
    if dist_km > 0.05:
        eta_mins = max(1, int(math.ceil(dist_km / (speed_kmh / 60.0))))
    else:
        eta_mins = 0
    emergency.eta = eta_mins

    # If status was accepted/assigned, advance to dispatched / on_the_way when moving
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

    emergency_data = format_emergency_data(emergency)

    return {
        'success': True,
        'sos_id': emergency.sosId,
        'vehicle_id': emergency.rescue_vehicle or 'Rescue Boat RB-04',
        'rescue_team': emergency.rescue_team or 'Team Alpha',
        'latitude': lat,
        'longitude': lng,
        'accuracy': accuracy,
        'timestamp': now.isoformat(),
        'distance_km': emergency.distance_km,
        'eta': eta_mins,
        'status': emergency.status,
        'emergency': emergency_data
    }


class RescueTrackingConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer managing real-time GPS coordinates and telemetry streaming
    for an active SOS rescue mission.
    Channel Group: rescue_<sos_id>
    """

    async def connect(self):
        url_kwargs = self.scope.get('url_route', {}).get('kwargs', {})
        self.sos_id = url_kwargs.get('sos_id')
        if not self.sos_id:
            path_parts = [p for p in self.scope.get('path', '').split('/') if p]
            if len(path_parts) >= 3 and path_parts[0] == 'ws' and path_parts[1] == 'rescue':
                self.sos_id = path_parts[2]
            elif path_parts:
                self.sos_id = path_parts[-1]
            else:
                self.sos_id = 'default'

        self.room_group_name = f"rescue_{self.sos_id}"

        # Join the channel group for this active SOS
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

        # Fetch and transmit initial state
        init_data = await sync_to_async(get_initial_emergency_data)(self.sos_id)
        if init_data.get('exists'):
            await self.send_json({
                'type': 'tracking_init',
                'sos_id': self.sos_id,
                'status': init_data.get('status'),
                'telemetry': init_data.get('telemetry'),
                'emergency': init_data.get('emergency'),
                'timestamp': timezone.now().isoformat()
            })
        else:
            await self.send_json({
                'type': 'error',
                'message': f"Emergency request {self.sos_id} not found."
            })

    async def disconnect(self, close_code):
        # Leave group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive_json(self, content):
        """Handle incoming WebSocket payload from client (vehicle GPS ping or status update)."""
        action = content.get('action') or content.get('type')

        if action == 'ping':
            await self.send_json({'type': 'pong', 'timestamp': timezone.now().isoformat()})
            return

        # Location update from rescue team device
        if action in ['location_update', 'vehicle_location']:
            lat = content.get('latitude') or content.get('lat')
            lng = content.get('longitude') or content.get('lng')
            accuracy = content.get('accuracy', 5.0)
            token = content.get('token')
            if not token and b'token=' in self.scope.get('query_string', b''):
                import urllib.parse
                qs = urllib.parse.parse_qs(self.scope['query_string'].decode('utf-8'))
                token = qs.get('token', [None])[0]

            res = await sync_to_async(update_vehicle_position_db)(
                self.sos_id, lat, lng, accuracy, token
            )

            if res.get('success'):
                # Broadcast new coordinates to all connected subscribers (User, NGO, Admin)
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'vehicle_location_broadcast',
                        'data': res
                    }
                )
            else:
                await self.send_json({
                    'type': 'error',
                    'message': res.get('error', 'Location update failed')
                })

        # Status update action (dispatched, arrived, resolved)
        elif action in ['status_update', 'update_status']:
            new_status = content.get('status')
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'rescue_status_broadcast',
                    'data': {
                        'sos_id': self.sos_id,
                        'status': new_status,
                        'timestamp': timezone.now().isoformat()
                    }
                }
            )

    async def vehicle_location_broadcast(self, event):
        """Handler for vehicle_location_broadcast event from channel group."""
        await self.send_json({
            'type': 'vehicle_location',
            **event['data']
        })

    async def rescue_status_broadcast(self, event):
        """Handler for rescue_status_broadcast event from channel group."""
        await self.send_json({
            'type': 'rescue_status',
            **event['data']
        })
