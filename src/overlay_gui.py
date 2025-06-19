import os, time, re, subprocess, psutil, shutil, json, keyboard
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
from idlelib.tooltip import Hovertip

"""Initialize global variables"""
HOTKEYS_FILE = "data/hotkeys.json"
SETTINGS_FILE = "data/overlay_settings.json"

DEFAULT_SETTINGS = {
    "overlay_pid": None,
    "overlay_location": "Top Right",
    "icon_size": 44,
}

overlay_pid = None
previous_image_path = None
last_saved_state = {
    "name": "",
    "hotkey": "",
    "image": None
}

BACKGROUND_COLOR = "#f0f0f0"
add_apply_button_enabled = False
delete_confirmation = False

class HotkeyEntry(tk.Entry):
    """Logic for capturing key combinations."""

    def __init__(self, master=None, **kwargs):
        """Initialize the HotkeyEntry widget."""
        super().__init__(master, **kwargs)
        self.keys_pressed = set()
        self.key_order = []
        self.is_recording = False
        self.default_text = "Click to set hotkey"
        self.insert(0, self.default_text)
        self.bind("<FocusIn>", self.on_focus_in)
        self.bind("<FocusOut>", self.on_focus_out)
        self.bind("<Key>", self.prevent_default)

    def get_hotkey(self):
        """Return the current key combination or an empty string."""
        current_text = self.get()
        return current_text if current_text != self.default_text else ""

    def on_focus_in(self, event):
        """Start recording hotkeys on focus."""
        if not self.is_recording:
            self.is_recording = True
            current_text = self.get()
            if current_text == self.default_text:
                self.delete(0, tk.END)
            self.keys_pressed.clear()
            self.key_order.clear()
            keyboard.hook(self.check_hotkeys)

    def on_focus_out(self, event):
        """Stop recording hotkeys on focus out."""
        if self.is_recording:
            self.finish_recording()

    def prevent_default(self, event):
        """Prevent default key event processing."""
        return "break"

    def check_hotkeys(self, event):
        """Process key events and update the key combination."""
        if not self.is_recording:
            return
        
        capitalized_key = self.capitalize_key(event.name)

        if event.event_type == keyboard.KEY_DOWN:
            if capitalized_key not in self.keys_pressed:
                self.keys_pressed.add(capitalized_key)
                if capitalized_key in self.key_order:
                    self.key_order.remove(capitalized_key)
                self.key_order.append(capitalized_key)
                self.update_display()
                enable_add_apply_button()
        
        elif event.event_type == keyboard.KEY_UP:
            if capitalized_key in self.keys_pressed:
                self.keys_pressed.remove(capitalized_key)
                self.key_order.remove(capitalized_key)
                if not self.keys_pressed:
                    self.finish_recording()
                enable_add_apply_button()

    def capitalize_key(self, key):
        """Capitalize the first letter of every word in a key."""
        return ' '.join(word.capitalize() for word in key.split())

    def update_display(self):
        """Update the Entry widget to display the current key combination."""
        hotkey_str = " + ".join(self.key_order)
        self.delete(0, tk.END)
        self.insert(0, hotkey_str)

    def finish_recording(self):
        """Finish recording the key combination."""
        self.is_recording = False
        keyboard.unhook(self.check_hotkeys)
        if not self.get():
            self.insert(0, self.default_text)
        self.master.focus_set()
    
