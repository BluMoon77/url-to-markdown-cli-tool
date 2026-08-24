#!/usr/bin/env python3
"""
GTK4/libadwaita front-end for the url-to-md CLI.

This is a wrapper, not a reimplementation: every conversion shells out to the
Node CLI and the GUI only builds the argument list, streams progress, and shows
the result. Defaults deliberately match the CLI's (mobile viewport, 1.5s wait,
images and links kept) so the two never disagree about what a run does.
"""

import os
import shutil
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

APP_ID = "io.github.blumoon77.UrlToMarkdown"

# PROGRESS:<stage> markers emitted by the CLI's --progress flag.
STAGE_LABELS = {
    "launching": "Launching browser…",
    "fetching": "Fetching page…",
    "waiting": "Waiting for content…",
    "extracting": "Extracting HTML…",
    "converting": "Converting to Markdown…",
    "writing": "Writing file…",
    "done": "Done",
}

VIEWPORTS = [
    ("Mobile — 375×667 (default)", "--mobile"),
    ("Tablet — 768×1024", "--tablet"),
    ("Desktop — 1920×1080", "--desktop"),
]


def find_node():
    """Find a node binary.

    PATH alone is not enough: launching from the GNOME app grid gives a process
    that never sourced the user's shell profile, so an nvm-managed node is
    invisible. Fall back to scanning nvm's install root, newest version first.
    """
    node = shutil.which("node")
    if node:
        return node

    nvm_root = Path(os.environ.get("NVM_DIR", Path.home() / ".nvm")) / "versions" / "node"
    if nvm_root.is_dir():
        def version_key(path):
            parts = path.name.lstrip("v").split(".")
            return tuple(int(p) if p.isdigit() else 0 for p in parts)

        for version_dir in sorted(nvm_root.iterdir(), key=version_key, reverse=True):
            candidate = version_dir / "bin" / "node"
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)

    for fallback in ("/usr/local/bin/node", "/usr/bin/node"):
        if os.access(fallback, os.X_OK):
            return fallback

    return None


def find_cli():
    """Locate the CLI: the checkout this file lives in, else url-to-md on PATH.

    Returns an argv prefix, e.g. ['node', '/path/src/index.js'] or ['url-to-md'].
    """
    local = Path(__file__).resolve().parent.parent / "src" / "index.js"
    node = find_node()
    if local.is_file() and node:
        return [node, str(local)]

    installed = shutil.which("url-to-md")
    if installed:
        return [installed]

    return None


