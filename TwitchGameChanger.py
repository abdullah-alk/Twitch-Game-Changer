# TwitchGameChanger.py  (modified: unified tray icon, tray recovery, removed console spam)
import os
import json
import winreg
import subprocess
from pathlib import Path
from typing import List, Set
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import socket
import time
import sys
import gc
import base64
import hashlib

# Optional modules (lazy/light usage)
try:
    import pystray
    from pystray import MenuItem as item
    TRAY_AVAILABLE = True
except Exception:
    pystray = None
    item = None
    TRAY_AVAILABLE = False

# Detect startup mode
STARTUP_MODE = "--startup" in sys.argv

# App directories & files
APP_DATA_DIR = Path(os.getenv('APPDATA', os.path.expanduser('~'))) / "TwitchGameChanger"
APP_DATA_DIR.mkdir(exist_ok=True)
TWITCH_CONFIG_FILE = APP_DATA_DIR / 'twitch_config.json'
EXCLUDED_GAMES_FILE = APP_DATA_DIR / 'excluded_games.json'
GAMES_CACHE_FILE = APP_DATA_DIR / 'games_cache.json'
ICON_CACHE_DIR = APP_DATA_DIR / 'icons'
ICON_CACHE_DIR.mkdir(exist_ok=True)

# ---------- Token Encryption ----------
class TokenEncryption:
    """Secure token storage with machine-specific encryption"""
    @staticmethod
    def _get_machine_key():
        try:
            import uuid, platform
            machine_id = str(uuid.getnode()) + platform.node()
            return hashlib.sha256(machine_id.encode()).digest()
        except: 
            return hashlib.sha256(b'default_key_fallback').digest()
    
    @staticmethod
    def encrypt(data: str) -> str:
        if not data: return ""
        try:
            from cryptography.fernet import Fernet
            key = base64.urlsafe_b64encode(TokenEncryption._get_machine_key())
            return Fernet(key).encrypt(data.encode()).decode()
        except:
            # Fallback XOR encryption
            key = TokenEncryption._get_machine_key()
            encrypted = bytearray()
            for i, char in enumerate(data.encode()):
                encrypted.append(char ^ key[i % len(key)])
            return base64.b64encode(encrypted).decode()
    
    @staticmethod
    def decrypt(data: str) -> str:
        if not data: return ""
        try:
            from cryptography.fernet import Fernet
            key = base64.urlsafe_b64encode(TokenEncryption._get_machine_key())
            return Fernet(key).decrypt(data.encode()).decode()
        except:
            try:
                # Fallback XOR decryption
                key = TokenEncryption._get_machine_key()
                encrypted = base64.b64decode(data.encode())
                decrypted = bytearray()
                for i, byte in enumerate(encrypted):
                    decrypted.append(byte ^ key[i % len(key)])
                return decrypted.decode()
            except:
                # Backward compatibility - return plaintext if decryption fails
                return data

# ---------- Icon Extraction ----------
class IconExtractor:
    """Extract and cache game icons from executables"""
    @staticmethod
    def extract_icon(exe_path: str, game_name: str):
        icon_path = ICON_CACHE_DIR / f"{hashlib.md5(game_name.encode()).hexdigest()}.png"
        if icon_path.exists(): 
            return str(icon_path)
        try:
            from PIL import Image
            import win32api, win32con, win32ui, win32gui
            ico_x = win32api.GetSystemMetrics(win32con.SM_CXICON)
            large, small = win32gui.ExtractIconEx(exe_path, 0)
            if not large: 
                return None
            hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
            hbmp = win32ui.CreateBitmap()
            hbmp.CreateCompatibleBitmap(hdc, ico_x, ico_x)
            hdc_mem = hdc.CreateCompatibleDC()
            hdc_mem.SelectObject(hbmp)
            win32gui.DrawIconEx(hdc_mem.GetHandleOutput(), 0, 0, large[0], ico_x, ico_x, 0, 0, win32con.DI_NORMAL) # type: ignore
            bmpinfo = hbmp.GetInfo()
            bmpstr = hbmp.GetBitmapBits(True)
            img = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1)
            img.save(icon_path, 'PNG')
            win32gui.DestroyIcon(large[0])
            for i in small: 
                win32gui.DestroyIcon(i)
            return str(icon_path)
        except: 
            return None

# ---------- Data class ----------
class Game:
    def __init__(self, name: str, path: str, platform: str, exe_path: str = "", icon: str = ""):
        self.name = name
        self.path = path
        self.platform = platform
        self.exe_path = exe_path if exe_path else path
        self.icon = icon

