"""Password Manager GUI — sidebar layout.

Windows:
  App              — root window: top bar, sidebar (site list), detail card
  SetupWindow      — first-run master credential creation
  LoginWindow      — normal login
  ForgotWindow     — recovery-key password reset
  ResetWindow      — set a new master password after recovery
  HistoryWindow    — per-site password history with date filtering
  HealthWindow     — weak/reused/stale password report
"""

import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from cryptography.fernet import InvalidToken
from PIL import Image
from tkcalendar import DateEntry

import auth
from auth import AuthManager
from backup import export_backup, import_backup
from breach import check_breach
from generator import generate_password
from manager import DEFAULT_CATEGORIES, PasswordManager
from strength import check_strength

SETTINGS_FILE = "settings.json"
NEW_CATEGORY_LABEL = "＋ New Category…"
MANAGE_CATEGORY_LABEL = "Manage Categories…"
CLIPBOARD_CLEAR_MS = 20_000
INACTIVITY_TIMEOUT = 120  # seconds

PAD = 14          # outer padding unit
FIELD_WIDTH = 320

# ── Themes (identical flat layout; only the palettes change) ─────────────
# Each theme = a customtkinter JSON file (widget colors) + these in-code
# (light, dark) tuples for the spots that need explicit colors.
APP_DIR = os.path.dirname(os.path.abspath(__file__))
ICONS_DIR = os.path.join(APP_DIR, "icons")

APP_VERSION = "1.0"
APP_AUTHOR = "NikosG"

THEMES = {
    "Twitch": {
        "file": "twitch_theme.json",
        "TEXT_MUTED": ("#53535F", "#ADADB8"),
        "GHOST_TEXT": ("#53535F", "#D3D3D9"),
        "GHOST_HOVER": ("#E6E6EA", "#26262C"),
        "CARD_BG": ("#FFFFFF", "#18181B"),
        "CARD_BORDER": ("#D3D3D9", "#2F2F35"),
        "ROW_SELECTED": ("#E6E6EA", "#26262C"),
        "ROW_HOVER": ("#EFEFF1", "#1F1F23"),
        "ROW_TEXT": ("#0E0E10", "#EFEFF1"),
        "DANGER_TEXT": ("#B3261E", "#F87171"),
        "DANGER_HOVER": ("#FBEAEA", "#2A1D20"),
        "STRONG_COLOR": ("#0E8A16", "#4ADE80"),
        "MEDIUM_COLOR": ("#B45309", "#FBBF24"),
        "WEAK_COLOR": ("#B3261E", "#F87171"),
    },
    "Claude": {
        "file": "claude_theme.json",
        "TEXT_MUTED": ("#6E6A5E", "#A6A29A"),
        "GHOST_TEXT": ("#5E5A4E", "#C2C0B6"),
        "GHOST_HOVER": ("#EAE6DA", "#3A3A37"),
        "CARD_BG": ("#FFFFFF", "#30302E"),
        "CARD_BORDER": ("#E3E0D4", "#3F3E3A"),
        "ROW_SELECTED": ("#E5E1D3", "#3F3E3A"),
        "ROW_HOVER": ("#EAE6DA", "#34342F"),
        "ROW_TEXT": ("#1F1E1D", "#ECEAE4"),
        "DANGER_TEXT": ("#B3432B", "#E0755A"),
        "DANGER_HOVER": ("#F3E2DC", "#3B2B26"),
        "STRONG_COLOR": ("#4E7D34", "#8CBF6B"),
        "MEDIUM_COLOR": ("#A8730A", "#D9A93D"),
        "WEAK_COLOR": ("#B3432B", "#E0755A"),
    },
    "Default": {
        "file": "default_theme.json",
        "TEXT_MUTED": ("#5A5A5A", "#A3A3A3"),
        "GHOST_TEXT": ("#4A4A4A", "#C7C7C7"),
        "GHOST_HOVER": ("#E0E0E0", "#2B2B2B"),
        "CARD_BG": ("#FFFFFF", "#212121"),
        "CARD_BORDER": ("#CFCFCF", "#333333"),
        "ROW_SELECTED": ("#D4E2F0", "#1F3A52"),
        "ROW_HOVER": ("#E5E5E5", "#262626"),
        "ROW_TEXT": ("#141414", "#EDEDED"),
        "DANGER_TEXT": ("#C42B1C", "#FF6B6B"),
        "DANGER_HOVER": ("#F6E0DD", "#3A2426"),
        "STRONG_COLOR": ("#2E7D32", "#66BB6A"),
        "MEDIUM_COLOR": ("#B26A00", "#FFB74D"),
        "WEAK_COLOR": ("#C42B1C", "#FF6B6B"),
    },
}


def load_icon(name: str, size: int = 16) -> ctk.CTkImage:
    """Load a light/dark icon pair from the icons folder."""
    return ctk.CTkImage(
        light_image=Image.open(os.path.join(ICONS_DIR, f"{name}_light.png")),
        dark_image=Image.open(os.path.join(ICONS_DIR, f"{name}_dark.png")),
        size=(size, size))


def load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    return {"dark_mode": False}


def save_settings(settings: dict) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as file:
        json.dump(settings, file)


# The theme is fixed at startup — customtkinter can't restyle live widgets,
# so changing it in the UI saves the choice and offers an app restart.
ACTIVE_THEME = load_settings().get("theme", "Twitch")
if ACTIVE_THEME not in THEMES:
    ACTIVE_THEME = "Twitch"
_palette = THEMES[ACTIVE_THEME]
THEME_FILE = os.path.join(APP_DIR, "themes", _palette["file"])
TEXT_MUTED = _palette["TEXT_MUTED"]
GHOST_TEXT = _palette["GHOST_TEXT"]
GHOST_HOVER = _palette["GHOST_HOVER"]
CARD_BG = _palette["CARD_BG"]
CARD_BORDER = _palette["CARD_BORDER"]
ROW_SELECTED = _palette["ROW_SELECTED"]
ROW_HOVER = _palette["ROW_HOVER"]
ROW_TEXT = _palette["ROW_TEXT"]
DANGER_TEXT = _palette["DANGER_TEXT"]
DANGER_HOVER = _palette["DANGER_HOVER"]
STRONG_COLOR = _palette["STRONG_COLOR"]
MEDIUM_COLOR = _palette["MEDIUM_COLOR"]
WEAK_COLOR = _palette["WEAK_COLOR"]


# ── Tooltips ─────────────────────────────────────────────────────────────

