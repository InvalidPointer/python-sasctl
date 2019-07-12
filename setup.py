#!/usr/bin/env python
# encoding: utf-8
#
# Copyright © 2019, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import os
import re

from setuptools import setup, find_packages


def read_dunder(name):
    with open(os.path.join('src', 'sasctl', '__init__.py')) as f:
        for line in f.readlines():
            match = re.search(r'(?<=^__{}__ = [\'"]).*\b'.format(name), line)
            if match:
                return match.group(0)
        raise RuntimeError('Unable to find __%s__ in __init__.py' % name)


def get_file(filename):
    with open(filename, 'r') as f:
        return f.read()

setup(
    name='sasctl',
    description='SAS Viya REST Client',
    long_description=get_file('README.md'),
    long_description_content_type='text/markdown',
    version=read_dunder('version'),
    author=read_dunder('author'),
    url='https://github.com/sassoftware/python-sasctl/',
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        'requests',
        'six >= 1.11'
    ],
    extras_require = {
        'swat': ['swat'],
        'kerberos': ['kerberos ; platform_system != "Windows"',
                     'winkerberos ; platform_system == "Windows"'],
        'all': ['swat',
                'kerberos ; platform_system != "Windows"',
                'winkerberos ; platform_system == "Windows"'],
    },
    entry_points = {'console_scripts': ['sasctl = sasctl.utils.cli:main']},
    python_requires='>=2.7'
)