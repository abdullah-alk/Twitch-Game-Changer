import os
import json
import winreg
from pathlib import Path
from typing import List, Set, Optional
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import sys
import gc
import base64
import hashlib
import struct

# Lazy imports
pystray = item = None
TRAY_AVAILABLE = False

def init_tray():
    global pystray, item, TRAY_AVAILABLE
    try:
        import pystray
        from pystray import MenuItem as item
        TRAY_AVAILABLE = True
    except: pass

STARTUP_MODE = "--startup" in sys.argv
APP_DATA_DIR = Path(os.getenv('APPDATA', os.path.expanduser('~'))) / "TwitchGameChanger"
APP_DATA_DIR.mkdir(exist_ok=True)
TWITCH_CONFIG_FILE = APP_DATA_DIR / 'twitch_config.json'
EXCLUDED_GAMES_FILE = APP_DATA_DIR / 'excluded_games.json'
GAMES_CACHE_FILE = APP_DATA_DIR / 'games_cache.json'
ICON_CACHE_DIR = APP_DATA_DIR / 'icons'
ICON_CACHE_DIR.mkdir(exist_ok=True)

# Secure token encryption
class TokenEncryption:
    @staticmethod
    def _get_machine_key():
        try:
            import uuid, platform
            machine_id = str(uuid.getnode()) + platform.node()
            return hashlib.sha256(machine_id.encode()).digest()
        except: return hashlib.sha256(b'default_key_fallback').digest()
    
    @staticmethod
    def encrypt(data: str) -> str:
        if not data: return ""
        try:
            from cryptography.fernet import Fernet
            key = base64.urlsafe_b64encode(TokenEncryption._get_machine_key())
            return Fernet(key).encrypt(data.encode()).decode()
        except:
            # Fallback XOR encryption if cryptography not available
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
            # Fallback XOR decryption
            key = TokenEncryption._get_machine_key()
            encrypted = base64.b64decode(data.encode())
            decrypted = bytearray()
            for i, byte in enumerate(encrypted):
                decrypted.append(byte ^ key[i % len(key)])
            return decrypted.decode()

# Icon extraction
class IconExtractor:
    @staticmethod
    def extract_icon(exe_path: str, game_name: str) -> Optional[str]:
        icon_path = ICON_CACHE_DIR / f"{hashlib.md5(game_name.encode()).hexdigest()}.png"
        if icon_path.exists(): return str(icon_path)
        try:
            from PIL import Image
            import win32api, win32con, win32ui, win32gui
            ico_x = win32api.GetSystemMetrics(win32con.SM_CXICON)
            large, small = win32gui.ExtractIconEx(exe_path, 0)
            if not large: return None
            hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
            hbmp = win32ui.CreateBitmap()
            hbmp.CreateCompatibleBitmap(hdc, ico_x, ico_x)
            hdc_mem = hdc.CreateCompatibleDC()
            hdc_mem.SelectObject(hbmp)
            win32gui.DrawIconEx(hdc_mem.GetHandleOutput(), 0, 0, large[0], ico_x, ico_x, 0, None, win32con.DI_NORMAL)
            bmpinfo = hbmp.GetInfo()
            bmpstr = hbmp.GetBitmapBits(True)
            img = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1)
            img.save(icon_path, 'PNG')
            win32gui.DestroyIcon(large[0])
            for i in small: win32gui.DestroyIcon(i)
            gc.collect()
            return str(icon_path)
        except: return None

class Game:
    __slots__ = ['name', 'path', 'platform', 'exe_path', 'icon']
    def __init__(self, name: str, path: str, platform: str, exe_path: str = "", icon: str = ""):
        self.name = name
        self.path = path
        self.platform = platform
        self.exe_path = exe_path or path
        self.icon = icon

