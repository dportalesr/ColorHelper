"""
ColorHelper

Copyright (c) 2015 Isaac Muse <isaacmuse@gmail.com>
License: MIT
"""
import sublime
import sublime_plugin
from ColorHelper.lib.color_box import color_box, palette_preview
from ColorHelper.lib.scheme_lum import scheme_lums
from ColorHelper.lib.rgba import RGBA
import ColorHelper.lib.webcolors as webcolors
import threading
from time import time, sleep
import re

css = None
pref_settings = None
ch_settings = None
border_color = '#333333'
back_arrow = None
cross = None

COLOR_RE = re.compile(
    r'''(?x)
    (?P<hex>\#(?P<hex_content>(?:[\dA-Fa-f]{3}){1,2})) |
    (?P<rgb>rgb\(\s*(?P<rgb_content>(?:\d+\s*,\s*){2}\d+)\s*\)) |
    (?P<rgba>rgba\(\s*(?P<rgba_content>(?:\d+\s*,\s*){3}(?:(?:\d*\.\d+)|\d))\s*\)) |
    (?P<hsl>hsl\(\s*(?P<hsl_content>\d+\s*,\s*\d+%\s*,\s*\d+%)\s*\)) |
    (?P<hsla>hsla\(\s*(?P<hsla_content>\d+\s*,\s*(?:\d+%\s*,\s*){2}(?:(?:\d*\.\d+)|\d))\s*\)) |
    (?P<hash>\#) |
    (?P<rgb_open>rgb\() |
    (?P<rgba_open>rgba\() |
    (?P<hsl_open>hsl\() |
    (?P<hsla_open>hsla\()
    '''
)

if 'ch_thread' not in globals():
    ch_thread = None


