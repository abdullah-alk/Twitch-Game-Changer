from cx_Freeze import setup, Executable
import sys

# Dependencies
build_exe_options = {
    "packages": [
        "tkinter",
        "requests", 
        "psutil",
        "PIL",
        "PIL.Image",
        "PIL.ImageTk",
        "cryptography",
        "pystray",
        "win32api",
        "win32con", 
        "win32ui",
        "win32gui",
    ],
    "excludes": [
        "matplotlib",
        "numpy",
        "scipy",
        "pandas",
        "unittest",
        "test",
        "tests",
        "distutils",
        "email",
        "html",
        "http",
        "urllib",
        "xml",
    ],
    "include_files": [
        ("icon.ico", "icon.ico"),  # Include if you have an icon
    ],
    "optimize": 2,
}

# Setup configuration
setup(
    name="TwitchGameChanger",
    version="2.0",
    description="Automatically change Twitch category when playing games",
    author="Your Name",
    options={"build_exe": build_exe_options},
    executables=[
        Executable(
            "TwitchGameChanger_Optimized.py",
            base="Win32GUI" if sys.platform == "win32" else None,
            icon="icon.ico",
            target_name="TwitchGameChanger.exe",
            shortcut_name="Twitch Game Changer",
            shortcut_dir="DesktopFolder",
        )
    ],
)
