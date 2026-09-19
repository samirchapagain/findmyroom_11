import logging
from django.http import JsonResponse
from django.shortcuts import render
from django.conf import settings

logger = logging.getLogger(__name__)

class ErrorHandlingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_exception(self, request, exception):
        logger.error(f"Unhandled exception: {exception}", exc_info=True)
        
        if request.path.startswith('/api/'):
            return JsonResponse({
                'error': 'Internal server error',
                'message': str(exception) if settings.DEBUG else 'Something went wrong'
            }, status=500)
        
        return render(request, 'started/error.html', {
            'error': str(exception) if settings.DEBUG else 'Something went wrong'
        }, status=500)