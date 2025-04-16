# -*- coding: utf-8 -*-

"""
ESP32 WebSocket Client - Handles WiFi & WebSocket Reconnections

Connects to WiFi, monitors connections, receives latency level,
performs interpolation with decay, sends periodic keep-alives,
and adjusts target level based on message arrival delays.
Allows interruption via CTRL-C.
"""

import machine
import time
import ujson
import gc
import errno
import network
import sys
import uselect
import ucollections # REQUIRED for deque

# --- Library Import ---
# NOTE: Using the provided websocket library structure
try:
    # Use the class/functions directly from the provided code
    from websocket import connect, Websocket, OP_PING, OP_CLOSE, CLOSE_OK, \
                          WebsocketClient, urlparse, URI # Assuming your lib is websocket.py
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    print("ERROR: Failed to import 'websocket.py'. Check filename/location.")
    # If websocket.py contains the classes directly:
    # from websocket import connect, Websocket, OP_PING ... etc
    WEBSOCKETS_AVAILABLE = False
    # machine.reset() # Maybe don't reset immediately, let main check WEBSOCKETS_AVAILABLE

# --- Configuration ---
SERVER_URI = "ws://SERVER_IP:5678" # REQUIRED
WIFI_SSID = "SSID"
WIFI_PASSWORD = "KEY"

CONNECT_TIMEOUT_S = 15
WIFI_CHECK_INTERVAL_S = 30

RECONNECT_DELAY_BASE_S = 1
RECONNECT_DELAY_MAX_S = 30
INTERPOLATION_INTERVAL_MS = 30
LERP_FACTOR = 0.8
DECAY_FACTOR = 0.25
WEBSOCKET_TIMEOUT_S = 1.0 # Timeout for ws.recv()
PULSE_PERIOD_S = 1.0

PIN_NUM_GREEN = 18
PIN_NUM_ORANGE = 19
PIN_NUM_RED = 4
PWM_FREQUENCY = 1000

# --- NEW: Timing & Delay Configuration ---
DELTA_WINDOW_SIZE = 15 # Number of inter-message intervals to average
DEFAULT_EXPECTED_INTERVAL_MS = 100 # Initial guess, will self-level
BASE_DELAY_PENALTY = 5 # Level points to add per expected interval missed
KEEP_ALIVE_INTERVAL_MS = 250 # Send PING every 250ms

# --- Globals ---
ws: WebsocketClient = None # Type hint using imported class
is_websocket_connected = False
wlan = network.WLAN(network.STA_IF)
last_wifi_check_time = time.ticks_ms()

current_duty = { str(p): 0 for p in [PIN_NUM_GREEN, PIN_NUM_ORANGE, PIN_NUM_RED] }
target_duty = { str(p): 0 for p in [PIN_NUM_GREEN, PIN_NUM_ORANGE, PIN_NUM_RED] } # Updated by level_to_target_pwms
pwm_pins = {}
last_interpolation_time = time.ticks_ms()

# Serial input polling
serial_poll = uselect.poll()
serial_poll.register(sys.stdin, uselect.POLLIN)

# --- NEW: Timing & Delay Globals ---
last_valid_message_time_ms = time.ticks_ms()
inter_message_deltas_ms = ucollections.deque((), DELTA_WINDOW_SIZE)
average_delta_time_ms = float(DEFAULT_EXPECTED_INTERVAL_MS)
server_target_level = 0 # Last level received from server
last_keep_alive_sent_time_ms = time.ticks_ms()

# --- PWM Setup ---
try:
    pwm_pins[str(PIN_NUM_GREEN)] = machine.PWM(machine.Pin(PIN_NUM_GREEN), freq=PWM_FREQUENCY, duty_u16=0)
    pwm_pins[str(PIN_NUM_ORANGE)] = machine.PWM(machine.Pin(PIN_NUM_ORANGE), freq=PWM_FREQUENCY, duty_u16=0)
    pwm_pins[str(PIN_NUM_RED)] = machine.PWM(machine.Pin(PIN_NUM_RED), freq=PWM_FREQUENCY, duty_u16=0)
    print("PWM initialized.")
except Exception as e:
    print(f"ERROR: PWM Init failed: {e}")
    machine.reset()

# --- Helper Functions ---
def scale_to_duty_u16(value_8bit): value_8bit = max(0, min(255, value_8bit)); return value_8bit * 257