class CustomTooltip(Hovertip):
    """Create the tooltip when hovering over the Upload Image button."""

    def __init__(self, widget, text, hover_delay=1000, x_min=0, x_max=100, y_min=0, y_max=100):
        """Initialize the tooltip with boundaries constrained to the Upload Image button."""
        super().__init__(widget, text, hover_delay)
        self.widget = widget
        self.BACKGROUND_COLOR = BACKGROUND_COLOR
        self.last_motion = 0
        self.widget.bind("<Motion>", self.on_motion)
        self.x_min, self.x_max = x_min, x_max
        self.y_min, self.y_max = y_min, y_max

    def showtip(self):
        """Display the tooltip if conditions are met."""
        if time.time() - self.last_motion < 1:
            return
        if self.tipwindow:
            return
        x = self.widget.winfo_pointerx()
        y = self.widget.winfo_pointery()
        
        widget_x = self.widget.winfo_rootx() + 2
        widget_y = self.widget.winfo_rooty() + 3
        if not (self.x_min <= x - widget_x <= self.x_max and self.y_min <= y - widget_y <= self.y_max):
            return

        x -= 82
        y -= 21
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(1)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background=self.BACKGROUND_COLOR, relief=tk.SOLID, borderwidth=1)
        label.pack(ipadx=1)

    def on_motion(self, event):
        """Handle mouse motion events to control the tooltip."""
        self.last_motion = time.time()
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None
        self.schedule()

    def hidetip(self):
        """Hide the tooltip."""
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None

def load_overlay_settings():
    """Load overlay settings from overlay_settings.json."""
    global DEFAULT_SETTINGS
    if not os.path.exists(SETTINGS_FILE):
        save_overlay_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS
    with open(SETTINGS_FILE, "r") as file:
        settings = json.load(file)
        for key, value in DEFAULT_SETTINGS.items():
            if key not in settings:
                settings[key] = value
        return settings

def save_overlay_settings(settings):
    """Save overlay settings to overlay_settings.json."""
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as file:
        json.dump(settings, file, indent=4)

def load_previous_process():
    """Load and verify the previous overlay process."""
    global overlay_pid
    if overlay_is_running():
        with open(SETTINGS_FILE, "r") as file:
            data = json.load(file)
        pid = data.get("overlay_pid")
        if pid:
            try:
                overlay_pid = psutil.Process(pid)
                if not overlay_pid.is_running() or overlay_pid.status() == psutil.STATUS_ZOMBIE:
                    overlay_pid = None
                    save_overlay_status(None)
            except psutil.NoSuchProcess:
                overlay_pid = None
                save_overlay_status(None)
    else:
        overlay_pid = None

def overlay_is_running():
    """Check if the overlay is running."""
    try:
        with open(SETTINGS_FILE, "r") as file:
            data = json.load(file)
        pid = data.get("overlay_pid")
        if pid is not None:
            try:
                process = psutil.Process(pid)
                return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
            except psutil.NoSuchProcess:
                return False
    except (FileNotFoundError, json.JSONDecodeError):
        return False
    return False

def save_overlay_status(pid=None):
    """Save the current overlay process ID to overlay_settings.json."""
    try:
        with open(SETTINGS_FILE, "r") as file:
            data = json.load(file)
        
        data["overlay_pid"] = pid

        with open(SETTINGS_FILE, "w") as file:
            json.dump(data, file, indent=4)
    except IOError as e:
        messagebox.showerror("Error", f"Failed to save overlay status: {e}")