def split_tags(text):
    """Parse a tag field. Commas and whitespace both separate."""
    return [tag for tag in text.replace(",", " ").split() if tag]


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("URL to Markdown")
        self.set_default_size(760, 800)

        self.process = None
        self.markdown = ""
        self.stderr_lines = []

        self.toasts = Adw.ToastOverlay()
        self.set_content(self.toasts)

        toolbar = Adw.ToolbarView()
        self.toasts.set_child(toolbar)

        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        self.copy_button = Gtk.Button(icon_name="edit-copy-symbolic")
        self.copy_button.set_tooltip_text("Copy Markdown")
        self.copy_button.set_sensitive(False)
        self.copy_button.connect("clicked", self.on_copy)
        header.pack_end(self.copy_button)

        toolbar.set_content(self.build_body())

    # ---------------------------------------------------------------- layout

    def build_body(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)

        box.append(self.build_options())
        box.append(self.build_actions())
        box.append(self.build_status())
        box.append(Gtk.Separator())
        box.append(self.build_output())
        return box

    def build_options(self):
        group = Adw.PreferencesGroup()

        self.url_row = Adw.EntryRow(title="URL")
        self.url_row.set_activates_default(True)
        self.url_row.connect("entry-activated", lambda _row: self.on_convert(None))
        group.add(self.url_row)

        content = Adw.ExpanderRow(title="Content", subtitle="What to keep from the page")
        group.add(content)

        self.include_row = Adw.EntryRow(title="Include tags")
        self.include_row.set_tooltip_text(
            "Keep only these tags, e.g. article main section. Leave empty for the whole page."
        )
        content.add_row(self.include_row)

        self.remove_row = Adw.EntryRow(title="Remove tags")
        self.remove_row.set_tooltip_text("Drop these tags, e.g. nav footer aside")
        content.add_row(self.remove_row)

        self.clean_row = Adw.SwitchRow(
            title="Clean content",
            subtitle="Drop nav, footer, aside, header, script, style, noscript, canvas",
        )
        content.add_row(self.clean_row)

        self.images_row = Adw.SwitchRow(title="Keep images", active=True)
        content.add_row(self.images_row)

        self.gif_row = Adw.SwitchRow(title="Keep GIF images", active=True)
        content.add_row(self.gif_row)

        self.svg_row = Adw.SwitchRow(title="Keep SVG images", active=True)
        content.add_row(self.svg_row)

        self.links_row = Adw.SwitchRow(title="Keep links", active=True)
        content.add_row(self.links_row)

        browser = Adw.ExpanderRow(title="Browser", subtitle="How the page is rendered")
        group.add(browser)

        self.viewport_row = Adw.ComboRow(
            title="Viewport",
            model=Gtk.StringList.new([label for label, _flag in VIEWPORTS]),
        )
        browser.add_row(self.viewport_row)

        self.wait_row = Adw.SpinRow.new_with_range(0, 60, 0.5)
        self.wait_row.set_title("Wait")
        self.wait_row.set_subtitle("Seconds to let scripts finish loading")
        self.wait_row.set_value(1.5)
        self.wait_row.set_digits(1)
        browser.add_row(self.wait_row)

        self.show_browser_row = Adw.SwitchRow(
            title="Show browser window",
            subtitle="Watch the page load, for debugging",
        )
        browser.add_row(self.show_browser_row)

        self.web_security_row = Adw.SwitchRow(
            title="Disable web security",
            subtitle="Bypasses CORS. Only for pages that refuse to load otherwise",
        )
        browser.add_row(self.web_security_row)

        return group

    def build_actions(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_halign(Gtk.Align.END)

        self.cancel_button = Gtk.Button(label="Cancel")
        self.cancel_button.set_visible(False)
        self.cancel_button.connect("clicked", self.on_cancel)
        box.append(self.cancel_button)

        self.save_button = Gtk.Button(label="Save As…")
        self.save_button.set_sensitive(False)
        self.save_button.connect("clicked", self.on_save)
        box.append(self.save_button)

        self.convert_button = Gtk.Button(label="Convert")
        self.convert_button.add_css_class("suggested-action")
        self.convert_button.connect("clicked", self.on_convert)
        box.append(self.convert_button)

        self.set_default_widget(self.convert_button)
        return box

    def build_status(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_visible(False)

        self.spinner = Gtk.Spinner()
        box.append(self.spinner)

        self.status_label = Gtk.Label(xalign=0)
        self.status_label.add_css_class("dim-label")
        box.append(self.status_label)

        self.status_box = box
        return box

    def build_output(self):
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.output_view = Gtk.TextView(editable=False, monospace=True)
        self.output_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.output_view.set_left_margin(8)
        self.output_view.set_right_margin(8)
        self.output_view.set_top_margin(8)
        scroller.set_child(self.output_view)

        self.output_buffer = self.output_view.get_buffer()
        self.output_buffer.set_text(
            "Enter a URL and press Convert.\n\nThe Markdown will appear here."
        )
        return scroller

    # ------------------------------------------------------------- commands

    def build_argv(self):
        """Translate the form into a CLI argument list."""
        cli = find_cli()
        if cli is None:
            return None, (
                "Could not find the converter.\n\n"
                "Expected src/index.js next to this GUI plus a node binary,\n"
                "or url-to-md on PATH."
            )

        url = self.url_row.get_text().strip()
        if not url:
            return None, "Enter a URL first."
        if "://" not in url:
            url = "https://" + url
            self.url_row.set_text(url)

        argv = cli + [url, "--progress"]
        argv += ["--wait", f"{self.wait_row.get_value():g}"]
        argv.append(VIEWPORTS[self.viewport_row.get_selected()][1])

        include = split_tags(self.include_row.get_text())
        if include:
            argv += ["--include-tags"] + include

        remove = split_tags(self.remove_row.get_text())
        if remove:
            argv += ["--remove-tags"] + remove

        if self.clean_row.get_active():
            argv.append("--clean-content")
        if not self.images_row.get_active():
            argv.append("--no-images")
        if not self.gif_row.get_active():
            argv.append("--no-gif-images")
        if not self.svg_row.get_active():
            argv.append("--no-svg-images")
        if not self.links_row.get_active():
            argv.append("--no-links")
        if self.show_browser_row.get_active():
            argv.append("--show-browser")
        if self.web_security_row.get_active():
            argv.append("--disable-web-security")

        return argv, None

    def on_convert(self, _button):
        if self.process is not None:
            return

        argv, error = self.build_argv()
        if error:
            self.toast(error)
            return

        self.markdown = ""
        self.stderr_lines = []
        self.set_running(True)
        self.set_status("Starting…")
        self.output_buffer.set_text("")

        try:
            self.process = Gio.Subprocess.new(
                argv,
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
            )
        except GLib.Error as exc:
            self.set_running(False)
            self.show_error("Could not start the converter", exc.message)
            return

        self.read_lines(self.process.get_stderr_pipe(), self.on_stderr_line)
        self.read_lines(self.process.get_stdout_pipe(), self.on_stdout_line)
        self.process.wait_async(None, self.on_finished)

    def on_cancel(self, _button):
        if self.process is not None:
            self.process.force_exit()
            self.set_status("Cancelling…")

    # --------------------------------------------------------- async plumbing

    def read_lines(self, pipe, callback):
        """Stream a subprocess pipe line by line without blocking the UI."""
        stream = Gio.DataInputStream.new(pipe)

        def next_line(source, result):
            try:
                line, _length = source.read_line_finish_utf8(result)
            except GLib.Error:
                return
            if line is None:
                return
            callback(line)
            source.read_line_async(GLib.PRIORITY_DEFAULT, None, next_line)

        stream.read_line_async(GLib.PRIORITY_DEFAULT, None, next_line)

    def on_stderr_line(self, line):
        if line.startswith("PROGRESS:"):
            stage = line[len("PROGRESS:"):].strip()
            self.set_status(STAGE_LABELS.get(stage, stage))
        elif line.strip():
            self.stderr_lines.append(line)

    def on_stdout_line(self, line):
        self.markdown += line + "\n"
        end = self.output_buffer.get_end_iter()
        self.output_buffer.insert(end, line + "\n")

    def on_finished(self, process, result):
        try:
            process.wait_finish(result)
            status = process.get_exit_status()
        except GLib.Error as exc:
            status = -1
            self.stderr_lines.append(exc.message)

        self.process = None
        self.set_running(False)

        if status == 0:
            self.set_status("")
            self.copy_button.set_sensitive(bool(self.markdown.strip()))
            self.save_button.set_sensitive(bool(self.markdown.strip()))
            words = len(self.markdown.split())
            self.toast(f"Converted — {words:,} words")
        else:
            self.set_status("")
            detail = "".join(self.stderr_lines).strip() or f"Exited with status {status}."
            self.output_buffer.set_text(detail)
            self.show_error("Conversion failed", detail)

    # ------------------------------------------------------------------ ui

    def set_running(self, running):
        self.convert_button.set_sensitive(not running)
        self.cancel_button.set_visible(running)
        self.status_box.set_visible(running)
        if running:
            self.spinner.start()
            self.copy_button.set_sensitive(False)
            self.save_button.set_sensitive(False)
        else:
            self.spinner.stop()

    def set_status(self, text):
        self.status_label.set_text(text)

    def toast(self, message):
        self.toasts.add_toast(Adw.Toast.new(message))

    def show_error(self, heading, body):
        dialog = Adw.AlertDialog.new(heading, body)
        dialog.add_response("ok", "Close")
        dialog.present(self)

    def on_copy(self, _button):
        self.get_clipboard().set(self.markdown)
        self.toast("Copied to clipboard")

    def on_save(self, _button):
        dialog = Gtk.FileDialog()
        dialog.set_initial_name("page.md")

        def finish(source, result):
            try:
                gfile = source.save_finish(result)
            except GLib.Error:
                return  # cancelled
            try:
                Path(gfile.get_path()).write_text(self.markdown, encoding="utf-8")
                self.toast(f"Saved to {gfile.get_basename()}")
            except OSError as exc:
                self.show_error("Could not save", str(exc))

        dialog.save(self, None, finish)


class Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.window = None

    def do_activate(self):
        self.ensure_window().present()

    def do_open(self, files, n_files, hint):
        """Support `url-to-markdown-gui https://…` and URL handoff from the shell."""
        window = self.ensure_window()
        if files:
            window.url_row.set_text(files[0].get_uri())
        window.present()

    def ensure_window(self):
        if self.window is None:
            self.window = MainWindow(application=self)
        return self.window


def main():
    # Wayland needs this to match the .desktop file and show the right icon/name.
    GLib.set_prgname(APP_ID)
    GLib.set_application_name("URL to Markdown")
    return Application().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
