# Penny Buddy

**Money made simple** — A personal finance app for young professionals.

Penny Buddy helps you track daily expenses, set savings goals, manage EMIs and subscriptions, and understand your spending habits — all through a clean, mobile-friendly interface that works in your browser.

No sign-ups. No cloud. Your data stays on your machine.

---

## What Does This App Do?

| Feature | What It Means |
|---------|---------------|
| **Dashboard** | A home screen showing your balance, how much you earned vs spent this month, recent transactions, and upcoming bills |
| **Quick Add Expense** | Tap a button, pick a category (Food, Transport, Shopping, etc.), enter the amount — done in seconds |
| **Transactions** | A searchable list of everything you've earned or spent, filterable by category and month |
| **Savings Goals** | Set a target (e.g. "New Laptop — $1000"), contribute money over time, and watch a visual progress ring fill up |
| **EMI & Dues** | Track recurring payments like loan EMIs, Netflix, gym memberships — get reminded 5 days before each due date |
| **Money Pulse** | A weekly 1-minute check-in: how do you feel about your finances this week? Tracks your financial wellness over time |
| **Insights** | Charts showing where your money goes, daily spending trends, and how this month compares to last month |
| **Multi-Currency** | Works with INR (₹), USD ($), EUR (€), and GBP (£) |
| **Dark Mode** | Easy on the eyes at night — toggle it from Profile settings |
| **Install as App** | Add it to your phone's home screen and use it like a native app (works offline too) |

---

## Tech Stack (What's Under the Hood)

If you're new to programming, here's a plain-English breakdown of every technology used:

| Technology | What It Is | Role in This Project |
|------------|-----------|----------------------|
| **Python** | A beginner-friendly programming language | Runs the server (the "backend" that stores and retrieves your data) |
| **Flask** | A lightweight Python web framework | Handles web requests — when the app asks "show me my transactions," Flask answers |
| **SQLite** | A simple file-based database | Stores all your data in a single file (`pennybuddy.db`) — no database server to install |
| **HTML** | The language that defines web page structure | Creates the layout — buttons, inputs, sections of the app |
| **CSS** | The language that styles web pages | Makes everything look good — colors, fonts, spacing, dark mode |
| **JavaScript** | The language that makes web pages interactive | Handles all the logic — switching screens, calling the server, drawing charts |
| **Service Worker** | A browser feature for offline apps | Caches the app so it works even without internet |
| **Capacitor** | A tool that wraps web apps into mobile apps | *(Optional)* Lets you build a real Android/iOS app from this web code |

**No frameworks** like React or Angular — just plain HTML, CSS, and JavaScript. This makes the code easier to read and learn from.

---

## Getting Started

### What You Need to Install First

