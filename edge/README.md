# ESP32 RFID bridge

`esp32_http_bridge.cpp` reads one text line per tag from UART2, then sends it to the RFID Tyre Management API.

Expected reader line:

```text
E2000017221101441890ABCD,-48.2,1
```

Fields: `EPC,RSSI_DBM,ANTENNA_ID`. A module with a binary serial protocol needs a module-specific `parseReaderLine()` implementation.

The firmware keeps up to 20 observations in a FIFO RAM queue. It retries Wi-Fi and temporary API/server failures, including timeouts and HTTP 5xx/429 responses. The queue is cleared on power loss or reset; when full, the newest read is dropped. Permanent API rejections (other HTTP 4xx responses) are removed from the queue and printed to Serial Monitor.

Configure Wi-Fi credentials, API URL, heartbeat URL, device API key, reader ID, station ID, UART pins, and baud rate near the top of the source file. Both URLs must use the computer's LAN IP, and the backend must listen on `0.0.0.0:8000` so the ESP32 can reach it. The firmware posts a reader heartbeat every 15 seconds; the dashboard marks a reader offline after 45 seconds without one. Set the same `DEVICE_API_KEY` value in the firmware and `RFID_DEVICE_API_KEY` in the backend environment.
