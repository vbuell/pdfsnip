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
except:
    print("python-djvulibre wasn't found. Djvu is disabled.")

import poppler      #for the rendering of pdf pages
from pyPdf import PdfFileWriter, PdfFileReader

ROOT_DIR = '/apps/pdfsnip'

KEY_THUMBNAILS = ROOT_DIR + '/prefer_embedded_thumbnails'
KEY_WINDOW_WIDTH = ROOT_DIR + '/ui_width'
KEY_WINDOW_HEIGHT = ROOT_DIR + '/ui_height'

class PDFsnip:
    # =======================================================
    # All the preferences are stored here.
    # =======================================================
    prefs = {
        'window width': min (700, gtk.gdk.screen_get_default().get_width() / 2 ),
        'window height': min(600, gtk.gdk.screen_get_default().get_height() - 50 ),
        'window x': 0,
        'window y': 0,
        'initial thumbnail size': 300,
        'initial zoom scale': 0.25,
        'initial gizmo size': 200,
    }

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
        """
        Item 1: The menu path. The letter after the underscore indicates an
           accelerator key once the menu is open.
        Item 2: The accelerator key for the entry
        Item 3: The callback function.
        Item 4: The callback action.  This changes the parameters with
           which the function is called.  The default is 0.
        Item 5: The item type, used to define what kind of an item it is.
           Here are the possible values:

           NULL               -> "<Item>"
           ""                 -> "<Item>"
           "<Title>"          -> create a title item
           "<Item>"           -> create a simple item
           "<CheckItem>"      -> create a check item
           "<ToggleItem>"     -> create a toggle item
           "<RadioItem>"      -> create a radio item
           <path>             -> path of a radio item to link against
           "<Separator>"      -> create a separator
           "<Branch>"         -> create an item to hold sub items (optional)
           "<LastBranch>"     -> create a right justified branch
        """
        self.menu_items = (
   	            ( "/_File",             None,         None, 0, "<Branch>" ),
#   	            ( "/File/_New",         "<control>N", self.about_dialog, 0, None ),
#   	            ( "/File/_Open",        "<control>O", self.about_dialog, 0, None ),
   	            ( "/File/_Append",      "<control>I", self.on_action_add_doc_activate, 0, None ),
   	            ( "/File/_Save",        "<control>S", self.save_file, 0, None ),
   	            ( "/File/Save _As...",  None,         self.choose_export_pdf_name, 0, None ),
   	            ( "/File/sep1",         None,         None, 0, "<Separator>" ),
   	            ( "/File/File _Info",   None,         self.file_info, 0, None ),
   	            ( "/File/sep1",         None,         None, 0, "<Separator>" ),
   	            ( "/File/Quit",         "<control>Q", self.close_application, 0, None ),
   	            ( "/_Edit/Delete",      "Delete",     self.clear_selected, 0, None ),
   	            ( "/_Edit/Rotate Clockwise",   "<MOD1>]",        self.rotate_page_right, 0, None ),
   	            ( "/_Edit/Rotate Counterclockwise",   "<MOD1>[",        self.rotate_page_left, 0, None ),
   	            ( "/_Edit/Crop...",     None,         self.crop_page_dialog, 0, None ),
   	            ( "/_View/Use thumbnails when possible",     None, self.toggle_use_thumbnails, 0, "<ToggleItem>" ),
   	            ( "/_View/Zoom In",     None,         self.set_zoom_width, 0, None ),
   	            ( "/_View/Zoom Out",    None,         None, 0, None ),
   	            ( "/_View/Zoom To Width", "<control>0", None, 0, None ),
#   	            ( "/_Tools/Add thumbnails to file",   None,  None, 0, None ),
   	            ( "/_Help/About",       None,         self.about_dialog, 0, None ),
   	            )
        # GConf stuff
        self.gconf_client = gconf.client_get_default()
        self.gconf_client.add_dir(ROOT_DIR, gconf.CLIENT_PRELOAD_NONE)

        try:
            gconf_value = int(self.gconf_client.get_string(KEY_WINDOW_WIDTH))
            if gconf_value:
                self.prefs['window width'] = gconf_value
            gconf_value = int(self.gconf_client.get_string(KEY_WINDOW_HEIGHT))
            if gconf_value:
                self.prefs['window height'] = gconf_value
        except Exception, e:
            print e

        # Create the temporary directory
        self.tmp_dir = tempfile.mkdtemp("pdfsnip")
        os.chmod(self.tmp_dir, 0700)

        pixmap = os.path.join(sys.prefix,'share','pixmaps','pdfsnip.png')
        try:
            gtk.window_set_default_icon_from_file(pixmap)
        except:
            print(_('File %s does not exist') % pixmap)

        self.is_dirty = False

        # Create the main window, and attach delete_event signal to terminating
        # the application
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)

        self.window.set_title('PdfSnip')
        self.window.set_border_width(0)
        self.window.move(self.prefs['window x'], self.prefs['window y'])
        self.window.set_default_size(self.prefs['window width'],
                                     self.prefs['window height'])
        self.window.connect('delete_event', self.close_application)
        self.window.show()

        # Create a vbox to hold the thumnails-container
        vbox = gtk.VBox()
        self.window.add(vbox)

        menubar = self.get_main_menu(self.window)
        vbox.pack_start(menubar, False, True, 0)
        menubar.show()

        # Create a scrolled widow to hold the thumnails-container
        self.sw = gtk.ScrolledWindow()
        self.sw.set_border_width(0)
        self.sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        self.sw.drag_dest_set(gtk.DEST_DEFAULT_MOTION |
                              gtk.DEST_DEFAULT_HIGHLIGHT |
                              gtk.DEST_DEFAULT_DROP |
                              gtk.DEST_DEFAULT_MOTION,
                              self.TARGETS_SW,
                              gtk.gdk.ACTION_COPY |
                              gtk.gdk.ACTION_MOVE )
        self.sw.connect('drag_data_received', self.sw_dnd_received_data)
        self.sw.connect('button_press_event', self.sw_button_press_event)
        vbox.pack_start(self.sw)

        # Create an alignment to keep the thumbnails center-aligned