class InsertionCalc(object):
    def __init__(self, view, point, target_color):
        """ Init insertion object """
        self.view = view
        self.convert_rgb = False
        self.convert_hsl = False
        self.alpha = None
        self.region = sublime.Region(point)
        self.format_override = False
        self.start = point - 50
        self.end = point + 50
        self.point = point
        visible = self.view.visible_region()
        if self.start < visible.begin():
            self.start = visible.begin()
        if self.end > visible.end():
            self.end = visible.end()
        self.use_web_colors = bool(ch_settings.get('use_webcolor_names', True))
        self.preferred_format = ch_settings.get('preferred_format', 'hex')
        self.preferred_alpha_format = ch_settings.get('preferred_alpha_format', 'rgba')
        self.target_color = target_color
        try:
            self.web_color = webcolors.hex_to_name(target_color) if self.use_web_colors else None
        except:
            self.web_color = None

    def replacement(self, m):
        """ See if match is a replacement of an existing color """
        found = True
        if m.group('hex'):
            self.region = sublime.Region(m.start('hex') + self.start, m.end('hex') + self.start)
            if self.preferred_format in ('rgb', 'hsl'):
                self.format_override = True
                if self.preferred_format == 'rgb':
                    self.convert_rgb = True
                else:
                    self.convert_hsl = True
        elif m.group('rgb'):
            if self.web_color:
                self.region = sublime.Region(m.start('rgb') + self.start, m.end('rgb') + self.start)
            else:
                if self.preferred_format in ('hex', 'hsl'):
                    self.format_override = True
                    self.region = sublime.Region(m.start('rgb') + self.start, m.end('rgb') + self.start)
                    if self.preferred_format == 'hsl':
                        self.convert_hsl = True
                else:
                    self.region = sublime.Region(m.start('rgb_content') + self.start, m.end('rgb_content') + self.start)
                    self.convert_rgb = True
        elif m.group('rgba'):
            self.web_color = None
            if self.preferred_alpha_format == 'hsla':
                self.format_override = True
                self.region = sublime.Region(m.start('rgba') + self.start, m.end('rgba') + self.start)
                self.convert_hsl = True
            else:
                self.region = sublime.Region(m.start('rgba_content') + self.start, m.end('rgba_content') + self.start)
                self.convert_rgb = True
            content = [x.strip() for x in m.group('rgba_content').split(',')]
            self.alpha = content[3]
        elif m.group('hsl'):
            if self.web_color:
                self.region = sublime.Region(m.start('hsl') + self.start, m.end('hsl') + self.start)
            else:
                if self.preferred_format in ('hex', 'rgb'):
                    self.format_override = True
                    self.region = sublime.Region(m.start('hsl') + self.start, m.end('hsl') + self.start)
                    if self.preferred_format == 'rgb':
                        self.convert_rgb = True
                self.region = sublime.Region(m.start('hsl_content') + self.start, m.end('hsl_content') + self.start)
                self.convert_hsl = True
        elif m.group('hsla'):
            self.web_color = None
            if self.preferred_alpha_format == 'rgba':
                self.format_override = True
                self.region = sublime.Region(m.start('hsla') + self.start, m.end('hsla') + self.start)
                self.convert_rgb = True
            else:
                self.region = sublime.Region(m.start('hsla_content') + self.start, m.end('hsla_content') + self.start)
                self.convert_hsl = True
            content = [x.strip().rstrip('%') for x in m.group('hsla_content').split(',')]
            self.alpha = content[3]
        else:
            found = False
        return found

    def completion(self, m):
        """ See if match is completing an color """
        found = False
        if m.group('hash'):
            self.region = sublime.Region(m.start('hash') + self.start, m.end('hash') + self.start)
            if self.preferred_format in ('rgb', 'hsl'):
                self.format_override = True
                if self.preferred_format == 'rgb':
                    self.convert_rgb = True
                else:
                    self.convert_hsl = True
        elif m.group('rgb_open'):
            offset = 1 if self.view.substr(self.point) == ')' else 0
            if self.web_color:
                self.region = sublime.Region(m.start('rgb_open') + self.start, m.end('rgb_open') + self.start + offset)
            elif self.preferred_format in ('hex', 'hsl'):
                    self.format_override = True
                    self.region = sublime.Region(m.start('rgb_open') + self.start, m.end('rgb_open') + self.start + offset)
                    if self.preferred_format == 'hsl':
                        self.convert_hsl = True
            else:
                self.convert_rgb = True
        elif m.group('rgba_open'):
            offset = 1 if self.view.substr(self.point) == ')' else 0
            if self.preferred_alpha_format == 'hsla':
                self.format_override = True
                self.region = sublime.Region(m.start('rgba_open') + self.start, m.end('rgb_open') + self.start + offset)
                self.convert_hsl = True
            else:
                self.convert_rgb = True
            self.alpha = '1'
        elif m.group('hsl_open'):
            offset = 1 if self.view.substr(self.point) == ')' else 0
            if self.web_color:
                self.region = sublime.Region(m.start('hsl_open') + self.start, m.end('hsl_open') + self.start + offset)
            elif self.preferred_format in ('hex', 'rgb'):
                self.format_override = True
                self.region = sublime.Region(m.start('hsl_open') + self.start, m.end('hsl_open') + self.start + offset)
                if self.preferred_format == 'rgb':
                    self.convert_rgb = True
            else:
                self.convert_hsl = True
        elif m.group('hsla_open'):
            self.offset = 1 if self.view.substr(self.point) == ')' else 0
            if self.preferred_alpha_format == 'rgba':
                self.format_override = True
                self.region = sublime.Region(m.start('hsla_open') + self.start, m.end('hsla_open') + self.start + offset)
                self.convert_rgb = True
            else:
                self.convert_hsl = True
            self.alpha = '1'
        else:
            found = False
        return found

    def calc(self):
        """ Calculate how we are to insert the target_color """
        bfr = self.view.substr(sublime.Region(self.start, self.end))
        ref = self.point - self.start
        found = False
        for m in COLOR_RE.finditer(bfr):
            if ref >= m.start(0) and ref < m.end(0):
                found = self.replacement(m)
            elif ref == m.end(0):
                found = self.completion(m)
            if found:
                break

        if not found:
            word_region = self.view.word(sublime.Region(self.point))
            word = self.view.substr(word_region)
            try:
                webcolors.name_to_hex(word).lower()
                self.region = word_region
            except:
                pass
        return found


