# Extreme Campus Fabric Visibility Dashboard

Interactive dashboard for monitoring Extreme Networks Fabric Connect environments.

## Features
- Fabric Topology Map (core / distribution / edge nodes)
- IS-IS adjacency and health metrics
- Service segmentation (I-SIDs, VRFs, tenants)
- Performance analytics with 7-day trends
- Simulated real-time updates every 5 seconds

---

## Run Locally

### Prerequisites
- Python 3.8 or higher
- pip

### Steps

1. **Clone the repo**
   ```bash
   git clone https://github.com/dhuffma/ExtremeNetworks-Playground.git
   cd ExtremeNetworks-Playground
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Start the server**
   ```bash
   python app.py
   ```

4. **Open in your browser**
   ```
   http://localhost:5000
   ```

---

## Deploy on Railway

Railway auto-deploys on every push to `main`.

1. Connect this repo to your Railway project
2. Railway detects `requirements.txt` and `Procfile` automatically
3. The `Procfile` tells Railway to run: `python app.py`
4. Railway injects the `PORT` environment variable — the app reads it automatically
5. Once deployed, open the public URL Railway assigns (e.g. `https://your-app.up.railway.app`)

---

## Project Structure

```
├── app.py              # Flask web server
├── requirements.txt    # Python dependencies
├── Procfile            # Railway start command
└── public/
    └── index.html      # Dashboard (single-page app)
```