#        align = gtk.Alignment(0.5, 0.5, 0, 0)
#        self.sw.add_with_viewport(align)

        # Create ListStore model and IconView
        self.model = gtk.ListStore(str,             # 0.Text descriptor
                                   gtk.gdk.Pixbuf,  # 1.Thumbnail image
                                   int,             # 2.Document number
                                   int,             # 3.Page number
                                   int,             # 4.Thumbnail width
                                   str,             # 5.Document filename
                                   bool,            # 6.Rendered
                                   int,             # 7.Rotation angle
                                   float,           # 8.Crop left
                                   float,           # 9.Crop right
                                   float,           # 10.Crop top
                                   float)           # 11.Crop bottom

        self.zoom_scale = self.prefs['initial zoom scale']
        self.gizmo_size = self.prefs['initial gizmo size']
#        self.iv_col_width = self.prefs['initial thumbnail size']
        self.iv_col_width = self.prefs['initial gizmo size']

        self.iconview = gtk.IconView(self.model)
        self.iconview.set_item_width(self.iv_col_width + 12)

        self.iconview.set_pixbuf_column(1)
#        self.cellpb = gtk.CellRendererPixbuf()
#        self.cellpb.set_property('follow-state', True)
#        self.iconview.pack_start(self.cellpb, False)
#        self.iconview.set_attributes(self.cellpb, pixbuf=1)

#        self.iconview.set_text_column(0)
        self.celltxt = gtk.CellRendererText()
        self.celltxt.set_property('width', self.iv_col_width)
        self.celltxt.set_property('wrap-width', self.iv_col_width)
        self.celltxt.set_property('alignment', pango.ALIGN_CENTER)
        self.iconview.pack_start(self.celltxt, False)
        self.iconview.set_attributes(self.celltxt, text=0)

        self.iconview.set_selection_mode(gtk.SELECTION_MULTIPLE)
        self.iconview.enable_model_drag_source(gtk.gdk.BUTTON1_MASK,
                                               self.TARGETS_IV,
                                               gtk.gdk.ACTION_COPY |
                                               gtk.gdk.ACTION_MOVE )
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
        style_sw = self.sw.get_style()
        for state in (gtk.STATE_NORMAL, gtk.STATE_PRELIGHT, gtk.STATE_ACTIVE):
            style.base[state] = style_sw.bg[gtk.STATE_NORMAL]
        self.iconview.set_style(style)

#        align.add(self.iconview)
#        self.sw.add_with_viewport(self.iconview)
        self.sw.add(self.iconview)

        # Status bar
#        self.status_bar = gtk.Statusbar()
#        vbox.pack_start(self.status_bar, True, True, 0)
#        self.status_bar.show()

        # Define window callback function and show window
        self.window.connect('size_allocate', self.on_window_size_request)        # resize
