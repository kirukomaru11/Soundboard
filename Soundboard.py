from Utils import *

from gi.repository import Gst

try:
    from gi.repository import Gst
except:
    Gst = False
if not Gst:
    print("GStreamer not found")
    exit()

INFO = {
    "ID": "io.github.kirukomaru11.Soundboard",
    "Developer": "きるこ丸11号",
    "Comment": "Play sounds",
    "Issue URL": "https://github.com/kirukomaru11/Soundboard/issues",
    "Website": "https://github.com/kirukomaru11/Soundboard",
    "Categories": ["Network", "AudioVideo"],
    "Branding": ["#23b866", "#1b8d4e"],
}

class Sound(ListObject):
    __gtype_name__ = "Sound"
    id = GObject.Property(type=int, nick="ID", default=0)
    @GObject.Property(type=str)
    def uri(self): return getattr(self, "_uri", "")

    @uri.setter
    def uri(self, value):
        old_uri = self.uri
        self._uri = value
        if old_uri:
            App.default.data.update(table="Sounds", column="URI", value=value, conditions="URI = ?", conds=(old_uri,))
            Task.invoke(SOUNDS.do_dict)

    name = GObject.Property(type=str)
    hidden = GObject.Property(type=bool, default=False)

    @staticmethod
    def changed(self, p): App.default.data.update(table="Sounds", column=p.get_nick() or p.get_name().replace("-", " ").replace("_", " ").title(), value=getattr(self, p.get_name().replace("-", "_"), None), conditions="URI = ?", conds=(self.uri,))

    def delete(uri):
        if isinstance(uri, Sound):
            uri = uri.uri
        t = SOUNDS[uri]
        if t: SOUNDS.remove(t)
        App.default.data.delete(table="Sounds", conditions="URI = ?", conds=(uri,))
        if Window.current:
            for i in Window.current.box:
                if i.sound == t: i.unparent()

class SoundWidget(Gtk.Button):
    sound = GObject.Property(type=Sound)
    def __init__(self, sound):
        super().__init__()
        self.sound = sound
        self.sound.bind_property("uri", self, "label", DEFAULT_BIND, self.__class__.name_bind)
        self.sound.bind_property("name", self, "label", DEFAULT_BIND, self.__class__.name_bind)

    def do_clicked(self):
        p = Gst.parse_launch(f"uridecodebin3 name=Bin ! audioconvert ! pulsesink device={INFO['ID']}")
        if not hasattr(self.sound, "pipelines"):
            self.sound.pipelines = []
        self.sound.pipelines.append(p)
        Window.current.sync_play()
        p.get_bus().add_signal_watch()
        p.get_bus().connect("message::eos", self.__class__.do_eos, (self.sound, p))
        p.get_by_name("Bin").set_property("uri", uri_relative_encode(self.sound.uri))
        p.set_state(Gst.State.PLAYING)

    @staticmethod
    def do_eos(a, b, d):
        sound, pipeline = d
        if pipeline in sound.pipelines: sound.pipelines.remove(pipeline)
        if Window.current: Task.invoke(Window.current.sync_play)
        Task.invoke(MediaStream.destroy_pipeline, pipeline)

    @staticmethod
    def name_bind(b, v):
        sound = b.get_property("source")
        if not sound: return "None"
        if not sound.name: return basename(sound.uri) if (sound.uri.startswith("file://") or not "://" in sound.uri) else sound.uri
        return sound.name

