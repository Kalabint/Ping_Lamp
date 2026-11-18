# -*- coding: utf-8 -*-
"""
Ping Lamp XVU driver board - single source of truth for the design.

Holds the parts list, the netlist and the placement. generate.py turns this
into the KiCad schematic, the routed PCB and the fabrication outputs.

Units: millimetres. PCB coordinates are relative to the board centre,
x to the right, y downwards (KiCad convention). Rotation in degrees, CCW.
"""

BOARD_DIAMETER_MM = 54.0
MOUNT_HOLE_RADIUS_MM = 22.0          # bolt circle radius of the 4 x M3 holes
MOUNT_HOLE_ANGLES_DEG = (30, 150, 232, 308)   # 0 = east, CCW, y up

FP = {
    "R0603": "Resistor_SMD:R_0603_1608Metric",
    "C0603": "Capacitor_SMD:C_0603_1608Metric",
    "C0805": "Capacitor_SMD:C_0805_2012Metric",
    "C1206": "Capacitor_SMD:C_1206_3216Metric",
    "LED0603": "LED_SMD:LED_0603_1608Metric",
    "SOT23": "Package_TO_SOT_SMD:SOT-23",
    "SOT235": "Package_TO_SOT_SMD:SOT-23-5",
    "SOT236": "Package_TO_SOT_SMD:SOT-23-6",
    "SMA": "Diode_SMD:D_SMA",
    "F1812": "Fuse:Fuse_1812_4532Metric",
    "L4030": "Inductor_SMD:L_Sunlord_SWPA4030S",
    "SW": "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A",
    "USBC": "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
    "TB5": "TerminalBlock_Phoenix:TerminalBlock_Phoenix_PT-1,5-5-3.5-H_1x05_P3.50mm_Horizontal",
    "HDR4": "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    "HDR2": "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
    "ESP": "RF_Module:ESP32-C3-WROOM-02",
    "HOLE": "MountingHole:MountingHole_3.2mm_M3",
}

# LCSC numbers: "src" tells how far each one was checked.
#   S = seen in a distributor search snippet, M = from memory only (check before ordering).
PARTS = {
    "10k":    dict(mpn="0603WAF1002T5E", lcsc="C25804", src="S", desc="Resistor 10 k 1 % 0603"),
    "100R":   dict(mpn="0603WAF1000T5E", lcsc="C22775", src="S", desc="Resistor 100 R 1 % 0603"),
    "5k1":    dict(mpn="0603WAF5101T5E", lcsc="C23186", src="S", desc="Resistor 5.1 k 1 % 0603"),
    "100k":   dict(mpn="0603WAF1003T5E", lcsc="C25803", src="S", desc="Resistor 100 k 1 % 0603"),
    "1k":     dict(mpn="0603WAF1001T5E", lcsc="C21190", src="S", desc="Resistor 1 k 1 % 0603"),
    "390k":   dict(mpn="0603WAF3903T5E", lcsc="", src="M", desc="Resistor 390 k 1 % 0603"),
    "100n":   dict(mpn="CC0603KRX7R9BB104", lcsc="C14663", src="S", desc="Capacitor 100 nF 50 V X7R 0603"),
    "1u":     dict(mpn="CL10A105KB8NNNC", lcsc="C15849", src="S", desc="Capacitor 1 uF 50 V X5R 0603"),
    "10u":    dict(mpn="CL21A106KAYNNNE", lcsc="C15850", src="S", desc="Capacitor 10 uF 25 V X5R 0805"),
    "22u":    dict(mpn="CL21A226MAQNNNE", lcsc="C45783", src="S", desc="Capacitor 22 uF 25 V X5R 0805"),
    "10u50":  dict(mpn="CL31A106KBHNNNE", lcsc="C13585", src="S", desc="Capacitor 10 uF 50 V X5R 1206"),
    "LEDR":   dict(mpn="KT-0603R", lcsc="C2286", src="S", desc="LED red 0603"),
    "AO3422": dict(mpn="AO3422", lcsc="C37130", src="S", desc="N-MOSFET 55 V 2.1 A SOT-23 (genuine AOS)"),
    "AP2112": dict(mpn="AP2112K-3.3TRG1", lcsc="C51118", src="S", desc="LDO 3.3 V 600 mA SOT-23-5"),
    "MT3608": dict(mpn="MT3608", lcsc="C84817", src="M", desc="Boost converter 1.2 MHz SOT-23-6"),
    "USBLC6": dict(mpn="USBLC6-2SC6", lcsc="C7519", src="S", desc="USB ESD protection SOT-23-6"),
    "SS34":   dict(mpn="SS34", lcsc="C8678", src="S", desc="Schottky 40 V 3 A SMA"),
    "PTC":    dict(mpn="BSMD1812-110-33V", lcsc="C883150", src="S", desc="PTC fuse 1.1 A hold 33 V 1812"),
    "L22u":   dict(mpn="SWPA4030S220MT", lcsc="C83472", src="S", desc="Inductor 22 uH 1.3 A sat. 4x4x3 mm"),
    "TACT":   dict(mpn="TS-1187A-B-A-B", lcsc="C318884", src="S", desc="Tactile switch 5.1x5.1 mm SMD"),
    "USBC":   dict(mpn="TYPE-C-31-M-12", lcsc="C165948", src="S", desc="USB-C receptacle 16P USB 2.0"),
    "ESP":    dict(mpn="ESP32-C3-WROOM-02-N4", lcsc="C2934560", src="S", desc="ESP32-C3 module 4 MB flash"),
    "TB5":    dict(mpn="5-pos screw terminal 3.5 mm pitch (Phoenix PT 1,5/5-3.5-H or equiv.)", lcsc="",
                   src="M", desc="Terminal block 5 x 3.5 mm, THT, hand soldered"),
    "HDR4":   dict(mpn="1x4 pin header 2.54 mm", lcsc="", src="M", desc="Expansion header, not populated"),
    "HDR2":   dict(mpn="2 solder pads 2.54 mm", lcsc="", src="M", desc="Alternative 5 V wire entry, not populated"),
}