#        self.window.connect('key_press_event', self.on_keypress_event ) # keypress
        self.window.show_all()

        # Creating the popup menu
        self.popup = gtk.Menu()
        popup_rotate_right = gtk.MenuItem(_('Rotate Page(s) Clockwise'))
        popup_rotate_left = gtk.MenuItem(_('Rotate Page(s) Counterclockwise'))
        popup_crop = gtk.MenuItem(_('Crop Page(s)'))
        popup_delete = gtk.MenuItem(_('Delete Page(s)'))
        popup_rotate_right.connect('activate', self.rotate_page_right)
        popup_rotate_left.connect('activate', self.rotate_page_left)
        popup_crop.connect('activate', self.crop_page_dialog)
        popup_delete.connect('activate', self.clear_selected)
        popup_rotate_right.show()
        popup_rotate_left.show()
        popup_crop.show()
        popup_delete.show()
        self.popup.append(popup_rotate_right)
        self.popup.append(popup_rotate_left)
        self.popup.append(popup_crop)
        self.popup.append(popup_delete)

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
        self.rendering_thread = PDF_Renderer(self.model, self.pdfqueue,
                                             0, self.gizmo_size)
#                                             self.zoom_scale, self.gizmo_size)
        self.rendering_thread.connect('reset_iv_width', self.reset_iv_width)
        self.rendering_thread.daemon = True
        self.rendering_thread.start()

        self.retitle()

        # Importing documents passed as command line arguments
        for filename in sys.argv[1:]:
            self.filename = os.path.abspath(filename)
            (self.path, self.shortname) = os.path.split(self.filename)
            (self.shortname, self.ext) = os.path.splitext(self.shortname)
            if self.ext.lower() == '.djvu':
                self.add_djvu_pages(filename)
            elif self.ext.lower() == '.pdf':
                self.add_pdf_pages(filename)


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
        self.window.set_title(title)
        print "retitle():", title


    def get_main_menu(self, window):
        accel_group = gtk.AccelGroup()

        # This function initializes the item factory.
        # Param 1: The type of menu - can be MenuBar, Menu,
        #          or OptionMenu.
        # Param 2: The path of the menu.
        # Param 3: A reference to an AccelGroup. The item factory sets up
        #          the accelerator table while generating menus.
        item_factory = gtk.ItemFactory(gtk.MenuBar, "<main>", accel_group)

        # This method generates the menu items. Pass to the item factory
        #  the list of menu items
        item_factory.create_items(self.menu_items)

        # Attach the new accelerator group to the window.
        window.add_accel_group(accel_group)

        item_use_thumbs = item_factory.get_widget("/View/Use thumbnails when possible")
        print "item_factory.get_item(/_View/Use thumbnails when possible)", item_use_thumbs
        try:
            item_use_thumbs.set_active(self.gconf_client.get_bool(KEY_THUMBNAILS))
        except Exception, e:
            print e

        # need to keep a reference to item_factory to prevent its destruction
        self.item_factory = item_factory
        # Finally, return the actual menu bar created by the item factory.
        return item_factory.get_widget("<main>")

    def toggle_use_thumbnails(self, window, event):
        self.gconf_client.set_bool(KEY_THUMBNAILS, event.get_active())

    def set_zoom_width(self, window, event):
        
        self.gizmo_size = self.gizmo_size * 2
        self.rendering_thread.set_width(self.gizmo_size)

        for row in self.model:
           row[6] = False

        if self.rendering_thread.paused:
            self.rendering_thread.paused = False
            self.rendering_thread.evnt.set()
            self.rendering_thread.evnt.clear()


    # =======================================================
    def on_window_size_request(self, window, event):
        """Main Window resize - workaround for autosetting of
           iconview cols no."""

        #add 12 because of: http://bugzilla.gnome.org/show_bug.cgi?id=570152
        col_num = 9 * window.get_size()[0] / (10 * (self.iv_col_width + 12))
        self.iconview.set_columns(col_num)

    # =======================================================
    def reset_iv_width(self, renderer=None):
        """Reconfigures the width of the iconview columns"""

        gobject.idle_add(self.set_something)

    def set_something(self):
        max_w = max(row[4] for row in self.model)
        print "(reset_iv_width) Before: ", self.iv_col_width
        print "(reset_iv_width) After: ", max_w
        if max_w != self.iv_col_width:
            self.iv_col_width = max_w
            self.celltxt.set_property('width', self.iv_col_width)
            self.celltxt.set_property('wrap-width', self.iv_col_width)
            self.iconview.set_item_width(self.iv_col_width + 12) #-1)
            self.on_window_size_request(self.window, None)

    # =======================================================
    def on_keypress_event(self, widget, event):
        """Keypress events in Main Window"""

        #keyname = gtk.gdk.keyval_name(event.keyval)
        if event.keyval == 65535:   # Delete keystroke
            self.clear_selected()

    # =======================================================
    def close_application(self, widget, event=None, data=None):
        """Termination"""

        # save configuration
        self.gconf_client.set_string(KEY_WINDOW_WIDTH, str(self.window.get_size()[0]))
        self.gconf_client.set_string(KEY_WINDOW_HEIGHT, str(self.window.get_size()[1]))

        #gtk.gdk.threads_leave()
        self.rendering_thread.quit = True
        #gtk.gdk.threads_enter()
        if self.rendering_thread.paused == True:
             self.rendering_thread.evnt.set()
             self.rendering_thread.evnt.clear()
        if os.path.isdir(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)
        if gtk.main_level():
            gtk.main_quit()
        else:
            sys.exit(0)
        return False

    # =======================================================
    def add_djvu_pages(self, filename,
                            firstpage=None, lastpage=None,
                            angle=0, crop=[0.,0.,0.,0.]   ):
        """Add pages of a pdf document to the model"""

        print "add_djvu_pages"

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

        n_start = 1
        n_end = pdfdoc.npage
        if firstpage:
           n_start = min(n_end, max(1, firstpage))
        if lastpage:
           n_end = max(n_start, min(n_end, lastpage))

        for npage in range(n_start, n_end + 1):
            descriptor = ''.join([pdfdoc.shortname, '\n', _('page'), ' ', str(npage)])
            width = self.iv_col_width
            thumbnail = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False,
                                       8, width, width)
            self.model.append((descriptor,              # 0
                               thumbnail,               # 1
                               pdfdoc.nfile,            # 2
                               npage,                   # 3
                               width,                   # 4
                               pdfdoc.filename,         # 5
                               False,                   # 6
                               angle,                   # 7
                               crop[0],crop[1],         # 8-9
                               crop[2],crop[3]       )) # 10-11
            res = True

        gobject.idle_add(self.retitle)
        if res and self.rendering_thread.paused:
            self.rendering_thread.paused = False
            self.rendering_thread.evnt.set()
            self.rendering_thread.evnt.clear()
        return res

    # =======================================================
    def add_pdf_pages(self, filename,
                            firstpage=None, lastpage=None,
                            angle=0, crop=[0.,0.,0.,0.]   ):
        """Add pages of a pdf document to the model"""

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

        n_start = 1
        n_end = pdfdoc.npage
        if firstpage:
           n_start = min(n_end, max(1, firstpage))
        if lastpage:
           n_end = max(n_start, min(n_end, lastpage))

        for npage in range(n_start, n_end + 1):
            descriptor = ''.join([pdfdoc.shortname, '\n', _('page'), ' ', str(npage)])
            width = self.iv_col_width
            thumbnail = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False,
                                       8, width, width)
            self.model.append((descriptor,              # 0
                               thumbnail,               # 1
                               pdfdoc.nfile,            # 2
                               npage,                   # 3
                               width,                   # 4
                               pdfdoc.filename,         # 5
                               False,                   # 6
                               angle,                   # 7
                               crop[0],crop[1],         # 8-9
                               crop[2],crop[3]       )) # 10-11
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
            self.export_to_file(self.pdfqueue[0].filename)
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

    # =======================================================
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
                    file_out = file_out + '.pdf'
                try:
                    self.export_to_file(file_out)
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

    # =======================================================
    def export_to_file(self, file_out):
        """Export to file"""

        pdf_output = PdfFileWriter()
        pdf_input = []
        for pdfdoc in self.pdfqueue:
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
            nfile = row[2]
            npage = row[3]
            current_page = pdf_input[nfile-1].getPage(npage-1)
            angle = row[7]
            angle0 = current_page.get("/Rotate",0)
            crop = [row[8],row[9],row[10],row[11]]
            if angle is not 0:
                current_page.rotateClockwise(angle)
            if crop != [0.,0.,0.,0.]:
                rotate_times = ( ( ( angle + angle0 ) % 360 + 45 ) / 90 ) % 4
                crop_init = crop
                if rotate_times is not 0:
                    perm = [0,2,1,3]
                    for it in range(rotate_times):
                        perm.append(perm.pop(0))
                    perm.insert(1,perm.pop(2))
                    crop = [crop_init[perm[side]] for side in range(4)]
                #(x1, y1) = current_page.cropBox.lowerLeft
                #(x2, y2) = current_page.cropBox.upperRight
                (x1, y1) = [float(xy) for xy in current_page.mediaBox.lowerLeft]
                (x2, y2) = [float(xy) for xy in current_page.mediaBox.upperRight]
                x1_new = int( x1 + (x2-x1) * crop[0] )
                x2_new = int( x2 - (x2-x1) * crop[1] )
                y1_new = int( y1 + (y2-y1) * crop[3] )
                y2_new = int( y2 - (y2-y1) * crop[2] )
                #current_page.cropBox.lowerLeft = (x1_new, y1_new)
                #current_page.cropBox.upperRight = (x2_new, y2_new)
                current_page.mediaBox.lowerLeft = (x1_new, y1_new)
                current_page.mediaBox.upperRight = (x2_new, y2_new)

            pdf_output.addPage(current_page)

        # finally, write "output" to document-output.pdf
        print(_('exporting to:'), file_out)
        pdf_output.write(file(file_out, 'wb'))

    # =======================================================
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
                    elif ext == '.odt' or ext == '.ods' or ext == '.odc':
                        print(_('OpenDocument not supported yet!'))
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

    # =======================================================
    def clear_selected(self, button=None, data=None):
        """Removes the selected Element in the IconView"""

        model = self.iconview.get_model()
        selection = self.iconview.get_selected_items()
        if selection:
            selection.sort(reverse=True)
            self.set_dirty(True)
            for path in selection:
                iter = model.get_iter(path)
                model.remove(iter)
            path = selection[-1]
            self.iconview.select_path(path)
            if not self.iconview.path_is_selected(path):
                if len(model) > 0:	# select the last row
                    row = model[-1]
                    path = row.path
                    self.iconview.select_path(path)
            self.iconview.grab_focus()

    # =======================================================
    def iv_drag_begin(self, iconview, context):
        """Sets custom icon on drag begin for multiple items selected"""

        if len(iconview.get_selected_items()) > 1:
            iconview.stop_emission('drag_begin')
            context.set_icon_stock(gtk.STOCK_DND_MULTIPLE, 0, 0)

    # =======================================================
    def iv_dnd_get_data(self, iconview, context, 
                        selection_data, target_id, etime):
        """Handles requests for data by drag and drop in iconview"""

        model = iconview.get_model()
        selection = self.iconview.get_selected_items()
        selection.sort(key=lambda x: x[0])
        data = []
        for path in selection:
            if selection_data.target == 'MODEL_ROW_INTERN':
                data.append( str(path[0]) )
            elif selection_data.target == 'MODEL_ROW_EXTERN':
                iter = model.get_iter(path)
                nfile, npage, angle = model.get(iter, 2, 3, 7)
                crop = model.get(iter, 8, 9, 10, 11)
                pdfdoc = self.pdfqueue[nfile - 1]
                data.append('\n'.join([pdfdoc.filename,
                                       str(npage),
                                       str(angle)      ] +
                                       [str(side) for side in crop] ) )
        if data:
            data = '\n;\n'.join(data)
            selection_data.set(selection_data.target, 8, data)

    # =======================================================
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
                before = (   position == gtk.ICON_VIEW_DROP_LEFT
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
                        npage, angle = [int(k) for k in tmp[1:3]]
                        crop = [float(side) for side in tmp[3:7]]
                        if self.add_pdf_pages(filename, npage, npage,
                                                        angle, crop  ):
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

    # =======================================================
    def iv_dnd_data_delete(self, widget, context):
        """Deletes dnd items after a successful move operation"""

        model = self.iconview.get_model()
        selection = self.iconview.get_selected_items()
        ref_del_list = [gtk.TreeRowReference(model,path) for path in selection]
        for ref_del in ref_del_list:
            path = ref_del.get_path()
            iter = model.get_iter(path)
            model.remove(iter)

    # =======================================================
    def iv_dnd_motion(self, iconview, context, x, y, etime):
        """Handles the drag-motion signal in order to auto-scroll the view"""

        autoscroll_area = 40
        sw_vadj = self.sw.get_vadjustment()
        sw_height = self.sw.get_allocation().height
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

    # =======================================================
    def iv_dnd_leave_end(self, widget, context, ignored=None):
        """Ends the auto-scroll during DND"""

        if self.iv_auto_scroll_timer:
            gobject.source_remove(self.iv_auto_scroll_timer)
            self.iv_auto_scroll_timer = None

    # =======================================================
    def iv_auto_scroll(self):
        """Timeout routine for auto-scroll"""

        sw_vadj = self.sw.get_vadjustment()
        sw_vpos = sw_vadj.get_value()
        if self.iv_auto_scroll_direction == gtk.DIR_UP:
            sw_vpos -= sw_vadj.step_increment
            sw_vadj.set_value( max(sw_vpos, sw_vadj.lower) )
        elif self.iv_auto_scroll_direction == gtk.DIR_DOWN:
            sw_vpos += sw_vadj.step_increment
            sw_vadj.set_value( min(sw_vpos, sw_vadj.upper - sw_vadj.page_size) )
        return True  #call me again

    # =======================================================
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
                self.popup.popup( None, None, None, event.button, time)
            return 1

    # =======================================================
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
                npage, angle = [int(k) for k in tmp[1:3]]
                crop = [float(side) for side in tmp[3:7]]
                if self.add_pdf_pages(filename, npage, npage, angle, crop):
                    if context.action == gtk.gdk.ACTION_MOVE:
                        context.finish(True, True, etime)
        elif target_id == self.TEXT_URI_LIST:
            uri = data.strip()
            uri_splitted = uri.split() # we may have more than one file dropped
            for uri in uri_splitted:
                filename = self.get_file_path_from_dnd_dropped_uri(uri)
                if os.path.isfile(filename): # is it file?
                    self.add_pdf_pages(filename)

    # =======================================================
    def sw_button_press_event(self, scrolledwindow, event):
        """Unselects all items in iconview on mouse click in scrolledwindow"""

        if event.button == 1:
            self.iconview.unselect_all()

    # =======================================================
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

    # =======================================================
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
            nfile = model.get_value(iter, 2)
            npage = model.get_value(iter, 3)

            rotate_times = ( ( (-angle) % 360 + 45 ) / 90 ) % 4
            crop = [0.,0.,0.,0.]
            if rotate_times is not 0:
                perm = [0,2,1,3]
                for it in range(rotate_times):
                    perm.append(perm.pop(0))
                perm.insert(1,perm.pop(2))
                crop = [model.get_value(iter, 8 + perm[side]) for side in range(4)]
                for side in range(4):
                    model.set_value(iter, 8 + side, crop[side])

            new_angle = model.get_value(iter, 7) + angle
            model.set_value(iter, 7, new_angle)
            model.set_value(iter, 6, False) #rendering request

        if self.rendering_thread.paused:
            self.rendering_thread.paused = False
            self.rendering_thread.evnt.set()
            self.rendering_thread.evnt.clear()


    # =======================================================
    def file_info(self, widget, event):
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

    # =======================================================
    def crop_page_dialog(self, widget):
        """Opens a dialog box to define margins for page cropping"""

        model = self.iconview.get_model()
        selection = self.iconview.get_selected_items()

        crop = [0.,0.,0.,0.]
        if selection:
            path = selection[0]
            iter = model.get_iter(path)
            crop = [model.get_value(iter, 8 + side) for side in range(4)]

        dialog = gtk.Dialog(title=(_('Crop Selected Page(s)')),
                            parent=self.window,
                            flags=gtk.DIALOG_MODAL,
                            buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                     gtk.STOCK_OK, gtk.RESPONSE_OK))
        dialog.set_size_request(340, 250)
        dialog.set_default_response(gtk.RESPONSE_OK)

        frame = gtk.Frame(_('Crop Margins'))
        dialog.vbox.pack_start(frame, False, False, 20)

        vbox = gtk.VBox(False, 0)
        frame.add(vbox)

        spin_list = []
        units = 2 * [_('% of width')] + 2 * [_('% of height')] 
        for margin in (_('Left'),_('Right'),_('Top'),_('Bottom')):
            hbox = gtk.HBox(True, 0)
            vbox.pack_start(hbox, False, False, 5)

            label = gtk.Label(margin)
            label.set_alignment(0, 0.0)
            hbox.pack_start(label, True, True, 20)

            adj = gtk.Adjustment(100.*crop.pop(0), 0.0, 100.0, 1.0, 5.0, 0.0)
            spinner = gtk.SpinButton(adj, 0, 1)
            spinner.set_activates_default(True)
            spin_list.append(spinner)
            hbox.pack_start(spinner, False, False, 30)

            label = gtk.Label(units.pop(0))
            label.set_alignment(0, 0.0)
            hbox.pack_start(label, True, True, 0)

        dialog.show_all()
        result = dialog.run()

        if result == gtk.RESPONSE_OK:
            crop = []
            for side in spin_list:
                crop.append( side.get_value()/100. )
            for path in selection:
                iter = model.get_iter(path)
                for it in range(4):
                    model.set_value(iter, 8 + it, crop[it])
                model.set_value(iter, 6, False) #rendering request
            if self.rendering_thread.paused:
                self.rendering_thread.paused = False
                self.rendering_thread.evnt.set()
                self.rendering_thread.evnt.clear()
        elif result == gtk.RESPONSE_CANCEL:
            print(_('Dialog closed'))
        dialog.destroy()

    # =======================================================
    def about_dialog(self, widget, data=None):
        about_dialog = gtk.AboutDialog()
        try:
            about_dialog.set_transient_for(self.window)
            about_dialog.set_modal(True)
        except:
            pass
        # FIXME
        about_dialog.set_name('PdfSnip')
        about_dialog.set_version('0.1')
        about_dialog.set_comments(_(
            'PdfSnip is an GTK+ based utility for splitting, rearrangement \
            and modification of PDF documents.'))
        about_dialog.set_authors(['Volodymyr Buell','Konstantinos Poulios',])
        about_dialog.set_website_label('http://code.google.com/p/pdfsnip/')
        about_dialog.set_logo_icon_name('pdfsnip')
        about_dialog.connect('response', lambda w, a: about_dialog.destroy())
        about_dialog.connect('delete_event', lambda w, a: about_dialog.destroy())
        about_dialog.show_all()

