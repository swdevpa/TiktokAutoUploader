
import os
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from typing import Optional
from zoneinfo import ZoneInfo

from tkcalendar import DateEntry

from tiktok_uploader import tiktok
from tiktok_uploader.Video import Video
from tiktok_uploader.gemini_caption import GeminiCaptionError, GeminiCaptionService

US_EASTERN = ZoneInfo("America/New_York")

class TiktokUploaderGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tiktok Auto Uploader")
        self.geometry("980x820")
        self.minsize(900, 750)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        self.video_dir = os.path.join(os.getcwd(), "VideosDirPath")
        self.visibility_options = {"Public": 0, "Private": 1}
        self.datacenter_options = [
            "Automatic",
            "useast2a",
            "useast5",
            "uswest2",
            "eu-ttp2",
            "euw1",
            "asia-singapore-1",
        ]
        self.framework_pdfs = [
            os.path.join(os.getcwd(), "Scale Your App to 50k:mo Installs with Organic Content 29-10.pdf"),
            os.path.join(os.getcwd(), "TikTok Algo Guide.pdf"),
        ]
        self._caption_thread: Optional[threading.Thread] = None
        self._upload_thread: Optional[threading.Thread] = None
        self._active_tasks = 0

        self.create_upload_tab()
        self.create_users_tab()
        self.create_videos_tab()

    def create_upload_tab(self):
        upload_tab = ttk.Frame(self.notebook)
        self.notebook.add(upload_tab, text="Upload")
        upload_tab.columnconfigure(0, weight=1)
        upload_tab.rowconfigure(0, weight=1)
        upload_tab.rowconfigure(1, weight=0)

        form_container = ttk.Frame(upload_tab, padding=(0, 5))
        form_container.grid(row=0, column=0, sticky="nsew")
        form_container.columnconfigure(0, weight=1)
        form_container.columnconfigure(1, weight=1)

        status_container = ttk.Frame(upload_tab)
        status_container.grid(row=1, column=0, pady=(5, 0), sticky="nsew")

        left_column = ttk.Frame(form_container)
        left_column.grid(row=0, column=0, padx=(0, 5), sticky="nsew")
        left_column.columnconfigure(0, weight=1)
        left_column.rowconfigure(1, weight=1)

        right_column = ttk.Frame(form_container)
        right_column.grid(row=0, column=1, padx=(5, 0), sticky="nsew")
        right_column.columnconfigure(0, weight=1)

        # Upload details section
        details_frame = ttk.LabelFrame(left_column, text="Upload Details")
        details_frame.grid(row=0, column=0, padx=5, pady=(0, 5), sticky="ew")
        details_frame.columnconfigure(1, weight=1)
        details_frame.columnconfigure(2, weight=1)

        ttk.Label(details_frame, text="Select User:").grid(row=0, column=0, padx=(10, 5), pady=8, sticky="w")
        self.user_combobox = ttk.Combobox(details_frame, state="readonly")
        self.user_combobox.grid(row=0, column=1, columnspan=2, padx=(0, 10), pady=8, sticky="ew")
        self.update_user_list()

        self.upload_type = tk.StringVar(value="local")
        upload_type_frame = ttk.Frame(details_frame)
        upload_type_frame.grid(row=1, column=0, columnspan=3, padx=10, pady=(0, 5), sticky="w")
        ttk.Radiobutton(upload_type_frame, text="Local File", variable=self.upload_type, value="local", command=self.toggle_upload_source).pack(side="left", padx=(0, 10))
        ttk.Radiobutton(upload_type_frame, text="YouTube URL", variable=self.upload_type, value="youtube", command=self.toggle_upload_source).pack(side="left")

        self.source_label = ttk.Label(details_frame, text="Video Path:")
        self.source_label.grid(row=2, column=0, padx=(10, 5), pady=8, sticky="w")
        self.source_entry = ttk.Entry(details_frame)
        self.source_entry.grid(row=2, column=1, padx=(0, 5), pady=8, sticky="ew")
        self.browse_button = ttk.Button(details_frame, text="Browse...", command=self.browse_local_video, width=10)
        self.browse_button.grid(row=2, column=2, padx=(0, 10), pady=8, sticky="e")

        # Caption section
        caption_frame = ttk.LabelFrame(left_column, text="Caption")
        caption_frame.grid(row=1, column=0, padx=5, pady=(0, 5), sticky="nsew")
        caption_frame.columnconfigure(0, weight=1)
        caption_frame.rowconfigure(0, weight=1)

        self.caption_text = tk.Text(caption_frame, height=6, wrap="word")
        self.caption_text.grid(row=0, column=0, padx=(10, 0), pady=10, sticky="nsew")
        self.caption_scrollbar = ttk.Scrollbar(caption_frame, orient="vertical", command=self.caption_text.yview)
        self.caption_scrollbar.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="ns")
        self.caption_text.configure(yscrollcommand=self.caption_scrollbar.set)

        caption_actions = ttk.Frame(caption_frame)
        caption_actions.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")
        caption_actions.columnconfigure(0, weight=1)
        self.caption_status_var = tk.StringVar(value="")
        self.caption_status_label = ttk.Label(caption_actions, textvariable=self.caption_status_var)
        self.caption_status_label.grid(row=0, column=0, sticky="w")
        self.caption_general_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            caption_actions,
            text="Caption ohne App-Fokus",
            variable=self.caption_general_var,
        ).grid(row=1, column=0, columnspan=2, pady=(6, 0), sticky="w")
        self.generate_caption_button = ttk.Button(caption_actions, text="Generate Caption with Gemini", command=self.generate_caption_with_gemini)
        self.generate_caption_button.grid(row=0, column=1, sticky="e")

        # Metadata toggles
        meta_frame = ttk.LabelFrame(right_column, text="Metadata & Permissions")
        meta_frame.grid(row=0, column=0, padx=5, pady=(0, 5), sticky="ew")
        meta_frame.columnconfigure(1, weight=1)

        self.ai_generated_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(meta_frame, text="Mark as AI-generated", variable=self.ai_generated_var).grid(row=0, column=0, columnspan=2, padx=10, pady=(8, 2), sticky="w")

        permissions_frame = ttk.Frame(meta_frame)
        permissions_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 5), sticky="w")
        self.allow_comment_var = tk.BooleanVar(value=True)
        self.allow_duet_var = tk.BooleanVar(value=False)
        self.allow_stitch_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(permissions_frame, text="Allow Comments", variable=self.allow_comment_var).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(permissions_frame, text="Allow Duet", variable=self.allow_duet_var).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(permissions_frame, text="Allow Stitch", variable=self.allow_stitch_var).pack(side="left")

        ttk.Label(meta_frame, text="Visibility:").grid(row=2, column=0, padx=(10, 5), pady=(0, 8), sticky="w")
        self.visibility_combobox = ttk.Combobox(meta_frame, state="readonly", values=list(self.visibility_options.keys()))
        self.visibility_combobox.grid(row=2, column=1, padx=(0, 10), pady=(0, 8), sticky="ew")
        self.visibility_combobox.current(0)

        brand_frame = ttk.Frame(meta_frame)
        brand_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="w")
        self.brand_organic_var = tk.BooleanVar(value=False)
        self.branded_content_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(brand_frame, text="Brand Organic", variable=self.brand_organic_var).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(brand_frame, text="Branded Content", variable=self.branded_content_var).pack(side="left")

        # Schedule time
        schedule_frame = ttk.LabelFrame(right_column, text="Schedule (US Eastern)")
        schedule_frame.grid(row=1, column=0, padx=5, pady=(0, 5), sticky="ew")
        schedule_frame.columnconfigure(1, weight=1)
        schedule_frame.columnconfigure(3, weight=1)

        schedule_label = ttk.Label(schedule_frame, text="Offset (seconds, optional):")
        schedule_label.grid(row=0, column=0, sticky="w")
        self.schedule_entry = ttk.Entry(schedule_frame)
        self.schedule_entry.grid(row=0, column=1, padx=(8, 0), pady=(0, 5), sticky="ew")
        ttk.Button(schedule_frame, text="Clear", command=self._clear_schedule_picker).grid(row=0, column=3, padx=(8, 0), pady=(0, 5), sticky="e")

        self.schedule_date_var = tk.StringVar(value="")
        ttk.Label(schedule_frame, text="Date:").grid(row=1, column=0, sticky="w")
        self.schedule_date_picker = DateEntry(
            schedule_frame,
            width=14,
            textvariable=self.schedule_date_var,
            font=("TkDefaultFont", 10),
            selectforeground="white",
            date_pattern="yyyy-mm-dd",
        )
        self.schedule_date_picker.grid(row=1, column=1, padx=(8, 0), pady=(0, 5), sticky="w")
        self.schedule_date_var.set("")
        self.schedule_date_picker.delete(0, tk.END)
        ttk.Button(schedule_frame, text="Today", command=self._set_schedule_today).grid(row=1, column=2, padx=(10, 0), pady=(0, 5), sticky="ew")

        self.schedule_time_var = tk.StringVar(value="")
        ttk.Label(schedule_frame, text="Time:").grid(row=2, column=0, sticky="w")
        self.schedule_time_combobox = ttk.Combobox(
            schedule_frame,
            textvariable=self.schedule_time_var,
            values=self._time_picker_options(),
            state="readonly",
        )
        self.schedule_time_combobox.grid(row=2, column=1, padx=(8, 0), pady=(0, 5), sticky="ew")
        ttk.Button(schedule_frame, text="Now", command=self._set_schedule_now).grid(row=2, column=2, padx=(10, 0), pady=(0, 5), sticky="ew")

        schedule_hint = ttk.Label(
            schedule_frame,
            text="Leave fields empty for immediate upload. Eastern time is used.",
            foreground="gray",
        )
        schedule_hint.grid(row=3, column=0, columnspan=4, sticky="w")

        # Network / advanced options
        advanced_frame = ttk.LabelFrame(right_column, text="Advanced Options")
        advanced_frame.grid(row=2, column=0, padx=5, pady=(0, 5), sticky="ew")
        advanced_frame.columnconfigure(1, weight=1)

        ttk.Label(advanced_frame, text="Proxy (optional):").grid(row=0, column=0, padx=(10, 5), pady=8, sticky="w")
        self.proxy_entry = ttk.Entry(advanced_frame)
        self.proxy_entry.grid(row=0, column=1, padx=(0, 10), pady=8, sticky="ew")

        ttk.Label(advanced_frame, text="Datacenter (optional):").grid(row=1, column=0, padx=(10, 5), pady=(0, 10), sticky="w")
        self.datacenter_var = tk.StringVar(value=self.datacenter_options[0])
        self.datacenter_combobox = ttk.Combobox(
            advanced_frame,
            textvariable=self.datacenter_var,
            values=self.datacenter_options,
            state="readonly",
        )
        self.datacenter_combobox.grid(row=1, column=1, padx=(0, 10), pady=(0, 10), sticky="ew")

        # Upload button
        action_frame = ttk.Frame(right_column)
        action_frame.grid(row=3, column=0, padx=5, pady=(5, 5), sticky="e")
        self.upload_button = ttk.Button(action_frame, text="Upload", command=self.upload_video, width=18)
        self.upload_button.pack(padx=5, pady=(5, 0))

        self._build_status_section(status_container)

    def _build_status_section(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        status_frame = ttk.LabelFrame(parent, text="Status")
        status_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        status_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(1, weight=1)

        header = ttk.Frame(status_frame)
        header.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        header.columnconfigure(1, weight=1)

        self.status_message_var = tk.StringVar(value="Bereit.")
        ttk.Label(header, textvariable=self.status_message_var).grid(row=0, column=0, sticky="w")

        self.status_progress = ttk.Progressbar(header, mode="indeterminate")
        self.status_progress.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        self.status_text = tk.Text(status_frame, height=8, wrap="word", state="disabled")
        self.status_text.grid(row=1, column=0, padx=(10, 0), pady=(0, 10), sticky="nsew")

        self.status_scrollbar = ttk.Scrollbar(status_frame, orient="vertical", command=self.status_text.yview)
        self.status_scrollbar.grid(row=1, column=1, padx=(0, 10), pady=(0, 10), sticky="ns")
        self.status_text.configure(yscrollcommand=self.status_scrollbar.set)

    def create_users_tab(self):
        users_tab = ttk.Frame(self.notebook)
        self.notebook.add(users_tab, text="Users")

        self.user_listbox = tk.Listbox(users_tab)
        self.user_listbox.pack(padx=10, pady=10, fill="both", expand=True)
        self.update_user_listbox()

        button_frame = ttk.Frame(users_tab)
        button_frame.pack(fill="x", padx=10, pady=5)

        add_user_button = ttk.Button(button_frame, text="Add User", command=self.add_user)
        add_user_button.pack(side="left", padx=5)

        remove_user_button = ttk.Button(button_frame, text="Remove User", command=self.remove_user)
        remove_user_button.pack(side="left", padx=5)

    def create_videos_tab(self):
        videos_tab = ttk.Frame(self.notebook)
        self.notebook.add(videos_tab, text="Videos")

        self.video_listbox = tk.Listbox(videos_tab)
        self.video_listbox.pack(padx=10, pady=10, fill="both", expand=True)
        self.update_video_listbox()

        refresh_button = ttk.Button(videos_tab, text="Refresh", command=self.update_video_listbox)
        refresh_button.pack(pady=5)

    def toggle_upload_source(self):
        if self.upload_type.get() == "local":
            self.source_label.config(text="Video Path:")
            self.browse_button.state(["!disabled"])
        else:
            self.source_label.config(text="YouTube URL:")
            self.browse_button.state(["disabled"])

    def browse_local_video(self):
        initial_dir = self.video_dir if os.path.isdir(self.video_dir) else os.getcwd()
        filetypes = [
            ("Video files", "*.mp4 *.mov *.avi *.mkv *.webm *.m4v"),
            ("All files", "*.*"),
        ]
        file_path = filedialog.askopenfilename(
            title="Select Video",
            initialdir=initial_dir,
            filetypes=filetypes,
        )
        if file_path:
            self.source_entry.delete(0, tk.END)
            self.source_entry.insert(0, file_path)

    def _known_users(self):
        cookie_dir = os.path.join(os.getcwd(), "CookiesDir")
        if not os.path.exists(cookie_dir):
            return []
        users = []
        for filename in os.listdir(cookie_dir):
            if filename.startswith("tiktok_session-") and filename.endswith(".cookie"):
                username = filename[len("tiktok_session-") : -len(".cookie")]
                users.append(username)
        return sorted(users)

    def update_user_list(self):
        users = self._known_users()
        self.user_combobox["values"] = users
        if users:
            current = self.user_combobox.get()
            if current not in users:
                self.user_combobox.set(users[0])
        else:
            self.user_combobox.set("")
        if hasattr(self, "user_listbox"):
            self.update_user_listbox()

    def update_user_listbox(self):
        if not hasattr(self, "user_listbox"):
            return
        self.user_listbox.delete(0, tk.END)
        for user in self._known_users():
            self.user_listbox.insert(tk.END, user)

    def add_user(self):
        # This will open a browser window for the user to log in.
        # We need to get the username from the user.
        # For simplicity, we will use a simple dialog.
        from tkinter import simpledialog
        user_name = simpledialog.askstring("Add User", "Enter a name for this user:")
        if user_name:
            try:
                tiktok.login(user_name)
            except RuntimeError as err:
                messagebox.showerror("Login failed", str(err))
            else:
                self.update_user_list()

    def remove_user(self):
        selected_user = self.user_listbox.get(tk.ACTIVE)
        if selected_user:
            cookie_file = os.path.join(os.getcwd(), "CookiesDir", f"tiktok_session-{selected_user}.cookie")
            if os.path.exists(cookie_file):
                os.remove(cookie_file)
                self.update_user_list()

    def update_video_listbox(self):
        self.video_listbox.delete(0, tk.END)
        video_dir = os.path.join(os.getcwd(), "VideosDirPath")
        if os.path.exists(video_dir):
            videos = [f for f in os.listdir(video_dir)]
            for video in videos:
                self.video_listbox.insert(tk.END, video)

    def upload_video(self):
        if self._upload_thread and self._upload_thread.is_alive():
            self._report_status("Upload läuft bereits; bitte warten.")
            messagebox.showinfo("Upload läuft", "Es wird bereits ein Upload ausgeführt.")
            return

        user = self.user_combobox.get()
        source = self.source_entry.get().strip()
        caption = self.caption_text.get("1.0", tk.END).strip()
        ai_label = 1 if self.ai_generated_var.get() else 0
        allow_comment = 1 if self.allow_comment_var.get() else 0
        allow_duet = 1 if self.allow_duet_var.get() else 0
        allow_stitch = 1 if self.allow_stitch_var.get() else 0
        visibility_label = self.visibility_combobox.get()
        visibility_type = self.visibility_options.get(visibility_label, 0)
        brand_organic_type = 1 if self.brand_organic_var.get() else 0
        branded_content_type = 1 if self.branded_content_var.get() else 0
        proxy = self.proxy_entry.get().strip()
        datacenter_selection = self.datacenter_var.get().strip()
        datacenter = None if datacenter_selection == "Automatic" else datacenter_selection or None

        if not user or not source or not caption:
            messagebox.showerror("Missing information", "Please select a user, choose a video, and enter a caption.")
            self._report_status("Upload abgebrochen: fehlende Angaben.")
            return

        try:
            schedule_time = self._resolve_schedule_seconds()
        except ValueError as err:
            messagebox.showerror("Invalid schedule", str(err))
            self._report_status("Upload abgebrochen: ungültige Planungszeit.")
            return

        upload_type = self.upload_type.get()
        source_reference = source
        if upload_type == "local":
            if not os.path.isabs(source_reference):
                source_reference = os.path.join(self.video_dir, source_reference)
            if not os.path.exists(source_reference):
                messagebox.showerror("Video not found", f"Video not found: {source_reference}")
                self._report_status(f"Upload abgebrochen: Video nicht gefunden ({source_reference}).")
                return

        job = {
            "user": user,
            "source": source_reference if upload_type == "local" else source,
            "caption": caption,
            "schedule_time": schedule_time,
            "allow_comment": allow_comment,
            "allow_duet": allow_duet,
            "allow_stitch": allow_stitch,
            "visibility_type": visibility_type,
            "brand_organic_type": brand_organic_type,
            "branded_content_type": branded_content_type,
            "ai_label": ai_label,
            "proxy": proxy or None,
            "datacenter": datacenter,
            "upload_type": upload_type,
        }

        self._set_upload_in_progress(True)
        self._begin_task()
        self._report_status("Starte Upload-Vorbereitung.")
        self._upload_thread = threading.Thread(target=self._upload_worker, args=(job,), daemon=True)
        self._upload_thread.start()

    def _resolve_schedule_seconds(self) -> int:
        raw_seconds = self.schedule_entry.get().strip()
        date_text = getattr(self, "schedule_date_var", tk.StringVar()).get().strip()
        time_text = getattr(self, "schedule_time_var", tk.StringVar()).get().strip()

        if date_text or time_text:
            if not date_text or not time_text:
                raise ValueError("Bitte sowohl Datum als auch Uhrzeit angeben oder beide leer lassen.")
            try:
                parsed_dt = datetime.strptime(f"{date_text} {time_text}", "%Y-%m-%d %H:%M")
            except ValueError as exc:
                raise ValueError("Datum/Uhrzeit müssen dem Format YYYY-MM-DD und HH:MM (24h) entsprechen.") from exc
            target_dt = parsed_dt.replace(tzinfo=US_EASTERN)
            delta_seconds = int((target_dt - datetime.now(US_EASTERN)).total_seconds())
            if delta_seconds < 0:
                raise ValueError("Der gewählte Zeitpunkt liegt in der Vergangenheit (US Eastern).")
            # Reflect computed offset so the previous behaviour stays visible.
            self.schedule_entry.delete(0, tk.END)
            self.schedule_entry.insert(0, str(delta_seconds))
            return delta_seconds

        if raw_seconds:
            try:
                schedule_seconds = int(raw_seconds)
            except ValueError as exc:
                raise ValueError("Schedule time must be a non-negative integer (seconds).") from exc
            if schedule_seconds < 0:
                raise ValueError("Schedule time must be a non-negative integer (seconds).")
            return schedule_seconds

        return 0

    def _time_picker_options(self):
        if not hasattr(self, "_schedule_time_options"):
            options = []
            for hour in range(24):
                for minute in range(0, 60, 5):
                    options.append(f"{hour:02d}:{minute:02d}")
            self._schedule_time_options = options
        return self._schedule_time_options

    def _set_schedule_today(self):
        today = datetime.now(US_EASTERN).date()
        if hasattr(self, "schedule_date_picker"):
            self.schedule_date_picker.set_date(today)
        self.schedule_date_var.set(today.strftime("%Y-%m-%d"))

    def _set_schedule_now(self):
        now = datetime.now(US_EASTERN).replace(second=0, microsecond=0)
        rounded_minute = (now.minute // 5) * 5
        now = now.replace(minute=rounded_minute)
        self._set_schedule_today()
        formatted_time = f"{now.hour:02d}:{now.minute:02d}"
        self.schedule_time_var.set(formatted_time)
        if hasattr(self, "schedule_time_combobox"):
            self.schedule_time_combobox.set(formatted_time)

    def _clear_schedule_picker(self):
        self.schedule_entry.delete(0, tk.END)
        if hasattr(self, "schedule_date_var"):
            self.schedule_date_var.set("")
        if hasattr(self, "schedule_time_var"):
            self.schedule_time_var.set("")
        if hasattr(self, "schedule_date_picker"):
            self.schedule_date_picker.delete(0, tk.END)
        if hasattr(self, "schedule_time_combobox"):
            self.schedule_time_combobox.set("")

    def generate_caption_with_gemini(self):
        if self._caption_thread and self._caption_thread.is_alive():
            return

        if self.upload_type.get() != "local":
            messagebox.showerror("Generate caption", "Gemini caption generation currently supports local video files only.")
            return

        source = self.source_entry.get().strip()
        if not source:
            messagebox.showerror("Generate caption", "Please choose a local video first.")
            return

        video_path = source
        if not os.path.isabs(video_path):
            video_path = os.path.join(self.video_dir, video_path)
        if not os.path.exists(video_path):
            messagebox.showerror("Generate caption", f"Video not found: {video_path}")
            return

        self.generate_caption_button.state(["disabled"])
        self.caption_status_var.set("Generating caption with Gemini...")
        self._begin_task()
        self._report_status("Starte Gemini-Caption-Generierung.")

        general_caption = self.caption_general_var.get()
        self._caption_thread = threading.Thread(
            target=self._capture_caption_worker, args=(video_path, general_caption), daemon=True
        )
        self._caption_thread.start()

    def _capture_caption_worker(self, video_path: str, general_caption: bool):
        try:
            pdfs = [path for path in self.framework_pdfs if os.path.isfile(path)]
            service = GeminiCaptionService(pdf_paths=pdfs, app_focus=not general_caption)
            suggestion = service.generate_caption(video_path)
        except GeminiCaptionError as err:
            self.after(0, lambda: self._on_caption_generation_error(str(err)))
        except Exception as exc:
            self.after(0, lambda: self._on_caption_generation_error(str(exc)))
        else:
            self.after(0, lambda: self._on_caption_generation_success(suggestion))

    def _on_caption_generation_success(self, suggestion):
        self.generate_caption_button.state(["!disabled"])
        self.caption_text.delete("1.0", tk.END)
        self.caption_text.insert(tk.END, suggestion.formatted)
        self.caption_status_var.set("Caption generated with Gemini 2.5 Pro.")
        self._report_status("Caption generated with Gemini 2.5 Pro.")
        self._end_task()

    def _on_caption_generation_error(self, message: str):
        self.generate_caption_button.state(["!disabled"])
        self.caption_status_var.set("")
        self._report_status(f"Caption generation failed: {message}")
        self._end_task()
        messagebox.showerror("Generate caption", message)

    def _upload_worker(self, job):
        try:
            if job["upload_type"] == "youtube":
                self._report_status("Lade YouTube-Video herunter.")
                video_obj = Video(job["source"], job["caption"], status_callback=self._report_status)
                try:
                    video_obj.is_valid_file_format()
                except SystemExit as exc:
                    raise RuntimeError(str(exc)) from None
                video_path = video_obj.source_ref
                if not video_path or not os.path.exists(video_path):
                    raise RuntimeError("YouTube-Download fehlgeschlagen; keine Videodatei gefunden.")
                self._report_status("YouTube-Download abgeschlossen.")
            else:
                video_path = job["source"]

            self._report_status("Starte Upload zu TikTok.")
            success = tiktok.upload_video(
                job["user"],
                video_path,
                job["caption"],
                schedule_time=job["schedule_time"],
                allow_comment=job["allow_comment"],
                allow_duet=job["allow_duet"],
                allow_stitch=job["allow_stitch"],
                visibility_type=job["visibility_type"],
                brand_organic_type=job["brand_organic_type"],
                branded_content_type=job["branded_content_type"],
                ai_label=job["ai_label"],
                proxy=job["proxy"],
                datacenter=job["datacenter"],
                status_callback=self._report_status,
            )
        except RuntimeError as err:
            err_msg = str(err)
            self.after(0, lambda msg=err_msg: self._on_upload_error(msg))
        except Exception as exc:
            exc_msg = str(exc)
            self.after(0, lambda msg=exc_msg: self._on_upload_error(msg))
        else:
            if success:
                self.after(0, self._on_upload_success)
            else:
                self.after(0, lambda: self._on_upload_failure("TikTok hat den Upload ohne Erfolg beendet."))

    def _on_upload_success(self):
        self._report_status("Upload erfolgreich abgeschlossen.")
        self._set_upload_in_progress(False)
        self._upload_thread = None
        self._end_task()
        messagebox.showinfo("Upload", "Video erfolgreich hochgeladen.")

    def _on_upload_failure(self, message: str):
        self._report_status(message)
        self._set_upload_in_progress(False)
        self._upload_thread = None
        self._end_task()
        messagebox.showerror("Upload fehlgeschlagen", message)

    def _on_upload_error(self, message: str):
        self._report_status(f"Upload fehlgeschlagen: {message}")
        self._set_upload_in_progress(False)
        self._upload_thread = None
        self._end_task()
        messagebox.showerror("Upload fehlgeschlagen", message)

    def _set_upload_in_progress(self, in_progress: bool):
        if in_progress:
            self.upload_button.state(["disabled"])
        else:
            self.upload_button.state(["!disabled"])

    def _report_status(self, message: str):
        self.after(0, lambda: self._append_status(message))

    def _append_status(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}\n"
        self.status_text.configure(state="normal")
        self.status_text.insert(tk.END, entry)
        self.status_text.see(tk.END)
        self.status_text.configure(state="disabled")
        self.status_message_var.set(message)

    def _begin_task(self):
        self._active_tasks += 1
        if self._active_tasks == 1:
            self.status_progress.start(10)

    def _end_task(self):
        if self._active_tasks == 0:
            return
        self._active_tasks -= 1
        if self._active_tasks == 0:
            self.status_progress.stop()


if __name__ == "__main__":
    app = TiktokUploaderGUI()
    app.mainloop()