###########################
# Main Code
###########################
class ColorHelperCommand(sublime_plugin.TextCommand):
    def on_navigate(self, href):
        """ Handle link clicks """
        if href.startswith('#'):
            self.insert_color(href)
        elif not href.startswith('__'):
            self.show_colors(href, update=True)
        elif href == '__close__':
            self.view.hide_popup()
        elif href == '__palettes__':
            self.show_palettes(update=True)
        elif href == '__info__':
            self.show_color_info(update=True)

    def insert_color(self, target_color):
        """ Insert colors """
        sels = self.view.sel()
        if (len(sels) == 1 and sels[0].size() == 0):
            point = sels[0].begin()
            insert_calc = InsertionCalc(self.view, point, target_color)
            insert_calc.calc()
            if insert_calc.web_color:
                value = insert_calc.web_color
            elif insert_calc.convert_rgb:
                value = "%d, %d, %d" % (
                    int(target_color[1:3], 16),
                    int(target_color[3:5], 16),
                    int(target_color[5:7], 16)
                )
                if insert_calc.alpha:
                    value += ', %s' % insert_calc.alpha
                if insert_calc.format_override:
                    value = ("rgba(%s)" if insert_calc.alpha else "rgb(%s)") % value
            elif insert_calc.convert_hsl:
                hsl = RGBA(target_color)
                h, l, s = hsl.tohls()
                value = "%d, %d%%, %d%%" % (
                    int('%.0f' % (h * 360.0)),
                    int('%.0f' % (s * 100.0)),
                    int('%.0f' % (l * 100.0))
                )
                if insert_calc.alpha:
                    value += ', %s' % insert_calc.alpha
                if insert_calc.format_override:
                    value = ("hsla(%s)" if insert_calc.alpha else "hsl(%s)") % value
            else:
                value = target_color
            self.view.sel().subtract(sels[0])
            self.view.sel().add(insert_calc.region)
            self.view.run_command("insert", {"characters": value})
        self.view.hide_popup()

    def format_palettes(self, color_list, label, caption=None):
        """ Format color palette previews """
        colors = ['<h1 class="header">%s</h1>' % label]
        if caption:
            colors.append('<span class="caption">%s</span><br>' % caption)
        colors.append(
            '<a href="%s">%s</a>' % (
                label,
                palette_preview(color_list, border_color)
            )
        )
        return ''.join(colors)

    def format_colors(self, color_list, label):
        """ Format colors under palette """
        colors = ['<h1 class="header">%s</h1>' % label]
        count = 0
        for f in color_list:
            if count != 0 and (count % 8 == 0):
                colors.append('<br><br>')
            elif count != 0:
                if sublime.platform() == 'windows':
                    colors.append('&nbsp; ')
                else:
                    colors.append('&nbsp;')
            colors.append('<a href="%s">%s</a>' % (f, color_box(f, border_color, size=32)))
            count += 1
        return ''.join(colors)

    def format_info(self, color):
        """ Format the selected color info """
        rgba = RGBA(color)

        try:
            web_color = webcolors.hex_to_name(color)
        except:
            web_color = None

        info = ['<h1 class="header">%s</h1>' % color]
        if web_color is not None:
            info.append('<strong>%s</strong><br><br>' % web_color)
        info.append('<a href="__palettes__">%s</a><br><br>' % color_box(color, border_color, size=64))
        info.append(
            '<span class="key">r:</span> %d ' % rgba.r +
            '<span class="key">g:</span> %d ' % rgba.g +
            '<span class="key">b:</span> %d<br>' % rgba.b
        )
        h, s, v = rgba.tohsv()
        info.append(
            '<span class="key">h:</span> %.0f ' % (h * 360.0) +
            '<span class="key">s:</span> %.0f ' % (s * 100.0) +
            '<span class="key">v:</span> %.0f<br>' % (v * 100.0)
        )
        h, l, s = rgba.tohls()
        info.append(
            '<span class="key">h:</span> %.0f ' % (h * 360.0) +
            '<span class="key">s:</span> %.0f ' % (s * 100.0) +
            '<span class="key">l:</span> %.0f<br>' % (l * 100.0)
        )
        return ''.join(info)

    def show_palettes(self, update=False):
        """ Show preview of all palettes """
        html = [
            '<style>%s</style>' % (css if css is not None else '') +
            '<div class="content">'
            # '<a href="__close__"><img style="width: 16px; height: 16px;" src="%s"></a>' % cross
        ]
        if not self.no_info:
            html.append('<a href="__info__"><img style="width: 16px; height: 16px;" src="%s"></a>' % back_arrow)

        bookmark_colors = ch_settings.get("bookmarks", [])
        if len(bookmark_colors):
            bookmarks = [{"name": "Bookmarks", "colors": bookmark_colors}]
        else:
            bookmarks = []

        for palette in (bookmarks + ch_settings.get("palettes", [])):
            html.append(self.format_palettes(palette['colors'], palette['name'], palette.get('caption')))
        html.append('</div>')

        if update:
            self.view.update_popup(''.join(html))
        else:
            self.view.show_popup(
                ''.join(html), location=-1, max_width=600,
                on_navigate=self.on_navigate
            )

    def show_colors(self, palette_name, update=False):
        """ Show colors under the given palette """
        target = None
        for palette in ch_settings.get("palettes", []):
            if palette_name == palette['name']:
                target = palette

        if target is not None:
            html = [
                '<style>%s</style>' % (css if css is not None else '') +
                '<div class="content">' +
                # '<a href="__close__"><img style="width: 16px; height: 16px;" src="%s"></a>' % cross +
                '<a href="__palettes__"><img style="width: 16px; height: 16px;" src="%s"></a>' % back_arrow +
                self.format_colors(target['colors'], target['name']) +
                '</div>'
            ]

            if update:
                self.view.update_popup(''.join(html))
            else:
                self.view.show_popup(
                    ''.join(html), location=-1, max_width=600,
                    on_navigate=self.on_navigate
                )

    def show_color_info(self, update=False):
        """ Show the color under the cursor """

        color = None
        sels = self.view.sel()
        if (len(sels) == 1 and sels[0].size() == 0):
            point = sels[0].begin()
            visible = self.view.visible_region()
            start = point - 50
            end = point + 50
            if start < visible.begin():
                start = visible.begin()
            if end > visible.end():
                end = visible.end()
            bfr = self.view.substr(sublime.Region(start, end))
            ref = point - start
            for m in COLOR_RE.finditer(bfr):
                if ref >= m.start(0) and ref < m.end(0):
                    if m.group('hex'):
                        content = m.group('hex_content')
                        if len(content) == 6:
                            color = "%02x%02x%02x" % (
                                int(content[0:2], 16), int(content[2:4], 16), int(content[4:6], 16)
                            )
                        else:
                            color = "%02x%02x%02x" % (
                                int(content[0:1] * 2, 16), int(content[1:2] * 2, 16), int(content[2:3] * 2, 16)
                            )
                        break
                    elif m.group('rgb'):
                        content = [x.strip() for x in m.group('rgb_content').split(',')]
                        color = "%02x%02x%02x" % (
                            int(content[0]), int(content[1]), int(content[2])
                        )
                        break
                    elif m.group('rgba'):
                        content = [x.strip() for x in m.group('rgba_content').split(',')]
                        color = "%02x%02x%02x%02x" % (
                            int(content[0]), int(content[1]), int(content[2]),
                            int('%.0f' % (float(content[3]) * 255.0))
                        )
                        break
                    elif m.group('hsl'):
                        content = [x.strip().rstrip('%') for x in m.group('hsl_content').split(',')]
                        rgba = RGBA()
                        h = float(content[0]) / 360.0
                        s = float(content[1]) / 100.0
                        l = float(content[2]) / 100.0
                        rgba.fromhls(h, l, s)
                        color = rgba.get_rgb()[1:]
                        break
                    elif m.group('hsla'):
                        content = [x.strip().rstrip('%') for x in m.group('hsla_content').split(',')]
                        rgba = RGBA()
                        h = float(content[0]) / 360.0
                        s = float(content[1]) / 100.0
                        l = float(content[2]) / 100.0
                        rgba.fromhls(h, l, s)
                        color = rgba.get_rgb()[1:]
                        color += "%02X" % int('%.0f' % (float(content[3]) * 255.0))
                        break
            if color is None:
                word = self.view.substr(self.view.word(sels[0]))
                try:
                    color = webcolors.name_to_hex(word).lower()[1:]
                except:
                    pass
        if color is not None:
            html = [
                '<style>%s</style>' % (css if css is not None else '') +
                '<div class="content">' +
                # '<a href="__close__"><img style="width: 16px; height: 16px;" src="%s"></a>' % cross +
                self.format_info('#' + color.lower()) +
                '</div>'
            ]
            if update:
                self.view.update_popup(''.join(html))
            else:
                self.view.show_popup(
                    ''.join(html), location=-1, max_width=600,
                    on_navigate=self.on_navigate
                )
        elif update:
            self.view.hide_popup()

    def run(self, edit, palette_picker=False, palette_name=None):
        """ Run the specified tooltip """
        self.no_info = True
        if palette_name:
            self.show_colors(palette_name)
        elif palette_picker:
            self.show_palettes()
        else:
            self.no_info = False
            self.show_color_info()