class TwitchBot:
    CLIENT_ID = 'll2bpleltqt52whwzu4cidrthdgipj'
    GAME_NAME_MAPPING = {
        'little nightmares enhanced edition': 'Little Nightmares II Enhanced Edition',
        'little nightmares': 'Little Nightmares II Enhanced Edition',
    }
    
    def __init__(self):
        self.config = self._load_config()
        self.access_token = self._decrypt_token(self.config.get('access_token'))
        self.user_id = self.config.get('user_id')
    
    def _load_config(self) -> dict:
        try:
            if TWITCH_CONFIG_FILE.exists():
                with open(TWITCH_CONFIG_FILE, 'r') as f:
                    return json.load(f)
        except: pass
        return {'channel_name': '', 'enabled': False, 'access_token': None, 'user_id': None}
    
    def _save_config(self):
        try:
            cfg = self.config.copy()
            if self.access_token:
                cfg['access_token'] = TokenEncryption.encrypt(self.access_token)
            with open(TWITCH_CONFIG_FILE, 'w') as f:
                json.dump(cfg, f, indent=2)
        except: pass
    
    def _decrypt_token(self, encrypted: Optional[str]) -> Optional[str]:
        return TokenEncryption.decrypt(encrypted) if encrypted else None
    
    def update_config(self, channel: str, enabled: bool):
        self.config['channel_name'] = channel
        self.config['enabled'] = enabled
        self._save_config()
    
    def authenticate(self) -> bool:
        if not self.config.get('channel_name'): return False
        try:
            import requests, webbrowser
            r = requests.post('https://id.twitch.tv/oauth2/device',
                data={'client_id': self.CLIENT_ID, 'scopes': 'channel:manage:broadcast'}, timeout=10)
            if r.status_code != 200: return False
            data = r.json()
            webbrowser.open(data.get('verification_uri', 'https://www.twitch.tv/activate'))
            popup = tk.Toplevel()
            popup.title("Twitch Authentication")
            popup.geometry("420x260")
            popup.configure(bg="#0f1629")
            tk.Label(popup, text="🔐 Twitch Authentication", font=("Segoe UI", 16, "bold"), bg="#0f1629", fg="#ffffff").pack(pady=15)
            tk.Label(popup, text="Enter this code on Twitch:", bg="#0f1629", fg="#9ca3af", font=("Segoe UI", 11)).pack()
            tk.Label(popup, text=data['user_code'], bg="#0f1629", fg="#9146ff", font=("Segoe UI", 34, "bold")).pack(pady=10)
            tk.Label(popup, text="Waiting for authorization...", bg="#0f1629", fg="#60a5fa").pack(pady=10)
            token_data = {}
            def poll():
                start = time.time()
                while time.time() - start < data.get('expires_in', 600):
                    time.sleep(data.get('interval', 5))
                    t = requests.post('https://id.twitch.tv/oauth2/token', data={
                        'client_id': self.CLIENT_ID, 'device_code': data['device_code'],
                        'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'}, timeout=10)
                    if t.status_code == 200:
                        token_data.update(t.json())
                        popup.after(0, popup.destroy)
                        break
            threading.Thread(target=poll, daemon=True).start()
            popup.wait_window()
            if 'access_token' in token_data:
                self.access_token = token_data['access_token']
                self.config['refresh_token'] = token_data.get('refresh_token')
                self._save_config()
                return True
        except: pass
        return False
    
    def refresh_access_token(self) -> bool:
        try:
            import requests
            if not self.config.get('refresh_token'): return False
            r = requests.post('https://id.twitch.tv/oauth2/token', data={
                'grant_type': 'refresh_token', 'refresh_token': self.config['refresh_token'],
                'client_id': self.CLIENT_ID}, timeout=10)
            if r.status_code == 200:
                d = r.json()
                self.access_token = d['access_token']
                if 'refresh_token' in d: self.config['refresh_token'] = d['refresh_token']
                self._save_config()
                return True
        except: pass
        return False
    
    def ensure_token_valid(self) -> bool:
        if not self.access_token:
            return self.refresh_access_token() or self.authenticate()
        try:
            import requests
            r = requests.get('https://api.twitch.tv/helix/users',
                headers={'Authorization': f'Bearer {self.access_token}', 'Client-Id': self.CLIENT_ID}, timeout=6)
            if r.status_code == 200: return True
            elif r.status_code == 401: return self.refresh_access_token() or self.authenticate()
        except: pass
        return False
    
    def get_user_id(self) -> bool:
        if not self.access_token: return False
        try:
            import requests
            r = requests.get('https://api.twitch.tv/helix/users',
                headers={'Authorization': f'Bearer {self.access_token}', 'Client-Id': self.CLIENT_ID}, timeout=10)
            if r.status_code == 200:
                data = r.json().get('data', [])
                if data:
                    self.user_id = data[0].get('id')
                    self.config['user_id'] = self.user_id
                    self._save_config()
                    return True
        except: pass
        return False
    
    def smart_search_game(self, game_name: str, is_game_running=True):
        if not game_name: return "509658"
        mapped_name = self.GAME_NAME_MAPPING.get(game_name.strip().lower(), game_name)
        try:
            import requests
            r = requests.get('https://api.twitch.tv/helix/search/categories',
                params={'query': mapped_name},
                headers={'Authorization': f'Bearer {self.access_token}', 'Client-Id': self.CLIENT_ID}, timeout=6)
            if r.status_code == 200:
                results = r.json().get('data', [])
                if results:
                    lower_query = mapped_name.strip().lower()
                    for item in results:
                        if item.get('name', '').strip().lower() == lower_query: return item['id']
                    return results[0]['id']
            return "66082" if is_game_running else "509658"
        except: return "66082" if is_game_running else "509658"
    
    def change_category(self, game_name: str) -> bool:
        if not self.config.get('enabled') or not self.ensure_token_valid(): return False
        if not self.user_id and not self.get_user_id(): return False
        try:
            import requests
            game_id = "509658" if game_name.lower() == "just chatting" else self.smart_search_game(game_name, bool(game_name))
            r = requests.patch(f'https://api.twitch.tv/helix/channels?broadcaster_id={self.user_id}',
                headers={'Authorization': f'Bearer {self.access_token}', 'Client-Id': self.CLIENT_ID, 'Content-Type': 'application/json'},
                json={'game_id': game_id}, timeout=8)
            return r.status_code == 204
        except: return False