def create_gui():
    """Create and set up the GUI."""
    global root, frame, entry_new_name, entry_hotkey, upload_button, add_apply_button, start_stop_button, icon_dropdown, icon_menu, delete_button, toggle_button, icon_size_var, upload_photo

    root = tk.Tk()
    root.title("Microphone Status Overlay GUI")
    root.geometry("393x280")
    root.resizable(False, False)
    root.configure(bg=BACKGROUND_COLOR)
    root.iconbitmap("assets/Microphone.ico")

    frame = tk.Frame(root, bg=BACKGROUND_COLOR)
    frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    tk.Label(frame, text="Select:").grid(row=0, column=0, sticky="e", padx=(0, 5))
    icon_dropdown = tk.StringVar(root)
    icon_names = ["New Icon"] + list(load_hotkeys().keys())
    icon_dropdown.set(icon_names[0])
    
    icon_menu = tk.OptionMenu(frame, icon_dropdown, *icon_names)
    icon_menu.config(width=12)
    icon_menu.grid(row=0, column=1, padx=(3, 5), pady=5, sticky="ew")

    delete_button = tk.Button(frame, text="Delete", command=toggle_delete_confirm, width=7)
    delete_button.grid(row=0, column=2, padx=(5, 5), pady=5)
    delete_button.config(state="disabled", text="Delete")

    tk.Label(frame, text="Name:").grid(row=1, column=0, sticky="e", padx=(0, 5))
    entry_new_name = tk.Entry(frame, width=30)
    entry_new_name.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky="ew")

    tk.Label(frame, text="Hotkey:").grid(row=2, column=0, sticky="e", padx=(0, 5))
    entry_hotkey = HotkeyEntry(frame, text="Click to set hotkey", width=30)
    entry_hotkey.grid(row=2, column=1, columnspan=2, padx=5, pady=5, sticky="ew")

    tk.Label(frame, text="Location:").grid(row=3, column=0, sticky="e", padx=(0, 5))

    upload_icon_path = "assets/Upload_Image.png"
    upload_photo = ImageTk.PhotoImage(Image.open(upload_icon_path).resize((96, 96), Image.LANCZOS))
    
    upload_button = tk.Button(frame, image=upload_photo, command=upload_image, width=96, height=96)
    upload_button.image = upload_photo
    upload_button.grid(row=0, column=3, rowspan=3, padx=(10, 0), pady=5)
    CustomTooltip(upload_button, "Upload Image", hover_delay=1000, x_min=0, x_max=96, y_min=0, y_max=96)

    create_location_buttons(frame)

    fake_image = tk.PhotoImage(width=1, height=1)
    toggle_button = tk.Button(frame, text="Toggle Icon", command=toggle_icon_state, image=fake_image, width=96, height=48, compound="c")
    toggle_button.image = fake_image
    toggle_button.grid(row=3, column=3, padx=(10, 0), pady=(7, 0), sticky="n")

    icon_size_frame = tk.Frame(frame)
    icon_size_frame.place(in_=frame, x=262, y=184)

    tk.Label(icon_size_frame, text="Icon Size:").pack(side=tk.LEFT)
    icon_size_var = tk.IntVar(value=load_overlay_settings().get("icon_size", 44))
    icon_size_spinbox = tk.Spinbox(icon_size_frame, from_=10, to=1000, width=3, textvariable=icon_size_var, command=update_icon_size, increment=5)
    icon_size_spinbox.pack(side=tk.LEFT)

    px_frame = tk.Frame(frame)
    px_frame.place(in_=frame, y=184)

    tk.Label(icon_size_frame, text="px").pack(side=tk.LEFT)

    icon_dropdown.trace_add("write", on_dropdown_change)

    button_frame = tk.Frame(root)
    button_frame.pack(fill=tk.X, padx=10, pady=10)

    ok_button = tk.Button(button_frame, text="OK", command=ok_action, width=5)
    add_apply_button = tk.Button(button_frame, text="Add Icon", command=apply_action, width=7, state="disabled", relief="sunken")
    cancel_button = tk.Button(button_frame, text="Cancel", command=root.destroy, width=6)
    start_stop_button = tk.Button(button_frame, text="Stop Microphone Overlay", command=start_stop_overlay, width=11)

    ok_button.pack(side=tk.RIGHT, padx=(5, 5))
    cancel_button.pack(side=tk.RIGHT, padx=(5, 5))
    add_apply_button.pack(side=tk.RIGHT, padx=(5, 5))
    start_stop_button.pack(side=tk.LEFT, padx=5)

    entry_new_name.bind("<KeyPress>", enable_add_apply_button)
    icon_size_spinbox.bind("<KeyRelease>", update_icon_size)

    return root