class Editor(Adw.Dialog):
    sound = GObject.Property(type=Sound)
    def __init__(self, e=None):
        group = Adw.PreferencesGroup()
        page = GroupsPage()
        page.add(group)
        toolbar = Adw.ToolbarView(content=page)
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)
        super().__init__(title=e.uri if e else "New Sound", content_height=264, content_width=360, child=Adw.ToastOverlay(child=toolbar))
        self.sound = e
        self.uri = URIRow(title="URI", multiple=False)
        self.name_row = Adw.EntryRow(title="Name")
        self.hidden = Adw.SwitchRow(title="Hidden")
        if self.sound:
            self.uri.text = self.sound.uri
            self.name_row.set_text(self.sound.name)
            self.hidden.set_active(self.sound.hidden)
            self.uri.connect("notify::text", self.__class__.changed)
            self.name_row.connect("changed", self.__class__.changed)
            self.hidden.connect("notify::active", self.__class__.changed)
            header.pack_start(Button(css_classes=["destructive-action"], icon_name="user-trash", tooltip_text="Delete", callback=self.__class__.delete))
        else:
            header.pack_start(Button(css_classes=["suggested-action"], icon_name="list-add", tooltip_text="Add", callback=self.__class__.add))
        for i in (self.uri, self.name_row, self.hidden): group.add(i)
        self.present(Window.current)

    @staticmethod
    def changed(w, p=None):
        self = w.get_ancestor(Editor)
        if not self or not w.get_mapped(): return
        if w == self.hidden:
            self.sound.hidden = w.get_active()
        if w == self.name_row:
            self.sound.name = w.get_text()
        if w == self.uri:
            if not w.get_text(): return Toast("URI can't be empty")
            if SOUNDS[w.get_text()]: return Toast(f"{w.get_text()} already exists!")
            self.sound.uri = w.get_text()
            self.set_title(self.sound.uri)

    @staticmethod
    def do_actually_delete(d):
        t = SOUNDS[d.editor.get_title()]
        if t: t.delete()
        d.editor.close()
        del d.editor

    @staticmethod
    def delete(b):
        self = b.get_ancestor(Editor)
        if not self: return
        p = Prompt(heading=f"Delete {self.get_title()}?", callback=self.__class__.do_actually_delete)
        p.editor = self
        p.present(self.get_root())

    @staticmethod
    def add(b):
        self = b.get_ancestor(Editor)
        if not self: return
        n = self.uri.get_text()
        if not n: return Toast("Empty URI")
        if App.default.data.exists(table="Sounds", conditions="URI = ?", conds=(n,)): return Toast(f"{n} already exists!")
        v = {"ID": max((i.id for i in SOUNDS), default=0) + 1, "URI": n, "Hidden": self.hidden.get_active(), "Name": self.name_row.get_text()}
        App.default.data.new(table="Sounds", names=tuple(v.keys()), values=tuple(v.values()))
        v = SOUNDS.add(v)
        if Window.current: Window.current.box.append(SoundWidget(v))
        self.close()

class Context(Gtk.PopoverMenu):
    __gtype_name__ = "Context"

    widget = GObject.Property(type=Gtk.Widget)

    def __init__(self): super().__init__(has_arrow=False, width_request=100)

    @staticmethod
    def activate(a, s, window): Context.action(widget=window.context.widget if window.context else window, action=s.unpack().strip("'"))

    @staticmethod
    def action(widget, action=""):
        if action == "Edit" and getattr(widget, "sound"): Editor(widget.sound)

