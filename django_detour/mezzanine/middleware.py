# FIXME: Unused import
from urlparse import urlparse

from django.conf import settings
from django.contrib.sites.models import get_current_site

from mezzanine.pages.views import page as page_view
from mezzanine.pages.models import Page
from mezzanine.utils.urls import path_to_slug

from fusionbox.middleware import (
    RedirectFallbackMiddleware, get_redirect)


class RedirectFallbackMiddleware(RedirectFallbackMiddleware):
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
