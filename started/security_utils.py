import re
import html
from django.utils.html import escape
from django.core.exceptions import ValidationError

def sanitize_input(text):
    """Sanitize user input to prevent XSS attacks"""
    if not text:
        return text
    
    # Remove potentially dangerous HTML tags
    dangerous_tags = ['script', 'iframe', 'object', 'embed', 'form', 'input']
    for tag in dangerous_tags:
        text = re.sub(f'<{tag}[^>]*>.*?</{tag}>', '', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(f'<{tag}[^>]*/?>', '', text, flags=re.IGNORECASE)
    
    # Escape remaining HTML
    return escape(text)

def validate_phone_number(phone):
    """Validate phone number format"""
    if not phone:
        return phone
    
    # Remove all non-digit characters
    digits_only = re.sub(r'\D', '', phone)
    
    # Check if it's a valid length (10-15 digits)
    if len(digits_only) < 10 or len(digits_only) > 15:
        raise ValidationError('Phone number must be between 10-15 digits')
    
    return digits_only

def validate_email_domain(email):
    """Basic email domain validation"""
    if not email:
        return email
    
    # Basic email format check
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        raise ValidationError('Invalid email format')
    
    return email.lower()

def safe_int(value, default=0):
    """Safely convert value to integer"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def safe_decimal(value, default=0.0):
    """Safely convert value to decimal"""
    try:
        from decimal import Decimal
        return Decimal(str(value))
    except (ValueError, TypeError):
        return Decimal(str(default))