class GameScanner:
    def __init__(self):
        self.excluded = self._load_excluded()
    
    def _load_excluded(self) -> Set[str]:
        try:
            if EXCLUDED_GAMES_FILE.exists():
                with open(EXCLUDED_GAMES_FILE, 'r') as f:
                    return set(json.load(f).get('excluded', []))
        except: pass
        return set()
    
    def _save_excluded(self):
        try:
            with open(EXCLUDED_GAMES_FILE, 'w') as f:
                json.dump({'excluded': list(self.excluded)}, f)
        except: pass
    
    def exclude(self, name: str):
        self.excluded.add(name)
        self._save_excluded()
    
    def unexclude(self, name: str):
        if name in self.excluded:
            self.excluded.remove(name)
            self._save_excluded()
            return True
        return False
    
    def is_excluded(self, name: str) -> bool:
        return name in self.excluded
    
    def get_excluded_list(self) -> List[str]:
        return sorted(list(self.excluded))
    
    def _find_exe(self, gpath: Path, installdir: str, name: str) -> Optional[Path]:
        common = [gpath / f"{installdir}.exe", gpath / f"{name}.exe", gpath / "bin" / f"{installdir}.exe",
                  gpath / "Binaries" / "Win64" / f"{installdir}.exe", gpath / "Binaries" / "Win64" / f"{name}.exe",
                  gpath / f"{installdir}-Win64-Shipping.exe", gpath / "Game" / f"{installdir}.exe",
                  gpath / "Client" / f"{installdir}.exe"]
        for exe_path in common:
            if exe_path.exists(): return exe_path
        skip = ['unins', 'install', 'setup', 'crash', 'report', 'redist', 'dotnet', 'directx', 'vcredist', 'unity', 'unreal']
        try:
            exes = [e for e in gpath.glob("*.exe") if not any(s in e.stem.lower() for s in skip)]
            if exes:
                game_exes = [e for e in exes if 'game' in e.stem.lower() or installdir.lower() in e.stem.lower()]
                return game_exes[0] if game_exes else exes[0]
            for root, dirs, files in os.walk(gpath):
                if root[len(str(gpath)):].count(os.sep) > 3:
                    dirs.clear()
                    continue
                exe_files = [f for f in files if f.endswith('.exe') and not any(s in f.lower() for s in skip)]
                if exe_files:
                    game_exes = [f for f in exe_files if 'game' in f.lower() or installdir.lower() in f.lower()]
                    return Path(root) / (game_exes[0] if game_exes else exe_files[0])
        except: pass
        return None
    
    def scan_steam(self) -> List[Game]:
        games = []
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
            steam_path = Path(winreg.QueryValueEx(key, "SteamPath")[0])
            winreg.CloseKey(key)
            lib_file = steam_path / "steamapps" / "libraryfolders.vdf"
            if lib_file.exists():
                with open(lib_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if '"path"' in line:
                            steamapps = Path(line.split('"')[3].replace('\\\\', '\\')) / "steamapps"
                            if steamapps.exists():
                                for acf in steamapps.glob("appmanifest_*.acf"):
                                    try:
                                        with open(acf, 'r', encoding='utf-8') as af:
                                            content = af.read()
                                            name = installdir = None
                                            for l in content.split('\n'):
                                                if '"name"' in l: name = l.split('"')[3]
                                                if '"installdir"' in l: installdir = l.split('"')[3]
                                            if name and installdir and not self.is_excluded(name):
                                                gpath = steamapps / "common" / installdir
                                                if gpath.exists():
                                                    exe = self._find_exe(gpath, installdir, name)
                                                    icon = IconExtractor.extract_icon(str(exe), name) if exe else ""
                                                    games.append(Game(name, str(gpath), "Steam", str(exe) if exe else "", icon))
                                    except: continue
        except: pass
        return games
    
    def scan_epic(self) -> List[Game]:
        games = []
        try:
            manifests = Path(os.getenv('PROGRAMDATA', 'C:\\ProgramData')) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
            if manifests.exists():
                for mf in manifests.glob("*.item"):
                    try:
                        with open(mf, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            name, loc = data.get('DisplayName'), data.get('InstallLocation')
                            if name and loc and not self.is_excluded(name):
                                gpath = Path(loc)
                                if gpath.exists():
                                    exe = self._find_exe(gpath, gpath.name, name)
                                    icon = IconExtractor.extract_icon(str(exe), name) if exe else ""
                                    games.append(Game(name, str(gpath), "Epic", str(exe) if exe else "", icon))
                    except: continue
        except: pass
        return games
    
    def scan_gog(self) -> List[Game]:
        games = []
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\GOG.com\Games")
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, subkey_name)
                    name = winreg.QueryValueEx(subkey, "gameName")[0]
                    path = Path(winreg.QueryValueEx(subkey, "path")[0])
                    exe_path = winreg.QueryValueEx(subkey, "exe")[0] if "exe" in [winreg.EnumValue(subkey, j)[0] for j in range(winreg.QueryInfoKey(subkey)[1])] else ""
                    winreg.CloseKey(subkey)
                    if not self.is_excluded(name) and path.exists():
                        exe = Path(exe_path) if exe_path and Path(exe_path).exists() else self._find_exe(path, path.name, name)
                        icon = IconExtractor.extract_icon(str(exe), name) if exe else ""
                        games.append(Game(name, str(path), "GOG", str(exe) if exe else "", icon))
                except: continue
            winreg.CloseKey(key)
        except: pass
        return games
    
    def scan_ea(self) -> List[Game]:
        games = []
        try:
            ea_path = Path(os.getenv('PROGRAMDATA', 'C:\\ProgramData')) / "EA Desktop" / "library"
            if ea_path.exists():
                for mf in ea_path.glob("*.mfst"):
                    try:
                        with open(mf, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            name = data.get('displayName')
                            loc = data.get('installLocation')
                            if name and loc and not self.is_excluded(name):
                                gpath = Path(loc)
                                if gpath.exists():
                                    exe = self._find_exe(gpath, gpath.name, name)
                                    icon = IconExtractor.extract_icon(str(exe), name) if exe else ""
                                    games.append(Game(name, str(gpath), "EA", str(exe) if exe else "", icon))
                    except: continue
        except: pass
        return games
    
    def scan_riot(self) -> List[Game]:
        games = []
        try:
            riot_path = Path(os.getenv('PROGRAMDATA', 'C:\\ProgramData')) / "Riot Games" / "Metadata"
            if riot_path.exists():
                for prod_dir in riot_path.iterdir():
                    if prod_dir.is_dir():
                        try:
                            name = prod_dir.name
                            install_json = prod_dir / "install.json"
                            if install_json.exists() and not self.is_excluded(name):
                                with open(install_json, 'r') as f:
                                    data = json.load(f)
                                    loc = data.get('install_location')
                                    if loc:
                                        gpath = Path(loc)
                                        if gpath.exists():
                                            exe = self._find_exe(gpath, gpath.name, name)
                                            icon = IconExtractor.extract_icon(str(exe), name) if exe else ""
                                            games.append(Game(name, str(gpath), "Riot", str(exe) if exe else "", icon))
                        except: continue
        except: pass
        return games
    
    def scan_battlenet(self) -> List[Game]:
        games = []
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Blizzard Entertainment")
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    game_key = winreg.EnumKey(key, i)
                    if game_key not in ['Battle.net', 'BattleNet']:
                        subkey = winreg.OpenKey(key, game_key)
                        path = Path(winreg.QueryValueEx(subkey, "InstallPath")[0])
                        winreg.CloseKey(subkey)
                        if not self.is_excluded(game_key) and path.exists():
                            exe = self._find_exe(path, path.name, game_key)
                            icon = IconExtractor.extract_icon(str(exe), game_key) if exe else ""
                            games.append(Game(game_key, str(path), "Battle.net", str(exe) if exe else "", icon))
                except: continue
            winreg.CloseKey(key)
        except: pass
        return games
    
    def scan_xbox(self) -> List[Game]:
        games = []
        try:
            local_packages = Path(os.getenv('LOCALAPPDATA', os.path.expanduser('~'))) / "Packages"
            if local_packages.exists():
                for pkg_dir in local_packages.iterdir():
                    if pkg_dir.is_dir():
                        manifest = pkg_dir / "AppxManifest.xml"
                        if manifest.exists():
                            try:
                                with open(manifest, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                    if '<Application ' in content:
                                        import re
                                        name_match = re.search(r'DisplayName="([^"]+)"', content)
                                        if name_match:
                                            game_name = name_match.group(1)
                                            if not self.is_excluded(game_name):
                                                content_folder = pkg_dir / "Content"
                                                if content_folder.exists():
                                                    exes = list(content_folder.glob("*.exe"))
                                                    if exes:
                                                        icon = IconExtractor.extract_icon(str(exes[0]), game_name)
                                                        games.append(Game(game_name, str(content_folder), "Xbox", str(exes[0]), icon))
                            except: continue
        except: pass
        return games
    
    def scan_all(self) -> List[Game]:
        all_games = []
        for scan_func in [self.scan_steam, self.scan_epic, self.scan_gog, self.scan_ea, self.scan_riot, self.scan_battlenet, self.scan_xbox]:
            all_games.extend(scan_func())
            gc.collect()  # Memory optimization
        return all_games

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
                self.exe_map[os.path.normpath(game.exe_path).lower()] = game.name
                try:
                    skip = ['unins', 'install', 'setup', 'crash', 'report', 'launcher']
                    for exe in Path(game.exe_path).parent.glob("*.exe"):
                        if not any(s in exe.stem.lower() for s in skip):
                            self.exe_map[os.path.normpath(str(exe)).lower()] = game.name
                    if game.platform == "Xbox":
                        for exe in Path(game.path).glob("*.exe"):
                            self.exe_map[os.path.normpath(str(exe)).lower()] = game.name
                except: pass
        gc.collect()
    
    def start(self):
        self.active = True
        self.build_exe_map()
        threading.Thread(target=self._monitor_loop, daemon=True).start()
    
    def stop(self):
        self.active = False
        self.tracked_pids.clear()
        self.close_timers.clear()
        gc.collect()
    
    def _monitor_loop(self):
        try:
            import psutil
        except: return
        while self.active:
            try:
                current_pids = set()
                active_games = set()
                for proc in psutil.process_iter(['pid', 'exe']):
                    try:
                        pid, exe = proc.info.get('pid'), proc.info.get('exe')
                        if not exe: continue
                        current_pids.add(pid)
                        norm_exe = os.path.normpath(exe).lower()
                        if norm_exe in self.exe_map:
                            game_name = self.exe_map[norm_exe]
                            active_games.add(game_name)
                            self.close_timers.pop(game_name, None)
                            if pid not in self.tracked_pids:
                                self.tracked_pids[pid] = game_name
                                if list(self.tracked_pids.values()).count(game_name) == 1:
                                    if self.twitch.config.get('enabled'):
                                        threading.Thread(target=lambda gn=game_name: self.twitch.change_category(gn), daemon=True).start()
                                    self.status_callback(f"🎮 {game_name} detected!", "#34d399")
                    except: pass
                for pid in set(self.tracked_pids.keys()) - current_pids:
                    game_name = self.tracked_pids.pop(pid, None)
                    if game_name and game_name not in active_games:
                        self.close_timers.setdefault(game_name, time.time())
                for game_name in [g for g, t in self.close_timers.items() if time.time() - t >= 30]:
                    del self.close_timers[game_name]
                    if self.twitch.config.get('enabled'):
                        threading.Thread(target=lambda: self.twitch.change_category("Just Chatting"), daemon=True).start()
                    self.status_callback(f"🔴 {game_name} closed", "#fbbf24")
                time.sleep(3.5)
            except:
                time.sleep(3.5)

class GUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Twitch Game Changer")
        self.tray_icon = None
        self.is_minimized_to_tray = False
        
        try:
            icon_path = Path('icon.ico')
            if not icon_path.exists():
                icon_path = Path(os.path.dirname(os.path.abspath(__file__))) / 'icon.ico'
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except: pass
        
        w, h = 1200, 800
        self.root.geometry(f"{w}x{h}+{(root.winfo_screenwidth()-w)//2}+{(root.winfo_screenheight()-h)//2}")
        self.root.minsize(1000, 700)
        self.root.configure(bg="#0a0e27")
        
        init_tray()
        if TRAY_AVAILABLE:
            self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
        else:
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.scanner = GameScanner()
        self.twitch = TwitchBot()
        self.monitor = None
        self.games = []
        self.filtered = []
        self.game_images = {}  # Cache for PhotoImage objects
        
        self.setup_ui()
        self.root.after(1400, self.load_cache)
    
    def setup_ui(self):
        # Header
        header = tk.Frame(self.root, bg="#0f1629", height=120)
        header.pack(fill="x")
        header.pack_propagate(False)
        header_content = tk.Frame(header, bg="#0f1629")
        header_content.pack(expand=True)
        title_frame = tk.Frame(header_content, bg="#0f1629")
        title_frame.pack()
        tk.Label(title_frame, text="🎮", font=("Segoe UI", 48), bg="#0f1629", fg="#60a5fa").pack(side="left", padx=(0, 15))
        title_text = tk.Frame(title_frame, bg="#0f1629")
        title_text.pack(side="left")
        tk.Label(title_text, text="Twitch Game Changer", font=("Segoe UI", 32, "bold"), bg="#0f1629", fg="#ffffff").pack(anchor="w")
        tk.Label(title_text, text="Auto-change Twitch category", font=("Segoe UI", 11), bg="#0f1629", fg="#6b7280").pack(anchor="w")
        
        # Controls
        ctrl = tk.Frame(self.root, bg="#0a0e27")
        ctrl.pack(fill="x", padx=30, pady=20)
        btn_container = tk.Frame(ctrl, bg="#0a0e27")
        btn_container.pack(side="left")
        btn_style = {"font": ("Segoe UI", 10, "bold"), "relief": "flat", "cursor": "hand2", "borderwidth": 0, "padx": 20, "pady": 10}
        tk.Button(btn_container, text="🔍 Scan", command=self.scan, bg="#3b82f6", fg="#ffffff", **btn_style).pack(side="left", padx=5)
        tk.Button(btn_container, text="📡 Twitch", command=self.twitch_settings, bg="#9146ff", fg="#ffffff", **btn_style).pack(side="left", padx=5)
        tk.Button(btn_container, text="🗑️ Excluded", command=self.show_excluded_games, bg="#1f2937", fg="#ffffff", **btn_style).pack(side="left", padx=5)
        self.monitor_btn = tk.Button(btn_container, text="⚪ Monitor", command=self.toggle_monitor, bg="#10b981", fg="#ffffff", **btn_style)
        self.monitor_btn.pack(side="left", padx=5)
        
        # Search
        search_container = tk.Frame(ctrl, bg="#0a0e27")
        search_container.pack(side="right")
        search_box = tk.Frame(search_container, bg="#1a1f3a", highlightthickness=1, highlightbackground="#2a2f4a")
        search_box.pack(side="left", padx=(0, 10))
        tk.Label(search_box, text="🔎", font=("Segoe UI", 12), bg="#1a1f3a", fg="#6b7280").pack(side="left", padx=(10, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *args: self.filter())
        tk.Entry(search_box, textvariable=self.search_var, font=("Segoe UI", 11), bg="#1a1f3a", fg="#ffffff", relief="flat", width=30, borderwidth=0).pack(side="left", padx=(0, 10), pady=8)
        
        filter_frame = tk.Frame(search_container, bg="#1a1f3a", highlightthickness=1, highlightbackground="#2a2f4a")
        filter_frame.pack(side="left")
        self.platform_var = tk.StringVar(value="All Platforms")
        platforms = ["All Platforms", "Steam", "Epic", "GOG", "EA", "Riot", "Battle.net", "Xbox"]
        dropdown = ttk.Combobox(filter_frame, textvariable=self.platform_var, values=platforms, state="readonly", width=15, font=("Segoe UI", 10))
        dropdown.pack(padx=10, pady=8)
        dropdown.bind("<<ComboboxSelected>>", lambda e: self.filter())
        
        # Game list
        list_frame = tk.Frame(self.root, bg="#0a0e27")
        list_frame.pack(fill="both", expand=True, padx=30, pady=(0, 20))
        canvas = tk.Canvas(list_frame, bg="#0a0e27", highlightthickness=0)
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg="#0a0e27")
        self.scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Status bar
        status_bar = tk.Frame(self.root, bg="#0f1629", height=50)
        status_bar.pack(fill="x", side="bottom")
        status_bar.pack_propagate(False)
        self.status = tk.Label(status_bar, text="Ready", font=("Segoe UI", 11), bg="#0f1629", fg="#9ca3af", anchor="w")
        self.status.pack(side="left", padx=20, pady=10)
    
    def scan(self):
        self.status.config(text="🔄 Scanning games...", fg="#60a5fa")
        self.root.update()
        def scan_thread():
            self.games = self.scanner.scan_all()
            self.filtered = self.games.copy()
            self.root.after(0, lambda: [self.display(), self.save_cache(), 
                self.status.config(text=f"✅ Found {len(self.games)} games", fg="#10b981")])
        threading.Thread(target=scan_thread, daemon=True).start()
    
    def display(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.game_images.clear()
        gc.collect()
        
        for game in self.filtered:
            card = tk.Frame(self.scrollable_frame, bg="#151b2e", highlightthickness=1, highlightbackground="#2a2f4a")
            card.pack(fill="x", pady=8)
            
            # Icon
            icon_label = tk.Label(card, bg="#151b2e")
            if game.icon:
                try:
                    from PIL import Image, ImageTk
                    img = Image.open(game.icon).resize((48, 48), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.game_images[game.name] = photo
                    icon_label.config(image=photo)
                except:
                    icon_label.config(text="🎮", font=("Segoe UI", 24), fg="#60a5fa")
            else:
                icon_label.config(text="🎮", font=("Segoe UI", 24), fg="#60a5fa")
            icon_label.pack(side="left", padx=15, pady=10)
            
            info = tk.Frame(card, bg="#151b2e")
            info.pack(side="left", fill="x", expand=True, padx=10, pady=10)
            tk.Label(info, text=game.name, font=("Segoe UI", 12, "bold"), bg="#151b2e", fg="#f3f4f6", anchor="w").pack(anchor="w")
            tk.Label(info, text=f"{game.platform} • {game.path[:60]}...", font=("Segoe UI", 9), bg="#151b2e", fg="#6b7280", anchor="w").pack(anchor="w")
            
            tk.Button(card, text="🗑️", command=lambda g=game: self.exclude_game(g), font=("Segoe UI", 14), bg="#ef4444", fg="#ffffff", relief="flat", cursor="hand2", borderwidth=0, width=3).pack(side="right", padx=10)
    
    def filter(self):
        query = self.search_var.get().lower()
        platform = self.platform_var.get()
        self.filtered = [g for g in self.games if (query in g.name.lower()) and (platform == "All Platforms" or g.platform == platform)]
        self.display()
    
    def exclude_game(self, game: Game):
        if messagebox.askyesno("Exclude Game", f"Remove '{game.name}' from library?"):
            self.scanner.exclude(game.name)
            self.games = [g for g in self.games if g.name != game.name]
            self.filter()
            self.save_cache()
            self.status.config(text=f"🗑️ Excluded {game.name}", fg="#ef4444")
    
    def show_excluded_games(self):
        excluded_list = self.scanner.get_excluded_list()
        dialog = tk.Toplevel(self.root)
        dialog.title("Excluded Games")
        dialog.geometry("600x500")
        dialog.configure(bg="#0f1629")
        dialog.grab_set()
        tk.Label(dialog, text="🗑️ Excluded Games", font=("Segoe UI", 18, "bold"), bg="#0f1629", fg="#ef4444").pack(pady=20)
        if not excluded_list:
            tk.Label(dialog, text="No excluded games", font=("Segoe UI", 12), bg="#0f1629", fg="#6b7280").pack(pady=50)
            tk.Button(dialog, text="Close", command=dialog.destroy, font=("Segoe UI", 11, "bold"), bg="#374151", fg="#ffffff", relief="flat", padx=30, pady=10).pack(pady=20)
            return
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
            tk.Button(item_frame, text="↩️ Restore", command=lambda n=game_name: self._restore(n, dialog), font=("Segoe UI", 9, "bold"), bg="#10b981", fg="#ffffff", relief="flat", padx=15, pady=6).pack(side="right", padx=10)
        tk.Button(dialog, text="Close", command=dialog.destroy, font=("Segoe UI", 11, "bold"), bg="#374151", fg="#ffffff", relief="flat", padx=30, pady=10).pack(pady=(0, 20))
    
    def _restore(self, name, dialog):
        if messagebox.askyesno("Restore Game", f"Restore '{name}'?\n\nRescan to see it."):
            if self.scanner.unexclude(name):
                self.status.config(text=f"✅ Restored {name} - rescan", fg="#10b981")
                dialog.destroy()
                self.show_excluded_games()
    
    def twitch_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Twitch Settings")
        dialog.geometry("500x350")
        dialog.configure(bg="#0f1629")
        dialog.grab_set()
        tk.Label(dialog, text="📡 Twitch Integration", font=("Segoe UI", 20, "bold"), bg="#0f1629", fg="#9146ff").pack(pady=20)
        
        form = tk.Frame(dialog, bg="#0f1629")
        form.pack(pady=20)
        tk.Label(form, text="Channel Name:", font=("Segoe UI", 12), bg="#0f1629", fg="#d1d5db").grid(row=0, column=0, sticky="e", padx=10, pady=10)
        channel_var = tk.StringVar(value=self.twitch.config.get('channel_name', ''))
        tk.Entry(form, textvariable=channel_var, font=("Segoe UI", 11), bg="#1a1f3a", fg="#ffffff", relief="flat", width=25).grid(row=0, column=1, pady=10)
        
        enabled_var = tk.BooleanVar(value=self.twitch.config.get('enabled', False))
        tk.Checkbutton(form, text="Enable auto-category change", variable=enabled_var, font=("Segoe UI", 11), bg="#0f1629", fg="#d1d5db", selectcolor="#1a1f3a").grid(row=1, column=0, columnspan=2, pady=10)
        
        def save():
            self.twitch.update_config(channel_var.get(), enabled_var.get())
            self.status.config(text="✅ Twitch settings saved", fg="#10b981")
            dialog.destroy()
        
        def auth():
            if self.twitch.authenticate():
                messagebox.showinfo("Success", "Authentication successful!")
                self.status.config(text="✅ Twitch authenticated", fg="#10b981")
            else:
                messagebox.showerror("Error", "Authentication failed")
        
        btn_frame = tk.Frame(dialog, bg="#0f1629")
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text="🔐 Authenticate", command=auth, font=("Segoe UI", 11, "bold"), bg="#9146ff", fg="#ffffff", relief="flat", padx=20, pady=10).pack(side="left", padx=5)
        tk.Button(btn_frame, text="💾 Save", command=save, font=("Segoe UI", 11, "bold"), bg="#10b981", fg="#ffffff", relief="flat", padx=20, pady=10).pack(side="left", padx=5)
    
    def toggle_monitor(self):
        if self.monitor and self.monitor.active:
            self.monitor.stop()
            self.monitor = None
            self.monitor_btn.config(text="⚪ Monitor", bg="#10b981")
            self.status.config(text="⚪ Monitor stopped", fg="#6b7280")
        else:
            if not self.games:
                messagebox.showwarning("No Games", "Scan games first!")
                return
            self.monitor = GameMonitor(self.games, self.twitch, self.update_status)
            self.monitor.start()
            self.monitor_btn.config(text="🟢 Monitor", bg="#ef4444")
            self.status.config(text="🟢 Monitor active", fg="#10b981")
    
    def update_status(self, msg: str, color: str):
        self.root.after(0, lambda: self.status.config(text=msg, fg=color))
    
    def save_cache(self):
        try:
            data = [{'name': g.name, 'path': g.path, 'platform': g.platform, 'exe_path': g.exe_path, 'icon': g.icon} for g in self.games]
            with open(GAMES_CACHE_FILE, 'w') as f:
                json.dump(data, f)
        except: pass
    
    def load_cache(self):
        try:
            if GAMES_CACHE_FILE.exists():
                with open(GAMES_CACHE_FILE, 'r') as f:
                    data = json.load(f)
                    self.games = [Game(g['name'], g['path'], g['platform'], g.get('exe_path', ''), g.get('icon', '')) for g in data]
                    self.filtered = self.games.copy()
                    if self.games:
                        self.display()
                        self.status.config(text=f"✅ Loaded {len(self.games)} games", fg="#10b981")
        except: pass
    
    def minimize_to_tray(self):
        if not TRAY_AVAILABLE or not pystray:
            self.root.iconify()
            return
        if self.is_minimized_to_tray: return
        self.root.withdraw()
        self.is_minimized_to_tray = True
        if not self.tray_icon:
            try:
                from PIL import Image
                icon_path = Path("icon.ico")
                if not icon_path.exists():
                    icon_path = Path(os.path.dirname(os.path.abspath(__file__))) / "icon.ico"
                image = Image.open(icon_path).resize((32, 32), Image.LANCZOS) if icon_path.exists() else None
            except: image = None
            menu = pystray.Menu(item('Show', self.show_window, default=True), item('Monitor Status', self.show_monitor_status),
                pystray.Menu.SEPARATOR, item('Exit', self.quit_app))
            try:
                self.tray_icon = pystray.Icon("twitch_game_changer", image, "Twitch Game Changer", menu)
            except:
                self.tray_icon = pystray.Icon("twitch_game_changer", None, "Twitch Game Changer", menu)
            def start_tray():
                while self.is_minimized_to_tray:
                    try:
                        self.tray_icon.run()
                        break
                    except:
                        time.sleep(1)
                        if not self.is_minimized_to_tray: break
                        try:
                            self.tray_icon = pystray.Icon("twitch_game_changer", image, "Twitch Game Changer", menu)
                        except: time.sleep(1)
            threading.Thread(target=start_tray, daemon=True).start()
    
    def show_window(self, icon=None, item=None):
        self.is_minimized_to_tray = False
        try:
            if self.tray_icon:
                self.tray_icon.stop()
                self.tray_icon = None
        except: pass
        self.root.after(0, self.root.deiconify)
        self.root.after(0, self.root.lift)
    
    def show_monitor_status(self, icon=None, item=None):
        status = "🟢 Monitor ACTIVE" if self.monitor and self.monitor.active else "⚪ Monitor INACTIVE"
        self.root.after(0, lambda: messagebox.showinfo("Monitor Status", status))
    
    def quit_app(self, icon=None, item=None):
        try:
            if self.monitor and self.monitor.active: self.monitor.stop()
            if self.tray_icon: self.tray_icon.stop()
        except: pass
        self.root.after(0, self.root.destroy)
    
    def on_closing(self):
        if self.monitor and self.monitor.active:
            if messagebox.askyesno("Monitor Active", "Exit anyway?"):
                self.monitor.stop()
                self.root.destroy()
        else:
            self.root.destroy()

def main():
    root = tk.Tk()
    app = GUI(root)
    if STARTUP_MODE and hasattr(app, "minimize_to_tray"):
        root.after(800, app.minimize_to_tray)
    root.mainloop()

if __name__ == "__main__":
    main()