def load_hotkeys():
    """Load hotkeys from hotkeys.json or initialize System Mute hotkey."""
    try:
        with open(HOTKEYS_FILE, "r") as f:
            hotkeys = json.load(f)
        if not hotkeys:
            hotkeys = {"System Mute": ["Ctrl", "Shift", "A", False]}
            with open(HOTKEYS_FILE, "w") as f:
                json.dump(hotkeys, f, indent=4)
        return hotkeys
    except FileNotFoundError:
        hotkeys = {"System Mute": ["Ctrl", "Shift", "A", False]}
        with open(HOTKEYS_FILE, "w") as f:
            json.dump(hotkeys, f, indent=4)
        return hotkeys
    
def toggle_delete_confirm():
    """Toggle delete confirmation state."""
    global delete_confirmation, root
    selected = icon_dropdown.get()
    
    if not delete_confirmation:
        delete_button.config(text="Confirm")
        delete_confirmation = True
        root.bind("<Button-1>", check_focus)
    else:
        delete_icon(selected)

def upload_image():
    """Handle image upload for icons."""
    global previous_image_path
    file_path = filedialog.askopenfilename(filetypes=[("Image Files", "*.png;*.jpg;*.jpeg")])
    if file_path:
        img = Image.open(file_path).resize((96, 96), Image.LANCZOS)
        img_tk = ImageTk.PhotoImage(img)
        upload_button.config(image=img_tk, text="", width=96, height=96)
        upload_button.image = img_tk
        previous_image_path = file_path
    enable_add_apply_button()

def create_location_buttons(frame):
    """Create buttons for choosing overlay location."""
    global location_frame
    location_frame = tk.Frame(frame)
    location_frame.grid(row=3, column=1, columnspan=2, padx=(3, 0), pady=(5, 0), sticky="w")

    locations = [
        "Top Left", "Top Middle", "Top Right",
        "Middle Left", "", "Middle Right",
        "Bottom Left", "Bottom Middle", "Bottom Right"
    ]

    settings = load_overlay_settings()
    current_location = settings.get("overlay_location", "Top Right")

    button_width = 7
    button_height = 1
    for i, loc in enumerate(locations):
        row = i // 3
        col = i % 3
        if loc:
            btn_text = "X" if loc == current_location else ""
            btn = tk.Button(location_frame, text=btn_text, width=button_width, height=button_height, 
                            command=lambda l=loc: update_overlay_location(l))
            btn.location = loc
            btn.grid(row=row, column=col, padx=2, pady=2)
        elif row == 1 and col == 1:
            tk.Label(location_frame, text="").grid(row=row, column=col, padx=5, pady=5)

def on_dropdown_change(var_name: str, index: str, mode: str):
    """Handle changes in the icon dropdown menu."""
    global delete_confirmation, add_apply_button_enabled
    selected = icon_dropdown.get()
    
    if selected == "New Icon" or selected == "System Mute":
        delete_button.config(state="disabled")
        toggle_button.config(state="disabled")
    else:
        delete_button.config(state="normal")
        toggle_button.config(state="normal")
    
    add_apply_button.config(state="disabled", relief="sunken")
    add_apply_button_enabled = False

    add_apply_button.config(text="Add Icon" if selected == "New Icon" else "Apply")

    reset_delete_button_state()
    update_toggle_button_state()

    if selected == "New Icon":
        entry_new_name.config(state="normal")
        entry_new_name.delete(0, tk.END)
        entry_hotkey.delete(0, tk.END)
        entry_hotkey.insert(0, entry_hotkey.default_text)
        upload_button.config(image=upload_photo)
        upload_button.image = upload_photo
    elif selected == "System Mute":
        entry_new_name.config(state="normal")
        entry_new_name.delete(0, tk.END)
        entry_new_name.insert(0, "System Mute")
        entry_new_name.config(state="readonly")
    else:
        entry_new_name.config(state="normal")

    load_icon_data(selected)

def ok_action():
    """Apply settings when OK button is pressed."""
    save_icon(True)

def apply_action():
    """Apply settings when Add Icon/Apply button is pressed."""
    save_icon(False)

