# Ping Lamp XVU: Assembly and Operating Manual

For driver board v1.0 and the printed base ring. Technical data: [datasheet](datasheet.md).

> **Read first.** No unit has been built yet. This manual describes the intended procedure; it
> has not been walked through on real hardware. Steps that depend on an unconfirmed property
> of the tower are marked **[verify]**.

## 1. Safety and intended use

- The lamp works with 5 V and 24 V DC only. Connect only a Harmony XVU tower whose units are
  marked **24 V AC/DC**. Never connect units marked 100 to 240 V AC.
- It is an indicator for a desk or shelf, indoors. Do not use it as a safety, alarm or process
  signal.
- Unplug the USB cable before opening the base or touching the wiring.
- Use a USB charger rated for 1 A or more. Do not supply the "5V IN" pads and the USB socket
  from two different supplies at once.
- Keep metal away from the antenna end of the board (opposite side to the terminal block). A
  metal base plate weakens the Wi-Fi link.
- The lamp has not been tested for EMC or product safety.

## 2. What is needed

### Parts

| Qty | Part | Note |
|---|---|---|
| 1 | Driver board, assembled | Ordered as described in section 3 |
| 1 | Screw terminal block, 5 positions, 3.5 mm pitch, through-hole | Phoenix PT 1,5/5-3.5-H or equivalent |
| 1 | Printed tray and lid | `enclosure/*.stl`, after adapting the tower interface |
| 1 | Harmony XVU tower: base, green, orange and red 24 V AC/DC units | |
| 4 | Countersunk screw M3 x 25 | Nylon at the two holes next to the antenna is preferable |
| 2 | Countersunk wood screw, 3.5 to 4 mm | Tray to base plate |
| n | Screws for the tower base | Default model: 3 x M4, at most 8 mm of thread below the tower base |
| 4 | Wires 0.25 to 0.5 mm2, about 120 mm each | Board to tower |
| 1 | USB-C cable and USB charger, 1 A or more | Right-angle plug keeps the cable close to the ring |
| 1 | Base plate | Wood or another non-metal material |

### Tools and software

- Soldering iron, small screwdrivers, multimeter, 3D printer.
- A computer with Python 3.8 or later, for the latency server and for flashing.
- `esptool` and `mpremote` (installed with pip), MicroPython firmware for ESP32-C3, and the
  `websocket.py` client library named in the repository README.

## 3. Ordering the board

Orders are placed by hand with a board assembler; the repository does not place them.

1. Upload `hardware/pcb/fab/ping_lamp_gerber.zip`. 2 layers, 1.6 mm.
2. Select SMT assembly, top side, and upload `ping_lamp_bom.csv` and `ping_lamp_cpl.csv`.
3. Check every matched part against the "LCSC number check" column of the parts list.
4. **Do not order if R8 (390 k) is unmatched or replaced by another value.** It sets the
   24 V output; without it the converter destroys itself at first power-up.
5. Check the rotation of all polarised parts in the placement preview. U3 and U4 are the
   critical ones: they fit their pads when turned by 180 degrees. Pin 1 is marked on the board.

**Before ordering [verify]:** test one tower unit with a 24 V supply and a MOSFET switched at
1 kHz. If the unit does not dim, or only lights with the common wire on 0 V, the board will
not give a smooth fade, or will not drive the tower at all. See section 9.

## 4. Preparing the mechanical parts

1. Measure the tower base: outer diameter, cable hole diameter, number of fixing screws, their
   bolt circle and thread.
2. Enter the values in `hardware/enclosure/ping_lamp_base.scad` (`tower_d`,
   `tower_cable_hole_d`, `tower_bolt_count`, `tower_bolt_circle`, `tower_bolt_angle`).
   OpenSCAD reports an error if a tower screw would hit a spacer tube. Keep the tower screws
   away from the antenna side as well.
3. Export and print both parts. Tray as modelled, lid upside down, no supports, 0.2 mm layers,
   3 or more perimeters, PETG or PLA.
4. Drill the base plate for the two tray screws. For a hidden cable, also set
   `floor_cable_hole_d`, drill the plate at the same position and cut a groove underneath.

## 5. Assembly