def _c(ref, sym, value, fp, part, nets, at, rot=0, sch=(0, 0), dnp=False, smt=True):
    return dict(ref=ref, sym=sym, value=value, fp=FP[fp] if fp else "", part=part, nets=nets,
                at=at, rot=rot, sch=sch, dnp=dnp, smt=smt)


def _r(ref, value, n1, n2, at, rot=0, sch=(0, 0)):
    part = {"10k": "10k", "100R": "100R", "5.1k": "5k1", "100k": "100k", "1k": "1k", "390k": "390k"}[value]
    return _c(ref, "Device:R", value, "R0603", part, {"1": n1, "2": n2}, at, rot, sch)


def _cap(ref, value, fp, part, n1, n2, at, rot=0, sch=(0, 0)):
    return _c(ref, "Device:C", value, fp, part, {"1": n1, "2": n2}, at, rot, sch)


def _fet(ref, gate, drain, at, sch):
    # SOT-23: 1 = gate, 2 = source, 3 = drain. Rotated so the drain faces the terminal block.
    return _c(ref, "Transistor_FET:AO3400A", "AO3422", "SOT23", "AO3422",
              {"1": gate, "2": "GND", "3": drain}, at, 270, sch)


# Channel centre lines (x) of the four switched outputs; equal to the terminal pin positions.
X_G, X_O, X_R, X_AUX = -3.5, 0.0, 3.5, 7.0

