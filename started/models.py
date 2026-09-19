# ============================================================================
# MODELS.PY - Database Models for LuxeRooms Platform
# ============================================================================
# This file defines all database tables and their relationships
# Each model represents a table in the database
# ============================================================================

from django.db import models
from django.contrib.auth.models import User  # Django's built-in user system
from django.utils import timezone

# ============================================================================
# USER PROFILE MODEL
# ============================================================================
# Extends Django's User model with additional profile information
# One-to-One relationship means each User has exactly one UserProfile
class UserProfile(models.Model):
    # Links to Django's built-in User model (username, email, password)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    
    # Profile picture upload - stored in media/profiles/ folder
    profile_image = models.ImageField(upload_to='profiles/', blank=True, null=True)
    
    # Additional contact information
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    
    # Personal bio/description (max 500 characters)
    bio = models.TextField(max_length=500, blank=True, null=True)
    
    # Password reset PIN (6-digit code)
    reset_pin = models.CharField(max_length=6, blank=True, null=True)
    pin_created_at = models.DateTimeField(blank=True, null=True)
    
    def __str__(self):
        # String representation for admin panel
        return f'{self.user.username} Profile'
    
    def get_profile_image(self):
        # Helper method to get profile image URL or None
        try:
            if self.profile_image:
                return self.profile_image.url
        except (ValueError, AttributeError):
            pass
        return None
    
    def generate_reset_pin(self):
        # Generate 6-digit PIN for password reset
        import random
        from django.utils import timezone
        
        self.reset_pin = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        self.pin_created_at = timezone.now()
        self.save()
        return self.reset_pin
    
    def is_pin_valid(self):
        # Check if PIN is still valid (expires after 15 minutes)
        if not self.reset_pin or not self.pin_created_at:
            return False
        
        from django.utils import timezone
        from datetime import timedelta
        
        expiry_time = self.pin_created_at + timedelta(minutes=15)
        return timezone.now() < expiry_time

# ============================================================================
# ROLE-BASED USER MODELS
# ============================================================================
# These models define different user roles in the system
# Each user can be either an Owner (lists properties) or Client (searches properties)

class Owner(models.Model):
    """Property owners who list rooms for rent"""
    # Links to User account - one user can be one owner
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    
    # Owner's contact information
    phone = models.CharField(max_length=20)
    address = models.TextField()  # Business/property address
    
    # Automatically set when owner account is created
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f'Room Owner: {self.user.username}'

class Client(models.Model):
    """Clients who search for rooms to rent"""
    # Links to User account - one user can be one client
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    
    # Client's contact and preference information
    phone = models.CharField(max_length=20)
    preferred_location = models.CharField(max_length=200, blank=True, null=True)
    
    # Automatically set when client account is created
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f'Client: {self.user.username}'

# ============================================================================
# ROOM MODEL - Core Property Listing
# ============================================================================
# This is the main model for property listings
# Contains all information about rooms/properties available for rent

class Room(models.Model):
    """Property listings created by owners"""
    
    # Predefined choices for room types
    # Used in dropdown menus and filtering
    ROOM_TYPE_CHOICES = [
        ('private', 'Private Room'),      # Single occupancy room
        ('shared', 'Shared Room'),        # Shared with roommates
        ('studio', 'Studio Apartment'),   # Small apartment
        ('apartment', 'Full Apartment'),  # Complete apartment
        ('house', 'House'),              # Entire house
    ]
    
    # Basic property information
    title = models.CharField(max_length=200)  # Property title/name
    room_type = models.CharField(max_length=20, choices=ROOM_TYPE_CHOICES)
    location = models.CharField(max_length=200)  # Address/area
    
    # Pricing information (supports up to 99,999,999.99)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Detailed description of the property
    description = models.TextField()
    
    # Contact information (initially hidden, unlocked via payment)
    contact_phone = models.CharField(max_length=20)
    contact_email = models.EmailField()
    
    # Property specifications
    area_m2 = models.IntegerField(default=25)    # Size in square meters
    beds = models.IntegerField(default=1)        # Number of bedrooms
    baths = models.IntegerField(default=1)       # Number of bathrooms
    
    # Property image upload - stored in media/rooms/ folder
    image = models.ImageField(upload_to='rooms/', blank=True, null=True)
    
    # Links to the property owner
    owner = models.ForeignKey('Owner', on_delete=models.CASCADE, null=True, blank=True)

    latitude = models.DecimalField(
        max_digits=17,
        decimal_places=8,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        max_digits=17,
        decimal_places=8,
        null=True,
        blank=True,
    )
    
    # Automatically set when room is created
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.title
    
    class Meta:
        # Show newest rooms first in admin and queries
        ordering = ['-created_at']


class RoomImage(models.Model):
    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name='images',
    )
    image = models.ImageField(upload_to='room_images/')
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', 'created_at']


class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ]

    client = models.ForeignKey('Client', on_delete=models.CASCADE)
    owner = models.ForeignKey('Owner', on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('client', 'room')]

    def __str__(self):
        return f'{self.client.user.username} - {self.room.title} - {self.status}'


class Payment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]
    
    PAYMENT_TYPE_CHOICES = [
        ('chat_access', 'Chat Access'),
        ('room_unlock', 'Room Unlock'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, null=True, blank=True)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES, default='room_unlock')
    stripe_payment_intent_id = models.CharField(max_length=200, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f'{self.user.username} - {self.amount} - {self.status}'

class ChatAccess(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f'{self.user.username} - Chat Access'

class RoomAccess(models.Model):
    client = models.ForeignKey('Client', on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE)
    unlocked_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['client', 'room'],
                name='unique_client_room_access'
            )
        ]
    
    def __str__(self):
        return f'{self.client.user.username} - {self.room.title}'

class ClientPayment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]
    
    client = models.ForeignKey('Client', on_delete=models.CASCADE)
    owner = models.ForeignKey('Owner', on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=30.00)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    transaction_id = models.CharField(max_length=200, unique=True)
    esewa_ref_id = models.CharField(max_length=200, blank=True, null=True)
    verification_code = models.CharField(max_length=6, blank=True, null=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['client', 'room'],
                name='unique_client_room_payment'
            )
        ]
    
    def __str__(self):
        return f'{self.client.user.username} - {self.room.title} - Rs.{self.amount}'

class Conversation(models.Model):
    """Unique conversation between a client and owner for a specific room"""
    client = models.ForeignKey('Client', on_delete=models.CASCADE)
    owner = models.ForeignKey('Owner', on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['client', 'owner', 'room'],
                name='unique_conversation'
            )
        ]
    
    def __str__(self):
        return f'{self.client.user.username} - {self.owner.user.username} - {self.room.title}'

class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    content = models.TextField()
    image = models.ImageField(upload_to='messages/', blank=True, null=True)
    read_status = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f'{self.sender.username} to {self.receiver.username}: {self.content[:50]}'
    
    class Meta:
        ordering = ['timestamp']