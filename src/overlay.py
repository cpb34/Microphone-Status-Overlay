import sys, os, re, json, keyboard
from PyQt5.QtWidgets import QApplication, QWidget, QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

"""Initialize global variables"""
HOTKEYS_FILE = "data/hotkeys.json"
SETTINGS_FILE = "data/overlay_settings.json"

class IconOverlay(QWidget):
    """Manage the icon overlay."""

    def __init__(self):
        """Initialize the IconOverlay widget."""
        super().__init__(flags=Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.load_overlay_settings()
        self.load_hotkeys()
        self.cache_icon_paths()
        self.setup_overlay()
        self.setup_key_combos()
        self.apply_current_state()

    def load_overlay_settings(self):
        """Load overlay settings from overlay_settings.json."""
        try:
            with open(SETTINGS_FILE, "r") as f:
                self.settings = json.load(f)
        except FileNotFoundError:
            self.settings = {
                "overlay_location": "Top Right",
                "icon_size": 45,
            }
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, "w") as f:
                json.dump(self.settings, f, indent=4)

    def load_hotkeys(self):
        """Load hotkeys from hotkeys.json or initialize System Mute hotkey."""
        try:
            with open(HOTKEYS_FILE, "r") as f:
                hotkeys_data = json.load(f)
        except FileNotFoundError:
            hotkeys_data = {"System Mute": ["Ctrl", "Shift", "A", False]}
            os.makedirs(os.path.dirname(HOTKEYS_FILE), exist_ok=True)
            with open(HOTKEYS_FILE, "w") as f:
                json.dump(hotkeys_data, f, indent=4)

        self.hotkeys = {k: v[:-1] for k, v in hotkeys_data.items()}
        self.icon_states = {k: v[-1] for k, v in hotkeys_data.items()}

    def cache_icon_paths(self):
        """Cache the file paths for all icon images."""
        self.icon_paths = {}
        for icon_name in self.hotkeys.keys():
            sanitized_icon_name = sanitize(icon_name)
            for file in os.listdir("icons"):
                if file.startswith(f"{sanitized_icon_name}."):
                    self.icon_paths[icon_name] = os.path.join("icons", file)
                    break
    
    def setup_overlay(self):
        """Set up the overlay according to overlay_settings.json."""
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(0, 0, screen.width(), screen.height())

        self.icons = {}
        self.master_mute_icon = None

        x_start, y_start, x_direction, y_direction = self.overlay_location()
        x_offset, y_offset = x_start, y_start

        if "System Mute" in self.hotkeys:
            self.master_mute_icon = self.create_icons("System Mute", x_offset, y_offset)

        for icon_name in self.hotkeys.keys():
            if icon_name != "System Mute":
                icon = self.create_icons(icon_name, x_offset, y_offset)
                self.icons[icon_name] = icon
                
                x_offset += x_direction * (self.settings["icon_size"] + 5)
                y_offset += y_direction * (self.settings["icon_size"] + 5)

    def setup_key_combos(self):
        """Manage current key combos."""
        self.last_combo = None
        for hotkey, combo in self.hotkeys.items():
            keyboard.add_hotkey("+".join(combo), self.check_hotkey, args=(hotkey,))
        
        keyboard.on_release(self.reset_last_combo)

    def apply_current_state(self):
        """Apply current mute states to icons."""
        if self.icon_states["System Mute"]:
            for icon in self.icons.values():
                icon.hide()
            if self.master_mute_icon:
                self.master_mute_icon.show()
        else:
            if self.master_mute_icon:
                self.master_mute_icon.hide()
            for icon_name, icon in self.icons.items():
                icon.setVisible(self.icon_states[icon_name])
        
        self.update()

    def overlay_location(self):
        """Update the overlay location and icon orientation."""
        screen = QApplication.primaryScreen().geometry()
        icon_size = self.settings["icon_size"]
        padding = 3
        total_width = (len(self.hotkeys) - 1) * (icon_size + padding)
        total_height = total_width

        positions = {
            "Top Left": (padding, padding, 1, 0),
            "Top Middle": (screen.width() // 2 - total_width // 2, padding, 1, 0),
            "Top Right": (screen.width() - icon_size - padding, padding, -1, 0),
            "Bottom Left": (padding, screen.height() - icon_size - padding, 1, 0),
            "Bottom Middle": (screen.width() // 2 - total_width // 2, screen.height() - icon_size - padding, 1, 0),
            "Bottom Right": (screen.width() - icon_size - padding, screen.height() - icon_size - padding, -1, 0),
            "Middle Left": (padding, screen.height() // 2 - total_height // 2, 0, 1),
            "Middle Right": (screen.width() - icon_size - padding, screen.height() // 2 - total_height // 2, 0, 1)
        }

        return positions.get(self.settings["overlay_location"], positions["Top Right"])

    def create_icons(self, icon_name, x, y):
        """Create and set properties for overlay icons."""
        icon = QLabel(self)
        icon.setAttribute(Qt.WA_TransparentForMouseEvents)
        if icon_name in self.icon_paths:
            icon_path = self.icon_paths[icon_name]
            pixmap = QPixmap(icon_path).scaled(self.settings["icon_size"], self.settings["icon_size"], Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            icon.setPixmap(pixmap)
        icon.setGeometry(x, y, self.settings["icon_size"], self.settings["icon_size"])
        return icon

    def check_hotkey(self, hotkey):
        """Check if current key combo matches a hotkey"""
        current_keys = keyboard.get_hotkey_name().split("+")
        current_combo = current_keys[-1]

        if current_combo != self.last_combo:
            self.last_combo = current_combo
            self.toggle_icon(hotkey)

    def reset_last_combo(self, event):
        """Reset the last key combo."""
        self.last_combo = None

    def toggle_icon(self, icon_name):
        """Toggle an icon's visibility."""
        if icon_name == "System Mute":
            self.icon_states["System Mute"] = not self.icon_states["System Mute"]
        elif icon_name in self.icons:
            self.icon_states[icon_name] = not self.icon_states[icon_name]
        
        self.apply_current_state()
        self.update_hotkeys()

    def update_hotkeys(self):
        """Update hotkeys.json with updated hotkey data."""
        try:
            with open(HOTKEYS_FILE, "r") as f:
                hotkeys_data = json.load(f)
            for icon_name, state in self.icon_states.items():
                if icon_name in hotkeys_data:
                    hotkeys_data[icon_name][-1] = state
            with open(HOTKEYS_FILE, "w") as f:
                json.dump(hotkeys_data, f, indent=4)
        except Exception as e:
            print(f"Error updating hotkeys.json: {e}")

def sanitize(filename):
    """Remove characters not allowed by file system and replace spaces with underscores."""
    return re.sub(r'[<>:"/\\|?*]', '', filename).strip(". ").replace(" ", "_")

app = QApplication(sys.argv)
overlay = IconOverlay()
overlay.show()
sys.exit(app.exec_())