# =======================================================
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
            self.npage = self.document.get_n_pages()
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
            self.npage = len(self.document.pages)

        else:
            self.nfile = 0



# =======================================================
class PDF_Renderer(threading.Thread, gobject.GObject):

    def __init__(self, model, pdfqueue, scale=1., width=100):
        threading.Thread.__init__(self)
        gobject.GObject.__init__(self)
        self.model = model
        self.scale = scale
        self.default_width = width
        self.pdfqueue = pdfqueue
        self.quit = False
        self.evnt = threading.Event()
        self.paused = False
        self.antialiazing = True
        self.antialiazing_factor = 4

    def set_width(self, width):
        self.default_width = width

    def run(self):
        while not self.quit:
            rendered_all = True
            for row in self.model:
                if self.quit:
                    break
                if not row[6]:
                    rendered_all = False
#                    gtk.gdk.threads_enter() # Overusing of threads_enter for models
                    try:
                        nfile = row[2]
                        npage = row[3]
                        angle = row[7]
                        crop = [row[8],row[9],row[10],row[11]]
                        pdfdoc = self.pdfqueue[nfile - 1]
                        if isinstance(pdfdoc, PDF_Doc):
                            thumbnail = self.load_pdf_thumbnail(pdfdoc, npage, angle, crop)
                        elif isinstance(pdfdoc, DJVU_Doc):
                            thumbnail = self.load_djvu_thumbnail(pdfdoc, npage, angle, crop)

                        row[6] = True
                        row[4] = thumbnail.get_width()
                        row[1] = thumbnail
                    finally:
                        pass