# ---------- Twitch integration ----------
class TwitchBot:
    CLIENT_ID = 'll2bpleltqt52whwzu4cidrthdgipj'  # kept as in file

    def __init__(self):
        self.config = self.load_config()
        # Decrypt tokens on load
        encrypted_token = self.config.get('access_token')
        self.access_token = TokenEncryption.decrypt(encrypted_token) if encrypted_token else None
        self.user_id = self.config.get('user_id', None)

    def load_config(self) -> dict:
        try:
            if TWITCH_CONFIG_FILE.exists():
                with open(TWITCH_CONFIG_FILE, 'r') as f:
                    cfg = json.load(f)
                    return cfg
        except Exception:
            pass
        return {'channel_name': '', 'enabled': False, 'access_token': None, 'user_id': None}

    def save_config(self):
        try:
            # Encrypt token before saving
            config_to_save = self.config.copy()
            if self.access_token:
                config_to_save['access_token'] = TokenEncryption.encrypt(self.access_token)
            if hasattr(self, 'refresh_token') and self.refresh_token:
                config_to_save['refresh_token'] = TokenEncryption.encrypt(self.refresh_token)
            with open(TWITCH_CONFIG_FILE, 'w') as f:
                json.dump(config_to_save, f, indent=2)
        except Exception:
            pass

    def update_config(self, channel: str, enabled: bool):
        self.config['channel_name'] = channel
        self.config['enabled'] = enabled
        if self.access_token:
            self.config['access_token'] = self.access_token  # Will be encrypted in save_config
        if self.user_id:
            self.config['user_id'] = self.user_id
        self.save_config()

    def authenticate(self) -> bool:
        """Device flow with refresh token storage."""
        if not self.config.get('channel_name'):
            return False
        try:
            import requests, webbrowser, time, threading
            r = requests.post('https://id.twitch.tv/oauth2/device',
                              data={'client_id': self.CLIENT_ID,
                                    'scopes': 'channel:manage:broadcast'},
                              timeout=10)
            if r.status_code != 200:
                return False

            data = r.json()
            user_code, device_code = data['user_code'], data['device_code']
            verify_url = data.get('verification_uri', 'https://www.twitch.tv/activate')
            expires_in = data.get('expires_in', 600)
            interval = data.get('interval', 5)

            webbrowser.open(verify_url)

            popup = tk.Toplevel()
            popup.title("Twitch Authentication")
            popup.geometry("420x260")
            popup.configure(bg="#0f1629")

            tk.Label(popup, text="🔐 Twitch Authentication",
                     font=("Segoe UI", 16, "bold"), bg="#0f1629", fg="#ffffff").pack(pady=15)
            tk.Label(popup, text="Enter this code on Twitch:",
                     bg="#0f1629", fg="#9ca3af", font=("Segoe UI", 11)).pack()
            tk.Label(popup, text=user_code,
                     bg="#0f1629", fg="#9146ff", font=("Segoe UI", 34, "bold")).pack(pady=10)
            tk.Label(popup, text="Waiting for you to authorize...",
                     bg="#0f1629", fg="#60a5fa").pack(pady=10)

            token_data = {}

            def poll():
                start = time.time()
                while time.time() - start < expires_in:
                    time.sleep(interval)
                    t = requests.post('https://id.twitch.tv/oauth2/token', data={
                        'client_id': self.CLIENT_ID,
                        'device_code': device_code,
                        'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
                    }, timeout=10)
                    if t.status_code == 200:
                        token_data.update(t.json())
                        popup.after(0, popup.destroy)
                        break

            threading.Thread(target=poll, daemon=True).start()
            popup.wait_window()

            if 'access_token' in token_data:
                self.access_token = token_data['access_token']
                self.refresh_token = token_data.get('refresh_token')
                self.config.update({
                    'access_token': self.access_token,
                    'refresh_token': self.refresh_token
                })
                self.save_config()
                return True
            return False
        except Exception:
            return False

    def refresh_access_token(self) -> bool:
        """Use stored refresh_token to get a new access_token silently."""
        try:
            import requests
            if not self.config.get('refresh_token'):
                return False
            r = requests.post('https://id.twitch.tv/oauth2/token', data={
                'grant_type': 'refresh_token',
                'refresh_token': self.config['refresh_token'],
                'client_id': self.CLIENT_ID
            }, timeout=10)
            if r.status_code == 200:
                d = r.json()
                self.access_token = d['access_token']
                self.config['access_token'] = d['access_token']
                if 'refresh_token' in d:
                    self.config['refresh_token'] = d['refresh_token']
                self.save_config()
                return True
        except Exception:
            pass
        return False

    def ensure_token_valid(self) -> bool:
        """Check token validity, refresh or re-auth if needed."""
        if not self.access_token:
            if self.refresh_access_token():
                return True
            return self.authenticate()

        try:
            import requests
            h = {'Authorization': f'Bearer {self.access_token}',
                 'Client-Id': self.CLIENT_ID}
            r = requests.get('https://api.twitch.tv/helix/users', headers=h, timeout=6)
            if r.status_code == 200:
                return True
            elif r.status_code == 401:
                if self.refresh_access_token():
                    return True
                return self.authenticate()
        except Exception:
            pass
        return False

    def get_user_id(self) -> bool:
        if not self.access_token:
            return False
        try:
            import requests
            headers = {'Authorization': f'Bearer {self.access_token}'}
            # try /userinfo first
            try:
                resp = requests.get('https://id.twitch.tv/oauth2/userinfo', headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    self.user_id = data.get('sub')
                    self.config['channel_name'] = data.get('preferred_username', self.config.get('channel_name', ''))
                    self.save_config()
                    return True
            except Exception:
                pass

            headers = {'Authorization': f'Bearer {self.access_token}', 'Client-Id': self.CLIENT_ID}
            resp = requests.get('https://api.twitch.tv/helix/users', headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('data'):
                    user = data['data'][0]
                    self.user_id = user.get('id')
                    self.config['channel_name'] = user.get('login', self.config.get('channel_name', ''))
                    self.save_config()
                    return True
            return False
        except Exception:
            return False

    # Game name mapping for games that have different names on Twitch
    GAME_NAME_MAPPING = {
        'little nightmares enhanced edition': 'Little Nightmares II Enhanced Edition',
        'little nightmares': 'Little Nightmares II Enhanced Edition',
        # Add more mappings here as needed
    }

    def smart_search_game(self, game_name: str, is_game_running=True):
        """
        Smart Twitch category picker:
        - Exact match first
        - If not found, take top result
        - If no results but a game is running, set to 'Games + Demos'
        - If nothing running, set to 'Just Chatting'
        """
        if not game_name:
            # No active game detected → Just Chatting
            return "509658"

        # Apply game name mapping if exists
        game_name_lower = game_name.strip().lower()
        mapped_name = self.GAME_NAME_MAPPING.get(game_name_lower, game_name)

        try:
            import requests
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Client-Id': self.CLIENT_ID
            }

            # Search Twitch categories
            r = requests.get(
                'https://api.twitch.tv/helix/search/categories',
                params={'query': mapped_name},
                headers=headers,
                timeout=6
            )

            if r.status_code == 200:
                results = r.json().get('data', [])
                if results:
                    lower_query = mapped_name.strip().lower()

                    # 1️⃣ Exact match (case-insensitive)
                    for item in results:
                        if item.get('name', '').strip().lower() == lower_query:
                            return item['id']

                    # 2️⃣ Top result fallback
                    return results[0]['id']

            # 3️⃣ If no result but a game is running → Games + Demos
            if is_game_running:
                # Games + Demos category ID (verified from Twitch)
                return "66082"

            # 4️⃣ No game → Just Chatting
            return "509658"

        except Exception:
            # Network or token error → fallback depending on context
            return "66082" if is_game_running else "509658"





    def change_category(self, game_name: str) -> bool:
        if not self.config.get('enabled'):
            return False
        if not self.ensure_token_valid():
            return False

        if not self.user_id and not self.get_user_id():
            return False
        try:
            import requests
            if game_name.lower() == "just chatting":
                game_id = "509658"
            else:
                game_id = self.smart_search_game(game_name, is_game_running=bool(game_name))
                if not game_id:
                    game_id = "66082" if game_name else "509658"
            headers = {'Authorization': f'Bearer {self.access_token}', 'Client-Id': self.CLIENT_ID, 'Content-Type': 'application/json'}
            data = {'game_id': game_id}
            resp = requests.patch(f'https://api.twitch.tv/helix/channels?broadcaster_id={self.user_id}', headers=headers, json=data, timeout=8)
            return resp.status_code == 204
        except Exception:
            return False

# ---------- Scanner ----------
class GameScanner:
    def __init__(self):
        self.excluded = self.load_excluded()

    def load_excluded(self) -> Set[str]:
        try:
            if EXCLUDED_GAMES_FILE.exists():
                with open(EXCLUDED_GAMES_FILE, 'r') as f:
                    return set(json.load(f).get('excluded', []))
        except Exception:
            pass
        return set()

    def save_excluded(self):
        try:
            with open(EXCLUDED_GAMES_FILE, 'w') as f:
                json.dump({'excluded': list(self.excluded)}, f, indent=2)
        except Exception:
            pass

    def exclude(self, name: str):
        self.excluded.add(name)
        self.save_excluded()

    def unexclude(self, name: str):
        if name in self.excluded:
            self.excluded.remove(name)
            self.save_excluded()
            return True
        return False

    def get_excluded_list(self) -> List[str]:
        return sorted(list(self.excluded))

    def is_excluded(self, name: str) -> bool:
        return name in self.excluded

    def get_drives(self) -> List[str]:
        import string
        return [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]

    # (scanning methods kept unchanged - long function bodies omitted here for brevity)
    # We'll keep your original implementations for scan_steam(), scan_epic(), scan_gog(), scan_ea(), scan_riot(), scan_battlenet(), scan_xbox(), scan_all()
    # For brevity in this view I won't repeat them, but keep them identical to your uploaded file.

    def scan_steam(self) -> List[Game]:
        # same body as your original implementation
        games = []
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
            steam_path = Path(winreg.QueryValueEx(key, "SteamPath")[0])
            winreg.CloseKey(key)

            library_file = steam_path / "steamapps" / "libraryfolders.vdf"
            if library_file.exists():
                with open(library_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if '"path"' in line:
                            path = line.split('"')[3].replace('\\\\', '\\')
                            steamapps = Path(path) / "steamapps"
                            if steamapps.exists():
                                for acf in steamapps.glob("appmanifest_*.acf"):
                                    try:
                                        with open(acf, 'r', encoding='utf-8') as af:
                                            content = af.read()
                                            name = installdir = None
                                            for l in content.split('\n'):
                                                if '"name"' in l:
                                                    name = l.split('"')[3]
                                                if '"installdir"' in l:
                                                    installdir = l.split('"')[3]
                                            if name and installdir and not self.is_excluded(name):
                                                gpath = steamapps / "common" / installdir
                                                if gpath.exists():
                                                    exe_found = None
                                                    common_exes = [
                                                        gpath / f"{installdir}.exe",
                                                        gpath / f"{name}.exe",
                                                        gpath / "bin" / f"{installdir}.exe",
                                                        gpath / "Binaries" / "Win64" / f"{installdir}.exe",
                                                        gpath / "Binaries" / "Win64" / f"{name}.exe",
                                                        gpath / f"{installdir}-Win64-Shipping.exe",
                                                        gpath / "Game" / f"{installdir}.exe",
                                                        gpath / "Client" / f"{installdir}.exe",
                                                    ]
                                                    for exe_path in common_exes:
                                                        if exe_path.exists():
                                                            exe_found = exe_path
                                                            break
                                                    if not exe_found:
                                                        try:
                                                            # Skip obvious non-game executables
                                                            skip_patterns = ['unins', 'install', 'setup', 'crash', 'report', 'redist', 'dotnet', 'directx', 'vcredist', 'unity', 'unreal']
                                                            
                                                            exes_root = [e for e in gpath.glob("*.exe") 
                                                                        if not any(skip in e.stem.lower() for skip in skip_patterns)]
                                                            if exes_root:
                                                                # Prefer executables with "game" or the install dir name
                                                                game_exes = [e for e in exes_root if 'game' in e.stem.lower() or installdir.lower() in e.stem.lower()]
                                                                exe_found = game_exes[0] if game_exes else exes_root[0]
                                                            else:
                                                                # Look in subdirectories
                                                                for root, dirs, files in os.walk(gpath):
                                                                    depth = root[len(str(gpath)):].count(os.sep)
                                                                    if depth > 3:
                                                                        dirs.clear()
                                                                        continue
                                                                    exe_files = [f for f in files if f.endswith('.exe') 
                                                                                and not any(skip in f.lower() for skip in skip_patterns)]
                                                                    if exe_files:
                                                                        # Prefer main game executables
                                                                        game_exes = [f for f in exe_files if 'game' in f.lower() or installdir.lower() in f.lower()]
                                                                        exe_found = Path(root) / (game_exes[0] if game_exes else exe_files[0])
                                                                        break
                                                        except Exception:
                                                            pass
                                                    # Extract icon
                                                    icon = IconExtractor.extract_icon(str(exe_found), name) if exe_found else ""
                                                    games.append(Game(name, str(gpath), "Steam", str(exe_found) if exe_found else "", icon)) # type: ignore
                                    except Exception:
                                        continue
        except Exception:
            pass
        return games

    def scan_epic(self) -> List[Game]:
        games = []
        manifests = Path(os.environ.get('PROGRAMDATA', 'C:\\ProgramData')) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
        if manifests.exists():
            for manifest in manifests.glob("*.item"):
                try:
                    with open(manifest, 'r') as f:
                        data = json.load(f)
                        name = data.get('DisplayName')
                        location = data.get('InstallLocation')
                        if name and location and Path(location).exists() and not self.is_excluded(name):
                            # Find exe
                            gpath = Path(location)
                            exe_found = None
                            for exe in gpath.glob("*.exe"):
                                if not any(skip in exe.stem.lower() for skip in ['unins', 'install', 'setup', 'crash']):
                                    exe_found = exe
                                    break
                            # Extract icon
                            icon = IconExtractor.extract_icon(str(exe_found), name) if exe_found else ""
                            games.append(Game(name, location, "Epic Games", str(exe_found) if exe_found else "", icon)) # type: ignore
                except Exception:
                    continue
        return games

    def scan_gog(self) -> List[Game]:
        games = []
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\GOG.com\Games")
            i = 0
            while True:
                try:
                    subkey = winreg.OpenKey(key, winreg.EnumKey(key, i))
                    name = winreg.QueryValueEx(subkey, "gameName")[0]
                    path = winreg.QueryValueEx(subkey, "path")[0]
                    exe = winreg.QueryValueEx(subkey, "exe")[0]
                    winreg.CloseKey(subkey)
                    if Path(path).exists() and not self.is_excluded(name):
                        exe_path = str(Path(path) / exe)
                        icon = IconExtractor.extract_icon(exe_path, name) if Path(exe_path).exists() else ""
                        games.append(Game(name, path, "GOG", exe_path, icon)) # type: ignore # type: ignore
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except Exception:
            pass
        return games

    def scan_ea(self) -> List[Game]:
        games = []
        ea_path = Path(os.environ.get('PROGRAMDATA', 'C:\\ProgramData')) / "Origin" / "LocalContent"
        if ea_path.exists():
            for folder in ea_path.iterdir():
                if folder.is_dir():
                    for mfst in folder.glob("*.mfst"):
                        try:
                            with open(mfst, 'r') as f:
                                if 'dipinstallpath' in f.read().lower():
                                    name = folder.name
                                    if not self.is_excluded(name):
                                        # Find exe and extract icon
                                        exe_found = None
                                        for exe in folder.glob("*.exe"):
                                            if not any(skip in exe.stem.lower() for skip in ['unins', 'install', 'setup']):
                                                exe_found = exe
                                                break
                                        icon = IconExtractor.extract_icon(str(exe_found), name) if exe_found else ""
                                        games.append(Game(name, str(folder), "EA/Origin", str(exe_found) if exe_found else "", icon)) # type: ignore
                                    break
                        except Exception:
                            continue
        return games

    def scan_riot(self) -> List[Game]:
        games = []
        for drive in self.get_drives():
            paths = [
                Path(drive) / "Riot Games",
                Path(drive) / "Program Files" / "Riot Games",
                Path(drive) / "ProgramData" / "Riot Games"
            ]
            for riot_path in paths:
                if riot_path.exists():
                    for folder in riot_path.iterdir():
                        if folder.is_dir() and folder.name.lower() not in ['riot client', 'metadata']:
                            exes = list(folder.rglob("*.exe"))
                            if exes and not self.is_excluded(folder.name):
                                if not any(g.name == folder.name for g in games):
                                    # Find exe and extract icon
                                    exe_found = None
                                    for exe in folder.glob("*.exe"):
                                        if not any(skip in exe.stem.lower() for skip in ['unins', 'install', 'setup']):
                                            exe_found = exe
                                            break
                                    icon = IconExtractor.extract_icon(str(exe_found), folder.name) if exe_found else ""
                                    games.append(Game(folder.name, str(folder), "Riot Games", str(exe_found) if exe_found else "", icon)) # type: ignore
        return games

    def scan_battlenet(self) -> List[Game]:
        games = []
        blizz_games = [
            {"name": "Overwatch", "folders": ["Overwatch", "Overwatch 2"], "exe": "Overwatch.exe"},
            {"name": "World of Warcraft", "folders": ["World of Warcraft"], "exe": "Wow.exe"},
            {"name": "Diablo III", "folders": ["Diablo III"], "exe": "Diablo III64.exe"},
            {"name": "Diablo IV", "folders": ["Diablo IV"], "exe": "Diablo IV.exe"},
            {"name": "Hearthstone", "folders": ["Hearthstone"], "exe": "Hearthstone.exe"},
            {"name": "StarCraft II", "folders": ["StarCraft II"], "exe": "SC2_x64.exe"},
            {"name": "Warcraft III", "folders": ["Warcraft III"], "exe": "Warcraft III.exe"},
            {"name": "Heroes of the Storm", "folders": ["Heroes of the Storm"], "exe": "HeroesOfTheStorm_x64.exe"}
        ]
        for drive in self.get_drives():
            drive_path = Path(drive)
            try:
                for item in drive_path.iterdir():
                    if not item.is_dir():
                        continue
                    for game_info in blizz_games:
                        for folder_variant in game_info["folders"]:
                            if item.name.lower() == folder_variant.lower():
                                exe_found = None
                                direct_exe = item / game_info["exe"]
                                if direct_exe.exists() and direct_exe.is_file():
                                    exe_found = direct_exe
                                else:
                                    try:
                                        for root, dirs, files in os.walk(item):
                                            depth = root[len(str(item)):].count(os.sep)
                                            if depth > 3:
                                                dirs.clear()
                                                continue
                                            if game_info["exe"] in files:
                                                exe_found = Path(root) / game_info["exe"]
                                                break
                                    except Exception:
                                        pass
                                if exe_found and not self.is_excluded(game_info["name"]):
                                    if not any(g.name == game_info["name"] for g in games):
                                        icon = IconExtractor.extract_icon(str(exe_found), game_info["name"]) if exe_found else ""
                                        games.append(Game(game_info["name"], str(item), "Battle.net", str(exe_found), icon)) # type: ignore
                                        break
            except Exception:
                pass
        return games

    def scan_xbox(self) -> List[Game]:
        games = []
        for drive in self.get_drives():
            search_paths = [
                Path(drive) / "xbox",
                Path(drive) / "Xbox",
                Path(drive) / "Games" / "xbox",
                Path(drive) / "Games" / "Xbox"
            ]
            for xbox_folder in search_paths:
                if not xbox_folder.exists():
                    continue
                for game_folder in xbox_folder.iterdir():
                    if not game_folder.is_dir():
                        continue
                    game_name = game_folder.name
                    content_folder = game_folder / "Content"
                    if not content_folder.exists():
                        content_folder = game_folder / "content"
                    if content_folder.exists():
                        exes = list(content_folder.glob("*.exe"))
                        if exes and not self.is_excluded(game_name):
                            if not any(g.name == game_name for g in games):
                                icon = IconExtractor.extract_icon(str(exes[0]), game_name)
                                games.append(Game(game_name, str(content_folder), "Xbox", str(exes[0]), icon)) # type: ignore
        return games

    def scan_all(self) -> List[Game]:
        all_games = []
        all_games.extend(self.scan_steam())
        all_games.extend(self.scan_epic())
        all_games.extend(self.scan_gog())
        all_games.extend(self.scan_ea())
        all_games.extend(self.scan_riot())
        all_games.extend(self.scan_battlenet())
        all_games.extend(self.scan_xbox())
        return all_games

# ---------- Monitor ----------
class GameMonitor:
    def __init__(self, games: List[Game], twitch: TwitchBot, status_callback):
        self.games = games
        self.twitch = twitch
        self.status_callback = status_callback
        self.active = False
        self.tracked_pids = {}
        self.exe_map = {}
        self.close_timers = {}

    def build_exe_map(self):
        self.exe_map.clear()
        for game in self.games:
            if game.exe_path and os.path.exists(game.exe_path):
                norm_path = os.path.normpath(game.exe_path).lower()
                self.exe_map[norm_path] = game.name
                
                # Also add the parent directory's other executables for games with multiple EXEs
                try:
                    exe_dir = Path(game.exe_path).parent
                    for exe in exe_dir.glob("*.exe"):
                        exe_norm = os.path.normpath(str(exe)).lower()
                        if exe_norm not in self.exe_map:
                            # Only add if it's a reasonable game executable (not an installer/uninstaller)
                            exe_name = exe.stem.lower()
                            if not any(skip in exe_name for skip in ['unins', 'install', 'setup', 'launcher', 'crash', 'report']):
                                self.exe_map[exe_norm] = game.name
                except Exception:
                    pass
                
                if game.platform == "Xbox":
                    try:
                        content_path = Path(game.path)
                        for exe in content_path.glob("*.exe"):
                            exe_norm = os.path.normpath(str(exe)).lower()
                            if exe_norm not in self.exe_map:
                                self.exe_map[exe_norm] = game.name
                    except Exception:
                        pass

    def start(self):
        self.active = True
        self.build_exe_map()
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def stop(self):
        self.active = False
        self.tracked_pids.clear()
        self.close_timers.clear()

    def _monitor_loop(self):
        try:
            import psutil
        except Exception:
            return

        while self.active:
            try:
                current_pids = set()
                active_games = set()
                for proc in psutil.process_iter(['pid', 'exe']):
                    try:
                        pid = proc.info.get('pid')
                        exe = proc.info.get('exe')
                        if not exe:
                            continue
                        current_pids.add(pid)
                        try:
                            norm_exe = os.path.normpath(exe).lower()
                        except Exception:
                            continue
                        if norm_exe in self.exe_map:
                            game_name = self.exe_map[norm_exe]
                            active_games.add(game_name)
                            if game_name in self.close_timers:
                                del self.close_timers[game_name]
                            if pid not in self.tracked_pids:
                                self.tracked_pids[pid] = game_name
                                if list(self.tracked_pids.values()).count(game_name) == 1:
                                    if self.twitch.config.get('enabled'):
                                        threading.Thread(target=lambda gn=game_name: self.twitch.change_category(gn), daemon=True).start()
                                    self.status_callback(f"🎮 {game_name} detected!", "#34d399")
                    except Exception:
                        pass

                closed_pids = set(self.tracked_pids.keys()) - current_pids
                for pid in closed_pids:
                    game_name = self.tracked_pids.pop(pid, None)
                    if game_name:
                        if game_name not in active_games:
                            if game_name not in self.close_timers:
                                self.close_timers[game_name] = time.time()

                current_time = time.time()
                games_to_close = []
                for game_name, start_time in list(self.close_timers.items()):
                    elapsed = current_time - start_time
                    if elapsed >= 30:
                        games_to_close.append(game_name)

                for game_name in games_to_close:
                    del self.close_timers[game_name]
                    if self.twitch.config.get('enabled'):
                        threading.Thread(target=lambda: self.twitch.change_category("Just Chatting"), daemon=True).start()
                    self.status_callback(f"🔴 {game_name} closed", "#fbbf24")

                time.sleep(3.5)
            except Exception:
                time.sleep(3.5)

# ---------- GUI ----------
class GUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Twitch Game Changer")

        # Tray and icon state
        self.tray_icon = None
        self.is_minimized_to_tray = False

        # Icon set up (window icon)
        try:
            icon_path = Path('icon.ico')
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
            else:
                icon_path = Path(os.path.dirname(os.path.abspath(__file__))) / 'icon.ico'
                if icon_path.exists():
                    self.root.iconbitmap(str(icon_path))
        except Exception:
            pass

        # Window geometry
        w, h = 1200, 800
        x = (root.winfo_screenwidth() - w) // 2
        y = (root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.minsize(1000, 700)
        self.root.configure(bg="#0a0e27")

        # Close behavior
        if TRAY_AVAILABLE:
            self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)  # always minimize-to-tray when available
        else:
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Core components
        self.scanner = GameScanner()
        self.twitch = TwitchBot()
        self.monitor = None
        self.games = []
        self.filtered = []

        self.setup_ui()
        self.root.after(1400, self.load_cache)

    def setup_ui(self):
        # UI kept identical to your original implementation (unchanged)
        header = tk.Frame(self.root, bg="#0f1629", height=120)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)
        header_content = tk.Frame(header, bg="#0f1629")
        header_content.pack(expand=True)
        title_frame = tk.Frame(header_content, bg="#0f1629")
        title_frame.pack()
        tk.Label(title_frame, text="🎮", font=("Segoe UI", 48), bg="#0f1629", fg="#60a5fa").pack(side="left", padx=(0, 15))
        title_text = tk.Frame(title_frame, bg="#0f1629")
        title_text.pack(side="left")
        tk.Label(title_text, text="Twitch Game Changer", font=("Segoe UI", 32, "bold"), bg="#0f1629", fg="#ffffff").pack(anchor="w")
        tk.Label(title_text, text="Automatically change your Twitch category when you play", font=("Segoe UI", 11), bg="#0f1629", fg="#6b7280").pack(anchor="w")

        ctrl = tk.Frame(self.root, bg="#0a0e27")
        ctrl.pack(fill="x", padx=30, pady=20)
        btn_container = tk.Frame(ctrl, bg="#0a0e27")
        btn_container.pack(side="left")
        btn_style = {"font": ("Segoe UI", 10, "bold"), "relief": "flat", "cursor": "hand2", "borderwidth": 0, "padx": 20, "pady": 10}
        tk.Button(btn_container, text="🔍 Scan", command=self.scan, bg="#3b82f6", fg="#ffffff", activebackground="#2563eb", **btn_style).pack(side="left", padx=5)
        tk.Button(btn_container, text="📡 Twitch", command=self.twitch_settings, bg="#9146ff", fg="#ffffff", activebackground="#7c3aed", **btn_style).pack(side="left", padx=5)
        tk.Button(btn_container, text="🗑️ Excluded", command=self.show_excluded_games, bg="#1f2937", fg="#ffffff", activebackground="#111827", **btn_style).pack(side="left", padx=5)
        self.monitor_btn = tk.Button(btn_container, text="⚪ Monitor", command=self.toggle_monitor, bg="#10b981", fg="#ffffff", activebackground="#059669", **btn_style)
        self.monitor_btn.pack(side="left", padx=5)

        search_container = tk.Frame(ctrl, bg="#0a0e27")
        search_container.pack(side="right")
        search_box = tk.Frame(search_container, bg="#1a1f3a", highlightthickness=1, highlightbackground="#2a2f4a", highlightcolor="#3b82f6")
        search_box.pack(side="left", padx=(0, 10))
        tk.Label(search_box, text="🔎", font=("Segoe UI", 12), bg="#1a1f3a", fg="#6b7280").pack(side="left", padx=(10, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *args: self.filter())
        search_entry = tk.Entry(search_box, textvariable=self.search_var, font=("Segoe UI", 11), bg="#1a1f3a", fg="#ffffff", relief="flat", width=30, borderwidth=0, insertbackground="#60a5fa")
        search_entry.pack(side="left", padx=(0, 10), pady=8)

        filter_frame = tk.Frame(search_container, bg="#1a1f3a", highlightthickness=1, highlightbackground="#2a2f4a")
        filter_frame.pack(side="left")
        self.platform_var = tk.StringVar(value="All Platforms")
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Modern.TCombobox', fieldbackground='#1a1f3a', background='#1a1f3a', foreground='#ffffff', borderwidth=0, arrowcolor='#6b7280')
        style.map('Modern.TCombobox', fieldbackground=[('readonly', '#1a1f3a')], selectbackground=[('readonly', '#1a1f3a')], selectforeground=[('readonly', '#ffffff')])
        platform_combo = ttk.Combobox(filter_frame, textvariable=self.platform_var, values=["All Platforms", "Steam", "Epic Games", "GOG", "EA/Origin", "Riot Games", "Battle.net", "Xbox"], state="readonly", font=("Segoe UI", 10), width=16, style='Modern.TCombobox')
        platform_combo.pack(padx=10, pady=7)
        self.platform_var.trace("w", lambda *args: self.filter())

        self.status = tk.Label(self.root, text="Ready to scan", font=("Segoe UI", 10), bg="#0a0e27", fg="#6b7280", anchor="w", padx=30, pady=8)
        self.status.pack(fill="x")

        container = tk.Frame(self.root, bg="#0a0e27")
        container.pack(fill="both", expand=True, padx=30, pady=(0, 20))
        scrollbar_frame = tk.Frame(container, bg="#0a0e27", width=12)
        scrollbar_frame.pack(side="right", fill="y", padx=(10, 0))
        scrollbar = tk.Canvas(scrollbar_frame, bg="#1a1f3a", width=8, highlightthickness=0)
        scrollbar.pack(fill="y", expand=True)
        self.canvas = tk.Canvas(container, bg="#0a0e27", highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        def on_configure(event):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.games_frame = tk.Frame(self.canvas, bg="#0a0e27")
        self.canvas_window = self.canvas.create_window((0, 0), window=self.games_frame, anchor="nw")
        self.games_frame.bind("<Configure>", on_configure)
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)

    # ---------- scanning / UI helpers ----------
    def scan(self):
        self.status.config(text="🔄 Scanning all drives for games...", fg="#60a5fa")
        self.root.update()
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self):
        self.games = self.scanner.scan_all()
        self.save_cache()
        gc.collect()
        self.root.after(0, self._finish_scan)

    def _finish_scan(self):
        self.filtered = self.games.copy()
        self.status.config(text=f"✅ Found {len(self.games)} games across all platforms", fg="#10b981")
        self.display()

    def filter(self):
        search = self.search_var.get().lower()
        platform = self.platform_var.get()
        self.filtered = [g for g in self.games if search in g.name.lower() and (platform == "All Platforms" or g.platform == platform)]
        self.display()

    def display(self):
        for w in self.games_frame.winfo_children():
            w.destroy()
        if not hasattr(self, 'game_images'):
            self.game_images = {}
        self.game_images.clear()
        gc.collect()
        
        if not self.filtered:
            empty_frame = tk.Frame(self.games_frame, bg="#0a0e27")
            empty_frame.pack(expand=True, fill="both", pady=100)
            tk.Label(empty_frame, text="📂", font=("Segoe UI", 64), bg="#0a0e27", fg="#374151").pack()
            tk.Label(empty_frame, text="No games found", font=("Segoe UI", 16, "bold"), bg="#0a0e27", fg="#6b7280").pack(pady=(10, 5))
            tk.Label(empty_frame, text="Click 'Scan' to discover your games", font=("Segoe UI", 11), bg="#0a0e27", fg="#4b5563").pack()
            return
        colors = {"Steam": "#1b2838", "Epic Games": "#000000", "GOG": "#86328a", "EA/Origin": "#f56300", "Riot Games": "#d13639", "Xbox": "#107c10", "Battle.net": "#148eff"}
        for game in self.filtered:
            card = tk.Frame(self.games_frame, bg="#0a0e27")
            card.pack(fill="x", pady=6)
            card_frame = tk.Frame(card, bg="#151b2e", highlightthickness=1, highlightbackground="#1f2937")
            card_frame.pack(fill="x")
            accent = tk.Frame(card_frame, bg=colors.get(game.platform, "#4b5563"), width=5)
            accent.pack(side="left", fill="y")
            
            # Add icon if available
            if game.icon and os.path.exists(game.icon):
                try:
                    from PIL import Image, ImageTk
                    img = Image.open(game.icon).resize((40, 40), Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS) # type: ignore
                    photo = ImageTk.PhotoImage(img)
                    self.game_images[game.name] = photo
                    icon_label = tk.Label(card_frame, image=photo, bg="#151b2e")
                    icon_label.pack(side="left", padx=12, pady=12)
                except:
                    pass
            
            content = tk.Frame(card_frame, bg="#151b2e")
            content.pack(side="left", fill="both", expand=True, padx=20, pady=16)
            tk.Label(content, text=game.name, font=("Segoe UI", 13, "bold"), bg="#151b2e", fg="#f3f4f6", anchor="w").pack(anchor="w")
            details = tk.Frame(content, bg="#151b2e")
            details.pack(anchor="w", pady=(6, 0))
            badge = tk.Label(details, text=game.platform, font=("Segoe UI", 8, "bold"), bg=colors.get(game.platform, "#4b5563"), fg="#ffffff", padx=10, pady=3)
            badge.pack(side="left", padx=(0, 12))
            path_text = game.path if len(game.path) <= 70 else game.path[:67] + "..."
            tk.Label(details, text=f"📁 {path_text}", font=("Segoe UI", 9), bg="#151b2e", fg="#6b7280").pack(side="left")
            remove_btn = tk.Button(card_frame, text="✕", command=lambda g=game: self.remove(g), font=("Segoe UI", 12, "bold"), bg="#ef4444", fg="#ffffff", activebackground="#dc2626", relief="flat", padx=16, pady=8, cursor="hand2", borderwidth=0)
            remove_btn.pack(side="right", padx=16, pady=12)

    def remove(self, game):
        if messagebox.askyesno("Remove Game", f"Remove '{game.name}' from library?"):
            self.scanner.exclude(game.name)
            self.games = [g for g in self.games if g.name != game.name]
            self.filtered = [g for g in self.filtered if g.name != game.name]
            self.save_cache()
            self.display()
            self.status.config(text=f"❌ Removed {game.name}", fg="#f59e0b")

    def toggle_monitor(self):
        if self.monitor and self.monitor.active:
            self.monitor.stop()
            self.monitor = None
            self.monitor_btn.config(text="⚪ Monitor", bg="#10b981")
            self.status.config(text="Monitor stopped", fg="#6b7280")
        else:
            if not self.games:
                messagebox.showwarning("No Games", "Please scan for games first!")
                return
            self.monitor = GameMonitor(self.games, self.twitch, self.update_status)
            self.monitor.start()
            self.monitor_btn.config(text="🟢 Active", bg="#ef4444")
            self.status.config(text="🔴 Monitoring active - detecting game launches", fg="#10b981")

    def update_status(self, text, color):
        self.root.after(0, lambda: self.status.config(text=text, fg=color))

    # ---------- Twitch settings UI ----------
    def twitch_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Twitch Settings")
        dialog.geometry("550x400")
        dialog.configure(bg="#0f1629")
        dialog.transient(self.root)
        dialog.grab_set()
        tk.Label(dialog, text="📡 Twitch Integration", font=("Segoe UI", 18, "bold"), bg="#0f1629", fg="#60a5fa").pack(pady=20)
        tk.Label(dialog, text="Automatically changes your stream category when you launch games", font=("Segoe UI", 10), bg="#0f1629", fg="#9ca3af", justify="center", wraplength=450).pack(pady=10)
        form = tk.Frame(dialog, bg="#0f1629")
        form.pack(pady=20, padx=40)
        tk.Label(form, text="Channel Name:", bg="#0f1629", fg="#ffffff", font=("Segoe UI", 11)).grid(row=0, column=0, sticky="w", pady=15)
        channel_entry = tk.Entry(form, font=("Segoe UI", 11), bg="#1a1f3a", fg="#ffffff", width=30, borderwidth=0, relief="flat")
        channel_entry.grid(row=0, column=1, pady=15, ipady=8, padx=10)
        channel_entry.insert(0, self.twitch.config.get('channel_name', ''))
        enabled_var = tk.BooleanVar(value=self.twitch.config.get('enabled', False))
        tk.Checkbutton(form, text="Enable automatic category changes", variable=enabled_var, font=("Segoe UI", 10), bg="#0f1629", fg="#ffffff", selectcolor="#1a1f3a", activebackground="#0f1629", activeforeground="#ffffff").grid(row=1, column=0, columnspan=2, pady=15)
        btn_frame = tk.Frame(dialog, bg="#0f1629")
        btn_frame.pack(pady=20)

        def authenticate():
            channel = channel_entry.get().strip()
            if not channel:
                messagebox.showwarning("Missing Info", "Enter your Twitch channel name!")
                return
            self.twitch.update_config(channel, True)
            auth_btn.config(text="Authenticating...", state="disabled")
            dialog.update()
            def do_auth():
                ok = self.twitch.authenticate() and self.twitch.get_user_id()
                self.root.after(0, lambda: auth_btn.config(text="🔐 Authenticate", state="normal"))
                if ok:
                    dialog.destroy()
                else:
                    self.root.after(0, lambda: messagebox.showerror("Failed", "❌ Authentication failed!\n\nPlease try again."))

            threading.Thread(target=do_auth, daemon=True).start()

        auth_btn = tk.Button(btn_frame, text="🔐 Authenticate", command=authenticate, font=("Segoe UI", 11, "bold"), bg="#9146ff", fg="#ffffff", relief="flat", padx=25, pady=10, cursor="hand2", borderwidth=0)
        auth_btn.pack(side="left", padx=5)

        def save():
            self.twitch.update_config(channel_entry.get().strip(), enabled_var.get())
            dialog.destroy()

        tk.Button(btn_frame, text="💾 Save", command=save, font=("Segoe UI", 11, "bold"), bg="#3b82f6", fg="#ffffff", relief="flat", padx=30, pady=10, cursor="hand2", borderwidth=0).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Cancel", command=dialog.destroy, font=("Segoe UI", 11), bg="#374151", fg="#ffffff", relief="flat", padx=30, pady=10, cursor="hand2", borderwidth=0).pack(side="left", padx=5)
        tk.Label(dialog, text="💡 Click 'Authenticate' to login with Twitch (opens browser)", font=("Segoe UI", 9), bg="#0f1629", fg="#6b7280").pack(pady=(0, 10))

    def show_excluded_games(self):
        excluded_list = self.scanner.get_excluded_list()
        dialog = tk.Toplevel(self.root)
        dialog.title("Excluded Games")
        dialog.geometry("600x500")
        dialog.configure(bg="#0f1629")
        dialog.transient(self.root)
        dialog.grab_set()
        tk.Label(dialog, text="🗑️ Excluded Games", font=("Segoe UI", 18, "bold"), bg="#0f1629", fg="#ef4444").pack(pady=20)
        if not excluded_list:
            tk.Label(dialog, text="No excluded games", font=("Segoe UI", 12), bg="#0f1629", fg="#6b7280").pack(pady=50)
            tk.Button(dialog, text="Close", command=dialog.destroy, font=("Segoe UI", 11, "bold"), bg="#374151", fg="#ffffff", relief="flat", padx=30, pady=10, cursor="hand2", borderwidth=0).pack(pady=20)
            return
        tk.Label(dialog, text=f"These games were removed from your library ({len(excluded_list)} total)", font=("Segoe UI", 10), bg="#0f1629", fg="#9ca3af", wraplength=500).pack(pady=(0, 15))
        list_container = tk.Frame(dialog, bg="#0f1629")
        list_container.pack(fill="both", expand=True, padx=30, pady=(0, 20))
        canvas = tk.Canvas(list_container, bg="#1a1f3a", highlightthickness=0)
        scrollbar = tk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#1a1f3a")
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        for game_name in excluded_list:
            item_frame = tk.Frame(scrollable_frame, bg="#151b2e", highlightthickness=1, highlightbackground="#2a2f4a")
            item_frame.pack(fill="x", padx=10, pady=5)
            tk.Label(item_frame, text=game_name, font=("Segoe UI", 11), bg="#151b2e", fg="#f3f4f6", anchor="w").pack(side="left", padx=15, pady=12)
            def restore_game(name=game_name):
                if messagebox.askyesno("Restore Game", f"Restore '{name}' to your library?\n\nYou'll need to rescan to see it."):
                    if self.scanner.unexclude(name):
                        self.status.config(text=f"✅ Restored {name} - please rescan", fg="#10b981")
                        dialog.destroy()
                        self.show_excluded_games()
            tk.Button(item_frame, text="↩️ Restore", command=restore_game, font=("Segoe UI", 9, "bold"), bg="#10b981", fg="#ffffff", activebackground="#059669", relief="flat", padx=15, pady=6, cursor="hand2", borderwidth=0).pack(side="right", padx=10)
        tk.Button(dialog, text="Close", command=dialog.destroy, font=("Segoe UI", 11, "bold"), bg="#374151", fg="#ffffff", relief="flat", padx=30, pady=10, cursor="hand2", borderwidth=0).pack(pady=(0, 20))

    def save_cache(self):
        try:
            data = [{'name': g.name, 'path': g.path, 'platform': g.platform, 'exe_path': g.exe_path, 'icon': g.icon} for g in self.games]
            with open(GAMES_CACHE_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def load_cache(self):
        try:
            if GAMES_CACHE_FILE.exists():
                with open(GAMES_CACHE_FILE, 'r') as f:
                    data = json.load(f)
                    self.games = [Game(g['name'], g['path'], g['platform'], g.get('exe_path', ''), g.get('icon', '')) for g in data]
                    self.filtered = self.games.copy()
                    if self.games:
                        self.display()
                        self.status.config(text=f"✅ Loaded {len(self.games)} games from cache", fg="#10b981")
        except Exception:
            pass

    # ---------- tray / icon ----------
    def create_tray_icon_image(self):
        """Always use the real icon.ico for the tray icon."""
        try:
            from PIL import Image
            icon_path = Path("icon.ico")
            if not icon_path.exists():
                icon_path = Path(os.path.dirname(os.path.abspath(__file__))) / "icon.ico"
            if icon_path.exists():
                image = Image.open(icon_path).convert("RGBA")
                image = image.resize((32, 32), Image.LANCZOS)  # type: ignore
                return image
            else:
                return None
        except Exception:
            return None

    def minimize_to_tray(self):
        # Called when window is closed or minimized (WM_DELETE_WINDOW)
        if not TRAY_AVAILABLE or pystray is None:
            self.root.iconify()
            return

        if self.is_minimized_to_tray:
            return

        # Hide window
        self.root.withdraw()
        self.is_minimized_to_tray = True

        # Create tray icon if not exists or not visible
        if not self.tray_icon:
            image = self.create_tray_icon_image()
            if item is None or pystray is None:
                return

            menu = pystray.Menu(
                item('Show', self.show_window, default=True),
                item('Monitor Status', self.show_monitor_status),
                pystray.Menu.SEPARATOR,
                item('Exit', self.quit_app)
            )

            # Create Icon object and run it inside a resilient thread
            try:
                self.tray_icon = pystray.Icon("twitch_game_changer", image, "Twitch Game Changer", menu)
            except Exception:
                self.tray_icon = pystray.Icon("twitch_game_changer", None, "Twitch Game Changer", menu)

            def start_tray_loop():
                # keep trying to run the tray icon; if run() exits due to Explorer restart, recreate & rerun
                while self.is_minimized_to_tray:
                    try:
                        # run will block until stop(); if system explorer restarts it may raise/exit
                        self.tray_icon.run() # type: ignore
                        # if run returns normally (stop called), break
                        break
                    except Exception:
                        # short pause and recreate the icon object if still minimized
                        time.sleep(1.0)
                        if not self.is_minimized_to_tray:
                            break
                        try:
                            image2 = self.create_tray_icon_image()
                            self.tray_icon = pystray.Icon("twitch_game_changer", image2, "Twitch Game Changer", menu) # type: ignore
                        except Exception:
                            # if recreation fails, sleep and retry
                            time.sleep(1.0)
                            continue

            threading.Thread(target=start_tray_loop, daemon=True).start()

    def show_window(self, icon=None, item=None):
        # Restore window, stop tray icon
        self.is_minimized_to_tray = False
        try:
            if self.tray_icon:
                try:
                    self.tray_icon.stop()
                except Exception:
                    pass
                # clear reference so new icon can be created later
                self.tray_icon = None
        except Exception:
            pass
        self.root.after(0, self.root.deiconify)
        self.root.after(0, self.root.lift)
        self.root.after(0, self.root.focus_force)

    def show_monitor_status(self, icon=None, item=None):
        if self.monitor and self.monitor.active:
            status = "🟢 Monitor is ACTIVE\nDetecting game launches..."
        else:
            status = "⚪ Monitor is INACTIVE\nGames are not being tracked"
        def show_msg():
            messagebox.showinfo("Monitor Status", status)
        self.root.after(0, show_msg)

    def quit_app(self, icon=None, item=None):
        # Clean exit
        try:
            if self.monitor and self.monitor.active:
                self.monitor.stop()
        except Exception:
            pass
        try:
            if self.tray_icon:
                try:
                    self.tray_icon.stop()
                except Exception:
                    pass
                self.tray_icon = None
        except Exception:
            pass
        self.root.after(0, self.root.destroy)

    def on_closing(self):
        if self.monitor and self.monitor.active:
            if messagebox.askyesno("Monitor Active", "Game monitor is active. Exit anyway?\n\nThis will stop tracking your games."):
                self.monitor.stop()
                self.root.destroy()
        else:
            self.root.destroy()

# ---------- entrypoint ----------
def main():
    root = tk.Tk()
    app = GUI(root)

    # minimize on startup only if flagged
    if STARTUP_MODE and hasattr(app, "minimize_to_tray"):
        root.after(800, app.minimize_to_tray)

    root.mainloop()

if __name__ == "__main__":
    main()
