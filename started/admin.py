from django.contrib import admin
from .models import Room, Payment, ChatAccess, Message, Owner, Client, UserProfile, ClientPayment, RoomAccess, Conversation

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ['title', 'room_type', 'location', 'price', 'created_at']
    list_filter = ['room_type', 'created_at']
    search_fields = ['title', 'location']

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['user', 'amount', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['user__username', 'stripe_payment_intent_id']

@admin.register(ChatAccess)
class ChatAccessAdmin(admin.ModelAdmin):
    list_display = ['user', 'payment', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['sender', 'receiver', 'room', 'content', 'read_status', 'timestamp']
    list_filter = ['read_status', 'timestamp']
    search_fields = ['sender__username', 'receiver__username', 'content']

@admin.register(ClientPayment)
class ClientPaymentAdmin(admin.ModelAdmin):
    list_display = ['client', 'owner', 'room', 'amount', 'status', 'paid_at', 'created_at']
    list_filter = ['status', 'paid_at', 'created_at']
    search_fields = ['client__user__username', 'owner__user__username', 'transaction_id']

@admin.register(Owner)
class OwnerAdmin(admin.ModelAdmin):
    list_display = ['user', 'phone', 'created_at']
    search_fields = ['user__username', 'user__email', 'phone']
    list_filter = ['created_at']

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['user', 'phone', 'preferred_location', 'created_at']
    search_fields = ['user__username', 'user__email', 'phone', 'preferred_location']
    list_filter = ['created_at']

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'phone_number']
    search_fields = ['user__username', 'user__email', 'phone_number']

@admin.register(RoomAccess)
class RoomAccessAdmin(admin.ModelAdmin):
    list_display = ['client', 'room', 'payment', 'unlocked_at']
    list_filter = ['unlocked_at']
    search_fields = ['client__user__username', 'room__title']

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['client', 'owner', 'room', 'created_at', 'updated_at']
    list_filter = ['created_at', 'updated_at']
    search_fields = ['client__user__username', 'owner__user__username', 'room__title']