### 5.1 Board

1. Solder the terminal block J2 on the component side, **wire entry towards the board centre**.
2. Only for a cable through the base plate: solder the cable to J4 (square pad +5 V, round
   pad GND). Leave J3 empty unless a sensor or button is added.

### 5.2 First power-up, on the bench

Do this before the board goes into the ring. The tower is not connected yet.

1. Plug in USB. Measure 3.3 V between J3 pin 3 and pin 4.
2. Put the board in download mode: hold BOOT, press and release RESET, release BOOT.
3. Erase and flash MicroPython. Replace the port name with the one on the computer
   (Linux `/dev/ttyACM0`, macOS `/dev/cu.usbmodem...`, Windows `COM...`):

   ```bash
   esptool.py --chip esp32c3 --port /dev/ttyACM0 erase_flash
   ```

   ```bash
   esptool.py --chip esp32c3 --port /dev/ttyACM0 --baud 460800 write_flash -z 0x0 ESP32_GENERIC_C3.bin
   ```

4. Press RESET. Open the console and switch the 24 V rail on:

   ```bash
   mpremote connect /dev/ttyACM0 repl
   ```

   ```python
   from machine import Pin; Pin(10, Pin.OUT, value=1)
   ```

5. Measure between the "24V" terminal and GND (J3 pin 4). Expected: 23 to 25 V.
   Without the enable command about 4.5 V is normal.
6. Unplug USB.

### 5.3 Firmware

1. In `ESP32/main.py` set:

   | Constant | Value |
   |---|---|
   | `WIFI_SSID`, `WIFI_PASSWORD` | Wi-Fi access data |
   | `SERVER_URI` | `ws://<address of the server computer>:5678` |
   | `PIN_NUM_GREEN` | `4` |
   | `PIN_NUM_ORANGE` | `5` |
   | `PIN_NUM_RED` | `6` |
   | `PIN_NUM_BOOST_EN` | `10` |

   The values in the file as delivered are for the older breadboard version. On this board
   they would put the LED signals on the USB pins.

2. Copy the library and the program to the board:

   ```bash
   mpremote connect /dev/ttyACM0 cp websocket.py :websocket.py
   ```

   ```bash
   mpremote connect /dev/ttyACM0 cp ESP32/main.py :main.py
   ```

The program has so far run on a classic ESP32 only. Running it on the ESP32-C3 build of
MicroPython is untested.

### 5.4 Wiring and closing the ring

1. Screw the tray to the base plate with the two wood screws.
2. Connect four wires to J2 and tighten them:

   | Terminal | Goes to |
   |---|---|
   | 24V | Common terminal of the tower base |
   | G | Green unit |
   | O | Orange unit |
   | R | Red unit |
   | AUX | Empty, or a fourth unit such as a buzzer |

3. Lower the board into the tray, USB socket into the wall opening.
4. Feed the wires through the centre hole of the lid. Put the lid on and fit the four M3
   screws. Tighten them gently; they clamp the board through the spacer tubes.
5. Lay the wire slack to one side so that it does not rest on the BOOT and RESET buttons
   below the centre hole. A wire pressing on RESET keeps the lamp off.
6. Screw the tower base to the lid, connect the wires to the tower terminals according to the
   tower's own wiring diagram **[verify]**, and stack the light units.

## 6. Latency server

The lamp shows what a small Python program on a computer in the same network measures. Set-up
is described in the repository README; in short:

```bash
pip install -r requirements.txt
```

```bash
python server.py
```

The server reads its settings from the `.env` file:

| Setting | Meaning | Default |
|---|---|---|
| `PING_TARGET_1_HOST`, `PING_TARGET_1_INTERVAL_S`, `..._2_...` | Hosts to ping and how often | none, at least one is required |
| `SERVER_PORT` | WebSocket port the lamp connects to | 5678 |
| `AVG_ORANGE_THRESHOLD_MS`, `AVG_RED_THRESHOLD_MS` | Long-term average latency for orange and red | 15, 30 |
| `ABS_RED_SHORT_TERM_MS` | A single latency at or above this is red at once | 40 |
| `Z_SCORE_ORANGE_THRESHOLD`, `Z_SCORE_RED_THRESHOLD` | Sensitivity to sudden deviations | 1.5, 3.0 |
| `CLIENT_WATCHDOG_TIMEOUT_S` | Lamp counts as absent after this silence | 1.5 |

