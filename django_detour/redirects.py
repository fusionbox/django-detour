from __future__ import unicode_literals

from collections import namedtuple, deque
import logging
import os

import six
if six.PY2:
    import unicodecsv as csv
else:
    import csv

from six.moves import http_client
from six.moves.urllib import parse as urlparse

from django.conf import settings
from django.utils.translation import ugettext as _

logger = logging.getLogger(__name__)


ALL_DOMAINS = '__all__'


def append_slash(s):
    if not s.endswith('/'):
        return s + '/'
    else:
        return s

def split_url(url):
    domain = urlparse.urlparse(url).netloc
    if not domain:
        domain = ALL_DOMAINS

    _, _, path, params, query, fragment = urlparse.urlparse(url)
    full_path = urlparse.urlunparse(
        urlparse.ParseResult('', '', path, params, query, fragment)
    )

    return domain, full_path


class Redirect(namedtuple('RedirectBase', ['lineno', 'fname', 'target', 'status_code'])):
    VALID_STATUS_CODES = {301, 302, 303, 307, 410}
    REDIRECT_CODES = {301, 302, 303, 307}

    def __init__(self, *args, **kwargs):
        super(Redirect, self).__init__(*args, **kwargs)
        self._errors = None

    @property
    def target_set(self):
        res = set([self.target])
        if settings.APPEND_SLASH:
            res |= set([append_slash(self.target)])
        return res

    @property
    def errors(self):
        if self._errors is None:
            self.full_clean()
        return self._errors

    def full_clean(self):
        if self._errors is None:
            self._errors = []

        if self.status_code not in self.VALID_STATUS_CODES:
            self._errors.append(_("Invalid status code {status_code}").format(self.status_code))

    def is_valid(self):
        return bool(self.errors)

    @property
    def is_redirect(self):
        return self.status_code in self.REDIRECT_CODES


class RedirectMap(dict):
    """
    This a mapping:
        domain -> path -> path/fullurl

    We didn't go with a mapping
        fullurl -> path/fullurl

    Because this allow us to ignore whether the redirect CSV contains https or http URL.
    In addition, this makes the code simpler, because the path and the domain are two different
    variable in the middleware. We would have had to build a url from the domain on the path
    """
    def __init__(self, *args, **kwargs):
        super(RedirectMap, self).__init__(*args, **kwargs)
        self._errors = None

    def load_redirects(self, directory):
        for fname in os.listdir(directory):
            _, ext = os.path.splitext(fname)
            if ext == '.csv':
                path = os.path.join(directory, fname)
                with open(path, 'r') as fp:
                    reader = csv.DictReader(fp, fieldnames=['source', 'target', 'status_code'])
                    for lineno, columns in enumerate(reader):
                        self.add_redirect(fname=os.path.basename(path), lineno=lineno, **columns)

    def add_redirect(self, fname, lineno, source, target=None, status_code=None):
        if not status_code:
            if not target:
                status_code = http_client.GONE
            else:
                status_code = http_client.FOUND
        else:
            status_code = int(status_code)

        domain, path = split_url(source)
        self.setdefault(domain, {})

        self[domain][path] = Redirect(
            fname=fname,
            lineno=lineno,
            target=target,
            status_code=status_code
        )

    def clean_circular(self):
        """
        Find circular imports
        """
        def get_circular(trail):
            assert len(trail) > 0

            visited = {r.target for r in trail}

            start = trail[-1]
            for dest in start.target_set:
                domain, path = split_url(dest)

                new_dest = self.get_redirect(path, domain)
                if new_dest.target in visited:
                    return trail

                res = get_circular(trail + [new_dest])
                if res is not None:
                    return res

        part_of_circular = set()

        for domain, redirects in six.iteritems(self):
            for source, dest in six.iteritems(redirects):
                if source in part_of_circular:
                    continue

                visited = set()
                to_visit = deque()

                to_visit.extend(dest.target_set)
                while to_visit:
                    elem = to_visit.popleft()
                    if elem not in visited:
                        visited.add(elem)

                        domain, path = split_url(elem)
                        if domain in self:
                            new_dest = self.get_redirect(path, domain)
                            if new_dest is not None and new_dest.is_redirect:
                                to_visit.extend(new_dest.target_set)
                    else:
                        circular = get_circular([dest])
                        part_of_circular.update({t.target for t in circular})
                        circular_msg = ' -> '.join([
                            '{r.target} ({r.fname}:{r.lineno})'.format(r=r)
                            for r in circular
                        ])
                        self._errors.append(
                            "Possible circular redirect: {}".format(circular_msg)
                        )
                        break

    def clean_redirects(self):
        pass

    def full_clean(self):
        if self._errors is None:
            self._errors = []
            # TODO: Actually raise and catch a ValidationError here
            self.clean_redirects()
            self.clean_circular()

    @property
    def errors(self):
        if self._errors is None:
            self.full_clean()
        return self._errors

    def is_valid(self):
        return not bool(self.errors)

    def get_redirect(self, path, domain=None):
        if domain is None:
            domain = ALL_DOMAINS

        redirect = self.get(domain, {}).get(path)
        if redirect is None:
            redirect = self.get(ALL_DOMAINS, {}).get(path)
        return redirect
