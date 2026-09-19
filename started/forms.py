from django import forms
from django.core.exceptions import ValidationError
from .models import Room
from .security_utils import sanitize_input, validate_phone_number, validate_email_domain

class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        exclude = ['owner']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'e.g., Modern Studio in Downtown', 'class': 'form-control'}),
            'location': forms.TextInput(attrs={'placeholder': 'Enter address', 'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'placeholder': 'e.g., 15000', 'class': 'form-control', 'min': '0'}),
            'contact_phone': forms.TextInput(attrs={'placeholder': '+91 98765 43210', 'class': 'form-control'}),
            'contact_email': forms.EmailInput(attrs={'placeholder': 'your@email.com', 'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Describe your property...', 'class': 'form-control'}),
            'room_type': forms.Select(attrs={'class': 'form-control'}),
            'area_m2': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'beds': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'baths': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }
    
    def clean_title(self):
        title = self.cleaned_data.get('title')
        return sanitize_input(title)
    
    def clean_description(self):
        description = self.cleaned_data.get('description')
        return sanitize_input(description)
    
    def clean_location(self):
        location = self.cleaned_data.get('location')
        return sanitize_input(location)
    
    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price and price <= 0:
            raise ValidationError('Price must be greater than 0')
        return price
    
    def clean_contact_phone(self):
        phone = self.cleaned_data.get('contact_phone')
        return validate_phone_number(phone)
    
    def clean_contact_email(self):
        email = self.cleaned_data.get('contact_email')
        return validate_email_domain(email)