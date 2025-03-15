#!/usr/bin/env python3
import os
import sys
import json
import sqlite3
import difflib
import time
import string
import logging
import shutil
import re
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import yaml

# You must have your stashapi module installed and accessible.
from stashapi.stashapp import StashInterface
import stashapi.log as log

# Global constants
TEST_USER = "2023f"
TARGET_SCENE_COUNT = 10

###################################################################
# Utility Functions
###################################################################
def sanitize_for_windows(filename: str) -> str:
    """
    Removes non-alphanumeric characters and converts the filename to lowercase.
    (Does not handle extension removal or dash suffix removal.)
    """
    return "".join(ch for ch in filename if ch.isalnum()).lower()

def remove_dash_number_suffix(text: str) -> str:
    """
    If the input text ends with a dash followed by exactly two digits (e.g. "-01"),
    remove that suffix. Example: 'some-title-01' -> 'some-title'.
    """
    if not text:
        return ""
    return re.sub(r'-\d\d$', '', text)

###################################################################
# Logger Setup
###################################################################
logger = logging.getLogger("FirefoxHistoryGUI")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler = logging.FileHandler("log_fox.txt", mode="w", encoding="utf-8")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

class TextHandler(logging.Handler):
    """
    Logging handler that writes log messages to a Tkinter Text widget.
    See https://docs.python.org/3/howto/logging.html for details.
    """
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record) + "\n"

        def append():
            self.text_widget.configure(state='normal')
            # If the log message includes "Match found" or "Update complete", apply the corresponding tag.
            if "Match found" in msg:
                self.text_widget.insert(tk.END, msg, 'match_found')
            elif "Update complete" in msg:
                self.text_widget.insert(tk.END, msg, 'update_complete')
            else:
                self.text_widget.insert(tk.END, msg)
            self.text_widget.configure(state='disabled')
            self.text_widget.yview(tk.END)

        self.text_widget.after(0, append)

