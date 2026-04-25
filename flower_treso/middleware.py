from django.shortcuts import redirect
from django.urls import reverse
import re

class GlobalLoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt_urls = [
            re.compile(r'^/accounts/'),
            re.compile(r'^/static/'),
            re.compile(r'^/media/'),
        ]

    def __call__(self, request):
        if not request.user.is_authenticated:
            path = request.path_info
            if not any(m.match(path) for m in self.exempt_urls):
                return redirect(f"{reverse('account_login')}?next={path}")
        
        return self.get_response(request)
