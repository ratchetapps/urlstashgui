# urlstashgui.py - Modernized with CustomTkinter
import os
import re
import sqlite3
import shutil
import threading
import time
import json
import sys

import customtkinter as ctk
from tkinter import ttk, messagebox, filedialog
import tkinter as tk  # Still needed for some specific widgets

from stashapi.stashapp import StashInterface
from logger_setup import TextHandler, setup_logger
from utils import sanitize_for_windows, remove_dash_number_suffix

# Set CustomTkinter appearance
ctk.set_appearance_mode("system")  # "light", "dark", or "system"
ctk.set_default_color_theme("blue")  # "blue", "green", or "dark-blue"

TARGET_SCENE_COUNT = 10
LOG_FILE_NAME = "urlstashgui.log"
logger = setup_logger("UrlStashGUI", LOG_FILE_NAME)


class ToolTip:
    """Simple tooltip class for CTkLabel widgets"""

    def __init__(self, widget, text="widget info"):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0

        # Bind events
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.widget.bind("<ButtonPress>", self.leave)

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(200, self.showtip)

    def unschedule(self):
        id = self.id
        self.id = None
        if id:
            self.widget.after_cancel(id)

    def showtip(self, event=None):
        if self.tipwindow or not self.text:
            return
        x, y, cx, cy = (
            self.widget.bbox("insert") if hasattr(self.widget, "bbox") else (0, 0, 0, 0)
        )
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20

        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry("+%d+%d" % (x, y))

        label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            font=("tahoma", "9", "normal"),
            wraplength=1200,
        )
        label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

    def update_text(self, new_text):
        self.text = new_text


class UrlStashGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Set light theme only
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        # Configure window
        self.title("urlstashgui - v2.1.0")
        self.geometry("1200x880")
        self.minsize(1200, 880)
        self._set_window_icon()

        """Configure modern styling"""
        style = ttk.Style()

        # Use Windows 10 theme if available
        try:
            style.theme_use("winnative")
        except:
            try:
                style.theme_use("clam")
            except:
                pass

        # Configure button styles
        style.configure("Filter.TButton", padding=(5, 5), font=("Segoe UI", 10))

        style.configure("Active.TButton", padding=(5, 5), font=("Segoe UI", 10, "bold"))

        style.configure("File.TButton", padding=(5, 5), font=("Segoe UI", 11))

        # Sidebar state variables
        self.sidebar_expand = True
        self.log_visible = True
        self.nav_items = ["Scenes", "DB Config", "Settings", "Help"]
        self.active_page = None

        # Configure grid weight
        self.grid_columnconfigure(0, weight=0)  # Sidebar
        self.grid_columnconfigure(1, weight=1)  # Content
        self.grid_rowconfigure(0, weight=0)  # Main area
        self.grid_rowconfigure(1, weight=1)  # Log section (resizable)

        # Threading and state variables
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.stop_event = threading.Event()
        self.processing_thread = None
        self.all_checked = False
        self.scenes = []

        # Track Stash connectivity and dependent button state
        self.stash_connected = False
        self.accept_in_progress = False
        self.connection_dependent_buttons = []

        self.scene_url_candidates = []  # Store all URL candidates for tooltips
        self.url_tooltips = []  # Store tooltip objects

        # Session tracking for database sync
        self.synced_this_session = False
        self.sync_prompt_shown = False

        # Create the modern UI
        self.create_modern_widgets()

        # Load configuration after widgets are created
        self.load_json_config()

        # Ensure URL replacements exist
        if not hasattr(self, "url_replacements") or self.url_replacements is None:
            self.url_replacements = [
                {"url_text": "spankbang.party", "replace_with": "spankbang.com"}
            ]

        # Set up logging
        self.setup_logging()

        # Initialize scene ID
        self.initialize_scene_id()

    def _get_runtime_base_dir(self):
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            return sys._MEIPASS
        return os.path.dirname(os.path.abspath(__file__))

    def _get_persistent_base_dir(self):
        if getattr(sys, "frozen", False):
            return os.path.dirname(os.path.abspath(sys.executable))
        return os.path.dirname(os.path.abspath(__file__))

    def _set_window_icon(self):
        icon_path = os.path.join(
            self._get_runtime_base_dir(),
            "img",
            "urlstashgui.ico",
        )
        if not os.path.exists(icon_path):
            return
        try:
            self.iconbitmap(icon_path)
        except Exception as e:
            logger.warning(f"Could not set window icon from '{icon_path}': {e}")

    def create_modern_widgets(self):
        """Create the modern CustomTkinter interface with sidebar navigation"""

        # === SIDEBAR ===
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0, fg_color="#108cff")
        self.sidebar_frame.grid(row=0, column=0, rowspan=2, sticky="ns")
        self.sidebar_frame.grid_propagate(False)

        # === MAIN CONTENT AREA ===
        self.content_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#ecf0f1")
        self.content_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)

        # === LOG SECTION ===
        self.log_section = ctk.CTkFrame(self, corner_radius=10, height=180)
        self.log_section.grid(row=1, column=1, sticky="nsew", padx=10, pady=(5, 10))
        self.log_section.grid_columnconfigure(0, weight=1)
        self.log_section.grid_rowconfigure(1, weight=1)
        self.log_section.grid_propagate(False)  # Prevent resizing based on content

        # Create log widgets
        self.create_log_section()

        # Create sidebar widgets
        self.create_sidebar()

        # Initialize StringVar widgets that will be used across pages
        self.initialize_variables()

        # Default page
        self.show_page("Scenes")

    def initialize_variables(self):
        """Initialize all tk variables needed across pages"""
        self.scheme_var = tk.StringVar(value="")
        self.host_var = tk.StringVar(value="")
        self.port_var = tk.StringVar(value="")
        self.apikey_var = tk.StringVar(value="")
        self.start_id_var = tk.StringVar()
        self.skip_organized_var = tk.BooleanVar(value=True)
        self.auto_accept_var = tk.BooleanVar(value=False)
        self.threshold_var = tk.StringVar(value="3")

        # Scene row widgets
        self.scene_row_frames = []
        self.scene_num_labels = []
        self.checkbox_vars = []
        self.diff_labels = []
        self.url_labels = []

    def create_sidebar(self):
        """Create sidebar navigation"""
        # Nav buttons
        self.nav_buttons = []
        for text in self.nav_items:
            btn = ctk.CTkButton(
                self.sidebar_frame,
                text=text,
                width=180,
                height=40,
                corner_radius=0,
                fg_color="#108cff",
                hover_color="#0869c7",
                font=ctk.CTkFont(size=18, weight="bold"),
                command=lambda t=text: self.show_page(t),
            )
            btn.pack(pady=5, padx=10, fill="x", anchor="w")
            self.nav_buttons.append(btn)

        # Spacer to push bottom buttons down
        spacer = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        # Open Dir button
        self.open_dir_button = ctk.CTkButton(
            self.sidebar_frame,
            text="📁 Open Dir",
            width=180,
            height=35,
            corner_radius=0,
            fg_color="#034787",
            hover_color="#023056",
            font=ctk.CTkFont(size=12),
            command=self.open_local_directory,
        )
        self.open_dir_button.pack(pady=5, padx=10, fill="x", anchor="w", side="bottom")

    def create_log_section(self):
        """Create the log output section"""
        self.log_header = ctk.CTkLabel(
            self.log_section,
            text="Log",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.log_header.grid(row=0, column=0, sticky="w", padx=15, pady=(4, 2))

        # Log text widget
        self.log_text = tk.Text(
            self.log_section,
            state="disabled",
            wrap=tk.WORD,
            bg="#F5F5F5",
            fg="#000000",
            font=("Consolas", 10),
            relief="flat",
            borderwidth=0,
        )
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 15))

        # Configure log text tags
        self.log_text.tag_config(
            "match_found", foreground="#2E7D32", font=("Consolas", 10, "bold")
        )
        self.log_text.tag_config(
            "update_complete", foreground="#1565C0", font=("Consolas", 10, "bold")
        )
        self.log_text.tag_config(
            "file_error", foreground="#C62828", font=("Consolas", 10, "bold")
        )

        # Add scrollbar
        scrollbar = ctk.CTkScrollbar(self.log_section, command=self.log_text.yview)
        scrollbar.grid(row=1, column=1, sticky="ns", pady=(0, 15), padx=(0, 10))
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def show_page(self, name: str):
        """Show the selected page"""
        if name == "Scenes":
            self.grid_rowconfigure(0, weight=0)
            self.grid_rowconfigure(1, weight=1)
        else:
            self.grid_rowconfigure(0, weight=1)
            self.grid_rowconfigure(1, weight=0)

        # Update active page highlighting
        for idx, item in enumerate(self.nav_items):
            if item == name:
                # Highlight active button with darker background
                self.nav_buttons[idx].configure(fg_color="#034787")
                self.active_page = name
            else:
                # Reset inactive buttons to default color
                self.nav_buttons[idx].configure(fg_color="#108cff")

        # Clear content
        for w in self.content_frame.winfo_children():
            self._cleanup_widget_before_destroy(w)
            w.destroy()

        if name == "Scenes":
            self.show_scenes_page()
        elif name == "Settings":
            self.show_settings_page()
        elif name == "DB Config":
            self.show_db_config_page()
        elif name == "Help":
            self.show_help_page()
        else:
            # Simple placeholder for other pages
            ctk.CTkLabel(
                self.content_frame,
                text=f"{name} page",
                font=ctk.CTkFont(size=24),
            ).pack(expand=True)

    def _iter_widget_tree(self, widget):
        """Yield a widget and all descendants."""
        try:
            yield widget
            for child in widget.winfo_children():
                yield from self._iter_widget_tree(child)
        except Exception:
            return

    def _cleanup_widget_before_destroy(self, root_widget):
        """Detach CTkEntry textvariables safely to avoid stale trace callbacks."""
        for widget in self._iter_widget_tree(root_widget):
            if isinstance(widget, ctk.CTkEntry):
                try:
                    text_var = getattr(widget, "_textvariable", None)
                    trace_name = getattr(widget, "_textvariable_callback_name", "")

                    # Remove the write trace installed by CTkEntry __init__ before detaching.
                    if text_var is not None and trace_name:
                        try:
                            text_var.trace_remove("write", trace_name)
                        except Exception:
                            pass
                        try:
                            widget._textvariable_callback_name = ""
                        except Exception:
                            pass

                    # Rebind to an isolated variable so the shared app variable no longer points
                    # at this soon-to-be-destroyed widget.
                    widget.configure(textvariable=tk.StringVar(value=widget.get()))
                except Exception:
                    pass

    def show_scenes_page(self):
        """Display the scene URL matching page (old top_frame + middle_frame content)"""
        # Main container
        container = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        container.pack(fill="x", expand=False, padx=20, pady=20)

        # === TOP CONTROL FRAME ===
        self.top_frame = ctk.CTkFrame(container, corner_radius=10)
        self.top_frame.pack(fill="x", pady=(0, 10))
        self.top_frame.grid_columnconfigure(0, weight=1)

        # Row 1: Scene ID controls
        self.scene_controls_frame = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self.scene_controls_frame.pack(fill="x", padx=10, pady=10)
        self.scene_controls_frame.grid_columnconfigure(0, minsize=140)
        self.scene_controls_frame.grid_columnconfigure(1, minsize=220)
        self.scene_controls_frame.grid_columnconfigure(2, minsize=180)
        self.scene_controls_frame.grid_columnconfigure(3, minsize=160)
        self.scene_controls_frame.grid_columnconfigure(4, minsize=140)
        self.scene_controls_frame.grid_columnconfigure(5, weight=1)

        self.load_button = ctk.CTkButton(
            self.scene_controls_frame,
            text="Start",
            command=self.load_scenes,
            width=140,
            fg_color="blue",
        )
        self.load_button.grid(row=0, column=0, padx=(0, 10), pady=4)

        start_group = ctk.CTkFrame(self.scene_controls_frame, fg_color="transparent")
        start_group.grid(row=0, column=1, sticky="w", padx=(0, 10), pady=4)
        ctk.CTkLabel(
            start_group, text="Start Scene ID:", font=ctk.CTkFont(weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.start_id_entry = ctk.CTkEntry(
            start_group, textvariable=self.start_id_var, width=80
        )
        self.start_id_entry.grid(row=0, column=1, sticky="w")

        self.end_id_label = ctk.CTkLabel(
            self.scene_controls_frame,
            text="End Scene ID: Unknown",
            text_color="blue",
            width=180,
            anchor="w",
        )
        self.end_id_label.grid(row=0, column=2, sticky="w", padx=(10, 0), pady=4)

        self.skip_organized_check = ctk.CTkCheckBox(
            self.scene_controls_frame,
            text="Skip Organized",
            variable=self.skip_organized_var,
            width=160,
        )
        self.skip_organized_check.grid(row=0, column=3, padx=(20, 6), pady=4)

        self.auto_accept_check = ctk.CTkCheckBox(
            self.scene_controls_frame,
            text="Auto-Accept",
            variable=self.auto_accept_var,
            width=140,
        )
        self.auto_accept_check.grid(row=0, column=4, padx=(6, 6), pady=4, sticky="w")

        # Add tooltips for scene controls
        ToolTip(
            self.start_id_entry,
            "Scene ID to start scanning from (leave blank for scene 1)",
        )
        ToolTip(
            self.skip_organized_check,
            "Skip scenes that are already organized in StashApp",
        )
        ToolTip(
            self.auto_accept_check,
            "Automatically accept and update URLs after all scenes are found",
        )


        # Row 2: Action buttons
        self.action_frame = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self.action_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.action_frame.grid_columnconfigure(1, minsize=160)
        self.action_frame.grid_columnconfigure(2, minsize=130)
        self.action_frame.grid_columnconfigure(3, minsize=170)
        self.action_frame.grid_columnconfigure(4, weight=1)

        self.accept_button = ctk.CTkButton(
            self.action_frame,
            text="Accept",
            command=self.accept_candidates,
            width=150,
            fg_color="green",
            state="disabled",
            hover=False,
        )
        self.accept_button.grid(row=0, column=1, padx=6, pady=5, sticky="w")

        self.stop_verify_button = ctk.CTkButton(
            self.action_frame,
            text="Stop",
            command=self.stop_and_verify_scenes,
            width=120,
            fg_color="gray",
            state="disabled",
            hover=False,
        )
        self.stop_verify_button.grid(row=0, column=2, padx=6, pady=5, sticky="w")

        self.toggle_check_button = ctk.CTkButton(
            self.action_frame,
            text="Check/Uncheck All",
            command=self.toggle_check_all,
            width=170,
            fg_color="blue",
            state="disabled",
            hover=False,
        )
        self.toggle_check_button.grid(row=0, column=3, padx=6, pady=5, sticky="w")

        # Keep a handle to all buttons that depend on a confirmed Stash connection
        self.connection_dependent_buttons = [
            self.accept_button,
            self.stop_verify_button,
            self.toggle_check_button,
        ]
        self._refresh_connection_dependent_buttons()

        # Threshold controls moved next to action buttons
        threshold_group = ctk.CTkFrame(
            self.action_frame, fg_color="transparent"
        )
        threshold_group.grid(row=0, column=5, sticky="e", padx=(10, 0), pady=5)

        ctk.CTkLabel(
            threshold_group,
            text="Auto-check Threshold:",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.threshold_entry = ctk.CTkEntry(
            threshold_group, textvariable=self.threshold_var, width=60
        )
        self.threshold_entry.grid(row=0, column=1, sticky="w")

        threshold_spin_frame = ctk.CTkFrame(threshold_group, fg_color="transparent")
        threshold_spin_frame.grid(row=0, column=2, padx=(6, 2))

        self.threshold_up_btn = ctk.CTkButton(
            threshold_spin_frame,
            text="▲",
            width=25,
            height=20,
            command=self.increment_threshold,
            fg_color="gray",
        )
        self.threshold_up_btn.pack(side="top", pady=(0, 2))

        self.threshold_down_btn = ctk.CTkButton(
            threshold_spin_frame,
            text="▼",
            width=25,
            height=20,
            command=self.decrement_threshold,
            fg_color="gray",
        )
        self.threshold_down_btn.pack(side="top")

        # Add tooltips for buttons
        ToolTip(self.threshold_entry, "Only check scenes with fewer matched URLs than threshold")
        ToolTip(self.load_button, "Start loading scenes from StashApp and find URL matches")
        ToolTip(self.accept_button, "Update selected scenes with matched URLs")
        ToolTip(
            self.stop_verify_button, "Stop current operation and verify loaded scenes"
        )
        ToolTip(self.toggle_check_button, "Toggle selection of all loaded scenes")

        # Row 1: Status and Progress
        self.status_label = ctk.CTkLabel(
            self.action_frame,
            text="Ready",
            font=ctk.CTkFont(weight="bold"),
            text_color="green",
        )
        self.status_label.grid(row=1, column=0, columnspan=2, padx=6, pady=5, sticky="w")

        self.progress_bar = ctk.CTkProgressBar(self.action_frame, width=200)
        self.progress_bar.grid(row=1, column=2, columnspan=2, padx=6, pady=5, sticky="w")
        self.progress_bar.set(0)

        # === SCENE ROWS FRAME ===
        self.middle_frame_outer = ctk.CTkFrame(container, corner_radius=5)
        self.middle_frame_outer.pack(fill="x", expand=False, pady=(1, 1))
        self.middle_frame_outer.grid_columnconfigure(0, weight=1)
        self.middle_frame_outer.grid_rowconfigure(0, weight=1)

        self.middle_canvas = tk.Canvas(
            self.middle_frame_outer,
            height=460,
            bg="#dbdbdb",
            borderwidth=1,
            highlightthickness=1,
            relief="flat",
        )
        self.middle_canvas.grid(row=0, column=0, sticky="ew", padx=1, pady=(1, 0))

        self.middle_x_scrollbar = ctk.CTkScrollbar(
            self.middle_frame_outer,
            orientation="horizontal",
            command=self.middle_canvas.xview,
        )
        self.middle_x_scrollbar.grid(row=1, column=0, sticky="ew", padx=8, pady=(2,2))
        self.middle_canvas.configure(xscrollcommand=self.middle_x_scrollbar.set)

        self.middle_frame = ctk.CTkFrame(self.middle_canvas, fg_color="transparent")
        self.middle_frame.grid_columnconfigure(0, weight=1)
        self.middle_canvas_window = self.middle_canvas.create_window(
            (0, 0), window=self.middle_frame, anchor="nw"
        )
        self.middle_frame.bind("<Configure>", self._refresh_scene_canvas_scrollregion)
        self.middle_canvas.bind("<Configure>", self._resize_scene_canvas_window)

        # Scene rows
        self.scene_row_frames = []
        self.scene_num_labels = []
        self.checkbox_vars = []
        self.diff_labels = []
        self.url_labels = []
        self.url_tooltips = []

        import tkinter.font as tkFont

        # Choose a fixed-width font so "60 chars" maps evenly to pixels
        font = tkFont.Font(family="Consolas", size=11)

        # Measure pixel width of 60 characters
        px_for_60 = font.measure("0" * 60)
        for i in range(TARGET_SCENE_COUNT):
            # Create row frame with alternating background
            row_color = ("#E8E8E8", "#E8E8E8") if i % 2 == 0 else ("#F5F5F5", "#F5F5F5")
            row_frame = ctk.CTkFrame(
                self.middle_frame, corner_radius=0, height=45, fg_color=row_color
            )
            row_frame.grid(row=i, column=0, sticky="ew", padx=0, pady=0)
            row_frame.grid_propagate(False)

            # Configure columns
            row_frame.grid_columnconfigure(0, weight=0, minsize=50)  # Checkbox
            row_frame.grid_columnconfigure(1, weight=0, minsize=100)  # Scene number
            row_frame.grid_columnconfigure(2, weight=0, minsize=px_for_60)  # Diff info
            row_frame.grid_columnconfigure(3, weight=1)  # URL

            # Center content vertically
            row_frame.grid_rowconfigure(0, weight=1)

            # Checkbox
            checkbox_var = tk.BooleanVar(value=True)
            checkbox = ctk.CTkCheckBox(
                row_frame, text="", variable=checkbox_var, width=30
            )
            checkbox.grid(row=0, column=0, padx=(15, 5), sticky="w")

            # Scene label
            scene_label = ctk.CTkLabel(
                row_frame, text="Scene NA", font=ctk.CTkFont(weight="bold"), anchor="w"
            )
            scene_label.grid(row=0, column=1, padx=5, sticky="w")

            # Diff label
            diff_label = ctk.CTkLabel(
                row_frame,
                text="N/A\nN/A",
                font=ctk.CTkFont(size=12),
                anchor="w",
                justify="left",
            )
            diff_label.grid(row=0, column=2, padx=5, sticky="w")
            diff_label.configure(width=0)

            # URL label
            url_label = ctk.CTkLabel(
                master=row_frame,
                text="No URL",
                width=200,
                justify="left",
                font=ctk.CTkFont(size=12),
                anchor="w",
            )
            url_label.grid(row=0, column=3, padx=5, sticky="we")

            self.scene_row_frames.append(row_frame)
            self.checkbox_vars.append(checkbox_var)
            self.scene_num_labels.append(scene_label)
            self.diff_labels.append(diff_label)
            self.url_labels.append(url_label)
            tooltip = ToolTip(url_label, "No URLs available")
            self.url_tooltips.append(tooltip)

    def _refresh_scene_canvas_scrollregion(self, event=None):
        if not hasattr(self, "middle_canvas"):
            return
        self.middle_canvas.configure(scrollregion=self.middle_canvas.bbox("all"))
        self._resize_scene_canvas_window()

    def _resize_scene_canvas_window(self, event=None):
        if not hasattr(self, "middle_canvas") or not hasattr(self, "middle_canvas_window"):
            return

        canvas_width = event.width if event else self.middle_canvas.winfo_width()
        requested_width = self.middle_frame.winfo_reqwidth()
        self.middle_canvas.itemconfigure(
            self.middle_canvas_window,
            width=max(canvas_width, requested_width),
        )

    def show_settings_page(self):
        """Display the settings page"""
        # Main container with padding
        container = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=30, pady=30)

        # Title
        title = ctk.CTkLabel(
            container,
            text="Connection Settings",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title.pack(anchor="w", pady=(0, 20))

        # Settings frame with clean white background
        settings_frame = ctk.CTkFrame(container, corner_radius=10, fg_color="white")
        settings_frame.pack(fill="x", pady=10)

        # Add padding inside settings frame
        inner_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        inner_frame.pack(fill="both", expand=True, padx=25, pady=25)

        # Scheme field
        self.create_setting_field(
            inner_frame,
            "Scheme:",
            self.scheme_var,
            0,
            placeholder_text="http",
            style_placeholder_hint=True,
        )

        # Host field
        self.create_setting_field(
            inner_frame,
            "Host:",
            self.host_var,
            1,
            placeholder_text="localhost",
            style_placeholder_hint=True,
        )

        # Port field
        self.create_setting_field(
            inner_frame,
            "Port:",
            self.port_var,
            2,
            placeholder_text="9999",
            style_placeholder_hint=True,
        )

        # API Key field (with password style)
        self.create_setting_field(inner_frame, "API Key:", self.apikey_var, 3, show="*")

        # Auto-Accept checkbox (row 4)
        auto_accept_frame = ctk.CTkFrame(inner_frame, fg_color="transparent")
        auto_accept_frame.grid(row=4, column=0, columnspan=2, sticky="w", pady=10)

        ctk.CTkCheckBox(
            auto_accept_frame,
            text="✓ Auto-Accept URLs after loading scenes",
            variable=self.auto_accept_var,
        ).pack(anchor="w")

        # Skip Organized checkbox (row 5)
        skip_org_frame = ctk.CTkFrame(inner_frame, fg_color="transparent")
        skip_org_frame.grid(row=5, column=0, columnspan=2, sticky="w", pady=10)

        ctk.CTkCheckBox(
            skip_org_frame,
            text="⏭ Skip Organized Scenes",
            variable=self.skip_organized_var,
        ).pack(anchor="w")

        # Auto-Startup checkbox (row 6)
        if not hasattr(self, 'auto_startup_var'):
            self.auto_startup_var = tk.BooleanVar(value=self.auto_startup if hasattr(self, 'auto_startup') else False)

        auto_startup_frame = ctk.CTkFrame(inner_frame, fg_color="transparent")
        auto_startup_frame.grid(row=6, column=0, columnspan=2, sticky="w", pady=10)

        ctk.CTkCheckBox(
            auto_startup_frame,
            text="🚀 Auto-Startup: Sync DB and Find Matches on Launch",
            variable=self.auto_startup_var,
        ).pack(anchor="w")

        # Auto-check Threshold (row 7)
        threshold_frame = ctk.CTkFrame(inner_frame, fg_color="transparent")
        threshold_frame.grid(row=7, column=0, columnspan=2, sticky="ew", pady=10)

        ctk.CTkLabel(
            threshold_frame,
            text="Auto-check Threshold:",
            font=ctk.CTkFont(weight="bold"),
        ).pack(side="left", padx=(0, 10))

        ctk.CTkEntry(
            threshold_frame,
            textvariable=self.threshold_var,
            width=100,
        ).pack(side="left", padx=5)

        # Spinner buttons
        ctk.CTkButton(
            threshold_frame,
            text="▲",
            width=30,
            command=self.increment_threshold,
            fg_color="gray",
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            threshold_frame,
            text="▼",
            width=30,
            command=self.decrement_threshold,
            fg_color="gray",
        ).pack(side="left", padx=2)

        # Help text
        ctk.CTkLabel(
            threshold_frame,
            text="(0 = check all, >0 = check only if match count < threshold)",
            text_color="gray",
        ).pack(side="left", padx=10)

        # Action buttons
        action_buttons = ctk.CTkFrame(container, fg_color="transparent")
        action_buttons.pack(anchor="w", pady=(20, 0))

        save_btn = ctk.CTkButton(
            action_buttons,
            text="Save Settings",
            fg_color="blue",
            command=self.save_settings,
            width=150,
        )
        save_btn.pack(side="left")

        default_btn = ctk.CTkButton(
            action_buttons,
            text="Default Connection",
            fg_color="#6c757d",
            hover_color="#5a6268",
            command=self.reset_settings_to_defaults,
            width=170,
        )
        default_btn.pack(side="left", padx=(10, 0))

    def create_setting_field(
        self,
        parent,
        label_text,
        text_var,
        row,
        show=None,
        placeholder_text=None,
        style_placeholder_hint=False,
    ):
        """Helper to create a labeled setting field"""
        ctk.CTkLabel(
            parent,
            text=label_text,
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=row, column=0, sticky="w", pady=10, padx=(0, 10))

        entry_kwargs = {"textvariable": text_var, "width": 300}
        if show:
            entry_kwargs["show"] = show
        if placeholder_text:
            entry_kwargs["placeholder_text"] = placeholder_text
            # Hint text is typically easier to parse in a muted color.
            entry_kwargs["placeholder_text_color"] = "#7a7a7a"

        entry = ctk.CTkEntry(parent, **entry_kwargs)
        entry.grid(
            row=row, column=1, sticky="ew", pady=10
        )
        if style_placeholder_hint and placeholder_text:
            self._apply_placeholder_hint_font(entry, text_var)

    def _apply_placeholder_hint_font(self, entry, text_var):
        """Use italic font when placeholder hint is visible for empty entry fields."""
        normal_font = ctk.CTkFont(size=13)
        hint_font = ctk.CTkFont(size=13, slant="italic")

        def sync_font():
            try:
                is_empty = str(text_var.get()).strip() == ""
                has_focus = self.focus_get() == entry
                entry.configure(font=hint_font if is_empty and not has_focus else normal_font)
            except Exception:
                pass

        entry.bind("<FocusIn>", lambda _e: sync_font(), add="+")
        entry.bind("<FocusOut>", lambda _e: self.after(1, sync_font), add="+")
        entry.bind("<KeyRelease>", lambda _e: sync_font(), add="+")
        sync_font()

    def save_settings(self):
        """Save current settings to config"""
        try:
            # Update auto_startup from UI variable
            if hasattr(self, 'auto_startup_var'):
                self.auto_startup = self.auto_startup_var.get()

            last_scene = self.lastsceneID if hasattr(self, "lastsceneID") else 1
            last_max = self.lastmaxID if hasattr(self, "lastmaxID") else 0
            self.write_json_config(last_scene, last_max)
            messagebox.showinfo(
                "Settings Saved", "Settings have been saved successfully!"
            )
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            messagebox.showerror("Error", f"Failed to save settings: {e}")

    def reset_settings_to_defaults(self):
        """Reset settings-page controls to app defaults and persist immediately."""
        try:
            defaults = {
                "scheme": "http",
                "host": "localhost",
                "port": "9999",
                "apikey": "",
                "auto_check_threshold": "3",
                "auto_accept": False,
                "skip_organized": True,
                "auto_startup": False,
            }

            if hasattr(self, "scheme_var"):
                self.scheme_var.set(defaults["scheme"])
            if hasattr(self, "host_var"):
                self.host_var.set(defaults["host"])
            if hasattr(self, "port_var"):
                self.port_var.set(defaults["port"])
            if hasattr(self, "apikey_var"):
                self.apikey_var.set(defaults["apikey"])
            if hasattr(self, "threshold_var"):
                self.threshold_var.set(defaults["auto_check_threshold"])
            if hasattr(self, "auto_accept_var"):
                self.auto_accept_var.set(defaults["auto_accept"])
            if hasattr(self, "skip_organized_var"):
                self.skip_organized_var.set(defaults["skip_organized"])
            if hasattr(self, "auto_startup_var"):
                self.auto_startup_var.set(defaults["auto_startup"])

            self.auto_startup = defaults["auto_startup"]

            last_scene = self.lastsceneID if hasattr(self, "lastsceneID") else 1
            last_max = self.lastmaxID if hasattr(self, "lastmaxID") else "Unknown"
            self.write_json_config(last_scene, last_max)

            logger.info("Settings reset to defaults and saved.")
            messagebox.showinfo(
                "Defaults Restored",
                "Connection and matching settings were reset to defaults.",
            )
        except Exception as e:
            logger.error(f"Error resetting settings to defaults: {e}", exc_info=True)
            messagebox.showerror("Error", f"Failed to restore defaults: {e}")

    def show_db_config_page(self):
        """Display the database configuration page"""
        # Main container
        container = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)

        # Title row with Sync and Apply button
        title_row = ctk.CTkFrame(container, fg_color="transparent")
        title_row.pack(fill="x", pady=(0, 15))

        title = ctk.CTkLabel(
            title_row,
            text="Database Configuration",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title.pack(side="left")

        # Sync and Apply button (placeholder for now)
        self.process_history_button = ctk.CTkButton(
            title_row,
            text="Process Browser History",
            fg_color="green",
            command=self.copy_places_db,
            width=200,
        )
        self.process_history_button.pack(side="right")

        # Create notebook for tabs
        from tkinter import ttk

        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True)

        # Tab 1: DB Sources
        sources_tab = ctk.CTkFrame(notebook, fg_color="white")
        notebook.add(sources_tab, text="DB Sources")
        self.create_db_sources_tab(sources_tab)

        # Tab 2: URL Removal Filter
        filter_tab = ctk.CTkFrame(notebook, fg_color="white")
        notebook.add(filter_tab, text="URL Removal Filter")
        self.create_url_filter_tab(filter_tab)

        # Tab 3: URL Replacements
        replacements_tab = ctk.CTkFrame(notebook, fg_color="white")
        notebook.add(replacements_tab, text="URL Replacements")
        self.create_url_replacements_tab(replacements_tab)

    def create_db_sources_tab(self, parent):
        """Interactive browser history source management"""
        parent.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            parent,
            text="Configured Browser History Files",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            parent,
            text="Add, remove, and manage the browser history database files that will be merged.",
            text_color="gray",
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 15))

        list_frame = ctk.CTkFrame(parent, fg_color="transparent")
        list_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 10))
        parent.grid_rowconfigure(2, weight=1)

        scrollbar = ctk.CTkScrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        self.db_sources_listbox = tk.Listbox(
            list_frame,
            height=10,
            bg="#f8f9fa",
            fg="#2c3e50",
            font=("Segoe UI", 10),
            relief="flat",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground="#dee2e6",
            selectbackground="#108cff",
            activestyle="none",
            yscrollcommand=scrollbar.set,
        )
        self.db_sources_listbox.pack(fill="both", expand=True, side="left")
        scrollbar.configure(command=self.db_sources_listbox.yview)

        self.refresh_db_sources_listbox()

        buttons_frame = ctk.CTkFrame(parent, fg_color="transparent")
        buttons_frame.grid(row=3, column=0, sticky="w", padx=20, pady=(10, 20))

        add_file_btn = ctk.CTkButton(
            buttons_frame,
            text="➕ Add File",
            fg_color="#28a745",
            hover_color="#218838",
        )
        add_file_btn.pack(side="left", padx=(0, 10))
        self.bind_button_mouse_up(add_file_btn, self.add_db_source)

        info_btn = ctk.CTkButton(
            buttons_frame,
            text="Info",
            fg_color="#0d6efd",
            hover_color="#0b5ed7",
        )
        info_btn.pack(side="left", padx=(0, 10))
        self.bind_button_mouse_up(info_btn, self.show_db_source_path_examples)

        remove_file_btn = ctk.CTkButton(
            buttons_frame,
            text="🗑 Remove Selected",
            fg_color="#dc3545",
            hover_color="#c82333",
        )
        remove_file_btn.pack(side="left")
        self.bind_button_mouse_up(remove_file_btn, self.remove_db_source)

    def create_url_filter_tab(self, parent):
        """Editable URL filter management"""
        parent.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            parent,
            text="URL Removal Filters",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            parent,
            text="Enter URL patterns (one per line) to exclude from merged history during cleaning.",
            text_color="gray",
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 15))

        text_frame = ctk.CTkFrame(parent, fg_color="transparent")
        text_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 10))
        parent.grid_rowconfigure(2, weight=1)

        scrollbar = ctk.CTkScrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")

        self.url_filter_text = tk.Text(
            text_frame,
            bg="#f8f9fa",
            fg="#2c3e50",
            font=("Consolas", 10),
            relief="flat",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground="#dee2e6",
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set,
        )
        self.url_filter_text.pack(fill="both", expand=True, side="left")
        scrollbar.configure(command=self.url_filter_text.yview)

        url_filters = getattr(self, "url_filters", [])
        if url_filters:
            self.url_filter_text.insert("1.0", "\n".join(url_filters))

        save_filters_btn = ctk.CTkButton(
            parent,
            text="💾 Save Filters",
        )
        save_filters_btn.grid(row=3, column=0, sticky="w", padx=20, pady=(10, 20))
        self.bind_button_mouse_up(save_filters_btn, self.save_url_filters)

    def create_url_replacements_tab(self, parent):
        """Editable URL replacements grid"""
        parent.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            parent,
            text="URL Replacements",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            parent,
            text="Define URL text to find and replace during cleaning. Double-click a cell to edit its contents.",
            text_color="gray",
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 15))

        tree_frame = ctk.CTkFrame(parent, fg_color="transparent")
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 10))
        parent.grid_rowconfigure(2, weight=1)

        scrollbar = ctk.CTkScrollbar(tree_frame)
        scrollbar.pack(side="right", fill="y")

        style = ttk.Style()
        style.configure(
            "Replacement.Treeview",
            background="#f8f9fa",
            foreground="#2c3e50",
            fieldbackground="#f8f9fa",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Replacement.Treeview.Heading",
            background="#dee2e6",
            foreground="#2c3e50",
            font=("Segoe UI", 10, "bold"),
        )

        self.replacements_tree = ttk.Treeview(
            tree_frame,
            columns=("url_text", "replace_with"),
            show="headings",
            height=10,
            style="Replacement.Treeview",
            yscrollcommand=scrollbar.set,
        )
        self.replacements_tree.heading("url_text", text="URL Text to Find")
        self.replacements_tree.heading("replace_with", text="Replace With")
        self.replacements_tree.column("url_text", anchor="w", width=320)
        self.replacements_tree.column("replace_with", anchor="w", width=320)
        self.replacements_tree.pack(fill="both", expand=True, side="left")
        scrollbar.configure(command=self.replacements_tree.yview)
        self.replacements_tree.tag_configure(
            "blank",
            background="#ffc75f",
            foreground="#4a1c00",
            font=("Segoe UI", 10, "bold"),
        )  # High-contrast highlight for unfinished rows

        for rep in getattr(self, "url_replacements", []):
            item_id = self.replacements_tree.insert(
                "", tk.END, values=(rep["url_text"], rep["replace_with"])
            )
            self.update_replacement_row_tag(item_id)

        self.replacements_tree.bind("<Double-1>", self.on_replacement_double_click)

        buttons_frame = ctk.CTkFrame(parent, fg_color="transparent")
        buttons_frame.grid(row=3, column=0, sticky="w", padx=20, pady=(10, 20))

        save_replacements_btn = ctk.CTkButton(
            buttons_frame,
            text="💾 Save Replacements",
        )
        save_replacements_btn.pack(side="left", padx=(0, 10))
        self.bind_button_mouse_up(save_replacements_btn, self.save_url_replacements)

        add_row_btn = ctk.CTkButton(
            buttons_frame,
            text="➕ Add Row",
            fg_color="#28a745",
            hover_color="#218838",
        )
        add_row_btn.pack(side="left", padx=(0, 10))
        self.bind_button_mouse_up(add_row_btn, self.add_replacement_row)

        remove_row_btn = ctk.CTkButton(
            buttons_frame,
            text="🗑 Remove Selected",
            fg_color="#dc3545",
            hover_color="#c82333",
        )
        remove_row_btn.pack(side="left")
        self.bind_button_mouse_up(remove_row_btn, self.remove_replacement_row)

    def refresh_db_sources_listbox(self):
        """Refresh the DB sources listbox with current config"""
        if not hasattr(self, "db_sources_listbox"):
            return

        self.db_sources_listbox.delete(0, tk.END)
        for file_path in getattr(self, "userbrowserhistory", []):
            self.db_sources_listbox.insert(tk.END, file_path)

    def add_db_source(self):
        """Prompt for a DB source file and add it to the config"""
        filename = filedialog.askopenfilename(
            title="Select Browser History File",
            filetypes=[
                ("Database files", "*.db *.sqlite *.sqlite3 *History"),
                ("All files", "*.*"),
            ],
        )
        if not filename:
            return

        history_list = getattr(self, "userbrowserhistory", [])
        if filename in history_list:
            messagebox.showinfo(
                "Already Added",
                "That browser history file is already in the list.",
            )
            return

        history_list.append(filename)
        self.userbrowserhistory = history_list
        self.refresh_db_sources_listbox()
        logger.info(f"Added DB source: {filename}")
        self.persist_config_changes()

    def show_db_source_path_examples(self):
        """Show common browser history DB paths."""
        messagebox.showinfo(
            "Common Browser History Paths",
            "Firefox example:\n"
            "User/AppData/Roaming/Mozilla/Firefox/Profiles/your profile/places.sqlite\n\n"
            "Chrome example:\n"
            "User/AppData/Local/Google/Chrome/User Data/your profile/History",
        )

    def remove_db_source(self):
        """Remove the currently selected DB source"""
        if not hasattr(self, "db_sources_listbox"):
            return
        selection = self.db_sources_listbox.curselection()
        if not selection:
            messagebox.showwarning(
                "Nothing Selected", "Select a browser history file to remove."
            )
            return

        index = selection[0]
        try:
            removed_path = self.userbrowserhistory.pop(index)
        except (AttributeError, IndexError):
            return

        self.refresh_db_sources_listbox()
        logger.info(f"Removed DB source: {removed_path}")
        self.persist_config_changes()

    def save_url_filters(self):
        """Persist URL removal filters entered in the tab"""
        if not hasattr(self, "url_filter_text"):
            return

        content = self.url_filter_text.get("1.0", tk.END)
        filters = [line.strip() for line in content.splitlines() if line.strip()]
        self.url_filters = filters
        self.persist_config_changes()
        messagebox.showinfo(
            "Filters Saved", f"URL filters updated ({len(filters)} pattern(s))."
        )
        logger.info(f"URL filters saved: {len(filters)} pattern(s)")

    def save_url_replacements(self):
        """Persist URL replacements from the treeview"""
        if not hasattr(self, "replacements_tree"):
            return

        replacements = []
        for item in self.replacements_tree.get_children():
            url_text, replace_with = self.replacements_tree.item(item, "values")
            if url_text.strip() or replace_with.strip():
                replacements.append(
                    {"url_text": url_text.strip(), "replace_with": replace_with.strip()}
                )

        self.url_replacements = replacements
        self.persist_config_changes()
        messagebox.showinfo(
            "Replacements Saved",
            f"URL replacements updated ({len(replacements)} entr{'y' if len(replacements)==1 else 'ies'}).",
        )
        logger.info(f"URL replacements saved: {len(replacements)} entries")

    def add_replacement_row(self):
        """Insert a blank replacement row for editing"""
        if not hasattr(self, "replacements_tree"):
            return
        item_id = self.replacements_tree.insert("", tk.END, values=("", ""))
        self.update_replacement_row_tag(item_id)
        logger.info("Added empty URL replacement row")

    def remove_replacement_row(self):
        """Remove selected replacement rows"""
        if not hasattr(self, "replacements_tree"):
            return
        selection = self.replacements_tree.selection()
        if not selection:
            messagebox.showwarning(
                "Nothing Selected", "Select at least one replacement row to remove."
            )
            return

        for item in selection:
            self.replacements_tree.delete(item)
        logger.info(f"Removed {len(selection)} replacement row(s)")

    def on_replacement_double_click(self, event):
        """Enable in-place editing for the replacements treeview"""
        tree = getattr(self, "replacements_tree", None)
        if not tree:
            return

        region = tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        row_id = tree.identify_row(event.y)
        column_id = tree.identify_column(event.x)
        if not row_id:
            return

        bbox = tree.bbox(row_id, column_id)
        if not bbox:
            return

        x, y, width, height = bbox
        current_value = tree.set(row_id, column_id)

        if hasattr(self, "_replacement_edit_entry") and self._replacement_edit_entry:
            self._replacement_edit_entry.destroy()

        entry = tk.Entry(tree, font=("Segoe UI", 10))
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, current_value)
        entry.focus_set()
        self._replacement_edit_entry = entry

        def finalize_edit(event=None):
            if not entry.winfo_exists():
                return
            new_value = entry.get()
            tree.set(row_id, column_id, new_value)
            self.update_replacement_row_tag(row_id)
            entry.destroy()
            self._replacement_edit_entry = None

        def cancel_edit(event=None):
            entry.unbind("<FocusOut>")
            entry.destroy()
            self._replacement_edit_entry = None

        entry.bind("<Return>", finalize_edit)
        entry.bind("<Escape>", cancel_edit)
        entry.bind("<FocusOut>", finalize_edit)

    def update_replacement_row_tag(self, item_id):
        """Apply visual tags so blank rows are easy to spot"""
        tree = getattr(self, "replacements_tree", None)
        if not tree:
            return

        values = tree.item(item_id, "values")
        has_blank = any(not str(value).strip() for value in values)
        tree.item(item_id, tags=("blank",) if has_blank else ())

    def persist_config_changes(self):
        """Helper to persist config changes reflecting current UI state"""
        last_scene = getattr(self, "lastsceneID", 1)
        last_max = getattr(self, "lastmaxID", "Unknown")
        try:
            self.write_json_config(last_scene, last_max)
        except Exception as exc:
            logger.error(f"Failed to persist config changes: {exc}", exc_info=True)

    def bind_button_mouse_up(self, button, callback):
        """Ensure the given callback fires on mouse release (or keyboard activation)."""

        def is_enabled():
            state = str(button.cget("state")) if button.cget("state") is not None else ""
            return state not in ("disabled", "disabled_hover")

        def invoke():
            if is_enabled():
                callback()

        def on_release(event):
            if not is_enabled():
                return
            x_root, y_root = event.x_root, event.y_root
            within_x = button.winfo_rootx() <= x_root <= button.winfo_rootx() + button.winfo_width()
            within_y = button.winfo_rooty() <= y_root <= button.winfo_rooty() + button.winfo_height()
            if within_x and within_y:
                invoke()

        button.bind("<ButtonRelease-1>", on_release, add="+")
        button.bind("<KeyRelease-Return>", lambda event: invoke(), add="+")
        button.bind("<KeyRelease-space>", lambda event: invoke(), add="+" )

    # Old remaining methods continue from here...
    def _on_scene_seg(self, choice: str):
        if choice == "Start":
            self.load_scenes()
        elif choice == "Stop and Verify":
            self.stop_and_verify_scenes()

    def setup_logging(self):
        """Set up logging with the text widget"""
        text_handler = TextHandler(self.log_text)
        formatter = logger.handlers[0].formatter if logger.handlers else None
        if formatter:
            text_handler.setFormatter(formatter)
        logger.addHandler(text_handler)
        text_handler.start_polling()

    def initialize_scene_id(self):
        """Initialize scene ID from config"""
        try:
            scene_id = int(self.lastsceneID) if hasattr(self, "lastsceneID") else 1
            if scene_id <= 0:
                raise ValueError("Scene ID must be positive")
        except Exception as e:
            logger.error(f"Invalid scene ID: {e}. Using fallback value 1.")
            scene_id = 1
        self.start_id_var.set(str(scene_id))

    def toggle_theme(self):
        """Toggle between light and dark themes"""
        current_mode = ctk.get_appearance_mode()
        new_mode = "dark" if current_mode == "light" else "light"
        ctk.set_appearance_mode(new_mode)

        # Update log text colors
        if new_mode == "dark":
            self.log_text.configure(bg="#2b2b2b", fg="#ffffff")
        else:
            self.log_text.configure(bg="white", fg="black")

    # === EXISTING METHODS (unchanged functionality) ===
    # Add URL binding
    def write_json_config(self, last_scene, last_max):
        # Get current threshold value from UI
        threshold_value = (
            self.threshold_var.get() if hasattr(self, "threshold_var") else "3"
        )

        config_data = {
            "lastsceneID": str(last_scene),
            "lastmaxID": str(last_max),
            "userbrowserhistory": self.userbrowserhistory,
            "url_filters": self.url_filters,
            "url_replacements": self.url_replacements,
            "remember_browser_path": self.remember_browser_path,
            "auto_check_threshold": threshold_value,
            "auto_startup": self.auto_startup if hasattr(self, "auto_startup") else False,
            "scheme": self.scheme_var.get() if hasattr(self, "scheme_var") else "http",
            "host": self.host_var.get() if hasattr(self, "host_var") else "localhost",
            "port": self.port_var.get() if hasattr(self, "port_var") else "9999",
            "apikey": self.apikey_var.get() if hasattr(self, "apikey_var") else "",
        }
        try:
            with open(self.json_config_path, "w") as f:
                json.dump(config_data, f, indent=4)
            logger.info(f"[JSON] JSON config updated: {config_data}")
        except Exception as e:
            logger.error(f"[JSON] Failed to update JSON config: {e}")

    def sleep_with_pause(self, duration):
        start_time = time.time()
        increment = 0.1
        while time.time() - start_time < duration:
            if self.stop_event.is_set():
                return

            self.pause_event.wait(timeout=increment)
            if not self.pause_event.is_set():
                while not self.pause_event.is_set() and not self.stop_event.is_set():
                    time.sleep(increment)
                if self.stop_event.is_set():
                    return

    def update_status(self, message, color="black"):
        """Update the status label with message and color"""
        try:
            if hasattr(self, 'status_label') and self.status_label.winfo_exists():
                self.status_label.configure(text=message, text_color=color)
        except (AttributeError, RuntimeError, Exception):
            # Widget has been destroyed or is invalid - safely ignore
            pass

    def update_connection_status(self, message, color="black"):
        """Update the connection status label"""
        try:
            if hasattr(self, 'connection_status_label') and self.connection_status_label.winfo_exists():
                self.connection_status_label.configure(text=message, text_color=color)
        except (AttributeError, RuntimeError, Exception):
            # Widget has been destroyed or is invalid - safely ignore
            pass

    def _widget_exists(self, widget):
        """Return True only for live Tk widgets."""
        try:
            return widget is not None and widget.winfo_exists()
        except Exception:
            return False

    def _safe_configure_widget(self, widget, **kwargs):
        """Configure a widget only if it still exists."""
        if not self._widget_exists(widget):
            return False
        try:
            widget.configure(**kwargs)
            return True
        except Exception:
            return False

    def _update_end_id_label(self, text):
        """Safely update the end-scene label when Scenes widgets are alive."""
        self._safe_configure_widget(getattr(self, "end_id_label", None), text=text)

    def _scenes_widgets_ready(self):
        """Check if the Scenes page controls are currently mounted."""
        return self.active_page == "Scenes" and self._widget_exists(
            getattr(self, "load_button", None)
        )

    def set_connection_ready(self, is_ready: bool):
        """Toggle Stash-dependent controls based on connection readiness."""
        self.stash_connected = is_ready
        self._refresh_connection_dependent_buttons()

    def _refresh_connection_dependent_buttons(self):
        """Enable/disable buttons that require a confirmed Stash connection."""
        if not hasattr(self, "connection_dependent_buttons"):
            return

        desired_state = "normal" if getattr(self, "stash_connected", False) else "disabled"
        desired_hover = desired_state == "normal"
        accept_btn = getattr(self, "accept_button", None)

        for btn in self.connection_dependent_buttons:
            try:
                if btn is None or not btn.winfo_exists():
                    continue

                state = desired_state
                hover = desired_hover

                if getattr(self, "accept_in_progress", False) and btn is accept_btn:
                    state = "disabled"
                    hover = False

                btn.configure(state=state, hover=hover)
            except Exception:
                continue

    def set_accept_in_progress(self, in_progress: bool):
        """Keep the Accept button disabled while updates are running."""
        self.accept_in_progress = in_progress
        self._refresh_connection_dependent_buttons()

    def update_progress(self, value):
        """Update progress bar (0.0 to 1.0)"""
        try:
            if hasattr(self, 'progress_bar') and self.progress_bar.winfo_exists():
                self.progress_bar.set(value)
        except (AttributeError, RuntimeError, Exception):
            # Widget has been destroyed or is invalid - safely ignore
            pass

    def show_error_message(self, title, message, suggestions=None, error_details=None):
        """Show standardized error message with optional suggestions and collapsible error details"""
        self.update_status(f"Error: {title}", "red")

        # If no error details, use simple messagebox
        if error_details is None:
            full_message = message
            if suggestions:
                full_message += f"\n\nSuggestions:\n{suggestions}"
            messagebox.showerror(title, full_message)
            return

        # Create custom dialog with collapsible error details
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.resizable(True, True)
        dialog.transient(self)
        dialog.grab_set()

        base_width = 640
        base_height = 320
        dialog.geometry(f"{base_width}x{base_height}")

        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (base_width // 2)
        y = (dialog.winfo_screenheight() // 2) - (base_height // 2)
        dialog.geometry(f"{base_width}x{base_height}+{x}+{y}")

        # Use grid so the details area can expand
        dialog.grid_rowconfigure(0, weight=0)   # header/suggestions
        dialog.grid_rowconfigure(1, weight=1)   # details frame (when visible)
        dialog.grid_rowconfigure(2, weight=0)   # buttons
        dialog.grid_columnconfigure(0, weight=1)

        # Main content frame
        content_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        content_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=(20, 10))

        # Error message
        msg_label = ctk.CTkLabel(
            content_frame,
            text=message,
            font=ctk.CTkFont(size=14),
            wraplength=base_width - 60,
            justify="left",
            anchor="w"
        )
        msg_label.pack(pady=(0, 10), anchor="w", fill="x")

        # Suggestions section
        if suggestions:
            suggestions_label = ctk.CTkLabel(
                content_frame,
                text="Suggestions:",
                font=ctk.CTkFont(size=13, weight="bold"),
                anchor="w"
            )
            suggestions_label.pack(pady=(4, 2), anchor="w")

            suggestions_text = ctk.CTkLabel(
                content_frame,
                text=suggestions,
                font=ctk.CTkFont(size=12),
                wraplength=base_width - 60,
                justify="left",
                anchor="w"
            )
            suggestions_text.pack(pady=(0, 10), anchor="w", fill="x")

        # Error details section (initially hidden)
        details_frame = ctk.CTkFrame(dialog, fg_color="#F3F3F3", corner_radius=6)
        details_visible = [False]

        # Textbox + scrollbar for details
        details_frame.grid_rowconfigure(0, weight=1)
        details_frame.grid_columnconfigure(0, weight=1)

        details_textbox = ctk.CTkTextbox(
            details_frame,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
            fg_color="#FFFFFF",
            text_color="#000000"
        )
        details_textbox.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)

        details_scrollbar = ctk.CTkScrollbar(
            details_frame,
            command=details_textbox.yview
        )
        details_scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)

        details_textbox.configure(yscrollcommand=details_scrollbar.set)
        details_textbox.insert("1.0", error_details)
        details_textbox.configure(state="disabled")

        def toggle_details():
            if details_visible[0]:
                # Hide details
                details_frame.grid_forget()
                details_button.configure(text="▶ More Details")
                dialog.update_idletasks()
                details_visible[0] = False
            else:
                # Show details in the middle row and let it take spare space
                details_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
                dialog.update_idletasks()
                details_visible[0] = True
                details_button.configure(text="▼ Hide Details")

        # Button frame at the bottom
        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=0)

        # More Details button (left)
        details_button = ctk.CTkButton(
            button_frame,
            text="▶ More Details",
            command=toggle_details,
            width=150,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color="#E0E0E0",
            text_color="#000000",
            hover_color="#D0D0D0"
        )
        details_button.grid(row=0, column=0, sticky="w")

        # OK button (right)
        ok_button = ctk.CTkButton(
            button_frame,
            text="OK",
            command=dialog.destroy,
            width=110,
            height=32,
            font=ctk.CTkFont(size=12)
        )
        ok_button.grid(row=0, column=1, sticky="e")


        # Wait for dialog to close
        dialog.wait_window()

    def show_warning_message(self, title, message):
        """Show standardized warning message"""
        self.update_status(f"Warning: {title}", "orange")
        messagebox.showwarning(title, message)

    def show_info_message(self, title, message):
        """Show standardized info message"""
        self.update_status(message, "blue")
        messagebox.showinfo(title, message)

    def update_log_header(self, message):
        """Update the log header with current operation status"""
        try:
            if hasattr(self, 'log_header') and self.log_header.winfo_exists():
                self.log_header.configure(text=f"Log Output - {message}")
        except (AttributeError, RuntimeError, Exception):
            # Widget has been destroyed or is invalid - safely ignore
            pass

    def _get_valid_tables_from_db(self, db_path):
        """Get valid tables from database"""
        valid_tables_found = []
        if not os.path.exists(db_path):
            logger.error(f"Database file not found for table scan: {db_path}")
            return valid_tables_found
        conn = None
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            for tbl in tables:
                try:
                    cursor.execute(f"PRAGMA table_info(\"{tbl}\")")
                    columns_info = cursor.fetchall()
                    columns = [col[1].lower() for col in columns_info]
                    if "url" in columns and "title" in columns:
                        valid_tables_found.append(tbl)
                except sqlite3.Error as e_tbl:
                    logger.warning(f"Could not read info for table '{tbl}' in {db_path}: {e_tbl}")
            logger.debug(f"Valid tables found in {db_path}: {valid_tables_found}")
        except sqlite3.Error as e:
            logger.error(f"DB error scanning tables in {db_path}: {e}", exc_info=True)
        finally:
            if conn:
                conn.close()
        return valid_tables_found

    def append_to_browser_history_db(self, temp_db_path, table_name, browser_label, original_source_filepath):
        """Append data from temp database to main browser history database"""
        if not os.path.exists(temp_db_path):
            logger.error(f"{temp_db_path} not found for appending.")
            return None

        main_db_path = "browserHistory.db"
        main_conn, temp_conn = None, None
        appended_count = 0

        try:
            temp_conn = sqlite3.connect(f"file:{temp_db_path}?mode=ro", uri=True)
            temp_cursor = temp_conn.cursor()

            main_conn = sqlite3.connect(main_db_path)
            main_cursor = main_conn.cursor()

            main_cursor.execute("""
                CREATE TABLE IF NOT EXISTS browser_hist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    title TEXT,
                    browser TEXT,
                    historytitle TEXT,
                    source_file TEXT
                )
            """)
            main_conn.commit()

            main_cursor.execute("PRAGMA table_info(browser_hist)")
            columns = [info[1] for info in main_cursor.fetchall()]
            if 'source_file' not in columns:
                main_cursor.execute("ALTER TABLE browser_hist ADD COLUMN source_file TEXT")
                main_conn.commit()

            main_cursor.execute("""
                DELETE FROM browser_hist
                WHERE id NOT IN (
                    SELECT MIN(id) FROM browser_hist GROUP BY url
                )
            """)
            main_conn.commit()

            try:
                main_cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_browser_hist_url ON browser_hist(url)")
                main_conn.commit()
            except sqlite3.IntegrityError as e:
                logger.warning(f"Could not create unique index due to existing duplicates: {e}")

            temp_cursor.execute(f"PRAGMA table_info(\"{table_name}\")")
            source_columns = [col[1].lower() for col in temp_cursor.fetchall()]

            select_title_col = "title" if "title" in source_columns else "NULL AS title"
            if "url" not in source_columns:
                logger.error(f"Source table '{table_name}' in {original_source_filepath} does not have 'url' column.")
                return 0

            select_sql = f"SELECT url, {select_title_col} FROM \"{table_name}\" WHERE url IS NOT NULL AND url != ''"
            temp_cursor.execute(select_sql)
            rows = temp_cursor.fetchall()

            insert_sql = "INSERT OR IGNORE INTO browser_hist (url, title, browser, source_file, historytitle) VALUES (?, ?, ?, ?, ?)"
            source_filename_for_db = os.path.basename(original_source_filepath)

            for row_url, row_title in rows:
                try:
                    historytitle = sanitize_for_windows(str(row_title)) if row_title else ""

                    res = main_cursor.execute(insert_sql, (
                        row_url,
                        row_title,
                        browser_label,
                        source_filename_for_db,
                        historytitle
                    ))
                    if res.rowcount > 0:
                        appended_count += 1
                except sqlite3.Error as e_insert:
                    logger.warning(f"Could not insert row (URL: {row_url}) from {browser_label}: {e_insert}")

            main_conn.commit()

            if appended_count > 0:
                logger.info(f"{appended_count} new unique rows from '{table_name}' in '{original_source_filepath}' appended.")
            else:
                logger.info(f"No new unique rows from '{table_name}' in '{original_source_filepath}' to append.")

            return appended_count

        except sqlite3.Error as e:
            logger.error(f"SQLite error appending data from '{table_name}' ({original_source_filepath}): {e}", exc_info=True)
            return None
        finally:
            if temp_conn:
                temp_conn.close()
            if main_conn:
                main_conn.close()

    def _ensure_browser_history_metadata_table(self, cursor):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

    def _get_current_history_processing_settings(self):
        active_filters = self.url_filters if hasattr(self, "url_filters") else ["google.com", "localhost"]
        active_replacements = self.url_replacements if hasattr(self, "url_replacements") else []

        normalized_filters = sorted(
            str(item).strip()
            for item in active_filters
            if str(item).strip()
        )

        normalized_replacements = []
        for rep_pair in active_replacements:
            if not isinstance(rep_pair, dict):
                continue
            normalized_replacements.append(
                {
                    "url_text": str(rep_pair.get("url_text", "")).strip(),
                    "replace_with": str(rep_pair.get("replace_with", "")).strip(),
                }
            )

        return {
            "url_filters": json.dumps(normalized_filters, ensure_ascii=True),
            "url_replacements": json.dumps(normalized_replacements, ensure_ascii=True),
        }

    def _get_stored_history_processing_settings(self, db_path="browserHistory.db"):
        if not os.path.exists(db_path):
            return None

        conn = None
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            self._ensure_browser_history_metadata_table(cursor)
            conn.commit()

            settings = {}
            for key in ("url_filters", "url_replacements"):
                cursor.execute("SELECT value FROM app_metadata WHERE key = ?", (key,))
                row = cursor.fetchone()
                settings[key] = row[0] if row else None
            return settings
        except sqlite3.Error as e:
            logger.error(f"Failed to read stored browser history processing settings from {db_path}: {e}", exc_info=True)
            return None
        finally:
            if conn:
                conn.close()

    def _store_history_processing_settings(self, cursor):
        self._ensure_browser_history_metadata_table(cursor)
        current_settings = self._get_current_history_processing_settings()
        for key, value in current_settings.items():
            cursor.execute(
                "INSERT INTO app_metadata (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def _should_run_browser_history_maintenance(self, rows_appended, db_path="browserHistory.db"):
        if rows_appended > 0:
            logger.info(
                "Running deduplication and cleaning because new browser history rows were appended."
            )
            return True

        current_settings = self._get_current_history_processing_settings()
        stored_settings = self._get_stored_history_processing_settings(db_path)
        if not stored_settings:
            logger.info(
                "Running deduplication and cleaning because no stored DB processing settings were found."
            )
            return True

        if any(stored_settings.get(key) != current_settings.get(key) for key in current_settings):
            logger.info(
                "Running deduplication and cleaning because DB processing settings differ from the current config."
            )
            return True

        logger.info(
            "Skipped dedupe/clean because no new rows were appended and DB processing settings match the current config."
        )
        return False

    def _browser_history_has_duplicate_urls(self, cursor):
        cursor.execute("""
            SELECT 1
            FROM browser_hist
            WHERE url IS NOT NULL AND url != ''
            GROUP BY url
            HAVING COUNT(*) > 1
            LIMIT 1
        """)
        return cursor.fetchone() is not None

    def remove_duplicates(self, run_vacuum=False):
        """Remove duplicates from browser history database"""
        db_path = "browserHistory.db"
        if not os.path.exists(db_path):
            logger.warning(f"{db_path} not found. Cannot remove duplicates.")
            return

        duplicates_found = False
        conn = None
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            logger.info("Starting deduplication based on url and title...")

            duplicates_found = self._browser_history_has_duplicate_urls(cursor)
            if not duplicates_found:
                logger.info("Skipped duplicate rewrite because no duplicate URLs were found.")
                return

            cursor.executescript("""
                CREATE TEMP TABLE IF NOT EXISTS temp_browser_hist AS
                SELECT * FROM browser_hist
                WHERE id IN (
                    SELECT MAX(id) FROM browser_hist
                    GROUP BY url, title
                );

                DELETE FROM browser_hist;

                INSERT INTO browser_hist (id, url, title, browser, historytitle, source_file)
                SELECT id, url, title, browser, historytitle, source_file FROM temp_browser_hist;

                DROP TABLE temp_browser_hist;
            """)

            conn.commit()
            logger.info("Deduplication complete. Duplicate (url, title) pairs removed.")
        except sqlite3.Error as e:
            logger.error(f"Failed to remove duplicates from {db_path}: {e}", exc_info=True)
        finally:
            if conn:
                conn.close()

        if duplicates_found:
            if run_vacuum:
                self.repack_database(db_path)
            else:
                logger.info("VACUUM deferred after deduplication.")

    def clean_urls_merged_db(self, run_vacuum=False):
        """Clean URLs in the merged database"""
        main_db_path = "browserHistory.db"
        if not os.path.exists(main_db_path):
            logger.warning(f"{main_db_path} not found. Cannot clean.")
            return

        active_filters = self.url_filters if hasattr(self, 'url_filters') else ["google.com", "localhost"]
        active_replacements = self.url_replacements if hasattr(self, 'url_replacements') else []

        logger.info(f"Starting cleaning of {main_db_path}...")
        logger.info(f"Using URL filters: {active_filters if active_filters else 'None'}")
        logger.info(f"Using URL replacements: {active_replacements if active_replacements else 'None'}")

        conn = None
        try:
            conn = sqlite3.connect(main_db_path)
            cursor = conn.cursor()

            count_initial = cursor.execute("SELECT COUNT(*) FROM browser_hist").fetchone()[0]

            cursor.execute("DELETE FROM browser_hist WHERE title IS NULL OR title = '' OR url IS NULL OR url = ''")
            conn.commit()
            count_after_no_title_empty_url = cursor.execute("SELECT COUNT(*) FROM browser_hist").fetchone()[0]
            no_title_empty_url_removed = count_initial - count_after_no_title_empty_url
            if no_title_empty_url_removed > 0:
                logger.info(f"Removed {no_title_empty_url_removed} entries with no title or empty URL.")

            total_filtered_removed = 0
            if active_filters:
                for f_pattern in active_filters:
                    if not f_pattern.strip():
                        continue
                    res = cursor.execute("DELETE FROM browser_hist WHERE url LIKE ?", (f"%{f_pattern}%",))
                    removed_this_filter = res.rowcount
                    if removed_this_filter > 0:
                        logger.info(f"Filter '{f_pattern}' removed {removed_this_filter} entries.")
                    total_filtered_removed += removed_this_filter
            conn.commit()
            if total_filtered_removed > 0 or active_filters:
                logger.info(f"Total entries removed by filters: {total_filtered_removed}.")

            replacements_matched_total = 0
            replacements_updated_total = 0
            replacements_skipped_total = 0
            if active_replacements:
                for rep_pair in active_replacements:
                    find_text = rep_pair.get("url_text","")
                    replace_text = rep_pair.get("replace_with","")
                    if not find_text.strip():
                        continue
                    try:
                        # Count rows that actually contain the search text before update.
                        candidate_count = cursor.execute(
                            "SELECT COUNT(*) FROM browser_hist WHERE url LIKE ?",
                            (f"%{find_text}%",),
                        ).fetchone()[0]

                        if candidate_count <= 0:
                            logger.info(
                                f"Replacement '{find_text}'->'{replace_text}' matched 0 rows, updated 0 rows, skipped 0."
                            )
                            continue

                        res = cursor.execute(
                            "UPDATE OR IGNORE browser_hist "
                            "SET url = REPLACE(url, ?, ?) "
                            "WHERE url LIKE ?",
                            (find_text, replace_text, f"%{find_text}%")
                        )
                        updated_count = res.rowcount if res.rowcount and res.rowcount > 0 else 0
                        skipped_count = max(candidate_count - updated_count, 0)

                        replacements_matched_total += candidate_count
                        replacements_updated_total += updated_count
                        replacements_skipped_total += skipped_count

                        logger.info(
                            f"Replacement '{find_text}'->'{replace_text}' matched {candidate_count} rows, "
                            f"updated {updated_count} rows, skipped {skipped_count}."
                        )
                    except sqlite3.IntegrityError as e:
                        logger.warning(f"Skipping replacement '{find_text}'->'{replace_text}' due to duplicate URL: {e}")
            conn.commit()
            if active_replacements:
                logger.info(
                    "Total rows affected by URL replacements: "
                    f"matched={replacements_matched_total}, "
                    f"updated={replacements_updated_total}, "
                    f"skipped={replacements_skipped_total}."
                )

            cursor.execute("""
                SELECT id, title
                FROM browser_hist
                WHERE title IS NOT NULL
                  AND title <> ''
                  AND (historytitle IS NULL OR historytitle = '')
            """)
            rows_for_historytitle = cursor.fetchall()
            for row_id, title_val in rows_for_historytitle:
                simple_title = sanitize_for_windows(str(title_val))
                cursor.execute(
                    "UPDATE browser_hist SET historytitle = ? WHERE id = ?",
                    (simple_title, row_id)
                )
            conn.commit()
            logger.info(f"Generated/updated 'historytitle' for {len(rows_for_historytitle)} entries.")

            '''
            logger.info("Refreshing 'tableHits' summary table for repeated titles (count >= 2)...")
            cursor.execute("DROP TABLE IF EXISTS tableHits")
            conn.commit()

            cursor.execute("""
                CREATE TABLE tableHits AS
                SELECT historytitle AS ht, COUNT(*) AS cnt
                FROM browser_hist
                WHERE historytitle IS NOT NULL AND historytitle != ''
                GROUP BY historytitle
                HAVING COUNT(*) >= 2
            """)
            conn.commit()

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tableHits_ht ON tableHits(ht)")
            conn.commit()

            logger.info("'tableHits' table refreshed.")
            '''

            count_final = cursor.execute("SELECT COUNT(*) FROM browser_hist").fetchone()[0]
            self._store_history_processing_settings(cursor)
            conn.commit()
            logger.info(f"Cleaning of {main_db_path} complete. Final entry count: {count_final}.")

            if run_vacuum:
                self.repack_database(main_db_path)
            else:
                logger.info("VACUUM deferred after cleaning.")

        except sqlite3.Error as e:
            logger.error(f"Error cleaning URLs: {e}", exc_info=True)
        finally:
            if conn:
                conn.close()

    def repack_database(self, db_path_to_repack):
        """Repack (VACUUM) the database"""
        if not os.path.exists(db_path_to_repack):
            logger.warning(f"Database {db_path_to_repack} not found, cannot repack.")
            return
        conn = None
        try:
            conn = sqlite3.connect(db_path_to_repack)
            conn.execute("VACUUM")
            conn.commit()
            logger.info(f"Database {db_path_to_repack} repacked (VACUUMed).")
        except sqlite3.Error as e:
            logger.error(f"Failed to repack {db_path_to_repack}: {e}", exc_info=True)
        finally:
            if conn:
                conn.close()

    def process_single_history_file_and_clean(self, source_filepath, run_maintenance=True, return_rows=False):
        """Process a single history file: copy, append, deduplicate, and clean"""
        logger.info(f"Auto-processing individual file: {source_filepath}")

        if not os.path.exists(source_filepath):
            logger.error(f"[FILE ERROR] Source file not found for auto-processing: {source_filepath}")
            return False

        temp_db_path = f"temp_auto_processing_{os.path.basename(source_filepath)}.db"
        try:
            shutil.copy(source_filepath, temp_db_path)
        except Exception as e:
            logger.error(f"[FILE ERROR] Failed to copy {source_filepath} to {temp_db_path} for auto-processing: {e}", exc_info=True)
            return False

        rows_appended_from_this_source = 0
        file_processed_successfully = False

        try:
            valid_tables_in_source = self._get_valid_tables_from_db(temp_db_path)
            if not valid_tables_in_source:
                file_processed_successfully = True
            else:
                for table_name in valid_tables_in_source:
                    browser_label = f"{os.path.basename(source_filepath)}::{table_name}"
                    appended_this_table = self.append_to_browser_history_db(temp_db_path, table_name, browser_label, source_filepath)
                    if appended_this_table is not None:
                        rows_appended_from_this_source += appended_this_table
                file_processed_successfully = True

            if rows_appended_from_this_source > 0:
                logger.info(f"NEW ENTRIES: {rows_appended_from_this_source} new unique rows appended from {source_filepath}.")
            elif file_processed_successfully:
                logger.info(f"NEW ENTRIES: No new unique rows appended from {source_filepath} (data may already exist or source was empty/filtered).")

            if file_processed_successfully:
                if os.path.exists("browserHistory.db"):
                    if run_maintenance and self._should_run_browser_history_maintenance(rows_appended_from_this_source):
                        logger.info(f"Running deduplication and cleaning for browserHistory.db after processing {source_filepath}...")
                        self.remove_duplicates(run_vacuum=False)
                        self.clean_urls_merged_db(run_vacuum=False)
                    elif not run_maintenance:
                        logger.info(
                            f"Deferred deduplication and cleaning after processing {source_filepath}."
                        )
                else:
                    logger.info(f"browserHistory.db does not exist. Skipping deduplication and cleaning after {source_filepath}.")
            else:
                logger.warning(f"Core processing of {source_filepath} did not complete successfully. Skipping cleanup for this file.")

        except Exception as e:
            logger.error(f"Unhandled error during auto-processing of {source_filepath}: {e}", exc_info=True)
            file_processed_successfully = False
        finally:
            if os.path.exists(temp_db_path):
                try:
                    os.remove(temp_db_path)
                except Exception as e:
                    logger.warning(f"Could not remove temp DB {temp_db_path}: {e}")

        if return_rows:
            return file_processed_successfully, rows_appended_from_this_source

        return file_processed_successfully

    def sync_and_clean_all_sources(self):
        """Sync and clean all configured browser history sources"""
        if not self.userbrowserhistory:
            logger.info("No browser history files are configured to sync.")
            self.update_status("No sources configured", "orange")
            return

        logger.info("Starting 'Sync and Clean All Configured Histories'...")
        self.update_status("Processing browser histories...", "blue")

        total_rows_appended_overall = 0
        processed_files_count = 0
        temp_db_path = "temp_processing_browserHistory.db"

        for source_idx, source_filepath in enumerate(self.userbrowserhistory):
            if not os.path.exists(source_filepath):
                logger.warning(f"Source file not found, skipping: {source_filepath}")
                continue

            logger.info(f"Processing source file: {source_filepath}...")
            try:
                shutil.copy(source_filepath, temp_db_path)
            except Exception as e:
                logger.error(f"Failed to copy {source_filepath} to temp: {e}", exc_info=True)
                continue

            valid_tables_in_source = self._get_valid_tables_from_db(temp_db_path)
            if not valid_tables_in_source:
                logger.warning(f"No valid tables (with url/title) found in {source_filepath}. Skipping.")
            else:
                logger.info(f"Found valid tables {valid_tables_in_source} in {source_filepath}.")
                for table_name in valid_tables_in_source:
                    browser_label = f"{os.path.basename(source_filepath)}::{table_name}"
                    appended_this_table = self.append_to_browser_history_db(temp_db_path, table_name, browser_label, source_filepath)
                    if appended_this_table is not None:
                        total_rows_appended_overall += appended_this_table

            if os.path.exists(temp_db_path):
                try:
                    os.remove(temp_db_path)
                except Exception as e:
                    logger.warning(f"Could not remove temp DB {temp_db_path}: {e}")
            processed_files_count += 1

        if processed_files_count > 0:
            logger.info(f"Finished appending data from {processed_files_count} source file(s). Total rows appended in this session: {total_rows_appended_overall}.")
            if self._should_run_browser_history_maintenance(total_rows_appended_overall):
                logger.info("Now starting deduplication of the merged browserHistory.db...")
                self.remove_duplicates(run_vacuum=False)

                logger.info("Now starting final cleaning of the merged browserHistory.db...")
                self.clean_urls_merged_db(run_vacuum=False)

            logger.info("Sync and Clean All operation finished.")
            self.update_status("Processing complete", "green")
        else:
            logger.info("No source files were processed or no new data appended.")
            self.update_status("No files processed", "orange")

    def copy_places_db(self):
        """Process browser history: sync and clean all configured sources"""
        # Disable button during processing if it exists
        if hasattr(self, 'process_history_button'):
            self.process_history_button.configure(state="disabled", text="Processing...")

        # Mark that sync opportunity has been provided this session
        self.synced_this_session = True

        # Run sync and clean in a thread to avoid blocking UI
        def run_sync():
            try:
                self.sync_and_clean_all_sources()
            finally:
                # Restore button state
                if hasattr(self, 'process_history_button'):
                    self.process_history_button.configure(
                        state="normal", text="🔄 Process Browser History"
                    )
                self.update_status("Ready", "green")

        # Start in thread to keep UI responsive
        threading.Thread(target=run_sync, daemon=True).start()

    def get_last_scene_id_from_log(self):
        try:
            with open(LOG_FILE_NAME, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in reversed(lines):
                match = re.search(r"Loaded scene (\d+)", line)
                if match:
                    return int(match.group(1))
        except Exception as e:
            logger.error(f"Error reading log file: {e}")
        return None

    def load_scenes(self):
        if self.processing_thread and self.processing_thread.is_alive():
            logger.info(
                "A scene loading process is already active. Signaling it to stop."
            )
            self.stop_event.set()
            self.pause_event.set()

        # Check if database sync has occurred this session
        if not self.synced_this_session and not self.sync_prompt_shown:
            self.sync_prompt_shown = True  # Only ask once per session
            response = messagebox.askyesno(
                "Database Sync",
                "Database sync has not been performed this session.\n\n"
                "Would you like to sync and clean the browser history database now?\n\n"
                "This will process configured browser history paths and update the local database.",
                icon='question'
            )
            if response:
                # User wants to sync - open the history manager
                self.copy_places_db()
                # Don't proceed with loading scenes yet - let user complete sync first
                return
            else:
                # User declined - proceed with loading scenes
                logger.info("User declined database sync. Proceeding with scene loading.")

        self.load_button.configure(state="disabled", text="Loading...")
        self.update_status("Preparing to load scenes...", "orange")
        self.update_log_header("Matching scenes...")
        self.update_progress(0.0)

        self.stop_event.clear()
        self.pause_event.set()

        logger.info("Clearing previously displayed scenes for new load.")
        self.scenes = []
        self.load_current_scenes()

        try:
            initial_start_id_for_thread = int(self.start_id_var.get())
            if initial_start_id_for_thread <= 0:
                self.show_error_message(
                    "Invalid Scene ID",
                    "Start Scene ID must be a positive number.",
                    "• Enter a number greater than 0\n• Leave blank to start from scene 1",
                )
                self._finalize_ui_after_scan_attempt()
                return
        except ValueError:
            self.show_error_message(
                "Invalid Scene ID Format",
                f"Invalid Start Scene ID in textbox: '{self.start_id_var.get()}'",
                "• Enter a valid number\n• Leave blank to start from scene 1",
            )
            self._finalize_ui_after_scan_attempt()
            return

        self.update_status("Starting scene loading...", "blue")
        logger.info(
            f"Starting new scene loading thread from Scene ID: {initial_start_id_for_thread}."
        )
        self.processing_thread = threading.Thread(
            target=self._load_scenes_thread,
            args=(initial_start_id_for_thread,),
            daemon=True,
        )
        self.processing_thread.start()

    def _load_scenes_thread(self, initial_start_id_for_this_scan):
        max_id_local = "Unknown"
        try:
            self.stash = StashInterface(
                {
                    "scheme": self.scheme_var.get(),
                    "Host": self.host_var.get(),
                    "Port": self.port_var.get(),
                    "ApiKey": self.apikey_var.get(),
                }
            )
        except Exception as e:
            error_msg = "Error connecting to Stash"
            suggestions = "• Check that StashApp is running\n• Verify connection settings (scheme, host, port)\n• Test connection using the 'Test Connection' button"
            self.after(
                0,
                lambda: self.show_error_message(
                    "Stash Connection Failed", error_msg, suggestions, error_details=str(e)
                ),
            )
            self.after(0, lambda: self.set_connection_ready(False))
            self.after(0, self._finalize_ui_after_scan_attempt)
            return

        try:
            scenes_desc = self.stash.find_scenes(
                {}, filter={"per_page": 1, "sort": "id", "direction": "DESC"}
            )
            if scenes_desc and scenes_desc[0]:
                max_id_local = scenes_desc[0]["id"]
            self.after(0, lambda: self.set_connection_ready(True))
            self.after(
                0,
                lambda: self._update_end_id_label(text=f"End Scene ID: {max_id_local}"),
            )
        except Exception as e:
            self.after(0, lambda: self.set_connection_ready(False))
            self.after(
                0, lambda: self._update_end_id_label(text="End Scene ID: Unknown")
            )
            logger.error(f"Error retrieving maximum scene id: {e}")

        valid_scenes_this_run = []
        sid = initial_start_id_for_this_scan
        highest_found_scene_id = None  # Track the highest scene ID we actually found

        while len(valid_scenes_this_run) < TARGET_SCENE_COUNT:
            if self.stop_event.is_set():
                logger.info(
                    "Scene loading thread: Stop event detected. Terminating scan."
                )
                break

            self.pause_event.wait()

            if self.stop_event.is_set():
                logger.info(
                    "Scene loading thread: Stop event detected after pause. Terminating scan."
                )
                break

            # Check if we've reached or exceeded max_id before querying
            if max_id_local != "Unknown":
                try:
                    if sid > int(max_id_local):
                        logger.info(
                            f"Current scene ID {sid} exceeds maximum known scene ID {max_id_local}. Stopping scan."
                        )
                        break
                except ValueError:
                    logger.warning(
                        f"Could not compare with max_id_local: '{max_id_local}' is not a valid integer."
                    )

            # Update progress and status
            progress = len(valid_scenes_this_run) / TARGET_SCENE_COUNT
            self.after(0, lambda: self.update_progress(progress))
            self.after(
                0,
                lambda: self.update_status(
                    f"Matching scenes... {len(valid_scenes_this_run)}/{TARGET_SCENE_COUNT} found",
                    "blue",
                ),
            )

            scene = self.stash.find_scene(sid)
            current_sid_for_log = sid
            sid += 1

            if not scene:
                logger.info(f"Scene {current_sid_for_log} not found; skipping.")
                self.sleep_with_pause(0.2)
                continue

            if self.skip_organized_var.get() and scene.get("organized", False):
                logger.info(f"Scene {scene.get('id')} organized, skipped")
                self.sleep_with_pause(0.2)
                continue

            files = scene.get("files")
            if not files or len(files) == 0:
                logger.info(f"Scene {scene.get('id')} has no file; skipping.")
                self.sleep_with_pause(0.2)
                continue

            filename = os.path.basename(files[0]["path"])
            base_filename = os.path.splitext(filename)[0]
            candidates = self.get_browser_urls(base_filename)
            if not candidates:
                logger.info(
                    f"Scene {scene.get('id')} no matches using '{base_filename}'"
                )
                self.sleep_with_pause(0.2)
                continue

            candidate_title, candidate_url = candidates[0]
            existing_urls = scene.get("urls", [])
            if any(
                (isinstance(url_obj, dict) and url_obj.get("url", "") == candidate_url)
                or (isinstance(url_obj, str) and url_obj == candidate_url)
                for url_obj in existing_urls
            ):
                logger.info(
                    f"Scene {scene.get('id')} URL already exists: {candidate_url}"
                )
                self.sleep_with_pause(0.2)
                continue

            valid_scenes_this_run.append(scene)

            # Track the highest scene ID we've actually found
            scene_id = scene.get('id')
            if scene_id:
                try:
                    scene_id_int = int(scene_id)
                    if highest_found_scene_id is None or scene_id_int > highest_found_scene_id:
                        highest_found_scene_id = scene_id_int
                except (ValueError, TypeError):
                    pass

            log_message = f"Scene {scene.get('id')} Match found - {base_filename} with browser {candidate_title} - {candidate_url}"
            self.log_text.after(
                0,
                lambda msg=log_message: self._log_message_with_tag(msg, "match_found"),
            )
            self.sleep_with_pause(0.2)

        # Calculate next_start_id intelligently:
        # - If we found scenes, start from highest_found_scene_id + 1
        # - Otherwise, use the current sid (last checked ID)
        # - But never exceed max_id_local
        if highest_found_scene_id is not None:
            next_start_id = highest_found_scene_id + 1
        else:
            next_start_id = sid

        # Clamp next_start_id to not exceed max_id_local
        if max_id_local != "Unknown":
            try:
                max_id_int = int(max_id_local)
                if next_start_id > max_id_int:
                    next_start_id = max_id_int
                    logger.info(f"Clamping next_start_id to max_id_local: {max_id_int}")
            except ValueError:
                pass

        self.after(
            0,
            lambda: self._finish_load_scenes(valid_scenes_this_run, max_id_local, next_start_id),
        )

    def _log_message_with_tag(self, message, tag_name):
        logger.info(message)

    def _finish_load_scenes(self, found_scenes, max_id, next_start_id):
        self.scenes = found_scenes

        if max_id != "Unknown":
            self._update_end_id_label(text=f"End Scene ID: {max_id}")
            self.lastmaxID = max_id

        self.start_id_var.set(str(next_start_id))
        if self._scenes_widgets_ready():
            self.load_current_scenes()
        else:
            logger.info("Skipping scene row refresh because Scenes page is not active.")

        self._finalize_ui_after_scan_attempt()

    def _finalize_ui_after_scan_attempt(self):
        if self._widget_exists(getattr(self, "load_button", None)):
            self.load_button.configure(state="normal", text="Start")
        if self.scenes:
            self.update_status("Scene loading completed", "green")
            self.update_log_header(f"Ready - {len(self.scenes)} scenes loaded")

            # Auto-accept if toggle is enabled
            if self.auto_accept_var.get():
                logger.info(
                    "Auto-accept is enabled. Automatically triggering accept_candidates()..."
                )
                self.after(500, self.accept_candidates)  # Small delay to let UI update
        else:
            self.update_status("No scenes found", "orange")
            self.update_log_header("Ready - No scenes found")

        self.update_progress(0.0)
        self.processing_thread = None
        logger.info("Scene loading UI finalized.")

    def forward_block(self):
        self.load_scenes()

    def open_local_directory(self):
        local_path = os.path.dirname(os.path.abspath(__file__))
        try:
            os.startfile(local_path)
        except Exception as e:
            logger.error(f"Error opening directory '{local_path}': {e}")

    def get_title_hit_count(self, clean_base: str) -> int:
        # tableHits lookup disabled.
        return 0
        '''
        db_path = os.path.abspath("browserHistory.db")
        if not os.path.exists(db_path):
            logger.error(f"{db_path} not found for hit counts.")
            return 0

        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT cnt FROM tableHits WHERE ht = ?", (clean_base,))
            row = cur.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"Error querying tableHits for '{clean_base}': {e}")
            return 0
        finally:
            conn.close()
        '''

    def load_current_scenes(self):
        if not self._scenes_widgets_ready():
            logger.info("Skipping load_current_scenes because Scenes widgets are unavailable.")
            return

        self.scene_url_candidates = []
        for i in range(TARGET_SCENE_COUNT):
            if i >= len(self.scenes):
                self.scene_num_labels[i].configure(text="Scene NA")
                self.diff_labels[i].configure(text="N/A\nN/A")
                self.url_labels[i].configure(text="No URL")
                self.checkbox_vars[i].set(False)
                self.url_tooltips[i].update_text("No URLs available")
                self.scene_url_candidates.append([])
                continue

            scene = self.scenes[i]
            scene_id = scene.get("id", "N/A")
            files = scene.get("files")

            filename_for_processing = "No file found"
            candidate_title = "(none)"
            candidate_url = ""
            all_candidates = []

            if files and len(files) > 0:
                fname = os.path.basename(files[0].get("path", ""))
                if fname:
                    filename_for_processing = os.path.splitext(fname)[0]

            clean_base = self.clean_filename(filename_for_processing)

            if filename_for_processing != "No file found":
                db_path = os.path.abspath("./browserHistory.db")
                if not os.path.exists(db_path):
                    logger.error(
                        f"Browser History database not found at {db_path}. Cannot get URLs for {clean_base}."
                    )
                else:
                    # Get all candidates for tooltip
                    all_candidates = self.get_browser_urls(
                        filename_for_processing, get_all=True
                    )

                    # Get primary candidate for display
                    primary_candidates = self.get_browser_urls(
                        filename_for_processing, get_all=False
                    )
                    if primary_candidates:
                        candidate_title, candidate_url = primary_candidates[0]
                        if not candidate_title or not candidate_title.strip():
                            candidate_title = candidate_url
            # Store all candidates for this scene
            self.scene_url_candidates.append(all_candidates)

            try:
                self.scene_num_labels[i].configure(text=f"Scene {int(scene_id):5d}")
            except (ValueError, TypeError):
                self.scene_num_labels[i].configure(text=f"Scene {scene_id}")

            if len(candidate_title) > 76:
                candidate_title_trunc = candidate_title[:74] + "..."
            else:
                candidate_title_trunc = candidate_title

            # Truncate clean_base to 76 chars + "…" if it’s over 76
            if len(clean_base) > 76:
                clean_base_trunc = clean_base[:74] + "..."
            else:
                clean_base_trunc = clean_base
            self.diff_labels[i].configure(
                text=f"{clean_base_trunc}\n{candidate_title_trunc}"
            )

            title_hit_val = len(all_candidates)
            display_prefix = f"({title_hit_val}) " if title_hit_val else ""
            display_url = candidate_url or "No URL found"
            self.url_labels[i].configure(text=display_prefix + display_url)

            # Update tooltip with all candidates
            if all_candidates:
                tooltip_text = f"All matches for '{clean_base}':\n"
                for idx, (title, url) in enumerate(all_candidates, 1):
                    tooltip_text += f"{idx}. {title}\n   {url}\n"
                self.url_tooltips[i].update_text(tooltip_text.strip())
            else:
                self.url_tooltips[i].update_text("No matching URLs found")

            # Get threshold value from UI control
            try:
                value_str = self.threshold_var.get().strip()
                # Handle blank or negative values
                if value_str == "" or value_str is None:
                    threshold = 0
                else:
                    threshold = int(value_str)
                    if threshold < 0:
                        threshold = 0
            except (ValueError, AttributeError):
                threshold = 3  # Default fallback

            # Threshold logic:
            # - threshold = 0: Auto-check all scenes (no filtering)
            # - threshold > 0: Auto-check only if hit count < threshold
            if threshold == 0:
                should_check = True  # Check all when threshold is 0
            else:
                should_check = not (title_hit_val and title_hit_val >= threshold)

            self.checkbox_vars[i].set(should_check)

    def clean_filename(self, filename_to_clean: str) -> str:
        if filename_to_clean.lower().endswith(".mp4"):
            filename_to_clean = filename_to_clean[:-4]

        filename_to_clean = remove_dash_number_suffix(filename_to_clean)
        return sanitize_for_windows(filename_to_clean)

    def get_browser_urls(self, base_filename, get_all=False):
        clean_base = self.clean_filename(base_filename)

        db_path = os.path.abspath("./browserHistory.db")
        if not os.path.exists(db_path):
            return []

        conn = None
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            sql_query = """
            SELECT historytitle, url 
            FROM browser_hist 
            WHERE historytitle LIKE ? COLLATE NOCASE
              AND LENGTH(historytitle) >= LENGTH(?)
            """
            param = clean_base + "%"
            cursor.execute(sql_query, (param, clean_base))
            results = cursor.fetchall()

        except sqlite3.Error as e:
            logger.error(f"SQLite error for '{clean_base}' in {db_path}: {e}")
            return []
        except Exception as e:
            logger.error(f"General query error for '{clean_base}' in {db_path}: {e}")
            return []
        finally:
            if conn:
                conn.close()

        filter_domains = (
            self.url_filters
            if hasattr(self, "url_filters") and self.url_filters
            else ["localhost", "google.com"]
        )

        filtered_results = [
            (ht, u)
            for (ht, u) in results
            if u
            and isinstance(u, str)
            and all(d.lower() not in u.lower() for d in filter_domains)
            and ht
            and isinstance(ht, str)
        ]

        if get_all:
            # Apply the same startswith filtering for get_all=True
            return [
                (ht, u)
                for (ht, u) in filtered_results
                if ht.lower().startswith(clean_base.lower())
            ]

        for candidate_historytitle, candidate_url in filtered_results:
            if candidate_historytitle.lower().startswith(clean_base.lower()):
                return [(candidate_historytitle, candidate_url)]

        if filtered_results:
            return [filtered_results[0]]

        return []

    def accept_candidates(self):
        if not all([self.scheme_var.get(), self.host_var.get(), self.port_var.get()]):
            self.show_error_message(
                "Missing Connection Details",
                "Stash connection details are missing. Please fill them in before accepting candidates.",
                "• Fill in scheme (http/https)\n• Fill in host (localhost)\n• Fill in port (9999)\n• Test connection first",
            )
            return

        self.set_accept_in_progress(True)
        self.update_status("Starting URL updates...", "blue")
        self.update_log_header("Updating URLs...")
        self.update_progress(0.0)
        threading.Thread(target=self._accept_candidates_thread, daemon=True).start()

    def _accept_candidates_thread(self):
        updated_scenes_count = 0
        last_updated_scene_id_for_config = ""

        if not hasattr(self, "stash") or self.stash is None:
            try:
                self.stash = StashInterface(
                    {
                        "scheme": self.scheme_var.get(),
                        "Host": self.host_var.get(),
                        "Port": self.port_var.get(),
                        "ApiKey": self.apikey_var.get(),
                    }
                )
            except Exception as e:
                logger.error(f"Error initializing Stash for accepting candidates: {e}")
                error_msg = f"Stash connection failed: {str(e)}"
                suggestions = "• Check that StashApp is running\n• Verify connection settings\n• Test connection first"
                self.after(
                    0,
                    lambda: self.show_error_message(
                        "Stash Connection Failed", error_msg, suggestions
                    ),
                )
                def handle_accept_failure():
                    self.set_accept_in_progress(False)
                    self.set_connection_ready(False)

                self.after(0, handle_accept_failure)
                return

        # Stash connection succeeded or already existed
        self.after(0, lambda: self.set_connection_ready(True))

        total_scenes = len(self.scenes)
        for i in range(total_scenes):
            if self.stop_event.is_set():
                logger.info("Accept candidates thread: stop event detected.")
                break
            self.pause_event.wait()

            # Update progress
            progress = i / total_scenes
            self.after(0, lambda: self.update_progress(progress))
            self.after(
                0,
                lambda: self.update_status(
                    f"Updating URLs... {i}/{total_scenes} processed", "blue"
                ),
            )

            scene = self.scenes[i]
            scene_id_str = str(scene.get("id", ""))

            if not scene_id_str:
                logger.warning(f"Scene at index {i} has no ID. Skipping.")
                continue

            if self.checkbox_vars[i].get():
                selected_url = self.url_labels[i].cget("text")
                selected_url = re.sub(r"^\(\d+\)\s+", "", selected_url)
                if selected_url and selected_url.lower().startswith("http"):
                    current_scene_data = self.stash.find_scene(scene_id_str)
                    if not current_scene_data:
                        logger.error(
                            f"Scene {scene_id_str} not found in Stash during accept. Skipping."
                        )
                        continue

                    existing_urls = current_scene_data.get("urls", [])
                    if not isinstance(existing_urls, list):
                        existing_urls = []

                    url_already_exists = any(
                        (isinstance(url_obj, str) and url_obj == selected_url)
                        or (
                            isinstance(url_obj, dict)
                            and url_obj.get("url", "") == selected_url
                        )
                        for url_obj in existing_urls
                    )

                    if url_already_exists:
                        logger.info(
                            f"Scene {scene_id_str}: Candidate URL '{selected_url}' already exists in Stash; skipping update."
                        )
                        continue

                    updated_urls = existing_urls + [selected_url]
                    try:
                        tag = self.stash.find_tag("URLHistory", create=True)
                        tag_ids_to_update = [tag["id"]] if tag and "id" in tag else []

                        current_tags_in_stash = current_scene_data.get("tags", [])
                        for t_stash in current_tags_in_stash:
                            if (
                                isinstance(t_stash, dict)
                                and "id" in t_stash
                                and t_stash["id"] not in tag_ids_to_update
                            ):
                                tag_ids_to_update.append(t_stash["id"])

                        payload = {"id": scene_id_str, "urls": updated_urls}
                        if tag_ids_to_update:
                            payload["tag_ids"] = tag_ids_to_update

                        self.stash.update_scene(payload)

                        log_msg = (
                            f"Scene {scene_id_str} Updated with URL: {selected_url}"
                        )
                        if tag_ids_to_update and (
                            tag and "id" in tag and tag["id"] in tag_ids_to_update
                        ):
                            log_msg += " and tagged 'URLHistory'."

                        self.log_text.after(
                            0,
                            lambda msg=log_msg, tag="update_complete": self._log_message_with_tag(
                                msg, tag
                            ),
                        )
                        updated_scenes_count += 1
                        last_updated_scene_id_for_config = scene_id_str
                    except Exception as e:
                        logger.error(
                            f"Error updating scene {scene_id_str} in Stash: {e}",
                            exc_info=True,
                        )
                else:
                    logger.info(
                        f"Scene {scene_id_str}: No valid URL selected or to update ('{selected_url}')."
                    )
            else:
                logger.info(f"Scene {scene_id_str}: Checkbox not selected; skipping.")
            self.sleep_with_pause(0.05)

        if last_updated_scene_id_for_config:
            self.after(
                0,
                lambda: self.write_json_config(
                    last_updated_scene_id_for_config, self.lastmaxID
                ),
            )

        # Reset UI state and show completion
        self.after(0, lambda: self.set_accept_in_progress(False))
        self.after(0, lambda: self.update_progress(1.0))
        self.after(
            0,
            lambda: self.update_status(
                f"URL updates completed - {updated_scenes_count} scenes updated",
                "green",
            ),
        )
        self.after(
            0,
            lambda: self.update_log_header(
                f"Updates completed - {updated_scenes_count} scenes updated"
            ),
        )

        self.after(0, self.load_scenes)

    def stop_and_verify_scenes(self):
        logger.info("'Stop and Verify' clicked.")
        if self.processing_thread and self.processing_thread.is_alive():
            logger.info("Signaling active scene loading thread to stop...")
            self.stop_event.set()
            self.pause_event.set()
            self.update_status("Stopping scene loading...", "orange")
        else:
            logger.info("No active scene loading thread to stop.")
            if self.scenes:
                logger.info("Displaying existing matched scenes for verification.")
                self.load_current_scenes()
                self.update_status("Ready for verification", "green")
            else:
                logger.info("No matched scenes to display for verification.")

        self.load_button.configure(state="normal")

    def toggle_check_all(self):
        self.all_checked = not self.all_checked
        if self.all_checked:
            self.toggle_check_button.configure(text="Uncheck All")
            self.update_status("All scenes selected", "green")
        else:
            self.toggle_check_button.configure(text="Check All")
            self.update_status("All scenes deselected", "orange")
        for checkbox_var in self.checkbox_vars:
            checkbox_var.set(self.all_checked)

    def increment_threshold(self):
        """Increment the auto-check threshold value"""
        try:
            value_str = self.threshold_var.get().strip()
            # Handle blank values
            if value_str == "":
                current = 0
            else:
                current = int(value_str)
                # Handle negative values
                if current < 0:
                    current = 0

            if current < 99:  # Max limit
                self.threshold_var.set(str(current + 1))
        except (ValueError, AttributeError):
            self.threshold_var.set("0")  # Set to 0 if invalid

    def decrement_threshold(self):
        """Decrement the auto-check threshold value"""
        try:
            value_str = self.threshold_var.get().strip()
            # Handle blank values
            if value_str == "":
                current = 0
            else:
                current = int(value_str)
                # Handle negative values
                if current < 0:
                    current = 0

            if current > 0:  # Min limit is 0
                self.threshold_var.set(str(current - 1))
        except (ValueError, AttributeError):
            self.threshold_var.set("0")  # Set to 0 if invalid

    def show_help_page(self):
        """Display the help page"""
        # Main container
        container = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        title_label = ctk.CTkLabel(
            container,
            text="Help & Instructions",
            font=ctk.CTkFont(size=28, weight="bold"),
        )
        title_label.pack(pady=(0, 20))

        # Help content frame
        help_frame = ctk.CTkFrame(container, corner_radius=10)
        help_frame.pack(fill="both", expand=True)

        # Help text
        help_text = (
            "INSTRUCTIONS:\n\n"
            "1. In DB Config, add a browser history file.\n\n"
            "2. Click Process Browser History to copy and condense the history for this app.\n\n"
            "3. Click 'Save History' to import into browserHistory.db.\n\n"
            "4. In Settings, edit any connection info if needed.\n\n"
            "5. Start up your Stash server.\n\n"
            "6. Go back to Scenes and click 'Start'.\n\n"
            "7. Check/uncheck as needed, then click 'Accept' to push them into Stash.\n\n\n"
            "After: In Stash, filter scenes by Tag 'urlhistory' and then use the tagger to scrape with Source 'Scrape with URL'\n\n"
            "Tip: Use the DB Config URL removal and replacement features to correct URLs if scraping doesnt work. \n"
            "E.g. replace 'https://example.com/' with https://www.example.com/ and then re-run app for scenes.\n\n"
        )

        # Scrollable text widget
        text_widget = ctk.CTkTextbox(
            help_frame,
            font=ctk.CTkFont(size=14),
            wrap="word",
        )
        text_widget.pack(fill="both", expand=True, padx=20, pady=20)
        text_widget.insert("1.0", help_text)
        text_widget.configure(state="disabled")

    def sync_scene_file_summary(self):
        file_path = filedialog.askopenfilename(
            title="Select Scene File Summary Database", filetypes=[("All Files", "*.*")]
        )
        if not file_path:
            return

        if not all([self.scheme_var.get(), self.host_var.get(), self.port_var.get()]):
            messagebox.showerror(
                "Stash Error",
                "Stash connection details are missing. Please fill them in.",
            )
            return

        threading.Thread(
            target=self._sync_scene_file_summary_thread, args=(file_path,), daemon=True
        ).start()

    def _sync_scene_file_summary_thread(self, db_path):
        try:
            local_stash = StashInterface(
                {
                    "scheme": self.scheme_var.get(),
                    "Host": self.host_var.get(),
                    "Port": self.port_var.get(),
                    "ApiKey": self.apikey_var.get(),
                }
            )
        except Exception as e:
            logger.error(f"Error connecting to Stash for side DB sync: {e}")
            self.after(
                0,
                lambda: messagebox.showerror(
                    "Stash Error", f"Stash connection failed: {e}"
                ),
            )
            return

        conn = None
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='scene_file_summary'"
            )
            if not cursor.fetchone():
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "DB Error",
                        "Table 'scene_file_summary' not found in selected database.",
                    ),
                )
                return

            cursor.execute(
                "SELECT scene_id, url_1 FROM scene_file_summary WHERE url_1 IS NOT NULL AND TRIM(url_1) <> ''"
            )
            rows = cursor.fetchall()

        except Exception as e:
            logger.error(f"Error processing side DB '{db_path}': {e}", exc_info=True)
            self.after(
                0,
                lambda: messagebox.showerror(
                    "DB Error", f"Error processing side DB: {e}"
                ),
            )
            return
        finally:
            if conn:
                conn.close()

        if not rows:
            return

        updated_count = 0
        processed_count = 0
        for scene_id_from_db, url_from_db in rows:
            if self.stop_event.is_set():
                logger.info("Side DB sync: stop event detected.")
                break
            self.pause_event.wait()

            processed_count += 1
            scene_id_str = str(scene_id_from_db)

            if not isinstance(url_from_db, str) or not url_from_db.lower().startswith(
                "http"
            ):
                logger.info(
                    f"Scene {scene_id_str}: URL '{url_from_db}' from side DB is not valid, skipping."
                )
                continue
            try:
                scene_in_stash = local_stash.find_scene(scene_id_str)
            except Exception as e:
                logger.error(f"Error retrieving scene {scene_id_str} from Stash: {e}")
                continue

            if not scene_in_stash:
                logger.info(
                    f"Scene {scene_id_str} not found in Stash; skipping sync for this entry."
                )
                continue

            existing_urls_in_stash = scene_in_stash.get("urls", [])
            if not isinstance(existing_urls_in_stash, list):
                existing_urls_in_stash = []

            url_already_exists_in_stash = any(
                (isinstance(url_obj, dict) and url_obj.get("url", "") == url_from_db)
                or (isinstance(url_obj, str) and url_obj == url_from_db)
                for url_obj in existing_urls_in_stash
            )

            if url_already_exists_in_stash:
                logger.info(
                    f"Scene {scene_id_str}: URL '{url_from_db}' from side DB already exists in Stash; skipping."
                )
                continue

            logger.info(
                f"Scene {scene_id_str}: Syncing URL from side DB: {url_from_db}"
            )
            try:
                tag = local_stash.find_tag("URLHistory", create=True)
                tag_ids_to_update = [tag["id"]] if tag and "id" in tag else []

                current_tags_in_stash = scene_in_stash.get("tags", [])
                for t_stash in current_tags_in_stash:
                    if (
                        isinstance(t_stash, dict)
                        and "id" in t_stash
                        and t_stash["id"] not in tag_ids_to_update
                    ):
                        tag_ids_to_update.append(t_stash["id"])

                new_urls_list_for_stash = existing_urls_in_stash + [url_from_db]
                payload = {"id": scene_id_str, "urls": new_urls_list_for_stash}
                if tag_ids_to_update:
                    payload["tag_ids"] = tag_ids_to_update

                local_stash.update_scene(payload)
                updated_count += 1
            except Exception as e:
                logger.error(
                    f"Error updating scene {scene_id_str} in Stash with URL from side DB: {e}",
                    exc_info=True,
                )
            self.sleep_with_pause(0.05)

        final_message = f"Side DB Sync Complete. Processed {processed_count} rows. Synced URLs for {updated_count} scenes."
        logger.info(final_message)

    def load_json_config(self):
        config_path = os.path.join(
            self._get_persistent_base_dir(), "urlstashgui.config"
        )
        self.json_config_path = config_path
        default_config = {
            "lastsceneID": "1",
            "lastmaxID": "Unknown",
            "userbrowserhistory": [],
            "url_filters": ["google.com", "localhost"],
            "url_replacements": [
                {"url_text": "spankbang.party", "replace_with": "spankbang.com"}
            ],
            "remember_browser_path": False,
            "auto_check_threshold": "3",
            "auto_startup": False,
            "scheme": "http",
            "host": "localhost",
            "port": "9999",
            "apikey": "",
        }
        config_data = default_config.copy()
        need_update_file = False

        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    loaded_data = json.load(f)
                logger.info(f"[JSON] JSON config loaded from {config_path}")

                for key in default_config:
                    if key in loaded_data:
                        current_value = loaded_data[key]
                        if key == "lastsceneID":
                            try:
                                val = int(current_value)
                                config_data[key] = str(
                                    val if val > 0 else default_config[key]
                                )
                                if val <= 0:
                                    need_update_file = True
                            except (ValueError, TypeError):
                                logger.warning(
                                    f"[JSON] Invalid value for '{key}': '{current_value}'. Using default: '{default_config[key]}'"
                                )
                                config_data[key] = default_config[key]
                                need_update_file = True
                        elif key == "lastmaxID":
                            config_data[key] = str(current_value)
                        elif key == "remember_browser_path":
                            if isinstance(current_value, bool):
                                config_data[key] = current_value
                            else:
                                old_val_str = str(current_value).lower()
                                new_bool_val = old_val_str in ["true", "1", "yes", "on"]
                                if str(config_data[key]).lower() != old_val_str:
                                    logger.warning(
                                        f"[JSON] Coerced '{key}':'{current_value}' to boolean {new_bool_val}."
                                    )
                                    need_update_file = True
                                config_data[key] = new_bool_val
                        elif key == "userbrowserhistory":
                            if isinstance(current_value, list) and all(
                                isinstance(x, str) for x in current_value
                            ):
                                config_data[key] = current_value
                            elif isinstance(current_value, str):
                                config_data[key] = (
                                    [current_value] if current_value.strip() else []
                                )
                                need_update_file = True
                                logger.info(
                                    f"[JSON] Converted single string userbrowserhistory to list."
                                )
                            else:
                                logger.warning(
                                    f"[JSON] Invalid value for '{key}': '{current_value}'. Using default."
                                )
                                config_data[key] = default_config[key]
                                need_update_file = True
                        elif key == "url_filters":
                            if isinstance(current_value, list) and all(
                                isinstance(x, str) for x in current_value
                            ):
                                config_data[key] = current_value
                            else:
                                logger.warning(
                                    f"[JSON] Invalid value for '{key}': '{current_value}'. Using default."
                                )
                                config_data[key] = default_config[key]
                                need_update_file = True
                        elif key == "url_replacements":
                            if isinstance(current_value, list) and all(
                                isinstance(item, dict)
                                and "url_text" in item
                                and "replace_with" in item
                                for item in current_value
                            ):
                                config_data[key] = current_value
                            else:
                                logger.warning(
                                    f"[JSON] Invalid value for '{key}': '{current_value}'. Using default."
                                )
                                config_data[key] = default_config[key]
                                need_update_file = True
                        elif key == "auto_check_threshold":
                            try:
                                # Handle blank, negative, or invalid values
                                if current_value == "" or current_value is None:
                                    config_data[key] = "0"
                                    logger.info(
                                        f"[JSON] Blank threshold value, setting to 0"
                                    )
                                    need_update_file = True
                                else:
                                    val = int(current_value)
                                    # Set negative values to 0
                                    if val < 0:
                                        config_data[key] = "0"
                                        logger.info(
                                            f"[JSON] Negative threshold value '{val}', setting to 0"
                                        )
                                        need_update_file = True
                                    else:
                                        config_data[key] = str(val)
                            except (ValueError, TypeError):
                                logger.warning(
                                    f"[JSON] Invalid threshold value: '{current_value}'. Setting to 0"
                                )
                                config_data[key] = "0"
                                need_update_file = True
                        elif key == "auto_startup":
                            if isinstance(current_value, bool):
                                config_data[key] = current_value
                            else:
                                old_val_str = str(current_value).lower()
                                new_bool_val = old_val_str in ["true", "1", "yes", "on"]
                                if str(config_data[key]).lower() != old_val_str:
                                    logger.warning(
                                        f"[JSON] Coerced '{key}':'{current_value}' to boolean {new_bool_val}."
                                    )
                                    need_update_file = True
                                config_data[key] = new_bool_val
                        elif key in ["scheme", "host", "port", "apikey"]:
                            # Connection settings - ensure they are strings
                            if current_value is None:
                                config_data[key] = default_config[key]
                                need_update_file = True
                            else:
                                config_data[key] = str(current_value)
                        else:
                            config_data[key] = current_value
                    else:
                        logger.info(
                            f"[JSON] Key '{key}' not in config, using default value: '{default_config[key]}'"
                        )
                        config_data[key] = default_config[key]
                        need_update_file = True

                extra_keys = [key for key in loaded_data if key not in default_config]
                if extra_keys:
                    logger.info(
                        f"[JSON] Obsolete keys found in config and will be ignored: {extra_keys}"
                    )

            except json.JSONDecodeError as e:
                logger.error(
                    f"[JSON] Failed to decode JSON config from {config_path}: {e}. Using defaults and attempting to overwrite."
                )
                config_data = default_config.copy()
                need_update_file = True
            except Exception as e:
                logger.error(
                    f"[JSON] Error loading JSON config {config_path}: {e}. Using defaults.",
                    exc_info=True,
                )
                config_data = default_config.copy()
                need_update_file = True

        else:
            logger.info(
                f"[JSON] Config file not found at {config_path}. Creating with default values."
            )
            config_data = default_config.copy()
            need_update_file = True

        if need_update_file:
            try:
                final_config_to_save = {
                    k: config_data[k] for k in default_config if k in config_data
                }
                with open(config_path, "w") as f:
                    json.dump(final_config_to_save, f, indent=4)
                logger.info(f"[JSON] JSON config (re)written at {config_path}")
                config_data = final_config_to_save
            except Exception as e:
                logger.error(
                    f"[JSON] Failed to write JSON config to {config_path}: {e}"
                )

        self.lastsceneID = config_data.get("lastsceneID", default_config["lastsceneID"])
        self.lastmaxID = config_data.get("lastmaxID", default_config["lastmaxID"])
        self.userbrowserhistory = config_data.get(
            "userbrowserhistory", default_config["userbrowserhistory"]
        )
        self.url_filters = config_data.get("url_filters", default_config["url_filters"])
        self.url_replacements = config_data.get(
            "url_replacements", default_config["url_replacements"]
        )
        self.remember_browser_path = config_data.get(
            "remember_browser_path", default_config["remember_browser_path"]
        )
        self.auto_check_threshold_config = config_data.get(
            "auto_check_threshold", default_config["auto_check_threshold"]
        )
        self.auto_startup = config_data.get(
            "auto_startup", default_config["auto_startup"]
        )

        # Load connection settings
        scheme = config_data.get("scheme", default_config["scheme"])
        host = config_data.get("host", default_config["host"])
        port = config_data.get("port", default_config["port"])
        apikey = config_data.get("apikey", default_config["apikey"])

        if hasattr(self, "start_id_var"):
            self.start_id_var.set(self.lastsceneID)
        self._update_end_id_label(text=f"End Scene ID: {self.lastmaxID}")
        if hasattr(self, "threshold_var"):
            self.threshold_var.set(self.auto_check_threshold_config)

        # Set connection settings UI variables
        if hasattr(self, "scheme_var"):
            self.scheme_var.set(scheme)
        if hasattr(self, "host_var"):
            self.host_var.set(host)
        if hasattr(self, "port_var"):
            self.port_var.set(port)
        if hasattr(self, "apikey_var"):
            self.apikey_var.set(apikey)


if __name__ == "__main__":
    app = UrlStashGUI()
    app.mainloop()

