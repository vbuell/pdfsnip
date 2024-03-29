#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
 --------------------------------------------------------------------------
 PdfSnip - GTK+ based utility for splitting, rearrangement and modification 
 of PDF documents. 
 <http://code.google.com/p/pdfsnip/>
 
 Based on PDF-Shuffler by Konstantinos Poulios:
 <https://sourceforge.net/projects/pdfshuffler>

 --------------------------------------------------------------------------

 This program is free software; you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation; either version 2 of the License, or
 (at your option) any later version.

 This program is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License along
 with this program; if not, write to the Free Software Foundation, Inc.,
 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

 --------------------------------------------------------------------------
"""

import os
import shutil       #needed for file operations like whole directory deletion
import sys          #needed for proccessing of command line args
import urllib       #needed to parse filename information passed by DnD
import threading
import tempfile
import logging

import locale       #for multilanguage support
import gettext
gettext.install('pdfsnip', unicode=1)

try:
    import pygtk
    pygtk.require('2.0')
    import gtk
    assert gtk.gtk_version >= (2, 10, 0)
    assert gtk.pygtk_version >= (2, 10, 0)
except AssertionError:
    print('You do not have the required versions of GTK+ and/or PyGTK ' +
          'installed.\n\n' +
          'Installed GTK+ version is ' +
          '.'.join([str(n) for n in gtk.gtk_version]) + '\n' +
          'Required GTK+ version is 2.10.0 or higher\n\n'
          'Installed PyGTK version is ' +
          '.'.join([str(n) for n in gtk.pygtk_version]) + '\n' +
          'Required PyGTK version is 2.10.0 or higher')
    sys.exit(1)
except:
    print('PyGTK version 2.10.0 or higher is required to run this program.')
    print('No version of PyGTK was found on your system.')
    sys.exit(1)

import gobject      #to use custom signals
import pango        #to adjust the text alignment in CellRendererText
import gconf
import cairo

try:
    import djvu.decode
    found_djvu = True
except:
    found_djvu = False
    print("python-djvulibre wasn't found. Djvu is disabled.")

import poppler      #for the rendering of pdf pages
try:
    from pyPdf import PdfFileWriter, PdfFileReader
    found_pypdf = True
except:
    found_pypdf = False
    print("pyPdf wasn't found. Document saving is disabled.")

import subprocess
try:
    args = ["pdftk"]
    subprocess.call(args)
    found_pdftk = True
except:
    found_pdftk = False


VERSION = '0.1.1'

LOG_FILE = './pdfsnip.log'

ROOT_DIR = '/apps/pdfsnip'

KEY_THUMBNAILS = ROOT_DIR + '/prefer_embedded_thumbnails'
KEY_WINDOW_WIDTH = ROOT_DIR + '/ui_width'
KEY_WINDOW_HEIGHT = ROOT_DIR + '/ui_height'
KEY_USE_PDFTK = ROOT_DIR + '/use_pdftk'
KEY_THUMBNAILS_SIZE = ROOT_DIR + '/thumbnails_size'
KEY_THUMBNAILS_LAZY = ROOT_DIR + '/thumbnails_lazy'
KEY_FIT_WIDTH = ROOT_DIR + '/fit_width'
KEY_FIT_WIDTH_DUAL = ROOT_DIR + '/fit_width_double'

GIZMO_SIZES = [75, 100, 200, 300, 400, 500, 600, 700, 800]


class Preferences:
    """
    Application preferences. Note that not all are being saved to gconf.
    """
    gizmoSize = 2
    windowWidth = min(700, gtk.gdk.screen_get_default().get_width() / 2)
    windowHeight = min(600, gtk.gdk.screen_get_default().get_height() - 50)
    windowX = 200
    windowY = 200
    preferThumbnails = True
    usePdftk = True
    lazyThumbnailsRendering = True
    fitPageWidth = False
    fitPageWidthDual = False
    useAntialiazing = False
    pageWidth = 0

    @staticmethod
    def load():
        # GConf stuff
        gconf_client = gconf.client_get_default()
        Preferences.gconf_client = gconf_client
        gconf_client.add_dir(ROOT_DIR, gconf.CLIENT_PRELOAD_NONE)

        try:
            gconf_value = int(gconf_client.get_string(KEY_THUMBNAILS_SIZE))
            if gconf_value:
                Preferences.gizmoSize = gconf_value
            gconf_value = int(gconf_client.get_string(KEY_WINDOW_WIDTH))
            if gconf_value:
                Preferences.windowWidth = gconf_value
            gconf_value = int(gconf_client.get_string(KEY_WINDOW_HEIGHT))
            if gconf_value:
                Preferences.windowHeight = gconf_value
            gconf_value = gconf_client.get_bool(KEY_THUMBNAILS)
            if isinstance(gconf_value, bool):
                Preferences.preferThumbnails = gconf_value
            else:
                logging.error("Not a BOOL!!!! " + str(gconf_value))
            gconf_value = gconf_client.get_bool(KEY_USE_PDFTK)
            if isinstance(gconf_value, bool):
                Preferences.usePdftk = gconf_value
            else:
                logging.error("Not a BOOL!!!! " + str(gconf_value))
            gconf_value = gconf_client.get_bool(KEY_THUMBNAILS_LAZY)
            if isinstance(gconf_value, bool):
                Preferences.lazyThumbnailsRendering = gconf_value
            else:
                logging.error("Not a BOOL!!!! " + str(gconf_value))
            gconf_value = gconf_client.get_bool(KEY_FIT_WIDTH)
            if isinstance(gconf_value, bool):
                Preferences.fitPageWidth = gconf_value
            else:
                logging.error("Not a BOOL!!!! " + str(gconf_value))
            gconf_value = gconf_client.get_bool(KEY_FIT_WIDTH_DUAL)
            if isinstance(gconf_value, bool):
                Preferences.fitPageWidthDual = gconf_value
            else:
                logging.error("Not a BOOL!!!! " + str(gconf_value))
            logging.debug("Loaded preferences from gconf: " + str(Preferences.__dict__))
        except Exception, e:
            logging.exception(e)

    @staticmethod
    def save():
        Preferences.gconf_client.set_string(KEY_WINDOW_WIDTH, str(Preferences.windowWidth))
        Preferences.gconf_client.set_string(KEY_WINDOW_HEIGHT, str(Preferences.windowHeight))
        Preferences.gconf_client.set_bool(KEY_USE_PDFTK, Preferences.usePdftk)
        Preferences.gconf_client.set_string(KEY_THUMBNAILS_SIZE, str(Preferences.gizmoSize))
        Preferences.gconf_client.set_bool(KEY_THUMBNAILS_LAZY, Preferences.lazyThumbnailsRendering)
        Preferences.gconf_client.set_bool(KEY_FIT_WIDTH, Preferences.fitPageWidth)
        Preferences.gconf_client.set_bool(KEY_FIT_WIDTH_DUAL, Preferences.fitPageWidthDual)

        logging.debug("Preferences saved.")


class ListObject:
    def __init__(self):
        self.text = None            # 0.Text descriptor
        self.doc_number = None      # 2.Document number
        self.page_number = None     # 3.Page number
        self.thumbnail_width = None # 4.Thumbnail width
        self.thumbnail_size = (0, 0)# Thumbnail size
        self.doc_filename = None    # 5.Document filename
        self.rendered = False       # 6.Rendered
        self.rotation_angle = None  # 7.Rotation angle
        self.crop = [0., 0., 0., 0.]    # 8.Crop left
        self.need_to_be_rendered = None # 12.Need to be rendered

class PDFsnip(gtk.Builder):
    MODEL_ROW_INTERN = 1001
    MODEL_ROW_EXTERN = 1002
    TEXT_URI_LIST = 1003
    MODEL_ROW_MOTION = 1004
    TARGETS_IV = [('MODEL_ROW_INTERN', gtk.TARGET_SAME_WIDGET, MODEL_ROW_INTERN),
                  ('MODEL_ROW_EXTERN', gtk.TARGET_OTHER_APP, MODEL_ROW_EXTERN),
                  ('MODEL_ROW_MOTION', 0, MODEL_ROW_MOTION)]
    TARGETS_SW = [('text/uri-list', 0, TEXT_URI_LIST),
                  ('MODEL_ROW_EXTERN', gtk.TARGET_OTHER_APP, MODEL_ROW_EXTERN)]

    def __init__(self):
        super(PDFsnip, self).__init__()

        # Check first in the directory of this script.
        if os.path.isfile('data/glade/topwindow.ui'):
            glade_file = 'data/glade/topwindow.ui'
        # Then check to see if its installed on a *nix system
        elif os.path.isfile(os.path.join(os.path.dirname(sys.argv[0]), '../share/pdfsnip/topwindow.ui')):
            glade_file = os.path.join(os.path.dirname(sys.argv[0]), '../share/pdfsnip/topwindow.ui')
        else:
            print 'ERROR.'
            print 'Could not find the glade UI file.'
            print 'Try reinstalling the application.'
            sys.exit(1)

        self.add_from_file(glade_file)
        self.connect_signals(self)

        Preferences.load()

        self.menuitem12.set_active(Preferences.preferThumbnails)

        # Create Undo/Redo stack
        self.undo_stack = UndoRedoStack()

        # Create the temporary directory
        self.tmp_dir = tempfile.mkdtemp("pdfsnip")
        os.chmod(self.tmp_dir, 0700)

        try:
            icon_theme = gtk.icon_theme_get_default()
            if icon_theme.has_icon("pdfsnip"):
                sizes = icon_theme.get_icon_sizes("pdfsnip")
                logging.debug("Avail icon sizes: " + str(sizes))
                self.icon = icon_theme.load_icon("pdfsnip", max(sizes), gtk.ICON_LOOKUP_NO_SVG)
                gtk.window_set_default_icon(self.icon)
                logging.debug("Choosen icon size: " + str(max(sizes)))
        except Exception, e:
            logging.exception(e)
            logging.error("Can't load icon. Application isn't installed correctly.")

        self.is_dirty = False

        # Create the main window, and attach delete_event signal to terminating
        # the application
        window = self.topWindow
        window.set_border_width(0)
        window.move(Preferences.windowX, Preferences.windowY)
        window.set_default_size(Preferences.windowWidth,
                                     Preferences.windowHeight)

        # Create a scrolled widow to hold the thumnails-container
        sw = self.scrolledwindow1
        sw.drag_dest_set(gtk.DEST_DEFAULT_MOTION |
                              gtk.DEST_DEFAULT_HIGHLIGHT |
                              gtk.DEST_DEFAULT_DROP |
                              gtk.DEST_DEFAULT_MOTION,
                              self.TARGETS_SW,
                              gtk.gdk.ACTION_COPY |
                              gtk.gdk.ACTION_MOVE)
        sw.connect('drag_data_received', self.sw_dnd_received_data)
        sw.connect('button_press_event', self.sw_button_press_event)

        # Create ListStore model and IconView
        self.model = gtk.ListStore(str, gtk.gdk.Pixbuf, gobject.TYPE_PYOBJECT, str)
        self.iconview_col_width = self.get_current_gizmo_size()

        self.iconview = self.iconview2
        self.iconview.set_model(self.model)
        self.iconview.set_item_width(self.iconview_col_width + 12)

        # Borders and paddings
#        self.iconview.set_item_padding(1)
#        self.iconview.set_margin(0)
#        self.iconview.set_spacing(0)
#        self.iconview.set_column_spacing(0)
#        self.iconview.set_row_spacing(0)

        self.iconview.set_pixbuf_column(1)
#        self.cellpb = gtk.CellRendererPixbuf()
#        self.cellpb.set_property('follow-state', True)
#        self.iconview.pack_start(self.cellpb, False)
#        self.iconview.set_attributes(self.cellpb, pixbuf=1)

        self.iconview.set_tooltip_column(3)

#        self.iconview.set_text_column(0)
        self.celltxt = gtk.CellRendererText()
        self.celltxt.set_property('width', self.iconview_col_width)
        self.celltxt.set_property('wrap-width', self.iconview_col_width)
        self.celltxt.set_property('alignment', pango.ALIGN_CENTER)
        self.iconview.pack_start(self.celltxt, False)
        self.iconview.set_attributes(self.celltxt, text=0)

        self.iconview.set_selection_mode(gtk.SELECTION_MULTIPLE)
        self.iconview.enable_model_drag_source(gtk.gdk.BUTTON1_MASK,
                                               self.TARGETS_IV,
                                               gtk.gdk.ACTION_COPY |
                                               gtk.gdk.ACTION_MOVE)
        self.iconview.enable_model_drag_dest(self.TARGETS_IV,
                                             gtk.gdk.ACTION_DEFAULT)
        self.iconview.connect('drag_begin', self.iv_drag_begin)
        self.iconview.connect('drag_data_get', self.iv_dnd_get_data)
        self.iconview.connect('drag_data_received', self.iv_dnd_received_data)
        self.iconview.connect('drag_data_delete', self.iv_dnd_data_delete)
        self.iconview.connect('drag_motion', self.iv_dnd_motion)
        self.iconview.connect('drag_leave', self.iv_dnd_leave_end)
        self.iconview.connect('drag_end', self.iv_dnd_leave_end)
        self.iconview.connect('button_press_event', self.iv_button_press_event)
        self.iv_auto_scroll_direction = 0

        style = self.iconview.get_style().copy()
        style_sw = sw.get_style()
        for state in (gtk.STATE_NORMAL, gtk.STATE_PRELIGHT, gtk.STATE_ACTIVE):
            style.base[state] = style_sw.bg[gtk.STATE_NORMAL]
        self.iconview.set_style(style)

        if Preferences.lazyThumbnailsRendering:
            self.iconview.connect_object('expose-event', self.__on_iconview_visibility_change, self.iconview)

#        self.iconview.set_margin(0)

        # Status bar
        status_bar = self.statusbar1

        self.statusbar = gtk.HBox()

        frame = status_bar.get_children()[0]
        frame.remove(frame.get_children()[0])
        frame.add(self.statusbar)

        status_bar.show_all()
#        self.status_bar.set_has_resize_grip(True)
#        self.status_bar.push(context_id, "")

#        # Add progress bar
#        hbox = gtk.HBox()
#        self.status_bar.add(hbox)

        self.progress_bar = gtk.ProgressBar()
        self.progress_bar.set_size_request(50, 0)
        self.statusbar.pack_start(self.progress_bar, True, True, 0)
#        self.progress_bar.pulse()
        self.progress_bar.unrealize()
        self.progress_bar.hide_all()

        # Add zoom-in / zoom-out buttons
        btn_zoom_out = gtk.Button(label="-")
        self.statusbar.pack_start(btn_zoom_out, False, False, 0)
        label_zoom = gtk.Label("100%")
        self.statusbar.pack_start(label_zoom, False, False, 0)
        btn_zoom_in = gtk.Button(label="+")
        self.statusbar.pack_start(btn_zoom_in, False, False, 0)

        # Initializing variables
        self.export_directory = os.getenv('HOME')
        self.import_directory = os.getenv('HOME')
        self.nfile = 0
        self.idle = None
        self.iv_auto_scroll_timer = None
        self.pdfqueue = []

        gobject.type_register(PDF_Renderer)
        gobject.signal_new('reset_iv_width', PDF_Renderer,
                           gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ())
        gobject.signal_new('update_progress_bar', PDF_Renderer,
                           gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, [gobject.TYPE_FLOAT, gobject.TYPE_STRING])
        gobject.signal_new('update_thumbnail', PDF_Renderer,
                           gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, [gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT])
        self.rendering_thread = PDF_Renderer(self.model, self.pdfqueue,
                                             0, self.get_current_gizmo_size())
        self.rendering_thread.connect('reset_iv_width', self.reset_iv_width)
        self.rendering_thread.connect('update_progress_bar', self.update_progress_bar)
        self.rendering_thread.connect('update_thumbnail', self.update_thumbnail)
        self.rendering_thread.set_prefer_thumbnails(Preferences.preferThumbnails)
        self.rendering_thread.daemon = True
        self.rendering_thread.start()

        self.retitle()

        self.topWindow.show_all()

        self.check_backends()

        # Importing documents passed as command line arguments
        for filename in sys.argv[1:]:
            self.filename = os.path.abspath(filename)
            (self.path, self.shortname) = os.path.split(self.filename)
            (self.shortname, self.ext) = os.path.splitext(self.shortname)
            if self.ext.lower() == '.djvu':
                self.add_djvu_pages(filename)
            elif self.ext.lower() == '.pdf':
                self.add_pdf_pages(filename)

    def __getattr__(self, attr):
        obj = self.get_object(attr)
        if not obj:
            raise AttributeError('object %r has no attribute %r' % (self,attr))
        setattr(self, attr, obj)
        return obj

    def get_current_gizmo_size(self):
        try:
            return GIZMO_SIZES[Preferences.gizmoSize]
        except IndexError:
            Preferences.gizmoSize = 2
            return GIZMO_SIZES[Preferences.gizmoSize]

    def on_undo(self, window, event):
        pass

    def on_redo(self, window, event):
        pass

    def set_dirty(self, flag):
        self.is_dirty = flag
        gobject.idle_add(self.retitle)

    def retitle(self):
        title = ""
        if self.is_dirty:
            title += "*"

        if len(self.pdfqueue) == 1:
            title += self.pdfqueue[0].filename
        elif len(self.pdfqueue) == 0:
            title += "(no document)"
        else:
            title += "(several documents)"

        title += ' - PdfSnip'
        self.topWindow.set_title(title)

    def redraw_thumbnails(self):
        """Drop all existing thumbnails and start rendering thread again"""
        for row in self.model:
            item = row[2]
            item.rendered = False
            item.need_to_be_rendered = False
            item.thumbnail_width = 0

        self.rendering_thread.restart_loop = True

        self.__on_iconview_visibility_change()

        if self.rendering_thread.paused:
            self.rendering_thread.paused = False
            self.rendering_thread.evnt.set()
            self.rendering_thread.evnt.clear()

    def toggle_use_thumbnails(self, window, event):
        self.gconf_client.set_bool(KEY_THUMBNAILS, event.get_active())
        Preferences.preferThumbnails = event.get_active()
        if hasattr(self, 'rendering_thread'):
            self.rendering_thread.set_prefer_thumbnails(event.get_active())
            self.redraw_thumbnails()

    def update_progress_bar(self, object, fraction, text):
#        print "$$$$", fraction
        gtk.gdk.threads_enter()
        self.progress_bar.set_fraction(fraction)
        self.progress_bar.set_text(text)
        if fraction == 1.0:
            self.progress_bar.unrealize()
            self.progress_bar.hide_all()
        gtk.gdk.threads_leave()

    def update_thumbnail(self, object, iter, thumbnail):
        gtk.gdk.threads_enter()
        logging.debug("Updating thumbnail")
        if self.model.iter_is_valid(iter):
            obj = self.model.get_value(iter, 2)
            obj.rendered = True
            obj.thumbnail_width = thumbnail.get_width()
            self.model.set_value(iter, 2, obj)
            self.model.set_value(iter, 1, thumbnail)
        gtk.gdk.threads_leave()

    def set_zoom_in(self, window, event=None):
        """Zoom in thunbnails view."""
        logging.debug("Clicked: set_zoom_in")
        Preferences.fitPageWidth = False
        if Preferences.gizmoSize < len(GIZMO_SIZES) - 1:
            Preferences.gizmoSize += 1
            self.redraw_thumbnails()

    def set_zoom_out(self, window, event=None):
        """Zoom out thunbnails view."""
        logging.debug("Clicked: set_zoom_out")
        Preferences.fitPageWidth = False
        if Preferences.gizmoSize > 0:
            Preferences.gizmoSize -= 1
            self.redraw_thumbnails()

    def set_zoom_width(self, window, event=None):
        """
        Zoom in thunbnails view to the window width.
        @type window: CheckMenuItem
        """
        logging.debug("Clicked: set_zoom_width. " + str(window))
        checked = window.get_active()
#        Preferences.gizmoSize = self.iconview2.get_allocation().width - int(spacings)
        Preferences.fitPageWidth = checked
        self.recalculate_gizmo_size()
        self.redraw_thumbnails()

    def set_zoom_width_dual(self, window, event=None):
        """
        Zoom in thunbnails view to the window width.
        @type window: CheckMenuItem
        """
        logging.debug("Clicked: set_zoom_width_dual. " + str(window))
        checked = window.get_active()
#        Preferences.gizmoSize = self.iconview2.get_allocation().width - int(spacings)
        Preferences.fitPageWidthDual = checked
        self.recalculate_gizmo_size()
        self.redraw_thumbnails()

    def recalculate_gizmo_size(self):
        if Preferences.fitPageWidth:
            if not Preferences.fitPageWidthDual:
                spacings = self.iconview.get_item_padding() * 2 + (self.iconview.get_margin() + 1) * 2 + 2 * 1 + 2
                logging.debug("Set spacing to iconview to " + str(spacings))
                Preferences.pageWidth = self.iconview2.get_allocation().width - int(spacings)
                logging.info("Set width to " + str(self.get_current_gizmo_size()))
            else:
                spacings = self.iconview.get_item_padding() * 4 + (self.iconview.get_margin() + 1) * 2 + 2 * 2 + 4 + self.iconview.get_column_spacing()
                logging.debug("Set spacing to iconview to " + str(spacings))
                Preferences.pageWidth = int((self.iconview2.get_allocation().width - int(spacings)) / 2)
                logging.info("Set width to " + str(self.get_current_gizmo_size()))

    def __on_iconview_visibility_change(self, view=None, *args):
        logging.debug("__update_visibility")
        vrange = self.iconview.get_visible_range()
        if vrange is None:
            return
        start, end = vrange

        logging.info("Visible items: " + str(start[0]) + ":" + str(end[0]))
        if self.iconview_col_width == 0:
            logging.error("self.iconview_col_width == 0")
            # TODO: Investigate the problem
            self.iconview_col_width = 50

        # Here we drops all images that are out of sight
        if Preferences.fitPageWidth:
            thumbnail = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False,
                                       8, self.iconview_col_width, self.iconview_col_width)
            for i in range(len(self.model)):
                if i not in range(start[0], end[0] + 1):
                    item = self.model[i][2]
                    item.thumbnail_width = 0
                    if item.need_to_be_rendered:
                        item.need_to_be_rendered = False
                    if not self.model[i][1]:
                        self.model[i][1] = thumbnail

        for i in range(start[0], end[0] + 1):
            if not self.model[i][2].need_to_be_rendered:
                self.model[i][2].need_to_be_rendered = True

        if self.rendering_thread.paused:
            self.rendering_thread.paused = False
            self.rendering_thread.evnt.set()
            self.rendering_thread.evnt.clear()

    def on_window_size_request(self, window, event):
        """Main Window resize - workaround for autosetting of
           iconview cols no."""
#        col_num = 9 * window.get_size()[0] / (10 * (self.iconview_col_width + self.iconview.get_column_spacing() * 2))
#        logging.debug("Set column size: " + str(col_num))
#        col_num = (window.get_size()[0] - self.iconview.get_column_spacing() * 2) / ((self.iconview_col_width + self.iconview.get_spacing() * 2 + self.iconview.get_margin() * 2))
#        print "on_window_size_request", 9 * window.get_size()[0], (10 * (self.iconview_col_width + self.iconview.get_column_spacing() * 2)), 9 * window.get_size()[0] / (10 * (self.iconview_col_width + self.iconview.get_column_spacing() * 2))
#        print "get_spacing", self.iconview.get_spacing(), "get_row_spacing", self.iconview.get_row_spacing(), "get_column_spacing", self.iconview.get_column_spacing(), "get_margin", self.iconview.get_margin()
#        self.iconview.set_columns(col_num)
        self.recalculate_gizmo_size()
        if Preferences.fitPageWidth:
            self.redraw_thumbnails()

    def reset_iv_width(self, renderer=None):
        """Reconfigures the width of the iconview columns"""
        gobject.idle_add(self.reset_iv_width_real)

    def reset_iv_width_real(self):
        if not len(self.model):
            return
        max_w = max(row[2].thumbnail_width for row in self.model)
        logging.debug("(reset_iv_width) Before: " + str(self.iconview_col_width) + " After: " + str(max_w))
        if max_w != self.iconview_col_width:
            self.iconview_col_width = max_w
            self.celltxt.set_property('width', self.iconview_col_width)
            self.celltxt.set_property('wrap-width', self.iconview_col_width)
            self.iconview.set_item_width(self.iconview_col_width + self.iconview.get_item_padding() * 2)
            self.on_window_size_request(self.topWindow, None)

    def close_application(self, widget, event=None, data=None):
        """Termination"""
        if self.is_dirty:
            msg_dialog = gtk.MessageDialog(flags=gtk.DIALOG_MODAL,
                                              type=gtk.MESSAGE_WARNING,
               message_format="The document was changed. Are you sure you want to close app?",
                                              buttons=gtk.BUTTONS_YES_NO)
            response = msg_dialog.run()
            msg_dialog.destroy()
            if response == gtk.RESPONSE_NO:
                return True

        # save configuration
        Preferences.save()

        #gtk.gdk.threads_leave()
        self.rendering_thread.quit = True
        #gtk.gdk.threads_enter()
        if self.rendering_thread.paused:
             self.rendering_thread.evnt.set()
             self.rendering_thread.evnt.clear()
        if os.path.isdir(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)
        if gtk.main_level():
            gtk.main_quit()
        else:
            sys.exit(0)
        return False

    def add_djvu_pages(self, filename,
                            firstpage=None, lastpage=None,
                            angle=0, crop=[0.,0.,0.,0.]):
        """
        Add pages of a pdf document to the model.
        Note that firstpage and lastpage are zero based.
        """
        logging.debug("add_djvu_pages")
        res = False
        # Check if the document has already been loaded
        pdfdoc = None
        for it_pdfdoc in self.pdfqueue:
            if os.path.isfile(it_pdfdoc.filename) and \
               os.path.samefile(filename, it_pdfdoc.filename) and \
               os.path.getmtime(filename) is it_pdfdoc.mtime:
                pdfdoc = it_pdfdoc
                break

        if not pdfdoc:
            pdfdoc = DJVU_Doc(filename, self.nfile, self.tmp_dir)
            self.import_directory = os.path.split(filename)[0]
            self.export_directory = self.import_directory
            if pdfdoc.nfile != 0 and pdfdoc != []:
                self.nfile = pdfdoc.nfile
                self.pdfqueue.append(pdfdoc)
            else:
                return res

        n_start = 0
        n_end = pdfdoc.number_of_pages
        if firstpage:
           n_start = min(n_end, max(1, firstpage + 1))
        if lastpage:
           n_end = max(n_start, min(n_end, lastpage + 1))

        for page_number in range(n_start, n_end):
#            if only one document:
            descriptor = ''.join([_('page'), ' ', str(page_number + 1)])
            tooltip = ''.join([pdfdoc.shortname, '\n', _('page'), ' ', str(page_number + 1)])
            width = self.iconview_col_width
            thumbnail = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False,
                                       8, width, width)
            item = ListObject()
            item.text = descriptor
            item.doc_number = pdfdoc.nfile
            item.page_number = page_number
            item.thumbnail_width = 0
            item.doc_filename = pdfdoc.filename
            item.rendered = False
            item.rotation_angle = angle
            item.crop = crop
            item.need_to_be_rendered = not Preferences.lazyThumbnailsRendering

            self.model.append((descriptor,
                               thumbnail,
                               item,
                               tooltip))
            res = True

        gobject.idle_add(self.retitle)
        if res and self.rendering_thread.paused:
            self.rendering_thread.paused = False
            self.rendering_thread.evnt.set()
            self.rendering_thread.evnt.clear()
        return res

    def add_pdf_pages(self, filename,
                            firstpage=None, lastpage=None,
                            angle=0, crop=[0.,0.,0.,0.]):
        """
        Add pages of a pdf document to the model.
        Note that firstpage and lastpage are zero based.
        """
        res = False
        # Check if the document has already been loaded
        pdfdoc = None
        for it_pdfdoc in self.pdfqueue:
            if os.path.isfile(it_pdfdoc.filename) and \
               os.path.samefile(filename, it_pdfdoc.filename) and \
               os.path.getmtime(filename) is it_pdfdoc.mtime:
                pdfdoc = it_pdfdoc
                break

        if not pdfdoc:
            pdfdoc = PDF_Doc(filename, self.nfile, self.tmp_dir)
            self.import_directory = os.path.split(filename)[0]
            self.export_directory = self.import_directory
            if pdfdoc.nfile != 0 and pdfdoc != []:
                self.nfile = pdfdoc.nfile
                self.pdfqueue.append(pdfdoc)
            else:
                return res

        n_start = 0
        n_end = pdfdoc.number_of_pages
        if firstpage:
           n_start = min(n_end, max(1, firstpage + 1))
        if lastpage:
           n_end = max(n_start, min(n_end, lastpage + 1))

        for page_number in range(n_start, n_end):
#            if only one document:
            descriptor = ''.join([_('page'), ' ', str(page_number + 1)])
            tooltip = ''.join([pdfdoc.shortname, '\n', _('page'), ' ', str(page_number + 1)])
            pix_w, pix_h = pdfdoc.document.get_page(page_number).get_size()
            pix_w, pix_h, pix_scale = PixbufUtils.bbox_upscale((pix_w, pix_h), self.iconview_col_width)
            
            thumbnail = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False,
                                       8, pix_w, pix_h)
            item = ListObject()
            item.text = descriptor
            item.doc_number = pdfdoc.nfile
            item.page_number = page_number
            item.thumbnail_width = pix_w
            item.thumbnail_size = (pix_w, pix_h)
            item.doc_filename = pdfdoc.filename
            item.rendered = False
            item.rotation_angle = angle
            item.crop = crop
            item.need_to_be_rendered = not Preferences.lazyThumbnailsRendering

            self.model.append((descriptor,
                               thumbnail,
                               item,
                               tooltip))
            res = True

        gobject.idle_add(self.retitle)
        if res and self.rendering_thread.paused:
            self.rendering_thread.paused = False
            self.rendering_thread.evnt.set()
            self.rendering_thread.evnt.clear()
        return res

    def save_file(self, widget=None, data=None):
        if len(self.pdfqueue) == 1:
            print "len(self.pdfqueue)", len(self.pdfqueue)
            if not Preferences.usePdftk:
                self.export_to_file_using_pypdf(self.pdfqueue[0].filename)
            else:
                self.export_to_file_using_pdftk(self.pdfqueue[0].filename)
            self.set_dirty(False)
        else:
            error_msg_win = gtk.MessageDialog(flags=gtk.DIALOG_MODAL,
                                              type=gtk.MESSAGE_ERROR,
               message_format=_("Save isn't available while you have multiple \
               documents opened. Use `Save as...` instead."),
                                              buttons=gtk.BUTTONS_OK)
            response = error_msg_win.run()
            if response == gtk.RESPONSE_OK:
                error_msg_win.destroy()

    def choose_export_pdf_name(self, widget=None, data=None):
        """Handles choosing a name for exporting """
        chooser = gtk.FileChooserDialog(title=_('Export ...'),
                                        action=gtk.FILE_CHOOSER_ACTION_SAVE,
                                        buttons=(gtk.STOCK_CANCEL,
                                                 gtk.RESPONSE_CANCEL,
                                                 gtk.STOCK_SAVE,
                                                 gtk.RESPONSE_OK))
        chooser.set_do_overwrite_confirmation(True)
        chooser.set_current_folder(self.export_directory)
        filter_pdf = gtk.FileFilter()
        filter_pdf.set_name(_('PDF files'))
        filter_pdf.add_pattern('*.pdf')
        chooser.add_filter(filter_pdf)

        filter_all = gtk.FileFilter()
        filter_all.set_name(_('All files'))
        filter_all.add_pattern('*')
        chooser.add_filter(filter_all)

        while True:
            response = chooser.run()
            if response == gtk.RESPONSE_OK:
                file_out = chooser.get_filename()
                (path, shortname) = os.path.split(file_out)
                (shortname, ext) = os.path.splitext(shortname)
                if ext.lower() != '.pdf':
                    file_out += '.pdf'
                try:
                    if not Preferences.usePdftk:
                        self.export_to_file_using_pypdf(file_out)
                    else:
                        self.export_to_file_using_pdftk(file_out)
                    self.export_directory = path
                except IOError:
                    error_msg_win = gtk.MessageDialog(flags=gtk.DIALOG_MODAL,
                                                      type=gtk.MESSAGE_ERROR,
                       message_format=_("Error writing file: %s") % file_out,
                                                      buttons=gtk.BUTTONS_OK)
                    response = error_msg_win.run()
                    if response == gtk.RESPONSE_OK:
                        error_msg_win.destroy()
                    continue
            break
        chooser.destroy()

    def check_backends(self):
        """Check backends"""
        msg = None
        go_to_preferences = None
        if not found_pypdf and not found_pdftk:
            msg = "Neither pypdf or pdftk installed. You won't be able to save your changes."
        elif not found_pypdf and not Preferences.usePdftk:
            msg = "pypdf not installed. Please review your backend settings...\nAfter clicking preferences window will be shown."
            go_to_preferences = True
        elif not found_pdftk and Preferences.usePdftk:
            msg = "pdftk not installed. Please review your backend settings...\nAfter clicking preferences window will be shown."
            go_to_preferences = True
        if msg:
            msg_dialog = gtk.MessageDialog(None,
                gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_WARNING,
                gtk.BUTTONS_CLOSE,
                msg)
            msg_dialog.run()
            msg_dialog.destroy()
            logging.error(msg)
        if go_to_preferences:
            self.preferences_dialog()
        return msg is None

    def export_to_file_using_pypdf(self, file_out):
        """Export to file"""
        if not self.check_backends():
            return

        pdf_output = PdfFileWriter()
        pdf_input = []
        for pdfdoc in self.pdfqueue:
            print "&&&& File: ", pdfdoc.copyname
            pdfdoc_inp = PdfFileReader(file(pdfdoc.copyname, 'rb'))
            if pdfdoc_inp.getIsEncrypted():
                if (pdfdoc_inp.decrypt('')!=1): # Workaround for lp:#355479
                    print(_('File %s is encrypted.') % pdfdoc.filename)
                    print(_('Support for such files has not been implemented yet.'))
                    print(_('File export failed.'))
                    return
                #FIXME
                #else
                #   ask for password and decrypt file
            pdf_input.append(pdfdoc_inp)

        for row in self.model:
            # add pages from input to output document
            obj = row[2]
            current_page = pdf_input[obj.doc_number-1].getPage(obj.page_number)
            angle = obj.rotation_angle
            angle0 = current_page.get("/Rotate",0)
            if angle is not 0:
                current_page.rotateClockwise(angle)
            if obj.crop != [0.,0.,0.,0.]:
                rotate_times = (((angle + angle0) % 360 + 45) / 90) % 4
                crop_init = obj.crop
                if rotate_times is not 0:
                    perm = [0,2,1,3]
                    for it in range(rotate_times):
                        perm.append(perm.pop(0))
                    perm.insert(1,perm.pop(2))
                    obj.crop = [crop_init[perm[side]] for side in range(4)]
                #(x1, y1) = current_page.cropBox.lowerLeft
                #(x2, y2) = current_page.cropBox.upperRight
                (x1, y1) = [float(xy) for xy in current_page.mediaBox.lowerLeft]
                (x2, y2) = [float(xy) for xy in current_page.mediaBox.upperRight]
                x1_new = int(x1 + (x2-x1) * obj.crop[0])
                x2_new = int(x2 - (x2-x1) * obj.crop[1])
                y1_new = int(y1 + (y2-y1) * obj.crop[3])
                y2_new = int(y2 - (y2-y1) * obj.crop[2])
                #current_page.cropBox.lowerLeft = (x1_new, y1_new)
                #current_page.cropBox.upperRight = (x2_new, y2_new)
                current_page.mediaBox.lowerLeft = (x1_new, y1_new)
                current_page.mediaBox.upperRight = (x2_new, y2_new)

            pdf_output.addPage(current_page)

        # finally, write "output" to document-output.pdf
        print(_('exporting to:'), file_out)
        pdf_output.write(file(file_out, 'wb'))

    def export_to_file_using_pdftk(self, file_out):
        """Export to file using pdftk"""
        if not self.check_backends():
            return

        if len(self.pdfqueue) > 1:
            print("Currently saving don't work more than one file via pdftk. This will come next version. Keep tuned!")
        else:
            filename = self.pdfqueue[0].copyname
            pages = [str(row[2].page_number + 1) for row in self.model]

            args = ["pdftk", filename]
            args.append("cat")
            args += pages
            args.append("output")
            # finally, write "output" to document-output.pdf
            args.append(file_out)

            print args

            subprocess.call(args)

    def on_action_add_doc_activate(self, widget, data=None):
        """Import doc"""

        chooser = gtk.FileChooserDialog(title=_('Import...'),
                                        action=gtk.FILE_CHOOSER_ACTION_OPEN,
                                        buttons=(gtk.STOCK_CANCEL,
                                                  gtk.RESPONSE_CANCEL,
                                                  gtk.STOCK_OPEN,
                                                  gtk.RESPONSE_OK))
        chooser.set_current_folder(self.import_directory)
        chooser.set_select_multiple(True)

        filter_all = gtk.FileFilter()
        filter_all.set_name(_('All files'))
        filter_all.add_pattern('*')
        chooser.add_filter(filter_all)

        filter_pdf = gtk.FileFilter()
        filter_pdf.set_name(_('PDF files'))
        filter_pdf.add_pattern('*.pdf')
        chooser.add_filter(filter_pdf)

        response = chooser.run()
        if response == gtk.RESPONSE_OK:
            for filename in chooser.get_filenames():
                if os.path.isfile(filename):
                    # FIXME
                    ext = os.path.splitext(filename)[1].lower()
                    if ext == '.pdf':
                        self.add_pdf_pages(filename)
                    elif ext == '.djvu':
                        self.add_djvu_pages(filename)
                    elif ext == '.png' or ext == '.jpg' or ext == '.tiff':
                        print(_('Image file not supported yet!'))
                    else:
                        print(_('File type not supported!'))
                else:
                    print(_('File %s does not exist') % filename)
        elif response == gtk.RESPONSE_CANCEL:
            print(_('Closed, no files selected'))
        chooser.destroy()
        gobject.idle_add(self.retitle)

    def delete_selected_page(self, button=None, data=None):
        """Removes the selected Element in the IconView"""
        model = self.iconview.get_model()
        selection = self.iconview.get_selected_items()

        if selection:
            self.set_dirty(True)
            iters = [model.get_iter(path) for path in selection]
            for iter in iters:
                model.remove(iter)

            iter_next_selected = model.get_path(iters[-1])

            self.iconview.set_cursor(iter_next_selected)
            self.iconview.select_path(iter_next_selected)
            if not self.iconview.path_is_selected(iter_next_selected):
                if len(model) > 0:	# select the last row
                    row = model[-1]
                    path = row.path
                    self.iconview.select_path(path)
            self.iconview.grab_focus()

            if self.rendering_thread.paused:
                self.rendering_thread.paused = False
                self.rendering_thread.evnt.set()
                self.rendering_thread.evnt.clear()
            
    def load_all_thumbnails(self, button=None, data=None):
        """Load all thumbs"""
        for row in self.model:
            item = row[2]
            item.need_to_be_rendered = True

        self.rendering_thread.restart_loop = True

        if self.rendering_thread.paused:
            self.rendering_thread.paused = False
            self.rendering_thread.evnt.set()
            self.rendering_thread.evnt.clear()

    def iv_drag_begin(self, iconview, context):
        """Sets custom icon on drag begin for multiple items selected"""
        if len(iconview.get_selected_items()) > 1:
            iconview.stop_emission('drag_begin')
            context.set_icon_stock(gtk.STOCK_DND_MULTIPLE, 0, 0)

    def iv_dnd_get_data(self, iconview, context,
                        selection_data, target_id, etime):
        """Handles requests for data by drag and drop in iconview"""
        model = iconview.get_model()
        selection = self.iconview.get_selected_items()
        selection.sort(key=lambda x: x[0])
        data = []
        for path in selection:
            if selection_data.target == 'MODEL_ROW_INTERN':
                data.append(str(path[0]))
            elif selection_data.target == 'MODEL_ROW_EXTERN':
                iter = model.get_iter(path)
                obj = model.get(iter, 2)
                pdfdoc = self.pdfqueue[obj.doc_number - 1]
                data.append('\n'.join([pdfdoc.filename,
                                       str(obj.page_number + 1),
                                       str(obj.angle)] +
                                       [str(side) for side in obj.crop]))
        if data:
            data = '\n;\n'.join(data)
            selection_data.set(selection_data.target, 8, data)

    def iv_dnd_received_data(self, iconview, context, x, y,
                             selection_data, target_id, etime):
        """Handles received data by drag and drop in iconview"""
        model = iconview.get_model()
        data = selection_data.data
        if data:
            data = data.split('\n;\n')
            drop_info = iconview.get_dest_item_at_pos(x, y)
            iter_to = None
            if drop_info:
                path, position = drop_info
                ref_to = gtk.TreeRowReference(model,path)
            else:
                position = gtk.ICON_VIEW_DROP_RIGHT
                if len(model) > 0:  #find the iterator of the last row
                    row = model[-1]
                    path = row.path
                    ref_to = gtk.TreeRowReference(model,path)
            if ref_to:
                before = (position == gtk.ICON_VIEW_DROP_LEFT
                          or position == gtk.ICON_VIEW_DROP_ABOVE)
                #if target_id == self.MODEL_ROW_INTERN:
                if selection_data.target == 'MODEL_ROW_INTERN':
                    if before:
                        data.sort(key=int)
                    else:
                        data.sort(key=int,reverse=True)
                    ref_from_list = [gtk.TreeRowReference(model,path)
                                     for path in data]
                    for ref_from in ref_from_list:
                        path = ref_to.get_path()
                        iter_to = model.get_iter(path)
                        path = ref_from.get_path()
                        iter_from = model.get_iter(path)
                        row = model[iter_from]
                        if before:
                            model.insert_before(iter_to, row)
                        else:
                            model.insert_after(iter_to, row)
                    if context.action == gtk.gdk.ACTION_MOVE:
                        for ref_from in ref_from_list:
                            path = ref_from.get_path()
                            iter_from = model.get_iter(path)
                            model.remove(iter_from)

                #elif target_id == self.MODEL_ROW_EXTERN:
                elif selection_data.target == 'MODEL_ROW_EXTERN':
                    if not before:
                        data.reverse()
                    while data:
                        tmp = data.pop(0).split('\n')
                        filename = tmp[0]
                        page_number, angle = [int(k) for k in tmp[1:3]]
                        crop = [float(side) for side in tmp[3:7]]
                        if self.add_pdf_pages(filename, page_number, page_number,
                                                        angle, crop):
                            if len(model) > 0:
                                path = ref_to.get_path()
                                iter_to = model.get_iter(path)
                                row = model[-1] #the last row
                                path = row.path
                                iter_from = model.get_iter(path)
                                if before:
                                    model.move_before(iter_from, iter_to)
                                else:
                                    model.move_after(iter_from, iter_to)
                                if context.action == gtk.gdk.ACTION_MOVE:
                                    context.finish(True, True, etime)

    def iv_dnd_data_delete(self, widget, context):
        """Deletes dnd items after a successful move operation"""
        model = self.iconview.get_model()
        selection = self.iconview.get_selected_items()
        ref_del_list = [gtk.TreeRowReference(model,path) for path in selection]
        for ref_del in ref_del_list:
            path = ref_del.get_path()
            iter = model.get_iter(path)
            model.remove(iter)

    def iv_dnd_motion(self, iconview, context, x, y, etime):
        """Handles the drag-motion signal in order to auto-scroll the view"""
        autoscroll_area = 40
        sw_vadj = self.scrolledwindow1.get_vadjustment()
        sw_height = self.scrolledwindow1.get_allocation().height
        if y -sw_vadj.get_value() < autoscroll_area:
            if not self.iv_auto_scroll_timer:
                self.iv_auto_scroll_direction = gtk.DIR_UP
                self.iv_auto_scroll_timer = gobject.timeout_add(150,
                                                                self.iv_auto_scroll)
        elif y -sw_vadj.get_value() > sw_height - autoscroll_area:
            if not self.iv_auto_scroll_timer:
                self.iv_auto_scroll_direction = gtk.DIR_DOWN
                self.iv_auto_scroll_timer = gobject.timeout_add(150,
                                                                self.iv_auto_scroll)
        elif self.iv_auto_scroll_timer:
            gobject.source_remove(self.iv_auto_scroll_timer)
            self.iv_auto_scroll_timer = None

    def iv_dnd_leave_end(self, widget, context, ignored=None):
        """Ends the auto-scroll during DND"""
        if self.iv_auto_scroll_timer:
            gobject.source_remove(self.iv_auto_scroll_timer)
            self.iv_auto_scroll_timer = None

    def iv_auto_scroll(self):
        """Timeout routine for auto-scroll"""
        sw_vadj = self.scrolledwindow1.get_vadjustment()
        sw_vpos = sw_vadj.get_value()
        if self.iv_auto_scroll_direction == gtk.DIR_UP:
            sw_vpos -= sw_vadj.step_increment
            sw_vadj.set_value(max(sw_vpos, sw_vadj.lower))
        elif self.iv_auto_scroll_direction == gtk.DIR_DOWN:
            sw_vpos += sw_vadj.step_increment
            sw_vadj.set_value(min(sw_vpos, sw_vadj.upper - sw_vadj.page_size))
        return True  #call me again

    def iv_button_press_event(self, iconview, event):
        """Manages mouse clicks on the iconview"""
        if event.button == 3:
            x = int(event.x)
            y = int(event.y)
            time = event.time
            path = iconview.get_path_at_pos(x, y)
            selection = iconview.get_selected_items()
            if path:
                if path not in selection:
                    iconview.unselect_all()
                iconview.select_path(path)
                iconview.grab_focus()
                self.menu2.popup(None, None, None, event.button, time)  # Glade injection
            return 1

    def sw_dnd_received_data(self, scrolledwindow, context, x, y,
                             selection_data, target_id, etime):
        """Handles received data by drag and drop in scrolledwindow"""
        data = selection_data.data
        if target_id == self.MODEL_ROW_EXTERN:
            self.model
            if data:
                data = data.split('\n;\n')
            while data:
                tmp = data.pop(0).split('\n')
                filename = tmp[0]
                page_number, angle = [int(k) for k in tmp[1:3]]
                crop = [float(side) for side in tmp[3:7]]
                if self.add_pdf_pages(filename, page_number, page_number, angle, crop):
                    if context.action == gtk.gdk.ACTION_MOVE:
                        context.finish(True, True, etime)
        elif target_id == self.TEXT_URI_LIST:
            uri = data.strip()
            uri_splitted = uri.split() # we may have more than one file dropped
            for uri in uri_splitted:
                filename = self.get_file_path_from_dnd_dropped_uri(uri)
                if os.path.isfile(filename): # is it file?
                    self.add_pdf_pages(filename)

    def sw_button_press_event(self, scrolledwindow, event):
        """Unselects all items in iconview on mouse click in scrolledwindow"""
        if event.button == 1:
            self.iconview.unselect_all()

    def get_file_path_from_dnd_dropped_uri(self, uri):
        """Extracts the path from an uri"""
        path = urllib.url2pathname(uri) # escape special chars
        path = path.strip('\r\n\x00')   # remove \r\n and NULL

        # get the path to file
        if path.startswith('file:\\\\\\'): # windows
            path = path[8:]  # 8 is len('file:///')
        elif path.startswith('file://'):   # nautilus, rox
            path = path[7:]  # 7 is len('file://')
        elif path.startswith('file:'):     # xffm
            path = path[5:]  # 5 is len('file:')
        return path

    def rotate_page_right(self, widget, data=None):
        self.rotate_page(90)

    def rotate_page_left(self, widget, data=None):
        self.rotate_page(-90)

    def rotate_page(self, angle):
        """Rotates the selected page in the IconView"""
        model = self.iconview.get_model()
        selection = self.iconview.get_selected_items()
        if len(selection) > 0:
            self.set_dirty(True)
        for path in selection:
            iter = model.get_iter(path)
            obj = model.get_value(iter, 2)

            rotate_times = (((-angle) % 360 + 45) / 90) % 4
            crop = [0.,0.,0.,0.]
            if rotate_times is not 0:
                perm = [0,2,1,3]
                for it in range(rotate_times):
                    perm.append(perm.pop(0))
                perm.insert(1, perm.pop(2))
                crop = obj.crop
#                for side in range(4):
#                    model.set_value(iter, 8 + side, crop[side])

            obj.rotation_angle = obj.rotation_angle + angle
            obj.rendered = False

        if self.rendering_thread.paused:
            self.rendering_thread.paused = False
            self.rendering_thread.evnt.set()
            self.rendering_thread.evnt.clear()


    def file_info(self, widget, event=None):
        """Shows info about opened file(s)"""
        info = "<b>Filename: </b>"
        if len(self.pdfqueue) == 1:
            info += self.pdfqueue[0].filename

        error_msg_win = gtk.MessageDialog(flags=gtk.DIALOG_MODAL,
                                          type=gtk.MESSAGE_INFO,
                                          message_format=info,
                                          buttons=gtk.BUTTONS_OK)
        error_msg_win.set_markup(info)
        response = error_msg_win.run()
        if response == gtk.RESPONSE_OK:
            error_msg_win.destroy()

    def crop_page_dialog(self, widget, data=None):
        """Opens a dialog box to define margins for page cropping"""
        model = self.iconview.get_model()
        selection = self.iconview.get_selected_items()

        crop = [0.,0.,0.,0.]
        if selection:
            path = selection[0]
            iter = model.get_iter(path)
            listObject = model.get_value(iter, 2)
            crop = listObject.crop
            image = model.get_value(iter, 1)

#        dialog = gtk.Dialog(title=(_('Crop Selected Page(s)')),
#                            parent=self.topWindow,
#                            flags=gtk.DIALOG_MODAL,
#                            buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
#                                     gtk.STOCK_OK, gtk.RESPONSE_OK))
#        dialog.set_size_request(340, 250)
#        dialog.set_default_response(gtk.RESPONSE_OK)
#
#        frame = gtk.Frame(_('Crop Margins'))
#        dialog.vbox.pack_start(frame, False, False, 20)
#
#        vbox = gtk.VBox(False, 0)
#        frame.add(vbox)
#
#        spin_list = []
#        units = 2 * [_('% of width')] + 2 * [_('% of height')]
#        for margin in (_('Left'),_('Right'),_('Top'),_('Bottom')):
#            hbox = gtk.HBox(True, 0)
#            vbox.pack_start(hbox, False, False, 5)
#
#            label = gtk.Label(margin)
#            label.set_alignment(0, 0.0)
#            hbox.pack_start(label, True, True, 20)
#
#            adj = gtk.Adjustment(100. * crop.pop(0), 0.0, 100.0, 1.0, 5.0, 0.0)
#            spinner = gtk.SpinButton(adj, 0, 1)
#            spinner.set_activates_default(True)
#            spin_list.append(spinner)
#            hbox.pack_start(spinner, False, False, 30)
#
#            label = gtk.Label(units.pop(0))
#            label.set_alignment(0, 0.0)
#            hbox.pack_start(label, True, True, 0)
#
#        dialog.show_all()

        dialog = self.dialogPage

        self.spinbuttonLeft.set_adjustment(gtk.Adjustment(100. * crop[0], 0.0, 100.0, 1.0, 5.0, 0.0))
        self.spinbuttonRight.set_adjustment(gtk.Adjustment(100. * crop[1], 0.0, 100.0, 1.0, 5.0, 0.0))
        self.spinbuttonTop.set_adjustment(gtk.Adjustment(100. * crop[2], 0.0, 100.0, 1.0, 5.0, 0.0))
        self.spinbuttonBottom.set_adjustment(gtk.Adjustment(100. * crop[3], 0.0, 100.0, 1.0, 5.0, 0.0))

        self.image2.set_from_pixbuf(image)

        dialog.show_all()
        result = dialog.run()

        if result == gtk.RESPONSE_OK:
            crop[0] = self.spinbuttonLeft.get_value()/100
            crop[1] = self.spinbuttonRight.get_value()/100
            crop[2] = self.spinbuttonTop.get_value()/100
            crop[3] = self.spinbuttonBottom.get_value()/100
            for path in selection:
                iter = model.get_iter(path)
                listObject = model.get_value(iter, 2)
                listObject.crop = crop
                listObject.rendered = False
            if self.rendering_thread.paused:
                self.rendering_thread.paused = False
                self.rendering_thread.evnt.set()
                self.rendering_thread.evnt.clear()
        elif result == gtk.RESPONSE_CANCEL:
            print(_('Dialog closed'))
        dialog.hide()

    def preferences_dialog(self, widget=None, data=None):
        """Opens a preferences dialog box"""
        dialog = PreferencesWindow()
        dialog.run()
        dialog.destroy()

    def about_dialog(self, widget, data=None):
        about_dialog = gtk.AboutDialog()
        try:
            about_dialog.set_transient_for(self.topWindow)
            about_dialog.set_modal(True)
        except Exception, e:
            logging.exception(e)
        # FIXME
        about_dialog.set_name('PdfSnip')
        about_dialog.set_version(VERSION)
        about_dialog.set_comments(_(
            'PdfSnip is an GTK+ based utility for splitting, rearrangement ' \
            'and modification of PDF documents.'))
        about_dialog.set_authors(['Volodymyr Buell','Konstantinos Poulios',])
        about_dialog.set_artists(['Marina Popovichenko'])
        about_dialog.set_website('http://code.google.com/p/pdfsnip/')
        if self.icon:
            about_dialog.set_logo(self.icon)
        else:
            about_dialog.set_logo_icon_name('pdfsnip')
        about_dialog.connect('response', lambda w, a: about_dialog.destroy())
        about_dialog.connect('delete_event', lambda w, a: about_dialog.destroy())
        about_dialog.show_all()

    def icon_view_resized(self):
        print "."

class PDF_Doc:
    """Class handling pdf documents"""

    def __init__(self, filename, nfile, tmp_dir):

        self.filename = os.path.abspath(filename)
        (self.path, self.shortname) = os.path.split(self.filename)
        (self.shortname, self.ext) = os.path.splitext(self.shortname)
        if self.ext.lower() == '.pdf':
            self.nfile = nfile + 1
            self.mtime = os.path.getmtime(filename)
            self.copyname = os.path.join(tmp_dir, '%02d_' % self.nfile +
                                                  self.shortname + '.pdf')
            shutil.copy(self.filename, self.copyname)
            self.document = poppler.document_new_from_file ("file://" + self.copyname, None)
            self.number_of_pages = self.document.get_n_pages()
        else:
            self.nfile = 0


class DJVU_Doc:
    """Class handling djvu documents"""

    def __init__(self, filename, nfile, tmp_dir):

        print "DJVU_Doc.__init__"
        self.djvu_context = djvu.decode.Context()

        self.filename = os.path.abspath(filename)
        (self.path, self.shortname) = os.path.split(self.filename)
        (self.shortname, self.ext) = os.path.splitext(self.shortname)
        if self.ext.lower() == '.djvu':
            self.nfile = nfile + 1
            self.mtime = os.path.getmtime(filename)
            self.copyname = os.path.join(tmp_dir, '%02d_' % self.nfile +
                                                  self.shortname + '.pdf')
            shutil.copy(self.filename, self.copyname)
            self.document = self.djvu_context.new_document(djvu.decode.FileURI(self.copyname))
#            self.document = poppler.document_new_from_file ("file://" + self.copyname, None)
            self.document.decoding_job.wait()
            self.number_of_pages = len(self.document.pages)
        else:
            self.nfile = 0


class PDF_Renderer(threading.Thread, gobject.GObject):

    def __init__(self, model, pdfqueue, scale=1., width=100):
        threading.Thread.__init__(self)
        gobject.GObject.__init__(self)
        self.model = model
        self.scale = scale
        self.pdfqueue = pdfqueue
        self.quit = False
        self.evnt = threading.Event()
        self.paused = False
        self.antialiazing_factor = 4
        self.prefer_thumbnails = True
        self.restart_loop = False

    def set_prefer_thumbnails(self, flag):
        self.prefer_thumbnails = flag

    def run(self):
        while not self.quit:
            iter = self.model.get_iter_first()
            while iter is not None and self.model.iter_is_valid(iter):
                if self.quit:
                    break
                if self.restart_loop:
                    self.restart_loop = False
                    # Rewind to the first item
                    iter = self.model.get_iter_first()
                obj = self.model.get_value(iter, 2)
                is_thumbnails_changed = self.process_item(iter, obj)
                if is_thumbnails_changed:
                    self.emit('reset_iv_width')
                iter = self.model.iter_next(iter)

            self.paused = True
#            if self.model.get_iter_first(): #just checking if model isn't empty
#                self.emit('reset_iv_width') # TODO: Remove that
#                gobject.idle_add(self.reset_iv_width)
            self.evnt.wait()

        logging.info("The rendering thread has been stopped.")

    def process_item(self, iter, obj):
        """
        @type obj: ListObject
        """
        if not obj.rendered and obj.need_to_be_rendered:
#                    gtk.gdk.threads_enter() # Overusing of threads_enter for models
            try:
                pdfdoc = self.pdfqueue[obj.doc_number - 1]
                if isinstance(pdfdoc, PDF_Doc):
                    thumbnail = self.load_pdf_thumbnail(pdfdoc, obj.page_number, obj.rotation_angle, obj.crop)
                elif isinstance(pdfdoc, DJVU_Doc):
                    thumbnail = self.load_djvu_thumbnail(pdfdoc, obj.page_number, obj.rotation_angle, obj.crop)

                self.emit('update_thumbnail', iter, thumbnail)
            except Exception, e:
                print e
            finally:
                pass
#                        gtk.gdk.threads_enter()
#                print "Rendering thumbnails... [%s/%s]" % (idx+1, len(self.model))
#                self.emit('update_progress_bar', float(idx+1) / len(self.model),
#                    "Rendering thumbnails... [%s/%s]" % (idx+1, len(self.model)))
                return True
#                        gtk.gdk.threads_leave()
        else:
            return False

    def scale_pixbuf(self, pixbuf, gizmo_size):
        pix_w = pixbuf.get_width()
        pix_h = pixbuf.get_height()
        # Scale pixbuf
        pix_w, pix_h, pix_scale = PixbufUtils.bbox_upscale((pix_w, pix_h), gizmo_size)
        thumbnail_small = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False,
                               8, pix_w , pix_h)
        pixbuf.scale(thumbnail_small, 0, 0, pix_w , pix_h, 0, 0,
                        pix_scale,
                        pix_scale,
                        gtk.gdk.INTERP_BILINEAR)
        return thumbnail_small

    def render_pdf_page(self, page, gizmo_size, prefer_thumbs=True):
        """Create pixbuf from page"""
        got_pixbuf = False
        if prefer_thumbs:
            thumbnail = page.get_thumbnail_pixbuf()
            if thumbnail:
                got_pixbuf = True
                print "Got thumbnail!!!!", thumbnail.get_width(), thumbnail.get_height()
                thumbnail = self.scale_pixbuf(thumbnail, GIZMO_SIZES[Preferences.gizmoSize])
        if not got_pixbuf:
            # Render page
            pix_w, pix_h = page.get_size()
            if self.scale == 0:
                pix_w, pix_h, pix_scale = PixbufUtils.bbox_upscale((pix_w, pix_h), GIZMO_SIZES[Preferences.gizmoSize])
            else:
                pix_scale = self.scale
                pix_w = int(pix_w * self.scale)
                pix_h = int(pix_h * self.scale)

            antialiasing = Preferences.useAntialiazing

            if antialiasing:
                pix_w = pix_w*self.antialiazing_factor
                pix_h = pix_h*self.antialiazing_factor
                pix_scale = pix_scale*self.antialiazing_factor

            thumbnail = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False,
                                       8, pix_w , pix_h)

#            print "render_to_pixbuf", pix_w, pix_h, pix_scale
            page.render_to_pixbuf(0,0,pix_w,pix_h, pix_scale, 0, thumbnail)

            if antialiasing:
                thumbnail = self.scale_pixbuf(thumbnail, GIZMO_SIZES[Preferences.gizmoSize])
        return thumbnail


    def render_djvu_page(self, page, gizmo_size, prefer_thumbs=True):
        """Create pixbuf from page"""
        import numpy

        assert type(page) is djvu.decode.Page

        # Render page
        page_job = page.decode(wait=True)
        pix_w, pix_h = page_job.size
#        pix_w, pix_h = page.get_size()
        rect = (0, 0, pix_w, pix_h)

#        pb = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, has_alpha=1, bits_per_sample=8, width=pix_h, height=pix_w)
#        try:
#            pa = pb.get_pixels_array()
#        except AttributeError, e:
#            print e
#            pa = pb.pixel_array

        mode = djvu.decode.RENDER_FOREGROUND
        djvu_pixel_format = djvu.decode.PixelFormatRgbMask(0xff0000, 0xff00, 0xff, bpp=32)

        try:
#            bytes_per_line = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_ARGB32, pix_w)
            bytes_per_line = pix_w * 4
            color_buffer = numpy.zeros((pix_h, bytes_per_line), dtype=numpy.uint32)
            print "1", mode, rect, rect, djvu_pixel_format, bytes_per_line, len(color_buffer)
            color_buffer = page_job.render(mode, rect, rect, djvu_pixel_format, row_alignment=bytes_per_line) # buffer=color_buffer
            print "2", type(color_buffer), len(color_buffer)
    #        mask_buffer = numpy.zeros((pix_h, bytes_per_line), dtype=numpy.uint32)
    #        if mode == djvu.decode.RENDER_FOREGROUND:
    #            mask_buffer = page_job.render(djvu.decode.RENDER_MASK_ONLY, rect, rect, djvu_pixel_format, row_alignment=bytes_per_line) # , buffer=mask_buffer
    #            mask_buffer <<= 24
    #            color_buffer |= mask_buffer
    #        color_buffer ^= 0xff000000
    #        surface = cairo.ImageSurface.create_for_data(color_buffer, cairo.FORMAT_ARGB32, pix_w, pix_h)
            # remove alpha
#            out = [object for index, object in enumerate(color_buffer) if index % 4 != 3]
#            print "Size without alpha:", len(out)
            thumbnail = gtk.gdk.pixbuf_new_from_data(color_buffer, gtk.gdk.COLORSPACE_RGB, False, 8, pix_w, pix_h, bytes_per_line)

            # Resize
            thumbnail = self.scale_pixbuf(thumbnail, GIZMO_SIZES[Preferences.gizmoSize])

            print "3"
            return thumbnail
        except Exception, e:
            logging.exception(e)

    def load_pdf_thumbnail(self, pdfdoc, page_number, rotation=0, crop=[0.,0.,0.,0.]):
        """Create pdf pixbuf"""
        page = pdfdoc.document.get_page(page_number)
        try:
            thumbnail = self.render_pdf_page(page, GIZMO_SIZES[Preferences.gizmoSize], prefer_thumbs=self.prefer_thumbnails)

            rotation = (-rotation) % 360
            rotation = ((rotation + 45) / 90) * 90
            thumbnail = thumbnail.rotate_simple(rotation)
            pix_w = thumbnail.get_width()
            pix_h = thumbnail.get_height()
            if crop != [0.,0.,0.,0.]:
                src_x = int(crop[0] * pix_w)
                src_y = int(crop[2] * pix_h)
                width = int((1. - crop[0] - crop[1]) * pix_w)
                height = int((1. - crop[2] - crop[3]) * pix_h)
                new_thumbnail = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False,
                                               8, width, height)
                thumbnail.copy_area(src_x, src_y, width, height,
                                    new_thumbnail, 0, 0)
                thumbnail = new_thumbnail
                pix_w = thumbnail.get_width()
                pix_h = thumbnail.get_height()
        except Exception, e:
            print "Exception detected:", e
            pix_w = GIZMO_SIZES[Preferences.gizmoSize]
            pix_h = pix_w
            thumbnail = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False,
                                       8, pix_w, pix_h)
            thumbnail.fill(0xffffffff)

        thumbnail = self.make_shadow(thumbnail)

        return thumbnail


    def load_djvu_thumbnail(self, pdfdoc, page_number, rotation=0, crop=[0.,0.,0.,0.]):
        """Create pdf pixbuf"""
        page = pdfdoc.document.pages[page_number]
        try:
            thumbnail = self.render_djvu_page(page, GIZMO_SIZES[Preferences.gizmoSize], prefer_thumbs=self.prefer_thumbnails)

            rotation = (-rotation) % 360
            rotation = ((rotation + 45) / 90) * 90
            thumbnail = thumbnail.rotate_simple(rotation)
            pix_w = thumbnail.get_width()
            pix_h = thumbnail.get_height()
            if crop != [0.,0.,0.,0.]:
                src_x = int(crop[0] * pix_w)
                src_y = int(crop[2] * pix_h)
                width = int((1. - crop[0] - crop[1]) * pix_w)
                height = int((1. - crop[2] - crop[3]) * pix_h)
                new_thumbnail = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False,
                                               8, width, height)
                thumbnail.copy_area(src_x, src_y, width, height,
                                    new_thumbnail, 0, 0)
                thumbnail = new_thumbnail
                pix_w = thumbnail.get_width()
                pix_h = thumbnail.get_height()
        except Exception, e:
            print "Exception detected:", e
            pix_w = GIZMO_SIZES[Preferences.gizmoSize]
            pix_h = pix_w
            thumbnail = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False,
                                       8, pix_w, pix_h)
            thumbnail.fill(0xffffffff)

        thumbnail = self.make_shadow(thumbnail)

        return thumbnail

    def make_shadow(self, thumbnail):
        # add border and shadows
        # canvas
        thickness = 2
        pix_w = thumbnail.get_width()
        pix_h = thumbnail.get_height()
        color = 0xFFFFFF00
        canvas = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, True, 8,
                                pix_w + thickness + 1,
                                pix_h + thickness + 1)
        canvas.fill(color)

        # border
        color = 0x404040FF
        canvas_border = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, True, 8,
                                pix_w + thickness + 1,
                                pix_h + thickness + 1)
        canvas_border.fill(color)

        # shadow
        color = 0xA0A090FF
        canvas_shadow = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, True, 8,
                        pix_w + thickness + 1,
                        pix_h + thickness + 1)
        canvas_shadow.fill(color)

        canvas_shadow.copy_area(0, 0, pix_w + 2, pix_h + 2, canvas, 1, 1)
        canvas_border.copy_area(0, 0, pix_w + 2, pix_h + 2, canvas, 0, 0)
        thumbnail.copy_area(0, 0, pix_w, pix_h, canvas, 1, 1)
        thumbnail = canvas

        return thumbnail


class PreferencesWindow(gtk.Dialog):
    """Displays global preference window"""

    def __init__(self):
        """ Initialize the Status window. """
        super(PreferencesWindow, self).__init__(flags=gtk.DIALOG_MODAL)
        self.set_title("Preferences")
        self.add_buttons(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OK, gtk.RESPONSE_OK)
        self._create()
        self.connect('response', self.close)

    def _create(self):
        self.set_default_size(300, 400)
        notebook = gtk.Notebook()
        notebook.set_border_width(6)
        notebook.insert_page(self._create_page_view(), gtk.Label("View"))
        notebook.insert_page(self._create_page_engine(), gtk.Label("PDF engine"))
        self.vbox.pack_start(notebook, True, True)
        self.vbox.show_all()

    def _create_page_view(self):
        vbox = gtk.VBox()
        vbox.set_border_width(12)

        table = gtk.Table(rows=4, columns=2, homogeneous=False)
        table.set_row_spacings(6)
        table.set_col_spacings(6)

        vbox.pack_start(table, True, True, 0)

        align = gtk.Alignment(0.0, 0.5)
        label = gtk.Label()
        label.set_markup("<b>Default zoom level:</b>")
        align.add(label)
        table.attach(align, 0, 1, 0, 1, gtk.FILL, gtk.FILL)

        align = gtk.Alignment(0.0, 0.5)
        self.zoom = gtk.combo_box_new_text() # gtk.ComboBox()
        align.add(self.zoom)
        self.zoom.append_text("100")
        self.zoom.append_text("200")
        self.zoom.append_text("300")
        self.zoom.append_text("400")
        self.zoom.append_text("Rember last time")
        table.attach(align, 1, 2, 0, 1, gtk.EXPAND | gtk.FILL, gtk.FILL)

        self.use_thumbs = gtk.CheckButton()
        self.use_thumbs.set_active(Preferences.preferThumbnails)
        self.use_thumbs.set_label("Use embedded thumbnails when possible")
        table.attach(self.use_thumbs, 0, 2, 1, 2, gtk.FILL, gtk.FILL)

        self.thumbs_lazy_rendering = gtk.CheckButton()
        self.thumbs_lazy_rendering.set_active(Preferences.lazyThumbnailsRendering)
        self.thumbs_lazy_rendering.set_label("Lazy thumbnails rendering")
        table.attach(self.thumbs_lazy_rendering, 0, 2, 2, 3, gtk.EXPAND | gtk.FILL, gtk.FILL)

        self.thumbs_antialiazing = gtk.CheckButton()
        self.thumbs_antialiazing.set_active(Preferences.useAntialiazing)
        self.thumbs_antialiazing.set_label("Use antialiazing")
        table.attach(self.thumbs_antialiazing, 0, 2, 3, 4, gtk.EXPAND | gtk.FILL, gtk.FILL)

        return vbox

    def _create_page_engine(self):
        vbox = gtk.VBox()
        vbox.set_border_width(12)

        table = gtk.Table(rows=4, columns=2, homogeneous=False)
        table.set_row_spacings(6)
        table.set_col_spacings(6)

        vbox.pack_start(table, True, True, 0)

        align = gtk.Alignment(0.0, 0.5)
        label = gtk.Label()
        label.set_markup("<b>Engine:</b>")
        align.add(label)
        table.attach(align, 0, 2, 0, 1, gtk.FILL, gtk.FILL)

        self.use_pypdf = gtk.RadioButton()
        self.use_pypdf.set_active(not Preferences.usePdftk)
        self.use_pypdf.set_label("PyPDF")
        table.attach(self.use_pypdf, 0, 1, 1, 2, gtk.FILL, gtk.FILL)

        if not found_pypdf:
            image = gtk.Image()
            image.set_from_stock(gtk.STOCK_DIALOG_WARNING, gtk.ICON_SIZE_MENU)
            image.set_tooltip_text("pypdf not installed")
            table.attach(image, 1, 2, 1, 2, gtk.EXPAND | gtk.FILL, gtk.FILL)
            self.use_pypdf.set_sensitive(False)

        self.use_pdftk = gtk.RadioButton(self.use_pypdf)
        self.use_pdftk.set_active(Preferences.usePdftk)
        self.use_pdftk.set_label("pdftk")
        table.attach(self.use_pdftk, 0, 1, 2, 3, gtk.EXPAND | gtk.FILL, gtk.FILL)

        if not found_pdftk:
            image = gtk.Image()
            image.set_from_stock(gtk.STOCK_DIALOG_WARNING, gtk.ICON_SIZE_MENU)
            image.set_tooltip_text("pypdf not installed")
            table.attach(image, 1, 2, 2, 3, gtk.EXPAND | gtk.FILL, gtk.FILL)
            self.use_pdftk.set_sensitive(False)

        return vbox

    def close(self, widget, event=None, data=None):
        if event == gtk.RESPONSE_OK:
            print "Saving settings..."
            # Push settings back
            Preferences.usePdftk = self.use_pdftk.get_active()
            Preferences.preferThumbnails = self.use_thumbs.get_active()
            Preferences.lazyThumbnailsRendering = self.thumbs_lazy_rendering.get_active()
# TODO            Preferences.gizmoSize = int(self.zoom.get_active_text())


class PixbufUtils:

    @staticmethod
    def bbox_upscale(box, gizmo):
        pix_w, pix_h = box
        if pix_h < pix_w or Preferences.fitPageWidth:
            pix_scale = float(Preferences.pageWidth)/float(pix_w)
            pix_h = int(float(Preferences.pageWidth) * float(pix_h) / float(pix_w))
            pix_w = Preferences.pageWidth
        elif pix_h > pix_w:
            pix_scale = float(gizmo)/float(pix_h)
            pix_w = int(float(gizmo) * float(pix_w) / float(pix_h))
            pix_h = gizmo
        else:
            pix_scale = float(gizmo)/float(pix_w)
            pix_w = gizmo
            pix_h = gizmo
        return (pix_w, pix_h, pix_scale)



class UndoRedoStack():
    def __init__(self):
        self.stack = []

    def undo(self):
        action = self.stack.pop()
        action.undo()

    def do(self, action):
        self.stack.append(action)
        action.do()


class Action:
    pass


class PageDeleteAction(Action):
    def __init__(self, object, before_idx, after_idx, postAction=None):
        self.name = "Delete page"
        self.object = object
        self.before = before_idx
        self.after = after_idx
        self.postAction = postAction

    def do(self):
        self.object.delete(self.after)
        if self.postAction:
            self.postAction()
        return True

    def undo(self):
        self.object.add(self.before)
        if self.postAction:
            self.postAction()
        return True


if __name__ == '__main__':
    gtk.gdk.threads_init()

    # Setup logging
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                        datefmt='%m-%d %H:%M',
                        filename=LOG_FILE,
                        filemode='a')

    consoleHandler = logging.StreamHandler()
    consoleHandler.setLevel(logging.DEBUG)
    consoleHandler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-8s %(message)s'))
    logging.getLogger('').addHandler(consoleHandler)
    logging.info("PdfSnip started...")

    PDFsnip()
#    gtk.gdk.threads_enter()
    gtk.main()
#    gtk.gdk.threads_leave()