def start_stop_overlay():
    """Start or stop the overlay."""
    global overlay_pid

    if overlay_is_running():
        if overlay_pid:
            try:
                overlay_pid.terminate()
                overlay_pid = None
                save_overlay_status(None)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to stop overlay: {e}")
        else:
            messagebox.showerror("Error", "Overlay process handle is missing.")
    else:
        try:
            overlay_pid = subprocess.Popen(["pythonw", "src/overlay.py"], 
                             creationflags=subprocess.CREATE_NO_WINDOW,
                             start_new_session=True)
            save_overlay_status(overlay_pid.pid)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start overlay: {e}")

    update_start_stop_button()

def enable_add_apply_button(event=None):
    """Enable the Add Icon/Apply button."""
    global add_apply_button_enabled
    selected_icon = icon_dropdown.get()
    
    if selected_icon != "System Mute":
        add_apply_button.config(state="normal", relief="raised")
        add_apply_button_enabled = True
    else:
        if entry_hotkey.focus_get() == entry_hotkey:
            add_apply_button.config(state="normal", relief="raised")
            add_apply_button_enabled = True

def update_icon_size(event=None):
    """Updates icon size."""
    try:
        size = int(icon_size_var.get())
        if size == 0:
            return
        settings = load_overlay_settings()
        if settings["icon_size"] != size:
            settings["icon_size"] = size
            save_overlay_settings(settings)
            restart_overlay()
    except (tk.TclError, ValueError):
        return

def delete_icon(icon_name):
    """Delete the selected icon."""
    if icon_name == "New Icon" or icon_name == "System Mute":
        return

    try:
        hotkeys = load_hotkeys()
        if icon_name in hotkeys:
            del hotkeys[icon_name]
            with open(HOTKEYS_FILE, "w") as f:
                json.dump(hotkeys, f, indent=4)

        for file in os.listdir("icons"):
            if file.startswith(sanitize(icon_name) + "."):
                os.remove(os.path.join("icons", file))
                break

        icon_names = ["New Icon"] + list(hotkeys.keys())
        icon_dropdown.set("New Icon")
        icon_menu["menu"].delete(0, "end")
        for name in icon_names:
            icon_menu["menu"].add_command(label=name, command=tk._setit(icon_dropdown, name, load_icon_data))

        reset_delete_button_state()
        load_icon_data("New Icon")
        restart_overlay()
    except Exception as e:
        messagebox.showerror("Error", f"Failed to delete icon: {str(e)}")

def update_overlay_location(location):
    """Update the overlay location in overlay_settings.json."""
    settings = load_overlay_settings()
    settings["overlay_location"] = location
    save_overlay_settings(settings)
    update_location_buttons()
    restart_overlay()

def reset_delete_button_state(event=None):
    """Reset the Delete button state."""
    global delete_confirmation, delete_button
    delete_button.config(text="Delete")
    delete_confirmation = False

def update_toggle_button_state():
    """Update the Toggle Icon button state."""
    selected = icon_dropdown.get()
    if selected == "New Icon":
        toggle_button.config(text="Toggle Icon", state="disabled")
    else:
        toggle_button.config(text=f"Toggle Icon", state="normal")

def load_icon_data(selection):
    """Load data for the selected icon."""
    global previous_image_path, last_saved_state

    if selection == "New Icon":
        previous_image_path = None
        last_saved_state = {
            "name": "",
            "hotkey": "",
            "image": None
        }
    else:
        hotkeys = load_hotkeys()
        if selection in hotkeys:
            entry_new_name.delete(0, tk.END)
            entry_new_name.insert(0, selection)
            entry_hotkey.delete(0, tk.END)
            entry_hotkey.insert(0, " + ".join(hotkeys[selection][:-1]))
            
            icon_path = None
            for file in os.listdir("icons"):
                if file.startswith(sanitize(selection) + "."):
                    icon_path = os.path.join("icons", file)
                    break

            if icon_path and os.path.exists(icon_path):
                if icon_path != previous_image_path:
                    img = Image.open(icon_path).resize((96, 96), Image.LANCZOS)
                    img_tk = ImageTk.PhotoImage(img)
                    upload_button.config(image=img_tk, text="", width=96, height=96)
                    upload_button.image = img_tk
                    previous_image_path = icon_path
            last_saved_state = {
                "name": selection,
                "hotkey": " + ".join(hotkeys[selection][:-1]),
                "image": icon_path if icon_path and os.path.exists(icon_path) else None
            }
    
    update_toggle_button_state()

