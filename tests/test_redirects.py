import os

from django_detour.redirects import RedirectMap
from django.test import TestCase


def get_redirect_dir(name):
    return os.path.join(os.path.dirname(__file__), 'redirects', name)


class RedirectTest(TestCase):
    def test_circular(self):
        redirects = RedirectMap()
        redirects.load_redirects(get_redirect_dir('circular'))

        # Detect circular redirects
        assert not redirects.is_valid()
        # Don't warn twice about the same loop
        assert len(redirects.errors) == 1

    def test_complex_circular(self):
        redirects = RedirectMap()
        redirects.load_redirects(get_redirect_dir('longcircular'))

        # Detect circular redirects
        assert not redirects.is_valid()
        # Don't warn twice about the same lop
        assert len(redirects.errors) == 2