COMPONENTS = [
    # ---------------------------------------------------------------- USB input
    _c("J1", "Connector:USB_C_Receptacle_USB2.0_16P", "USB-C", "USBC", "USBC", {
        "A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND", "S1": "GND",
        "A4": "VBUS", "A9": "VBUS", "B4": "VBUS", "B9": "VBUS",
        "A5": "CC1", "B5": "CC2",
        "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DN", "B7": "USB_DN",
    }, at=(23.55, 0.0), rot=90, sch=(45.72, 76.2)),
    _r("R1", "5.1k", "CC1", "GND", (15.4, 2.1), 0, (81.28, 104.14)),
    _r("R2", "5.1k", "CC2", "GND", (16.5, -5.3), 0, (93.98, 104.14)),
    _c("F1", "Device:Polyfuse", "1.1A", "F1812", "PTC", {"1": "+5V", "2": "VBUS"},
       (14.3, 6.3), 0, (81.28, 45.72)),
    _c("U4", "Power_Protection:USBLC6-2SC6", "USBLC6-2SC6", "SOT236", "USBLC6", {
        "1": "USB_DN", "6": "USB_DN", "3": "USB_DP", "4": "USB_DP", "2": "GND", "5": "VBUS",
    }, (14.5, -1.5), 0, (106.68, 66.04)),

    # Optional wire entry for a supply cable that comes up through the base plate instead of the USB plug.
    _c("J4", "Connector_Generic:Conn_01x02", "5V IN", "HDR2", "HDR2", {"1": "VBUS", "2": "GND"},
       (20.5, 8.0), 0, (45.72, 116.84), dnp=True, smt=False),

    # ---------------------------------------------------------------- 3.3 V rail
    _c("U2", "Regulator_Linear:AP2112K-3.3", "AP2112K-3.3", "SOT235", "AP2112", {
        "1": "+5V", "2": "GND", "3": "+5V", "5": "+3V3",
    }, (11.5, 11.0), 0, (165.1, 53.34)),
    _cap("C1", "10u", "C0805", "10u", "+5V", "GND", (9.75, 6.5), 90, (142.24, 60.96)),
    _cap("C2", "10u", "C0805", "10u", "+3V3", "GND", (16.3, 10.6), 0, (187.96, 60.96)),

    # ---------------------------------------------------------------- 24 V boost
    _c("U3", "Regulator_Switching:MT3608", "MT3608", "SOT236", "MT3608", {
        "1": "SW", "2": "GND", "3": "FB", "4": "BOOST_EN", "5": "+5V",
    }, (-15.5, 4.3), 0, (254.0, 55.88)),
    _c("L1", "Device:L", "22uH", "L4030", "L22u", {"1": "SW", "2": "+5V"},
       (-20.5, 2.5), 90, (254.0, 33.02)),
    _c("D1", "Device:D_Schottky", "SS34", "SMA", "SS34", {"1": "+24V", "2": "SW"},
       (-19.5, 8.3), 0, (284.48, 33.02)),
    _cap("C6", "22u", "C0805", "22u", "+5V", "GND", (-15.5, 0.6), 0, (218.44, 60.96)),
    _cap("C7", "10u/50V", "C1206", "10u50", "+24V", "GND", (-20.0, 11.9), 0, (325.12, 60.96)),
    _cap("C8", "10u/50V", "C1206", "10u50", "+24V", "GND", (-14.6, 11.9), 0, (340.36, 60.96)),
    _r("R7", "100k", "+3V3", "BOOST_EN", (-11.6, 2.7), 0, (231.14, 76.2)),
    _r("R8", "390k", "+24V", "FB", (-11.6, 8.5), 0, (302.26, 50.8)),
    _r("R9", "10k", "FB", "GND", (-11.6, 6.6), 0, (302.26, 71.12)),

    # ---------------------------------------------------------------- MCU
    _c("U1", "PingLamp:ESP32-C3-WROOM-02", "ESP32-C3-WROOM-02-N4", "ESP", "ESP", {
        "1": "+3V3", "2": "EN", "3": "GATE_G", "4": "GATE_O", "5": "GATE_R", "6": "GATE_AUX",
        "7": "IO8", "8": "IO9_BOOT", "9": "GND", "10": "BOOST_EN",
        "13": "USB_DN", "14": "USB_DP", "16": "IO2", "17": "IO1", "18": "IO0", "19": "GND",
    }, (0.0, -12.0), 0, (119.38, 193.04)),
    _cap("C3", "10u", "C0805", "10u", "+3V3", "GND", (-13.3, -16.3), 90, (53.34, 162.56)),
    _cap("C4", "100n", "C0603", "100n", "+3V3", "GND", (-11.3, -16.5), 90, (66.04, 162.56)),
    _r("R3", "10k", "+3V3", "EN", (9.4, -2.2), 90, (53.34, 190.5)),
    _cap("C5", "1u", "C0603", "1u", "EN", "GND", (11.2, -2.2), 90, (53.34, 213.36)),
    _r("R4", "10k", "+3V3", "IO2", (11.5, -15.5), 90, (175.26, 162.56)),
    _r("R5", "10k", "+3V3", "IO8", (-11.2, -5.5), 90, (66.04, 190.5)),
    _r("R6", "1k", "+3V3", "LED_A", (-12.9, -5.5), 90, (187.96, 162.56)),
    _c("LED1", "Device:LED", "red", "LED0603", "LEDR", {"1": "IO8", "2": "LED_A"},
       (-14.6, -5.5), 90, (187.96, 187.96)),
    _c("SW1", "Switch:SW_Push", "BOOT", "SW", "TACT", {"1": "IO9_BOOT", "2": "GND"},
       (-4.2, -1.2), 0, (81.28, 243.84)),
    _c("SW2", "Switch:SW_Push", "RESET", "SW", "TACT", {"1": "EN", "2": "GND"},
       (4.2, -1.2), 0, (114.3, 243.84)),
    _c("J3", "Connector_Generic:Conn_01x04", "EXP", "HDR4", "HDR4", {
        "1": "+3V3", "2": "IO0", "3": "IO1", "4": "GND",
    }, (-3.81, 4.1), 90, (180.34, 228.6), dnp=True, smt=False),

    # ---------------------------------------------------------------- output stage
    _fet("Q1", "G_G", "OUT_G", (X_G, 13.3), (254.0, 147.32)),
    _fet("Q2", "G_O", "OUT_O", (X_O, 13.3), (254.0, 182.88)),
    _fet("Q3", "G_R", "OUT_R", (X_R, 13.3), (254.0, 218.44)),
    _fet("Q4", "G_AUX", "OUT_AUX", (X_AUX, 13.3), (254.0, 254.0)),
    _r("R10", "100R", "GATE_G", "G_G", (X_G + 0.8, 7.9), 90, (226.06, 137.16)),
    _r("R11", "100R", "GATE_O", "G_O", (X_O + 0.8, 7.9), 90, (226.06, 172.72)),
    _r("R12", "100R", "GATE_R", "G_R", (X_R + 0.8, 7.9), 90, (226.06, 208.28)),
    _r("R13", "100R", "GATE_AUX", "G_AUX", (X_AUX + 0.8, 7.9), 90, (226.06, 243.84)),
    _r("R14", "10k", "GND", "G_G", (X_G, 10.3), 0, (238.76, 157.48)),
    _r("R15", "10k", "GND", "G_O", (X_O, 10.3), 0, (238.76, 193.04)),
    _r("R16", "10k", "GND", "G_R", (X_R, 10.3), 0, (238.76, 228.6)),
    _r("R17", "10k", "GND", "G_AUX", (X_AUX, 10.3), 0, (238.76, 264.16)),
    # Rotated 180 deg: wire entry faces the board centre, pin 1 is the eastern pin.
    _c("J2", "Connector:Screw_Terminal_01x05", "TOWER", "TB5", "TB5", {
        "1": "OUT_AUX", "2": "OUT_R", "3": "OUT_O", "4": "OUT_G", "5": "+24V",
    }, (7.0, 21.5), 180, (330.2, 198.12), smt=False),
]