###########################
# Threading
###########################
class ColorHelperListener(sublime_plugin.EventListener):
    def on_selection_modified(self, view):
        """ Flag that we need to show a tooltip """
        if ch_thread.ignore_all:
            return
        now = time()
        ch_thread.modified = True
        ch_thread.time = now

    def on_modified(self, view):
        """ Flag that we need to show a tooltip """
        if ch_thread.ignore_all:
            return
        now = time()
        ch_thread.modified = True
        ch_thread.time = now


class ChThread(threading.Thread):
    """ Load up defaults """

    def __init__(self):
        """ Setup the thread """
        self.reset()
        threading.Thread.__init__(self)

    def reset(self):
        """ Reset the thread variables """
        self.wait_time = 0.12
        self.time = time()
        self.modified = False
        self.ignore_all = False
        self.abort = False

    def payload(self):
        """ Code to run """
        self.modified = False
        self.ignore_all = True
        window = sublime.active_window()
        view = window.active_view()
        if view is not None:
            info = False
            execute = False
            sels = view.sel()
            if (
                len(sels) == 1 and sels[0].size() == 0
                and view.score_selector(sels[0].begin(), 'meta.property-value.css')
            ):
                point = sels[0].begin()
                visible = view.visible_region()
                start = point - 50
                end = point + 50
                if start < visible.begin():
                    start = visible.begin()
                if end > visible.end():
                    end = visible.end()
                bfr = view.substr(sublime.Region(start, end))
                ref = point - start
                for m in COLOR_RE.finditer(bfr):
                    if ref >= m.start(0) and ref < m.end(0):
                        if (
                            m.group('hex') or m.group('rgb') or m.group('rgba') or
                            m.group('hsl') or m.group('hsla')
                        ):
                            info = True
                            execute = True
                        break
                    elif ref == m.end(0):
                        if (
                            m.group('hash') or m.group('rgb_open') or m.group('rgba_open') or
                            m.group('hsl_open') or m.group('hsla_open')
                        ):
                            execute = True
                        break
                if not execute:
                    word = view.substr(view.word(sels[0]))
                    try:
                        webcolors.name_to_hex(word)
                        execute = True
                        info = True
                    except:
                        pass
                if execute:
                    view.run_command('color_helper', {"palette_picker": not info})
        self.ignore_all = False
        self.time = time()

    def kill(self):
        """ Kill thread """
        self.abort = True
        while self.is_alive():
            pass
        self.reset()

    def run(self):
        """ Thread loop """
        while not self.abort:
            if self.modified is True and time() - self.time > self.wait_time:
                sublime.set_timeout(lambda: self.payload(), 0)
            sleep(0.5)