def level_to_target_pwms(level):
    """Updates the global target_duty dictionary based on the level."""
    global target_duty; target_g_8bit, target_o_8bit, target_r_8bit = 0, 0, 0
    level = max(0, min(100, level)); # Clamp level
    if level <= 50: ratio = level / 50.0; target_g_8bit = int(255 * (1.0 - ratio)); target_o_8bit = int(255 * ratio)
    else: ratio = (level - 50) / 50.0; target_o_8bit = int(255 * (1.0 - ratio)); target_r_8bit = int(255 * ratio)
    target_duty[str(PIN_NUM_GREEN)] = scale_to_duty_u16(target_g_8bit)
    target_duty[str(PIN_NUM_ORANGE)] = scale_to_duty_u16(target_o_8bit)
    target_duty[str(PIN_NUM_RED)] = scale_to_duty_u16(target_r_8bit)

def pulse_red_led():
    # (Code remains the same)
    pwm_pins[str(PIN_NUM_GREEN)].duty_u16(0); pwm_pins[str(PIN_NUM_ORANGE)].duty_u16(0); current_duty[str(PIN_NUM_GREEN)] = 0; current_duty[str(PIN_NUM_ORANGE)] = 0
    cycle_time_ms = PULSE_PERIOD_S * 1000; current_phase = time.ticks_ms() % cycle_time_ms; brightness_ratio = 0.0
    if current_phase < (cycle_time_ms / 2): brightness_ratio = current_phase / (cycle_time_ms / 2)
    else: brightness_ratio = 1.0 - ((current_phase - (cycle_time_ms / 2)) / (cycle_time_ms / 2))
    pulse_value_8bit = int(brightness_ratio * 255); duty = scale_to_duty_u16(pulse_value_8bit)
    pwm_pins[str(PIN_NUM_RED)].duty_u16(duty); current_duty[str(PIN_NUM_RED)] = duty

def interpolate_and_apply_pwm():
    # (Code remains the same - interpolates towards global target_duty)
    global current_duty, target_duty, last_interpolation_time
    now = time.ticks_ms()
    if time.ticks_diff(now, last_interpolation_time) >= INTERPOLATION_INTERVAL_MS:
        last_interpolation_time = now
        green_pin_key = str(PIN_NUM_GREEN)
        for pin_key in pwm_pins.keys():
            # Use the target_duty set by level_to_target_pwms (which now includes delay logic)
            diff = target_duty[pin_key] - current_duty[pin_key]
            if abs(diff) > 1:
                factor_to_use = LERP_FACTOR
                # Apply conditional decay factor
                if diff < 0: # If target value is decreasing
                    if pin_key != green_pin_key: # Check if it's NOT the Green pin
                        factor_to_use = DECAY_FACTOR
                step = int(diff * factor_to_use)
                if step == 0: step = 1 if diff > 0 else -1
                current_duty[pin_key] += step
                current_duty[pin_key] = max(0, min(65535, current_duty[pin_key]))
                pwm_pins[pin_key].duty_u16(current_duty[pin_key])
            # Snap if close
            elif current_duty[pin_key] != target_duty[pin_key]:
                current_duty[pin_key] = target_duty[pin_key]
                pwm_pins[pin_key].duty_u16(current_duty[pin_key])

def ensure_wifi_connected():
    # (Code remains the same)
    global wlan
    if not wlan.isconnected():
        print("WiFi disconnected. Attempting reconnect...")
        if not wlan.active(): wlan.active(True)
        current_config = wlan.config('essid')
        if current_config != WIFI_SSID: print(f"SSID changed. Reconfiguring for '{WIFI_SSID}'.")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        start_time = time.ticks_ms()
        while not wlan.isconnected():
            if time.ticks_diff(time.ticks_ms(), start_time) > CONNECT_TIMEOUT_S * 1000: print("ERROR: WiFi reconnection timed out."); return False
            if check_serial_interrupt(): print("Interrupted during WiFi connect."); return False
            machine.idle(); time.sleep_ms(200)
        print("WiFi reconnected. Network config:", wlan.ifconfig()); time.sleep(1) # Shorter delay
    return True

def check_serial_interrupt():
    # (Code remains the same)
    if serial_poll.poll(0):
        char_code = sys.stdin.read(1)
        if char_code == '\x03': print("CTRL-C detected."); return True
    return False