# Symbols that are not part of the KiCad 7 standard libraries. They are written to
# ping_lamp.kicad_sym. Pins: (number, name, electrical type), listed top to bottom / left to right.
CUSTOM_SYMBOLS = {
    "ESP32-C3-WROOM-02": dict(
        reference="U", footprint=FP["ESP"],
        datasheet="https://www.espressif.com/sites/default/files/documentation/esp32-c3-wroom-02_datasheet_en.pdf",
        left=[("2", "EN", "input"), ("18", "IO0", "bidirectional"), ("17", "IO1", "bidirectional"),
              ("16", "IO2", "bidirectional"), ("15", "IO3", "bidirectional"), ("3", "IO4", "bidirectional"),
              ("4", "IO5", "bidirectional"), ("5", "IO6", "bidirectional"), ("6", "IO7", "bidirectional")],
        right=[("7", "IO8", "bidirectional"), ("8", "IO9", "bidirectional"), ("10", "IO10", "bidirectional"),
               ("13", "IO18/USB_D-", "bidirectional"), ("14", "IO19/USB_D+", "bidirectional"),
               ("11", "RXD/IO20", "bidirectional"), ("12", "TXD/IO21", "bidirectional")],
        top=[("1", "3V3", "power_in")],
        bottom=[("9", "GND", "power_in"), ("19", "GND", "power_in")],
    ),
}

# Tracks laid before autorouting (locked). The 5 V feed of the boost converter crosses the board
# on the bottom layer; left to itself the router takes it around the rim.
PREROUTES = [
    dict(net="+5V", layer="B.Cu", width=0.8, via=(0.8, 0.4),
         points=[(10.9, 7.0), (10.2, 6.3), (-12.3, 6.3), (-17.8, 0.8)]),
]

# No tracks, vias or copper pour within this radius of a mounting hole (screw head, printed boss).
HOLE_KEEPOUT_RADIUS_MM = 3.4

# Nets routed with wide tracks.
POWER_NETS = ["VBUS", "+5V", "+3V3", "+24V", "SW", "GND", "OUT_G", "OUT_O", "OUT_R", "OUT_AUX"]

# Schematic block titles (x, y, text).
SCH_NOTES = [
    (30.48, 25.4, "USB-C INPUT: 5 V supply and native USB (REPL / flashing)"),
    (137.16, 25.4, "3.3 V RAIL"),
    (213.36, 20.32, "BOOST 5 V -> 24 V   Vout = 0.6 V x (1 + R8/R9) = 24.0 V"),
    (30.48, 144.78, "ESP32-C3: GPIO4 = green, GPIO5 = orange, GPIO6 = red, GPIO7 = aux, GPIO10 = boost enable"),
    (213.36, 121.92, "LOW-SIDE SWITCHES: tower common = +24 V, one switched return per tier"),
    (30.48, 276.86, "SW1 BOOT and SW2 RESET are reachable through the centre hole of the printed lid."),
]
