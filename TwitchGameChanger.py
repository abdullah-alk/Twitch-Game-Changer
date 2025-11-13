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

# App version and update settings
APP_VERSION = "2.0.0"  # Update this when releasing new versions
GITHUB_REPO = "abdullah-alk/Twitch-Game-Changer"  # Change to your actual GitHub repo
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
UPDATE_CHECK_FILE = None  # Will be set after APP_DATA_DIR is created

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
UPDATE_CHECK_FILE = APP_DATA_DIR / 'last_update_check.json'

# Token Encryption
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

# ---------- Auto Updater ----------
class AutoUpdater:
    """Handles automatic updates from GitHub releases"""
    
    def __init__(self, current_version: str, repo: str, api_url: str):
        self.current_version = current_version
        self.repo = repo
        self.api_url = api_url
        self.last_check_file = UPDATE_CHECK_FILE
    
    @staticmethod
    def parse_version(version_str: str) -> tuple:
        """Parse version string like '1.0.0' or 'v1.0.0' into tuple (1, 0, 0)"""
        try:
            # Remove 'v' prefix if present
            version_str = version_str.lstrip('v')
            # Handle versions like "1.0" or "1.0.0"
            parts = version_str.split('.')
            while len(parts) < 3:
                parts.append('0')
            return tuple(map(int, parts[:3]))
        except:
            return (0, 0, 0)
    
    def should_check_for_updates(self) -> bool:
        """Check if enough time has passed since last update check (24 hours)"""
        try:
            if not self.last_check_file.exists(): # type: ignore
                return True
            
            with open(self.last_check_file, 'r') as f: # type: ignore
                data = json.load(f)
                last_check = data.get('last_check', 0)
                # Check every 24 hours
                return (time.time() - last_check) > 60
        except:
            return True
    
    def save_last_check(self):
        """Save the timestamp of the last update check"""
        try:
            with open(self.last_check_file, 'w') as f: # type: ignore
                json.dump({'last_check': time.time()}, f)
        except:
            pass
    
    def check_for_updates(self) -> dict:
        """
        Check GitHub for new releases
        Returns: dict with 'available', 'version', 'download_url', 'release_notes'
        """
        try:
            import requests
            response = requests.get(self.api_url, timeout=10)
            
            if response.status_code != 200:
                return {'available': False, 'error': 'Failed to check for updates'}
            
            release_data = response.json()
            latest_version = release_data.get('tag_name', '').lstrip('v')
            
            # Compare versions
            current = self.parse_version(self.current_version)
            latest = self.parse_version(latest_version)
            
            if latest > current:
                # Find the installer .exe asset
                download_url = None
                file_size = 0
                for asset in release_data.get('assets', []):
                    name_lower = asset['name'].lower()
                    # Look for the installer exe (TwitchGameChangerInstaller.exe or similar)
                    if 'installer' in name_lower and name_lower.endswith('.exe'):
                        download_url = asset['browser_download_url']
                        file_size = asset.get('size', 0)
                        break
                
                if not download_url:
                    # Fallback: look for any .exe
                    for asset in release_data.get('assets', []):
                        if asset['name'].endswith('.exe'):
                            download_url = asset['browser_download_url']
                            file_size = asset.get('size', 0)
                            break
                
                return {
                    'available': True,
                    'version': latest_version,
                    'download_url': download_url,
                    'file_size': file_size,
                    'release_notes': release_data.get('body', 'No release notes available.'),
                    'html_url': release_data.get('html_url', '')
                }
            
            return {'available': False}
        
        except Exception as e:
            return {'available': False, 'error': str(e)}
    
    def download_and_install_update(self, download_url: str, callback=None) -> bool:
        """
        Download the installer and run it
        Returns: True if successful, False otherwise
        """
        try:
            import requests
            
            if callback:
                callback("Downloading installer...")
            
            # Download the installer
            response = requests.get(download_url, stream=True, timeout=60)
            
            if response.status_code != 200:
                if callback:
                    callback("Failed to download installer")
                return False
            
            # Save installer to temp location
            installer_path = APP_DATA_DIR / "TwitchGameChangerInstaller_Update.exe"
            
            # Download with progress
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(installer_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if callback and total_size > 0:
                            progress = int((downloaded / total_size) * 100)
                            callback(f"Downloading... {progress}%")
            
            if callback:
                callback("Starting installer...")
            
            # Run the installer silently with /SILENT flag (Inno Setup)
            # /CLOSEAPPLICATIONS will close the current instance
            # /RESTARTAPPLICATIONS will restart after install
            subprocess.Popen([
                str(installer_path),
                '/SILENT',
                '/CLOSEAPPLICATIONS',
                '/RESTARTAPPLICATIONS'
            ])
            
            # Give installer a moment to start
            time.sleep(1)
            
            return True
            
        except Exception as e:
            if callback:
                callback(f"Update failed: {str(e)}")
            return False
    
    def download_installer_for_manual_install(self, download_url: str, callback=None) -> str:
        """
        Download installer for manual installation
        Returns: Path to downloaded installer or None
        """
        try:
            import requests
            
            if callback:
                callback("Downloading installer...")
            
            response = requests.get(download_url, stream=True, timeout=60)
            
            if response.status_code != 200:
                return None # type: ignore
            
            installer_path = APP_DATA_DIR / "TwitchGameChangerInstaller_Update.exe"
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(installer_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if callback and total_size > 0:
                            progress = int((downloaded / total_size) * 100)
                            callback(f"Downloading... {progress}%")
            
            if callback:
                callback("Download complete!")
            
            return str(installer_path)
            
        except Exception:
            return None # type: ignore

# Data Models
class Game:
    def __init__(self, name: str, path: str, platform: str, exe_path: str = ""):
        self.name = name
        self.path = path
        self.platform = platform
        self.exe_path = exe_path if exe_path else path

# Twitch Integration
class TwitchBot:
    CLIENT_ID = 'll2bpleltqt52whwzu4cidrthdgipj'  # kept as in file
    _authenticating = False  # Class-level flag to prevent multiple auth dialogs

    def __init__(self):
        self.config = self.load_config()
        # Decrypt tokens on load
        encrypted_access_token = self.config.get('access_token')
        encrypted_refresh_token = self.config.get('refresh_token')
        self.access_token = TokenEncryption.decrypt(encrypted_access_token) if encrypted_access_token else None
        self.refresh_token = TokenEncryption.decrypt(encrypted_refresh_token) if encrypted_refresh_token else None
        self.user_id = self.config.get('user_id', None)
        self.token_timestamp = self.config.get('token_timestamp', 0)

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
            # Encrypt tokens before saving
            config_to_save = self.config.copy()
            if self.access_token:
                config_to_save['access_token'] = TokenEncryption.encrypt(self.access_token)
            if self.refresh_token:
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
    
    def is_authenticated(self) -> bool:
        """Check if user is authenticated with valid token and enabled"""
        return (self.access_token is not None and 
                self.config.get('enabled', False) and 
                self.config.get('channel_name', '') != '')

    def authenticate(self) -> bool:
        """Device flow with refresh token storage. Only one auth dialog at a time."""
        # Prevent multiple authentication dialogs
        if TwitchBot._authenticating:
            return False
        
        if not self.config.get('channel_name'):
            return False
        
        try:
            TwitchBot._authenticating = True
            import requests, webbrowser, time, threading
            r = requests.post('https://id.twitch.tv/oauth2/device',
                              data={'client_id': self.CLIENT_ID,
                                    'scopes': 'channel:manage:broadcast'},
                              timeout=10)
            if r.status_code != 200:
                TwitchBot._authenticating = False
                return False

            data = r.json()
            user_code, device_code = data['user_code'], data['device_code']
            verify_url = data.get('verification_uri', 'https://www.twitch.tv/activate')
            expires_in = data.get('expires_in', 1800)
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
                import time
                self.token_timestamp = time.time()
                self.config.update({
                    'access_token': self.access_token,
                    'refresh_token': self.refresh_token,
                    'token_timestamp': self.token_timestamp
                })
                self.save_config()
                TwitchBot._authenticating = False
                return True
            
            TwitchBot._authenticating = False
            return False
        except Exception:
            TwitchBot._authenticating = False
            return False

    def refresh_access_token(self) -> bool:
        """Use stored refresh_token to get a new access_token silently."""
        if not self.refresh_token:
            return False
        try:
            import requests
            import time
            r = requests.post('https://id.twitch.tv/oauth2/token', data={
                'grant_type': 'refresh_token',
                'refresh_token': self.refresh_token,
                'client_id': self.CLIENT_ID
            }, timeout=10)
            
            if r.status_code == 200:
                d = r.json()
                self.access_token = d['access_token']
                self.token_timestamp = time.time()
                self.config['access_token'] = self.access_token
                self.config['token_timestamp'] = self.token_timestamp
                # Twitch ALWAYS returns a new refresh token, so update it
                if 'refresh_token' in d:
                    self.refresh_token = d['refresh_token']
                    self.config['refresh_token'] = self.refresh_token
                self.save_config()
                return True
            elif r.status_code == 400:
                # Refresh token is invalid or expired - need to re-authenticate
                self.refresh_token = None
                self.config['refresh_token'] = None
                self.save_config()
                return False
        except Exception:
            pass
        return False

    def ensure_token_valid(self) -> bool:
        """Check token validity, refresh or re-auth if needed. Always tries refresh before re-auth."""
        import time
        
        # Proactive refresh: if token is older than 3 hours (10800 seconds), refresh it
        # Twitch access tokens typically last ~4 hours, so this prevents expiration
        token_age = time.time() - self.token_timestamp if self.token_timestamp else float('inf')
        if token_age > 10800 and self.refresh_token:  # 3 hours = 10800 seconds
            if self.refresh_access_token():
                return True
        
        # If no access token, try refresh first (in case we have refresh token)
        if not self.access_token:
            if self.refresh_token and self.refresh_access_token():
                return True
            return self.authenticate()

        # Try to validate the current access token
        try:
            import requests
            h = {'Authorization': f'Bearer {self.access_token}',
                 'Client-Id': self.CLIENT_ID}
            r = requests.get('https://api.twitch.tv/helix/users', headers=h, timeout=6)
            
            if r.status_code == 200:
                # Token is valid
                return True
            elif r.status_code == 401:
                # Token is invalid/expired - try refresh
                if self.refresh_token and self.refresh_access_token():
                    return True
                # Refresh failed - need to re-authenticate
                return self.authenticate()
            else:
                # Other error - try refresh just in case
                if self.refresh_token and self.refresh_access_token():
                    return True
                return False
        except Exception:
            # Network error or other exception
            # Don't immediately re-auth on network errors
            # The token might still be valid, just couldn't reach API
            # Return False but don't trigger re-authentication
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

# Game Scanner
class GameScanner:
    # Applications that should NEVER be included in scans
    PERMANENT_EXCLUSIONS = {
        'Steamworks Common Redistributables',
        'Wallpaper Engine',
        'wallpaper engine',
    }
    
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
        # Check if in permanent exclusions (case-insensitive)
        name_lower = name.lower()
        for perm_exclusion in self.PERMANENT_EXCLUSIONS:
            if name_lower == perm_exclusion.lower():
                return True
        # Check user exclusions
        return name in self.excluded

    def get_drives(self) -> List[str]:
        import string
        return [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]

    def scan_steam(self) -> List[Game]:
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
                                                    
                                                    # Special handling for Marvel Rivals on Steam
                                                    if "marvel rivals" in name.lower():
                                                        # NOTE: Game uses "Marvel" not "MarvelRivals" in exe names!
                                                        marvel_exes = [
                                                            gpath / "Marvel-Win64-Shipping.exe",
                                                            gpath / "Marvel" / "Binaries" / "Win64" / "Marvel-Win64-Shipping.exe",
                                                            gpath / "Binaries" / "Win64" / "Marvel-Win64-Shipping.exe",
                                                            gpath / "MarvelGame" / "Marvel" / "Binaries" / "Win64" / "Marvel-Win64-Shipping.exe",
                                                            # Also check for MarvelRivals variant
                                                            gpath / "MarvelRivals" / "Binaries" / "Win64" / "MarvelRivals-Win64-Shipping.exe",
                                                            gpath / "Binaries" / "Win64" / "MarvelRivals-Win64-Shipping.exe",
                                                            gpath / "MarvelRivals-Win64-Shipping.exe",
                                                        ]
                                                        for marvel_exe in marvel_exes:
                                                            if marvel_exe.exists():
                                                                exe_found = marvel_exe
                                                                break
                                                        
                                                        # If still not found, do a deep search for Marvel Rivals specifically
                                                        if not exe_found:
                                                            try:
                                                                for root, dirs, files in os.walk(gpath):
                                                                    depth = root[len(str(gpath)):].count(os.sep)
                                                                    if depth > 5:
                                                                        dirs.clear()
                                                                        continue
                                                                    for file in files:
                                                                        file_lower = file.lower()
                                                                        # Look for Marvel-Win64-Shipping.exe OR MarvelRivals-Win64-Shipping.exe
                                                                        if (file_lower.endswith('-win64-shipping.exe') and 
                                                                            ('marvel-' in file_lower or 'marvelrivals-' in file_lower)):
                                                                            exe_found = Path(root) / file
                                                                            break
                                                                    if exe_found:
                                                                        break
                                                            except Exception:
                                                                pass
                                                    
                                                    # Standard exe detection if not found yet (for non-Marvel games or as fallback)
                                                    if not exe_found:
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
                                                            skip_patterns = ['unins', 'install', 'setup', 'crash', 'report', 'redist', 'dotnet', 'directx', 'vcredist', 'unity', 'unreal', 'launcher']
                                                            
                                                            # For Marvel Rivals specifically, ONLY accept shipping exe
                                                            if "marvel rivals" in name.lower():
                                                                exes_root = [e for e in gpath.glob("*.exe") 
                                                                            if 'shipping' in e.stem.lower() and not any(skip in e.stem.lower() for skip in skip_patterns)]
                                                            else:
                                                                exes_root = [e for e in gpath.glob("*.exe") 
                                                                            if not any(skip in e.stem.lower() for skip in skip_patterns)]
                                                            
                                                            if exes_root:
                                                                game_exes = [e for e in exes_root if 'game' in e.stem.lower() or installdir.lower() in e.stem.lower()]
                                                                exe_found = game_exes[0] if game_exes else exes_root[0]
                                                            else:
                                                                for root, dirs, files in os.walk(gpath):
                                                                    depth = root[len(str(gpath)):].count(os.sep)
                                                                    if depth > 3:
                                                                        dirs.clear()
                                                                        continue
                                                                    
                                                                    # For Marvel Rivals, ONLY look for shipping exe
                                                                    if "marvel rivals" in name.lower():
                                                                        exe_files = [f for f in files if f.endswith('.exe') 
                                                                                    and 'shipping' in f.lower()
                                                                                    and ('marvel-' in f.lower() or 'marvelrivals-' in f.lower())
                                                                                    and not any(skip in f.lower() for skip in skip_patterns)]
                                                                    else:
                                                                        exe_files = [f for f in files if f.endswith('.exe') 
                                                                                    and not any(skip in f.lower() for skip in skip_patterns)]
                                                                    
                                                                    if exe_files:
                                                                        game_exes = [f for f in exe_files if 'game' in f.lower() or installdir.lower() in f.lower()]
                                                                        exe_found = Path(root) / (game_exes[0] if game_exes else exe_files[0])
                                                                        break
                                                        except Exception:
                                                            pass
                                                    games.append(Game(name, str(gpath), "Steam", str(exe_found) if exe_found else ""))
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
                            gpath = Path(location)
                            exe_found = None
                            
                            # Special handling for Marvel Rivals on Epic
                            if "marvel rivals" in name.lower():
                                marvel_exes = [
                                    gpath / "MarvelRivals" / "Binaries" / "Win64" / "MarvelRivals-Win64-Shipping.exe",
                                    gpath / "Binaries" / "Win64" / "MarvelRivals-Win64-Shipping.exe",
                                    gpath / "MarvelRivals-Win64-Shipping.exe",
                                ]
                                for marvel_exe in marvel_exes:
                                    if marvel_exe.exists():
                                        exe_found = marvel_exe
                                        break
                                
                                # If still not found, do a deep search for Marvel Rivals specifically
                                if not exe_found:
                                    try:
                                        for root, dirs, files in os.walk(gpath):
                                            depth = root[len(str(gpath)):].count(os.sep)
                                            if depth > 5:
                                                dirs.clear()
                                                continue
                                            for file in files:
                                                if file.lower() in ['marvelrivals-win64-shipping.exe', 'marvelrivals.exe']:
                                                    exe_found = Path(root) / file
                                                    break
                                            if exe_found:
                                                break
                                    except Exception:
                                        pass
                            
                            # Special handling for Fortnite
                            elif "fortnite" in name.lower():
                                fortnite_exes = [
                                    gpath / "FortniteGame" / "Binaries" / "Win64" / "FortniteClient-Win64-Shipping.exe",
                                    gpath / "Binaries" / "Win64" / "FortniteClient-Win64-Shipping.exe",
                                    gpath / "FortniteClient-Win64-Shipping.exe",
                                ]
                                for fortnite_exe in fortnite_exes:
                                    if fortnite_exe.exists():
                                        exe_found = fortnite_exe
                                        break
                                
                                # If still not found, search for it
                                if not exe_found:
                                    try:
                                        for root, dirs, files in os.walk(gpath):
                                            depth = root[len(str(gpath)):].count(os.sep)
                                            if depth > 5:
                                                dirs.clear()
                                                continue
                                            for file in files:
                                                if file.lower() in ['fortniteclient-win64-shipping.exe', 'fortnite.exe']:
                                                    exe_found = Path(root) / file
                                                    break
                                            if exe_found:
                                                break
                                    except Exception:
                                        pass
                            
                            # Standard detection if not found (for other games or as final fallback)
                            if not exe_found:
                                skip_patterns = ['unins', 'install', 'setup', 'crash']
                                # Don't skip 'launcher' for Marvel Rivals and Fortnite
                                if "marvel rivals" not in name.lower() and "fortnite" not in name.lower():
                                    skip_patterns.append('launcher')
                                
                                for exe in gpath.glob("*.exe"):
                                    if not any(skip in exe.stem.lower() for skip in skip_patterns):
                                        exe_found = exe
                                        break
                            
                            games.append(Game(name, location, "Epic Games", str(exe_found) if exe_found else ""))
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
                        games.append(Game(name, path, "GOG", exe_path))
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except Exception:
            pass
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
                                    exe_found = None
                                    
                                    # Special handling for VALORANT - find the actual game exe
                                    if folder.name.lower() == "valorant":
                                        valorant_patterns = [
                                            folder / "live" / "ShooterGame" / "Binaries" / "Win64" / "VALORANT-Win64-Shipping.exe",
                                            folder / "live" / "VALORANT-Win64-Shipping.exe",
                                            folder / "VALORANT-Win64-Shipping.exe",
                                            folder / "VALORANT.exe",
                                        ]
                                        
                                        for pattern in valorant_patterns:
                                            if pattern.exists() and pattern.is_file():
                                                exe_found = pattern
                                                break
                                        
                                        # Deep search if not found
                                        if not exe_found:
                                            for root, dirs, files in os.walk(folder):
                                                for file in files:
                                                    file_lower = file.lower()
                                                    if file_lower == "valorant-win64-shipping.exe" or file_lower == "valorant.exe":
                                                        # Make sure it's not the launcher
                                                        if "riotclient" not in file_lower:
                                                            exe_found = Path(root) / file
                                                            break
                                                if exe_found:
                                                    break
                                    
                                    # Standard detection for other Riot games
                                    if not exe_found:
                                        for exe in folder.glob("*.exe"):
                                            if not any(skip in exe.stem.lower() for skip in ['unins', 'install', 'setup', 'riotclient']):
                                                exe_found = exe
                                                break
                                    
                                    games.append(Game(folder.name, str(folder), "Riot Games", str(exe_found) if exe_found else ""))
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
                                        games.append(Game(game_info["name"], str(item), "Battle.net", str(exe_found)))
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
                                games.append(Game(game_name, str(content_folder), "Xbox", str(exes[0])))
        return games

    def scan_marvel_rivals_universal(self) -> List[Game]:
        """Scan all drives for Marvel Rivals standalone install (excluding Steam/Epic)."""
        games = []
        found_paths = set()
        import string

        drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]

        for drive in drives:
            try:
                for root, dirs, files in os.walk(drive):
                    skip = ['windows', '$recycle.bin', 'system volume information', 'program files', 'program files (x86)']
                    dirs[:] = [d for d in dirs if d.lower() not in skip]

                    if root.count(os.sep) - drive.count(os.sep) > 6:
                        dirs.clear()
                        continue

                    # Look for folder name Marvel Rivals
                    if os.path.basename(root).lower() == "marvel rivals":
                        root_lower = root.lower()
                        if "steamapps" in root_lower or "epic" in root_lower:
                            continue  # skip Steam / Epic

                        game_path = Path(root)
                        exe_found = None

                        # Look specifically for the shipping exe
                        # NOTE: Game uses "Marvel" not "MarvelRivals" in exe names!
                        for r, d2, f2 in os.walk(game_path):
                            for file in f2:
                                file_lower = file.lower()
                                # Look for Marvel-Win64-Shipping.exe OR MarvelRivals-Win64-Shipping.exe
                                if (file_lower.endswith('-win64-shipping.exe') and 
                                    ('marvel-' in file_lower or 'marvelrivals-' in file_lower)):
                                    exe_found = Path(r) / file
                                    break
                            if exe_found:
                                break

                        # Fallback - ONLY accept shipping exe, NOT launcher
                        if not exe_found:
                            for r, d2, f2 in os.walk(game_path):
                                for file in f2:
                                    file_lower = file.lower()
                                    # MUST have "shipping" in the name to be accepted
                                    if (file_lower.endswith(".exe") and 
                                        "shipping" in file_lower and 
                                        ("marvel" in file_lower or "marvelrivals" in file_lower)):
                                        exe_found = Path(r) / file
                                        break
                                if exe_found:
                                    break

                        platform = "NetEase" if "netease" in root_lower else "Other"

                        # Save real EXE path
                        games.append(
                            Game("Marvel Rivals", str(game_path), platform, str(exe_found) if exe_found else "")
                        )

            except:
                continue

        return games


    def scan_all(self) -> List[Game]:
        all_games = []
        all_games.extend(self.scan_steam())
        all_games.extend(self.scan_epic())
        all_games.extend(self.scan_gog())
        all_games.extend(self.scan_riot())
        all_games.extend(self.scan_battlenet())
        all_games.extend(self.scan_xbox())
        all_games.extend(self.scan_marvel_rivals_universal())
        return all_games

# Game Monitor
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
            # Special handling for Marvel Rivals - ALWAYS try to find the shipping exe
            if "marvel rivals" in game.name.lower():
                try:
                    game_path = Path(game.path)
                    
                    # Common Marvel Rivals executable patterns across platforms
                    # NOTE: The game uses "Marvel" not "MarvelRivals" in exe names!
                    marvel_patterns = [
                        # Steam version - uses "Marvel" not "MarvelRivals"
                        game_path / "Marvel.exe",
                        game_path / "Marvel-Win64-Shipping.exe",
                        game_path / "Marvel" / "Binaries" / "Win64" / "Marvel-Win64-Shipping.exe",
                        game_path / "Binaries" / "Win64" / "Marvel-Win64-Shipping.exe",
                        
                        # Also check for MarvelRivals variant (some versions)
                        game_path / "MarvelRivals.exe",
                        game_path / "MarvelRivals-Win64-Shipping.exe",
                        game_path / "MarvelRivals" / "Binaries" / "Win64" / "MarvelRivals-Win64-Shipping.exe",
                        
                        # Epic Games version
                        game_path / "MarvelRivals-Win64-Shipping.exe",
                        
                        # NetEase/Standalone Launcher version
                        game_path / "Game" / "MarvelRivals" / "Binaries" / "Win64" / "MarvelRivals-Win64-Shipping.exe",
                        game_path / "MarvelGame" / "Marvel" / "Binaries" / "Win64" / "Marvel-Win64-Shipping.exe",
                    ]
                    
                    # Try common patterns first
                    for pattern_path in marvel_patterns:
                        if pattern_path.exists() and pattern_path.is_file():
                            marvel_exe_norm = os.path.normpath(str(pattern_path)).lower()
                            self.exe_map[marvel_exe_norm] = game.name
                    
                    # Do a thorough recursive search for ONLY the shipping executable
                    # Accept EITHER "Marvel" OR "MarvelRivals" in the filename
                    for root, dirs, files in os.walk(game_path):
                        depth = root[len(str(game_path)):].count(os.sep)
                        if depth > 6:  # Increased depth for nested structures
                            dirs.clear()
                            continue
                        for file in files:
                            file_lower = file.lower()
                            # Add ONLY the actual game executable with "shipping" in name
                            # Accept: Marvel-Win64-Shipping.exe OR MarvelRivals-Win64-Shipping.exe
                            # Reject: Anything with "launcher"
                            if (file_lower.endswith('.exe') and 
                                'shipping' in file_lower and 
                                ('marvel-' in file_lower or 'marvelrivals-' in file_lower) and
                                'launcher' not in file_lower):
                                marvel_exe = Path(root) / file
                                marvel_exe_norm = os.path.normpath(str(marvel_exe)).lower()
                                self.exe_map[marvel_exe_norm] = game.name
                    
                except Exception:
                    pass
                # Don't process the rest of the standard logic for Marvel Rivals
                continue
            
            # Special handling for Valorant - ALWAYS try to find the shipping exe
            if "valorant" in game.name.lower():
                try:
                    game_path = Path(game.path)
                    
                    # Common Valorant executable patterns
                    valorant_patterns = [
                        game_path / "live" / "ShooterGame" / "Binaries" / "Win64" / "VALORANT-Win64-Shipping.exe",
                        game_path / "live" / "VALORANT-Win64-Shipping.exe",
                        game_path / "VALORANT-Win64-Shipping.exe",
                        game_path / "VALORANT.exe",
                    ]
                    
                    # Try common patterns first
                    for pattern_path in valorant_patterns:
                        if pattern_path.exists() and pattern_path.is_file():
                            valorant_exe_norm = os.path.normpath(str(pattern_path)).lower()
                            self.exe_map[valorant_exe_norm] = game.name
                    
                    # Do a thorough recursive search for the shipping executable
                    for root, dirs, files in os.walk(game_path):
                        depth = root[len(str(game_path)):].count(os.sep)
                        if depth > 6:
                            dirs.clear()
                            continue
                        for file in files:
                            file_lower = file.lower()
                            # Look for VALORANT-Win64-Shipping.exe (NOT RiotClientServices.exe)
                            if (file_lower.endswith('.exe') and 
                                'valorant' in file_lower and 
                                ('shipping' in file_lower or file_lower == 'valorant.exe') and
                                'riotclient' not in file_lower):
                                valorant_exe = Path(root) / file
                                valorant_exe_norm = os.path.normpath(str(valorant_exe)).lower()
                                self.exe_map[valorant_exe_norm] = game.name
                    
                except Exception:
                    pass
                # Don't process the rest of the standard logic for Valorant
                continue
            
            # Standard processing for other games
            if game.exe_path and os.path.exists(game.exe_path):
                norm_path = os.path.normpath(game.exe_path).lower()
                self.exe_map[norm_path] = game.name
                
            # Special handling for Fortnite - detect actual game exe
            if "fortnite" in game.name.lower():
                try:
                    game_path = Path(game.path)
                    
                    # Common Fortnite executable patterns
                    fortnite_patterns = [
                        game_path / "FortniteGame" / "Binaries" / "Win64" / "FortniteClient-Win64-Shipping.exe",
                        game_path / "Binaries" / "Win64" / "FortniteClient-Win64-Shipping.exe",
                        game_path / "FortniteClient-Win64-Shipping.exe",
                        game_path / "FortniteGame" / "Binaries" / "Win64" / "FortniteLauncher.exe",
                    ]
                    
                    # Try common patterns first
                    for pattern_path in fortnite_patterns:
                        if pattern_path.exists() and pattern_path.is_file():
                            fortnite_exe_norm = os.path.normpath(str(pattern_path)).lower()
                            self.exe_map[fortnite_exe_norm] = game.name
                    
                    # Do a thorough recursive search for Fortnite executables
                    for root, dirs, files in os.walk(game_path):
                        depth = root[len(str(game_path)):].count(os.sep)
                        if depth > 5:  # Limit search depth
                            dirs.clear()
                            continue
                        for file in files:
                            file_lower = file.lower()
                            # Add ANY exe that might be the game
                            if file.endswith('.exe'):
                                # Priority 1: Game client
                                if any(keyword in file_lower for keyword in ['fortniteclient', 'shipping']):
                                    fortnite_exe = Path(root) / file
                                    fortnite_exe_norm = os.path.normpath(str(fortnite_exe)).lower()
                                    self.exe_map[fortnite_exe_norm] = game.name
                                # Priority 2: Any exe in FortniteGame/Binaries folder
                                elif 'fortnitegame' in root.lower() and 'binaries' in root.lower():
                                    fortnite_exe = Path(root) / file
                                    fortnite_exe_norm = os.path.normpath(str(fortnite_exe)).lower()
                                    self.exe_map[fortnite_exe_norm] = game.name
                except Exception:
                    pass
            
            # Also add the parent directory's other executables for games with multiple EXEs
            if game.exe_path and os.path.exists(game.exe_path):
                try:
                    exe_dir = Path(game.exe_path).parent
                    for exe in exe_dir.glob("*.exe"):
                        exe_norm = os.path.normpath(str(exe)).lower()
                        if exe_norm not in self.exe_map:
                            # Only add if it's a reasonable game executable (not an installer/uninstaller)
                            exe_name = exe.stem.lower()
                            skip_patterns = ['unins', 'install', 'setup', 'crash', 'report']
                            
                            # For Marvel Rivals, ONLY accept the shipping exe, NOT launcher
                            if "marvel rivals" in game.name.lower():
                                # Must contain BOTH "shipping" AND not contain "launcher"
                                if 'shipping' not in exe_name:
                                    continue  # Skip non-shipping executables
                                if 'launcher' in exe_name:
                                    continue  # Skip launcher executables
                            # Only skip launcher for games that aren't Fortnite
                            elif "fortnite" not in game.name.lower():
                                skip_patterns.append('launcher')
                            
                            if not any(skip in exe_name for skip in skip_patterns):
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
                                    self.status_callback(f"Game {game_name} detected!", "#34d399")
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
                    if elapsed >= 5:
                        games_to_close.append(game_name)

                for game_name in games_to_close:
                    del self.close_timers[game_name]
                    if self.twitch.config.get('enabled'):
                        threading.Thread(target=lambda: self.twitch.change_category("Just Chatting"), daemon=True).start()
                    self.status_callback(f"Closed: {game_name} closed", "#fbbf24")

                time.sleep(3.5)
            except Exception:
                time.sleep(3.5)

# GUI Application
class GUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Twitch Game Changer")

        # --- Tray logic moved to be persistent ---
        self.tray_icon = None
        self.is_minimized_to_tray = False # Flag to know if window is hidden
        self.app_is_closing = False      # Flag to control tray thread exit

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
        w, h = 1250, 800
        x = (root.winfo_screenwidth() - w) // 2
        y = (root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.minsize(1100, 700)
        self.root.configure(bg="#0a0e27")

        # Close behavior
        if TRAY_AVAILABLE:
            self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
            # --- Start the persistent tray icon on launch ---
            self.start_persistent_tray()
        else:
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Core components
        self.scanner = GameScanner()
        self.twitch = TwitchBot()
        self.monitor = None
        self.games = []
        self.filtered = []
        
        # Initialize updater
        self.updater = AutoUpdater(APP_VERSION, GITHUB_REPO, GITHUB_API_URL)

        self.setup_ui()
        self.root.after(1400, self.load_cache)
        # Auto-start monitor if Twitch is authenticated (after cache loads)
        self.root.after(1600, self.auto_start_monitor)
        # Check for updates after UI loads (non-blocking)
        self.root.after(2000, self.check_for_updates_background)

    def setup_ui(self):
        # Smooth, soft color scheme with gradual transitions
        self.colors = {
            'bg_dark': '#0d1117',          # Soft dark background
            'bg_medium': '#161b22',         # Medium background
            'bg_card': '#1f2937',           # Card background - softer
            'bg_hover': '#374151',          # Hover state - gentle transition
            'accent_blue': '#60a5fa',       # Soft blue
            'accent_purple': '#a78bfa',     # Gentle purple
            'accent_green': '#34d399',      # Smooth green
            'accent_red': '#f87171',        # Soft red
            'accent_orange': '#fb923c',     # Warm orange
            'text_primary': '#f9fafb',      # Soft white
            'text_secondary': '#9ca3af',    # Gentle gray
            'border': '#374151',            # Subtle smooth border
            'shadow': '#00000050',          # Soft shadow
        }
        
        self.root.configure(bg=self.colors['bg_dark'])
        
        # View mode (grid or list)
        self.view_mode = tk.StringVar(value="list")  # Default to list view
        
        # Image cache for covers/icons
        self.image_cache = {}
        
        # Top control bar with smooth, rounded feel
        topbar = tk.Frame(self.root, bg=self.colors['bg_medium'], height=80)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)
        
        # Left side - action buttons (no icons, smooth rounded feel)
        left_controls = tk.Frame(topbar, bg=self.colors['bg_medium'])
        left_controls.pack(side="left", padx=25, pady=18)
        
        btn_style = {
            "font": ("Segoe UI", 11, "bold"),
            "relief": "flat",
            "cursor": "hand2",
            "borderwidth": 0,
            "padx": 24,
            "pady": 12
        }
        
        # Create buttons with smooth styling (no icons)
        scan_btn = tk.Button(left_controls, text="Scan", command=self.scan,
                 bg=self.colors['accent_blue'], fg=self.colors['text_primary'],
                 activebackground="#4a8de0", **btn_style)
        scan_btn.pack(side="left", padx=5)
        
        add_btn = tk.Button(left_controls, text="Add Game", command=self.add_manual_game,
                 bg=self.colors['accent_purple'], fg=self.colors['text_primary'],
                 activebackground="#9d4edd", **btn_style)
        add_btn.pack(side="left", padx=5)
        
        twitch_btn = tk.Button(left_controls, text="Twitch", command=self.twitch_settings,
                 bg="#9146ff", fg=self.colors['text_primary'],
                 activebackground="#7c3aed", **btn_style)
        twitch_btn.pack(side="left", padx=5)
        
        excluded_btn = tk.Button(left_controls, text="Excluded", command=self.show_excluded_games,
                 bg=self.colors['bg_card'], fg=self.colors['text_primary'],
                 activebackground=self.colors['bg_hover'], **btn_style)
        excluded_btn.pack(side="left", padx=5)
        
        # Monitor button removed - monitoring is automatic when authenticated
        
        # Add smooth hover effects to all buttons
        def create_hover_effect(button, hover_color):
            original_color = button.cget("bg")
            def on_enter(e):
                button.config(bg=hover_color)
            def on_leave(e):
                button.config(bg=original_color)
            button.bind("<Enter>", on_enter)
            button.bind("<Leave>", on_leave)
        
        create_hover_effect(scan_btn, "#4a8de0")
        create_hover_effect(add_btn, "#9d4edd")
        create_hover_effect(twitch_btn, "#7c3aed")
        create_hover_effect(excluded_btn, self.colors['bg_hover'])
        
        # Right side - search, filter, view toggle
        right_controls = tk.Frame(topbar, bg=self.colors['bg_medium'])
        right_controls.pack(side="right", padx=20, pady=15)
        
        # View toggle buttons with smooth rounded styling (no icons)
        view_frame = tk.Frame(right_controls, bg=self.colors['bg_card'], 
                             highlightthickness=0)
        view_frame.pack(side="right", padx=(12, 0))
        
        self.list_btn = tk.Button(view_frame, text="List", command=lambda: self.set_view_mode("list"),
                                  bg=self.colors['accent_blue'], fg=self.colors['text_primary'],
                                  activebackground="#4a8de0", relief="flat", padx=20, pady=10,
                                  font=("Segoe UI", 10, "bold"), cursor="hand2", borderwidth=0)
        self.list_btn.pack(side="left", padx=1)
        
        self.grid_btn = tk.Button(view_frame, text="Grid", command=lambda: self.set_view_mode("grid"),
                                  bg=self.colors['bg_card'], fg=self.colors['text_secondary'],
                                  activebackground=self.colors['bg_hover'], relief="flat", padx=20, pady=10,
                                  font=("Segoe UI", 10, "bold"), cursor="hand2", borderwidth=0)
        self.grid_btn.pack(side="left", padx=1)
        
        # Add smooth hover effects
        def create_view_hover(button):
            def on_enter(e):
                if button.cget("bg") != self.colors['accent_blue']:
                    button.config(bg=self.colors['bg_hover'])
            def on_leave(e):
                if button.cget("bg") != self.colors['accent_blue']:
                    button.config(bg=self.colors['bg_card'])
            button.bind("<Enter>", on_enter)
            button.bind("<Leave>", on_leave)
        
        create_view_hover(self.list_btn)
        create_view_hover(self.grid_btn)
        
        # Platform filter
        filter_frame = tk.Frame(right_controls, bg=self.colors['bg_card'], highlightthickness=1,
                               highlightbackground=self.colors['border'])
        filter_frame.pack(side="right", padx=4)
        self.platform_var = tk.StringVar(value="All Platforms")
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Dark.TCombobox',
                       fieldbackground=self.colors['bg_card'],
                       background=self.colors['bg_card'],
                       foreground=self.colors['text_primary'],
                       borderwidth=0,
                       arrowcolor=self.colors['text_secondary'])
        style.map('Dark.TCombobox',
                 fieldbackground=[('readonly', self.colors['bg_card'])],
                 selectbackground=[('readonly', self.colors['bg_card'])],
                 selectforeground=[('readonly', self.colors['text_primary'])])
        
        platform_combo = ttk.Combobox(filter_frame, textvariable=self.platform_var,
                                     values=["All Platforms", "Steam", "Epic Games", "GOG",
                                           "Riot Games", "Battle.net", "Xbox", "Other"],
                                     state="readonly", font=("Segoe UI", 9), width=14,
                                     style='Dark.TCombobox')
        platform_combo.pack(padx=8, pady=6)
        self.platform_var.trace("w", lambda *args: self.filter())
        
        # Search box
        search_box = tk.Frame(right_controls, bg=self.colors['bg_card'], highlightthickness=1,
                             highlightbackground=self.colors['border'])
        search_box.pack(side="right", padx=4)
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *args: self.filter())
        search_entry = tk.Entry(search_box, textvariable=self.search_var, font=("Segoe UI", 10),
                               bg=self.colors['bg_card'], fg=self.colors['text_primary'],
                               relief="flat", width=25, borderwidth=0,
                               insertbackground=self.colors['accent_blue'])
        search_entry.pack(side="left", padx=10, pady=7)
        search_entry.insert(0, "Search games...")
        search_entry.bind("<FocusIn>", lambda e: search_entry.delete(0, tk.END) if search_entry.get() == "Search games..." else None)
        search_entry.bind("<FocusOut>", lambda e: search_entry.insert(0, "Search games...") if not search_entry.get() else None)
        
        # Status bar
        self.status = tk.Label(self.root, text="Ready to scan", font=("Segoe UI", 9),
                              bg=self.colors['bg_medium'], fg=self.colors['text_secondary'],
                              anchor="w", padx=20, pady=8)
        self.status.pack(fill="x")
        
        # Version info (bottom left of status bar)
        version_label = tk.Label(self.status, text=f"v{APP_VERSION}",
                                font=("Segoe UI", 8), bg=self.colors['bg_medium'],
                                fg=self.colors['text_secondary'])
        version_label.place(relx=1.0, rely=0.5, anchor="e", x=-20)
        
        self.update_indicator = tk.Label(self.status, text="", font=("Segoe UI", 8, "bold"),
                                         bg=self.colors['bg_medium'], fg=self.colors['accent_green'],
                                         cursor="hand2")
        self.update_indicator.place(relx=1.0, rely=0.5, anchor="e", x=-80)
        self.update_indicator.bind("<Button-1>", lambda e: self.show_update_dialog())
        
        # Main content area with scrolling
        container = tk.Frame(self.root, bg=self.colors['bg_dark'])
        container.pack(fill="both", expand=True, padx=15, pady=(10, 15))
        
        self.canvas = tk.Canvas(container, bg=self.colors['bg_dark'], highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        
        scrollbar = tk.Scrollbar(container, orient="vertical", command=self.canvas.yview,
                                bg=self.colors['bg_dark'], troughcolor=self.colors['bg_medium'],
                                activebackground=self.colors['text_secondary'], width=12)
        scrollbar.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.games_frame = tk.Frame(self.canvas, bg=self.colors['bg_dark'])
        self.canvas_window = self.canvas.create_window((0, 0), window=self.games_frame, anchor="nw")
        
        def on_configure(event):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.games_frame.bind("<Configure>", on_configure)
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))
        
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)
    
    def set_view_mode(self, mode):
        """Toggle between grid and list view"""
        self.view_mode.set(mode)
        if mode == "list":
            self.list_btn.config(bg=self.colors['accent_blue'], fg=self.colors['text_primary'])
            self.grid_btn.config(bg=self.colors['bg_card'], fg=self.colors['text_secondary'])
        else:
            self.grid_btn.config(bg=self.colors['accent_blue'], fg=self.colors['text_primary'])
            self.list_btn.config(bg=self.colors['bg_card'], fg=self.colors['text_secondary'])
        self.display()
    
    def fetch_game_image(self, game_name, image_type="icon"):
        """Fetch high-quality icons and covers with better non-Steam game support"""
        # Check cache first
        cache_key = f"{game_name}_{image_type}"
        if cache_key in self.image_cache:
            return self.image_cache[cache_key]
        
        try:
            import requests
            from io import BytesIO
            from PIL import Image, ImageTk
            import urllib.parse
            
            # Clean game name
            clean_name = game_name.replace('™', '').replace('®', '').replace('©', '').strip()
            clean_name = clean_name.replace(':', '').replace('  ', ' ')
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            image_urls = []
            
            print(f"🔍 Searching for images: {clean_name}")
            
            # ===== METHOD 1: Steam Community (BEST quality for Steam games) =====
            try:
                steam_search = clean_name.lower().replace(' ', '%20')
                steam_url = f"https://steamcommunity.com/actions/SearchApps/{steam_search}"
                
                response = requests.get(steam_url, headers=headers, timeout=5)
                if response.status_code == 200:
                    steam_data = response.json()
                    if steam_data and len(steam_data) > 0:
                        app_id = steam_data[0].get('appid')
                        if app_id:
                            print(f"✓ Found Steam App ID: {app_id}")
                            
                            if image_type == "icon":
                                # PRIORITY ORDER: Best quality icons first!
                                # 1. Library capsule (best quality, large)
                                image_urls.append(f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/capsule_184x69.jpg")
                                image_urls.append(f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/capsule_231x87.jpg")
                                # 2. Logo from community (high quality)
                                logo = steam_data[0].get('logo', '')
                                if logo:
                                    image_urls.append(f"https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/{app_id}/{logo}.jpg")
                                # 3. Header (good fallback)
                                image_urls.append(f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg")
                            else:
                                # For covers, get highest quality available
                                image_urls.append(f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/library_600x900_2x.jpg")
                                image_urls.append(f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/library_600x900.jpg")
                                image_urls.append(f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/library_hero.jpg")
                                image_urls.append(f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg")
                
            except Exception as e:
                print(f"  Steam search error: {e}")
            
            # ===== METHOD 2: RAWG API (Good for non-Steam games) =====
            if not image_urls or len(image_urls) == 0:
                try:
                    # RAWG has good coverage for all platforms
                    rawg_search = clean_name.lower().replace(' ', '-').replace("'", "")
                    rawg_url = f"https://api.rawg.io/api/games/{rawg_search}"
                    
                    response = requests.get(rawg_url, headers=headers, timeout=5)
                    if response.status_code == 200:
                        rawg_data = response.json()
                        
                        # Get background image (usually high quality)
                        bg_image = rawg_data.get('background_image')
                        if bg_image:
                            print(f"✓ Found RAWG image")
                            image_urls.append(bg_image)
                        
                        # Get additional background
                        bg_add = rawg_data.get('background_image_additional')
                        if bg_add:
                            image_urls.append(bg_add)
                    else:
                        # Try with spaces instead of dashes
                        rawg_search2 = clean_name.lower().replace(' ', '%20')
                        rawg_url2 = f"https://api.rawg.io/api/games?search={rawg_search2}"
                        
                        response2 = requests.get(rawg_url2, headers=headers, timeout=5)
                        if response2.status_code == 200:
                            rawg_data2 = response2.json()
                            results = rawg_data2.get('results', [])
                            if results and len(results) > 0:
                                print(f"✓ Found RAWG game via search")
                                bg_image = results[0].get('background_image')
                                if bg_image:
                                    image_urls.append(bg_image)
                        
                except Exception as e:
                    print(f"  RAWG search error: {e}")
            
            # ===== METHOD 3: Epic Games Store (for Epic games) =====
            if not image_urls and any(x in game_name.lower() for x in ['fortnite', 'rocket league', 'fall guys']):
                try:
                    # Common Epic Games images
                    epic_game_ids = {
                        'fortnite': 'fortnite',
                        'rocket league': 'sugar',
                        'fall guys': 'fallguys'
                    }
                    
                    for game_key, game_id in epic_game_ids.items():
                        if game_key in clean_name.lower():
                            print(f"✓ Detected Epic game: {game_key}")
                            # Epic CDN URLs
                            if image_type == "icon":
                                image_urls.append(f"https://cdn2.unrealengine.com/{game_id}-logo.png")
                            image_urls.append(f"https://cdn2.unrealengine.com/{game_id}-keyart.jpg")
                            break
                            
                except Exception as e:
                    print(f"  Epic search error: {e}")
            
            # ===== METHOD 4: Special handling for known games =====
            if not image_urls:
                try:
                    game_lower = clean_name.lower()
                    
                    # Marvel Rivals
                    if 'marvel' in game_lower and 'rivals' in game_lower:
                        print(f"✓ Detected Marvel Rivals")
                        image_urls.append("https://cdn.marvel.com/content/1x/marvrivals_lob_crd_01.jpg")
                        image_urls.append("https://www.marvelrivals.com/images/share-en.jpg")
                    
                    # Valorant
                    elif 'valorant' in game_lower:
                        print(f"✓ Detected Valorant")
                        image_urls.append("https://images.contentstack.io/v3/assets/bltb6530b271fddd0b1/blt5c61cf2eb38b3d53/5eb26f413b2d42079e84200a/V_AGENTS_587x900_Jett.png")
                        image_urls.append("https://playvalorant.com/assets/images/valorant-logo.png")
                    
                    # League of Legends
                    elif 'league' in game_lower and 'legends' in game_lower:
                        print(f"✓ Detected League of Legends")
                        image_urls.append("https://lolstatic-a.akamaihd.net/frontpage/apps/prod/rg-league-display-2021/en_US/5f0f4e0d0ee3a67f3a7e5fa54e7ef20bdc0c7143/assets/images/logo.png")
                    
                    # Overwatch
                    elif 'overwatch' in game_lower:
                        print(f"✓ Detected Overwatch")
                        image_urls.append("https://blz-contentstack-images.akamaized.net/v3/assets/blt9c12f249ac15c7ec/blt5a6b396c54b2b7b5/634f89c4e6d60c106d533909/ow-logo.png")
                    
                except Exception as e:
                    print(f"  Special handling error: {e}")
            
            # ===== Try to download and process images =====
            if not image_urls:
                print(f"✗ No image sources found for '{game_name}'")
                return None
            
            print(f"  Found {len(image_urls)} potential image sources")
            
            for idx, source_url in enumerate(image_urls):
                try:
                    print(f"  → Trying source {idx+1}/{len(image_urls)}: {source_url[:70]}...")
                    img_response = requests.get(source_url, timeout=10, headers=headers)
                    
                    if img_response.status_code == 200 and len(img_response.content) > 500:
                        # Valid image data
                        img_data = BytesIO(img_response.content)
                        img = Image.open(img_data)
                        
                        # Convert to RGB if needed (some PNGs have alpha)
                        if img.mode in ('RGBA', 'LA', 'P'):
                            # Create white background
                            background = Image.new('RGB', img.size, (255, 255, 255))
                            if img.mode == 'P':
                                img = img.convert('RGBA')
                            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                            img = background
                        
                        # Resize based on type - LARGER for better quality!
                        if image_type == "icon":
                            # Make icons nice and large (80x80 instead of 60x60)
                            img = img.resize((80, 80), Image.Resampling.LANCZOS)
                        else:
                            # Cover - maintain aspect ratio
                            img.thumbnail((230, 345), Image.Resampling.LANCZOS)
                        
                        photo = ImageTk.PhotoImage(img)
                        self.image_cache[cache_key] = photo
                        print(f"✓ Successfully loaded HIGH-QUALITY image for '{game_name}'")
                        return photo
                        
                except Exception as e:
                    print(f"  ✗ Failed: {str(e)[:50]}")
                    continue
            
            # No images worked
            print(f"✗ All image sources failed for '{game_name}'")
            return None
            
        except Exception as e:
            print(f"✗ Error in fetch_game_image for '{game_name}': {e}")
            return None

    # ---------- scanning / UI helpers ----------
    def scan(self):
        self.status.config(text="Scanning all drives for games...", fg="#60a5fa")
        self.root.update()
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self):
        # Preserve manually added games (those with "Other" platform)
        manual_games = [g for g in self.games if g.platform == "Other"]
        
        # Scan for new games
        scanned_games = self.scanner.scan_all()
        
        # Merge manual games with scanned games (avoid duplicates by name)
        scanned_names = {g.name.lower() for g in scanned_games}
        for manual_game in manual_games:
            if manual_game.name.lower() not in scanned_names:
                scanned_games.append(manual_game)
        
        self.games = scanned_games
        self.save_cache()
        gc.collect()
        self.root.after(0, self._finish_scan)

    def _finish_scan(self):
        self.filtered = self.games.copy()
        manual_count = len([g for g in self.games if g.platform == "Other"])
        if manual_count > 0:
            self.status.config(text=f"Found {len(self.games)} games ({manual_count} manually added)", fg="#10b981")
        else:
            self.status.config(text=f"Found {len(self.games)} games across all platforms", fg="#10b981")
        self.display()
        # Auto-start monitor after scan if Twitch is authenticated
        self.root.after(500, self.auto_start_monitor)

    def filter(self):
        search = self.search_var.get().lower().strip()
        platform = self.platform_var.get()
        
        # If no games loaded yet, show a helpful message
        if not self.games:
            self.status.config(text="No games loaded - please scan first!", fg="#f59e0b")
            self.filtered = []
            self.display()
            return
        
        # Apply filters
        self.filtered = [g for g in self.games if search in g.name.lower() and (platform == "All Platforms" or g.platform == platform)]
        
        # Update status with search results
        if search or platform != "All Platforms":
            total = len(self.games)
            found = len(self.filtered)
            if found == 0:
                self.status.config(text=f"No games match your search (0/{total})", fg="#f59e0b")
            else:
                self.status.config(text=f"Showing {found} of {total} games", fg="#60a5fa")
        else:
            self.status.config(text=f"Showing all {len(self.games)} games", fg="#10b981")
        
        self.display()

    def display(self):
        for w in self.games_frame.winfo_children():
            w.destroy()
        # Don't clear image_cache here - keep images cached
        gc.collect()
        
        if not self.filtered:
            empty_frame = tk.Frame(self.games_frame, bg=self.colors['bg_dark'])
            empty_frame.pack(expand=True, fill="both", pady=100)
            
            # Smooth empty state
            tk.Label(empty_frame, text="No games found", font=("Segoe UI", 24, "bold"),
                    bg=self.colors['bg_dark'], fg=self.colors['text_primary']).pack(pady=(0, 12))
            tk.Label(empty_frame, text="Click 'Scan' to discover your games",
                    font=("Segoe UI", 12), bg=self.colors['bg_dark'],
                    fg=self.colors['text_secondary']).pack()
            return
        
        if self.view_mode.get() == "grid":
            self.display_grid()
        else:
            self.display_list()
    
    def show_modern_dialog(self, title, message, dialog_type="info", callback=None):
        """Create a smooth modern custom dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("500x300")
        dialog.resizable(False, False)
        dialog.configure(bg=self.colors['bg_dark'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Colors based on type (no emojis)
        type_colors = {
            "info": self.colors['accent_blue'],
            "warning": self.colors['accent_orange'],
            "error": self.colors['accent_red'],
            "success": self.colors['accent_green'],
            "question": self.colors['accent_purple']
        }
        
        accent_color = type_colors.get(dialog_type, type_colors["info"])
        
        # Smooth header with accent color
        header = tk.Frame(dialog, bg=accent_color, height=90)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(header, text=title, font=("Segoe UI", 18, "bold"),
                bg=accent_color, fg=self.colors['text_primary']).pack(expand=True)
        
        # Content area
        content = tk.Frame(dialog, bg=self.colors['bg_dark'])
        content.pack(fill="both", expand=True, padx=40, pady=30)
        
        tk.Label(content, text=message, font=("Segoe UI", 11),
                bg=self.colors['bg_dark'], fg=self.colors['text_secondary'],
                wraplength=420, justify="center").pack()
        
        # Button frame
        btn_frame = tk.Frame(dialog, bg=self.colors['bg_dark'])
        btn_frame.pack(pady=(0, 25))
        
        if dialog_type == "question":
            # Yes/No buttons
            def on_yes():
                dialog.destroy()
                if callback:
                    callback(True)
            
            def on_no():
                dialog.destroy()
                if callback:
                    callback(False)
            
            tk.Button(btn_frame, text="Yes", command=on_yes,
                     font=("Segoe UI", 11, "bold"), bg=self.colors['accent_green'],
                     fg=self.colors['text_primary'], relief="flat", padx=35, pady=12,
                     cursor="hand2", borderwidth=0).pack(side="left", padx=6)
            
            tk.Button(btn_frame, text="No", command=on_no,
                     font=("Segoe UI", 11), bg=self.colors['bg_card'],
                     fg=self.colors['text_primary'], relief="flat", padx=35, pady=12,
                     cursor="hand2", borderwidth=0).pack(side="left", padx=6)
        else:
            # OK button
            tk.Button(btn_frame, text="OK", command=dialog.destroy,
                     font=("Segoe UI", 11, "bold"), bg=accent_color,
                     fg=self.colors['text_primary'], relief="flat", padx=45, pady=12,
                     cursor="hand2", borderwidth=0).pack()
        
        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
    
    def display_grid(self):
        """Display games in grid view with smooth, rounded card styling"""
        # Calculate columns based on window width
        cols = 5  # Default 5 columns
        
        platform_colors = {
            "Steam": "#2563eb",
            "Epic Games": "#0ea5e9",
            "GOG": "#a855f7",
            "Riot Games": "#ef4444",
            "Xbox": "#10b981",
            "Battle.net": "#0891b2",
            "Other": "#6b7280"
        }
        
        row_frame = None
        for idx, game in enumerate(self.filtered):
            if idx % cols == 0:
                row_frame = tk.Frame(self.games_frame, bg=self.colors['bg_dark'])
                row_frame.pack(fill="x", pady=10, padx=10)
            
            # Card container with smooth, soft shadow effect
            card_container = tk.Frame(row_frame, bg=self.colors['bg_dark'])
            card_container.pack(side="left", padx=10, pady=10)
            
            # Main card with smooth, rounded styling (no harsh borders)
            card = tk.Frame(card_container, bg=self.colors['bg_card'], 
                           highlightthickness=0,
                           width=230, height=370)
            card.pack()
            card.pack_propagate(False)
            
            # Image container with smooth background
            img_frame = tk.Frame(card, bg=self.colors['bg_hover'], width=220, height=310)
            img_frame.pack(padx=5, pady=5)
            img_frame.pack_propagate(False)
            
            # Try to fetch cover with proper caching
            def load_cover(g=game, frame=img_frame):
                try:
                    photo = self.fetch_game_image(g.name, "cover")
                    if photo:
                        # Schedule UI update on main thread
                        self.root.after(0, lambda p=photo, f=frame: self._update_cover(p, f))
                    else:
                        # Fallback: show game name with smooth gradient background
                        self.root.after(0, lambda: self._create_fallback_cover(g, frame))
                except Exception:
                    # On error, create fallback
                    self.root.after(0, lambda: self._create_fallback_cover(g, frame))
            
            # Load image in background
            threading.Thread(target=load_cover, daemon=True).start()
            
            # Info section below image
            info_frame = tk.Frame(card, bg=self.colors['bg_card'])
            info_frame.pack(fill="x", padx=10, pady=(0, 10))
            
            # Game name (truncated if too long)
            name_text = game.name[:30] + "..." if len(game.name) > 30 else game.name
            name_label = tk.Label(info_frame, text=name_text,
                                 font=("Segoe UI", 10, "bold"), bg=self.colors['bg_card'],
                                 fg=self.colors['text_primary'], anchor="w")
            name_label.pack(fill="x", pady=(0, 6))
            
            # Platform badge with smooth rounded color
            accent_color = platform_colors.get(game.platform, self.colors['border'])
            badge = tk.Label(info_frame, text=game.platform, font=("Segoe UI", 8, "bold"),
                           bg=accent_color, fg=self.colors['text_primary'], 
                           padx=10, pady=4)
            badge.pack(anchor="w")
            
            # Add smooth hover effects to card
            def on_enter(e, c=card):
                c.config(bg=self.colors['bg_hover'])
                info_frame.config(bg=self.colors['bg_hover'])
                name_label.config(bg=self.colors['bg_hover'])
            
            def on_leave(e, c=card):
                c.config(bg=self.colors['bg_card'])
                info_frame.config(bg=self.colors['bg_card'])
                name_label.config(bg=self.colors['bg_card'])
            
            card.bind("<Enter>", on_enter)
            card.bind("<Leave>", on_leave)
    
    def _update_cover(self, photo, frame):
        """Update cover image on main thread"""
        for widget in frame.winfo_children():
            widget.destroy()
        label = tk.Label(frame, image=photo, bg=self.colors['bg_hover'])
        label.pack(expand=True)
    
    def _create_fallback_cover(self, game, frame):
        """Create fallback cover when image fetch fails"""
        for widget in frame.winfo_children():
            widget.destroy()
        
        # Create a nice gradient-like fallback with game initial
        fallback_frame = tk.Frame(frame, bg=self.colors['bg_medium'])
        fallback_frame.pack(expand=True, fill="both")
        
        # Game initial in large font
        initial = tk.Label(fallback_frame, text=game.name[0].upper(),
                          font=("Segoe UI", 72, "bold"),
                          bg=self.colors['bg_medium'], fg=self.colors['accent_purple'])
        initial.pack(expand=True)
        
        # Game name at bottom
        name_text = game.name[:20] + "..." if len(game.name) > 20 else game.name
        name_label = tk.Label(fallback_frame, text=name_text,
                             font=("Segoe UI", 10, "bold"), 
                             bg=self.colors['bg_medium'],
                             fg=self.colors['text_primary'], wraplength=190)
        name_label.pack(side="bottom", pady=10)
    
    def display_list(self):
        """Display games in list view with smooth, rounded styling and HIGH-QUALITY icons"""
        platform_colors = {
            "Steam": "#2563eb",
            "Epic Games": "#0ea5e9",
            "GOG": "#a855f7",
            "Riot Games": "#ef4444",
            "Xbox": "#10b981",
            "Battle.net": "#0891b2",
            "Other": "#6b7280"
        }
        
        for game in self.filtered:
            # Outer container for smooth shadow effect
            card = tk.Frame(self.games_frame, bg=self.colors['bg_dark'])
            card.pack(fill="x", pady=4, padx=6)
            
            # Inner card with smooth rounded feel (no harsh borders)
            card_inner = tk.Frame(card, bg=self.colors['bg_card'], 
                                 highlightthickness=0)
            card_inner.pack(fill="x")
            
            # Platform accent bar (smooth, slightly thicker)
            accent_color = platform_colors.get(game.platform, self.colors['border'])
            accent = tk.Frame(card_inner, bg=accent_color, width=5)
            accent.pack(side="left", fill="y")
            
            # Icon container - LARGER for better quality icons (80x80)
            icon_frame = tk.Frame(card_inner, bg=self.colors['bg_hover'], width=80, height=80)
            icon_frame.pack(side="left", padx=18, pady=18)
            icon_frame.pack_propagate(False)
            
            # Try to fetch HIGH-QUALITY icon with proper caching
            def load_icon(g=game, frame=icon_frame, accent_col=accent_color):
                try:
                    photo = self.fetch_game_image(g.name, "icon")
                    if photo:
                        # Schedule UI update on main thread
                        self.root.after(0, lambda p=photo, f=frame: self._update_icon(p, f))
                    else:
                        # Fallback: show first letter with smooth background
                        self.root.after(0, lambda: self._create_fallback_icon(g, frame, accent_col))
                except Exception as e:
                    # On error, create fallback
                    self.root.after(0, lambda: self._create_fallback_icon(g, frame, accent_col))
            
            # Load icon in background
            threading.Thread(target=load_icon, daemon=True).start()
            
            # Content section
            content = tk.Frame(card_inner, bg=self.colors['bg_card'])
            content.pack(side="left", fill="both", expand=True, padx=24, pady=18)
            
            # Game name with smooth, larger font
            tk.Label(content, text=game.name, font=("Segoe UI", 13, "bold"),
                    bg=self.colors['bg_card'], fg=self.colors['text_primary'],
                    anchor="w").pack(anchor="w")
            
            # Details row
            details = tk.Frame(content, bg=self.colors['bg_card'])
            details.pack(anchor="w", pady=(8, 0))
            
            # Platform badge with smooth rounded corners effect
            badge = tk.Label(details, text=f"  {game.platform}  ", font=("Segoe UI", 9, "bold"),
                           bg=accent_color, fg=self.colors['text_primary'],
                           padx=12, pady=5)
            badge.pack(side="left", padx=(0, 12))
            
            # Path info (shortened)
            path_text = game.path if len(game.path) < 60 else "..." + game.path[-57:]
            tk.Label(details, text=path_text, font=("Segoe UI", 9),
                    bg=self.colors['bg_card'], fg=self.colors['text_secondary']).pack(side="left")
            
            # Remove button with smooth styling
            remove_btn = tk.Button(card_inner, text="✕", command=lambda g=game: self.remove(g),
                                  font=("Segoe UI", 12, "bold"), bg=self.colors['accent_red'],
                                  fg=self.colors['text_primary'], activebackground="#dc2626",
                                  relief="flat", padx=18, pady=12, cursor="hand2", borderwidth=0)
            remove_btn.pack(side="right", padx=18, pady=15)
            
            # Add smooth hover effect
            def on_enter(e):
                card_inner.config(bg=self.colors['bg_hover'])
                content.config(bg=self.colors['bg_hover'])
                for child in details.winfo_children():
                    if isinstance(child, tk.Label) and child != badge:
                        child.config(bg=self.colors['bg_hover'])
            
            def on_leave(e):
                card_inner.config(bg=self.colors['bg_card'])
                content.config(bg=self.colors['bg_card'])
                for child in details.winfo_children():
                    if isinstance(child, tk.Label) and child != badge:
                        child.config(bg=self.colors['bg_card'])
            
            card_inner.bind("<Enter>", on_enter)
            card_inner.bind("<Leave>", on_leave)
    
    def _update_icon(self, photo, frame):
        """Update icon on main thread"""
        for widget in frame.winfo_children():
            widget.destroy()
        label = tk.Label(frame, image=photo, bg=self.colors['bg_hover'])
        label.pack(expand=True)
    
    def _create_fallback_icon(self, game, frame, accent_color):
        """Create fallback icon when image fetch fails - larger size for better appearance"""
        for widget in frame.winfo_children():
            widget.destroy()
        fallback = tk.Label(frame, text=game.name[0].upper(),
                          font=("Segoe UI", 24, "bold"),  # Larger font for 80x80 icon
                          bg=accent_color, fg=self.colors['text_primary'])
        fallback.pack(expand=True, fill="both")

    def remove(self, game):
        def on_confirm(result):
            if result:
                self.scanner.exclude(game.name)
                self.games = [g for g in self.games if g.name != game.name]
                self.filtered = [g for g in self.filtered if g.name != game.name]
                self.save_cache()
                self.display()
                self.status.config(text=f"✓ Removed {game.name}", fg=self.colors['accent_orange'])
        
        self.show_modern_dialog(
            "Remove Game",
            f"Are you sure you want to remove '{game.name}' from your library?",
            "question",
            on_confirm
        )

    def auto_start_monitor(self):
        """Automatically start monitor if Twitch is authenticated (always on)"""
        # Auto-start if:
        # 1. Twitch is authenticated and enabled
        # 2. Games have been loaded (from cache or scan)
        # 3. Monitor is not already running
        if self.twitch.is_authenticated() and self.games and not (self.monitor and self.monitor.active):
            try:
                self.monitor = GameMonitor(self.games, self.twitch, self.update_status)
                self.monitor.start()
                
                # Show different message based on startup mode
                if STARTUP_MODE:
                    self.status.config(text="● Auto-monitoring active (Twitch authenticated)", 
                                     fg=self.colors['accent_green'])
                else:
                    self.status.config(text="● Monitoring active - Game launches will update Twitch", 
                                     fg=self.colors['accent_green'])
            except Exception as e:
                # Silently fail if auto-start doesn't work
                pass

    def update_status(self, text, color):
        self.root.after(0, lambda: self.status.config(text=text, fg=color))

    # ---------- Twitch settings UI ----------
    def twitch_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Twitch Settings")
        dialog.geometry("600x500")
        dialog.resizable(False, False)
        dialog.configure(bg=self.colors['bg_dark'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Smooth header with accent color
        header = tk.Frame(dialog, bg="#9146ff", height=100)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(header, text="Twitch Integration", font=("Segoe UI", 20, "bold"),
                bg="#9146ff", fg=self.colors['text_primary']).pack(expand=True)
        
        # Description
        desc_frame = tk.Frame(dialog, bg=self.colors['bg_dark'])
        desc_frame.pack(pady=20)
        tk.Label(desc_frame, 
                text="Automatically changes your stream category when you launch games",
                font=("Segoe UI", 11), bg=self.colors['bg_dark'],
                fg=self.colors['text_secondary'], justify="center",
                wraplength=520).pack()
        
        # Form container with smooth styling
        form_container = tk.Frame(dialog, bg=self.colors['bg_card'],
                                 highlightthickness=0)
        form_container.pack(pady=25, padx=50, fill="x")
        
        form = tk.Frame(form_container, bg=self.colors['bg_card'])
        form.pack(padx=30, pady=30)
        
        # Channel name field
        tk.Label(form, text="Channel Name:", bg=self.colors['bg_card'],
                fg=self.colors['text_primary'], font=("Segoe UI", 11, "bold")).grid(
                row=0, column=0, sticky="w", pady=(0, 10))
        
        channel_entry = tk.Entry(form, font=("Segoe UI", 12),
                                bg=self.colors['bg_medium'],
                                fg=self.colors['text_primary'], width=40,
                                borderwidth=0, relief="flat",
                                highlightthickness=0,
                                insertbackground=self.colors['accent_blue'])
        channel_entry.grid(row=1, column=0, pady=(0, 25), ipady=12, padx=5)
        channel_entry.insert(0, self.twitch.config.get('channel_name', ''))
        
        # Enable checkbox with smooth styling
        enabled_var = tk.BooleanVar(value=self.twitch.config.get('enabled', False))
        check_frame = tk.Frame(form, bg=self.colors['bg_card'])
        check_frame.grid(row=2, column=0, pady=20, sticky="w")
        
        tk.Checkbutton(check_frame, text="Enable automatic category changes",
                      variable=enabled_var, font=("Segoe UI", 10),
                      bg=self.colors['bg_card'], fg=self.colors['text_primary'],
                      selectcolor=self.colors['bg_medium'],
                      activebackground=self.colors['bg_card'],
                      activeforeground=self.colors['text_primary'],
                      cursor="hand2").pack(side="left")
        
        # Buttons with smooth styling
        btn_frame = tk.Frame(dialog, bg=self.colors['bg_dark'])
        btn_frame.pack(pady=30)

        def authenticate():
            channel = channel_entry.get().strip()
            if not channel:
                self.show_modern_dialog(
                    "Missing Information",
                    "Please enter your Twitch channel name!",
                    "warning"
                )
                return
            self.twitch.update_config(channel, True)
            auth_btn.config(text="Authenticating...", state="disabled", bg=self.colors['bg_medium'])
            dialog.update()
            
            def do_auth():
                ok = self.twitch.authenticate() and self.twitch.get_user_id()
                self.root.after(0, lambda: auth_btn.config(
                    text="Authenticate", state="normal", bg="#9146ff"))
                if ok:
                    self.root.after(0, lambda: self.show_modern_dialog(
                        "Success",
                        "Successfully authenticated with Twitch!",
                        "success"
                    ))
                    # Auto-start monitoring after successful authentication
                    self.root.after(100, self.auto_start_monitor)
                    dialog.destroy()
                else:
                    self.root.after(0, lambda: self.show_modern_dialog(
                        "Authentication Failed",
                        "Could not authenticate with Twitch. Please try again.",
                        "error"
                    ))

            threading.Thread(target=do_auth, daemon=True).start()

        auth_btn = tk.Button(btn_frame, text="Authenticate", command=authenticate,
                           font=("Segoe UI", 11, "bold"), bg="#9146ff",
                           fg=self.colors['text_primary'], relief="flat",
                           padx=28, pady=14, cursor="hand2", borderwidth=0)
        auth_btn.pack(side="left", padx=6)

        def save():
            self.twitch.update_config(channel_entry.get().strip(), enabled_var.get())
            self.show_modern_dialog(
                "Settings Saved",
                "Your Twitch settings have been saved successfully!",
                "success"
            )
            dialog.destroy()

        tk.Button(btn_frame, text="Save", command=save,
                 font=("Segoe UI", 11, "bold"), bg=self.colors['accent_blue'],
                 fg=self.colors['text_primary'], relief="flat",
                 padx=32, pady=14, cursor="hand2", borderwidth=0).pack(side="left", padx=6)
        
        tk.Button(btn_frame, text="Cancel", command=dialog.destroy,
                 font=("Segoe UI", 11), bg=self.colors['bg_card'],
                 fg=self.colors['text_primary'], relief="flat",
                 padx=32, pady=14, cursor="hand2", borderwidth=0).pack(side="left", padx=6)
        
        # Footer hint (no emoji)
        tk.Label(dialog, text="Click 'Authenticate' to login with Twitch (opens browser)",
                font=("Segoe UI", 9), bg=self.colors['bg_dark'],
                fg=self.colors['text_secondary']).pack(pady=(0, 20))

    def add_manual_game(self):
        """Manual game adder dialog"""
        from tkinter import filedialog
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Game Manually")
        dialog.geometry("600x400")
        dialog.resizable(False, False)  # Disable resizing
        dialog.configure(bg="#0f1629")
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text="➕ Add Game Manually", font=("Segoe UI", 18, "bold"), bg="#0f1629", fg="#8b5cf6").pack(pady=20)
        tk.Label(dialog, text="Add a game that wasn't detected by the automatic scan", font=("Segoe UI", 10), bg="#0f1629", fg="#9ca3af", justify="center", wraplength=450).pack(pady=10)
        
        form = tk.Frame(dialog, bg="#0f1629")
        form.pack(pady=20, padx=40)
        
        # Game name input
        tk.Label(form, text="Game Name:", bg="#0f1629", fg="#ffffff", font=("Segoe UI", 11)).grid(row=0, column=0, sticky="w", pady=15)
        name_entry = tk.Entry(form, font=("Segoe UI", 11), bg="#1a1f3a", fg="#ffffff", width=30, borderwidth=0, relief="flat")
        name_entry.grid(row=0, column=1, pady=15, ipady=8, padx=10)
        
        # Game folder input
        tk.Label(form, text="Game Folder:", bg="#0f1629", fg="#ffffff", font=("Segoe UI", 11)).grid(row=1, column=0, sticky="w", pady=15)
        folder_frame = tk.Frame(form, bg="#0f1629")
        folder_frame.grid(row=1, column=1, pady=15)
        
        folder_var = tk.StringVar()
        folder_entry = tk.Entry(folder_frame, textvariable=folder_var, font=("Segoe UI", 10), bg="#1a1f3a", fg="#ffffff", borderwidth=0, relief="flat", state="readonly", width=28)
        folder_entry.pack(side="left", ipady=8, padx=(0, 5))
        
        def browse_folder():
            folder = filedialog.askdirectory(title="Select Game Folder")
            if folder:
                folder_var.set(folder)
        
        tk.Button(folder_frame, text="Browse", command=browse_folder, font=("Segoe UI", 9, "bold"), bg="#3b82f6", fg="#ffffff", relief="flat", padx=15, pady=6, cursor="hand2", borderwidth=0).pack(side="right")
        
        btn_frame = tk.Frame(dialog, bg="#0f1629")
        btn_frame.pack(pady=20)
        
        def add_game():
            name = name_entry.get().strip()
            folder = folder_var.get().strip()
            
            if not name:
                messagebox.showwarning("Missing Info", "Please enter a game name!")
                return
            
            if not folder:
                messagebox.showwarning("Missing Info", "Please select a game folder!")
                return
            
            if not os.path.exists(folder):
                messagebox.showerror("Invalid Folder", "The selected folder doesn't exist!")
                return
            
            # Look for .exe files in the folder
            exe_found = None
            try:
                folder_path = Path(folder)
                skip_patterns = ['unins', 'install', 'setup', 'crash', 'report', 'redist', 'dotnet', 'directx', 'vcredist', 'unity', 'unreal']
                
                # First check root folder
                exes = [e for e in folder_path.glob("*.exe") if not any(skip in e.stem.lower() for skip in skip_patterns)]
                if exes:
                    exe_found = exes[0]
                else:
                    # Search subdirectories (max depth 3)
                    for root, dirs, files in os.walk(folder_path):
                        depth = root[len(str(folder_path)):].count(os.sep)
                        if depth > 3:
                            dirs.clear()
                            continue
                        exe_files = [f for f in files if f.endswith('.exe') and not any(skip in f.lower() for skip in skip_patterns)]
                        if exe_files:
                            exe_found = Path(root) / exe_files[0]
                            break
            except Exception:
                pass
            
            # Add the game with "Other" category
            new_game = Game(name, folder, "Other", str(exe_found) if exe_found else "")
            self.games.append(new_game)
            self.filtered.append(new_game)
            self.save_cache()
            self.display()
            
            # Update monitor if active
            if self.monitor and self.monitor.active:
                self.monitor.games = self.games
                self.monitor.build_exe_map()
            
            self.status.config(text=f"Added '{name}' to your library", fg="#10b981")
            dialog.destroy()
        
        tk.Button(btn_frame, text="➕ Add Game", command=add_game, font=("Segoe UI", 11, "bold"), bg="#8b5cf6", fg="#ffffff", relief="flat", padx=25, pady=10, cursor="hand2", borderwidth=0).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Cancel", command=dialog.destroy, font=("Segoe UI", 11), bg="#374151", fg="#ffffff", relief="flat", padx=30, pady=10, cursor="hand2", borderwidth=0).pack(side="left", padx=5)

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
                        self.status.config(text=f"Restored {name} - please rescan", fg="#10b981")
                        dialog.destroy()
                        self.show_excluded_games()
            tk.Button(item_frame, text="↩️ Restore", command=restore_game, font=("Segoe UI", 9, "bold"), bg="#10b981", fg="#ffffff", activebackground="#059669", relief="flat", padx=15, pady=6, cursor="hand2", borderwidth=0).pack(side="right", padx=10)
        tk.Button(dialog, text="Close", command=dialog.destroy, font=("Segoe UI", 11, "bold"), bg="#374151", fg="#ffffff", relief="flat", padx=30, pady=10, cursor="hand2", borderwidth=0).pack(pady=(0, 20))

    def save_cache(self):
        try:
            # --- 'icon' field removed from cache data ---
            data = [{'name': g.name, 'path': g.path, 'platform': g.platform, 'exe_path': g.exe_path} for g in self.games]
            with open(GAMES_CACHE_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def load_cache(self):
        try:
            if GAMES_CACHE_FILE.exists():
                with open(GAMES_CACHE_FILE, 'r') as f:
                    data = json.load(f)
                    # --- 'icon' field removed from cache loading ---
                    self.games = [Game(g['name'], g['path'], g['platform'], g.get('exe_path', '')) for g in data]
                    self.filtered = self.games.copy()
                    if self.games:
                        self.display()
                        self.status.config(text=f"Loaded {len(self.games)} games from cache", fg="#10b981")
        except Exception:
            pass

    # ---------- tray / icon (MODIFIED FOR PERSISTENT TRAY) ----------
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

    def start_persistent_tray(self):
        """Creates and runs the persistent tray icon in a thread."""
        if not TRAY_AVAILABLE or pystray is None or item is None:
            return

        image = self.create_tray_icon_image()
        menu = pystray.Menu(
            item('Show', self.show_window, default=True),
            item('Monitor Status', self.show_monitor_status),
            pystray.Menu.SEPARATOR,
            item('Exit', self.quit_app)
        )
        
        try:
            self.tray_icon = pystray.Icon("twitch_game_changer", image, "Twitch Game Changer", menu)
        except Exception:
            self.tray_icon = pystray.Icon("twitch_game_changer", None, "Twitch Game Changer", menu)

        def start_tray_loop():
            # keep trying to run the tray icon; if run() exits due to Explorer restart, recreate & rerun
            while not self.app_is_closing:
                try:
                    # run will block until stop(); if system explorer restarts it may raise/exit
                    self.tray_icon.run() # type: ignore
                    # if run returns normally (stop called), break
                    break
                except Exception:
                    # short pause and recreate the icon object if app is not closing
                    time.sleep(1.0)
                    if self.app_is_closing:
                        break
                    try:
                        image2 = self.create_tray_icon_image()
                        self.tray_icon = pystray.Icon("twitch_game_changer", image2, "Twitch Game Changer", menu) # type: ignore
                    except Exception:
                        # if recreation fails, sleep and retry
                        time.sleep(1.0)
                        continue

        threading.Thread(target=start_tray_loop, daemon=True).start()

    def minimize_to_tray(self):
        """Hides the window. Called by WM_DELETE_WINDOW."""
        self.is_minimized_to_tray = True
        self.root.withdraw()

    def show_window(self, icon=None, item=None):
        """Shows the window. Called by tray icon menu."""
        self.is_minimized_to_tray = False
        # --- No longer stops the icon ---
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
        """Cleanly exits the entire application."""
        self.app_is_closing = True # Signal tray thread to exit
        
        try:
            if self.monitor and self.monitor.active:
                self.monitor.stop()
        except Exception:
            pass
        
        try:
            if self.tray_icon:
                self.tray_icon.stop()
        except Exception:
            pass
        
        self.root.after(0, self.root.destroy)

    def check_for_updates_background(self):
        """Check for updates in background without blocking UI"""
        def check():
            try:
                # Only check if enough time has passed
                if not self.updater.should_check_for_updates():
                    return
                
                update_info = self.updater.check_for_updates()
                self.updater.save_last_check()
                
                if update_info.get('available'):
                    # Update available - show indicator
                    def show_indicator():
                        self.update_indicator.config(text="🔔 Update Available!", fg="#10b981")
                        self.pending_update = update_info # type: ignore
                    self.root.after(0, show_indicator)
            except Exception:
                pass
        
        # Run in background thread
        threading.Thread(target=check, daemon=True).start()
    
    def show_update_dialog(self):
        """Show update dialog with release notes and install option"""
        # Check if there's a pending update
        if not hasattr(self, 'pending_update'):
            # Manual check
            self.status.config(text="Checking for updates...", fg="#60a5fa")
            
            def check_and_show():
                update_info = self.updater.check_for_updates()
                
                def show_result():
                    if update_info.get('available'):
                        self.pending_update = update_info # type: ignore
                        self._display_update_dialog(update_info)
                    else:
                        self.status.config(text=f"You're on the latest version (v{APP_VERSION})", fg="#10b981")
                        messagebox.showinfo("No Updates", f"You're already running the latest version!\n\nCurrent version: v{APP_VERSION}")
                
                self.root.after(0, show_result)
            
            threading.Thread(target=check_and_show, daemon=True).start()
        else:
            self._display_update_dialog(self.pending_update) # type: ignore
    
    def _display_update_dialog(self, update_info):
        """Display the actual update dialog with smooth styling"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Update Available")
        dialog.geometry("750x750")
        dialog.resizable(False, False)
        dialog.configure(bg=self.colors['bg_dark'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Smooth header with accent color
        header = tk.Frame(dialog, bg=self.colors['accent_green'], height=110)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(header, text="Update Available", font=("Segoe UI", 22, "bold"),
                bg=self.colors['accent_green'], fg=self.colors['text_primary']).pack(expand=True)
        
        # Version info container
        version_container = tk.Frame(dialog, bg=self.colors['bg_card'],
                                    highlightthickness=0)
        version_container.pack(pady=25, padx=50, fill="x")
        
        version_frame = tk.Frame(version_container, bg=self.colors['bg_card'])
        version_frame.pack(pady=20)
        
        # Current and new version side by side
        current_frame = tk.Frame(version_frame, bg=self.colors['bg_card'])
        current_frame.pack(side="left", padx=25)
        tk.Label(current_frame, text="Current Version",
                font=("Segoe UI", 10), bg=self.colors['bg_card'],
                fg=self.colors['text_secondary']).pack()
        tk.Label(current_frame, text=f"v{APP_VERSION}",
                font=("Segoe UI", 16, "bold"), bg=self.colors['bg_card'],
                fg=self.colors['text_primary']).pack()
        
        tk.Label(version_frame, text="→", font=("Segoe UI", 20),
                bg=self.colors['bg_card'], fg=self.colors['accent_blue']).pack(side="left", padx=15)
        
        new_frame = tk.Frame(version_frame, bg=self.colors['bg_card'])
        new_frame.pack(side="left", padx=25)
        tk.Label(new_frame, text="New Version",
                font=("Segoe UI", 10), bg=self.colors['bg_card'],
                fg=self.colors['text_secondary']).pack()
        tk.Label(new_frame, text=f"v{update_info['version']}",
                font=("Segoe UI", 16, "bold"), bg=self.colors['bg_card'],
                fg=self.colors['accent_green']).pack()
        
        # Release notes section
        tk.Label(dialog, text="What's New", font=("Segoe UI", 14, "bold"),
                bg=self.colors['bg_dark'], fg=self.colors['text_primary']).pack(pady=(20, 12))
        
        notes_container = tk.Frame(dialog, bg=self.colors['bg_card'],
                                  highlightthickness=0)
        notes_container.pack(fill="both", expand=True, padx=50, pady=(0, 25))
        
        notes_text = tk.Text(notes_container, font=("Segoe UI", 10),
                           bg=self.colors['bg_card'], fg=self.colors['text_secondary'],
                           wrap="word", relief="flat", padx=18, pady=18, height=10)
        notes_scrollbar = tk.Scrollbar(notes_container, command=notes_text.yview,
                                      bg=self.colors['bg_dark'],
                                      troughcolor=self.colors['bg_medium'],
                                      activebackground=self.colors['text_secondary'])
        notes_text.config(yscrollcommand=notes_scrollbar.set)
        notes_scrollbar.pack(side="right", fill="y")
        notes_text.pack(side="left", fill="both", expand=True)
        
        # Insert release notes
        release_notes = update_info.get('release_notes', 'No release notes available.')
        notes_text.insert("1.0", release_notes)
        notes_text.config(state="disabled")
        
        # Status label
        status_label = tk.Label(dialog, text="", font=("Segoe UI", 10),
                               bg=self.colors['bg_dark'], fg=self.colors['accent_blue'])
        status_label.pack(pady=12)
        
        # Buttons with smooth styling
        btn_frame = tk.Frame(dialog, bg=self.colors['bg_dark'])
        btn_frame.pack(pady=25)
        
        def install_update():
            if not update_info.get('download_url'):
                self.show_modern_dialog(
                    "Error",
                    "No download URL available for this update.",
                    "error"
                )
                return
            
            install_btn.config(state="disabled", bg=self.colors['bg_medium'])
            later_btn.config(state="disabled", bg=self.colors['bg_medium'])
            
            def update_callback(message):
                status_label.config(text=message)
            
            def do_install():
                success = self.updater.download_and_install_update(
                    update_info['download_url'], 
                    callback=update_callback
                )
                
                if success:
                    def close_app():
                        status_label.config(text="Update will install shortly...",
                                          fg=self.colors['accent_green'])
                        self.root.after(2000, lambda: self.quit_app())
                    self.root.after(0, close_app)
                else:
                    def re_enable():
                        install_btn.config(state="normal", bg=self.colors['accent_green'])
                        later_btn.config(state="normal", bg=self.colors['bg_card'])
                        status_label.config(text="Update failed. Please try again.",
                                          fg=self.colors['accent_red'])
                    self.root.after(0, re_enable)
            
            threading.Thread(target=do_install, daemon=True).start()
        
        install_btn = tk.Button(btn_frame, text="Install Update", command=install_update,
                               font=("Segoe UI", 12, "bold"), bg=self.colors['accent_green'],
                               fg=self.colors['text_primary'], activebackground="#059669",
                               relief="flat", padx=32, pady=14, cursor="hand2", borderwidth=0)
        install_btn.pack(side="left", padx=7)
        
        later_btn = tk.Button(btn_frame, text="Later", command=dialog.destroy,
                             font=("Segoe UI", 11), bg=self.colors['bg_card'],
                             fg=self.colors['text_primary'], relief="flat",
                             padx=32, pady=14, cursor="hand2", borderwidth=0)
        later_btn.pack(side="left", padx=7)
        
        # View on GitHub button
        if update_info.get('html_url'):
            def open_github():
                import webbrowser
                webbrowser.open(update_info['html_url'])
            
            tk.Button(btn_frame, text="View on GitHub", command=open_github,
                     font=("Segoe UI", 10), bg=self.colors['bg_medium'],
                     fg=self.colors['text_secondary'], relief="flat",
                     padx=22, pady=12, cursor="hand2", borderwidth=0).pack(side="left", padx=7)

    def on_closing(self):
        """Fallback for non-tray systems, or if tray fails."""
        if self.monitor and self.monitor.active:
            def on_confirm(result):
                if result:
                    self.monitor.stop() # type: ignore
                    self.root.destroy()
            
            self.show_modern_dialog(
                "Monitor Active",
                "Game monitor is active. Exit anyway?\n\nThis will stop tracking your games.",
                "question",
                on_confirm
            )
        else:
            self.root.destroy()

# Application Entry Point
def main():
    root = tk.Tk()
    app = GUI(root)

    # minimize on startup only if flagged
    if STARTUP_MODE and hasattr(app, "minimize_to_tray"):
        # The tray icon is already running, so just hide the window
        root.after(800, app.minimize_to_tray)

    root.mainloop()

if __name__ == "__main__":
    main()
