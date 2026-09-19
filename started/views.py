from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db import transaction
from django.core.mail import send_mail
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode, url_has_allowed_host_and_scheme
from django.utils.encoding import force_bytes, force_str
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
import json
import stripe
import random
import string
import logging

from .models import Room, RoomImage, Booking, Payment, ChatAccess, Message, UserProfile, Owner, Client, RoomAccess, ClientPayment, Conversation
from django.utils import timezone
import requests
import hashlib
from .forms import RoomForm
from .decorators import owner_required, client_required
from .security_utils import sanitize_input, safe_int

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY if settings.STRIPE_SECRET_KEY else None


def upload_images(room, images):
    """Store at most five images, keeping the first image primary."""
    images = list(images)
    if len(images) > 5:
        raise ValueError('You can upload a maximum of 5 images.')
    # An edit with files is a replacement, rather than an unbounded append.
    if images:
        room.images.all().delete()
    for index, image in enumerate(images):
        RoomImage.objects.create(room=room, image=image, is_primary=index == 0)

@login_required
def client_dashboard(request):
    # Ensure user has profile
    UserProfile.objects.get_or_create(user=request.user)
    
    # Check if user has client profile, create if missing
    try:
        client = request.user.client
    except (Client.DoesNotExist, AttributeError):
        messages.error(request, 'No Client profile found. Please register as Client first.')
        return redirect('register')
    
    rooms = Room.objects.all()
    
    # Search and filter
    q = request.GET.get('q')
    location = request.GET.get('location')
    price_min = request.GET.get('price_min')
    price_max = request.GET.get('price_max')
    room_type = request.GET.get('room_type')
    
    if q:
        rooms = rooms.filter(
            Q(title__icontains=q) | 
            Q(location__icontains=q) | 
            Q(description__icontains=q)
        )
    
    if location and location != 'Any Location':
        rooms = rooms.filter(location__icontains=location)
    
    if price_min:
        rooms = rooms.filter(price__gte=price_min)
    
    if price_max:
        rooms = rooms.filter(price__lte=price_max)
    
    if room_type and room_type != 'Any Type':
        rooms = rooms.filter(room_type=room_type)
    
    # Check which rooms user has paid for
    unlocked_rooms = []
    if request.user.is_authenticated:
        try:
            unlocked_rooms = ClientPayment.objects.filter(
                client=client,
                status='success'
            ).values_list('room_id', flat=True)
        except:
            unlocked_rooms = []
    
    context = {
        'rooms': rooms,
        'unlocked_rooms': list(unlocked_rooms),
        'room_unlock_price': 30,  # Rs 30 per room
    }
    return render(request, 'started/client_dashboard.html', context)

@login_required
def owner_dashboard(request):
    # Ensure user has profile
    UserProfile.objects.get_or_create(user=request.user)
    
    # Check if user has owner profile, create if missing
    try:
        owner = request.user.owner
    except (Owner.DoesNotExist, AttributeError):
        messages.error(request, 'No Owner profile found. Please register as Owner first.')
        return redirect('register')
    
    if request.method == 'POST':
        form = RoomForm(request.POST, request.FILES)
        if form.is_valid():
            images = request.FILES.getlist('room_images')
            if len(images) > 5:
                form.add_error(None, 'You can upload a maximum of 5 images.')
                return render(request, 'started/owner_dashboard.html', {'form': form, 'owner_rooms': Room.objects.filter(owner=owner)[:10]})
            room = form.save(commit=False)
            room.owner = owner
            room.save()
            upload_images(room, images)
            messages.success(request, 'Room listing added successfully!')
            return redirect('owner_dashboard')
    else:
        form = RoomForm()
    
    owner_rooms = Room.objects.filter(owner=owner)[:10]
    booking_requests = Booking.objects.filter(owner=owner).select_related(
        'client__user', 'room'
    )[:20]
    return render(request, 'started/owner_dashboard.html', {
        'form': form,
        'owner_rooms': owner_rooms,
        'booking_requests': booking_requests,
    })


