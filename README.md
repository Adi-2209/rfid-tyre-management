# RFID Tyre Management

## Run the application

On macOS or Linux, start both the API and dashboard with one command from the project root:

```sh
./start.sh
```

Open the dashboard URL printed in the terminal (normally `http://127.0.0.1:5173`). The API listens on the LAN as well, so an ESP32 on the same network can reach it. If a default port is already occupied, the launcher chooses the next free port; set the firmware URLs to the API port printed by the launcher. Press Ctrl+C to stop both servers. The first run requires the backend and frontend dependencies below.

If either default port is already in use, choose alternate ports when launching, for example `RFID_API_PORT=8001 RFID_WEB_PORT=5174 ./start.sh`.

To start the API and dashboard separately, use two terminals. Start the API from the project root:

```sh
python3 -m pip install -r backend/requirements.txt
python3 -m uvicorn backend.app.main:app --reload
```

In a second terminal, start the React dashboard:

```sh
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite (normally `http://127.0.0.1:5173`). On first use, create the administrator account. Passwords must be at least 12 characters. The dashboard proxies API requests to `http://127.0.0.1:8000`.

To serve the dashboard from FastAPI instead, build it first:

```sh
cd frontend
npm run build
```

Then start FastAPI as above and open `http://127.0.0.1:8000`.

## ESP32 reader key

For ESP32 observations, set the same private key in the API environment and in `edge/esp32_http_bridge.cpp` (`DEVICE_API_KEY`). On macOS, for example:

```sh
export RFID_DEVICE_API_KEY="replace-with-a-long-random-secret"
python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Change the firmware's `API_URL` and `HEARTBEAT_URL` to the computer's LAN IP, then build and upload the firmware. The ESP32 sends a heartbeat every 15 seconds; the dashboard marks it offline after 45 seconds without one. Keep the reader key private. Dashboard users authenticate with their admin account; reader keys are only for ESP32 submissions.