###########################
# Plugin Initialization
###########################
def init_css():
    """ Load up desired CSS """
    global css
    global border_color
    global back_arrow
    global cross

    scheme_file = pref_settings.get('color_scheme')
    try:
        lums = scheme_lums(scheme_file)
    except:
        lums = 128

    if lums <= 127:
        css_file = 'Packages/' + ch_settings.get(
            'dark_css_override',
            'ColorHelper/css/dark.css'
        )
        border_color = '#CCCCCC'
        cross = 'res://Packages/ColorHelper/res/cross_dark.png'
        back_arrow = 'res://Packages/ColorHelper/res/back_dark.png'
    else:
        css_file = 'Packages/' + ch_settings.get(
            'light_css_override',
            'ColorHelper/css/light.css'
        )
        border_color = '#333333'
        cross = 'res://Packages/ColorHelper/res/cross_light.png'
        back_arrow = 'res://Packages/ColorHelper/res/back_light.png'

    try:
        css = sublime.load_resource(css_file).replace('\r', '\n')
    except:
        css = None
    ch_settings.clear_on_change('reload')
    ch_settings.add_on_change('reload', init_css)


def init_color_scheme():
    """ Setup color scheme match object with current scheme """
    global pref_settings
    global scheme_matcher
    pref_settings = sublime.load_settings('Preferences.sublime-settings')
    pref_settings.clear_on_change('reload')
    pref_settings.add_on_change('reload', init_color_scheme)

    # Reload the CSS since it can change with scheme luminance
    init_css()


def init_plugin():
    """ Setup plugin variables and objects """
    global ch_settings
    global ch_thread

    # Setup settings
    ch_settings = sublime.load_settings('color_helper.sublime-settings')

    # Setup color scheme
    init_color_scheme()

    if ch_thread is not None:
        ch_thread.kill()
    ch_thread = ChThread()
    ch_thread.start()


def plugin_loaded():
    """ Setup plugin """
    init_plugin()


def plugin_unloaded():
    ch_thread.kill()