@login_required
@require_http_methods(['POST'])
def book_room(request):
    try:
        client = request.user.client
    except (Client.DoesNotExist, AttributeError):
        return JsonResponse({'success': False, 'error': 'Client account required.'}, status=403)

    try:
        room_id = json.loads(request.body).get('room_id')
        room = get_object_or_404(Room.objects.select_related('owner'), id=room_id)
        if room.owner is None:
            return JsonResponse({'success': False, 'error': 'This room has no owner.'}, status=400)

        booking, created = Booking.objects.get_or_create(
            client=client,
            room=room,
            defaults={'owner': room.owner, 'status': 'pending'},
        )
        if not created and booking.status == 'pending':
            booking.status = 'cancelled'
            booking.save(update_fields=['status'])
            return JsonResponse({'success': True, 'status': 'cancelled'})
        if not created and booking.status == 'confirmed':
            return JsonResponse({'success': False, 'error': 'This booking is already confirmed.'}, status=400)

        booking.owner = room.owner
        booking.status = 'pending'
        booking.save(update_fields=['owner', 'status'])
        try:
            send_mail(
                f'New booking request for {room.title}',
                f'{request.user.get_username()} requested to book {room.title}.',
                settings.DEFAULT_FROM_EMAIL,
                [room.owner.user.email],
                fail_silently=False,
            )
        except Exception:
            logger.exception('Unable to send booking request email for room %s', room.id)
        return JsonResponse({'success': True, 'status': 'pending'})
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Invalid booking request.'}, status=400)


@login_required
@require_http_methods(['GET'])
def booking_status(request, room_id):
    try:
        booking = Booking.objects.get(room_id=room_id, client=request.user.client)
    except (Booking.DoesNotExist, Client.DoesNotExist, AttributeError):
        return JsonResponse({'has_booking': False, 'status': None})
    return JsonResponse({'has_booking': True, 'status': booking.status})


@login_required
@require_http_methods(['POST'])
def update_booking(request, booking_id):
    try:
        owner = request.user.owner
    except (Owner.DoesNotExist, AttributeError):
        return JsonResponse({'success': False, 'error': 'Owner account required.'}, status=403)

    try:
        action = json.loads(request.body).get('action')
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)
    if action not in {'confirmed', 'cancelled'}:
        return JsonResponse({'success': False, 'error': 'Invalid booking action.'}, status=400)

    booking = get_object_or_404(
        Booking.objects.select_related('client__user', 'room'),
        id=booking_id,
        owner=owner,
    )
    booking.status = action
    booking.save(update_fields=['status'])
    return JsonResponse({'success': True, 'status': booking.status})

@csrf_protect
@require_http_methods(["POST"])
@login_required
def unlock_room(request):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Authentication required'})
    
    try:
        data = json.loads(request.body)
        room_id = data.get('room_id')
        room = get_object_or_404(Room, id=room_id)
        if room.owner is None:
            return JsonResponse({'error': 'Room owner unavailable'}, status=404)
        client = getattr(request.user, 'client', None)
        if client is None or room.owner is None:
            return JsonResponse({'success': False, 'error': 'Client and room owner are required'}, status=403)

        # Chat is a free feature.  Do not make this depend on DEBUG: production
        # clients must use the same reliable HTTP fallback as local clients.
        client_payment, _ = ClientPayment.objects.update_or_create(
            client=client,
            room=room,
            defaults={
                'owner': room.owner,
                'amount': 0,
                'transaction_id': f'free_chat_{request.user.id}_{room.id}',
                'status': 'success',
                'paid_at': timezone.now(),
            },
        )
        return JsonResponse({
            'success': True,
            'message': 'Chat access granted.',
            'contact_details': {
                'phone': room.contact_phone,
                'email': room.contact_email,
                'location': room.location,
                'owner_name': room.owner.user.get_full_name() or room.owner.user.username,
                'can_message': True,
                'already_unlocked': True,
            },
        })

    except Exception as e:
        logger.exception('Unable to grant chat access')
        return JsonResponse({'success': False, 'error': 'Unable to access chat'}, status=400)