#                       gtk.gdk.threads_leave()
            if rendered_all:
                self.paused = True
                if self.model.get_iter_first(): #just checking if model isn't empty
                    self.emit('reset_iv_width')
#                    gobject.idle_add(self.reset_iv_width)
                self.evnt.wait()

    # =======================================================
    def bbox_upscale(self, box, gizmo):
        pix_w, pix_h = box
        if pix_h > pix_w:
            pix_scale = float(gizmo)/float(pix_h)
            pix_w = int(float(gizmo) * float(pix_w) / float(pix_h))
            pix_h = gizmo
        elif pix_h < pix_w:
            pix_scale = float(gizmo)/float(pix_w)
            pix_h = int(float(gizmo) * float(pix_h) / float(pix_w))
            pix_w = gizmo
        else:
            pix_scale = float(gizmo)/float(pix_w)
            pix_w = gizmo
            pix_h = gizmo
        return (pix_w, pix_h, pix_scale)

    def render_pdf_page(self, page, gizmo_size, antialiazing=True, prefer_thumbs=True):
        """Create pixbuf from page"""
        got_pixbuf = False
        if prefer_thumbs:
            thumbnail = page.get_thumbnail_pixbuf()
            if thumbnail:
                got_pixbuf = True
                print "Got thumbnail!!!!", thumbnail.get_width(), thumbnail.get_height()
                pix_w = thumbnail.get_width()
                pix_h = thumbnail.get_height()
                # Scale thumbnail
                pix_w, pix_h, pix_scale = self.bbox_upscale((pix_w, pix_h), self.default_width)
                thumbnail_small = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False,
                                       8, pix_w , pix_h)
                thumbnail.scale(thumbnail_small, 0, 0, pix_w , pix_h, 0, 0,
                                pix_scale,
                                pix_scale,
                                gtk.gdk.INTERP_BILINEAR)
                thumbnail = thumbnail_small
        if not got_pixbuf:
            # Render page
            pix_w, pix_h = page.get_size()
            if self.scale == 0:
                pix_w, pix_h, pix_scale = self.bbox_upscale((pix_w, pix_h), self.default_width)
            else:
                pix_scale = self.scale
                pix_w = int(pix_w * self.scale)
                pix_h = int(pix_h * self.scale)

            if self.antialiazing:
                pix_w = pix_w*self.antialiazing_factor
                pix_h = pix_h*self.antialiazing_factor
                pix_scale = pix_scale*self.antialiazing_factor

            thumbnail = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False,
                                       8, pix_w , pix_h)

            print "render_to_pixbuf", pix_w, pix_h, pix_scale
            page.render_to_pixbuf(0,0,pix_w,pix_h, pix_scale, 0, thumbnail)

            if self.antialiazing:
                pix_w = pix_w/self.antialiazing_factor
                pix_h = pix_h/self.antialiazing_factor
                pix_scale = pix_scale/self.antialiazing_factor
                thumbnail_small = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False,
                                       8, pix_w , pix_h)
                thumbnail.scale(thumbnail_small, 0, 0, pix_w , pix_h, 0, 0,
                                float(1)/float(self.antialiazing_factor),
                                float(1)/float(self.antialiazing_factor),
                                gtk.gdk.INTERP_BILINEAR)
                thumbnail = thumbnail_small
        return thumbnail


    def render_djvu_page(self, page, gizmo_size, antialiazing=True, prefer_thumbs=True):
        """Create pixbuf from page"""
        import numpy
        
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

        mode = djvu.decode.RENDER_COLOR_ONLY
        djvu_pixel_format = djvu.decode.PixelFormatRgbMask(0xff0000, 0xff00, 0xff, bpp=32)

        bytes_per_line = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_ARGB32, pix_w)
        color_buffer = numpy.zeros((pix_h, bytes_per_line), dtype=numpy.uint32)
        page_job.render(mode, rect, rect, djvu_pixel_format, row_alignment=bytes_per_line, buffer=color_buffer)
        mask_buffer = numpy.zeros((pix_h, bytes_per_line), dtype=numpy.uint32)
        if mode == djvu.decode.RENDER_FOREGROUND:
            page_job.render(djvu.decode.RENDER_MASK_ONLY, rect, rect, djvu_pixel_format, row_alignment=bytes_per_line, buffer=mask_buffer)
            mask_buffer <<= 24
            color_buffer |= mask_buffer
        color_buffer ^= 0xff000000
