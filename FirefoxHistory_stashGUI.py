#!/usr/bin/env python3
"""
FirefoxHistory_stashGUI.py
https://github.com/ratchetapps/mozhisStashGUI

A Tkinter-based GUI for updating scene URLs in StashApps. This application enables you to:
  - Query the maximum scene ID from StashApps.
  - Search forward through scenes with pause/resume functionality.
  - Update scene URLs in StashApps.
  - Clean the Firefox history database (places.sqlite).
  - Match candidate URLs from Firefox history while skipping duplicates.

Dependencies:
  - stashapi (version 0.27.2)

All other libraries (os, sqlite3, tkinter, etc.) are part of the Python standard library.

100% generated using ChatGPT.
"""

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

from stashapi.stashapp import StashInterface
import stashapi.log as log

# Global constants
TEST_USER = "YOUR-USERNAME-HERE"           # Update with your Windows username if needed.
TARGET_SCENE_COUNT = 10       # Number of scenes to load per block.

###################################################################
# Utility Functions
###################################################################
def sanitize_for_windows(filename: str) -> str:
    """
    Remove disallowed characters from a filename:
      - If filename ends with ".mp4", remove the extension.
      - Remove all non-alphanumeric characters.
      - Convert to lowercase.
    """
    if filename.lower().endswith(".mp4"):
        filename = filename[:-4]  # Remove extension
    filename = "".join(ch for ch in filename if ch.isalnum())
    return filename.lower()

###################################################################
# Logging Setup
###################################################################
logger = logging.getLogger("FirefoxHistoryGUI")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler = logging.FileHandler("log_fox.txt", mode="w")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

class TextHandler(logging.Handler):
    """
    Custom logging handler to display logs in a Tkinter Text widget.
    """
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record) + "\n"
        def append():
            self.text_widget.configure(state='normal')
            self.text_widget.insert(tk.END, msg)
            self.text_widget.configure(state='disabled')
            self.text_widget.yview(tk.END)
        self.text_widget.after(0, append)

###################################################################
# Helper to Highlight Differences (Unused; retained for future use)
###################################################################
def highlight_two_lines(text_widget: tk.Text, lineA: str, lineB: str):
    """
    Insert lineA and lineB into the text widget with partial highlights:
      - Equal segments in black.
      - Differences in red (lineA) and blue (lineB).
    This function is currently not used.
    """
    text_widget.config(state='normal')
    text_widget.delete("1.0", tk.END)
    text_widget.tag_config("equalA", foreground="black")
    text_widget.tag_config("equalB", foreground="black")
    text_widget.tag_config("diffA", foreground="red")
    text_widget.tag_config("diffB", foreground="blue")
    s = difflib.SequenceMatcher(None, lineA, lineB)
    idxA, idxB = "1.0", "2.0"
    for tag, i1, i2, j1, j2 in s.get_opcodes():
        segA = lineA[i1:i2]
        segB = lineB[j1:j2]
        if tag == "equal":
            text_widget.insert(idxA, segA, ("equalA",))
            text_widget.insert(idxB, segB, ("equalB",))
        elif tag == "replace":
            text_widget.insert(idxA, segA, ("diffA",))
            text_widget.insert(idxB, segB, ("diffB",))
        elif tag == "delete":
            text_widget.insert(idxA, segA, ("diffA",))
        elif tag == "insert":
            text_widget.insert(idxB, segB, ("diffB",))
    text_widget.config(state='disabled')

