from django.test import TestCase, Client as TestClient
from django.contrib.auth.models import User
from django.urls import reverse
from started.models import Owner, Client, Room, UserProfile, Message, Conversation, ClientPayment
from decimal import Decimal

class ModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.profile = UserProfile.objects.create(user=self.user)
        
    def test_user_profile_creation(self):
        self.assertEqual(str(self.profile), 'testuser Profile')
        self.assertIsNone(self.profile.get_profile_image())
        
    def test_pin_generation(self):
        pin = self.profile.generate_reset_pin()
        self.assertEqual(len(pin), 6)
        self.assertTrue(self.profile.is_pin_valid())
        
    def test_owner_creation(self):
        owner = Owner.objects.create(
            user=self.user,
            phone='1234567890',
            address='Test Address'
        )
        self.assertEqual(str(owner), 'Room Owner: testuser')
        
    def test_client_creation(self):
        client = Client.objects.create(
            user=self.user,
            phone='1234567890',
            preferred_location='Test Location'
        )
        self.assertEqual(str(client), 'Client: testuser')

class ViewTests(TestCase):
    def setUp(self):
        self.client = TestClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.owner_user = User.objects.create_user(
            username='owner',
            email='owner@example.com',
            password='testpass123'
        )
        self.client_user = User.objects.create_user(
            username='client',
            email='client@example.com',
            password='testpass123'
        )
        
        self.owner = Owner.objects.create(
            user=self.owner_user,
            phone='1234567890',
            address='Owner Address'
        )
        
        self.client_profile = Client.objects.create(
            user=self.client_user,
            phone='0987654321',
            preferred_location='Client Location'
        )
        
        self.room = Room.objects.create(
            title='Test Room',
            room_type='private',
            location='Test Location',
            price=Decimal('15000.00'),
            description='Test Description',
            contact_phone='1234567890',
            contact_email='test@example.com',
            owner=self.owner
        )
        
    def test_login_view(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        
    def test_register_view(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        
    def test_client_dashboard_requires_login(self):
        response = self.client.get(reverse('client_dashboard'))
        self.assertRedirects(response, '/login/?next=/client/dashboard/')
        
    def test_owner_dashboard_requires_login(self):
        response = self.client.get(reverse('owner_dashboard'))
        self.assertRedirects(response, '/login/?next=/owner/dashboard/')
        
    def test_client_dashboard_with_login(self):
        self.client.login(username='client', password='testpass123')
        response = self.client.get(reverse('client_dashboard'))
        self.assertEqual(response.status_code, 200)
        
    def test_owner_dashboard_with_login(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('owner_dashboard'))
        self.assertEqual(response.status_code, 200)

class PaymentTests(TestCase):
    def setUp(self):
        self.client = TestClient()
        self.owner_user = User.objects.create_user(
            username='owner',
            email='owner@example.com',
            password='testpass123'
        )
        self.client_user = User.objects.create_user(
            username='client',
            email='client@example.com',
            password='testpass123'
        )
        
        self.owner = Owner.objects.create(
            user=self.owner_user,
            phone='1234567890',
            address='Owner Address'
        )
        
        self.client_profile = Client.objects.create(
            user=self.client_user,
            phone='0987654321'
        )
        
        self.room = Room.objects.create(
            title='Test Room',
            room_type='private',
            location='Test Location',
            price=Decimal('15000.00'),
            description='Test Description',
            contact_phone='1234567890',
            contact_email='test@example.com',
            owner=self.owner
        )
        
    def test_client_payment_creation(self):
        payment = ClientPayment.objects.create(
            client=self.client_profile,
            owner=self.owner,
            room=self.room,
            transaction_id='test_123',
            status='success'
        )
        self.assertEqual(payment.amount, Decimal('30.00'))
        self.assertEqual(payment.status, 'success')

class MessageTests(TestCase):
    def setUp(self):
        self.owner_user = User.objects.create_user(
            username='owner',
            email='owner@example.com',
            password='testpass123'
        )
        self.client_user = User.objects.create_user(
            username='client',
            email='client@example.com',
            password='testpass123'
        )
        
        self.owner = Owner.objects.create(
            user=self.owner_user,
            phone='1234567890',
            address='Owner Address'
        )
        
        self.client_profile = Client.objects.create(
            user=self.client_user,
            phone='0987654321'
        )
        
        self.room = Room.objects.create(
            title='Test Room',
            room_type='private',
            location='Test Location',
            price=Decimal('15000.00'),
            description='Test Description',
            contact_phone='1234567890',
            contact_email='test@example.com',
            owner=self.owner
        )
        
        self.conversation = Conversation.objects.create(
            client=self.client_profile,
            owner=self.owner,
            room=self.room
        )
        
    def test_message_creation(self):
        message = Message.objects.create(
            conversation=self.conversation,
            sender=self.client_user,
            receiver=self.owner_user,
            room=self.room,
            content='Test message'
        )
        self.assertEqual(str(message), 'client to owner: Test message')
        self.assertFalse(message.read_status)