#        surface = cairo.ImageSurface.create_for_data(color_buffer, cairo.FORMAT_ARGB32, pix_w, pix_h)
        thumbnail = gtk.gdk.pixbuf_new_from_data(color_buffer, gtk.gdk.COLORSPACE_RGB, True, 32, pix_w, pix_h, 0)

        return thumbnail

    def load_pdf_thumbnail(self, pdfdoc, npage, rotation=0, crop=[0.,0.,0.,0.]):
        """Create pdf pixbuf"""

        page = pdfdoc.document.get_page(npage-1)
        try:
            thumbnail = self.render_pdf_page(page, self.default_width, antialiazing=True, prefer_thumbs=True)

            rotation = (-rotation) % 360
            rotation = ((rotation + 45) / 90) * 90
            thumbnail = thumbnail.rotate_simple(rotation)
            pix_w = thumbnail.get_width()
            pix_h = thumbnail.get_height()
            if crop != [0.,0.,0.,0.]:
                src_x = int( crop[0] * pix_w )
                src_y = int( crop[2] * pix_h )
                width = int( (1. - crop[0] - crop[1]) * pix_w )
                height = int( (1. - crop[2] - crop[3]) * pix_h )
                new_thumbnail = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False,
                                               8, width, height)
                thumbnail.copy_area(src_x, src_y, width, height,
                                    new_thumbnail, 0, 0)
                thumbnail = new_thumbnail
                pix_w = thumbnail.get_width()
                pix_h = thumbnail.get_height()
        except Exception, e:
            print "Exception detected:", e
            pix_w = self.default_width
            pix_h = pix_w
            thumbnail = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False,
                                       8, pix_w, pix_h)
            thumbnail.fill(0xffffffff)

        thumbnail = self.make_shadow(thumbnail)

        return thumbnail


    def load_djvu_thumbnail(self, pdfdoc, npage, rotation=0, crop=[0.,0.,0.,0.]):
        """Create pdf pixbuf"""

        page = pdfdoc.document.pages[npage-1]
        try:
            thumbnail = self.render_djvu_page(page, self.default_width, antialiazing=True, prefer_thumbs=True)

            rotation = (-rotation) % 360
            rotation = ((rotation + 45) / 90) * 90
            thumbnail = thumbnail.rotate_simple(rotation)
            pix_w = thumbnail.get_width()
            pix_h = thumbnail.get_height()
            if crop != [0.,0.,0.,0.]:
                src_x = int( crop[0] * pix_w )
                src_y = int( crop[2] * pix_h )
                width = int( (1. - crop[0] - crop[1]) * pix_w )
                height = int( (1. - crop[2] - crop[3]) * pix_h )
                new_thumbnail = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False,
                                               8, width, height)
                thumbnail.copy_area(src_x, src_y, width, height,
                                    new_thumbnail, 0, 0)
                thumbnail = new_thumbnail
                pix_w = thumbnail.get_width()
                pix_h = thumbnail.get_height()
        except Exception, e:
            print "Exception detected:", e
            pix_w = self.default_width
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


# =======================================================
if __name__ == '__main__':
    gtk.gdk.threads_init()
    PDFsnip()
#    gtk.gdk.threads_enter()
    gtk.main()
#    gtk.gdk.threads_leave()