def save_icon(OK):
    """Save icon and terminate GUI if OK button pressed."""
    global last_saved_state, previous_image_path, add_apply_button_enabled

    if not validate_save():
        return

    current_state = {
        "name": entry_new_name.get().strip(),
        "hotkey": entry_hotkey.get_hotkey(),
        "image": previous_image_path,
        "icon_size": int(icon_size_var.get())
    }
    
    selected = icon_dropdown.get()
    if selected == "System Mute":
        hotkeys = load_hotkeys()
        current_state["enabled"] = hotkeys["System Mute"][-1]
    
    if current_state != last_saved_state:
        try:
            old_name = last_saved_state["name"]
            old_image_path = last_saved_state["image"]
            
            if selected != "System Mute":
                new_image_extension = os.path.splitext(current_state["image"])[1]
                sanitized_name = sanitize(current_state["name"])
                new_image_path = f"icons/{sanitized_name}{new_image_extension}"

                image_changed = current_state["image"] != old_image_path

                if old_name and old_image_path and os.path.exists(old_image_path):
                    if old_name != current_state["name"]:
                        if image_changed:
                            if os.path.exists(old_image_path):
                                os.remove(old_image_path)
                            shutil.copy(current_state["image"], new_image_path)
                        else:
                            os.rename(old_image_path, new_image_path)
                    else:
                        if image_changed:
                            os.remove(old_image_path)
                            shutil.copy(current_state["image"], new_image_path)
                        else:
                            new_image_path = old_image_path
                else:
                    shutil.copy(current_state["image"], new_image_path)
            else:
                new_image_path = None

            update_hotkeys(current_state["name"], current_state["hotkey"], old_name)
            
            last_saved_state = {
                "name": current_state["name"],
                "hotkey": current_state["hotkey"],
                "image": new_image_path,
                "icon_size": current_state["icon_size"]
            }
            if selected != "System Mute":
                previous_image_path = new_image_path

            update_icon_size()

            if add_apply_button_enabled:
                hotkeys = load_hotkeys()
                icon_names = ["New Icon"] + list(hotkeys.keys())
                icon_dropdown.set(current_state["name"])
                icon_menu["menu"].delete(0, "end")
                for name in icon_names:
                    icon_menu["menu"].add_command(label=name, command=tk._setit(icon_dropdown, name, load_icon_data))

                restart_overlay()

            if OK:
                root.destroy()
            else:
                add_apply_button.config(state="disabled", relief="sunken")
                add_apply_button_enabled = False

        except Exception as e:
            messagebox.showerror("Error", f"Failed to save icon: {str(e)}")

def update_start_stop_button():
    """Update the Start/Stop button text to match current overlay process state."""
    start_stop_button.config(text="Stop Overlay" if overlay_is_running() else "Start Overlay")

def restart_overlay():
    """Restart the overlay."""
    global overlay_pid
    if overlay_is_running():
        try:
            if overlay_pid:
                overlay_pid.terminate()
                overlay_pid.wait()
            overlay_pid = subprocess.Popen(["pythonw", "src/overlay.py"], 
                             creationflags=subprocess.CREATE_NO_WINDOW,
                             start_new_session=True)
            save_overlay_status(overlay_pid.pid)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to restart overlay: {e}")