On Linux the `ping` command may need extra rights; see the troubleshooting section of the
repository README.

## 7. Operation

Plug in the USB cable. The lamp connects to the Wi-Fi network and to the server on its own
and reconnects after an interruption.

| Tower shows | Meaning |
|---|---|
| Green | Latency normal (level 0) |
| Green and orange mixed | Latency rising (level 1 to 49) |
| Orange | Latency elevated, or a ping target does not answer (level 50) |
| Orange and red mixed | Latency high (level 51 to 99) |
| Red | Latency very high (level 100) |
| Red pulsing once per second | No Wi-Fi, or the server cannot be reached |
| Dark | No power, 24 V rail not enabled, or the lamp is held in reset |

- The server sends a level from 0 to 100 about 20 times per second. The lamp fades towards it;
  orange and red fade out more slowly than they come up, so short spikes stay visible.
- If messages from the server arrive late, the lamp raises the level by itself. A stalled
  connection therefore turns the lamp towards red even before it is declared lost.
- The small red LED on the board is not used by the current program.

### Buttons

Both are under the centre hole of the lid and can be reached with a thin non-metal rod when the
tower base is off.

| Action | Effect |
|---|---|
| RESET | Restarts the lamp |
| Hold BOOT, tap RESET, release BOOT | USB download mode for flashing new firmware |

### Changing settings

Connect USB to a computer, edit the constants at the top of `main.py` and copy the file again
as in section 5.3. Useful ones: `PWM_FREQUENCY`, `LERP_FACTOR` and `DECAY_FACTOR` (fade speed),
`PULSE_PERIOD_S`.

## 8. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Nothing happens, no USB device appears | Charge-only cable, or fuse tripped by a short | Use a data cable. Unplug for a minute, check the wiring for shorts |
| 3.3 V present, tower dark, "24V" at about 4.5 V | 24 V rail not enabled | Check `PIN_NUM_BOOST_EN = 10` in `main.py` |
| "24V" at 23 to 25 V, a tier stays dark with its output on | Unit needs the opposite polarity, or wiring fault | Check the wiring. If the unit only lights with common on 0 V, the board cannot drive it; see section 9 |
| Tiers flicker or do not fade, only switch | The units do not accept PWM dimming | Lower `PWM_FREQUENCY` to 100 to 200. If that does not help, the firmware needs stepped on/off states |
| Red pulsing all the time | Wrong Wi-Fi data, wrong `SERVER_URI`, server not running, firewall | Read the console with `mpremote`, check the server log |
| Lamp restarts when all tiers light | USB source too weak | Use a charger rated for 1 A or more |
| Lamp does not start after closing the lid | A wire rests on RESET or BOOT | Re-lay the wire slack |
| Weak or unstable Wi-Fi | Metal near the antenna | Nylon screws at the two holes beside the antenna, no metal plate, turn the antenna side towards the access point |
| Server log shows "Client timed out" | Lamp not sending keep-alives | Check the lamp console; see the repository README |
| Board not recognised for flashing | Not in download mode | Hold BOOT, tap RESET, release BOOT, then run `esptool` |

## 9. Known limitations

- **Dimming and polarity of the XVU units are unconfirmed.** Both decide whether the lamp
  works as described. Test one unit before ordering the board.
- All three tiers on at once draw about 1 A from USB. That is a test condition, not a
  continuous operating mode; the fuse may trip in a warm housing.
- The 24 V rail has no over-voltage clamp; see the ordering check for R8.
- The tower interface of the printed lid is a placeholder until the real base is measured.
- The program is untested on the ESP32-C3.
- No EMC or safety assessment has been made.

## 10. Care and disposal

- Clean with a dry cloth. No solvents on the printed parts.
- Before any work on the tower or the wiring, unplug the USB cable.
- Dispose of the board as electronic waste.

## 11. Document history

| Revision | Change |
|---|---|
| A | First issue, for board v1.0. Procedure not yet verified on hardware. |
