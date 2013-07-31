# Copyright (C) 2008-2009 Open Society Institute
#               Thomas Moroz: tmoroz@sorosny.org
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License Version 2 as published
# by the Free Software Foundation.  You may not use, modify or distribute
# this program under any other version of the GNU General Public License.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.

__version__ = '1.24'

import os
import sys

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
try:
    README = open(os.path.join(here, 'README.txt')).read()
    CHANGES = open(os.path.join(here, 'CHANGES.txt')).read()
except IOError:
    README = ''
    CHANGES = ''

requires = [
    'pyramid_tm',
    'pyramid_zodbconn',
    'karl',
    'repoze.depinj',
    'repoze.retry',
    'repoze.urchin',
    'WebTest',
]

if sys.version_info[:2] < (2, 7):
    requires.append('argparse')

setup(name='karlserve',
      version=__version__,
      description='Easily serve multiple instances of Karl.',
      long_description=README + '\n\n' +  CHANGES,
      classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Topic :: Internet :: WWW/HTTP :: WSGI",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
        ],
      author='',
      author_email='',
      url='',
      keywords='web wsgi bfg zope',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      install_requires = requires,
      tests_require = requires,
      test_suite="karlserve",
      entry_points = """\
      [paste.app_factory]
      application = karlserve.application:make_app

      [paste.filter_app_factory]

      [console_scripts]
      karlserve = karlserve.scripts.main:main

      [karlserve.scripts]
      create_mailin_trace = karlserve.scripts.create_mailin_trace:config_parser
      debug = karlserve.scripts.debug:config_parser
      digest = karlserve.scripts.digest:config_parser
      evolve = karlserve.scripts.evolve:config_parser
      feeds = karlserve.scripts.feeds:config_parser
      mailin = karlserve.scripts.mailin:config_parser
      mailout = karlserve.scripts.mailout:config_parser
      migrate_ini = karlserve.scripts.migrate:config_parser
      mode = karlserve.scripts.mode:config_parser
      peopleconf = karlserve.scripts.peopleconf:config_parser
      samplegen = karlserve.scripts.samplegen:config_parser
      serve = karlserve.scripts.serve:config_parser
      settings = karlserve.scripts.settings:config_parser
      reindex_text = karlserve.scripts.reindex_text:config_parser
      """
      )