class ToolTip:
    """Small hover tooltip for any widget (Twitch-dark in both modes)."""

    BG = "#26262C"
    FG = "#EFEFF1"
    BORDER = "#4B4B53"
    DELAY_MS = 450

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self._after_id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self._after_id = self.widget.after(self.DELAY_MS, self._show)

    def _cancel(self):
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self):
        if self._tip is not None or not self.widget.winfo_exists():
            return
        self._tip = tk.Toplevel(self.widget)
        self._tip.overrideredirect(True)
        self._tip.attributes("-topmost", True)
        tk.Label(self._tip, text=self.text, bg=self.BG, fg=self.FG,
                 font=("Segoe UI", 9), justify="left", padx=8, pady=4,
                 highlightthickness=1,
                 highlightbackground=self.BORDER).pack()
        self._tip.update_idletasks()
        x = (self.widget.winfo_rootx()
             + self.widget.winfo_width() // 2
             - self._tip.winfo_reqwidth() // 2)
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._tip.geometry(f"+{max(x, 0)}+{y}")

    def _hide(self, _event=None):
        self._cancel()
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


def add_tooltip(widget, text: str) -> None:
    ToolTip(widget, text)


# ── Authentication windows ───────────────────────────────────────────────

class RecoveryCodeWindow(ctk.CTkToplevel):
    """Shows a recovery key exactly once and makes the user acknowledge
    saving it before continuing."""

    def __init__(self, app, code, on_close=None, subtitle=None):
        super().__init__(app)
        self.on_close = on_close
        self.title("Your Recovery Key")
        self.geometry("460x360")
        self.resizable(False, False)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._acknowledge)

        ctk.CTkLabel(self, text="Your Recovery Key",
                     font=ctk.CTkFont(size=17, weight="bold")).pack(pady=(22, 6))
        if subtitle:
            ctk.CTkLabel(self, text=subtitle, wraplength=400,
                         text_color=TEXT_MUTED).pack(pady=(0, 6))
        code_box = ctk.CTkEntry(self, width=340, justify="center",
                                font=ctk.CTkFont(family="Consolas", size=18,
                                                 weight="bold"))
        code_box.pack(pady=10)
        code_box.insert(0, code)
        code_box.configure(state="readonly")
        copy_btn = ctk.CTkButton(self, text="Copy", width=120,
                                 fg_color="transparent", border_width=1,
                                 hover_color=GHOST_HOVER, text_color=GHOST_TEXT,
                                 command=lambda: (self.clipboard_clear(),
                                                  self.clipboard_append(code)))
        copy_btn.pack(pady=(0, 8))
        ctk.CTkLabel(
            self, wraplength=400, justify="left",
            text=("This key is the ONLY way to unlock your vault if you "
                  "forget your master password. It is shown only once and "
                  "cannot be recovered later.\n\n"
                  "Write it down and store it somewhere safe — a printed "
                  "note or a drawer, not a file next to your vault."),
        ).pack(pady=6)
        ctk.CTkButton(self, text="I saved my recovery key", width=240,
                      command=self._acknowledge).pack(pady=14)

    def _acknowledge(self):
        self.destroy()
        if self.on_close:
            self.on_close()


class SetupWindow(ctk.CTkToplevel):
    """First run: create the master credentials."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Create Master Credentials")
        self.geometry("420x420")
        self.resizable(False, False)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", app.quit)

        ctk.CTkLabel(self, text="Create Master Credentials",
                     font=ctk.CTkFont(size=17, weight="bold")).pack(pady=(24, 8))
        ctk.CTkLabel(
            self, wraplength=360, text_color=TEXT_MUTED,
            text="After setup you'll receive a one-time recovery key — "
                 "it replaces secret questions.").pack(pady=(0, 10))
        ctk.CTkLabel(self, text="Username").pack()
        self.username_entry = ctk.CTkEntry(self, width=280)
        self.username_entry.pack(pady=(2, 10))
        ctk.CTkLabel(self, text="Password").pack()
        self.password_entry = ctk.CTkEntry(self, width=280, show="*")
        self.password_entry.pack(pady=(2, 10))
        ctk.CTkLabel(self, text="Confirm Password").pack()
        self.confirm_entry = ctk.CTkEntry(self, width=280, show="*")
        self.confirm_entry.pack(pady=(2, 10))
        self.error_label = ctk.CTkLabel(self, text="", text_color="red")
        self.error_label.pack()
        ctk.CTkButton(self, text="Create Account", width=220,
                      command=self.submit).pack(pady=14)

    def submit(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        confirm = self.confirm_entry.get()

        if password != confirm:
            self.error_label.configure(text="Passwords don't match!")
            return
        if not username or not password:
            self.error_label.configure(text="All fields are required!")
            return
        if check_strength(password) == "weak":
            if not messagebox.askyesno(
                    "Weak Master Password",
                    "This master password is weak — it protects every "
                    "other password in your vault.\n\nUse it anyway?",
                    icon="warning", parent=self):
                return

        cipher, code = auth.setup_master(username, password)
        self.destroy()
        RecoveryCodeWindow(self.app, code,
                           on_close=lambda: self.app.unlock(cipher))


class LoginWindow(ctk.CTkToplevel):
    """Normal login."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Login")
        self.geometry("380x340")
        self.resizable(False, False)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", app.quit)

        ctk.CTkLabel(self, text="🔐", font=ctk.CTkFont(size=34)).pack(pady=(22, 0))
        ctk.CTkLabel(self, text="Password Manager",
                     font=ctk.CTkFont(size=19, weight="bold")).pack(pady=(0, 14))
        self.username_entry = ctk.CTkEntry(self, width=260,
                                           placeholder_text="Username")
        self.username_entry.pack(pady=5)
        self.password_entry = ctk.CTkEntry(self, width=260, show="*",
                                           placeholder_text="Password")
        self.password_entry.pack(pady=5)
        self.password_entry.bind("<Return>", lambda e: self.submit())
        self.status_label = ctk.CTkLabel(self, text="", text_color="red")
        self.status_label.pack()
        ctk.CTkButton(self, text="Login", width=220,
                      command=self.submit).pack(pady=8)
        ctk.CTkButton(self, text="Forgot Password?", width=220,
                      fg_color="transparent", hover_color=GHOST_HOVER,
                      text_color=GHOST_TEXT,
                      command=self.forgot).pack()

    def submit(self):
        username = self.username_entry.get()
        password = self.password_entry.get()

        result, cipher = self.app.auth.verify(username, password)
        if result == "success":
            self.destroy()
            self.app.unlock(cipher)
        elif result == "failed":
            self.status_label.configure(
                text=f"Wrong Credentials! {self.app.auth.attempts_left()} attempts left")
        elif result == "locked":
            self.status_label.configure(
                text=f"Locked out! Try again in {self.app.auth.seconds_until_unlock()} seconds")

    def forgot(self):
        ForgotWindow(self.app, self)


