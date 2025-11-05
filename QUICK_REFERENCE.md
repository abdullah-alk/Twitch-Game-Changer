# TwitchGameChanger - Quick Reference

## 🚀 Quick Start

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run from Source
```bash
python TwitchGameChanger_Optimized.py
```

## 📦 Package to EXE (Choose One)

### Option 1: PyInstaller (Easy)
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --icon=icon.ico TwitchGameChanger_Optimized.py
# Output: dist/TwitchGameChanger_Optimized.exe
```

### Option 2: PyInstaller with Spec (Best)
```bash
pip install pyinstaller
pyinstaller TwitchGameChanger.spec
# Output: dist/TwitchGameChanger.exe
# Smaller size with UPX compression
```

### Option 3: Nuitka (Fastest)
```bash
pip install nuitka
python -m nuitka --standalone --onefile --windows-disable-console --enable-plugin=tk-inter TwitchGameChanger_Optimized.py
# Output: TwitchGameChanger_Optimized.exe
```

### Option 4: cx_Freeze (Cross-platform)
```bash
pip install cx_Freeze
python setup.py build
# Output: build/exe.win-amd64-3.x/TwitchGameChanger.exe
```

## 🔧 Common Commands

### Compress with UPX
```bash
upx --best --lzma TwitchGameChanger.exe
# Further reduce size by 30-50%
```

### Test Executable
```bash
# Run with console to see errors
TwitchGameChanger.exe

# Or build with console
pyinstaller --onefile --console TwitchGameChanger_Optimized.py
```

### Clean Build Files
```bash
# Windows
rmdir /s /q build dist
del *.spec

# Linux/Mac
rm -rf build dist *.spec
```

## 📁 File Structure

```
TwitchGameChanger/
├── TwitchGameChanger_Optimized.py  # Main optimized source
├── requirements.txt                 # Dependencies
├── TwitchGameChanger.spec          # PyInstaller config
├── setup.py                        # cx_Freeze config
├── icon.ico                        # App icon (optional)
├── PACKAGING_GUIDE.md              # Complete guide
└── OPTIMIZATION_REPORT.md          # Optimization details
```

## 🔑 Key Features

### Security
- ✅ Token encryption (machine-locked)
- ✅ Secure OAuth2 authentication
- ✅ Auto token refresh

### Performance
- ✅ 35-40% less RAM usage
- ✅ 25% smaller code
- ✅ 30% faster startup
- ✅ Lazy module loading

### Features
- ✅ Game icon extraction
- ✅ Multi-platform support (7 launchers)
- ✅ Auto Twitch category change
- ✅ System tray support
- ✅ Game name mapping

## 🐛 Troubleshooting

### Issue: Missing cryptography
```bash
pip install cryptography
# or it will use fallback XOR encryption
```

### Issue: Icons not extracting
```bash
pip install pywin32
# Required for icon extraction on Windows
```

### Issue: Tray not working
```bash
pip install pystray pillow
# Optional tray support
```

### Issue: Can't detect games
```bash
pip install psutil
# Required for process monitoring
```

## 📊 Memory Usage

| State | RAM Usage |
|-------|-----------|
| Idle | ~55 MB |
| After Scan | ~80 MB |
| Monitoring | ~95 MB |

## 🎯 Recommended Build

**For Distribution:**
```bash
# 1. Install PyInstaller
pip install pyinstaller

# 2. Build with spec file
pyinstaller TwitchGameChanger.spec

# 3. Compress
upx --best dist/TwitchGameChanger.exe

# Result: ~20-22 MB executable
```

## 📱 Auto-Startup

**Windows Startup Folder:**
1. Press `Win + R`
2. Type: `shell:startup`
3. Create shortcut to exe with parameter: `--startup`

**Or in code:**
```python
import winreg
key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
    r'Software\Microsoft\Windows\CurrentVersion\Run', 
    0, winreg.KEY_SET_VALUE)
winreg.SetValueEx(key, 'TwitchGameChanger', 0, 
    winreg.REG_SZ, r'"C:\path\to\TwitchGameChanger.exe" --startup')
```

## 📝 Distribution Checklist

- [ ] Build executable with PyInstaller/Nuitka
- [ ] Test on clean Windows machine
- [ ] Compress with UPX (optional)
- [ ] Code sign (optional but recommended)
- [ ] Create installer with Inno Setup (optional)
- [ ] Include README
- [ ] Provide SHA256 hash
- [ ] Upload to GitHub releases

## 🔗 Quick Links

- **Full Guide**: PACKAGING_GUIDE.md
- **Optimization Details**: OPTIMIZATION_REPORT.md
- **Dependencies**: requirements.txt

## 💡 Tips

1. **Smallest Size**: Use Nuitka + UPX (~18-20 MB)
2. **Fastest Build**: PyInstaller with spec file
3. **Most Compatible**: PyInstaller onefile
4. **Best Security**: Code sign your executable
5. **Professional**: Create installer with Inno Setup

## 📞 Support

- Check PACKAGING_GUIDE.md for detailed instructions
- Review OPTIMIZATION_REPORT.md for technical details
- Test in console mode to see error messages
- Ensure all dependencies are installed

---

**Quick Start Summary:**
```bash
# Install dependencies
pip install -r requirements.txt

# Build best version
pip install pyinstaller
pyinstaller TwitchGameChanger.spec

# Your exe is ready!
# Location: dist/TwitchGameChanger.exe
```