1. **Python 3.7 or newer**
   - Download from [python.org](https://www.python.org/downloads/)
   - During installation on Windows, **check the box that says "Add Python to PATH"** — this is important
   - To verify it's installed, open a terminal and type:
     ```bash
     python --version
     ```
     You should see something like `Python 3.11.4`

2. **pip** (Python's package installer)
   - This comes bundled with Python. Verify with:
     ```bash
     pip --version
     ```

That's all you need. No Node.js, no databases to set up, no Docker.

### Running the App

```bash
# Step 1: Open a terminal and navigate to the project folder
cd path/to/fintech

# Step 2: Install the two Python packages this app needs
pip install flask flask-cors

# Step 3: Start the server
python server.py
```

You should see output like:
```
 * Running on http://0.0.0.0:5000
```

**Step 4:** Open your browser and go to **http://localhost:5000**

The app will greet you with a 4-step onboarding: enter your name, pick a currency, set your monthly income, and choose your spending categories. After that, you're on the dashboard and ready to go.

> The database file (`pennybuddy.db`) is created automatically the first time the server starts. You don't need to set up anything.

### Stopping the Server

Press `Ctrl + C` in the terminal where the server is running.

---

## Project Structure

Here's what each file does:

```
penny-buddy/
│
├── server.py              # The backend — handles all data storage and API logic
├── index.html             # The single HTML page that IS the app
├── app.js                 # All frontend logic — screen rendering, user actions, API calls
├── styles.css             # All visual styling — layout, colors, dark mode, responsive design
├── sw.js                  # Service worker — enables offline use and caching
├── manifest.json          # Tells browsers this is an installable app (name, icons, theme)
│
├── pennybuddy.db          # Your data (auto-created, do NOT commit to version control)
│
├── icons/                 # App icons in various sizes for different devices
│   ├── icon-72x72.png
│   ├── icon-192x192.png
│   ├── icon-512x512.png
│   └── ...
│
├── case-study.html        # A standalone marketing/portfolio page about the app
│
├── package.json           # Node.js config (only needed if building mobile apps)
├── capacitor.config.json  # Mobile app settings (only needed for Android/iOS builds)
├── build-www.js           # Build script that copies files for mobile builds
├── build_www.py           # Same build script, Python version
└── www/                   # Auto-generated folder used by Capacitor for mobile builds
```

---

## How It Works

The app follows a simple **client-server** pattern:

```
┌──────────────┐         HTTP requests         ┌──────────────┐
│              │  ──── "give me my goals" ────> │              │
│   Browser    │                                │  Flask       │
│  (app.js)    │  <── JSON data back ────────── │  (server.py) │
│              │                                │      │       │
└──────────────┘                                │      ▼       │
     The UI you see                             │   SQLite     │
     and interact with                          │  (pennybuddy │
                                                │     .db)     │
                                                └──────────────┘
```

1. **You interact with the browser** — tapping buttons, filling forms
2. **JavaScript (app.js) sends requests** to the Flask server (e.g., "save this expense")
3. **Flask (server.py) processes the request** and reads/writes to the SQLite database
4. **Flask sends back a response** (e.g., "here are your transactions") as JSON data
5. **JavaScript updates the screen** with the new data

Everything runs on your computer. Nothing is sent to the cloud.

---

## API Endpoints

These are the URLs that the frontend uses to talk to the backend. If you're learning web development, this is a good reference for how REST APIs work.

| Method | Endpoint | What It Does |
|--------|----------|--------------|
| `GET` | `/api/user` | Get the user's profile and settings |
| `POST` | `/api/user` | Create a new user (during onboarding) |
| `PUT` | `/api/user` | Update user settings (name, income, currency, etc.) |
| `GET` | `/api/transactions` | Get all transactions (supports `?month=YYYY-MM` filter) |
| `POST` | `/api/transactions` | Add a new expense or income |
| `DELETE` | `/api/transactions/:id` | Delete a transaction by its ID |
| `GET` | `/api/summary` | Get this month's totals (income, expenses, balance) |
| `GET` | `/api/goals` | Get all savings goals |
| `POST` | `/api/goals` | Create a new savings goal |
| `PUT` | `/api/goals/:id` | Update a goal (e.g., add money to it) |
| `DELETE` | `/api/goals/:id` | Delete a goal |
| `GET` | `/api/dues` | Get all EMI/subscription/due payments |
| `POST` | `/api/dues` | Add a new recurring payment |
| `POST` | `/api/dues/:id/pay` | Mark a due as paid (auto-creates next month's entry if recurring) |
| `DELETE` | `/api/dues/:id` | Delete a due payment |
| `GET` | `/api/pulse` | Get all Money Pulse check-ins |
| `POST` | `/api/pulse` | Save this week's check-in |
| `GET` | `/api/pulse/current-week` | Check if you've already done this week's pulse |
| `POST` | `/api/reset` | Wipe all data and start fresh |

---

## Common Tasks

### Resetting All Data

Go to **Profile > Reset App** in the app. This deletes everything and takes you back to the onboarding screen.

Alternatively, you can delete the `pennybuddy.db` file and restart the server — a fresh database will be created.

### Installing as a Phone App (PWA)

1. Open `http://localhost:5000` in Chrome on your phone (your phone must be on the same Wi-Fi network — use your computer's local IP instead of `localhost`)
2. Chrome will show a banner or you can tap the menu > "Add to Home Screen"
3. The app now opens full-screen like a native app and works offline

### Changing Currency

Go to **Profile** (bottom-right icon) and select your preferred currency. All amounts will be displayed with the new currency symbol.

---

## Building a Mobile App (Optional, Advanced)

If you want to turn this into a real Android or iOS app, you'll need additional tools:

### Extra Prerequisites

- **Node.js 18+** — Download from [nodejs.org](https://nodejs.org/)
- **Android Studio** — For Android builds ([developer.android.com](https://developer.android.com/studio))
- **Xcode** — For iOS builds (macOS only, from the App Store)

### Build Steps

```bash
# Install Node dependencies (Capacitor and its plugins)
npm install

# Copy web files to the www/ folder for mobile packaging
npm run build:web

# Open in Android Studio to build an APK
npm run build:android

# Or open in Xcode to build for iPhone (macOS only)
npm run build:ios
```

This uses **Capacitor**, a tool that wraps your web app inside a native container so it can be distributed on the Google Play Store or Apple App Store.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `python: command not found` | Python isn't installed or isn't in your PATH. Reinstall and check "Add to PATH" |
| `ModuleNotFoundError: No module named 'flask'` | Run `pip install flask flask-cors` |
| `Address already in use` | Another program is using port 5000. Stop it, or edit `server.py` to change the port |
| App shows blank page | Make sure the server is running. Check the terminal for error messages |
| Can't access from phone | Use your computer's IP address (e.g., `http://192.168.1.5:5000`) instead of `localhost` |
| Database seems corrupted | Delete `pennybuddy.db` and restart the server for a fresh start |

---

## License

MIT — Free to use, modify, and distribute.
