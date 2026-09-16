from django.db import models
from django.contrib.auth.models import User
import random

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='user_profile')
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    pincode = models.CharField(max_length=10, blank=True, null=True)
    language = models.CharField(max_length=100, blank=True, null=True)
    family_count = models.CharField(max_length=50, blank=True, null=True, default='0')
    emergency_contact = models.CharField(max_length=20, blank=True, null=True)
    medical_conditions = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Citizen: {self.user.username}"

class NgoProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='ngo_profile')
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    pincode = models.CharField(max_length=10, blank=True, null=True)
    # Specializations stored as JSON list: e.g. ["flood", "fire"]
    specializations = models.JSONField(default=list)
    ambulances = models.IntegerField(default=0)
    boats = models.IntegerField(default=0)
    fire_trucks = models.IntegerField(default=0)
    volunteers = models.IntegerField(default=0)
    is_verified = models.BooleanField(default=True)

    def __str__(self):
        return f"NGO: {self.name}"

class Emergency(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending Dispatch'),
        ('ngo_found', 'Nearby NGO Found'),
        ('accepted', 'Accepted'),
        ('assigned', 'Team Assigned'),
        ('dispatched', 'Dispatched'),
        ('on_the_way', 'On The Way'),
        ('arrived', 'Team Arrived'),
        ('rescue_in_progress', 'Rescue In Progress'),
        ('resolved', 'Resolved & Closed'),
        ('cancelled', 'Cancelled'),
    )

    sosId = models.CharField(max_length=50, unique=True, primary_key=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='emergencies')
    disaster = models.CharField(max_length=50) # flood, landslide, fire, earthquake, accident, medical
    urgency = models.CharField(max_length=20) # critical, high, medium
    name = models.CharField(max_length=100) # reporter name
    phone = models.CharField(max_length=20) # reporter phone
    people = models.CharField(max_length=20, default='1') # e.g. '1', '2-5', '6-10', '10+'
    address = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    latitude = models.FloatField(default=0.0)
    longitude = models.FloatField(default=0.0)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending')
    eta = models.IntegerField(default=0) # in minutes
    matched_ngo = models.ForeignKey(NgoProfile, on_delete=models.SET_NULL, blank=True, null=True, related_name='matched_emergencies')
    rescue_team = models.CharField(max_length=100, blank=True, null=True) # e.g. Team Alpha
    rescue_vehicle = models.CharField(max_length=100, blank=True, null=True) # e.g. Rescue Boat RB-04
    vehicle_lat = models.FloatField(blank=True, null=True)
    vehicle_lng = models.FloatField(blank=True, null=True)
    location_accuracy = models.FloatField(blank=True, null=True, default=10.0) # victim GPS accuracy in meters
    location_updated_at = models.DateTimeField(blank=True, null=True)
    vehicle_accuracy = models.FloatField(blank=True, null=True, default=5.0) # vehicle GPS accuracy in meters
    vehicle_updated_at = models.DateTimeField(blank=True, null=True)
    distance_km = models.FloatField(blank=True, null=True, default=0.0)
    accepted_at = models.DateTimeField(blank=True, null=True)
    dispatched_at = models.DateTimeField(blank=True, null=True)
    arrived_at = models.DateTimeField(blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    rescued_people_count = models.IntegerField(default=0)
    resolution_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def generate_id(cls):
        while True:
            # SOS-123456
            num = random.randint(100000, 999999)
            potential_id = f"SOS-{num}"
            if not cls.objects.filter(sosId=potential_id).exists():
                return potential_id

    def __str__(self):
        return f"{self.sosId} - {self.disaster} ({self.status})"

class RescueAssignment(models.Model):
    sos_request = models.ForeignKey(Emergency, on_delete=models.CASCADE, related_name='assignments')
    ngo = models.ForeignKey(NgoProfile, on_delete=models.CASCADE, related_name='rescue_assignments')
    rescue_team = models.CharField(max_length=100, default='Team Alpha')
    vehicle = models.CharField(max_length=100, default='Rescue Boat RB-04')
    eta = models.IntegerField(default=15) # minutes
    status = models.CharField(max_length=30, default='accepted')
    notification_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Assignment {self.sos_request.sosId} -> {self.ngo.name} ({self.rescue_team})"

class DisasterAlert(models.Model):
    message = models.TextField()
    severity = models.CharField(max_length=20) # critical, warning, info
    channels = models.JSONField(default=list) # ["sms", "email", "push"]
    city = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.severity.upper()} alert in {self.city} - {self.message[:30]}"

class Donation(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='donations')
    ngo = models.ForeignKey(NgoProfile, on_delete=models.SET_NULL, blank=True, null=True, related_name='donations')
    ngo_name = models.CharField(max_length=200, blank=True, null=True)
    amount = models.FloatField()
    cause = models.CharField(max_length=100)
    transaction_id = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, default='Success')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Donation {self.transaction_id} of ₹{self.amount} for {self.cause}"

class TransmittedLocation(models.Model):
    latitude = models.FloatField()
    longitude = models.FloatField()
    accuracy = models.FloatField()
    is_offline = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        status = "OFFLINE" if self.is_offline else "ONLINE"
        return f"Coord {self.latitude}, {self.longitude} ({status}) at {self.created_at}"

class VehicleLocation(models.Model):
    sos_request = models.ForeignKey(Emergency, on_delete=models.CASCADE, related_name='location_logs')
    vehicle = models.CharField(max_length=100, default='Rescue Boat RB-04')
    latitude = models.FloatField()
    longitude = models.FloatField()
    accuracy = models.FloatField(default=5.0)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.vehicle} @ ({self.latitude:.5f}, {self.longitude:.5f}) for {self.sos_request.sosId}"
