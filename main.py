# main.py - Updated for CustomTkinter
import logging
import os
import ctypes
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
                processed_any = False
                # processed_any = False

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
                        success = app.process_single_history_file_and_clean(
                            history_path
                        )

                        if success:
                            summary_lines.append(
                                f"Path {idx+1} ('{history_path}') processed. Copied to temp, appended to main browserHistory.db, cleaned."
                            )
                            processed_any = True
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
            # Initialize scene ID and load scenes if configured
            if hasattr(app, "lastsceneID") and app.lastsceneID:
                app.start_id_var.set(str(app.lastsceneID))

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

    # Conditionally enable auto-initialization based on config
    if hasattr(app, 'auto_startup') and app.auto_startup:
        app.after(100, auto_initialize)

    # Start the application
    app.mainloop()
