import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import Room, Message, ClientPayment, Conversation, Owner, Client

logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            self.room_id = self.scope['url_route']['kwargs']['room_id']
            self.room_group_name = f'chat_{self.room_id}'
            self.user = self.scope['user']
            
            if not self.user.is_authenticated:
                await self.close()
                return
            
            # Check if user has access to this room
            has_access = await self.check_room_access()
            if not has_access:
                await self.close()
                return
            
            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            await self.accept()
        except Exception as e:
            logger.error(f"Error in ChatConsumer connect: {e}")
            await self.close()
    
    async def disconnect(self, close_code):
        try:
            # Leave room group
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
        except Exception as e:
            logger.error(f"Error in ChatConsumer disconnect: {e}")
    
    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type', 'chat_message')
            
            if message_type == 'chat_message':
                message = text_data_json.get('message', '').strip()
                receiver_id = text_data_json.get('receiver_id')
                
                if not message:
                    return
                
                # Save message to database
                saved_message = await self.save_message(message, receiver_id)
                
                if saved_message:
                    # Send message to room group
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'chat_message',
                            'message': saved_message
                        }
                    )
        except json.JSONDecodeError:
            logger.error("Invalid JSON received in ChatConsumer")
        except Exception as e:
            logger.error(f"Error in ChatConsumer receive: {e}")
    
    async def chat_message(self, event):
        try:
            message = event['message']
            
            # Send message to WebSocket
            await self.send(text_data=json.dumps({
                'type': 'chat_message',
                'message': message
            }))
        except Exception as e:
            logger.error(f"Error in ChatConsumer chat_message: {e}")
    
    @database_sync_to_async
    def check_room_access(self):
        try:
            room = Room.objects.get(id=self.room_id)
            
            # Check if user is client with access or room owner
            if hasattr(self.user, 'client'):
                return ClientPayment.objects.filter(
                    client=self.user.client,
                    room=room,
                    status='success'
                ).exists()
            elif hasattr(self.user, 'owner'):
                return room.owner == self.user.owner
            
            return False
        except Room.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Error checking room access: {e}")
            return False
    
    @database_sync_to_async
    def save_message(self, content, receiver_id):
        try:
            room = Room.objects.get(id=self.room_id)
            
            # Determine receiver and conversation participants
            if hasattr(self.user, 'client'):
                receiver = room.owner.user
                client = self.user.client
                owner = room.owner
            elif hasattr(self.user, 'owner'):
                if receiver_id:
                    receiver = User.objects.get(id=receiver_id)
                    client = receiver.client
                    owner = self.user.owner
                else:
                    return None
            else:
                return None
            
            # Get or create conversation
            conversation, created = Conversation.objects.get_or_create(
                client=client,
                owner=owner,
                room=room
            )
            
            message = Message.objects.create(
                conversation=conversation,
                sender=self.user,
                receiver=receiver,
                room=room,
                content=content
            )
            
            return {
                'id': message.id,
                'content': message.content,
                'sender_id': message.sender.id,
                'sender_name': message.sender.username,
                'receiver_id': message.receiver.id,
                'timestamp': message.timestamp.isoformat(),
                'is_mine': True
            }
        except Exception as e:
            logger.error(f"Error saving message: {e}")
            return None

class PaymentConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            self.user = self.scope['user']
            
            if not self.user.is_authenticated:
                await self.close()
                return
            
            # Join user-specific group for payment notifications
            self.user_group_name = f'client_{self.user.id}'
            
            await self.channel_layer.group_add(
                self.user_group_name,
                self.channel_name
            )
            
            await self.accept()
        except Exception as e:
            logger.error(f"Error in PaymentConsumer connect: {e}")
            await self.close()
    
    async def disconnect(self, close_code):
        try:
            # Leave user group
            if hasattr(self, 'user_group_name'):
                await self.channel_layer.group_discard(
                    self.user_group_name,
                    self.channel_name
                )
        except Exception as e:
            logger.error(f"Error in PaymentConsumer disconnect: {e}")
    
    async def payment_success(self, event):
        try:
            # Send payment success notification to WebSocket
            await self.send(text_data=json.dumps({
                'type': 'payment_success',
                'room_id': event['room_id'],
                'message': event['message']
            }))
        except Exception as e:
            logger.error(f"Error in PaymentConsumer payment_success: {e}")