def sanitize(filename):
    """Remove characters not allowed by file system and replace spaces with underscores."""
    return re.sub(r'[<>:"/\\|?*]', '', filename).strip(". ").replace(" ", "_")

def validate_save():
    """Validate current icon settings."""
    original_name = entry_new_name.get()
    trimmed_name = original_name.strip()
    hotkey_string = entry_hotkey.get_hotkey()
    error_message = ""

    existing_hotkeys = load_hotkeys()
    if any(trimmed_name.lower() == existing_name.lower() for existing_name in existing_hotkeys) and trimmed_name.lower() != last_saved_state["name"].lower():
        messagebox.showerror("Error", f'"{trimmed_name}" already exists. Please choose a different name.')
        return False

    if not trimmed_name or trimmed_name == "New Icon":
        error_message += "Please enter a name"

    if not hotkey_string:
        if not error_message:
            error_message = "Please set a hotkey"
        else:
            error_message += " and set a hotkey"

    if not previous_image_path and icon_dropdown.get() != "System Mute":
        if not error_message:
            error_message = "Please select an image"
        else:
            error_message += " and select an image"

    if error_message == "Please enter a name and set a hotkey and select an image":
        root.destroy()
        return False
        
    if error_message != "":
        error_message += "."
        messagebox.showerror("Error", error_message)
        return False

    try:
        icon_size = int(icon_size_var.get())
    except (tk.TclError, ValueError):
        messagebox.showerror("Error", "Please enter a valid number for the icon size.")
        return False

    return True

def toggle_icon_state():
    """Manually toggle the selected icon in the overlay."""
    selected = icon_dropdown.get()
    hotkeys = load_hotkeys()
    if selected in hotkeys:
        hotkeys[selected][-1] = not hotkeys[selected][-1]
        with open(HOTKEYS_FILE, "w") as f:
            json.dump(hotkeys, f, indent=4)
        update_toggle_button_state()
    elif selected == "System Mute":
        hotkeys["System Mute"][-1] = not hotkeys["System Mute"][-1]
        with open(HOTKEYS_FILE, "w") as f:
            json.dump(hotkeys, f, indent=4)
        update_toggle_button_state()
    restart_overlay()

from collections import OrderedDict

def update_hotkeys(new_name, hotkey_string, old_name=None):
    """Update hotkeys.json with updated hotkey data."""
    try:
        with open(HOTKEYS_FILE, "r") as f:
            hotkeys = json.load(f, object_pairs_hook=OrderedDict)

        if old_name and old_name in hotkeys:
            enabled_state = hotkeys[old_name][-1]
            if old_name != new_name:
                hotkeys = OrderedDict((new_name if k == old_name else k, v) for k, v in hotkeys.items())
        elif new_name in hotkeys:
            enabled_state = hotkeys[new_name][-1]
        else:
            enabled_state = True
            hotkeys[new_name] = []

        hotkeys[new_name] = hotkey_string.split(" + ") + [enabled_state]

        with open(HOTKEYS_FILE, "w") as f:
            json.dump(hotkeys, f, indent=4, ensure_ascii=False)

    except Exception as e:
        messagebox.showerror("Error", f"Failed to update hotkeys: {str(e)}")

def update_location_buttons():
    """Update location buttons to reflect the current overlay location."""
    settings = load_overlay_settings()
    current_location = settings.get("overlay_location", "Top Right")
    
    for child in location_frame.winfo_children():
        if isinstance(child, tk.Button) and hasattr(child, "location"):
            child.config(text="X" if child.location == current_location else "")

def check_focus(event):
    """Reset Delete button if clicked outside Confirm."""
    global delete_confirmation, delete_button, root
    if delete_confirmation and event.widget != delete_button:
        reset_delete_button_state()
        root.unbind("<Button-1>")

load_overlay_settings()
load_previous_process()

root = create_gui()
load_icon_data("New Icon")
update_start_stop_button()
root.mainloop()