###################################################################
# Popup Window for Processing Browser History Database
###################################################################
class CopyPlacesPopup(tk.Toplevel):
    """
    Popup for selecting and processing a browser history database.
    This is forced on top of the main UI. Includes a close button.
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Process Browser History DB")
        self.geometry("800x500")

        # Force on top of the main UI
        # (See https://docs.python.org/3/library/tkinter.html#top-level-windows)
        self.attributes("-topmost", True)
        self.transient(parent)

        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        # Variables to hold state
        self.db_loaded = False
        self.valid_tables = []
        self.selected_table = None
        self.duplicates_removed = 0  # Will store # duplicates removed

        # Frame for buttons
        button_frame = tk.Frame(self)
        button_frame.pack(pady=10)

        # "Select History" Button
        self.select_button = tk.Button(
            button_frame,
            text="Select History",
            command=self.select_history
        )
        self.select_button.pack(side=tk.LEFT, padx=5)

        # "Save History" Button (initially disabled)
        self.save_button = tk.Button(
            button_frame,
            text="Save History",
            state=tk.DISABLED,
            command=self.save_history
        )
        self.save_button.pack(side=tk.LEFT, padx=5)

        # "Clean URLs" Button (initially disabled)
        self.clean_button = tk.Button(
            button_frame,
            text="Clean URLs",
            state=tk.DISABLED,
            command=self.clean_urls
        )
        self.clean_button.pack(side=tk.LEFT, padx=5)

        # "Close" Button
        close_btn = tk.Button(
            button_frame,
            text="Close",
            command=self.close_popup
        )
        close_btn.pack(side=tk.LEFT, padx=5)

        # Treeview to show tables
        self.tree = ttk.Treeview(self, columns=("table_name",), show="tree")
        self.tree.heading("#0", text="Tables with url/title columns")
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        # Text box to store filter patterns
        self.filter_text = tk.Text(self, height=5, width=40)
        self.filter_text.pack(padx=10, pady=5)

        # yo dawg, add your extra URL removal text here.
        # only urls with exact matches will be removed from your temp history
        default_filters = [
            "google.com",
            "dinotube.com",
            "localhost"
        ]
        for pattern in default_filters:
            self.filter_text.insert(tk.END, pattern + "\n")

        # Label to display the current DB file path
        self.db_label = tk.Label(self, text="Current DB: None")
        self.db_label.pack(padx=10, pady=5)

    def close_popup(self):
        """Close this popup window."""
        self.destroy()

    def select_history(self):
        filetypes = [
            ("SQLite Databases", "*.db"),
            ("All Files", "*.*"),
        ]
        # Bring the popup window to the front and force it to be topmost
        self.lift()
        self.attributes("-topmost", True)
        filepath = filedialog.askopenfilename(
            parent=self,
            title="Select Browser History File",
            filetypes=filetypes
        )
        # Reset topmost attribute so only the popup stays above the main window
        self.attributes("-topmost", False)

        if not filepath:
            return  # User canceled

        try:
            shutil.copy(filepath, "temp_browserHistory.db")
            logger.info(f"Browser history copied from {filepath} to {os.path.abspath('temp_browserHistory.db')}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy file:\n{e}")
            return

        self.load_tables()
        if self.valid_tables:
            self.save_button.config(state=tk.NORMAL)
            self.db_loaded = True
        else:
            self.save_button.config(state=tk.DISABLED)
            messagebox.showwarning("No Valid Tables",
                                   "No tables with both 'url' and 'title' were found.")

    def load_tables(self):
        """Load tables from temp_browserHistory.db and display those containing 'url' and 'title'."""
        self.tree.delete(*self.tree.get_children())
        self.valid_tables.clear()

        if not os.path.exists("temp_browserHistory.db"):
            return

        try:
            conn = sqlite3.connect("temp_browserHistory.db")
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]

            for tbl in tables:
                cursor.execute(f"PRAGMA table_info({tbl})")
                columns_info = cursor.fetchall()
                columns = [col[1].lower() for col in columns_info]
                if "url" in columns and "title" in columns:
                    self.valid_tables.append(tbl)
                    self.tree.insert("", tk.END, iid=tbl, text=tbl)

            conn.close()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read tables:\n{e}")

    def on_tree_select(self, event):
        """Handles selection from the Treeview."""
        selected_item = self.tree.selection()
        if selected_item:
            self.selected_table = selected_item[0]

    def save_history(self):
        """
        Automatically determines the table to extract url/title. If 'browser_hist' is found, we use it;
        otherwise, we fall back to 'moz_places', 'url', or user-selected valid table.
        Appends the data into browserHistory.db (table browser_hist).
        Logs the event.
        """
        if not self.db_loaded:
            return

        target_table = None
        browser_label = None

        if "browser_hist" in self.valid_tables:
            target_table = "browser_hist"
            browser_label = "Browser History"
        elif "moz_places" in self.valid_tables:
            target_table = "moz_places"
            browser_label = "Mozilla History"
        elif "url" in self.valid_tables:
            target_table = "url"
            browser_label = "Chrome History"
        elif self.selected_table and self.selected_table in self.valid_tables:
            target_table = self.selected_table
            browser_label = f"Custom({self.selected_table})"

        if not target_table:
            messagebox.showwarning("Invalid Selection", "No valid table with url/title found in the selected database.")
            return

        messagebox.showinfo("Table Selected", f"Using table '{target_table}' for extracting url/title (Browser: {browser_label}).")

        self.append_to_browser_history_db(target_table, browser_label)
        self.remove_duplicates()

        db_path = os.path.abspath("browserHistory.db")
        self.db_label.config(text="Current DB: " + db_path)
        self.clean_button.config(state=tk.NORMAL)

        messagebox.showinfo("Done", "History has been saved successfully.")
        self.repack_database()

    def append_to_browser_history_db(self, table_name, browser_label):
        """
        Create or append to the browser_hist table in browserHistory.db.
        Logs 'History added...' upon completion.
        """
        if not os.path.exists("temp_browserHistory.db"):
            messagebox.showerror("Error", "temp_browserHistory.db not found.")
            return

        try:
            temp_conn = sqlite3.connect("temp_browserHistory.db")
            temp_cursor = temp_conn.cursor()

            main_conn = sqlite3.connect("browserHistory.db")
            main_cursor = main_conn.cursor()

            main_cursor.execute("""
                CREATE TABLE IF NOT EXISTS browser_hist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT,
                    title TEXT,
                    browser TEXT,
                    historytitle TEXT
                )
            """)

            select_sql = f"SELECT url, title FROM {table_name}"
            temp_cursor.execute(select_sql)
            rows = temp_cursor.fetchall()

            insert_sql = "INSERT INTO browser_hist (url, title, browser) VALUES (?, ?, ?)"
            for row in rows:
                main_cursor.execute(insert_sql, (row[0], row[1], browser_label))

            main_conn.commit()
            temp_conn.close()
            main_conn.close()

            logger.info(f"History added to history dump {os.path.abspath('browserHistory.db')}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to append data:\n{e}")

    def remove_duplicates(self):
        """
        Remove duplicate URLs from browserHistory.db (only keep the first ROWID).
        Store the number of removed duplicates in self.duplicates_removed.
        """
        try:
            main_conn = sqlite3.connect("browserHistory.db")
            main_cursor = main_conn.cursor()

            count_before = main_cursor.execute("SELECT COUNT(*) FROM browser_hist").fetchone()[0]

            sql_duplicates = """
                DELETE FROM browser_hist
                WHERE ROWID NOT IN (
                    SELECT MIN(ROWID)
                    FROM browser_hist
                    GROUP BY url
                );
            """
            main_cursor.execute(sql_duplicates)
            main_conn.commit()

            count_after = main_cursor.execute("SELECT COUNT(*) FROM browser_hist").fetchone()[0]
            self.duplicates_removed = count_before - count_after

            main_conn.close()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to remove duplicates:\n{e}")

    def clean_urls(self):
        """
        Deletes rows from browser_hist if title is NULL/empty or if URL matches
        any filter lines. Then logs the summary in one line:
          Removed X duplicates, Y no-title, Z filtered. Q remain.
        Also updates the historytitle column with a simplified version of title,
        and removes temp_browserHistory.db.
        """
        if not os.path.exists("browserHistory.db"):
            messagebox.showwarning("Warning", "browserHistory.db does not exist. Please save history first.")
            return

        lines = [line.strip() for line in self.filter_text.get("1.0", tk.END).splitlines() if line.strip()]

        try:
            conn = sqlite3.connect("browserHistory.db")
            cursor = conn.cursor()

            # Count before
            count_before = cursor.execute("SELECT COUNT(*) FROM browser_hist").fetchone()[0]

            # Remove no-title rows
            sql_no_title = "DELETE FROM browser_hist WHERE title IS NULL OR title = ''"
            cursor.execute(sql_no_title)
            conn.commit()
            after_no_title = cursor.execute("SELECT COUNT(*) FROM browser_hist").fetchone()[0]
            no_title_removed = count_before - after_no_title

            # Remove filter lines in URL
            filtered_removed = 0
            for f in lines:
                before_filter = cursor.execute("SELECT COUNT(*) FROM browser_hist").fetchone()[0]
                cursor.execute("DELETE FROM browser_hist WHERE url LIKE ?", (f"%{f}%",))
                conn.commit()
                after_filter = cursor.execute("SELECT COUNT(*) FROM browser_hist").fetchone()[0]
                filtered_removed += (before_filter - after_filter)

            # Replace 'spankbang.party' with 'spankbang.com' in the URL column
            cursor.execute("UPDATE browser_hist SET url = REPLACE(url, 'spankbang.party', 'spankbang.com')")
            conn.commit()

            # Update historytitle column by converting title using the simplified function.
            # The function keeps only alphanumeric characters and converts to lowercase.
            cursor.execute("SELECT id, title FROM browser_hist WHERE title IS NOT NULL AND title <> ''")
            rows = cursor.fetchall()
            for row in rows:
                row_id, title = row
                # Build the simplified title: keep only alphanumeric characters and lowercase it.
                simple_title = "".join(ch for ch in title if ch.isalnum()).lower()
                cursor.execute("UPDATE browser_hist SET historytitle = ? WHERE id = ?", (simple_title, row_id))
            conn.commit()

            # Final count
            remaining = cursor.execute("SELECT COUNT(*) FROM browser_hist").fetchone()[0]

            lines_str = " ".join(f"\"{l}\"" for l in lines)
            duplicates_removed = getattr(self, 'duplicates_removed', 0)

            # Single summary line
            logger.info(
                f"Removed {duplicates_removed} duplicate URLs, "
                f"{no_title_removed} entries with no title, "
                f"{filtered_removed} entries with containing {lines_str} in URL. "
                f"{remaining} entries remain."
            )
            logger.info("Generated simplified titles in column historytitle.")

            conn.close()

            # Remove temp file
            if os.path.exists("temp_browserHistory.db"):
                os.remove("temp_browserHistory.db")
                logger.info(f"Deleted {os.path.abspath('temp_browserHistory.db')}")

            messagebox.showinfo("Clean Complete", "Specified rows removed.")
            self.repack_database()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to clean URLs:\n{e}")

    def repack_database(self):
        """
        Repack (VACUUM) the database to optimize and compact it.
        See https://sqlite.org/lang_vacuum.html
        """
        try:
            conn = sqlite3.connect("browserHistory.db")
            conn.execute("VACUUM")
            conn.commit()
            conn.close()
        except Exception as e:
            messagebox.showwarning("Warning", f"Failed to repack the database:\n{e}")


###################################################################
# Main GUI Application
###################################################################
class FirefoxHistoryGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Firefox History Scene Updater")
        self.geometry("1200x1000")
        self.minsize(800, 800)

        # Custom style to reduce Checkbutton padding.
        self.style = ttk.Style(self)
        self.style.configure("my.TCheckbutton", padding=0)

        self.scenes = []
        self.current_index = 0
        self.stash = None

        # Create a threading event for pause/resume control.
        self.pause_event = threading.Event()
        self.pause_event.set()  # Initially running

        # Arrays for widget references.
        self.scene_num_labels = []
        self.checkbox_vars = []
        self.diff_labels = []
        self.url_labels = []
        self.skip_organized_var = tk.BooleanVar(value=True)  # default = True
        self.all_checked = True

        # ==================== TOP FRAME ====================
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(top_frame, text="Scheme:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.scheme_var = tk.StringVar(value="http")
        ttk.Entry(top_frame, textvariable=self.scheme_var, width=8).grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(top_frame, text="Host:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=2)
        self.host_var = tk.StringVar(value="localhost")
        ttk.Entry(top_frame, textvariable=self.host_var, width=15).grid(row=0, column=3, padx=5, pady=2)

        ttk.Label(top_frame, text="Port:").grid(row=0, column=4, sticky=tk.W, padx=5, pady=2)
        self.port_var = tk.StringVar(value="9999")
        ttk.Entry(top_frame, textvariable=self.port_var, width=8).grid(row=0, column=5, padx=5, pady=2)

        ttk.Label(top_frame, text="ApiKey:").grid(row=0, column=6, sticky=tk.W, padx=5, pady=2)
        self.apikey_var = tk.StringVar(value="")
        ttk.Entry(top_frame, textvariable=self.apikey_var, width=20).grid(row=0, column=7, padx=5, pady=2)

        ttk.Label(top_frame, text="Start Scene ID:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.start_id_var = tk.StringVar()
        self.start_id_entry = ttk.Entry(top_frame, textvariable=self.start_id_var, width=10)
        self.start_id_entry.grid(row=1, column=1, padx=5, pady=2)

        self.end_id_label = ttk.Label(top_frame, text="End Scene ID: Unknown", foreground="blue")
        self.end_id_label.grid(row=1, column=2, columnspan=2, padx=5, pady=2, sticky=tk.W)

        self.load_button = ttk.Button(top_frame, text="Load Scenes", command=self.load_scenes)
        self.load_button.grid(row=1, column=4, padx=10, pady=2)

        self.debug_var = tk.BooleanVar()
        self.debug_check = ttk.Checkbutton(top_frame, text="Enable Debug Logging", variable=self.debug_var,
                                           command=self.toggle_debug)
        self.debug_check.grid(row=1, column=5, padx=10, pady=2)
        self.skip_organized_check = ttk.Checkbutton(
            top_frame,
            text="Skip Organized Scenes",
            variable=self.skip_organized_var
        )
        # Position it in the same row as the others (adjust column if needed)
        self.skip_organized_check.grid(row=1, column=6, padx=10, pady=2)
        self.backward_button = ttk.Button(top_frame, text="<< Backward", command=self.backward_block)
        self.backward_button.grid(row=1, column=7, padx=5, pady=2)
        self.forward_button = ttk.Button(top_frame, text="Forward >>", command=self.forward_block)
        self.forward_button.grid(row=1, column=8, padx=5, pady=2)

        # Updated Copy button now opens our new popup.
        self.copy_button = ttk.Button(top_frame, text="Process Browser History DB", command=self.copy_places_db)
        self.copy_button.grid(row=2, column=0, padx=5, pady=2, sticky=tk.W)

        self.modtime_label = ttk.Label(top_frame, text="Mod time: Unknown", foreground="blue")
        self.modtime_label.grid(row=2, column=1, columnspan=3, padx=5, pady=2, sticky=tk.W)

        # ==================== SCROLLABLE MIDDLE FRAME ====================
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.canvas = tk.Canvas(container)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.scrollbar.pack(side="right", fill="y")

        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        for i in range(TARGET_SCENE_COUNT):
            row_frame = ttk.Frame(self.scrollable_frame)
            row_frame.pack(fill=tk.X, padx=2, pady=2)

            scene_label = ttk.Label(row_frame, text=f"Scene {i+1}", width=10, anchor="w")
            scene_label.pack(side="left", padx=(5,5))

            checkbox_var = tk.BooleanVar(value=True)
            checkbox = ttk.Checkbutton(row_frame, variable=checkbox_var, style="my.TCheckbutton")
            checkbox.pack(side="left", padx=(5,5))

            diff_label = ttk.Label(row_frame, text="", width=120, anchor="w", justify="left", wraplength=800)
            diff_label.pack(side="left", padx=(5,5))

            url_label = ttk.Label(row_frame, text="", width=100, anchor="w")
            url_label.pack(side="left", padx=(5,5))

            self.scene_num_labels.append(scene_label)
            self.checkbox_vars.append(checkbox_var)
            self.diff_labels.append(diff_label)
            self.url_labels.append(url_label)

        # ==================== BOTTOM FRAME ====================
        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X, padx=5, pady=5)

        self.accept_button = ttk.Button(button_frame, text="Accept / Update URLs", command=self.accept_candidates)
        self.accept_button.pack(side=tk.LEFT, padx=5)
        self.refresh_button = ttk.Button(button_frame, text="Refresh", command=self.refresh_candidates)
        self.refresh_button.pack(side=tk.LEFT, padx=5)
        self.toggle_check_button = ttk.Button(button_frame, text="Uncheck All", command=self.toggle_check_all)
        self.toggle_check_button.pack(side=tk.LEFT, padx=5)
        self.help_button = ttk.Button(button_frame, text="Help", command=self.show_help)
        self.help_button.pack(side=tk.LEFT, padx=5)
        self.pause_button = ttk.Button(button_frame, text="Pause", command=self.toggle_pause)
        self.pause_button.pack(side=tk.LEFT, padx=5)
        self.sync_side_button = ttk.Button(button_frame, text="Sync Scene File Summary", command=self.sync_scene_file_summary)
        self.sync_side_button.pack(side=tk.LEFT, padx=5)

        log_frame = ttk.LabelFrame(self, text="Log Output")
        log_frame.pack(fill=tk.X, expand=False, padx=5, pady=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, state='disabled', wrap=tk.WORD, height=20)
        self.log_text.tag_config('match_found', foreground='blue')
        self.log_text.tag_config('update_complete', foreground='dark green')
        self.log_text.pack(fill=tk.X, expand=False)
        text_handler = TextHandler(self.log_text)
        text_handler.setFormatter(formatter)
        logger.addHandler(text_handler)

        last_id = self.get_last_scene_id_from_log()
        self.start_id_var.set(str(last_id) if last_id else "1")

    def sleep_with_pause(self, duration):
        """
        Sleep in small increments while checking the pause event.
        """
        elapsed = 0
        increment = 0.1
        while elapsed < duration:
            if not self.pause_event.is_set():
                self.pause_event.wait()
            time.sleep(increment)
            elapsed += increment

    def toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_button.config(text="Resume")
            logger.info("Processing paused.")
        else:
            self.pause_event.set()
            self.pause_button.config(text="Pause")
            logger.info("Processing resumed.")

    def toggle_debug(self):
        if self.debug_var.get():
            logger.setLevel(logging.DEBUG)
            logger.info("Debug logging enabled.")
        else:
            logger.setLevel(logging.INFO)
            logger.info("Debug logging disabled.")

    def copy_places_db(self):
        """
        Open the new popup window for processing the browser history DB.
        """
        CopyPlacesPopup(self)

    def get_last_scene_id_from_log(self):
        """
        Attempt to find the last scene ID we loaded from the log file.
        """
        try:
            with open("log_fox.txt", "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in reversed(lines):
                match = re.search(r"Loaded scene (\d+)", line)
                if match:
                    return int(match.group(1))
        except Exception as e:
            logger.error(f"Error reading log file: {e}")
        return None

    def load_scenes(self):
        self.load_button.config(state="disabled")
        threading.Thread(target=self._load_scenes_thread, daemon=True).start()

    def _load_scenes_thread(self):
        try:
            self.stash = StashInterface({
                "scheme": self.scheme_var.get(),
                "Host": self.host_var.get(),
                "Port": self.port_var.get(),
                "ApiKey": self.apikey_var.get()
            })
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Error connecting to Stash: {e}"))
            self.after(0, lambda: self.load_button.config(state="normal"))
            return
        try:
            scenes_desc = self.stash.find_scenes({}, filter={"per_page": 1, "sort": "id", "direction": "DESC"})
            max_id = scenes_desc[0]["id"] if scenes_desc else "Unknown"
            self.end_id_label.config(text=f"End Scene ID: {max_id}")
        except Exception as e:
            self.end_id_label.config(text="End Scene ID: Unknown")
            logger.error(f"Error retrieving maximum scene id: {e}")

        valid_scenes = []
        try:
            start_id = int(self.start_id_var.get())
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Invalid start scene ID: {e}"))
            self.after(0, lambda: self.load_button.config(state="normal"))
            return

        sid = start_id
        # Attempt to load up to TARGET_SCENE_COUNT valid scenes
        while len(valid_scenes) < TARGET_SCENE_COUNT:
            self.pause_event.wait()
            scene = self.stash.find_scene(sid)
            sid += 1
            if not scene:
                logger.info(f"Scene {sid - 1} not found; skipping.")
                self.sleep_with_pause(0.2)
                # If we've exceeded the known max ID, we stop.
                if max_id != "Unknown" and sid > int(max_id):
                    break
                continue
            # Change: check "organized" as integer (1 = yes, 0 = no)
            if self.skip_organized_var.get() and scene.get("organized", 0) == 1:
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
            candidates = self.get_firefox_urls(base_filename)
            if not candidates:
                logger.info(f"Scene {scene.get('id')} no matches")
                self.sleep_with_pause(0.2)
                continue

            candidate_title, candidate_url = candidates[0]
            existing_urls = scene.get("urls", [])
            # Avoid duplication if the exact URL is already attached
            if existing_urls and any(
                (isinstance(url_obj, dict) and url_obj.get("url", "") == candidate_url) or
                (not isinstance(url_obj, dict) and url_obj == candidate_url)
                for url_obj in existing_urls
            ):
                logger.info(f"Scene {scene.get('id')} URL already exists")
                self.sleep_with_pause(0.2)
                continue

            valid_scenes.append(scene)
            self.log_text.tag_config('match_found', foreground='blue')
            logger.info(f"Scene {scene.get('id')} Match found - {base_filename} with browser {candidate_title} - {candidate_url}")
            self.sleep_with_pause(0.2)

        next_start = sid
        self.after(0, lambda: self._finish_load_scenes(valid_scenes, max_id, next_start))

    def _finish_load_scenes(self, valid_scenes, max_id, next_start):
        self.scenes = valid_scenes
        self.end_id_label.config(text=f"End Scene ID: {max_id}")
        self.start_id_var.set(str(next_start))
        self.current_index = 0
        self.load_current_scenes()
        self.load_button.config(state="normal")

    def forward_block(self):
        self.load_scenes()

    def backward_block(self):
        messagebox.showinfo("Info", "Backward navigation is not implemented in this version.")

    def load_current_scenes(self):
        """
        Display up to TARGET_SCENE_COUNT scenes in the middle panel,
        showing base filename vs. candidate browser historytitle.
        """
        for i in range(TARGET_SCENE_COUNT):
            if i >= len(self.scenes):
                self.scene_num_labels[i].config(text="Scene NA")
                self.diff_labels[i].config(text="N/A\nN/A")
                self.url_labels[i].config(text="No URL")
                self.checkbox_vars[i].set(False)
                continue

            scene = self.scenes[i]
            scene_id = scene["id"]
            files = scene.get("files")
            filename = "No file found"
            candidate_title = "(none)"
            candidate_url = ""
            if files and len(files) > 0:
                fname = os.path.basename(files[0]["path"])
                filename = os.path.splitext(fname)[0]

            # Compute the cleaned filename (clean_base)
            clean_base = self.clean_filename(filename)

            cands = self.get_firefox_urls(filename)
            if cands:
                candidate_title, candidate_url = cands[0]
                if not candidate_title.strip():
                    candidate_title = candidate_url

            try:
                self.scene_num_labels[i].config(text=f"Scene {int(scene_id):5d}")
            except Exception:
                self.scene_num_labels[i].config(text=f"Scene {scene_id}")

            self.diff_labels[i].config(text=f"{clean_base}\n{candidate_title}")
            self.url_labels[i].config(text=candidate_url if candidate_url else "No URL found")
            self.checkbox_vars[i].set(True)
            self.sleep_with_pause(0.1)

    def clean_filename(self, filename: str) -> str:
        """
        Cleans the filename by first removing the .mp4 extension (if present),
        then removing a trailing dash-number suffix (e.g. "-01"), and finally
        stripping out any non-alphanumeric characters and converting to lowercase.

        Example:
            "myscene-02.mp4" -> "myscene"
        """
        # Remove the .mp4 extension if present
        if filename.lower().endswith(".mp4"):
            filename = filename[:-4]
        # Remove any trailing dash followed by two digits
        filename = remove_dash_number_suffix(filename)
        # Remove any remaining non-alphanumeric characters and convert to lowercase
        return sanitize_for_windows(filename)

    def get_firefox_urls(self, base_filename):
        """
        Query ./browserHistory.db (table browser_hist) for matching 'historytitle' ~ base_filename.
        We now use a fully cleaned version of the filename (using clean_filename) so that any
        trailing '-##' is removed before matching.
        Returns a list of (historytitle, url) tuples or an empty list.
        """
        clean_base = self.clean_filename(base_filename)
        substring = clean_base
        db_path = os.path.abspath("./browserHistory.db")
        #logger.info(f"Using Browser History database at: {db_path}")
        #logger.info(f"Base filename: '{base_filename}', Clean base: '{clean_base}', Substring: '{substring}'")

        if not os.path.exists(db_path):
            logger.error(f"Browser History database not found at {db_path}")
            return []

        try:
            conn = sqlite3.connect(db_path)
        except Exception as e:
            logger.error(f"Error connecting to Browser History database: {e}")
            return []

        cursor = conn.cursor()
        try:
            sql_query = "SELECT historytitle, url FROM browser_hist WHERE historytitle LIKE ?"
            param = "%" + substring + "%"
            cursor.execute(sql_query, (param,))
            results = cursor.fetchall()
           # logger.info(f"Found {len(results)} results from query using param '{param}'")
        except Exception as e:
            logger.error(f"Query error: {e}")
            conn.close()
            return []

        conn.close()

        # Filter out known domains from the results
        filter_domains = ["localhost", "google.com", "tgtube.com", "dinotube.com"]
        filtered = [
            (ht, u) for (ht, u) in results
            if u and all(d not in u.lower() for d in filter_domains) and ht
        ]
       # logger.info(f"Filtered down to {len(filtered)} results after domain filtering")

        # Only return the candidate if its historytitle starts with our clean base
        for candidate_historytitle, candidate_url in filtered:
            if candidate_historytitle.startswith(clean_base):
                #logger.info(f"Candidate matches for '{clean_base}': '{candidate_historytitle}' (URL: {candidate_url})")
                return [(candidate_historytitle, candidate_url)]

        return []

    def accept_candidates(self):
        """
        Threaded operation to attach candidate URLs to each checked scene in Stash,
        tagging them with 'URLHistory' if not already present.
        """
        threading.Thread(target=self._accept_candidates_thread, daemon=True).start()

    def _accept_candidates_thread(self):
        updated_scenes_count = 0
        for i in range(TARGET_SCENE_COUNT):
            self.pause_event.wait()
            if i >= len(self.scenes):
                break
            scene = self.scenes[i]
            scene_id = scene["id"]
            if self.checkbox_vars[i].get():
                selected_url = self.url_labels[i].cget("text")
                if selected_url.startswith("http"):
                    existing_urls = scene.get("urls", [])
                    # Check if the URL already exists (it may be stored as a string or in a dict)
                    if existing_urls and any(
                            (isinstance(url_obj, str) and url_obj == selected_url) or
                            (isinstance(url_obj, dict) and url_obj.get("url", "") == selected_url)
                            for url_obj in existing_urls
                    ):
                        logger.info(f"Scene {scene_id}: Candidate URL already exists; skipping update")
                        continue
                    # Append the new URL as a string to the existing list.
                    updated_urls = existing_urls + [selected_url]
                    try:
                        tag = self.stash.find_tag("URLHistory", create=True)
                        self.stash.update_scene({
                            'id': scene_id,
                            'urls': updated_urls,
                            'tag_ids': [tag['id']]
                        })
                        self.log_text.tag_config('update_complete', foreground='dark green')
                        logger.info(f"Scene {scene_id} Updated and tagged 'URLHistory' - {selected_url}")
                        updated_scenes_count += 1
                    except Exception as e:
                        logger.error(f"Error updating scene {scene_id}: {e}")
                else:
                    logger.info(f"Scene {scene_id}: No valid URL to update.")
            else:
                logger.info(f"Scene {scene_id}: Checkbox not selected; skipping.")
            self.sleep_with_pause(0.2)

        self.after(0, self.load_scenes)
        if updated_scenes_count == 0:
            self.after(0, lambda: messagebox.showinfo("Skipped", "No URLs were saved."))

    def refresh_candidates(self):
        if self.scenes:
            self.load_current_scenes()

    def toggle_check_all(self):
        self.all_checked = not self.all_checked
        if self.all_checked:
            self.toggle_check_button.config(text="Uncheck All")
        else:
            self.toggle_check_button.config(text="Check All")
        for checkbox_var in self.checkbox_vars:
            checkbox_var.set(self.all_checked)

    def show_help(self):
        help_text = (
            "Instructions:\n\n"
            "1. Click 'Process Browser History DB' and use 'Select History' to choose a DB file.\n"
            "2. Valid tables (with 'url' and 'title') will be shown. If 'browser_hist' is found, it’s used.\n"
            "3. Click 'Save History' to import into browserHistory.db.\n"
            "4. Optionally click 'Clean URLs' to remove duplicates, empty titles, or filter patterns.\n"
            "5. Return to the main window, click 'Load Scenes' to see candidate URLs.\n"
            "6. Check/uncheck as needed, then click 'Accept / Update URLs' to push them into Stash.\n"
        )
        messagebox.showinfo("Help", help_text)

    def sync_scene_file_summary(self):
        """
        Sync URLs from a side DB's scene_file_summary table into Stash scenes.
        (Unrelated to the new browser_hist logic but remains in code.)
        """
        file_path = filedialog.askopenfilename(
            title="Select Scene File Summary Database",
            filetypes=[("SQLite DB", "*.sqlite"), ("All Files", "*.*")]
        )
        if not file_path:
            return
        threading.Thread(target=self._sync_scene_file_summary_thread, args=(file_path,), daemon=True).start()

    def _sync_scene_file_summary_thread(self, db_path):
        if self.stash is None:
            try:
                self.stash = StashInterface({
                    "scheme": self.scheme_var.get(),
                    "Host": self.host_var.get(),
                    "Port": self.port_var.get(),
                    "ApiKey": self.apikey_var.get()
                })
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", f"Error connecting to Stash: {e}"))
                return
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scene_file_summary'")
            if not cursor.fetchone():
                self.after(0, lambda: messagebox.showerror("Error", "Table 'scene_file_summary' not found."))
                conn.close()
                return

            cursor.execute("SELECT scene_id, url_1 FROM scene_file_summary WHERE url_1 IS NOT NULL AND TRIM(url_1) <> ''")
            rows = cursor.fetchall()
            conn.close()

        except Exception as e:
            logger.error(f"Error processing side DB: {e}")
            self.after(0, lambda: messagebox.showerror("Error", f"Error processing side DB: {e}"))
            return

        if not rows:
            self.after(0, lambda: messagebox.showinfo("Info", "No rows with valid URL found in scene_file_summary."))
            return

        updated_count = 0
        for scene_id, url in rows:
            self.pause_event.wait()
            if not url.lower().startswith("http"):
                logger.info(f"Scene {scene_id}: URL '{url}' is not valid, skipping.")
                continue
            try:
                scene = self.stash.find_scene(scene_id)
            except Exception as e:
                logger.error(f"Error retrieving scene {scene_id}: {e}")
                continue
            if not scene:
                logger.info(f"Scene {scene_id} not found in Stash; skipping.")
                continue
            existing_urls = scene.get("urls", [])
            if existing_urls and any(
                (isinstance(url_obj, dict) and url_obj.get("url", "") == url) or
                (not isinstance(url_obj, dict) and url_obj == url)
                for url_obj in existing_urls
            ):
                logger.info(f"Scene {scene_id}: URL '{url}' already exists; skipping.")
                continue
            logger.info(f"Scene {scene_id}: Syncing URL from side DB: {url}")
            try:
                tag = self.stash.find_tag("URLHistory", create=True)
                self.stash.update_scene({
                    'id': scene_id,
                    'url': url,
                    'tag_ids': [tag['id']]
                })
                updated_count += 1
            except Exception as e:
                logger.error(f"Error updating scene {scene_id}: {e}")
            self.sleep_with_pause(0.1)

        self.after(0, lambda: messagebox.showinfo("Sync Complete", f"Synced URLs for {updated_count} scenes."))


if __name__ == '__main__':
    app = FirefoxHistoryGUI()
    app.mainloop()