@csrf_protect
@require_http_methods(["POST"])
@login_required
def voice_search(request):
    try:
        data = json.loads(request.body)
        transcript = data.get('transcript', '').lower()
        
        # Process voice commands
        filters = {}
        
        # Location detection
        if 'downtown' in transcript:
            filters['location__icontains'] = 'downtown'
        elif 'university' in transcript:
            filters['location__icontains'] = 'university'
        elif 'business' in transcript:
            filters['location__icontains'] = 'business'
        
        # Room type detection
        if 'studio' in transcript:
            filters['room_type'] = 'studio'
        elif 'apartment' in transcript:
            filters['room_type'] = 'apartment'
        elif 'private' in transcript:
            filters['room_type'] = 'private'
        elif 'shared' in transcript:
            filters['room_type'] = 'shared'
        
        # Price detection
        if 'under' in transcript or 'below' in transcript:
            import re
            price_match = re.search(r'(\d+)', transcript)
            if price_match:
                filters['price__lte'] = int(price_match.group(1))
        
        rooms = Room.objects.filter(**filters) if filters else Room.objects.all()
        
        return JsonResponse({
            'success': True,
            'filters': filters,
            'count': rooms.count(),
            'message': f'Found {rooms.count()} rooms matching your voice search'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_protect
@require_http_methods(["POST"])
@login_required
def send_sms_inquiry(request):
    try:
        data = json.loads(request.body)
        room_id = data.get('room_id')
        message = data.get('message')
        
        room = get_object_or_404(Room, id=room_id)
        if room.owner is None:
            return JsonResponse({'error': 'Room owner unavailable'}, status=404)
        
        # Simulate SMS sending
        return JsonResponse({
            'success': True,
            'message': f'SMS inquiry sent to {room.contact_phone}'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def delete_room(request, room_id):
    try:
        owner = request.user.owner
    except Owner.DoesNotExist:
        messages.error(request, 'Access denied. Owner account required.')
        return redirect('login')
    
    if request.method == 'POST':
        room = get_object_or_404(Room, id=room_id, owner=owner)
        room.delete()
        messages.success(request, 'Room deleted successfully!')
    return redirect('owner_dashboard')

@login_required
def edit_room(request, room_id):
    try:
        owner = request.user.owner
    except Owner.DoesNotExist:
        messages.error(request, 'Access denied. Owner account required.')
        return redirect('login')
    
    room = get_object_or_404(Room, id=room_id, owner=owner)
    if request.method == 'POST':
        form = RoomForm(request.POST, request.FILES, instance=room)
        if form.is_valid():
            images = request.FILES.getlist('room_images')
            if len(images) > 5:
                form.add_error(None, 'You can upload a maximum of 5 images.')
                return render(request, 'started/edit_room.html', {'form': form, 'room': room})
            form.save()
            try:
                upload_images(room, images)
            except ValueError as exc:
                form.add_error(None, str(exc))
                return render(request, 'started/edit_room.html', {'form': form, 'room': room})
            messages.success(request, 'Room updated successfully!')
            return redirect('owner_dashboard')
    else:
        form = RoomForm(instance=room)
    
    return render(request, 'started/edit_room.html', {'form': form, 'room': room})

@login_required
def create_payment_intent(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            room_id = data.get('room_id')
            room = get_object_or_404(Room, id=room_id)
            
            # Check if room has an owner
            if not room.owner:
                return JsonResponse({'error': 'Room has no owner assigned'}, status=400)
            
            # Check if already unlocked
            if ClientPayment.objects.filter(client=request.user.client, room=room, status='success').exists():
                return JsonResponse({'error': 'Room already unlocked'}, status=400)
            
            # Create pending payment record
            transaction_id = f'room_unlock_{room_id}_{int(timezone.now().timestamp())}'
            
            client_payment, created = ClientPayment.objects.get_or_create(
                client=request.user.client,
                room=room,
                defaults={
                    'owner': room.owner,
                    'amount': 30.00,
                    'transaction_id': transaction_id,
                    'status': 'pending'
                }
            )
            
            # Use existing transaction_id if record already exists
            if not created:
                transaction_id = client_payment.transaction_id
            
            return JsonResponse({
                'transaction_id': transaction_id,
                'room_id': room_id,
                'amount': 30
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return JsonResponse({'error': 'Invalid payload'}, status=400)
    except stripe.error.SignatureVerificationError:
        return JsonResponse({'error': 'Invalid signature'}, status=400)
    
    if event['type'] == 'payment_intent.succeeded':
        payment_intent = event['data']['object']
        user_id = payment_intent['metadata']['user_id']
        room_id = payment_intent['metadata'].get('room_id')
        
        # Update payment status
        payment = Payment.objects.get(stripe_payment_intent_id=payment_intent['id'])
        payment.status = 'success'
        payment.save()
        
        # Create room access for chat
        if room_id and payment.payment_type == 'room_unlock':
            user = User.objects.get(id=user_id)
            RoomAccess.objects.get_or_create(
                client=user.client,
                room=payment.room,
                payment=payment
            )
    
    return JsonResponse({'status': 'success'})

@login_required
def get_messages(request):
    room_id = request.GET.get('room_id')
    client_id = request.GET.get('client_id')
    
    if not room_id:
        return JsonResponse({'error': 'Room ID required'}, status=400)
    
    room = get_object_or_404(Room, id=room_id)
    
    # Determine access based on user role
    if hasattr(request.user, 'client'):
        # Client can see all messages in the room between them and the owner
        messages = Message.objects.filter(
            room=room
        ).filter(
            Q(sender=request.user, receiver=room.owner.user) | Q(sender=room.owner.user, receiver=request.user)
        ).order_by('timestamp')
    elif hasattr(request.user, 'owner') and room.owner == request.user.owner:
        if client_id:
            client_user = get_object_or_404(User, id=client_id)
            messages = Message.objects.filter(
                room=room
            ).filter(
                Q(sender=client_user, receiver=request.user) | Q(sender=request.user, receiver=client_user)
            ).order_by('timestamp')
        else:
            messages = Message.objects.filter(
                room=room
            ).filter(
                Q(sender=request.user) | Q(receiver=request.user)
            ).order_by('timestamp')
    else:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    messages_data = []
    for msg in messages:
        profile_image = None
        try:
            profile_image = msg.sender.userprofile.get_profile_image()
        except:
            pass
        
        messages_data.append({
            'id': msg.id,
            'sender_id': msg.sender.id,
            'sender_name': msg.sender.get_full_name() or msg.sender.username,
            'profile_image': profile_image,
            'content': msg.content,
            'timestamp': msg.timestamp.isoformat(),
            'read_status': msg.read_status,
            'is_mine': msg.sender == request.user
        })
    
    return JsonResponse({'messages': messages_data})

@csrf_protect
@login_required
def send_message(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        room_id = data.get('room_id')
        client_id = data.get('client_id')
        content = sanitize_input(data.get('content', '')).strip()
        
        if not content:
            return JsonResponse({'error': 'Message content required'}, status=400)
        
        room = get_object_or_404(Room, id=room_id)
        
        # Determine receiver based on sender role
        if hasattr(request.user, 'client'):
            receiver = room.owner.user
            client = request.user.client
            owner = room.owner
        elif hasattr(request.user, 'owner') and room.owner == request.user.owner:
            if client_id:
                receiver = get_object_or_404(User, id=client_id)
                if not hasattr(receiver, 'client'):
                    return JsonResponse({'error': 'Client account required'}, status=400)
                client = receiver.client
                owner = request.user.owner
                # Owners may only reply to clients who have a conversation in
                # this room; this prevents cross-room message injection.
                if not Message.objects.filter(
                    room=room, sender=receiver, receiver=request.user
                ).exists():
                    return JsonResponse({'error': 'No conversation with this client'}, status=403)
            else:
                # Find the first client who has messaged in this room
                client_message = Message.objects.filter(
                    room=room,
                    sender__client__isnull=False
                ).first()
                
                if client_message:
                    receiver = client_message.sender
                    client = receiver.client
                    owner = request.user.owner
                else:
                    return JsonResponse({'error': 'No client found to send message to'}, status=400)
        else:
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        # Get or create conversation
        conversation, created = Conversation.objects.get_or_create(
            client=client,
            owner=owner,
            room=room
        )
        
        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            receiver=receiver,
            room=room,
            content=content
        )
        
        return JsonResponse({
            'success': True,
            'message': {
                'id': message.id,
                'content': message.content,
                'timestamp': message.timestamp.isoformat(),
                'sender_name': message.sender.username
            }
        })
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_protect
@login_required
def mark_messages_read(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        message_ids = data.get('message_ids', [])
        
        Message.objects.filter(
            id__in=message_ids,
            receiver=request.user
        ).update(read_status=True)
        
        return JsonResponse({'status': 'success'})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def get_unread_count(request):
    count = Message.objects.filter(
        receiver=request.user,
        read_status=False
    ).count()
    
    return JsonResponse({'unread_count': count})

@login_required
def profile_settings(request):
    from .models import UserProfile
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        uploaded_image = request.FILES.get('profile_image')
        if uploaded_image:
            if uploaded_image.size > 5 * 1024 * 1024:
                messages.error(request, 'Profile image must be 5MB or smaller.')
                return redirect('profile_settings')
            try:
                from PIL import Image
                with Image.open(uploaded_image) as opened:
                    opened.verify()
            except (ImportError, OSError, ValueError):
                messages.error(request, 'Please upload a valid image file.')
                return redirect('profile_settings')
        # Update user fields
        username = request.POST.get('username')
        email = request.POST.get('email')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        
        # Update profile fields
        phone_number = request.POST.get('phone_number')
        bio = request.POST.get('bio')
        
        # Password change
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if not username or not email:
            messages.error(request, 'Username and email are required.')
        # Validate username uniqueness
        elif username != request.user.username and User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists')
        # Validate email uniqueness
        elif email != request.user.email and User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered')
        # Validate password change
        elif current_password or new_password or confirm_password:
            if not request.user.check_password(current_password):
                messages.error(request, 'Current password is incorrect')
            elif not new_password:
                messages.error(request, 'Enter a new password.')
            elif new_password != confirm_password:
                messages.error(request, 'New passwords do not match')
            elif len(new_password) < 8:
                messages.error(request, 'Password must be at least 8 characters')
            else:
                # Update user info
                request.user.username = username
                request.user.email = email
                request.user.first_name = first_name
                request.user.last_name = last_name
                request.user.set_password(new_password)
                request.user.save()
                
                # Update profile info
                profile.phone_number = phone_number
                profile.bio = bio
                if uploaded_image:
                    profile.profile_image = uploaded_image
                profile.save()
                
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Profile updated successfully!')
                return redirect('profile_settings')
        else:
            # Update without password change
            request.user.username = username
            request.user.email = email
            request.user.first_name = first_name
            request.user.last_name = last_name
            request.user.save()
            
            profile.phone_number = phone_number
            profile.bio = bio
            if uploaded_image:
                profile.profile_image = uploaded_image
            profile.save()
            
            messages.success(request, 'Profile updated successfully!')
        
        return redirect('profile_settings')
    
    return render(request, 'started/profile_settings.html', {'profile': profile})

def login_view(request):
    if request.user.is_authenticated:
        # Redirect based on user role
        try:
            request.user.owner
            return redirect('owner_dashboard')
        except Owner.DoesNotExist:
            pass
        try:
            request.user.client
            return redirect('client_dashboard')
        except Client.DoesNotExist:
            pass
        return redirect('client_dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        role = request.POST.get('role')
        next_url = request.POST.get('next') or request.GET.get('next')
        
        if not username or not password or not role:
            messages.error(request, 'All fields are required')
        else:
            user = authenticate(request, username=username, password=password)
            if user is not None:
                # Check if user has the correct role
                if role == 'owner':
                    try:
                        user.owner
                        login(request, user)
                        messages.success(request, f'Welcome back, {user.username}!')
                        if next_url and url_has_allowed_host_and_scheme(
                            next_url, allowed_hosts={request.get_host()}
                        ) and next_url.startswith('/owner/'):
                            return redirect(next_url)
                        return redirect('owner_dashboard')
                    except Owner.DoesNotExist:
                        messages.error(request, f'No Owner profile found for user {user.username}. Please register as Owner first.')
                elif role == 'client':
                    try:
                        user.client
                        login(request, user)
                        messages.success(request, f'Welcome back, {user.username}!')
                        if next_url and url_has_allowed_host_and_scheme(
                            next_url, allowed_hosts={request.get_host()}
                        ) and next_url.startswith('/client/'):
                            return redirect(next_url)
                        return redirect('client_dashboard')
                    except Client.DoesNotExist:
                        messages.error(request, f'No Client profile found for user {user.username}. Please register as Client first.')
                else:
                    messages.error(request, 'Invalid role selected')
            else:
                messages.error(request, 'Invalid username or password')
    
    return render(request, 'started/login.html')

@transaction.atomic
def register_view(request):
    if request.user.is_authenticated:
        try:
            request.user.owner
            return redirect('owner_dashboard')
        except Owner.DoesNotExist:
            pass
        try:
            request.user.client
            return redirect('client_dashboard')
        except Client.DoesNotExist:
            pass
        return redirect('client_dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        role = request.POST.get('role')
        phone = request.POST.get('phone')
        address = request.POST.get('address', '').strip()
        preferred_location = request.POST.get('preferred_location', '').strip()
        
        # Validation
        if not username or not email or not password or not role or not phone:
            messages.error(request, 'All fields are required')
        elif role not in {'owner', 'client'}:
            messages.error(request, 'Invalid role selected')
        elif len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters long')
        elif password != confirm_password:
            messages.error(request, 'Passwords do not match')
        elif role == 'owner' and not address:
            messages.error(request, 'Address is required for Owner account')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists')
        elif User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered')
        else:
            user = None
            try:
                user = User.objects.create_user(username=username, email=email, password=password)
                UserProfile.objects.create(user=user)
                
                if role == 'owner':
                    if not address:
                        messages.error(request, 'Address is required for Owner account')
                        user.delete()
                        return render(request, 'started/register.html')
                    
                    owner = Owner.objects.create(
                        user=user,
                        phone=phone,
                        address=address
                    )
                    login(request, user)
                    messages.success(request, f'Owner account created successfully! Welcome {user.username}!')
                    return redirect('owner_dashboard')
                    
                elif role == 'client':
                    client = Client.objects.create(
                        user=user,
                        phone=phone,
                        preferred_location=preferred_location
                    )
                    login(request, user)
                    messages.success(request, f'Client account created successfully! Welcome {user.username}!')
                    return redirect('client_dashboard')
                else:
                    messages.error(request, 'Invalid role selected')
                    user.delete()
                    
            except Exception as e:
                if user is not None:
                    user.delete()
                messages.error(request, f'Registration failed: {str(e)}')
    
    return render(request, 'started/register.html')

def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully')
    return redirect('login')

@csrf_exempt
def esewa_webhook(request):
    """eSewa payment verification webhook"""
    if request.method == 'POST':
        try:
            # Get eSewa response parameters
            oid = request.POST.get('oid')
            amt = request.POST.get('amt')
            refId = request.POST.get('refId')
            
            # Extract room_id from oid (format: room_unlock_ROOMID_TIMESTAMP)
            if oid and oid.startswith('room_unlock_'):
                parts = oid.split('_')
                if len(parts) >= 3:
                    room_id = parts[2]
                    
                    # Verify payment with eSewa API
                    verification_url = 'https://uat.esewa.com.np/epay/transrec'
                    verification_data = {
                        'amt': amt,
                        'scd': 'EPAYTEST',
                        'rid': refId,
                        'pid': oid
                    }
                    
                    response = requests.post(verification_url, data=verification_data)
                    
                    if response.text.strip() == 'Success' and amt == '30':
                        room = get_object_or_404(Room, id=room_id)
                        
                        # Find the client payment record
                        client_payment = ClientPayment.objects.filter(
                            transaction_id=oid,
                            status='pending'
                        ).first()
                        
                        if client_payment:
                            # Generate unique verification code
                            verification_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                            
                            # Update payment status
                            client_payment.status = 'success'
                            client_payment.esewa_ref_id = refId
                            client_payment.verification_code = verification_code
                            client_payment.paid_at = timezone.now()
                            client_payment.save()
                            
                            # Send verification code via email/SMS (optional)
                            try:
                                from django.core.mail import send_mail
                                send_mail(
                                    'Room Unlock Code',
                                    f'Your verification code: {verification_code}\nUse this code to unlock room chat.',
                                    settings.DEFAULT_FROM_EMAIL,
                                    [client_payment.client.user.email],
                                    fail_silently=True,
                                )
                            except:
                                pass
                            
                            # Send real-time unlock notification via WebSocket
                            from channels.layers import get_channel_layer
                            from asgiref.sync import async_to_sync
                            
                            channel_layer = get_channel_layer()
                            async_to_sync(channel_layer.group_send)(
                                f'client_{client_payment.client.user.id}',
                                {
                                    'type': 'payment_success',
                                    'room_id': room_id,
                                    'message': 'Payment successful! Chat unlocked.'
                                }
                            )
                            
                            return JsonResponse({'status': 'success'})
            
            return JsonResponse({'status': 'failed'}, status=400)
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def esewa_success(request):
    room_id = request.GET.get('room')
    oid = request.GET.get('oid')
    amt = request.GET.get('amt')
    refId = request.GET.get('refId')
    
    if room_id and amt == '30':
        try:
            room = get_object_or_404(Room, id=room_id)
            
            # Create or update ClientPayment record
            client_payment, created = ClientPayment.objects.get_or_create(
                client=request.user.client,
                room=room,
                defaults={
                    'owner': room.owner,
                    'amount': 30.00,
                    'transaction_id': oid,
                    'esewa_ref_id': refId,
                    'verification_code': ''.join(random.choices(string.ascii_uppercase + string.digits, k=6)),
                    'status': 'success',
                    'paid_at': timezone.now()
                }
            )
            
            if not created:
                client_payment.status = 'success'
                client_payment.esewa_ref_id = refId
                client_payment.verification_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                client_payment.paid_at = timezone.now()
                client_payment.save()
            
            messages.success(request, 'Payment successful! Room unlocked.')
            return redirect(f'/client/dashboard/?payment=success&room={room_id}&open_chat=true')
            
        except Exception as e:
            messages.error(request, 'Payment verification failed.')
            return redirect('client_dashboard')
    
    messages.error(request, 'Invalid payment details.')
    return redirect('client_dashboard')

def esewa_failure(request):
    messages.error(request, 'Payment failed or cancelled.')
    return redirect('client_dashboard')

def password_reset_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        if not email:
            messages.error(request, 'Email address is required')
        else:
            try:
                user = User.objects.get(email=email)
                profile, created = UserProfile.objects.get_or_create(user=user)
                
                # Generate 6-digit PIN
                reset_pin = profile.generate_reset_pin()
                
                # Send PIN via email
                from django.core.mail import send_mail
                
                subject = 'Password Reset PIN - LuxeRooms'
                message = f'''
Hi {user.username},

You requested a password reset for your LuxeRooms account.

Your 6-digit reset PIN is: {reset_pin}

This PIN will expire in 15 minutes.

Use this PIN on the password reset page to set a new password.

If you didn't request this, please ignore this email.

Best regards,
LuxeRooms Team
'''
                
                try:
                    send_mail(
                        subject,
                        message,
                        settings.DEFAULT_FROM_EMAIL,
                        [email],
                        fail_silently=False,
                    )
                    messages.success(request, f'A 6-digit PIN has been sent to {email}. Please check your email.')
                    return redirect('password_reset_confirm')
                except Exception as e:
                    print(f'Email error: {e}')  # Debug print
                    messages.error(request, f'Failed to send email: {str(e)}')
                    
            except User.DoesNotExist:
                messages.error(request, 'No account found with this email address.')
    
    return render(request, 'started/password_reset.html')

def password_reset_confirm_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        reset_pin = request.POST.get('reset_pin')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if not email or not reset_pin or not new_password:
            messages.error(request, 'All fields are required')
        elif len(new_password) < 8:
            messages.error(request, 'Password must be at least 8 characters long')
        elif new_password != confirm_password:
            messages.error(request, 'Passwords do not match')
        else:
            try:
                user = User.objects.get(email=email)
                profile = UserProfile.objects.get(user=user)
                
                if profile.reset_pin == reset_pin and profile.is_pin_valid():
                    # PIN is valid, reset password
                    user.set_password(new_password)
                    user.save()
                    
                    # Clear the PIN
                    profile.reset_pin = None
                    profile.pin_created_at = None
                    profile.save()
                    
                    messages.success(request, 'Password has been reset successfully. You can now login.')
                    return redirect('login')
                else:
                    messages.error(request, 'Invalid or expired PIN. Please request a new one.')
                    
            except (User.DoesNotExist, UserProfile.DoesNotExist):
                messages.error(request, 'Invalid email address.')
    
    return render(request, 'started/password_reset_confirm.html')

@login_required
def chat_room(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    
    # Determine other user based on sender role
    if hasattr(request.user, 'client'):
        other_user = room.owner.user
    elif hasattr(request.user, 'owner') and room.owner == request.user.owner:
        other_user = None  # Owner can see all clients
    else:
        messages.error(request, 'Access denied.')
        return redirect('client_dashboard')
    
    context = {
        'room': room,
        'other_user': other_user
    }
    return render(request, 'started/chat_room.html', context)

@login_required
def get_room_info(request, room_id):
    try:
        room = get_object_or_404(Room, id=room_id)

        def format_coordinate(value):
            if value is None:
                return ''
            formatted = format(value, 'f').rstrip('0').rstrip('.')
            return formatted or '0'

        return JsonResponse({
            'owner_name': room.owner.user.get_full_name() or room.owner.user.username,
            'room_title': room.title,
            'location': room.location,
            'latitude': format_coordinate(room.latitude),
            'longitude': format_coordinate(room.longitude),
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
def get_client_messages(request):
    try:
        client = request.user.client
    except Client.DoesNotExist:
        return JsonResponse({'error': 'Client account required'}, status=403)
    
    try:
        conversations = []
        
        # Get all rooms where client has messages
        rooms_with_messages = Message.objects.filter(
            Q(sender=request.user) | Q(receiver=request.user)
        ).values_list('room', flat=True).distinct()
        
        for room_id in rooms_with_messages:
            room = Room.objects.get(id=room_id)
            
            # Get latest message in this room
            latest_message = Message.objects.filter(
                room=room
            ).filter(
                Q(sender=request.user) | Q(receiver=request.user)
            ).order_by('-timestamp').first()
            
            if latest_message:
                unread_count = Message.objects.filter(
                    room=room,
                    receiver=request.user,
                    read_status=False
                ).count()
                
                try:
                    profile_image = room.owner.user.userprofile.get_profile_image()
                except:
                    profile_image = None
                
                conversations.append({
                    'room_id': room.id,
                    'room_title': room.title,
                    'owner_id': room.owner.user.id,
                    'owner_name': room.owner.user.get_full_name() or room.owner.user.username,
                    'profile_image': profile_image,
                    'last_message': latest_message.content[:50] + ('...' if len(latest_message.content) > 50 else ''),
                    'last_message_time': latest_message.timestamp.isoformat(),
                    'unread_count': unread_count
                })
        
        conversations.sort(key=lambda x: x['last_message_time'], reverse=True)
        return JsonResponse({'conversations': conversations})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_protect
@login_required
def test_send_message(request):
    """Simple test function to debug message sending"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        room_id = data.get('room_id')
        content = sanitize_input(data.get('content', '')).strip()
        
        if not room_id or not content:
            return JsonResponse({'error': 'Room ID and content required'}, status=400)
        
        room = get_object_or_404(Room, id=room_id)
        
        # Simple logic: client sends to owner, owner sends to first client who messaged
        if hasattr(request.user, 'client'):
            receiver = room.owner.user
            client = request.user.client
            owner = room.owner
        elif hasattr(request.user, 'owner'):
            # Find any client who has messaged in this room
            client_message = Message.objects.filter(
                room=room,
                sender__client__isnull=False
            ).first()
            
            if client_message:
                receiver = client_message.sender
                client = receiver.client
                owner = request.user.owner
            else:
                return JsonResponse({'error': 'No client found to reply to'}, status=400)
        else:
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        # Get or create conversation
        conversation, created = Conversation.objects.get_or_create(
            client=client,
            owner=owner,
            room=room
        )
        
        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            receiver=receiver,
            room=room,
            content=content
        )
        
        return JsonResponse({
            'success': True,
            'message': {
                'id': message.id,
                'content': message.content,
                'timestamp': message.timestamp.isoformat(),
                'sender_name': message.sender.username,
                'receiver_name': message.receiver.username
            }
        })
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_owner_messages(request):
    try:
        owner = request.user.owner
    except Owner.DoesNotExist:
        return JsonResponse({'error': 'Owner account required'}, status=403)
    
    try:
        conversations = []
        client_ids = set()
        
        # Get unique clients who have messaged the owner
        unique_clients = Message.objects.filter(
            room__owner=owner
        ).filter(
            Q(sender__client__isnull=False, receiver=request.user) | Q(sender=request.user, receiver__client__isnull=False)
        ).values_list('sender', 'receiver').distinct()
        
        for sender_id, receiver_id in unique_clients:
            if sender_id != request.user.id:
                client_ids.add(sender_id)
            if receiver_id != request.user.id:
                client_ids.add(receiver_id)
        
        for client_id in client_ids:
            client_user = User.objects.get(id=client_id)
            
            # Get latest message between this specific client and owner
            latest_message = Message.objects.filter(
                room__owner=owner
            ).filter(
                Q(sender=client_user, receiver=request.user) | Q(sender=request.user, receiver=client_user)
            ).order_by('-timestamp').first()
                
            if latest_message:
                unread_count = Message.objects.filter(
                    room__owner=owner,
                    sender=client_user,
                    receiver=request.user,
                    read_status=False
                ).count()
                
                try:
                    profile_image = client_user.userprofile.get_profile_image()
                except:
                    profile_image = None
                
                conversations.append({
                    'room_id': latest_message.room.id,
                    'room_title': latest_message.room.title,
                    'client_id': client_user.id,
                    'client_name': client_user.get_full_name() or client_user.username,
                    'profile_image': profile_image,
                    'last_message': latest_message.content[:50] + ('...' if len(latest_message.content) > 50 else ''),
                    'last_message_time': latest_message.timestamp.isoformat(),
                    'unread_count': unread_count
                })
        
        conversations.sort(key=lambda x: x['last_message_time'], reverse=True)
        return JsonResponse({'conversations': conversations})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