###################################################################
# Main GUI Class
###################################################################
class FirefoxHistoryGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Firefox History Scene Updater")
        self.geometry("1200x800")
        self.minsize(800, 600)

        # Custom style to reduce checkbutton padding
        self.style = ttk.Style(self)
        self.style.configure("my.TCheckbutton", padding=0)

        # Initialize instance variables
        self.scenes = []            # Valid scene objects
        self.current_index = 0      # Index of current scene
        self.stash = None           # Instance of StashInterface
        self.loading_paused = False # Flag to pause scene loading

        # Arrays to hold row widgets
        self.scene_num_labels = []
        self.checkbox_vars = []
        self.diff_labels = []       # To display file base name and candidate title
        self.url_labels = []        # To display candidate URL
        self.all_checked = True

        # Build GUI sections
        self.build_top_frame()
        self.build_middle_frame()
        self.build_bottom_frame()
        self.build_log_frame()

        # Set the starting scene ID from log (or default to "1")
        last_id = self.get_last_scene_id_from_log()
        self.start_id_var.set(str(last_id) if last_id else "1")

    # ------------------- Top Frame -------------------
    def build_top_frame(self):
        """Build the top frame with connection details and control buttons."""
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=tk.X, padx=10, pady=5)

        # Connection details
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

        # Scene ID and control buttons
        ttk.Label(top_frame, text="Start Scene ID:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.start_id_var = tk.StringVar()
        self.start_id_entry = ttk.Entry(top_frame, textvariable=self.start_id_var, width=10)
        self.start_id_entry.grid(row=1, column=1, padx=5, pady=2)
        self.end_id_label = ttk.Label(top_frame, text="End Scene ID: Unknown", foreground="blue")
        self.end_id_label.grid(row=1, column=2, columnspan=2, padx=5, pady=2, sticky=tk.W)

        self.query_max_button = ttk.Button(top_frame, text="Query Max", command=self.query_max_scene)
        self.query_max_button.grid(row=1, column=4, padx=10, pady=2)
        self.play_button = ttk.Button(top_frame, text="Play", command=self.forward_block)
        self.play_button.grid(row=1, column=5, padx=5, pady=2)
        self.pause_button = ttk.Button(top_frame, text="Pause", command=self.pause_loading)
        self.pause_button.grid(row=1, column=6, padx=5, pady=2)

        self.copy_button = ttk.Button(top_frame, text="Copy places.sqlite", command=self.copy_places_db)
        self.copy_button.grid(row=2, column=0, padx=5, pady=2, sticky=tk.W)
        self.modtime_label = ttk.Label(top_frame, text="Mod time: Unknown", foreground="blue")
        self.modtime_label.grid(row=2, column=1, columnspan=3, padx=5, pady=2, sticky=tk.W)
        self.remove_bad_urls_button = ttk.Button(top_frame, text="Remove bad URLs from temp db history",
                                                  command=self.remove_bad_urls_temp_db)
        self.remove_bad_urls_button.grid(row=2, column=4, padx=5, pady=2, sticky=tk.W)

    # ------------------- Middle Frame -------------------
    def build_middle_frame(self):
        """Build the scrollable middle frame for displaying scene details."""
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.canvas = tk.Canvas(container)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.scrollbar.pack(side="right", fill="y")
        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # Create TARGET_SCENE_COUNT rows for scene info.
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

    # ------------------- Bottom Frame -------------------
    def build_bottom_frame(self):
        """Build the bottom frame with action buttons."""
        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        self.accept_button = ttk.Button(button_frame, text="Accept & Update URLs", command=self.accept_candidates)
        self.accept_button.pack(side=tk.LEFT, padx=5)
        self.refresh_button = ttk.Button(button_frame, text="Refresh", command=self.refresh_candidates)
        self.refresh_button.pack(side=tk.LEFT, padx=5)
        self.toggle_check_button = ttk.Button(button_frame, text="Uncheck All", command=self.toggle_check_all)
        self.toggle_check_button.pack(side=tk.LEFT, padx=5)
        self.help_button = ttk.Button(button_frame, text="Help", command=self.show_help)
        self.help_button.pack(side=tk.LEFT, padx=5)

    # ------------------- Log Frame -------------------
    def build_log_frame(self):
        """Build the log output frame."""
        log_frame = ttk.LabelFrame(self, text="Log Output")
        log_frame.pack(fill=tk.BOTH, expand=False, padx=5, pady=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, state='disabled', wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        text_handler = TextHandler(self.log_text)
        text_handler.setFormatter(logger.handlers[0].formatter)
        logger.addHandler(text_handler)

    # ------------------- Database Cleaning -------------------
    def remove_bad_urls_temp_db(self):
        """
        Copy the Firefox history database (places.sqlite) to a modified file,
        then remove unwanted URLs and sanitize titles.
        """
        user_profile = os.environ.get("USERPROFILE", "")
        original_db = os.path.join(user_profile, "Desktop", "places.sqlite")
        modified_db = os.path.join(user_profile, "Desktop", "places_modified.sqlite")
        try:
            shutil.copy2(original_db, modified_db)
            logger.info(f"Copied DB to {modified_db} for cleaning.")
        except Exception as copy_err:
            logger.error(f"Error copying DB: {copy_err}")
            messagebox.showerror("Error", f"Could not copy database: {copy_err}")
            return
        conn = None
        try:
            conn = sqlite3.connect(modified_db)
            cursor = conn.cursor()
            rows_removed_google = cursor.execute("DELETE FROM moz_places WHERE url LIKE '%google.com%'").rowcount
            rows_removed_dino = cursor.execute("DELETE FROM moz_places WHERE url LIKE '%dinotube.com%'").rowcount
            rows_removed_tg = cursor.execute("DELETE FROM moz_places WHERE url LIKE '%tgtube.com%'").rowcount
            rows_removed_local = cursor.execute("DELETE FROM moz_places WHERE url LIKE '%localhost%'").rowcount
            rows_removed_empty = cursor.execute("DELETE FROM moz_places WHERE title IS NULL").rowcount
            logger.info(f"Removed {rows_removed_google} google rows, {rows_removed_dino} dino rows, "
                        f"{rows_removed_tg} tgtube rows, {rows_removed_local} localhost rows, "
                        f"{rows_removed_empty} empty/NULL title rows.")
            # Sanitize remaining titles.
            cursor.execute("SELECT id, title FROM moz_places WHERE title IS NOT NULL")
            rows = cursor.fetchall()
            count_updates = 0
            for (row_id, current_title) in rows:
                cleaned = sanitize_for_windows(current_title)
                if cleaned != current_title:
                    cursor.execute("UPDATE moz_places SET title=? WHERE id=?", (cleaned, row_id))
                    count_updates += 1
            conn.commit()
            logger.info(f"Done cleaning. Updated {count_updates} titles in {modified_db}.")
            messagebox.showinfo("DB Cleaning Complete", f"Removed bad URLs and sanitized titles.\nUpdated {count_updates} titles.")
        except Exception as db_err:
            logger.error(f"Error during DB cleaning: {db_err}")
            messagebox.showerror("Error", f"DB cleaning error: {db_err}")
        finally:
            if conn:
                conn.close()

    # ------------------- Debug / Logging -------------------
    def toggle_debug(self):
        """Toggle debug logging on or off."""
        if self.debug_var.get():
            logger.setLevel(logging.DEBUG)
            logger.info("Debug logging enabled.")
        else:
            logger.setLevel(logging.INFO)
            logger.info("Debug logging disabled.")

    def get_last_scene_id_from_log(self):
        """Scan log_fox.txt for the last loaded scene ID."""
        try:
            with open("log_fox.txt", "r") as f:
                lines = f.readlines()
            for line in reversed(lines):
                match = re.search(r"Loaded scene (\d+)", line)
                if match:
                    return int(match.group(1))
        except Exception as e:
            logger.error(f"Error reading log file: {e}")
        return None

    def copy_places_db(self):
        """Allow the user to select a places.sqlite file and copy it to the Desktop."""
        initial_dir = r"C:\Users\2023f\AppData\Roaming\Mozilla\Firefox\Profiles"
        file_path = filedialog.askopenfilename(initialdir=initial_dir,
                                               title="Select places.sqlite",
                                               filetypes=[("SQLite DB", "places.sqlite")])
        if file_path:
            dest_path = os.path.join("C:\\Users", TEST_USER, "Desktop", "places.sqlite")
            try:
                shutil.copy2(file_path, dest_path)
                logger.info(f"Copied places.sqlite from {file_path} to {dest_path}.")
                mod_time = os.path.getmtime(dest_path)
                mod_time_str = time.ctime(mod_time)
                self.modtime_label.config(text=f"Mod time: {mod_time_str}")
            except Exception as e:
                logger.error(f"Error copying places.sqlite: {e}")
                messagebox.showerror("Error", f"Error copying file: {e}")

    # ------------------- Query Max Scene ID -------------------
    def query_max_scene(self):
        """Query and display the maximum scene ID from StashApps."""
        self.query_max_button.config(state="disabled")
        threading.Thread(target=self._query_max_scene_thread, daemon=True).start()

    def _query_max_scene_thread(self):
        try:
            self.stash = StashInterface({
                "scheme": self.scheme_var.get(),
                "Host": self.host_var.get(),
                "Port": self.port_var.get(),
                "ApiKey": self.apikey_var.get()
            })
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Error connecting to Stash: {e}"))
            self.after(0, lambda: self.query_max_button.config(state="normal"))
            return
        max_id = None
        try:
            scenes_desc = self.stash.find_scenes({}, filter={"per_page": 1, "sort": "id", "direction": "DESC"})
            if scenes_desc:
                max_id = int(scenes_desc[0]["id"])
        except Exception as e:
            logger.error(f"Error retrieving maximum scene id: {e}")
        self.after(0, lambda: self.end_id_label.config(text=f"Max Scene ID: {max_id if max_id is not None else 'Unknown'}"))
        self.after(0, lambda: self.query_max_button.config(state="normal"))

    # ------------------- Forward Scene Search (Play) -------------------
    def forward_block(self):
        """Triggered by the Play button. Start or resume forward scene search."""
        if self.loading_paused:
            self.loading_paused = False
            logger.info("Resumed loading.")
        else:
            self.load_scenes()

    def pause_loading(self):
        """Pause the current scene search."""
        self.loading_paused = True
        logger.info("Loading paused.")

    def load_scenes(self):
        """Initiate forward scene search to load TARGET_SCENE_COUNT scenes."""
        self.query_max_button.config(state="disabled")
        self.loading_paused = False
        threading.Thread(target=self._load_scenes_thread, daemon=True).start()

    def _load_scenes_thread(self):
        # Connect to Stash
        try:
            self.stash = StashInterface({
                "scheme": self.scheme_var.get(),
                "Host": self.host_var.get(),
                "Port": self.port_var.get(),
                "ApiKey": self.apikey_var.get()
            })
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Error connecting to Stash: {e}"))
            self.after(0, lambda: self.query_max_button.config(state="normal"))
            return

        # Query maximum scene ID
        max_id = "Unknown"
        try:
            scenes_desc = self.stash.find_scenes({}, filter={"per_page": 1, "sort": "id", "direction": "DESC"})
            if scenes_desc:
                max_id = int(scenes_desc[0]["id"])
        except Exception as e:
            logger.error(f"Error retrieving maximum scene id: {e}")
        self.after(0, lambda: self.end_id_label.config(text=f"Max Scene ID: {max_id if max_id is not None else 'Unknown'}"))
        self.after(0, lambda: self.query_max_button.config(state="normal"))

        valid_scenes = []
        try:
            start_id = int(self.start_id_var.get())
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Invalid start scene ID: {e}"))
            self.after(0, lambda: self.query_max_button.config(state="normal"))
            return

        sid = start_id
        # Loop until TARGET_SCENE_COUNT valid scenes are collected.
        while len(valid_scenes) < TARGET_SCENE_COUNT:
            try:
                scene = self.stash.find_scene(sid)
            except Exception as e:
                logger.error(f"Error retrieving scene {sid}: {e}")
                sid += 1
                continue
            sid += 1

            if not scene:
                logger.info(f"Scene {sid - 1} not found; skipping.")
                continue

            # Skip scenes with no files.
            files = scene.get("files")
            if not files or len(files) == 0:
                logger.info(f"Scene {scene.get('id')} has no files; skipping.")
                continue

            filename = os.path.basename(files[0]["path"])
            base_filename = os.path.splitext(filename)[0]
            candidates = self.get_firefox_urls(base_filename)
            if not candidates:
                logger.info(f"Scene {scene.get('id')} yielded no candidates; skipping.")
                continue

            # Retrieve top candidate.
            candidate_title, candidate_url = candidates[0]
            clean_candidate_title = sanitize_for_windows(candidate_title)
            clean_base_filename = sanitize_for_windows(base_filename)
            # Check that the candidate's cleansed title begins with the cleansed base filename.
            if not clean_candidate_title.startswith(clean_base_filename):
                logger.info(f"Scene {scene.get('id')}: candidate title '{candidate_title}' does not start with cleansed filename '{clean_base_filename}'; skipping.")
                continue

            # Duplicate URL check: use the scene's existing "urls" field.
            existing_urls = scene.get("urls", [])
            duplicate_found = False
            if existing_urls:
                for url_obj in existing_urls:
                    if isinstance(url_obj, dict):
                        existing_url = url_obj.get("url", "")
                    else:
                        existing_url = url_obj
                    # Compare the full candidate URL exactly.
                    if existing_url == candidate_url:
                        duplicate_found = True
                        break
            if duplicate_found:
                logger.info(f"Scene {scene.get('id')}: Candidate URL already exists; skipping scene.")
                continue

            valid_scenes.append(scene)
            logger.info(f"Scene {scene.get('id')} accepted for processing.")

        next_start = sid
        self.after(0, lambda: self._finish_load_scenes(valid_scenes, max_id, next_start))

    def _finish_load_scenes(self, valid_scenes, max_id, next_start):
        """Update the UI with the loaded valid scenes."""
        self.scenes = valid_scenes
        self.end_id_label.config(text=f"End Scene ID: {max_id}")
        self.start_id_var.set(str(next_start))
        self.current_index = 0
        self.load_current_scenes()
        self.load_button.config(state="normal")

    def forward_block(self):
        """Handler for the Forward (Play) button."""
        self.load_scenes()

    def backward_block(self):
        """Handler for the Backward button (not implemented)."""
        messagebox.showinfo("Info", "Backward navigation is not implemented in this version.")

    # ------------------- Firefox History Lookup -------------------
    def get_firefox_urls(self, base_filename):
        """
        Query the Firefox history database (places.sqlite) for candidate URLs.
        Process base_filename by removing any trailing numeric suffix and cleaning it
        to an all-lowercase alphanumeric string (clean_base). Then, filter the database
        using a substring from clean_base, clean each candidate title, and compute a match
        ratio using difflib. If a candidate's cleaned title starts exactly with clean_base,
        a perfect match (ratio 1.0) is assumed.
        Returns the top candidate if the score meets the threshold; otherwise, returns [].
        """
        import difflib

        # Remove trailing numeric suffix (e.g., "-01") and clean the base filename.
        base_filename_nosuffix = re.sub(r'-\d+$', '', base_filename)
        clean_base = sanitize_for_windows(base_filename_nosuffix)
        substring = clean_base[:3]
        desktop = os.path.join("C:\\Users", TEST_USER, "Desktop")
        db_path = os.path.join(desktop, "places.sqlite")
        logger.info(f"Using Firefox history database at: {db_path}")

        try:
            conn = sqlite3.connect(db_path)
        except Exception as e:
            logger.error(f"Error connecting to Firefox database: {e}")
            return []

        cursor = conn.cursor()
        try:
            sql_query = "SELECT title, url FROM moz_places WHERE url LIKE ?"
            param = "%" + substring + "%"
            cursor.execute(sql_query, (param,))
            results = cursor.fetchall()
        except Exception as e:
            logger.error(f"Query error: {e}")
            conn.close()
            return []
        conn.close()

        # Filter out unwanted domains.
        filtered = [
            (t, u) for (t, u) in results
            if u and "localhost" not in u.lower()
               and "google.com" not in u.lower()
               and "tgtube.com" not in u.lower()
               and "dinotube.com" not in u.lower()
               and t
        ]

        best_candidate = None
        best_ratio = 0.0
        for candidate_title, candidate_url in filtered:
            clean_candidate = sanitize_for_windows(candidate_title)
            if clean_candidate.startswith(clean_base):
                ratio = 1.0
            else:
                ratio = difflib.SequenceMatcher(None, clean_base, clean_candidate).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_candidate = (candidate_title, candidate_url)

        threshold = 0.9
        logger.info(f"Original filename: {base_filename}")
        logger.info(f"Filename without numeric suffix: {base_filename_nosuffix}")
        logger.info(f"clean_base: {clean_base}")
        logger.info(f"substring: {substring}")
        logger.info(f"best_candidate: {best_candidate}")
        logger.info(f"best_ratio: {best_ratio}")

        if best_candidate and best_ratio >= threshold:
            return [best_candidate]
        else:
            return []

    def normalize_text(self, s):
        """Normalize text by replacing punctuation with spaces and converting to lowercase."""
        translator = str.maketrans(string.punctuation, " " * len(string.punctuation))
        return s.translate(translator).lower().strip()

    # ------------------- Populate UI for Current Scenes -------------------
    def load_current_scenes(self):
        """
        For each of the TARGET_SCENE_COUNT rows, update the UI with:
          - Scene label ("Scene ####")
          - Diff label (base filename and candidate title on two lines)
          - URL label (candidate URL)
        """
        for i in range(TARGET_SCENE_COUNT):
            if i >= len(self.scenes):
                self.scene_num_labels[i].config(text="Scene ???")
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

            # Retrieve candidate URL from Firefox history lookup.
            cands = self.get_firefox_urls(filename)
            if cands:
                candidate_title, candidate_url = cands[0]
                if not candidate_title.strip():
                    candidate_title = candidate_url  # Fallback if title is empty

            try:
                self.scene_num_labels[i].config(text=f"Scene {int(scene_id):5d}")
            except Exception:
                self.scene_num_labels[i].config(text=f"Scene {scene_id}")

            self.diff_labels[i].config(text=f"{filename}\n{candidate_title}")
            self.url_labels[i].config(text=candidate_url if candidate_url else "No URL found")
            self.checkbox_vars[i].set(True)
            logger.info(f"Loaded scene {scene_id} with base filename '{filename}'.")

    # ------------------- Accept / Update Scenes -------------------
    def accept_candidates(self):
        """Start a thread to update selected scenes with the candidate URLs."""
        threading.Thread(target=self._accept_candidates_thread, daemon=True).start()

    def _accept_candidates_thread(self):
        updated_scenes_count = 0
        for i in range(TARGET_SCENE_COUNT):
            if i >= len(self.scenes):
                break
            scene = self.scenes[i]
            scene_id = scene["id"]
            if self.checkbox_vars[i].get():
                selected_url = self.url_labels[i].cget("text")
                # Duplicate URL check using the scene's "urls" field.
                existing_urls = scene.get("urls", [])
                if existing_urls and any((url_obj.get("url", "") if isinstance(url_obj, dict) else url_obj) == selected_url for url_obj in existing_urls):
                    logger.info(f"Scene {scene_id}: Candidate URL already exists; auto-moving to next scene.")
                    continue
                if selected_url.startswith("http"):
                    logger.info(f"Scene {scene_id}: Selected URL: {selected_url}")
                    try:
                        tag = self.stash.find_tag("URLHistory", create=True)
                        self.stash.update_scene({
                            'id': scene_id,
                            'url': selected_url,
                            'tag_ids': [tag['id']]
                        })
                        logger.info(f"Scene {scene_id} updated with URL and tagged 'URLHistory'.")
                        updated_scenes_count += 1
                    except Exception as e:
                        logger.error(f"Error updating scene {scene_id}: {e}")
                else:
                    logger.info(f"Scene {scene_id}: No valid URL to update.")
            else:
                logger.info(f"Scene {scene_id}: Checkbox not selected; skipping.")
        self.after(0, self.load_scenes)
        if updated_scenes_count == 0:
            self.after(0, lambda: messagebox.showinfo("Skipped", "No URLs were saved."))

    # ------------------- Refresh and Toggle Check -------------------
    def refresh_candidates(self):
        """Reload the current scenes in the UI."""
        if self.scenes:
            self.load_current_scenes()

    def toggle_check_all(self):
        """Toggle all scene checkboxes on or off."""
        self.all_checked = not self.all_checked
        if self.all_checked:
            self.toggle_check_button.config(text="Uncheck All")
        else:
            self.toggle_check_button.config(text="Check All")
        for checkbox_var in self.checkbox_vars:
            checkbox_var.set(self.all_checked)

    def show_help(self):
        """Display a help message with instructions."""
        help_text = (
            "Instructions:\n\n"
            "1. Enter your Stash server connection details (scheme, host, port, ApiKey).\n"
            "2. 'Start Scene ID' is loaded from the log or defaults to 1.\n"
            "3. Click 'Load Scenes' to fetch the next 10 valid scenes.\n"
            "4. Left column: 'Scene #####' label.\n"
            "5. Next column: Checkbox to select the scene for updating.\n"
            "6. Middle: File base name and candidate title on two lines (only if the candidate title begins exactly with the filename).\n"
            "7. Right column: The candidate's raw URL.\n"
            "8. 'Forward >>' loads the next block of scenes; 'Backward <<' is not implemented.\n"
            "9. 'Accept & Update URLs' updates selected scenes in Stash with the candidate URL.\n"
            "10. 'Remove bad URLs...' cleans and sanitizes places.sqlite on your Desktop.\n"
            "11. Scroll to view all 10 scenes if needed.\n"
        )
        messagebox.showinfo("Help", help_text)

    # ------------------- Forward Scene Search -------------------
    def forward_block(self):
        """Handler for the Forward (Play) button: initiate scene search."""
        self.load_scenes()

    def pause_loading(self):
        """Handler for the Pause button: pause scene search."""
        self.loading_paused = True
        logger.info("Loading paused.")

    def load_scenes(self):
        """Initiate forward scene search to load TARGET_SCENE_COUNT scenes."""
        self.query_max_button.config(state="disabled")
        self.loading_paused = False
        threading.Thread(target=self._load_scenes_thread, daemon=True).start()

    def _load_scenes_thread(self):
        # Connect to Stash
        try:
            self.stash = StashInterface({
                "scheme": self.scheme_var.get(),
                "Host": self.host_var.get(),
                "Port": self.port_var.get(),
                "ApiKey": self.apikey_var.get()
            })
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Error connecting to Stash: {e}"))
            self.after(0, lambda: self.query_max_button.config(state="normal"))
            return

        # Retrieve maximum scene ID.
        max_id = "Unknown"
        try:
            scenes_desc = self.stash.find_scenes({}, filter={"per_page": 1, "sort": "id", "direction": "DESC"})
            if scenes_desc:
                max_id = int(scenes_desc[0]["id"])
        except Exception as e:
            logger.error(f"Error retrieving maximum scene id: {e}")
        self.after(0, lambda: self.end_id_label.config(text=f"Max Scene ID: {max_id if max_id is not None else 'Unknown'}"))
        self.after(0, lambda: self.query_max_button.config(state="normal"))

        valid_scenes = []
        try:
            start_id = int(self.start_id_var.get())
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Invalid start scene ID: {e}"))
            self.after(0, lambda: self.query_max_button.config(state="normal"))
            return

        sid = start_id
        # Loop until TARGET_SCENE_COUNT valid scenes are collected.
        while len(valid_scenes) < TARGET_SCENE_COUNT:
            try:
                scene = self.stash.find_scene(sid)
            except Exception as e:
                logger.error(f"Error retrieving scene {sid}: {e}")
                sid += 1
                continue
            sid += 1

            if not scene:
                logger.info(f"Scene {sid - 1} not found; skipping.")
                continue

            # Skip scenes with no files.
            files = scene.get("files")
            if not files or len(files) == 0:
                logger.info(f"Scene {scene.get('id')} has no files; skipping.")
                continue

            filename = os.path.basename(files[0]["path"])
            base_filename = os.path.splitext(filename)[0]
            candidates = self.get_firefox_urls(base_filename)
            if not candidates:
                logger.info(f"Scene {scene.get('id')} yielded no candidates; skipping.")
                continue

            # Retrieve top candidate.
            candidate_title, candidate_url = candidates[0]
            clean_candidate_title = sanitize_for_windows(candidate_title)
            clean_base_filename = sanitize_for_windows(base_filename)
            if not clean_candidate_title.startswith(clean_base_filename):
                logger.info(f"Scene {scene.get('id')}: candidate title '{candidate_title}' does not start with cleansed filename '{clean_base_filename}'; skipping.")
                continue

            # --- Duplicate URL check: if candidate URL exists in scene's "urls" field, skip scene.
            existing_urls = scene.get("urls", [])
            duplicate_found = False
            if existing_urls:
                for url_obj in existing_urls:
                    if isinstance(url_obj, dict):
                        existing_url = url_obj.get("url", "")
                    else:
                        existing_url = url_obj
                    if existing_url == candidate_url:
                        duplicate_found = True
                        break
            if duplicate_found:
                logger.info(f"Scene {scene.get('id')}: Candidate URL already exists; skipping scene.")
                continue

            valid_scenes.append(scene)
            logger.info(f"Scene {scene.get('id')} accepted for processing.")

        next_start = sid
        self.after(0, lambda: self._finish_load_scenes(valid_scenes, max_id, next_start))

    def _finish_load_scenes(self, valid_scenes, max_id, next_start):
        """Update the UI with the loaded valid scenes."""
        self.scenes = valid_scenes
        self.end_id_label.config(text=f"End Scene ID: {max_id}")
        self.start_id_var.set(str(next_start))
        self.current_index = 0
        self.load_current_scenes()
        self.load_button.config(state="normal")

    # ------------------- Backward Scene Search -------------------
    def _load_scenes_backward_thread(self):
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
        valid_scenes = []
        try:
            start_id = int(self.start_id_var.get())
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Invalid start scene ID: {e}"))
            return
        sid = start_id
        while len(valid_scenes) < TARGET_SCENE_COUNT and sid > 0:
            while self.loading_paused:
                time.sleep(0.5)
            try:
                scene = self.stash.find_scene(sid)
            except Exception as e:
                logger.error(f"Error retrieving scene {sid}: {e}")
                sid -= 1
                continue
            sid -= 1
            if not scene:
                logger.info(f"Scene {sid + 1} not found; skipping.")
                continue
            if scene.get("urls", []) or scene.get("organized"):
                logger.info(f"Scene {scene.get('id')} has existing URLs or is organized; skipping.")
                continue
            files = scene.get("files")
            if not files or len(files) == 0:
                logger.info(f"Scene {scene.get('id')} has no files; skipping.")
                continue
            filename = os.path.basename(files[0]["path"])
            base_filename = os.path.splitext(filename)[0]
            candidates = self.get_firefox_urls(base_filename)
            if not candidates:
                logger.info(f"Scene {scene.get('id')} yielded no candidates; skipping.")
                continue
            candidate_title, candidate_url = candidates[0]
            if not candidate_title.startswith(base_filename):
                logger.info(f"Scene {scene.get('id')}: candidate title '{candidate_title}' does not start with filename '{base_filename}'; skipping.")
                continue
            valid_scenes.append(scene)
            logger.info(f"Scene {scene.get('id')} accepted for processing (backward).")
        next_start = sid if sid > 0 else 1
        self.after(0, lambda: self._finish_load_scenes(valid_scenes, "Unknown", next_start))

    def backward_block(self):
        """Handler for the Backward button."""
        self.query_max_button.config(state="disabled")
        self.loading_paused = False
        threading.Thread(target=self._load_scenes_backward_thread, daemon=True).start()

    # ------------------- Firefox History Lookup -------------------
    def get_firefox_urls(self, base_filename):
        """
        Query the Firefox history database (places.sqlite) for candidate URLs.
        Process the base_filename by:
          1. Removing any trailing numeric suffix (e.g. "-01").
          2. Cleaning it to an all-lowercase alphanumeric string (clean_base).
        Then, use a substring from clean_base to query the database and filter results.
        Each candidate title is cleaned similarly. If the cleaned candidate title starts exactly
        with clean_base, a perfect match (ratio 1.0) is assumed; otherwise, a fuzzy match ratio is computed.
        Returns the top candidate if its ratio meets the threshold.
        """
        import difflib

        # Remove trailing numeric suffix and clean the base filename.
        base_filename_nosuffix = re.sub(r'-\d+$', '', base_filename)
        clean_base = sanitize_for_windows(base_filename_nosuffix)
        substring = clean_base[:3]
        desktop = os.path.join("C:\\Users", TEST_USER, "Desktop")
        db_path = os.path.join(desktop, "places.sqlite")
        logger.info(f"Using Firefox history database at: {db_path}")

        try:
            conn = sqlite3.connect(db_path)
        except Exception as e:
            logger.error(f"Error connecting to Firefox database: {e}")
            return []
        cursor = conn.cursor()
        try:
            sql_query = "SELECT title, url FROM moz_places WHERE url LIKE ?"
            param = "%" + substring + "%"
            cursor.execute(sql_query, (param,))
            results = cursor.fetchall()
        except Exception as e:
            logger.error(f"Query error: {e}")
            conn.close()
            return []
        conn.close()

        # Filter out unwanted domains.
        filtered = [
            (t, u) for (t, u) in results
            if u and "localhost" not in u.lower()
               and "google.com" not in u.lower()
               and "tgtube.com" not in u.lower()
               and "dinotube.com" not in u.lower()
               and t
        ]

        best_candidate = None
        best_ratio = 0.0
        for candidate_title, candidate_url in filtered:
            clean_candidate = sanitize_for_windows(candidate_title)
            if clean_candidate.startswith(clean_base):
                ratio = 1.0
            else:
                ratio = difflib.SequenceMatcher(None, clean_base, clean_candidate).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_candidate = (candidate_title, candidate_url)

        threshold = 0.9
        logger.info(f"Original filename: {base_filename}")
        logger.info(f"Filename without numeric suffix: {base_filename_nosuffix}")
        logger.info(f"clean_base: {clean_base}")
        logger.info(f"substring: {substring}")
        logger.info(f"best_candidate: {best_candidate}")
        logger.info(f"best_ratio: {best_ratio}")

        if best_candidate and best_ratio >= threshold:
            return [best_candidate]
        else:
            return []

    def normalize_text(self, s):
        """Normalize text by replacing punctuation with spaces and converting to lowercase."""
        translator = str.maketrans(string.punctuation, " " * len(string.punctuation))
        return s.translate(translator).lower().strip()

    # ------------------- Populate UI -------------------
    def load_current_scenes(self):
        """
        Update the UI for each of the TARGET_SCENE_COUNT rows:
          - Scene label: "Scene ####"
          - Diff label: displays the file's base filename and candidate title (each on its own line)
          - URL label: displays the candidate's full URL.
        """
        for i in range(TARGET_SCENE_COUNT):
            if i >= len(self.scenes):
                self.scene_num_labels[i].config(text="Scene ???")
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
            # Retrieve candidate using Firefox history lookup.
            cands = self.get_firefox_urls(filename)
            if cands:
                candidate_title, candidate_url = cands[0]
                if not candidate_title.strip():
                    candidate_title = candidate_url  # fallback if title is empty
            try:
                self.scene_num_labels[i].config(text=f"Scene {int(scene_id):5d}")
            except Exception:
                self.scene_num_labels[i].config(text=f"Scene {scene_id}")
            self.diff_labels[i].config(text=f"{filename}\n{candidate_title}")
            self.url_labels[i].config(text=candidate_url if candidate_url else "No URL found")
            self.checkbox_vars[i].set(True)
            logger.info(f"Loaded scene {scene_id} with base filename '{filename}'.")

    # ------------------- Accept / Update Scenes -------------------
    def accept_candidates(self):
        """Start a thread to update selected scenes with candidate URLs."""
        threading.Thread(target=self._accept_candidates_thread, daemon=True).start()

    def _accept_candidates_thread(self):
        updated_scenes_count = 0
        for i in range(TARGET_SCENE_COUNT):
            if i >= len(self.scenes):
                break
            scene = self.scenes[i]
            scene_id = scene["id"]
            if self.checkbox_vars[i].get():
                selected_url = self.url_labels[i].cget("text")
                # Duplicate URL check using scene's "urls" field.
                existing_urls = scene.get("urls", [])
                if existing_urls and any((url_obj.get("url", "") if isinstance(url_obj, dict) else url_obj) == selected_url for url_obj in existing_urls):
                    logger.info(f"Scene {scene_id}: Candidate URL already exists; auto-moving to next scene.")
                    continue
                if selected_url.startswith("http"):
                    logger.info(f"Scene {scene_id}: Selected URL: {selected_url}")
                    try:
                        tag = self.stash.find_tag("URLHistory", create=True)
                        self.stash.update_scene({
                            'id': scene_id,
                            'url': selected_url,
                            'tag_ids': [tag['id']]
                        })
                        logger.info(f"Scene {scene_id} updated with URL and tagged 'URLHistory'.")
                        updated_scenes_count += 1
                    except Exception as e:
                        logger.error(f"Error updating scene {scene_id}: {e}")
                else:
                    logger.info(f"Scene {scene_id}: No valid URL to update.")
            else:
                logger.info(f"Scene {scene_id}: Checkbox not selected; skipping.")
        self.after(0, self.load_scenes)
        if updated_scenes_count == 0:
            self.after(0, lambda: messagebox.showinfo("Skipped", "No URLs were saved."))

    # ------------------- Refresh and Toggle Check -------------------
    def refresh_candidates(self):
        """Reload the current scenes in the UI."""
        if self.scenes:
            self.load_current_scenes()

    def toggle_check_all(self):
        """Toggle all checkboxes on or off."""
        self.all_checked = not self.all_checked
        if self.all_checked:
            self.toggle_check_button.config(text="Uncheck All")
        else:
            self.toggle_check_button.config(text="Check All")
        for checkbox_var in self.checkbox_vars:
            checkbox_var.set(self.all_checked)

    def show_help(self):
        """Display help instructions."""
        help_text = (
            "Instructions:\n\n"
            "1. Enter your Stash server connection details (scheme, host, port, ApiKey).\n"
            "2. 'Start Scene ID' is loaded from the log or defaults to 1.\n"
            "3. Click 'Load Scenes' to fetch the next 10 valid scenes.\n"
            "4. Left column: 'Scene #####' label.\n"
            "5. Next column: Checkbox to select the scene for updating.\n"
            "6. Middle: File base name and candidate title are shown on two lines (only if candidate title begins exactly with the filename).\n"
            "7. Right column: The candidate's raw URL.\n"
            "8. 'Forward >>' loads the next block of scenes; 'Backward <<' is not implemented.\n"
            "9. 'Accept & Update URLs' updates selected scenes in Stash with the candidate URL.\n"
            "10. 'Remove bad URLs...' cleans and sanitizes places.sqlite on your Desktop.\n"
            "11. Scroll to see all 10 scenes if necessary.\n"
        )
        messagebox.showinfo("Help", help_text)

    # ------------------- Main Scene Search (Forward / Play) -------------------
    def forward_block(self):
        """Handler for the Forward (Play) button."""
        self.load_scenes()

    def _load_scenes_thread(self):
        # Connect to StashApps
        try:
            self.stash = StashInterface({
                "scheme": self.scheme_var.get(),
                "Host": self.host_var.get(),
                "Port": self.port_var.get(),
                "ApiKey": self.apikey_var.get()
            })
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Error connecting to Stash: {e}"))
            self.after(0, lambda: self.query_max_button.config(state="normal"))
            return

        # Retrieve the maximum scene ID.
        max_id = "Unknown"
        try:
            scenes_desc = self.stash.find_scenes({}, filter={"per_page": 1, "sort": "id", "direction": "DESC"})
            if scenes_desc:
                max_id = int(scenes_desc[0]["id"])
        except Exception as e:
            logger.error(f"Error retrieving maximum scene id: {e}")
        self.after(0, lambda: self.end_id_label.config(text=f"Max Scene ID: {max_id if max_id is not None else 'Unknown'}"))
        self.after(0, lambda: self.query_max_button.config(state="normal"))

        valid_scenes = []
        try:
            start_id = int(self.start_id_var.get())
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Invalid start scene ID: {e}"))
            self.after(0, lambda: self.query_max_button.config(state="normal"))
            return

        sid = start_id
        # Loop until TARGET_SCENE_COUNT valid scenes are found.
        while len(valid_scenes) < TARGET_SCENE_COUNT:
            try:
                scene = self.stash.find_scene(sid)
            except Exception as e:
                logger.error(f"Error retrieving scene {sid}: {e}")
                sid += 1
                continue
            sid += 1
            if not scene:
                logger.info(f"Scene {sid - 1} not found; skipping.")
                continue

            # Skip scenes with no files.
            files = scene.get("files")
            if not files or len(files) == 0:
                logger.info(f"Scene {scene.get('id')} has no files; skipping.")
                continue

            filename = os.path.basename(files[0]["path"])
            base_filename = os.path.splitext(filename)[0]
            candidates = self.get_firefox_urls(base_filename)
            if not candidates:
                logger.info(f"Scene {scene.get('id')} yielded no candidates; skipping.")
                continue

            # Retrieve top candidate.
            candidate_title, candidate_url = candidates[0]
            clean_candidate_title = sanitize_for_windows(candidate_title)
            clean_base_filename = sanitize_for_windows(base_filename)
            if not clean_candidate_title.startswith(clean_base_filename):
                logger.info(f"Scene {scene.get('id')}: candidate title '{candidate_title}' does not start with cleansed filename '{clean_base_filename}'; skipping.")
                continue

            # --- Duplicate URL Check ---
            # Use the scene's existing "urls" field to see if candidate_url already exists.
            existing_urls = scene.get("urls", [])
            duplicate_found = False
            if existing_urls:
                for url_obj in existing_urls:
                    if isinstance(url_obj, dict):
                        existing_url = url_obj.get("url", "")
                    else:
                        existing_url = url_obj
                    if existing_url == candidate_url:
                        duplicate_found = True
                        break
            if duplicate_found:
                logger.info(f"Scene {scene.get('id')}: Candidate URL already exists; skipping scene.")
                continue

            valid_scenes.append(scene)
            logger.info(f"Scene {scene.get('id')} accepted for processing.")

        next_start = sid
        self.after(0, lambda: self._finish_load_scenes(valid_scenes, max_id, next_start))

    def _finish_load_scenes(self, valid_scenes, max_id, next_start):
        """Update the UI with the valid scenes loaded."""
        self.scenes = valid_scenes
        self.end_id_label.config(text=f"End Scene ID: {max_id}")
        self.start_id_var.set(str(next_start))
        self.current_index = 0
        self.load_current_scenes()
        self.load_button.config(state="normal")

    # ------------------- Backward Scene Search -------------------
    def _load_scenes_backward_thread(self):
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
        valid_scenes = []
        try:
            start_id = int(self.start_id_var.get())
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Invalid start scene ID: {e}"))
            return
        sid = start_id
        while len(valid_scenes) < TARGET_SCENE_COUNT and sid > 0:
            while self.loading_paused:
                time.sleep(0.5)
            try:
                scene = self.stash.find_scene(sid)
            except Exception as e:
                logger.error(f"Error retrieving scene {sid}: {e}")
                sid -= 1
                continue
            sid -= 1
            if not scene:
                logger.info(f"Scene {sid + 1} not found; skipping.")
                continue
            if scene.get("urls", []) or scene.get("organized"):
                logger.info(f"Scene {scene.get('id')} has existing URLs or is organized; skipping.")
                continue
            files = scene.get("files")
            if not files or len(files) == 0:
                logger.info(f"Scene {scene.get('id')} has no files; skipping.")
                continue
            filename = os.path.basename(files[0]["path"])
            base_filename = os.path.splitext(filename)[0]
            candidates = self.get_firefox_urls(base_filename)
            if not candidates:
                logger.info(f"Scene {scene.get('id')} yielded no candidates; skipping.")
                continue
            candidate_title, candidate_url = candidates[0]
            if not candidate_title.startswith(base_filename):
                logger.info(f"Scene {scene.get('id')}: candidate title '{candidate_title}' does not start with filename '{base_filename}'; skipping.")
                continue
            valid_scenes.append(scene)
            logger.info(f"Scene {scene.get('id')} accepted for processing (backward).")
        next_start = sid if sid > 0 else 1
        self.after(0, lambda: self._finish_load_scenes(valid_scenes, "Unknown", next_start))

    def backward_block(self):
        """Handler for the Backward button (not fully implemented)."""
        self.query_max_button.config(state="disabled")
        self.loading_paused = False
        threading.Thread(target=self._load_scenes_backward_thread, daemon=True).start()

    # ------------------- Main Entry Point -------------------
    if __name__ == '__main__':
        app = FirefoxHistoryGUI()
        app.mainloop()
