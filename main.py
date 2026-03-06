# main.py - Updated for CustomTkinter
import logging
import os
import ctypes
import threading
from tkinter import messagebox
from firefox_history_gui import UrlStashGUI
import customtkinter as ctk
import logger_setup
import utils
import firefox_history_gui

# Set global CustomTkinter settings
ctk.set_appearance_mode("system")  # "light", "dark", or "system"
ctk.set_default_color_theme("blue")  # "blue", "green", or "dark-blue"

if __name__ == "__main__":
    # Set DPI awareness for crisp rendering on high-DPI displays
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass  # Not Windows or function not available

    app = UrlStashGUI()

    def auto_initialize():
        local_logger = logging.getLogger("UrlStashGUI")
        summary_lines = []
        summary_lines.append("Auto_initialize...")
        processed_any = False
        total_rows_appended = 0
        processed_source_count = 0

        # Temporarily suppress message boxes during auto-run
        original_showinfo = messagebox.showinfo
        original_showerror = messagebox.showerror
        original_showwarning = messagebox.showwarning
        messagebox.showinfo = lambda *args, **kwargs: None  # type: ignore
        messagebox.showerror = lambda *args, **kwargs: None  # type: ignore
        messagebox.showwarning = lambda *args, **kwargs: None  # type: ignore
        messagebox.bell = lambda *args, **kwargs: None  # type: ignore

        try:
            if not app.userbrowserhistory:
                summary_lines.append(
                    "No history paths are configured. Skipping auto-initialization."
                )
            # return
            else:
                summary_lines.append(
                    f"Found {len(app.userbrowserhistory)} browser history path(s) to process."
                )

                for idx, history_path in enumerate(app.userbrowserhistory):
                    if not history_path or not os.path.exists(history_path):
                        error_msg = f"[FILE ERROR] Path {idx+1} ('{history_path}') not found or invalid. Skipping."
                        summary_lines.append(error_msg)
                        local_logger.error(error_msg)
                        continue

                    summary_lines.append(f"Processing path {idx+1}: {history_path}")
                    local_logger.info(
                        f"Auto-initializing with history file: {history_path}"
                    )

                    try:
                        success, rows_appended = app.process_single_history_file_and_clean(
                            history_path,
                            run_maintenance=False,
                            return_rows=True,
                        )

                        if success:
                            summary_lines.append(
                                f"Path {idx+1} ('{history_path}') processed. Copied to temp and appended to main browserHistory.db."
                            )
                            processed_any = True
                            processed_source_count += 1
                            total_rows_appended += rows_appended
                        else:
                            summary_lines.append(
                                f"Path {idx+1} ('{history_path}') failed to process."
                            )

                    except Exception as e_processing:
                        summary_lines.append(
                            f"Error processing path {idx+1} ('{history_path}'): {e_processing}"
                        )
                        local_logger.error(
                            f"Error during processing for {history_path}: {e_processing}",
                            exc_info=True,
                        )

                if processed_source_count > 0 and os.path.exists("browserHistory.db"):
                    if app._should_run_browser_history_maintenance(total_rows_appended):
                        summary_lines.append(
                            "Running batched dedupe/clean after all auto-start history files were appended."
                        )
                        app.remove_duplicates(run_vacuum=False)
                        app.clean_urls_merged_db(run_vacuum=False)
                    else:
                        summary_lines.append(
                            "Skipped batched dedupe/clean because no new rows were appended and DB settings match the current config."
                        )
            # Initialize scene ID and load scenes if configured
            if hasattr(app, "lastsceneID") and app.lastsceneID:
                app.after(0, lambda: app.start_id_var.set(str(app.lastsceneID)))

            # Mark that sync has been completed this session
            app.synced_this_session = True
            app.sync_prompt_shown = True  # Don't show prompt since auto-startup already ran

            # Auto-load scenes if processing was successful
            if processed_any:
                app.after(1000, app.load_scenes)
            local_logger.info("\n".join(summary_lines))

        except Exception as e:
            summary_lines.append(f"[JSON] Auto initialization failed: {e}")
            local_logger.error(f"[JSON] Auto initialization failed: {e}", exc_info=True)
            local_logger.info("\n".join(summary_lines))
        finally:
            messagebox.showinfo = original_showinfo  # type: ignore
            messagebox.showerror = original_showerror  # type: ignore
            messagebox.showwarning = original_showwarning  # type: ignore

    def start_auto_initialize_when_ready():
        local_logger = logging.getLogger("UrlStashGUI")
        app.deiconify()
        app.lift()
        app.update_idletasks()
        app.update_status("Preparing startup tasks...", "blue")
        local_logger.info("Startup UI rendered. Beginning auto-initialization shortly...")
        app.after(400, lambda: threading.Thread(target=auto_initialize, daemon=True).start())

    # Conditionally enable auto-initialization based on config
    if hasattr(app, 'auto_startup') and app.auto_startup:
        app.after_idle(start_auto_initialize_when_ready)

    # Start the application
    app.mainloop()
