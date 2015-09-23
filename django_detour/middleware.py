"""This module defines methods for implementing HTTP redirects.

Redirects are read from CSV files. In the case the Django app returns
a 404 response, the original request URL is looked up in the redirects
table and if one is found the appropriate redirect response is returned
instead.
"""

import os

import warnings

from collections import defaultdict

from django.utils import six
from django.conf import settings
from django.http import HttpResponse
from django.core.exceptions import ImproperlyConfigured
from django.contrib.sites.models import get_current_site
from django.utils.encoding import iri_to_uri

if six.PY2:
    import urlparse
    import unicodecsv as csv
else:
    from urllib import parse as urlparse
    import csv

def get_redirect(redirects, path, full_uri):
    if full_uri in redirects:
        redirect = redirects[full_uri]
    elif iri_to_uri(path) in redirects:
        redirect = redirects[iri_to_uri(path)]
    elif path in redirects:
        redirect = redirects[path]
    else:
        return None

    #target = redirec['target']
    #status_code = redirec['status_code']
    target = redirect.target
    status_code = redirect.status_code

    response = HttpResponse('', status=status_code)
    response['Location'] = target or None

    return response


def scrape_redirects(redirect_path):
    for filename in os.listdir(redirect_path):
        if filename.endswith('.csv'):
            path = os.path.join(redirect_path, filename)
            reader = csv.DictReader(
                open(path, 'r'),
                fieldnames=['source', 'target', 'status_code', 'domain']
            )
            for index, line in enumerate(reader):
                yield dict(line, filename=filename, line_number=index)


class Redirect(object):
    """
    Encapulates all of the information about a redirect.
    """
    def __init__(self, source, target, status_code, domain, filename, line_number):
        self.source = source.strip()
        self.parsed_source = urlparse.urlparse(self.source)
        self.target = (target or '').strip()
        self.parsed_target = urlparse.urlparse(self.target)
        self.domain = domain
        if target:
            self.status_code = int(status_code or 301)
        else:
            self.status_code = 410

        self.filename = filename
        self.line_number = line_number

        self._errors = None

    @property
    def errors(self):
        if self._errors is None:
            self.validate()
        return self._errors

    def is_valid(self):
        return bool(self.errors)

    def add_error(self, field, message):
        if self._errors is None:
            self._errors = defaultdict(list)
        self._errors[field].append(message)

    def validate(self):
        self._errors = self._errors or {}
        if self.status_code < 300 or self.status_code > 399 and not self.status_code == 410:
            self.add_error(
                'status_code',
                "ERROR: {redirect.filename}:{redirect.line_number} "
                "- Non 3xx/410 status code({redirect.status_code})"
                .format(redirect=self),
            )


def preprocess_redirects(lines, raise_errors=True):
    """
    Takes a list of dictionaries read from the csv redirect files, creates
    Redirect objects from them, and validates the redirects, returning a
    dictionary of Redirect objects.
    """
    error_messages = defaultdict(list)
    warning_messages = defaultdict(list)

    processed_redirects = {}
    for line in lines:
        redirect = Redirect(**line)
        # Runs internal validation on the redirect
        if not redirect.is_valid():
            for message in redirect.errors.values():
                error_messages[redirect.source] = message

        # Catch duplicate declaration of source urls.
        if redirect.source in processed_redirects:
            warning_messages[redirect.source].append(
                "WARNING: {filename}:{line_number} "
                "-  Duplicate declaration of url"
                .format(**line)
            )
        processed_redirects[redirect.source] = redirect

    def validate_redirect(redirect, with_slash=False):
        """
        Finds circular and possible circular redirects.
        """
        to_url = redirect.parsed_target
        if with_slash:
            if not to_url.path.endswith('/'):
                to_url = to_url._replace(path=to_url.path + '/')
            else:
                return
        if (redirect.target in processed_redirects
            or redirect.target == redirect.parsed_source.path):
            error_messages[redirect.source].append(
                'ERROR: {redirect.filename}:{redirect.line_number} '
                '- Circular redirect: {redirect.source} => {redirect.target}'
                .format(redirect=redirect)
            )
        elif (urlparse.urljoin(redirect.source, to_url.path) in processed_redirects
              and not redirect.status_code == 410):
            if not to_url.netloc:
                error_messages[redirect.source].append(
                    'ERROR: {redirect.filename}:{redirect.line_number} '
                    '- Circular redirect: {redirect.source} => {redirect.target}'
                    .format(redirect=redirect)
                )
            elif to_url.netloc and not redirect.parsed_source.netloc:
                warning_messages[redirect.source].append(
                    'WARNING: {redirect.filename}:{redirect.line_number}: '
                    '- Possible circular redirect if hosting on domain '
                    '{redirect.parsed_target.netloc}: {redirect.source} => '
                    '{redirect.target}'.format(redirect=redirect)
                )

    # Check for circular redirects.
    for source, redirect in processed_redirects.items():
        validate_redirect(redirect)
        if settings.APPEND_SLASH:
            validate_redirect(redirect, with_slash=True)

    # Now that we're done, either raise an exception if an error was raised and
    # we are not just running in validation mode
    if error_messages and raise_errors:
        raise ImproperlyConfigured('There were errors while parsing redirects. '
                                   'Run ./manage.py validate_redirects for error details')
    # Output warnings for all errors and warnings found.
    for messages in warning_messages.values() + error_messages.values():
        for message in messages:
            warnings.warn(message)

    return processed_redirects


class RedirectFallbackMiddleware(object):
    """
    This middleware handles 3xx redirects and 410s.

    Only 404 responses will be redirected, so if something else is returning a
    non 404 error, this middleware will not produce a redirect

    Redirects should be formatted in CSV files located in either
    ``<project_path>/redirects/`` or an absolute path declared in
    ``settings.REDIRECTS_DIRECTORY``.

    CSV files should not contain any headers, and be in the format ``source_url,
    target_url, status_code`` where ``status_code`` is optional and defaults to 301.
    To issue a 410, leave off target url and status code.
    """
    def __init__(self, *args, **kwargs):
        raise_errors = kwargs.pop('raise_errors', True)
        super(RedirectFallbackMiddleware, self).__init__(*args, **kwargs)
        raw_redirects = self.get_redirects()
        self.redirects = preprocess_redirects(raw_redirects, raise_errors)

    def get_redirects(self):
        # Get redirect directory
        redirect_path = getattr(settings, 'REDIRECTS_DIRECTORY',
                               os.path.join(settings.PROJECT_PATH, '..', 'redirects'))

        # Crawl the REDIRECTS_DIRECTORY scraping any CSV files found
        lines = scrape_redirects(redirect_path)

        #redirects = preprocess_redirects(lines)
        return lines

    def process_response(self, request, response):
        if response.status_code != 404 and get_current_site(request).domain == request.get_host():
            # No need to check for a redirect for non-404 responses, as long as
            # it's our Site.
            return response
        path = request.get_full_path()
        full_uri = request.build_absolute_uri()

        return get_redirect(self.redirects, path, full_uri) or response
