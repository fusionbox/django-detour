"""This module contains a modified redirect middleware that is compatible with Mezzanine."""
from __future__ import absolute_import

from django.utils import six
from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site

from ..middleware import (
    RedirectFallbackMiddleware as PlainRedirectFallbackMiddleware,
    get_redirect
)

if six.PY2:
    from urlparse import urlparse
else:
    from urllib.parse import urlparse

class RedirectFallbackMiddleware(PlainRedirectFallbackMiddleware):
    def process_response(self, request, response):
        is_404 = response.status_code == 404
        is_my_site = get_current_site(request).domain == request.get_host()

        # Mezzanine has a urlpattern for all urls that end in a slash, so
        # CommonMiddleware redirects all 404s. We still need to check for a
        # redirect in this case.
        is_common_redirect = False
        if settings.APPEND_SLASH and response.status_code == 301:
            parsed = urlparse(response['Location'])
            if parsed.path == request.path_info + '/':
                is_common_redirect = True

        if (is_404 or not is_my_site) or is_common_redirect:
            path = request.get_full_path()
            full_uri = request.build_absolute_uri()
            response = get_redirect(self.redirects, path, full_uri) or response
        return response