class ForgotWindow(ctk.CTkToplevel):
    """Password reset, verified by the recovery key."""

    def __init__(self, app, login_win):
        super().__init__(app)
        self.app = app
        self.login_win = login_win
        self.title("Reset Password")
        self.geometry("400x300")
        self.resizable(False, False)
        self.grab_set()

        ctk.CTkLabel(self, text="Recovery Key",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=10)
        ctk.CTkLabel(self, wraplength=350, text_color=TEXT_MUTED,
                     text="Enter the recovery key you saved when you "
                          "created your account (XXXX-XXXX-XXXX-XXXX).",
                     ).pack(pady=5)
        self.code_entry = ctk.CTkEntry(
            self, width=280, placeholder_text="XXXX-XXXX-XXXX-XXXX",
            font=ctk.CTkFont(family="Consolas", size=14))
        self.code_entry.pack(pady=10)
        self.status_label = ctk.CTkLabel(self, text="", text_color="red")
        self.status_label.pack()
        ctk.CTkButton(self, text="Verify", width=200,
                      command=self.submit).pack(pady=10)

    def submit(self):
        code = self.code_entry.get()
        if auth.verify_recovery_code(code):
            self.destroy()
            self.login_win.destroy()
            ResetWindow(self.app, code)
        else:
            self.status_label.configure(text="Wrong recovery key! Try again.")


class ResetWindow(ctk.CTkToplevel):
    """Sets a new master password. The verified recovery key is what
    actually unwraps the vault key — without it the vault would be
    lost."""

    def __init__(self, app, answer):
        super().__init__(app)
        self.app = app
        self.answer = answer
        self.title("Set New Password")
        self.geometry("340x300")
        self.resizable(False, False)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", app.quit)

        ctk.CTkLabel(self, text="Set New Password",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=12)
        self.new_pass_entry = ctk.CTkEntry(self, width=260, show="*",
                                           placeholder_text="New password")
        self.new_pass_entry.pack(pady=6)
        self.confirm_entry = ctk.CTkEntry(self, width=260, show="*",
                                          placeholder_text="Confirm password")
        self.confirm_entry.pack(pady=6)
        self.status_label = ctk.CTkLabel(self, text="", text_color="red")
        self.status_label.pack()
        ctk.CTkButton(self, text="Save", width=200,
                      command=self.submit).pack(pady=10)

    def submit(self):
        new_password = self.new_pass_entry.get()
        if new_password != self.confirm_entry.get():
            self.status_label.configure(text="Passwords don't match!")
            return
        if not new_password:
            self.status_label.configure(text="Password cannot be empty!")
            return
        if check_strength(new_password) == "weak":
            if not messagebox.askyesno(
                    "Weak Master Password",
                    "This master password is weak — it protects every "
                    "other password in your vault.\n\nUse it anyway?",
                    icon="warning", parent=self):
                return
        cipher, new_code = auth.reset_password_with_recovery(
            self.answer, new_password)
        self.destroy()
        if cipher is None:
            LoginWindow(self.app)
        elif new_code:
            RecoveryCodeWindow(
                self.app, new_code,
                subtitle="Your old recovery key has been retired — "
                         "here is your new one.",
                on_close=lambda: self.app.unlock(cipher))
        else:
            self.app.unlock(cipher)


# ── Feature windows ──────────────────────────────────────────────────────

class HistoryWindow(ctk.CTkToplevel):
    """Password history for one site, with optional date filtering."""

    def __init__(self, app, website):
        super().__init__(app)
        self.app = app
        self.website = website
        self.title(f"History — {website}")
        self.geometry("560x440")
        self.grab_set()

        ctk.CTkLabel(self, text=f"Password history for {website}",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(16, 8))

        filter_frame = ctk.CTkFrame(self, fg_color="transparent")
        filter_frame.pack(pady=4)
        ctk.CTkLabel(filter_frame, text="From:").grid(row=0, column=0, padx=4)
        self.from_date_entry = DateEntry(filter_frame, width=10,
                                         date_pattern="yyyy-mm-dd")
        self.from_date_entry.grid(row=0, column=1, padx=4)
        ctk.CTkLabel(filter_frame, text="To:").grid(row=0, column=2, padx=4)
        self.to_date_entry = DateEntry(filter_frame, width=10,
                                       date_pattern="yyyy-mm-dd")
        self.to_date_entry.grid(row=0, column=3, padx=4)
        ctk.CTkButton(filter_frame, text="Filter", width=80,
                      command=self.apply_filter).grid(row=0, column=4, padx=8)
        ctk.CTkButton(filter_frame, text="Show All", width=80,
                      fg_color="transparent", border_width=1,
                      hover_color=GHOST_HOVER, text_color=GHOST_TEXT,
                      command=self.show_all).grid(row=0, column=5, padx=2)

        self.list_frame = ctk.CTkScrollableFrame(self, width=500, height=280)
        self.list_frame.pack(padx=PAD, pady=(10, PAD), fill="both", expand=True)
        self.show_all()

    def _render(self, entries):
        for child in self.list_frame.winfo_children():
            child.destroy()
        if not entries:
            ctk.CTkLabel(self.list_frame, text="No history entries.",
                         text_color=TEXT_MUTED).pack(pady=20)
            return
        for entry in entries:
            row = ctk.CTkFrame(self.list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=entry["changed_at"], width=150,
                         anchor="w",
                         text_color=TEXT_MUTED).pack(side="left")
            ctk.CTkLabel(row, text=entry["password"], anchor="w",
                         font=ctk.CTkFont(family="Consolas", size=12)).pack(
                side="left", padx=8)

    def show_all(self):
        self._render(self.app.pm.get_history(self.website))

    def apply_filter(self):
        from_date = self.from_date_entry.get()
        to_date = self.to_date_entry.get()
        entries = []
        for entry in self.app.pm.get_history(self.website):
            entry_date = entry["changed_at"][:10]
            if from_date and entry_date < from_date:
                continue
            if to_date and entry_date > to_date:
                continue
            entries.append(entry)
        self._render(entries)


class HealthWindow(ctk.CTkToplevel):
    """Report of weak, reused, and stale passwords."""

    def __init__(self, app):
        super().__init__(app)
        self.title("Password Health Check")
        self.geometry("540x440")
        self.grab_set()

        report = app.pm.health_report()
        total = len(app.pm.get_websites())
        healthy = total - len(report)

        ctk.CTkLabel(self, text="🩺 Password Health",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(16, 4))
        ctk.CTkLabel(self,
                     text=f"{healthy} of {total} entries look healthy.",
                     text_color=TEXT_MUTED).pack()

        frame = ctk.CTkScrollableFrame(self, width=480, height=300)
        frame.pack(padx=PAD, pady=PAD, fill="both", expand=True)
        if not report:
            ctk.CTkLabel(frame, text="No problems found 🎉").pack(pady=20)
        for item in report:
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=item["website"], width=180,
                         anchor="w",
                         font=ctk.CTkFont(weight="bold")).pack(side="left")
            ctk.CTkLabel(row, text=", ".join(item["issues"]), anchor="w",
                         text_color=DANGER_TEXT).pack(side="left", padx=8)


# ── Main application ─────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Password Manager")
        self.geometry("1000x640")
        self.minsize(860, 560)
        self.withdraw()

        self.auth = AuthManager()
        self.pm = None              # created after login
        self.selected_site = None
        self.site_buttons = {}
        self.settings = load_settings()
        self.is_dark_mode = self.settings.get("dark_mode", False)

        ctk.set_appearance_mode("dark" if self.is_dark_mode else "light")
        if os.path.exists(THEME_FILE):
            ctk.set_default_color_theme(THEME_FILE)
        else:  # theme file missing — fall back to the stock look
            ctk.set_default_color_theme("blue")

        self.undo_stack = []
        self.redo_stack = []
        self.icons = {name: load_icon(name) for name in (
            "plus", "save", "trash-2", "lock", "lock-open", "copy",
            "refresh-cw", "history", "download", "upload",
            "moon", "sun", "shield-alert", "heart-pulse",
            "undo-2", "redo-2", "key-round", "info")}

        self.build_ui()

        self.bind("<Control-z>", lambda e: self.undo())
        self.bind("<Control-y>", lambda e: self.redo())
        self.bind("<Control-Z>", lambda e: self.redo())  # Ctrl+Shift+Z
        self.bind("<Motion>", lambda e: self.auth.update_activity())
        self.bind("<KeyPress>", lambda e: self.auth.update_activity())
        self.after(30_000, self.check_inactivity)

        self.show_login()

    # ── session control ──────────────────────────────────────────────

    def show_login(self):
        if auth.load_master() is None:
            SetupWindow(self)
        else:
            LoginWindow(self)

    def unlock(self, cipher):
        try:
            self.pm = PasswordManager(cipher)   # also migrates old vaults
        except (InvalidToken, ValueError):
            self.pm = None
            messagebox.showerror(
                "Vault key mismatch",
                "vault.json was not created by this account, so it cannot "
                "be decrypted.\n\n"
                "Every master.json can only open the vault.json created "
                "with it. Restore the matching pair of files (check your "
                "_saved_state folder), or remove vault.json if it belongs "
                "to a test account you no longer need.")
            LoginWindow(self)
            return
        self.auth.update_activity()
        self.deiconify()
        self.refresh_site_list()
        self._refresh_category_menus()

    def lock(self):
        """Hide the vault and forget the encryption key."""
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._update_undo_buttons()
        self.pm = None
        self.selected_site = None
        self.new_entry()
        self.withdraw()
        LoginWindow(self)

    def check_inactivity(self):
        if self.pm and self.auth.is_inactive(INACTIVITY_TIMEOUT) and self.winfo_viewable():
            self.lock()
        self.after(30_000, self.check_inactivity)

    # ── undo / redo ──────────────────────────────────────────────────

    MAX_UNDO = 50

    def _push_undo(self):
        """Snapshot the vault before a mutating operation."""
        if not self.pm:
            return
        self.undo_stack.append(self.pm.load_data())
        if len(self.undo_stack) > self.MAX_UNDO:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self._update_undo_buttons()

    def _apply_vault(self, data):
        self.pm.save_data(data)
        self.refresh_site_list()
        if self.selected_site and self.selected_site in data:
            self.select_site(self.selected_site)
        else:
            self.new_entry()
        self._update_undo_buttons()

    def undo(self):
        if not self.pm or not self.undo_stack:
            return
        self.redo_stack.append(self.pm.load_data())
        self._apply_vault(self.undo_stack.pop())

    def redo(self):
        if not self.pm or not self.redo_stack:
            return
        self.undo_stack.append(self.pm.load_data())
        self._apply_vault(self.redo_stack.pop())

    def _update_undo_buttons(self):
        self.undo_btn.configure(
            state="normal" if self.undo_stack else "disabled")
        self.redo_btn.configure(
            state="normal" if self.redo_stack else "disabled")

    # ── UI construction ──────────────────────────────────────────────

    def build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # ── top bar ──
        topbar = ctk.CTkFrame(self, height=54, corner_radius=0)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        ctk.CTkLabel(topbar, text="  🔐 Password Manager",
                     font=ctk.CTkFont(size=17, weight="bold")).pack(
            side="left", padx=PAD, pady=10)
        about_btn = ctk.CTkButton(topbar, text="", width=36,
                                  image=self.icons["info"],
                                  fg_color="transparent", border_width=1,
                                  hover_color=GHOST_HOVER,
                                  text_color=GHOST_TEXT,
                                  command=self.show_about)
        about_btn.pack(side="left", padx=2, pady=10)
        add_tooltip(about_btn, "About this app")
        self.undo_btn = ctk.CTkButton(topbar, text="", width=40,
                                      image=self.icons["undo-2"],
                                      state="disabled",
                                      fg_color="transparent", border_width=1,
                                      hover_color=GHOST_HOVER,
                                      text_color=GHOST_TEXT,
                                      command=self.undo)
        self.undo_btn.pack(side="left", padx=(4, 2), pady=10)
        add_tooltip(self.undo_btn, "Undo the last vault change (Ctrl+Z)")
        self.redo_btn = ctk.CTkButton(topbar, text="", width=40,
                                      image=self.icons["redo-2"],
                                      state="disabled",
                                      fg_color="transparent", border_width=1,
                                      hover_color=GHOST_HOVER,
                                      text_color=GHOST_TEXT,
                                      command=self.redo)
        self.redo_btn.pack(side="left", padx=2, pady=10)
        add_tooltip(self.redo_btn, "Redo the undone change (Ctrl+Y)")
        self.toggle_btn = ctk.CTkButton(
            topbar, text="",
            image=self.icons["sun" if self.is_dark_mode else "moon"],
            width=40, command=self.toggle_dark_mode,
            fg_color="transparent", border_width=1,
            hover_color=GHOST_HOVER, text_color=GHOST_TEXT)
        self.toggle_btn.pack(side="right", padx=(4, PAD), pady=10)
        add_tooltip(self.toggle_btn, "Toggle light / dark mode")
        self.theme_var = ctk.StringVar(value="Themes")
        theme_menu = ctk.CTkOptionMenu(topbar, values=list(THEMES),
                                       variable=self.theme_var, width=104,
                                       command=self.change_theme)
        theme_menu.pack(side="right", padx=4, pady=10)
        add_tooltip(theme_menu,
                    f"Choose a color theme (current: {ACTIVE_THEME})")
        rekey_btn = ctk.CTkButton(topbar, text="", width=40,
                                  image=self.icons["key-round"],
                                  fg_color="transparent", border_width=1,
                                  hover_color=GHOST_HOVER,
                                  text_color=GHOST_TEXT,
                                  command=self.regenerate_recovery_key)
        rekey_btn.pack(side="right", padx=4, pady=10)
        add_tooltip(rekey_btn,
                    "Generate a new recovery key (retires the old one)")
        restore_btn = ctk.CTkButton(topbar, text="Restore", width=100,
                                    image=self.icons["upload"],
                                    fg_color="transparent", border_width=1,
                                    hover_color=GHOST_HOVER, text_color=GHOST_TEXT,
                                    command=self.import_backup)
        restore_btn.pack(side="right", padx=4, pady=10)
        add_tooltip(restore_btn, "Import entries from an encrypted backup file")
        backup_btn = ctk.CTkButton(topbar, text="Backup", width=100,
                                   image=self.icons["download"],
                                   fg_color="transparent", border_width=1,
                                   hover_color=GHOST_HOVER, text_color=GHOST_TEXT,
                                   command=self.export_backup)
        backup_btn.pack(side="right", padx=4, pady=10)
        add_tooltip(backup_btn, "Export the vault as an encrypted backup file")
        health_btn = ctk.CTkButton(topbar, text="Health", width=100,
                                   image=self.icons["heart-pulse"],
                                   fg_color="transparent", border_width=1,
                                   hover_color=GHOST_HOVER, text_color=GHOST_TEXT,
                                   command=lambda: HealthWindow(self))
        health_btn.pack(side="right", padx=4, pady=10)
        add_tooltip(health_btn, "Scan the vault for weak, reused, or stale passwords")

        # ── sidebar ──
        sidebar = ctk.CTkFrame(self, width=270, corner_radius=0)
        sidebar.grid(row=1, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(2, weight=1)
        sidebar.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(sidebar, placeholder_text="🔍 Search…")
        self.search_entry.grid(row=0, column=0, sticky="ew",
                               padx=PAD, pady=(PAD, 6))
        self.search_entry.bind("<KeyRelease>", lambda e: self.refresh_site_list())

        self.filter_category_var = ctk.StringVar(value="All")
        self.filter_menu = ctk.CTkOptionMenu(
            sidebar, values=["All"] + DEFAULT_CATEGORIES,
            variable=self.filter_category_var,
            command=lambda _: self.refresh_site_list())
        self.filter_menu.grid(row=1, column=0, sticky="ew",
                              padx=PAD, pady=(0, 6))

        self.site_list = ctk.CTkScrollableFrame(sidebar, fg_color="transparent")
        self.site_list.grid(row=2, column=0, sticky="nsew", padx=6, pady=0)

        new_entry_btn = ctk.CTkButton(sidebar, text="New Entry",
                                       image=self.icons["plus"],
                                       command=self.new_entry)
        new_entry_btn.grid(row=3, column=0, sticky="ew", padx=PAD, pady=PAD)
        add_tooltip(new_entry_btn, "Clear the form to add a new entry")

        # ── detail card ──
        detail_bg = ctk.CTkFrame(self, fg_color="transparent")
        detail_bg.grid(row=1, column=1, sticky="nsew")
        detail_bg.grid_rowconfigure(0, weight=1)
        detail_bg.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(detail_bg, corner_radius=0, fg_color=CARD_BG,
                            border_width=1, border_color=CARD_BORDER)
        card.grid(row=0, column=0, padx=PAD * 2, pady=PAD * 2, sticky="nsew")
        card.grid_columnconfigure(1, weight=1)

        self.card_title = ctk.CTkLabel(card, text="New Entry",
                                       font=ctk.CTkFont(size=18, weight="bold"),
                                       anchor="w")
        self.card_title.grid(row=0, column=0, columnspan=2, sticky="w",
                             padx=PAD * 2, pady=(PAD * 2, PAD))

        def field_label(text, row):
            ctk.CTkLabel(card, text=text, width=90, anchor="w",
                         text_color=TEXT_MUTED).grid(
                row=row, column=0, sticky="nw", padx=(PAD * 2, 8), pady=8)

        field_label("Website", 1)
        self.website_entry = ctk.CTkEntry(card, width=FIELD_WIDTH,
                                          placeholder_text="e.g. www.google.com")
        self.website_entry.grid(row=1, column=1, sticky="w", pady=8)

        field_label("Username", 2)
        self.username_entry = ctk.CTkEntry(card, width=FIELD_WIDTH,
                                           placeholder_text="Enter username")
        self.username_entry.grid(row=2, column=1, sticky="w", pady=8)

        field_label("Password", 3)
        password_row = ctk.CTkFrame(card, fg_color="transparent")
        password_row.grid(row=3, column=1, sticky="w", pady=8)
        self.password_entry = ctk.CTkEntry(password_row, width=FIELD_WIDTH,
                                           show="*", placeholder_text="Enter password")
        self.password_entry.pack(side="left")
        self.password_entry.bind("<KeyRelease>", self.update_strength)
        for name, cmd, tip in (
                ("lock", self.toggle_password_visibility,
                 "Show / hide the password"),
                ("copy", self.copy_password,
                 "Copy to clipboard (auto-clears after 20 s)"),
                ("refresh-cw", self.fill_generated_password,
                 "Fill with a strong generated password")):
            icon_btn = ctk.CTkButton(password_row, text="", width=36,
                                     image=self.icons[name],
                                     fg_color="transparent", bg_color=CARD_BG,
                                     border_width=1,
                                     hover_color=GHOST_HOVER, text_color=GHOST_TEXT,
                                     command=cmd)
            icon_btn.pack(side="left", padx=(6, 2) if name == "lock" else 2)
            add_tooltip(icon_btn, tip)
            if name == "lock":
                self.eye_btn = icon_btn

        self.strength_label = ctk.CTkLabel(card, text="", anchor="w")
        self.strength_label.grid(row=4, column=1, sticky="w")

        field_label("Category", 5)
        self.selected_category = ctk.StringVar(value=DEFAULT_CATEGORIES[0])
        self._last_category = DEFAULT_CATEGORIES[0]
        self.category_menu = ctk.CTkOptionMenu(
            card,
            values=DEFAULT_CATEGORIES + [NEW_CATEGORY_LABEL,
                                         MANAGE_CATEGORY_LABEL],
            variable=self.selected_category, width=180,
            command=self._on_category_selected)
        self.category_menu.grid(row=5, column=1, sticky="w", pady=8)

        field_label("Notes", 6)
        self.notes_box = ctk.CTkTextbox(card, width=FIELD_WIDTH, height=70)
        self.notes_box.grid(row=6, column=1, sticky="w", pady=8)

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=7, column=0, columnspan=2, sticky="w",
                     padx=PAD * 2, pady=(PAD, PAD * 2))
        save_btn = ctk.CTkButton(actions, text="Save", width=110,
                                 image=self.icons["save"],
                                 bg_color=CARD_BG, command=self.save_entry)
        save_btn.pack(side="left", padx=(0, 8))
        add_tooltip(save_btn, "Encrypt and save this entry to the vault")
        history_btn = ctk.CTkButton(actions, text="History", width=110,
                                    image=self.icons["history"],
                                    fg_color="transparent", bg_color=CARD_BG,
                                    border_width=1,
                                    hover_color=GHOST_HOVER, text_color=GHOST_TEXT,
                                    command=self.show_history)
        history_btn.pack(side="left", padx=8)
        add_tooltip(history_btn,
                    "View previous passwords (asks for the master password)")
        breach_btn = ctk.CTkButton(actions, text="Breach Check", width=130,
                                   image=self.icons["shield-alert"],
                                   fg_color="transparent", bg_color=CARD_BG,
                                   border_width=1,
                                   hover_color=GHOST_HOVER, text_color=GHOST_TEXT,
                                   command=self.breach_check)
        breach_btn.pack(side="left", padx=8)
        add_tooltip(breach_btn,
                    "Check the password against known data breaches (HIBP)")
        delete_btn = ctk.CTkButton(actions, text="Delete", width=110,
                                   image=self.icons["trash-2"],
                                   fg_color="transparent", bg_color=CARD_BG,
                                   border_width=1,
                                   border_color=DANGER_TEXT, text_color=DANGER_TEXT,
                                   hover_color=DANGER_HOVER,
                                   command=self.delete_entry)
        delete_btn.pack(side="left", padx=8)
        add_tooltip(delete_btn, "Delete this entry from the vault")

    # ── sidebar list ─────────────────────────────────────────────────

    def refresh_site_list(self):
        for child in self.site_list.winfo_children():
            child.destroy()
        self.site_buttons = {}
        if not self.pm:
            return

        query = self.search_entry.get().lower().strip()
        category = self.filter_category_var.get()
        sites = (self.pm.get_websites() if category == "All"
                 else self.pm.get_websites_by_category(category))
        sites = sorted(s for s in sites if query in s.lower())

        if not sites:
            ctk.CTkLabel(self.site_list, text="No entries",
                         text_color=TEXT_MUTED).pack(pady=16)
            return

        for site in sites:
            btn = ctk.CTkButton(
                self.site_list, text=site, anchor="w", height=32,
                fg_color=ROW_SELECTED if site == self.selected_site
                else "transparent",
                text_color=ROW_TEXT,
                hover_color=ROW_HOVER,
                command=lambda s=site: self.select_site(s))
            btn.pack(fill="x", pady=1)
            self.site_buttons[site] = btn

    def select_site(self, website):
        result = self.pm.get_password(website)
        if not result:
            return
        self.selected_site = website
        self.card_title.configure(text=website)
        self.website_entry.delete(0, tk.END)
        self.website_entry.insert(0, website)
        self.username_entry.delete(0, tk.END)
        self.username_entry.insert(0, result["username"])
        self.password_entry.configure(show="*")
        self.eye_btn.configure(image=self.icons["lock"])
        self.password_entry.delete(0, tk.END)
        self.password_entry.insert(0, result["password"])
        self.selected_category.set(result["category"])
        self._last_category = result["category"]
        self.set_notes(result["notes"])
        self.update_strength()
        self.refresh_site_list()

    def new_entry(self):
        self.selected_site = None
        self.card_title.configure(text="New Entry")
        self.website_entry.delete(0, tk.END)
        self.username_entry.delete(0, tk.END)
        self.password_entry.delete(0, tk.END)
        self.set_notes("")
        self.strength_label.configure(text="")
        self.refresh_site_list()

    # ── categories ───────────────────────────────────────────────────

    def _refresh_category_menus(self):
        categories = (self.pm.get_categories() if self.pm
                      else list(DEFAULT_CATEGORIES))
        self.category_menu.configure(
            values=categories + [NEW_CATEGORY_LABEL, MANAGE_CATEGORY_LABEL])
        self.filter_menu.configure(values=["All"] + categories)

    def _on_category_selected(self, choice):
        if choice not in (NEW_CATEGORY_LABEL, MANAGE_CATEGORY_LABEL):
            self._last_category = choice
            return
        # revert the visible selection while a dialog is open
        self.selected_category.set(self._last_category)
        if choice == NEW_CATEGORY_LABEL:
            self._new_category_dialog()
        else:
            self._manage_categories_dialog()

    def _new_category_dialog(self):
        if not self.pm:
            return
        win = ctk.CTkToplevel(self)
        win.title("New Category")
        win.geometry("320x200")
        win.grab_set()
        ctk.CTkLabel(win, text="New category name:",
                     font=ctk.CTkFont(size=13)).pack(pady=(18, 6))
        name_entry = ctk.CTkEntry(win, width=240,
                                  placeholder_text="e.g. Gaming")
        name_entry.pack(pady=4)
        name_entry.focus_set()
        status = ctk.CTkLabel(win, text="", text_color="red")
        status.pack()

        def submit():
            name = " ".join(name_entry.get().split())
            if not name:
                status.configure(text="Name cannot be empty!")
                return
            if name == NEW_CATEGORY_LABEL:
                status.configure(text="Nice try!")
                return
            if not self.pm.add_category(name):
                status.configure(text="That category already exists!")
                return
            win.destroy()
            self._refresh_category_menus()
            self.selected_category.set(name)
            self._last_category = name

        name_entry.bind("<Return>", lambda e: submit())
        ctk.CTkButton(win, text="Add", width=160,
                      command=submit).pack(pady=10)

    def _manage_categories_dialog(self):
        if not self.pm:
            return
        win = ctk.CTkToplevel(self)
        win.title("Manage Categories")
        win.geometry("380x400")
        win.grab_set()
        ctk.CTkLabel(win, text="Manage Categories",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(16, 2))
        ctk.CTkLabel(win, wraplength=330, text_color=TEXT_MUTED,
                     text="Deleting a category moves its entries to "
                          "\"Other\".").pack(pady=(0, 6))
        list_frame = ctk.CTkScrollableFrame(win, width=320, height=250)
        list_frame.pack(padx=PAD, pady=(4, PAD), fill="both", expand=True)

        def render():
            for child in list_frame.winfo_children():
                child.destroy()
            entries = self.pm.load_data()
            for category in self.pm.get_categories():
                count = sum(1 for e in entries.values()
                            if e.get("category", "Other") == category)
                row = ctk.CTkFrame(list_frame, fg_color="transparent")
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text=category, anchor="w",
                             width=150).pack(side="left", padx=(4, 4))
                ctk.CTkLabel(row, text=f"{count} entr{'y' if count == 1 else 'ies'}",
                             anchor="w", width=80,
                             text_color=TEXT_MUTED).pack(side="left")
                if category != "Other":
                    ctk.CTkButton(
                        row, text="Delete", width=70,
                        fg_color="transparent", border_width=1,
                        border_color=DANGER_TEXT, text_color=DANGER_TEXT,
                        hover_color=DANGER_HOVER,
                        command=lambda c=category, n=count: delete(c, n)
                    ).pack(side="right", padx=4)

        def delete(category, count):
            message = f"Delete the category \"{category}\"?"
            if count:
                message += (f"\n\n{count} entr{'y' if count == 1 else 'ies'} "
                            "will be moved to \"Other\".")
            if not messagebox.askyesno("Delete category", message,
                                       parent=win):
                return
            self.pm.delete_category(category)
            self._refresh_category_menus()
            if self.selected_category.get() == category:
                self.selected_category.set("Other")
                self._last_category = "Other"
            if self.filter_category_var.get() == category:
                self.filter_category_var.set("All")
            self.refresh_site_list()
            render()

        render()

    # ── form helpers ─────────────────────────────────────────────────

    def get_notes(self) -> str:
        return self.notes_box.get("1.0", tk.END).strip()

    def set_notes(self, text: str) -> None:
        self.notes_box.delete("1.0", tk.END)
        if text:
            self.notes_box.insert("1.0", text)

    def update_strength(self, event=None):
        password = self.password_entry.get()
        if not password:
            self.strength_label.configure(text="")
            return
        strength = check_strength(password)
        if strength == "strong":
            self.strength_label.configure(text="Strong ●", text_color=STRONG_COLOR)
        elif strength == "medium":
            self.strength_label.configure(text="Medium ●", text_color=MEDIUM_COLOR)
        else:
            self.strength_label.configure(text="Weak ●", text_color=WEAK_COLOR)

    def toggle_password_visibility(self):
        current = self.password_entry.cget("show")
        self.password_entry.configure(show="" if current == "*" else "*")
        self.eye_btn.configure(
            image=self.icons["lock-open" if current == "*" else "lock"])

    def copy_password(self):
        password = self.password_entry.get()
        self.clipboard_clear()
        self.clipboard_append(password)
        self.after(CLIPBOARD_CLEAR_MS, lambda: self._clear_clipboard(password))

    def _clear_clipboard(self, expected):
        try:
            if self.clipboard_get() == expected:
                self.clipboard_clear()
        except tk.TclError:
            pass  # clipboard already holds non-text content

    def fill_generated_password(self):
        self.password_entry.delete(0, tk.END)
        self.password_entry.insert(0, generate_password())
        self.update_strength()

    # ── vault operations ─────────────────────────────────────────────

    def save_entry(self):
        website = self.website_entry.get().strip()
        username = self.username_entry.get()
        password = self.password_entry.get()
        if not website or not password:
            messagebox.showwarning("Missing data",
                                   "Website and password are required.")
            return
        if self.pm.get_password(website):
            if not messagebox.askyesno("Confirm", f"Confirm changes to {website}?"):
                return
        self._push_undo()
        self.pm.add_password(website, username, password,
                             self.selected_category.get(), self.get_notes())
        self.selected_site = website
        self.card_title.configure(text=website)
        self.refresh_site_list()

    def delete_entry(self):
        website = self.website_entry.get()
        if not website:
            return
        if not messagebox.askyesno("Delete?",
                                   f"Are you sure you want to delete {website}?"):
            return
        self._push_undo()
        if self.pm.delete_password(website):
            self.new_entry()
        else:
            self.undo_stack.pop()   # nothing was deleted
            self._update_undo_buttons()

    # ── history ──────────────────────────────────────────────────────

    def _require_master_password(self, on_success):
        """Small modal that re-verifies the master password, then calls
        `on_success` — used for History and recovery-key regeneration."""
        verify_win = ctk.CTkToplevel(self)
        verify_win.title("Verify Identity")
        verify_win.geometry("320x210")
        verify_win.grab_set()
        ctk.CTkLabel(verify_win, text="Enter Master Password:",
                     font=ctk.CTkFont(size=13)).pack(pady=15)
        pass_entry = ctk.CTkEntry(verify_win, width=240, show="*")
        pass_entry.pack(pady=5)
        status_label = ctk.CTkLabel(verify_win, text="", text_color="red")
        status_label.pack()

        def check():
            if auth.verify_master_password(pass_entry.get()):
                verify_win.destroy()
                on_success()
            else:
                status_label.configure(text="Incorrect password!")

        pass_entry.bind("<Return>", lambda e: check())
        ctk.CTkButton(verify_win, text="Verify", width=180,
                      command=check).pack(pady=10)

    def show_history(self):
        website = self.website_entry.get()
        if not website:
            messagebox.showwarning("No Website",
                                   "Please select or type a website first.")
            return
        self._require_master_password(
            lambda: HistoryWindow(self, website))

    # ── recovery key ─────────────────────────────────────────────────

    def regenerate_recovery_key(self):
        """Retire the current recovery key and show a fresh one.
        Requires re-entering the master password."""
        if not self.pm:
            return

        def rotate():
            code = auth.rotate_recovery_key(self.pm.cipher.key)
            if code:
                RecoveryCodeWindow(
                    self, code,
                    subtitle="Your old recovery key no longer works — "
                             "this is your new one.")

        self._require_master_password(rotate)

    # ── breach check ─────────────────────────────────────────────────

    def breach_check(self):
        password = self.password_entry.get()
        if not password:
            messagebox.showwarning("No Password",
                                   "Type or select a password first.")
            return

        # Run the network call off the UI thread so the window stays alive.
        def worker():
            count = check_breach(password)
            self.after(0, lambda: self._show_breach_result(count))

        threading.Thread(target=worker, daemon=True).start()

    def _show_breach_result(self, count):
        if count is None:
            messagebox.showerror(
                "Breach Check",
                "Couldn't reach the Have I Been Pwned service.\n"
                "Check your internet connection and try again.")
        elif count == 0:
            messagebox.showinfo(
                "Breach Check",
                "Good news — this password was not found in any known breach.")
        else:
            messagebox.showwarning(
                "Breach Check",
                f"⚠️ This password appears {count:,} times in known data "
                "breaches.\nYou should change it everywhere it's used.")

    # ── backups ──────────────────────────────────────────────────────

    def _ask_passphrase(self, title, confirm=False) -> str | None:
        win = ctk.CTkToplevel(self)
        win.title(title)
        win.geometry("360x250")
        win.grab_set()
        result = {"value": None}

        ctk.CTkLabel(win, text=title,
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=12)
        pass_entry = ctk.CTkEntry(win, width=260, show="*",
                                  placeholder_text="Backup passphrase")
        pass_entry.pack(pady=6)
        confirm_entry = None
        if confirm:
            confirm_entry = ctk.CTkEntry(win, width=260, show="*",
                                         placeholder_text="Confirm passphrase")
            confirm_entry.pack(pady=6)
        status = ctk.CTkLabel(win, text="", text_color="red")
        status.pack()

        def submit():
            value = pass_entry.get()
            if not value:
                status.configure(text="Passphrase cannot be empty!")
                return
            if confirm and value != confirm_entry.get():
                status.configure(text="Passphrases don't match!")
                return
            result["value"] = value
            win.destroy()

        ctk.CTkButton(win, text="OK", width=160, command=submit).pack(pady=10)
        self.wait_window(win)
        return result["value"]

    def export_backup(self):
        passphrase = self._ask_passphrase("Encrypt Backup", confirm=True)
        if not passphrase:
            return
        path = filedialog.asksaveasfilename(
            title="Save encrypted backup",
            defaultextension=".pmbackup",
            filetypes=[("Password Manager Backup", "*.pmbackup"),
                       ("All files", "*.*")],
        )
        if not path:
            return
        export_backup(self.pm.all_entries_decrypted(), passphrase, path)
        messagebox.showinfo("Backup", f"Encrypted backup saved to:\n{path}")

    def import_backup(self):
        path = filedialog.askopenfilename(
            title="Open encrypted backup",
            filetypes=[("Password Manager Backup", "*.pmbackup"),
                       ("All files", "*.*")],
        )
        if not path:
            return
        passphrase = self._ask_passphrase("Decrypt Backup")
        if not passphrase:
            return
        entries = import_backup(path, passphrase)
        if entries is None:
            messagebox.showerror(
                "Backup", "Wrong passphrase or not a valid backup file.")
            return
        if not messagebox.askyesno(
                "Import Backup",
                f"Restore {len(entries)} entries?\n"
                "Entries with the same website name will be overwritten."):
            return
        self._push_undo()
        count = self.pm.restore_entries(entries)
        self.refresh_site_list()
        messagebox.showinfo("Backup", f"Restored {count} entries.")

    # ── appearance ───────────────────────────────────────────────────

    def show_about(self):
        win = ctk.CTkToplevel(self)
        win.title("About")
        win.geometry("420x360")
        win.resizable(False, False)
        win.grab_set()

        ctk.CTkLabel(win, text="🔐", font=ctk.CTkFont(size=40)).pack(pady=(22, 4))
        ctk.CTkLabel(win, text="Password Manager",
                     font=ctk.CTkFont(size=20, weight="bold")).pack()
        ctk.CTkLabel(win, text=f"Version {APP_VERSION}",
                     text_color=TEXT_MUTED).pack(pady=(2, 0))
        ctk.CTkLabel(win, text=f"by {APP_AUTHOR}",
                     text_color=TEXT_MUTED).pack(pady=(0, 12))

        divider = ctk.CTkFrame(win, height=1, fg_color=CARD_BORDER)
        divider.pack(fill="x", padx=PAD * 2, pady=4)

        ctk.CTkLabel(
            win, wraplength=360, justify="left", text_color=TEXT_MUTED,
            text=("Your vault is encrypted as a single AES/Fernet blob — "
                  "site names, usernames, notes and categories never touch "
                  "the disk in the clear. The encryption key is derived with "
                  "PBKDF2-HMAC-SHA256 (600,000 iterations) and protected by "
                  "your master password, with a one-time recovery key as the "
                  "only backup.")).pack(padx=PAD * 2, pady=(10, 6))

        ctk.CTkButton(win, text="Close", width=140,
                      command=win.destroy).pack(pady=(8, 16))

    def change_theme(self, choice):
        self.theme_var.set("Themes")   # the button is a menu, not a value
        if choice == ACTIVE_THEME:
            return
        self.settings["theme"] = choice
        save_settings(self.settings)
        if messagebox.askyesno(
                "Theme changed",
                f"Switch to the {choice} theme now?\n\n"
                "The app will restart and you'll need to log in again."):
            subprocess.Popen(
                [sys.executable, os.path.join(APP_DIR, "main.py")],
                cwd=APP_DIR)
            self.destroy()
            sys.exit(0)
        # otherwise it simply applies on the next launch

    def toggle_dark_mode(self):
        self.is_dark_mode = not self.is_dark_mode
        ctk.set_appearance_mode("dark" if self.is_dark_mode else "light")
        self.toggle_btn.configure(
            image=self.icons["sun" if self.is_dark_mode else "moon"])
        self.settings["dark_mode"] = self.is_dark_mode
        save_settings(self.settings)


def run():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    run()
