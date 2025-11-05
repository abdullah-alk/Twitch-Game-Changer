# 🎮 Twitch Game Changer

**Automatically update your Twitch stream category to the game you're playing. No more "Forgot to change my category" moments!**

Twitch Game Changer is a lightweight, smart desktop application for Windows that scans your PC for installed games, monitors your active processes, and instantly updates your Twitch category when you launch a game. When you close it, it intelligently switches you back to "Just Chatting."



---

## ✨ Key Features

* **Multi-Platform Scanning:** Automatically detects games from all major launchers:
    * Steam
    * Epic Games
    * GOG
    * EA/Origin
    * Riot Games
    * Battle.net
    * Xbox
* **Smart Category Matching:** Uses the Twitch API to find the *exact* category for your game. If no game is running, it defaults to **"Just Chatting."** If a game is detected but not listed on Twitch, it falls back to **"Games + Demos."**
* **Secure Authentication:** Uses the official Twitch Device Flow for authentication. Your sensitive access tokens are **encrypted and stored locally** on your machine using machine-specific keys.
* **Full Game Library Management:**
    * Beautiful UI displays all found games with their icons and platform.
    * Search your library by name.
    * Filter by platform (e.g., show only Steam games).
    * Exclude games (like "wallpaper.exe" or test clients) you don't want to track.
    * A dedicated "Excluded Games" manager to restore games you've removed.
* **Efficient Background Monitoring:** Runs quietly in your system tray using minimal resources (`psutil` for process checking).
* **Resilient Tray Icon:** The system tray icon is designed to automatically recover and reload if Windows Explorer restarts (a common issue that crashes many tray apps).
* **Run on Startup:** Includes a `--startup` launch flag so you can add it to your Windows startup folder and have it run minimized automatically.

## 🚀 Installation

### Option 1: From Release (Recommended)

1.  Go to the **[Releases Page](https://github.com/your-username/your-repo/releases)**.
2.  Download the latest `TwitchGameChanger_vX.X.X.exe`.
3.   run The Installer and Enjoy The App ❤️.

### Option 2: From Source (For Developers)

If you have Python 3.10+ installed, you can run the app from the source code.

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-username/your-repo.git](https://github.com/your-username/your-repo.git)
    cd your-repo
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    .\venv\Scripts\activate
    ```

3.  **Install the required dependencies:**
    ```bash
    # Create a requirements.txt file with the following contents:
    # requests
    # pystray
    # Pillow
    # pywin32
    # cryptography
    # psutil
    
    pip install -r requirements.txt
    ```

4.  **Run the application:**
    ```bash
    python TwitchGameChanger.py
    ```

---

## 💡 How to Use

1.  **Launch** the application.
2.  **Scan for Games:** Click the **`🔍 Scan`** button. The app will search your drives for all supported launchers. This may take a minute on the first run. Your games will appear in the main window.
3.  **Authenticate with Twitch:**
    * Click the **`📡 Twitch`** button.
    * Enter your Twitch channel name (e.g., `your_username`).
    * Click **`🔐 Authenticate`**.
    * A popup will appear with a code. Your browser will open to `twitch.tv/activate`.
    * Enter the code on the Twitch page to authorize the app.
4.  **Enable and Save:**
    * Once authenticated, check the **"Enable automatic category changes"** box.
    * Click **`💾 Save`**.
5.  **Start Monitoring:** Click the **`⚪ Monitor`** button. It will turn green and read **`🟢 Active`**.
6.  **Minimize:** Close the window. The app will automatically minimize to your system tray.
7.  **All Done!** Just launch any game from your library, and your Twitch category will update within seconds.