# --- Main Function ---
def main():
    global ws, is_websocket_connected, last_wifi_check_time
    # --- NEW: Move timing vars into main scope or keep global? ---
    # Keeping global for simplicity, reset on connect
    global last_valid_message_time_ms, inter_message_deltas_ms, average_delta_time_ms
    global server_target_level, last_keep_alive_sent_time_ms

    if not WEBSOCKETS_AVAILABLE:
        print("ERROR: WebSocket library not available. Cannot continue.")
        return

    ws_reconnect_delay_s = RECONNECT_DELAY_BASE_S

    while True:
        # --- Check for Serial Interrupt ---
        if check_serial_interrupt():
            if ws and ws.open: ws.close() # Use ws.open attribute
            for pin_key in pwm_pins: pwm_pins[pin_key].duty_u16(0)
            break # Exit the main loop

        gc.collect()

        if not ensure_wifi_connected():
            if not check_serial_interrupt(): # Only print retry if not interrupted
                print(f"WiFi failed. Retrying checks after {RECONNECT_DELAY_MAX_S}s...")
                if ws and ws.open: ws.close()
                is_websocket_connected = False # Ensure state is correct
                start_wait = time.ticks_ms()
                while time.ticks_diff(time.ticks_ms(), start_wait) < RECONNECT_DELAY_MAX_S * 1000:
                    if check_serial_interrupt(): break
                    pulse_red_led(); time.sleep_ms(50)
                if check_serial_interrupt(): break
            continue

        # --- WebSocket Connection Logic ---
        if ws is None or not ws.open: # Check ws.open state
            if is_websocket_connected: print("WebSocket disconnected."); is_websocket_connected = False
            pulse_red_led() # Indicate connection attempt visually
            try:
                print(f"Attempting WebSocket connection to {SERVER_URI}...")
                # Use the connect function from the imported library
                ws = connect(SERVER_URI)
                ws.settimeout(WEBSOCKET_TIMEOUT_S)
                print("WebSocket connected.")
                is_websocket_connected = True
                ws_reconnect_delay_s = RECONNECT_DELAY_BASE_S
                last_wifi_check_time = time.ticks_ms()

                # --- NEW: Reset timing variables on successful connection ---
                now_ms_init = time.ticks_ms()
                last_valid_message_time_ms = now_ms_init
                # Clear the deque - create a new empty one
                inter_message_deltas_ms = ucollections.deque((), DELTA_WINDOW_SIZE)
                average_delta_time_ms = float(DEFAULT_EXPECTED_INTERVAL_MS)
                server_target_level = 0 # Reset to default level
                last_keep_alive_sent_time_ms = now_ms_init
                # ---------------------------------------------------------

            except Exception as e:
                print(f"ERROR: WebSocket connection failed: {e}"); ws = None; is_websocket_connected = False
                print(f"Retrying WS connection in {ws_reconnect_delay_s}s...")
                start_wait = time.ticks_ms()
                while time.ticks_diff(time.ticks_ms(), start_wait) < ws_reconnect_delay_s * 1000:
                    if check_serial_interrupt(): break
                    pulse_red_led(); time.sleep_ms(50)
                if check_serial_interrupt(): break
                ws_reconnect_delay_s = min(ws_reconnect_delay_s * 2, RECONNECT_DELAY_MAX_S)
                continue # Skip rest of loop iteration

        # --- WebSocket Operations (If Connected) ---
        if is_websocket_connected:
            now_ms = time.ticks_ms()
            msg = None
            received_valid_message_this_cycle = False # Flag

            # --- 1. Receive Message ---
            try:
                # Periodic WiFi Check (can stay here)
                if time.ticks_diff(now_ms, last_wifi_check_time) > WIFI_CHECK_INTERVAL_S * 1000:
                    last_wifi_check_time = now_ms
                    if not wlan.isconnected():
                        print("WiFi connection lost during operation.")
                        ws.close(); ws = None; is_websocket_connected = False; continue

                # Attempt to receive (handle timeout)
                msg = ws.recv() # Blocks for WEBSOCKET_TIMEOUT_S

                if msg is not None and len(msg) > 0:
                    # Process received message
                    try:
                        if isinstance(msg, str): # Should be text for JSON
                            data = ujson.loads(msg)
                            received_level = data.get("level")
                            print(f"WS-Data: level={received_level}") # Simpler log

                            # --- NEW: Update Timing ---
                            current_time_ms = time.ticks_ms() # Get fresh time
                            current_delta_ms = time.ticks_diff(current_time_ms, last_valid_message_time_ms)
                            last_valid_message_time_ms = current_time_ms

                            inter_message_deltas_ms.append(current_delta_ms) # Add to deque

                            # Recalculate average (avoid division by zero)
                            if len(inter_message_deltas_ms) > 0:
                                avg = sum(inter_message_deltas_ms) / len(inter_message_deltas_ms)
                                # Ensure average isn't unreasonably small
                                average_delta_time_ms = max(avg, INTERPOLATION_INTERVAL_MS)
                            # else: keep the default/previous average if deque is empty

                            # Update server target level
                            if received_level is not None and isinstance(received_level, (int, float)):
                                server_target_level = int(received_level)
                                received_valid_message_this_cycle = True # Mark success
                            else:
                                print(f"Warning: Invalid/missing 'level': {data}")

                            # --- REMOVED direct call to level_to_target_pwms ---

                        # Handle non-string or empty messages if needed
                        # else: print(f"Warning: Received non-string/empty data: {type(msg)}")

                    except (ValueError, TypeError) as e: print(f"ERROR: JSON parse failed: {e} - Received: {msg[:100]}")
                    except Exception as e: print(f"ERROR: Message processing error: {e}")

                elif msg is None: # Socket closed by server OR library indicates close frame received
                    print("WebSocket closed by server or CLOSE frame received.")
                    ws.close(); ws = None; is_websocket_connected = False; continue

            except OSError as e:
                if e.args[0] == errno.ETIMEDOUT: pass # Expected timeout, means no message arrived
                elif e.args[0] == errno.ECONNRESET: print("ERROR: WS Connection reset."); ws.close(); ws = None; is_websocket_connected = False; continue
                else: print(f"ERROR: WebSocket OSError: {e}"); ws.close(); ws = None; is_websocket_connected = False; continue
            except Exception as e: print(f"ERROR: WebSocket general error: {e}"); ws.close(); ws = None; is_websocket_connected = False; continue

            # --- 2. Calculate Delay Adjustment & Final Target Level ---
            # This runs every loop cycle if connected
            if is_websocket_connected: # Check connection again, might have dropped in recv block
                now_for_delay_calc = time.ticks_ms()
                time_since_last_ms = time.ticks_diff(now_for_delay_calc, last_valid_message_time_ms)

                level_adjustment = 0
                if average_delta_time_ms > 0: # Avoid division by zero
                    # Use a slightly higher floor for threshold check to avoid noise
                    threshold_ms = max(average_delta_time_ms * 1.1, DEFAULT_EXPECTED_INTERVAL_MS * 0.8)
                    if time_since_last_ms > threshold_ms:
                         # Calculate how many average intervals have been missed
                         intervals_missed = time_since_last_ms / average_delta_time_ms
                         level_adjustment = max(0, intervals_missed * BASE_DELAY_PENALTY)
                         # print(f"DEBUG: Delay detected! Since last: {time_since_last_ms}ms > {threshold_ms}ms. Adj: {level_adjustment}")

                # Determine final target level
                final_target_level = min(100, server_target_level + int(level_adjustment))

                # Update the global target duty cycles for interpolation
                level_to_target_pwms(final_target_level)

                # --- 3. Send Application Keep-Alive --- # <-- Renamed section
                # Check if websocket object 'ws' exists and is open before sending
                if ws and ws.open and time.ticks_diff(now_for_delay_calc, last_keep_alive_sent_time_ms) >= KEEP_ALIVE_INTERVAL_MS:
                    try:
                        keep_alive_msg = ujson.dumps({"type": "keepalive"})
                        # Use the send method of your WebsocketClient class
                        ws.send(keep_alive_msg)             # <--- SEND JSON
                        print("Sent Keep-Alive JSON")       # <--- Log indicates JSON sent
                        last_keep_alive_sent_time_ms = now_for_delay_calc
                    except Exception as e:
                        print(f"ERROR: Failed to send keep-alive: {e}")
                        # ws.close(); ws = None; is_websocket_connected = False; continue # Consider reconnect

                # --- 4. Interpolate towards the final target ---
                interpolate_and_apply_pwm()

        # --- Loop Delay ---
        if not is_websocket_connected:
            pulse_red_led() # Pulse red if WS disconnected
            time.sleep_ms(50)
        else:
            # Shorter sleep when connected, ensure it's not zero
            time.sleep_ms(max(5, INTERPOLATION_INTERVAL_MS // 2))


# --- Entry Point ---
if __name__ == "__main__":
    # --- Print Configuration Details ---
    print("---------------------------------------------------")
    print("ESP32 Latency Visualizer Client Starting...")
    print(f"Target WiFi SSID: {WIFI_SSID}")
    print(f"Target Server URI: {SERVER_URI}")
    print(f"Keep-Alive Interval: {KEEP_ALIVE_INTERVAL_MS}ms")
    print("(Handles reconnections, decay, keep-alives, delay detection)")
    print("(Press CTRL+C to stop script)")
    print("---------------------------------------------------")

    try:
        main()
    except KeyboardInterrupt:
        print("KeyboardInterrupt caught. Exiting gracefully.")
    finally:
        # Ensure LEDs are off and resources released
        try:
            if ws and ws.open: ws.close()
        except Exception: pass
        try:
            for pin_key in pwm_pins: pwm_pins[pin_key].deinit()
            print("PWM deinitialized.")
        except Exception as e: print(f"Error during PWM deinit: {e}")
        print("Script finished.")

