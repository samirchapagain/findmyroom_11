import time
from django.http import HttpResponse
from django.core.cache import cache
from django.conf import settings

class RateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip rate limiting for static files and admin
        if request.path.startswith('/static/') or request.path.startswith('/admin/'):
            return self.get_response(request)
        
        # Get client IP
        ip = self.get_client_ip(request)
        
        # Different limits for different endpoints
        if request.path.startswith('/api/'):
            limit = 100  # 100 requests per minute for API
            window = 60
        elif request.method == 'POST':
            limit = 20   # 20 POST requests per minute
            window = 60
        else:
            limit = 200  # 200 GET requests per minute
            window = 60
        
        # Check rate limit
        cache_key = f'rate_limit_{ip}_{request.path}'
        current_requests = cache.get(cache_key, 0)
        
        if current_requests >= limit:
            return HttpResponse("Rate limit exceeded. Please try again later.", status=429)
        
        # Increment counter
        cache.set(cache_key, current_requests + 1, window)
        
        response = self.get_response(request)
        return response
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip