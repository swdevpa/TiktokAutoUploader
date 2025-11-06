
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
from tiktok_uploader import tiktok

class TiktokUploaderGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tiktok Auto Uploader")
        self.geometry("800x600")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(pady=10, padx=10, fill="both", expand=True)

        self.video_dir = os.path.join(os.getcwd(), "VideosDirPath")
        self.visibility_options = {"Public": 0, "Private": 1}

        self.create_upload_tab()
        self.create_users_tab()
        self.create_videos_tab()

    def create_upload_tab(self):
        upload_tab = ttk.Frame(self.notebook)
        self.notebook.add(upload_tab, text="Upload")
        upload_tab.columnconfigure(1, weight=1)
        upload_tab.rowconfigure(3, weight=1)

        # User selection
        user_label = ttk.Label(upload_tab, text="Select User:")
        user_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.user_combobox = ttk.Combobox(upload_tab, state="readonly")
        self.user_combobox.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        self.update_user_list()

        # Upload type
        self.upload_type = tk.StringVar(value="local")
        local_radio = ttk.Radiobutton(upload_tab, text="Local File", variable=self.upload_type, value="local", command=self.toggle_upload_source)
        local_radio.grid(row=1, column=0, padx=10, pady=10, sticky="w")
        youtube_radio = ttk.Radiobutton(upload_tab, text="YouTube URL", variable=self.upload_type, value="youtube", command=self.toggle_upload_source)
        youtube_radio.grid(row=1, column=1, padx=10, pady=10, sticky="w")

        # File path / URL
        self.source_label = ttk.Label(upload_tab, text="Video Path:")
        self.source_label.grid(row=2, column=0, padx=10, pady=10, sticky="w")
        self.source_entry = ttk.Entry(upload_tab)
        self.source_entry.grid(row=2, column=1, padx=10, pady=10, sticky="ew")
        self.browse_button = ttk.Button(upload_tab, text="Browse...", command=self.browse_local_video)
        self.browse_button.grid(row=2, column=2, padx=10, pady=10, sticky="w")

        # Caption
        caption_label = ttk.Label(upload_tab, text="Caption:")
        caption_label.grid(row=3, column=0, padx=10, pady=10, sticky="nw")
        self.caption_text = tk.Text(upload_tab, height=6, wrap="word")
        self.caption_text.grid(row=3, column=1, padx=10, pady=10, sticky="nsew")
        self.caption_scrollbar = ttk.Scrollbar(upload_tab, orient="vertical", command=self.caption_text.yview)
        self.caption_scrollbar.grid(row=3, column=2, padx=(0, 10), pady=10, sticky="ns")
        self.caption_text.configure(yscrollcommand=self.caption_scrollbar.set)

        # AI label toggle
        self.ai_generated_var = tk.BooleanVar(value=False)
        self.ai_checkbox = ttk.Checkbutton(upload_tab, text="Mark as AI-generated", variable=self.ai_generated_var)
        self.ai_checkbox.grid(row=4, column=1, padx=10, pady=(0, 5), sticky="w")

        # Schedule time
        schedule_frame = ttk.Frame(upload_tab)
        schedule_frame.grid(row=5, column=1, padx=10, pady=(0, 5), sticky="ew")
        schedule_frame.columnconfigure(1, weight=1)
        schedule_label = ttk.Label(schedule_frame, text="Schedule (seconds from now, 0 for immediate):")
        schedule_label.grid(row=0, column=0, sticky="w")
        self.schedule_entry = ttk.Entry(schedule_frame)
        self.schedule_entry.grid(row=0, column=1, padx=(8, 0), sticky="ew")

        # Interaction permissions
        permissions_frame = ttk.Frame(upload_tab)
        permissions_frame.grid(row=6, column=1, padx=10, pady=(0, 5), sticky="w")
        self.allow_comment_var = tk.BooleanVar(value=True)
        self.allow_duet_var = tk.BooleanVar(value=False)
        self.allow_stitch_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(permissions_frame, text="Allow Comments", variable=self.allow_comment_var).grid(row=0, column=0, padx=(0, 10), sticky="w")
        ttk.Checkbutton(permissions_frame, text="Allow Duet", variable=self.allow_duet_var).grid(row=0, column=1, padx=(0, 10), sticky="w")
        ttk.Checkbutton(permissions_frame, text="Allow Stitch", variable=self.allow_stitch_var).grid(row=0, column=2, sticky="w")

        # Visibility
        visibility_frame = ttk.Frame(upload_tab)
        visibility_frame.grid(row=7, column=1, padx=10, pady=(0, 5), sticky="ew")
        ttk.Label(visibility_frame, text="Visibility:").grid(row=0, column=0, sticky="w")
        self.visibility_combobox = ttk.Combobox(visibility_frame, state="readonly", values=list(self.visibility_options.keys()))
        self.visibility_combobox.grid(row=0, column=1, padx=(8, 0), sticky="ew")
        self.visibility_combobox.current(0)

        # Brand settings
        brand_frame = ttk.Frame(upload_tab)
        brand_frame.grid(row=8, column=1, padx=10, pady=(0, 5), sticky="w")
        self.brand_organic_var = tk.BooleanVar(value=False)
        self.branded_content_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(brand_frame, text="Brand Organic", variable=self.brand_organic_var).grid(row=0, column=0, padx=(0, 10), sticky="w")
        ttk.Checkbutton(brand_frame, text="Branded Content", variable=self.branded_content_var).grid(row=0, column=1, sticky="w")

        # Proxy
        proxy_frame = ttk.Frame(upload_tab)
        proxy_frame.grid(row=9, column=1, padx=10, pady=(0, 5), sticky="ew")
        proxy_frame.columnconfigure(1, weight=1)
        ttk.Label(proxy_frame, text="Proxy (optional):").grid(row=0, column=0, sticky="w")
        self.proxy_entry = ttk.Entry(proxy_frame)
        self.proxy_entry.grid(row=0, column=1, padx=(8, 0), sticky="ew")

        # Upload button
        upload_button = ttk.Button(upload_tab, text="Upload", command=self.upload_video)
        upload_button.grid(row=10, column=1, padx=10, pady=10, sticky="e")

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
            tiktok.login(user_name)
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
        user = self.user_combobox.get()
        source = self.source_entry.get()
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

        if not user or not source or not caption:
            messagebox.showerror("Missing information", "Please select a user, choose a video, and enter a caption.")
            return

        schedule_value = self.schedule_entry.get().strip()
        if schedule_value:
            try:
                schedule_time = int(schedule_value)
                if schedule_time < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid schedule", "Schedule time must be a non-negative integer (seconds).")
                return
        else:
            schedule_time = 0

        try:
            if self.upload_type.get() == "local":
                video_path = source
                if not os.path.isabs(video_path):
                    video_path = os.path.join(self.video_dir, video_path)
                if not os.path.exists(video_path):
                    messagebox.showerror("Video not found", f"Video not found: {video_path}")
                    return
                tiktok.upload_video(
                    user,
                    video_path,
                    caption,
                    schedule_time=schedule_time,
                    allow_comment=allow_comment,
                    allow_duet=allow_duet,
                    allow_stitch=allow_stitch,
                    visibility_type=visibility_type,
                    brand_organic_type=brand_organic_type,
                    branded_content_type=branded_content_type,
                    ai_label=ai_label,
                    proxy=proxy or None,
                )
            else:
                from tiktok_uploader.Video import Video
                video_obj = Video(source, caption)
                video_obj.is_valid_file_format()
                video = video_obj.source_ref
                tiktok.upload_video(
                    user,
                    video,
                    caption,
                    schedule_time=schedule_time,
                    allow_comment=allow_comment,
                    allow_duet=allow_duet,
                    allow_stitch=allow_stitch,
                    visibility_type=visibility_type,
                    brand_organic_type=brand_organic_type,
                    branded_content_type=branded_content_type,
                    ai_label=ai_label,
                    proxy=proxy or None,
                )
        except RuntimeError as err:
            messagebox.showerror("Upload failed", str(err))
            return


if __name__ == "__main__":
    app = TiktokUploaderGUI()
    app.mainloop()
