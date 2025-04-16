#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Latency Monitoring Server (Two Overlapping Systems Model) - WITH WATCHDOG

Pings targets, calculates levels, combines results.
Broadcasts via WebSocket, BUT pauses sending to clients
that haven't sent a keep-alive recently (watchdog).
"""

import asyncio
import collections
import datetime
import json
import logging
import os
import platform
import subprocess
import time
from dataclasses import dataclass, field
# Typing imports adjusted for Python 3.8+ compatibility if needed
from typing import Deque, Dict, List, Optional, Tuple, Any, Set

import numpy as np
from dotenv import load_dotenv
# Correct imports for modern websockets library
from websockets import serve, WebSocketServerProtocol
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)
# Default level, AppConfig might override
logger.setLevel(logging.INFO)

# --- Configuration Loading & Defaults ---
load_dotenv()

@dataclass
class TargetConfig:
    # (No changes needed)
    name: str; host: str; interval_s: float; ping_timeout_s: int = 1

@dataclass
class AppConfig:
    """Application configuration."""
    # (Targets - Load dynamically - No changes needed)
    targets: Dict[str, TargetConfig] = field(default_factory=dict)

    # (Windows - No changes needed)
    short_window_s: float = float(os.getenv("SHORT_WINDOW_S", 1.5))
    long_window_s: float = float(os.getenv("LONG_WINDOW_S", 180))

    # (Intervals - No changes needed)
    aggregation_interval_s: float = float(os.getenv("AGGREGATION_INTERVAL_S", 0.05)) # 50ms
    long_term_calc_interval_s: float = float(os.getenv("LONG_TERM_CALC_INTERVAL_S", 10))

    # (Mapping Thresholds - No changes needed)
    z_score_orange: float = float(os.getenv("Z_SCORE_ORANGE_THRESHOLD", 1.5))
    z_score_red: float = float(os.getenv("Z_SCORE_RED_THRESHOLD", 3.0))
    abs_red_short_ms: float = float(os.getenv("ABS_RED_SHORT_TERM_MS", 40.0))
    min_std_dev_ms: float = float(os.getenv("MIN_STD_DEV_MS", 1.0))
    avg_orange_ms: float = float(os.getenv("AVG_ORANGE_THRESHOLD_MS", 15.0))
    avg_red_ms: float = float(os.getenv("AVG_RED_THRESHOLD_MS", 30.0))

    # Server
    server_host: str = os.getenv("SERVER_HOST", "0.0.0.0")
    server_port: int = int(os.getenv("SERVER_PORT", 5678))
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # --- NEW: Watchdog Configuration ---
    client_watchdog_timeout_s: float = float(os.getenv("CLIENT_WATCHDOG_TIMEOUT_S", 1.5)) # e.g., 1.5 seconds

    def __post_init__(self):
        # (Target loading logic remains the same)
        i = 1
        while True:
            host_key = f"PING_TARGET_{i}_HOST"; interval_key = f"PING_TARGET_{i}_INTERVAL_S"
            host = os.getenv(host_key); interval_str = os.getenv(interval_key)
            if host and interval_str:
                try:
                    interval = float(interval_str); target_name = f"T{i}"
                    self.targets[target_name] = TargetConfig(name=target_name, host=host, interval_s=interval)
                    logger.info(f"Loaded target {target_name}: host={host}, interval={interval}s")
                    i += 1
                except ValueError: logger.error(f"Invalid interval {interval_key}: {interval_str}"); break
            else: break
        if not self.targets: logger.warning("No PING_TARGET_* env vars found.")


# --- Globals & State ---
@dataclass
class TargetState:
     # (No changes needed)
    config: TargetConfig
    history_short: Deque[Tuple[float, Optional[float]]] = field(default_factory=collections.deque)
    history_long: Deque[Tuple[float, Optional[float]]] = field(default_factory=collections.deque)
    latest_mean_long: Optional[float] = None
    current_latency: Optional[float] = None

    def __post_init__(self):
        # (Deque init remains the same)
        short_maxlen = int(APP_CONFIG.short_window_s / self.config.interval_s) + 10
        long_maxlen = int(APP_CONFIG.long_window_s / self.config.interval_s) + 10
        self.history_short = collections.deque(maxlen=short_maxlen)
        self.history_long = collections.deque(maxlen=long_maxlen)

# --- Global Variables ---
APP_CONFIG = AppConfig()
TARGET_STATES: Dict[str, TargetState] = {name: TargetState(cfg) for name, cfg in APP_CONFIG.targets.items()}

# --- NEW: Client Tracking Dictionary ---
# Store client connection object as key, dictionary with state as value
# Example: {websocket_conn: {'last_keepalive_time': 12345.67}}
CONNECTED_CLIENTS: Dict[WebSocketServerProtocol, Dict[str, Any]] = {}

# --- Logging Setup ---
logging.basicConfig(
    level=APP_CONFIG.log_level,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("LatencyServerWatchdog") # Renamed logger

# --- Helper Functions ---
# (parse_ping_output, get_valid_latencies, calculate_stats_short,
#  calculate_mean_long, map_level_short, map_level_long - all remain unchanged)
def parse_ping_output(output: str, os_platform: str) -> Optional[float]:
    rtt_line = None; time_line = None; lines = output.strip().splitlines()
    for line in lines:
        if "rtt min/avg/max/mdev" in line: rtt_line = line; break
        elif "time=" in line and "bytes from" in line: time_line = line
    try:
        if os_platform in ["linux", "darwin"]:
            if rtt_line: parts = rtt_line.split("=")[1].strip().split(" ")[0].split("/"); return float(parts[1])
            elif time_line: time_part = time_line.split("time=")[1]; return float(time_part.split(" ")[0].strip())
        elif os_platform == "windows":
             avg_line = next((ln for ln in lines if "Average =" in ln), None); reply_line = next((ln for ln in lines if "Reply from" in ln and "time=" in ln), None)
             if avg_line: avg_part = avg_line.split("Average =")[1]; return float(avg_part.split("ms")[0].strip())
             elif reply_line: time_part = reply_line.split("time=")[1]; return float(time_part.split("ms")[0].strip())
        logger.debug(f"Could not extract latency from:\n{output}"); return None
    except (IndexError, ValueError, TypeError) as e: logger.error(f"Error parsing line '{rtt_line or time_line}': {e}"); return None
def get_valid_latencies(history_deque: Deque[Tuple[float, Optional[float]]], window_s: float) -> List[float]:
    now = time.monotonic(); valid_latencies = []
    for timestamp, latency in reversed(history_deque):
        if (now - timestamp) > window_s: break
        if latency is not None: valid_latencies.append(latency)
    valid_latencies.reverse(); return valid_latencies
def calculate_stats_short(latencies: List[float]) -> Tuple[Optional[float], Optional[float]]:
    if not latencies: return None, None
    try: mean = np.mean(latencies); std_dev = np.std(latencies); return mean, std_dev
    except Exception as e: logger.error(f"Numpy error (short): {e}"); return None, None
def calculate_mean_long(latencies: List[float]) -> Optional[float]:
    if not latencies: return None
    try: return np.mean(latencies)
    except Exception as e: logger.error(f"Numpy error (long): {e}"); return None
def map_level_short(current_avg: Optional[float], mean_short: Optional[float], std_dev_short: Optional[float], config: AppConfig) -> int:
    level = 0;
    if current_avg is None or mean_short is None or std_dev_short is None: return 50
    if current_avg >= config.abs_red_short_ms: return 100
    effective_std_dev = max(std_dev_short, config.min_std_dev_ms)
    if effective_std_dev == 0: return 0
    z_score = (current_avg - mean_short) / effective_std_dev
    if z_score >= config.z_score_red: level = 90 + int(10 * min(1.0, (z_score - config.z_score_red) / 2.0))
    elif z_score >= config.z_score_orange: level = 50 + int(39 * (z_score - config.z_score_orange) / (config.z_score_red - config.z_score_orange))
    else: level = max(0, int(49 * (z_score + 1) / (config.z_score_orange + 1) ))
    return max(0, min(100, level))
def map_level_long(mean_long: Optional[float], config: AppConfig) -> int:
    level = 0
    if mean_long is None: return 50
    if mean_long >= config.avg_red_ms: level = 90 + int(10 * min(1.0, (mean_long - config.avg_red_ms) / (config.avg_red_ms * 0.5)))
    elif mean_long >= config.avg_orange_ms: level = 50 + int(39 * (mean_long - config.avg_orange_ms) / (config.avg_red_ms - config.avg_orange_ms))
    else: level = max(0, int(49 * (mean_long / config.avg_orange_ms)))
    return max(0, min(100, level))


# --- Core Logic Tasks ---
# (ping_target and calculate_long_term_stats remain unchanged)
async def ping_target(target_config: TargetConfig, state: TargetState):
    os_platform = platform.system().lower(); logger.info(f"Starting ping task for {target_config.name} ({target_config.host}) every {target_config.interval_s}s")
    while True:
        start_time = time.monotonic(); latency = None
        try:
            if os_platform == "windows": cmd = ["ping", "-n", "1", "-w", str(target_config.ping_timeout_s * 1000), target_config.host]
            else: cmd = ["ping", "-c", "1", "-W", str(target_config.ping_timeout_s), "-i", "0.2", target_config.host]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                output = stdout.decode('utf-8', errors='ignore'); latency = parse_ping_output(output, os_platform)
                if latency is not None: state.current_latency = latency # Removed debug log
                else: logger.warning(f"Ping {target_config.name} OK but parsing failed.")
            else:
                stderr_output = stderr.decode('utf-8', errors='ignore').strip()
                if "Operation not permitted" in stderr_output: logger.error(f"Ping {target_config.name} failed: Permission Denied.")
                else: logger.warning(f"Ping {target_config.name} failed (code {proc.returncode}): {stderr_output}")
                state.current_latency = None
        except FileNotFoundError: logger.error(f"Ping command not found for {target_config.name}."); state.current_latency = None
        except Exception as e: logger.error(f"Error pinging {target_config.name}: {e}"); state.current_latency = None
        current_time = time.monotonic(); result = (current_time, latency)
        state.history_short.append(result); state.history_long.append(result)
        elapsed_time = time.monotonic() - start_time; sleep_duration = max(0, target_config.interval_s - elapsed_time)
        await asyncio.sleep(sleep_duration)

async def calculate_long_term_stats():
    logger.info(f"Starting long-term stats calculation task every {APP_CONFIG.long_term_calc_interval_s}s")
    while True:
        await asyncio.sleep(APP_CONFIG.long_term_calc_interval_s); # logger.debug("Calculating long-term stats...")
        for name, state in TARGET_STATES.items():
            try:
                long_latencies = get_valid_latencies(state.history_long, APP_CONFIG.long_window_s)
                mean_long = calculate_mean_long(long_latencies); state.latest_mean_long = mean_long
                # logger.debug(f"Updated {name} long-term mean: {mean_long:.2f}ms") # Verbose
            except Exception as e: logger.error(f"Error in long-term stats for {name}: {e}")


# --- MODIFIED: Aggregate and Broadcast Task with Watchdog ---
async def aggregate_and_broadcast():
    """Calculates levels, combines, and broadcasts ONLY to responsive clients."""
    logger.info(f"Starting aggregation and watchdog broadcast task every {APP_CONFIG.aggregation_interval_s}s")
    logger.info(f"Client Watchdog Timeout: {APP_CONFIG.client_watchdog_timeout_s}s")

    while True:
        start_agg_time = time.monotonic()
        final_level = 0 # Default to Green

        # --- Aggregation Logic (Mostly Unchanged) ---
        if not TARGET_STATES:
             logger.debug("No targets configured, skipping aggregation.")
             await asyncio.sleep(APP_CONFIG.aggregation_interval_s)
             continue

        for name, state in TARGET_STATES.items():
            try:
                short_latencies = get_valid_latencies(state.history_short, APP_CONFIG.short_window_s)
                mean_short, std_dev_short = calculate_stats_short(short_latencies)
                level_short = map_level_short(state.current_latency, mean_short, std_dev_short, APP_CONFIG)

                mean_long = state.latest_mean_long
                level_long = map_level_long(mean_long, APP_CONFIG)

                target_level = max(level_short, level_long)
                # logger.debug(f"{name}: Short={level_short}, Long={level_long} -> Target={target_level}") # Verbose

                final_level = max(final_level, target_level)

            except Exception as e:
                 logger.error(f"Error during aggregation for target {name}: {e}", exc_info=False) # Less noisy logs
                 final_level = max(final_level, 50) # Default to Orange on error for a target
        # --- End Aggregation ---


        # --- Prepare Message ---
        # Use monotonic time for server-internal comparisons, ISO for message payload
        current_server_time = time.monotonic()
        timestamp_iso = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
        # Include monotonic time for client-side filtering if still desired
        message_dict = {
            "timestamp": timestamp_iso,
             # Adding monotonic clock for potential client-side filtering/sync
             # Optional: remove if client doesn't use it
            "server_mono_ts": current_server_time,
            "level": final_level
        }
        message_json = json.dumps(message_dict)


        # --- Watchdog Broadcast ---
        # Create a list of clients to send to (avoids modifying dict while iterating)
        clients_to_send_to: List[WebSocketServerProtocol] = []
        clients_timed_out = 0

        # Check responsiveness *before* trying to send
        for client_ws, client_state in CONNECTED_CLIENTS.items():
            time_since_last_keepalive = current_server_time - client_state.get('last_keepalive_time', 0)

            if time_since_last_keepalive <= APP_CONFIG.client_watchdog_timeout_s:
                clients_to_send_to.append(client_ws)
            else:
                clients_timed_out += 1
                logger.warning(f"Client {client_ws.remote_address} timed out "
                              f"({time_since_last_keepalive:.1f}s > {APP_CONFIG.client_watchdog_timeout_s}s). "
                              f"Skipping send.")

        if clients_timed_out > 0:
             logger.info(f"Broadcasting Level: {final_level} to {len(clients_to_send_to)} clients "
                         f"({clients_timed_out} timed out).")
        elif clients_to_send_to:
            logger.debug(f"Broadcasting Level: {final_level} to {len(clients_to_send_to)} clients.")


        # --- Send concurrently (more efficient for multiple clients) ---
        if clients_to_send_to:
            tasks = [client.send(message_json) for client in clients_to_send_to]
            # gather results, capture exceptions per task
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Optional: Log errors from sending if needed
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    # Log the error, but often ConnectionClosed is expected
                    client_ws = clients_to_send_to[i] # Get corresponding client
                    if not isinstance(result, ConnectionClosed): # Log unexpected errors
                        logger.error(f"Error sending to client {client_ws.remote_address}: {result}")
                    # Note: The main handler will deal with removing the client if closed


        # --- Accurate Sleep ---
        elapsed_agg_time = time.monotonic() - start_agg_time
        sleep_agg_duration = max(0, APP_CONFIG.aggregation_interval_s - elapsed_agg_time)
        if sleep_agg_duration == 0 and len(TARGET_STATES) > 0:
            logger.warning(f"Aggregation loop duration ({elapsed_agg_time:.4f}s) >= interval ({APP_CONFIG.aggregation_interval_s}s).")
        await asyncio.sleep(sleep_agg_duration)


# --- WebSocket Connection Handler ---
async def handler(websocket: WebSocketServerProtocol):
    """Handles WebSocket client connections and processes keep-alives."""
    remote_addr = websocket.remote_address

    # Register client with initial keep-alive time
    client_state = {'last_keepalive_time': time.monotonic()}
    CONNECTED_CLIENTS[websocket] = client_state

    try:
        # Loop indefinitely processing messages from the client
        async for message in websocket:
            try:
                data = json.loads(message)
                # Check if it's our application-level keepalive
                if isinstance(data, dict) and data.get("type") == "keepalive":
                    logger.debug(f"Keepalive received from {remote_addr}")
                    client_state['last_keepalive_time'] = time.monotonic()
                    # Optional: Send immediate state update upon receiving keepalive?
                    # Might be useful if client was paused. Requires getting latest state.
                else:
                    # Handle other potential message types from client if needed
                    logger.debug(f"Received other message from {remote_addr}: {data}")

            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received from {remote_addr}: {message[:100]}")
            except Exception as e:
                 # Catch errors processing a specific message but keep connection open
                 logger.error(f"Error processing message from {remote_addr}: {e}", exc_info=False)

    except ConnectionClosed:
        logger.info(f"Client connection closed normally: {remote_addr}")
    except Exception as e:
        # Log errors related to the connection itself
        logger.error(f"Client connection error {remote_addr}: {e}", exc_info=False)
    finally:
        # Unregister client regardless of how the connection ended
        logger.info(f"Client disconnected: {remote_addr}")
        CONNECTED_CLIENTS.pop(websocket, None) # Remove safely


# --- Main Function ---
async def main():
    # (No changes needed in main setup logic)
    if not APP_CONFIG.targets: logger.critical("No targets configured. Exiting."); return
    logger.info("Initializing target states...")
    ping_tasks = [asyncio.create_task(ping_target(state.config, state)) for state in TARGET_STATES.values()]
    long_term_task = asyncio.create_task(calculate_long_term_stats())
    broadcast_task = asyncio.create_task(aggregate_and_broadcast())

    # Use the modified handler
    async with serve(handler, APP_CONFIG.server_host, APP_CONFIG.server_port) as server:
        logger.info(f"WebSocket server started on ws://{APP_CONFIG.server_host}:{APP_CONFIG.server_port}")
        await asyncio.gather(long_term_task, broadcast_task, *ping_tasks)

# --- Entry Point ---
if __name__ == "__main__":
    # (No changes needed)
    if not APP_CONFIG.targets: logger.critical("No targets loaded. Check .env file."); exit(1)
    try: asyncio.run(main())
    except KeyboardInterrupt: logger.info("Server stopped manually.")
    except Exception as e: logger.critical(f"Server critical error: {e}", exc_info=True)