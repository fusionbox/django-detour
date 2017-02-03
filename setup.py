#!/usr/bin/env python
import os

from setuptools import setup, find_packages

# FIXME: Please fix this setup.py file

current_directory = os.path.dirname(__file__)
with open(os.path.join(current_directory, 'README.rst')) as f:
    README = f.read()

version = '0.0.10'

setup(name='django-detour',
    version=version,
    description="Manages mass redirects. Very useful after a website redesign.",
    author="Fusionbox, Inc.",
    author_email="programmers@fusionbox.com",
    keywords="django redirect redirection mass massive redirects bulk csv",
    long_description=README,
    url="https://github.com/fusionbox/django-detour",
    packages=find_packages(),
    platforms="any",
    license="BSD",
    classifiers=[
        "Environment :: Web Environment",
        "Framework :: Django",
    ],
    install_requires=[],
    requires=[],
)
