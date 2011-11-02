#!/usr/bin/python

# PdfSnip - PDF merging, rearranging, and splitting tool
# Copyright (C) 2010 Volodymyr Buell
# Copyright (C) 2008-2009 Konstantinos Poulios
# <https://sourceforge.net/projects/pdfshuffler>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

import os
import re
from distutils.core import setup

data_files=[('share/applications/', ['data/pdfsnip.desktop']),
#            ('share/pixmaps/', ['data/icons/pdfsnip.svg']),
            ('share/pixmaps/', ['data/icons/pdfsnip.png']),
            ('share/pdfsnip/', ['data/glade/topwindow.ui']),

            ("share/icons/hicolor/16x16/apps", ["data/icons/16x16/pdfsnip.png"]),
            ("share/icons/hicolor/22x22/apps", ["data/icons/22x22/pdfsnip.png"]),
            ("share/icons/hicolor/24x24/apps", ["data/icons/24x24/pdfsnip.png"]),
            ("share/icons/hicolor/32x32/apps", ["data/icons/32x32/pdfsnip.png"]),
            ("share/icons/hicolor/48x48/apps", ["data/icons/48x48/pdfsnip.png"]),
            ("share/icons/hicolor/64x64/apps", ["data/icons/64x64/pdfsnip.png"]),
            ("share/icons/hicolor/128x128/apps", ["data/icons/128x128/pdfsnip.png"]),
            ("share/icons/hicolor/256x256/apps", ["data/icons/256x256/pdfsnip.png"])  ]
#            ("share/icons/hicolor/scalable/apps", ["data/icons/pdfsnip.svg"])  ]


# Freshly generate .mo from .po, add to data_files:
if os.path.isdir('mo/'):
    os.system ('rm -r mo/')
for name in os.listdir('po'):
    m = re.match(r'(.+)\.po$', name)
    if m is not None:
        lang = m.group(1)
        out_dir = 'mo/%s/LC_MESSAGES' % lang
        out_name = os.path.join(out_dir, 'pdfsnip.mo')
        install_dir = 'share/locale/%s/LC_MESSAGES/' % lang
        os.makedirs(out_dir)
        os.system('msgfmt -o %s po/%s' % (out_name, name))
        data_files.append((install_dir, [out_name]))

setup(name='pdfsnip',
      version='0.0.10',
      author='Volodymyr Buell',
      author_email='vbuell @ gmail.com',
      description='GTK+ based utility for splitting, rearrangement and modification of PDF documents.',
      url = 'http://code.google.com/p/pdfsnip/',
      license='GNU GPL-2',
      scripts=['pdfsnip.py'],
      data_files=data_files
     )

# Clean up temporary files
if os.path.isdir('mo/'):
    os.system ('rm -r mo/')
if os.path.isdir('build/'):
    os.system ('rm -r build/')