class Window(Window):
    box = GObject.Property(type=Adw.WrapBox)
    no_results_status = GObject.Property(type=Adw.StatusPage)
    empty_status = GObject.Property(type=Adw.StatusPage)
    context = GObject.Property(type=Context)
    search = GObject.Property(type=Gtk.SearchEntry)
    search_button = GObject.Property(type=Gtk.ToggleButton)
    header = GObject.Property(type=Adw.HeaderBar)
    status_button = GObject.Property(type=Gtk.Button)
    sound_widget = GObject.Property(type=SoundWidget)
    drop_target_gtypes = (SoundWidget,)
    def __init__(self):
        sw = Gtk.ScrolledWindow()
        overlay = Gtk.Overlay(child=sw)
        toolbar = Adw.ToolbarView(content=overlay)
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)
        super().__init__(content=toolbar)
        self.set_hide_on_close(True)
        header.pack_start(Button(icon_name="list-add", tooltip_text="Add", callback=self.__class__.add))
        self.status_button = Button(icon_name="media-playback-pause", tooltip_text="Paused", callback=self.__class__.stop_all)
        header.pack_start(self.status_button)
        self.header = header
        self.search = Gtk.SearchEntry(placeholder_text="Search")
        self.search.connect("search-changed", Window.do_filter)
        self.add_action(Gio.SimpleAction.new("context", get_variant("str").get_type()))
        self.lookup_action("context").connect("activate", Context.activate, self)
        header.pack_end(Button(t=Gtk.MenuButton, menu_model=Menu({"!a": Menu({"Show Hidden": "show-hidden"}), "!b": Menu({"Quit": "quit"}), "!c": App.default.default_menu}), icon_name="open-menu", tooltip_text="Menu"))
        self.search_button = Button(t=Gtk.ToggleButton, icon_name="edit-find", tooltip_text="Find", callback=self.__class__.show_search)
        header.pack_end(self.search_button)
        self.box = Adw.WrapBox(child_spacing=6, line_spacing=6)
        self.box.add_css_class("main")
        sw.set_child(self.box)
        self.empty_status = Adw.StatusPage(title="No Sounds", icon_name="audio-speakers-symbolic")
        self.no_results_status = Adw.StatusPage(visible=False, title="No Results", icon_name="edit-find-symbolic")
        overlay.add_overlay(self.empty_status)
        overlay.add_overlay(self.no_results_status)
        self.set_properties(default_width=600, default_height=600)
        self.populate()
        self.do_filter()
        SOUNDS.bind_property("n-items", self.empty_status, "visible", DEFAULT_BIND, invert_bool_bind)
        self.present()

    @staticmethod
    def on_drag_source_prepare(e, x, y):
        w = e.get_widget().pick(x, y, Gtk.PickFlags.DEFAULT)
        e.get_widget().sound_widget = w = w.get_ancestor(SoundWidget) if w else None
        if not w:
            e.set_actions(Gdk.DragAction.NONE)
            return None
        c = Gdk.ContentProvider.new_for_value(w)
        e.set_actions(Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        e.set_content(c)
        return c

    @staticmethod
    def on_drag_source_drag_begin(e, d):
        if e.get_widget().sound_widget: Gtk.DragIcon.get_for_drag(d).set_child(Gtk.Picture(paintable=Gtk.WidgetPaintable.new(e.get_widget().sound_widget)))

    @staticmethod
    def on_drag_source_drag_end(e, d, de):
        if hasattr(e, "set_content"): e.set_content(None)
        e.get_widget().sound_widget = None
        e.get_widget().box.remove_css_class("drag-move")

    @staticmethod
    def on_drop_target_motion(e, x, y):
        box = e.get_widget().box
        if e.get_widget().sound_widget:
            h = e.get_widget().pick(x, y, Gtk.PickFlags.DEFAULT)
            h = h.get_ancestor(SoundWidget) if h else None
            context_widget = e.get_widget().sound_widget
            if h and h != context_widget:
                h = h.get_prev_sibling() or h
                if h == context_widget:
                    h = h.get_next_sibling() or h.get_prev_sibling()
                if h == box.get_first_child():
                    context_widget.unparent()
                    box.prepend(context_widget)
                else: box.reorder_child_after(context_widget, h)
                box.add_css_class("drag-move")
                for n, i in enumerate(box):
                    i.sound.id = n + 1
            return Gdk.DragAction.MOVE
        box.remove_css_class("drag-move")
        return Gdk.DragAction.COPY

    def sync_play(self):
        if any(getattr(i, "pipelines", False) for i in SOUNDS): self.status_button.set_properties(icon_name="media-playback-start-symbolic", tooltip_text="Playing")
        else: self.status_button.set_properties(icon_name="media-playback-pause-symbolic", tooltip_text="Paused")

    @staticmethod
    def stop_all(b):
        if b.get_tooltip_text() != "Playing": return
        for i in SOUNDS:
            for p in getattr(i, "pipelines", []): Task.invoke(SoundWidget.do_eos, None, None, (i, p))

    @staticmethod
    def show_search(b, p=None):
        self = b.get_root()
        self.header.set_title_widget(self.search if b.get_active() else None)
        if b.get_active(): self.search.grab_focus()

    @staticmethod
    def add(b): Editor()

    @staticmethod
    def on_click(*args):
        self, e, n, x, y, signal, b, state = Window.click_to_args(*args)
        if self.context and self.context.get_mapped(): return self.context.popdown()
        w = self.pick(x, y, Gtk.PickFlags.DEFAULT)
        if not w: return
        w = w.get_ancestor(SoundWidget)
        if not w: return
        if b == 3:
            self.context = self.context or Context()
            self.context.widget = w
            self.context.set_menu_model(Menu({"Edit": "win.context::Edit"}))
            self.show_popover_at_widget(self.context, self.get_content(), x, y)

    @staticmethod
    def do_filter(*_):
        self = Window.current
        if not self: return
        s = App.default.lookup_action("show-hidden").get_state().unpack()
        se = self.search.get_text().lower()
        st = not self.empty_status.get_visible()
        for i in self.box:
            if (se and not (se in i.sound.name or se in i.sound.uri)) or (not s and i.sound.hidden): i.set_visible(False)
            else:
                st = False
                i.set_visible(True)
        self.no_results_status.set_visible(st)

    @staticmethod
    def on_key_pressed(e, v, kc, s):
        self = e.get_widget()
        if s == Gdk.ModifierType.CONTROL_MASK and v == Gdk.KEY_f: self.search_button.set_active(not self.search_button.get_active())
        if v == Gdk.KEY_Escape: self.search_button.set_active(False)

    def populate(self):
        for i in SOUNDS: self.box.append(SoundWidget(i))

def activate(a):
    if a.get_active_window(): return a.get_active_window().present()
    DBUS(APP_DBUS, a.get_application_id(), DBUS.path(a.get_application_id()), call)
    unload()
    GLib.spawn_command_line_sync(f"pactl load-module module-null-sink sink_name={INFO['ID']} sink_properties=device.description=\"Soundboard\"")
    GLib.spawn_command_line_sync(f"pactl load-module module-null-sink sink_name={INFO['ID']}.Combined sink_properties=device.description=\"Combined\"")
    GLib.spawn_command_line_sync(f"pactl load-module module-remap-source master={INFO['ID']}.Combined.monitor source_name={INFO['ID']}.Combined source_properties=device.description=\"Combined\"")
    GLib.spawn_command_line_sync(f"pactl load-module module-loopback source={INFO['ID']}.monitor sink=@DEFAULT_SINK@")
    GLib.spawn_command_line_sync(f"pactl load-module module-loopback source={INFO['ID']}.monitor sink={INFO['ID']}.Combined")
    GLib.spawn_command_line_sync(f"pactl load-module module-loopback source=@DEFAULT_SOURCE@ sink={INFO['ID']}.Combined")
    Window()

def unload():
    GLib.spawn_command_line_sync(f"pactl unload-module module-loopback")
    GLib.spawn_command_line_sync(f"pactl unload-module module-remap-source")
    GLib.spawn_command_line_sync(f"pactl unload-module module-null-sink")

def shutdown(a):
    App.default.data.data.close()
    unload()

def id_sort(i): return i.get("ID", 0)

DATA_INIT = """
CREATE TABLE IF NOT EXISTS Sounds('ID' INTEGER, URI TEXT NOT NULL PRIMARY KEY, Name TEXT DEFAULT '', Hidden INTEGER NOT NULL DEFAULT 0);
"""

def call(dbus=None, _c=None, _s=None, _o=None, i="", m="", p=None, inv=None):
    p = p or []
    if i == App.default.get_application_id():
        if m == "Play":
            for n, i in enumerate(Window.current.box):
                if (n + 1) == p[0]: i.emit("clicked")
        if m == "Stop":
            for i in SOUNDS:
                for p in getattr(i, "pipelines", []): Task.invoke(SoundWidget.do_eos, None, None, (i, p))
    return inv.return_value(None) if inv else None

def main():
    App(info=INFO, shortcuts={ "General": { "Find": "<primary>f", "Stop Search": "Escape" } }, data=DATA_INIT, activate=activate, shutdown=shutdown, actions=[("quit", App.quit_default, "<primary>q")])
    Gst.init()
    global APP_DBUS, SOUNDS
    APP_DBUS = { App.default.get_application_id(): {
        "methods": { "Play": { "id": { "direction": "in", "type": "i" } }, "Stop": {} },
     } }
    App.default.add_action(Gio.SimpleAction.new_stateful("show-hidden", None, get_variant(False)))
    App.default.lookup_action("show-hidden").connect("notify::state", Window.do_filter)
    SOUNDS = List(Sound, unique="uri", list=sorted(App.default.data.read(table="Sounds", return_dict=True, force_tuple=True), key=id_sort), static=True)
    App.default.main(css="""
    wrap-box.main { padding: 0px 6px 6px 6px; }
    box.groups { padding: 24px; }
    """)

if __name__ == "__main__": main()