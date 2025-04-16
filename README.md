# PING_LAMP - ESP32 Network Latency Visualizer

## Overview

This project provides a real-time visualization of network latency using an ESP32 microcontroller (`ESP32/main.py`) and connected LEDs. A Python server (`server.py`) pings configured network targets, calculates a latency level, and sends this level to the ESP32 client via WebSocket. The ESP32 drives LEDs to represent the latency.

## Features

*   **Server (`server.py`):**
    *   Pings multiple network targets (configured via `.env`).
    *   Calculates latency metrics (combining short/long term analysis).
    *   Broadcasts results via WebSocket.
    *   Includes a server-side watchdog based on client keep-alives (expects `{"type": "keepalive"}` JSON from client) to pause sending data to unresponsive clients.
    *   Configurable via `.env` file.
*   **Client (`ESP32/main.py`):**
    *   Connects to WiFi and the WebSocket server.
    *   Handles automatic reconnections for WiFi and WebSocket.
    *   Receives the latency level from the server.
    *   Controls LEDs using PWM with interpolation and decay ("afterglow").
    *   Implements client-side delay detection: increases target level if messages are delayed.
    *   Sends periodic application-level keep-alive messages (`{"type": "keepalive"}`) to the server.
    *   Supports interruption via CTRL+C over serial.

## Hardware Requirements

*   ESP32 Development Board
*   LEDs (e.g., 1x Red, 1x Green, 1x Orange/Yellow)
*   Current-Limiting Resistors (Appropriate for LEDs and 3.3V)
*   Breadboard and Jumper Wires
*   Micro USB Cable
*   Computer (To run `server.py`)
*   WiFi Network

## Software Requirements

*   **Server (`server.py`):**
    *   Python 3.8+
    *   Required Python libraries:
        *   `websockets==15.0.1` (or version specified in `requirements.txt`)
        *   `numpy`
        *   `python-dotenv`
    *   Installation: Create/activate a virtual environment and run `pip install -r requirements.txt`.
    *   `ping` command accessible in the system's PATH. (May require `sudo`/`cap_net_raw` on Linux).
    *   **Important:** Ensure the `handler` function signature in `server.py` is `async def handler(websocket):` (without `path`) to be compatible with `websockets` v10+.
*   **Client (`ESP32/main.py`):**
    *   MicroPython firmware flashed onto the ESP32.
    *   MicroPython WebSocket client library: `websocket.py` from [this Gist](https://gist.github.com/laurivosandi/2983fe38ad7aff85a5e3b86be8f00718) (needs to be uploaded to ESP32).
    *   Tool for flashing/uploading files (e.g., Thonny, `esptool.py`, `rshell`).

## Setup & Installation

1.  **Clone/Download:** Obtain the project files.
2.  **Server Setup:**
    *   Navigate to the project root directory (`PING_LAMP`).
    *   Create and activate a Python virtual environment.
    *   Install dependencies: `pip install -r requirements.txt`.
    *   **Modify `server.py`:** Change the `handler` function definition to `async def handler(websocket):` (remove the `path` argument) if it's not already updated.
    *   Create and configure the `.env` file (define `PING_TARGET_*`, `SERVER_HOST`, `SERVER_PORT`, `CLIENT_WATCHDOG_TIMEOUT_S`, etc.).
3.  **Client Setup (ESP32):**
    *   Flash MicroPython firmware to the ESP32.
    *   Upload `ESP32/main.py` and the required `websocket.py` library to the ESP32 filesystem.
    *   Edit `ESP32/main.py` (on the ESP32 or before uploading) to set correct `WIFI_SSID`, `WIFI_PASSWORD`, `SERVER_URI`, and GPIO `PIN_NUM_*` constants matching your hardware wiring. Ensure `KEEP_ALIVE_INTERVAL_MS` is set appropriately (e.g., 250-1000ms).

## Hardware Wiring

*   Connect LEDs with appropriate resistors to the GPIO pins defined in `ESP32/main.py` (`PIN_NUM_GREEN`, etc.) and to GND on the ESP32. Verify pin capabilities (PWM support).

## Configuration

*   **Server (`.env` file):** Define `PING_TARGET_*`, WebSocket server host/port, calculation parameters, `CLIENT_WATCHDOG_TIMEOUT_S`, logging level.
*   **Client (`ESP32/main.py` Constants):** Define `WIFI_SSID`, `WIFI_PASSWORD`, `SERVER_URI`, LED GPIO pins, `KEEP_ALIVE_INTERVAL_MS`, interpolation factors, delay detection parameters.

## Usage

1.  Start the Python server: `python server.py`
2.  Power on/reset the ESP32.
3.  Monitor serial output from the ESP32 and console output from the server.
4.  Observe LED behavior. Press CTRL+C in the ESP32's serial terminal to stop the client.

## Troubleshooting

*   **WiFi/WebSocket connection issues:** Check credentials, URIs, server status, firewalls.
*   **LED issues:** Check wiring, pins, resistors, code configuration.
*   **Server `TypeError: handler() missing 1 required positional argument: 'path'`:** The `handler` function definition in `server.py` needs to be updated to `async def handler(websocket):` (remove `path`) to match `websockets` library v10+.
*   **Server logs "Client timed out":** Check client is sending `{"type": "keepalive"}` JSON periodically. Verify client `KEEP_ALIVE_INTERVAL_MS` < server `CLIENT_WATCHDOG_TIMEOUT_S`. Check client logs for errors sending keep-alive.
*   **Server `ping` permission errors (Linux):** Run server with `sudo` or grant `cap_net_raw`.
*   **Server dependency errors:** Ensure virtual environment is active and `requirements.txt` installed correctly.

## License

*   Refer to `LICENSE.TXT`.