#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Generates the KiCad 7 project of the Ping Lamp XVU driver board from design.py:

  ping_lamp.kicad_sch   schematic (connections by net label)
  ping_lamp.kicad_pcb   placed, autorouted, ground-poured board
  fab/                  Gerber + drill archive, BOM, placement file, PDFs, DRC report

Requirements: KiCad 7 (pcbnew Python module, kicad-cli), Java and a Freerouting jar.
Usage:  /usr/bin/python3 generate.py --freerouting /path/to/freerouting.jar
"""

import argparse
import collections
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import uuid
import zipfile

import pcbnew

import design

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "ping_lamp"
PROJECT_LIB = "PingLamp"
SYM_DIR = "/usr/share/kicad/symbols"
FP_DIR = "/usr/share/kicad/footprints"
CX, CY = 100.0, 100.0            # board centre on the PCB sheet
UUID_NS = uuid.UUID("6f1c2a52-3c0b-4a67-9a55-2f1d8c1b7e10")


def uid(*key):
    """Deterministic UUID, so regenerating does not churn the files."""
    return str(uuid.uuid5(UUID_NS, "/".join(str(k) for k in key)))


# --------------------------------------------------------------------------- S-expressions
class Q(str):
    """A quoted string token."""


def parse_sexpr(text):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()"]+', text)
    stack, cur = [], []
    for tok in tokens:
        if tok == "(":
            stack.append(cur)
            cur = []
        elif tok == ")":
            done = cur
            cur = stack.pop()
            cur.append(done)
        elif tok.startswith('"'):
            cur.append(Q(tok[1:-1]))
        else:
            cur.append(tok)
    return cur[0]


def dump_sexpr(node, depth=0):
    if isinstance(node, Q):
        return '"%s"' % node
    if not isinstance(node, list):
        return str(node)
    flat = "(" + " ".join(dump_sexpr(n) for n in node) + ")"
    if len(flat) < 110 or not any(isinstance(n, list) for n in node):
        return flat
    pad = "\n" + "  " * (depth + 1)
    out = "(" + dump_sexpr(node[0])
    for n in node[1:]:
        out += (pad if isinstance(n, list) else " ") + dump_sexpr(n, depth + 1)
    return out + "\n" + "  " * depth + ")"


def child(node, key):
    for n in node:
        if isinstance(n, list) and n and n[0] == key:
            return n
    return None


def font(size=1.27):
    return ["font", ["size", size, size]]


def r2(v):
    return round(v + 0.0, 2)


# --------------------------------------------------------------------------- symbol libraries
_lib_cache = {}


def custom_symbol(name, spec):
    """Builds a plain rectangular symbol from a pin table (see design.CUSTOM_SYMBOLS)."""
    grid = 2.54
    rows = max(len(spec["left"]), len(spec["right"]))
    half_h = grid * (rows + 1) / 2
    half_w = 5 * grid

    def prop(key, value, x, y, hide=False):
        return ["property", Q(key), Q(value), ["at", r2(x), r2(y), 0],
                ["effects", font(), ["justify", "left"]] + (["hide"] if hide else [])]

    def pin(number, pin_name, kind, x, y, angle):
        return ["pin", kind, "line", ["at", r2(x), r2(y), angle], ["length", grid],
                ["name", Q(pin_name), ["effects", font()]], ["number", Q(number), ["effects", font()]]]

    pins = []
    for side, x, angle in (("left", -half_w - grid, 0), ("right", half_w + grid, 180)):
        for i, (number, pin_name, kind) in enumerate(spec[side]):
            pins.append(pin(number, pin_name, kind, x, half_h - grid * (i + 1), angle))
    for side, y, angle in (("top", half_h + grid, 270), ("bottom", -half_h - grid, 90)):
        count = len(spec[side])
        for i, (number, pin_name, kind) in enumerate(spec[side]):
            pins.append(pin(number, pin_name, kind, grid * (i - (count - 1) / 2), y, angle))
    return ["symbol", Q(name), ["in_bom", "yes"], ["on_board", "yes"],
            prop("Reference", spec["reference"], -half_w, half_h + 1.27),
            prop("Value", name, 2.54, half_h + 1.27),
            prop("Footprint", spec["footprint"], 0, 0, True),
            prop("Datasheet", spec["datasheet"], 0, 0, True),
            ["symbol", Q(name + "_0_1"),
             ["rectangle", ["start", r2(-half_w), r2(half_h)], ["end", r2(half_w), r2(-half_h)],
              ["stroke", ["width", 0.254], ["type", "default"]], ["fill", ["type", "background"]]]],
            ["symbol", Q(name + "_1_1")] + pins]


def write_project_library(path):
    lib = ["kicad_symbol_lib", ["version", 20220914], ["generator", "kicad_symbol_editor"]]
    lib += [custom_symbol(name, spec) for name, spec in design.CUSTOM_SYMBOLS.items()]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(dump_sexpr(lib) + "\n")
    with open(os.path.join(os.path.dirname(path), "sym-lib-table"), "w", encoding="utf-8") as fh:
        fh.write('(sym_lib_table\n  (lib (name "%s")(type "KiCad")(uri "${KIPRJMOD}/%s")(options "")'
                 '(descr "Ping Lamp project symbols"))\n)\n' % (PROJECT_LIB, os.path.basename(path)))


def lib_symbol(lib_id):
    """Returns the library symbol with 'extends' resolved, named 'Lib:Name'."""
    lib, name = lib_id.split(":")
    if lib == PROJECT_LIB:
        sym = custom_symbol(name, design.CUSTOM_SYMBOLS[name])
        return [sym[0], Q(lib_id)] + sym[2:]
    if lib not in _lib_cache:
        with open(os.path.join(SYM_DIR, lib + ".kicad_sym"), encoding="utf-8") as fh:
            _lib_cache[lib] = parse_sexpr(fh.read())

    def find(n):
        for node in _lib_cache[lib]:
            if isinstance(node, list) and node[0] == "symbol" and node[1] == n:
                return node
        raise KeyError(lib_id)

    sym = find(name)
    ext = child(sym, "extends")
    if ext is None:
        return [sym[0], Q(lib_id)] + sym[2:]
    parent = find(ext[1])
    own_props = {n[1]: n for n in sym if isinstance(n, list) and n[0] == "property"}
    out = ["symbol", Q(lib_id)]
    for n in parent[2:]:
        if not isinstance(n, list):
            continue
        if n[0] == "property":
            out.append(own_props.pop(n[1], n))
        elif n[0] == "symbol":
            out.append(["symbol", Q(n[1].replace(parent[1], name, 1))] + n[2:])
        else:
            out.append(n)
    first_unit = next(i for i, n in enumerate(out) if isinstance(n, list) and n[0] == "symbol")
    out[first_unit:first_unit] = list(own_props.values())
    return out


def symbol_pins(sym):
    """[(number, x, y, angle)] in library coordinates (y up)."""
    pins = []
    for unit in sym:
        if isinstance(unit, list) and unit[0] == "symbol":
            for n in unit:
                if isinstance(n, list) and n[0] == "pin":
                    at = child(n, "at")
                    pins.append((str(child(n, "number")[1]), float(at[1]), float(at[2]), int(float(at[3]))))
    return pins


# --------------------------------------------------------------------------- schematic
def build_schematic(path):
    root_uuid = uid("root")
    libs, body = {}, []
    extra = [dict(ref="#FLG%02d" % (i + 1), sym="power:PWR_FLAG", value="PWR_FLAG", fp="", part=None,
                  nets={"1": net}, sch=(33.02 + 15.24 * i, 127.0), dnp=False, flag=True)
             for i, net in enumerate(["GND", "VBUS", "+5V", "+3V3", "+24V"])]
    holes = [dict(ref="H%d" % (i + 1), sym="Mechanical:MountingHole", value="M3", part=None, nets={},
                  fp=design.FP["HOLE"], sch=(330.2 + 12.7 * i, 233.68), dnp=False, flag=True) for i in range(4)]

    for comp in design.COMPONENTS + extra + holes:
        sym = libs.setdefault(comp["sym"], lib_symbol(comp["sym"]))
        sx, sy = comp["sch"]
        pins = symbol_pins(sym)
        numbers = {p[0] for p in pins}
        missing = set(comp["nets"]) - numbers
        if missing:
            raise SystemExit("%s: pins %s not in symbol %s" % (comp["ref"], sorted(missing), comp["sym"]))

        inst = ["symbol", ["lib_id", Q(comp["sym"])], ["at", r2(sx), r2(sy), 0], ["unit", 1],
                ["in_bom", "no" if comp.get("flag") else "yes"], ["on_board", "yes"],
                ["dnp", "yes" if comp["dnp"] else "no"], ["uuid", uid("sym", comp["ref"])]]
        part = design.PARTS.get(comp["part"], {})
        values = {"Reference": comp["ref"], "Value": comp["value"], "Footprint": comp["fp"]}
        for prop in sym:
            if isinstance(prop, list) and prop[0] == "property" and prop[1] in (
                    "Reference", "Value", "Footprint", "Datasheet"):
                at = child(prop, "at")
                eff = child(prop, "effects")
                inst.append(["property", Q(prop[1]), Q(values.get(prop[1], prop[2])),
                             ["at", r2(sx + float(at[1])), r2(sy - float(at[2])), at[3]], eff])
        for key in ("mpn", "lcsc"):
            if part.get(key):
                inst.append(["property", Q(key.upper()), Q(part[key]), ["at", r2(sx), r2(sy), 0],
                             ["effects", font(), "hide"]])
        for number in sorted(numbers):
            inst.append(["pin", Q(number), ["uuid", uid("pin", comp["ref"], number)]])
        inst.append(["instances", ["project", Q(NAME), ["path", Q("/" + root_uuid),
                                                         ["reference", Q(comp["ref"])], ["unit", 1]]]])
        body.append(inst)

        seen = {}
        for number, px, py, angle in pins:
            pos = (r2(sx + px), r2(sy - py))
            net = comp["nets"].get(number)
            if pos in seen:
                if seen[pos] != net:
                    raise SystemExit("%s: stacked pins with different nets at %s" % (comp["ref"], pos))
                continue
            seen[pos] = net
            if net is None:
                body.append(["no_connect", ["at", pos[0], pos[1]], ["uuid", uid("nc", comp["ref"], number)]])
                continue
            # The label points away from the symbol body.
            label_angle, justify = {0: (180, "right"), 180: (0, "left"),
                                    90: (270, "right"), 270: (90, "left")}[angle]
            body.append(["label", Q(net), ["at", pos[0], pos[1], label_angle],
                         ["effects", font(), ["justify", justify, "bottom"]],
                         ["uuid", uid("lbl", comp["ref"], number)]])

    for i, (x, y, text) in enumerate(design.SCH_NOTES):
        body.append(["text", Q(text), ["at", x, y, 0],
                     ["effects", font(2.0), ["justify", "left", "bottom"]], ["uuid", uid("note", i)]])

    sch = ["kicad_sch", ["version", 20230121], ["generator", "eeschema"], ["uuid", root_uuid],
           ["paper", Q("A3")],
           ["title_block", ["title", Q("Ping Lamp - Harmony XVU driver")], ["rev", Q("1.0")],
            ["comment", 1, Q("Generated by hardware/pcb/generate.py from design.py")]],
           ["lib_symbols"] + list(libs.values())] + body + [
              ["sheet_instances", ["path", Q("/"), ["page", Q("1")]]]]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(dump_sexpr(sch) + "\n")
    return holes


# --------------------------------------------------------------------------- project file
RULES = {"min_clearance": 0.15, "min_track_width": 0.2, "min_via_diameter": 0.6,
         "min_via_annular_width": 0.13, "min_through_hole_diameter": 0.3,
         "min_hole_to_hole": 0.25, "min_hole_clearance": 0.25, "min_copper_edge_clearance": 0.3,
         "min_silk_clearance": 0.0, "min_text_height": 0.8, "min_text_thickness": 0.08,
         "solder_mask_to_copper_clearance": 0.0, "min_microvia_diameter": 0.2,
         "min_microvia_drill": 0.1, "use_height_for_length_calcs": True}
# name: (track width, clearance, via diameter, via drill) in mm
NETCLASSES = {"Default": (0.25, 0.15, 0.6, 0.3), "Power": (0.5, 0.2, 0.8, 0.4)}


def write_project(path):
    def netclass(name, width, clearance, via, drill):
        return {"name": name, "clearance": clearance, "track_width": width, "via_diameter": via,
                "via_drill": drill, "diff_pair_width": 0.2, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25,
                "microvia_diameter": 0.3, "microvia_drill": 0.1, "bus_width": 12, "wire_width": 6,
                "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)",
                "schematic_color": "rgba(0, 0, 0, 0.000)"}

    project = {
        "board": {"design_settings": {
            "defaults": {"board_outline_line_width": 0.1, "copper_line_width": 0.2,
                         "silk_line_width": 0.15, "silk_text_size_h": 1.0, "silk_text_size_v": 1.0,
                         "silk_text_thickness": 0.15},
            "rules": RULES,
            "track_widths": [0.0, 0.25, 0.5], "via_dimensions": [{"diameter": 0.0, "drill": 0.0}],
        }},
        "meta": {"filename": NAME + ".kicad_pro", "version": 1},
        "net_settings": {
            "classes": [netclass(name, *values) for name, values in NETCLASSES.items()],
            "meta": {"version": 3},
            "net_colors": None,
            "netclass_assignments": None,
            "netclass_patterns": [{"netclass": "Power", "pattern": n} for n in design.POWER_NETS],
        },
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [], "text_variables": {},
    }
    # Saving a board makes KiCad write its own, complete project file. Keep that one and only
    # replace the rules and net classes in it.
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            native = json.load(fh)
        template = (native.get("net_settings", {}).get("classes") or [{}])[0]
        native.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rules", {}).update(RULES)
        net_settings = native.setdefault("net_settings", {})
        net_settings["classes"] = [dict(template, **cls) for cls in project["net_settings"]["classes"]]
        net_settings["netclass_patterns"] = project["net_settings"]["netclass_patterns"]
        project = native
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(project, fh, indent=2)


# --------------------------------------------------------------------------- PCB
def mm(v):
    return pcbnew.FromMM(float(v))


def pt(x, y):
    return pcbnew.VECTOR2I(mm(CX + x), mm(CY + y))


def circle_points(radius, steps=96):
    return [(radius * math.cos(2 * math.pi * i / steps), radius * math.sin(2 * math.pi * i / steps))
            for i in range(steps)]


def hole_positions():
    r = design.MOUNT_HOLE_RADIUS_MM
    return [(r * math.cos(math.radians(a)), -r * math.sin(math.radians(a))) for a in design.MOUNT_HOLE_ANGLES_DEG]


def add_text(board, text, x, y, layer, size=1.0, angle=0):
    item = pcbnew.PCB_TEXT(board)
    item.SetText(text)
    item.SetLayer(layer)
    item.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    item.SetTextThickness(mm(size * 0.15))
    item.SetPosition(pt(x, y))
    item.SetTextAngleDegrees(angle)
    if layer == pcbnew.B_SilkS:
        item.SetMirrored(True)
    board.Add(item)


def apply_rules(board):
    """Sets design rules and net classes on a board and returns the Power net class.

    Needed after every load as well: a headless LoadBoard does not restore the net classes."""
    bds = board.GetDesignSettings()
    bds.m_MinClearance = mm(RULES["min_clearance"])
    bds.m_TrackMinWidth = mm(RULES["min_track_width"])
    bds.m_ViasMinSize = mm(RULES["min_via_diameter"])
    bds.m_MinThroughDrill = mm(RULES["min_through_hole_diameter"])
    bds.m_CopperEdgeClearance = mm(RULES["min_copper_edge_clearance"])
    bds.m_HoleClearance = mm(RULES["min_hole_clearance"])
    bds.m_HoleToHoleMin = mm(RULES["min_hole_to_hole"])
    default = bds.m_NetSettings.m_DefaultNetClass
    power = pcbnew.NETCLASS("Power")
    for cls, (width, clearance, via, drill) in ((default, NETCLASSES["Default"]), (power, NETCLASSES["Power"])):
        cls.SetTrackWidth(mm(width))
        cls.SetClearance(mm(clearance))
        cls.SetViaDiameter(mm(via))
        cls.SetViaDrill(mm(drill))
    bds.m_NetSettings.m_NetClasses["Power"] = power
    for name in design.POWER_NETS:
        net = board.FindNet(name)
        if net is not None:
            net.SetNetClass(power)
    return power


def build_board(path, holes):
    board = pcbnew.BOARD()
    radius = design.BOARD_DIAMETER_MM / 2
    power = apply_rules(board)

    outline = pcbnew.PCB_SHAPE(board)
    outline.SetShape(pcbnew.SHAPE_T_CIRCLE)
    outline.SetCenter(pt(0, 0))
    outline.SetEnd(pt(radius, 0))
    outline.SetLayer(pcbnew.Edge_Cuts)
    outline.SetWidth(mm(0.1))
    board.Add(outline)

    nets = {}

    def net(name):
        if name not in nets:
            nets[name] = pcbnew.NETINFO_ITEM(board, name)
            board.Add(nets[name])
            if name in design.POWER_NETS:
                nets[name].SetNetClass(power)
        return nets[name]

    for comp in design.COMPONENTS:
        lib, fp_name = comp["fp"].split(":")
        fp = pcbnew.FootprintLoad(os.path.join(FP_DIR, lib + ".pretty"), fp_name)
        fp.SetFPID(pcbnew.LIB_ID(lib, fp_name))
        fp.SetReference(comp["ref"])
        fp.SetValue(comp["value"])
        fp.SetPath(pcbnew.KIID_PATH("/" + uid("sym", comp["ref"])))
        part = design.PARTS.get(comp["part"], {})
        if part.get("lcsc"):
            fp.SetProperty("LCSC", part["lcsc"])
        fp.SetPosition(pt(*comp["at"]))
        fp.SetOrientationDegrees(comp["rot"])
        if comp["dnp"]:
            fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
        pad_numbers = set()
        for pad in list(fp.Pads()):
            # The module footprint carries 0.2 mm thermal vias under its ground pad. They are below the
            # standard drill size of low-cost fabs and not required by the module, so they are dropped.
            if 0 < pcbnew.ToMM(pad.GetDrillSize().x) < 0.3:
                fp.Remove(pad)
                continue
            number = pad.GetNumber()
            pad_numbers.add(number)
            if number in comp["nets"]:
                pad.SetNet(net(comp["nets"][number]))
        missing = set(comp["nets"]) - pad_numbers
        if missing:
            raise SystemExit("%s: pins %s not in footprint %s" % (comp["ref"], sorted(missing), comp["fp"]))
        board.Add(fp)

    for hole, (x, y) in zip(holes, hole_positions()):
        lib, fp_name = hole["fp"].split(":")
        fp = pcbnew.FootprintLoad(os.path.join(FP_DIR, lib + ".pretty"), fp_name)
        fp.SetFPID(pcbnew.LIB_ID(lib, fp_name))
        fp.SetReference(hole["ref"])
        fp.SetValue(hole["value"])
        fp.SetPath(pcbnew.KIID_PATH("/" + uid("sym", hole["ref"])))
        fp.SetPosition(pt(x, y))
        fp.Reference().SetVisible(False)
        board.Add(fp)

        keepout = pcbnew.ZONE(board)
        keepout.SetIsRuleArea(True)
        keepout.SetDoNotAllowTracks(True)
        keepout.SetDoNotAllowVias(True)
        keepout.SetDoNotAllowCopperPour(True)
        keepout.SetDoNotAllowPads(False)
        keepout.SetDoNotAllowFootprints(False)
        layers = pcbnew.LSET()
        layers.AddLayer(pcbnew.F_Cu)
        layers.AddLayer(pcbnew.B_Cu)
        keepout.SetLayerSet(layers)
        poly = keepout.Outline()
        poly.NewOutline()
        for kx, ky in circle_points(design.HOLE_KEEPOUT_RADIUS_MM, 24):
            poly.Append(mm(CX + x + kx), mm(CY + y + ky))
        board.Add(keepout)

    for route in design.PREROUTES:
        points = route["points"]
        for start, end in zip(points, points[1:]):
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pt(*start))
            track.SetEnd(pt(*end))
            track.SetWidth(mm(route["width"]))
            track.SetLayer(board.GetLayerID(route["layer"]))
            track.SetNet(net(route["net"]))
            track.SetLocked(True)
            board.Add(track)
        for position in (points[0], points[-1]):
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(pt(*position))
            via.SetViaType(pcbnew.VIATYPE_THROUGH)
            via.SetWidth(mm(route["via"][0]))
            via.SetDrill(mm(route["via"][1]))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetNet(net(route["net"]))
            via.SetLocked(True)
            board.Add(via)

    # Silkscreen: keep reference designators small, hide the values.
    # Passives, transistors and switches are too dense for legible designators; they stay on F.Fab.
    for fp in board.GetFootprints():
        fp.Value().SetVisible(False)
        ref = fp.Reference()
        ref.SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
        ref.SetTextThickness(mm(0.12))
        if re.match(r"(R|C|Q|LED|H|SW)\d", fp.GetReference()):
            ref.SetVisible(False)

    add_text(board, "BOOT", -4.2, 2.2, pcbnew.F_SilkS, 0.8)
    add_text(board, "RST", 4.2, 2.2, pcbnew.F_SilkS, 0.8)
    add_text(board, "PING LAMP XVU v1.0", 0, 13.3, pcbnew.B_SilkS, 1.0)
    add_text(board, "USB 5V in / 24V out", 0, -3.0, pcbnew.B_SilkS, 1.0)
    for label, x in (("AUX", design.X_AUX), ("R", design.X_R), ("O", design.X_O),
                     ("G", design.X_G), ("+24V", -7.0)):
        add_text(board, label, x, 18.6, pcbnew.B_SilkS, 0.9, 90)
    for i, label in enumerate(design.J3_LABELS):
        add_text(board, label, design.J3_AT[0] + 2.6, design.J3_AT[1] + 2.54 * i, pcbnew.B_SilkS, 0.8)
    # Terminal labels on the component side as well: the bottom is hidden once the board is mounted.
    for label, x in (("AUX", design.X_AUX), ("R", design.X_R), ("O", design.X_O),
                     ("G", design.X_G), ("24V", -7.0)):
        add_text(board, label, x, 16.1, pcbnew.F_SilkS, 0.8)
    return board, nets


def add_stitching(board, gnd):
    """Adds ground vias where both pours are solid. Zones must be filled. Returns the via count."""
    zones = [z for z in board.Zones() if not z.GetIsRuleArea()]
    diameter, drill = design.STITCH_VIA
    reach = diameter / 2 + 0.1
    boxes = []
    for pad in board.GetPads():
        box = pad.GetBoundingBox()
        box.Inflate(mm(design.STITCH_PAD_DISTANCE_MM + diameter / 2))
        boxes.append(box)
    limit = design.BOARD_DIAMETER_MM / 2 - 1.5
    pitch = design.STITCH_GRID_MM
    steps = int(limit / pitch)
    grid = [(ix * pitch, iy * pitch) for ix in range(-steps, steps + 1) for iy in range(-steps, steps + 1)
            if math.hypot(ix * pitch, iy * pitch) <= limit]
    placed = []
    for x, y in list(design.STITCH_POINTS) + grid:
        if any(math.hypot(x - px, y - py) < design.STITCH_MIN_SPACING_MM for px, py in placed):
            continue
        probes = [pt(x, y)] + [pt(x + reach * math.cos(a * math.pi / 4), y + reach * math.sin(a * math.pi / 4))
                               for a in range(8)]
        if not all(zone.HitTestFilledArea(zone.GetLayer(), p, 0) for zone in zones for p in probes):
            continue
        if any(box.Contains(pt(x, y)) for box in boxes):
            continue
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pt(x, y))
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetWidth(mm(diameter))
        via.SetDrill(mm(drill))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(gnd)
        board.Add(via)
        placed.append((x, y))
    return len(placed)


def add_ground_zones(board, gnd):
    radius = design.BOARD_DIAMETER_MM / 2 + 1.0
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        zone = pcbnew.ZONE(board)
        zone.SetLayer(layer)
        zone.SetNetCode(gnd.GetNetCode())
        poly = zone.Outline()
        poly.NewOutline()
        for x, y in circle_points(radius):
            poly.Append(mm(CX + x), mm(CY + y))
        zone.SetMinThickness(mm(0.25))
        zone.SetLocalClearance(mm(0.3))
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        zone.SetAssignedPriority(0)
        board.Add(zone)


def autoroute(board, jar, work, reuse=False):
    dsn, ses = os.path.join(work, NAME + ".dsn"), os.path.join(work, NAME + ".ses")
    stamp = ses + ".input.sha256"
    # The router keeps only its track clearance to the outline. Export a slightly smaller
    # outline so that the copper-to-edge rule holds on the real one.
    radius = design.BOARD_DIAMETER_MM / 2
    outline = next(d for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts)
    outline.SetEnd(pt(radius - 0.4, 0))
    exported = pcbnew.ExportSpecctraDSN(board, dsn)
    outline.SetEnd(pt(radius, 0))
    if not exported:
        raise SystemExit("DSN export failed")
    # The export lists every net in the default class. Move the power nets into the (empty)
    # Power class so that the router uses the wide tracks.
    with open(dsn, encoding="utf-8") as fh:
        text = fh.read()
    match = re.search(r'\(class kicad_default ""(.*?)\n\s*\(circuit', text, re.S)
    names = match.group(1).split()
    wide = [n for n in names if n in design.POWER_NETS]
    text = (text[:match.start(1)] + " " + " ".join(n for n in names if n not in wide)
            + text[match.end(1):]).replace("(class Power\n", "(class Power " + " ".join(wide) + "\n", 1)
    with open(dsn, "w", encoding="utf-8") as fh:
        fh.write(text)

    # A stored session is reused only if it was routed from exactly this placement and netlist.
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    stored = open(stamp).read().strip() if os.path.exists(stamp) else ""
    if reuse and os.path.exists(ses) and stored == digest:
        print("routing: reusing the stored session")
    else:
        if reuse:
            print("routing: stored session does not match the design, routing again")
        for f in (ses, stamp):
            if os.path.exists(f):
                os.remove(f)
        cmd = ["java", "-jar", jar, "-de", dsn, "-do", ses, "-mp", "40", "-mt", "1", "-dct", "0"]
        if shutil.which("xvfb-run"):
            cmd = ["xvfb-run", "-a"] + cmd
        log = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, cwd=work)
        if not os.path.exists(ses):
            raise SystemExit("Freerouting produced no session file:\n" + log.stdout[-3000:] + log.stderr[-3000:])
        with open(stamp, "w") as fh:
            fh.write(digest)
    import_session(board, ses)


def import_session(board, ses_path):
    """Adds the tracks and vias of a Specctra session file to the board.

    KiCad 7 only offers the session import for the board open in its GUI, hence this small reader."""
    with open(ses_path, encoding="utf-8") as fh:
        routes = child(parse_sexpr(fh.read()), "routes")
    res = child(routes, "resolution")
    scale = {"um": 1e-3, "mm": 1.0, "mil": 0.0254}[res[1]] / float(res[2])     # file units -> mm

    def point(x, y):
        return pcbnew.VECTOR2I(mm(float(x) * scale), mm(-float(y) * scale))

    # The session holds only what the router added; the locked pre-laid tracks stay on the board.
    for net_node in child(routes, "network_out")[1:]:
        net = board.FindNet(str(net_node[1]))
        if net is None:
            raise SystemExit("session file names unknown net %s" % net_node[1])
        for item in net_node[2:]:
            if item[0] == "wire":
                path = child(item, "path")
                layer = board.GetLayerID(str(path[1]))
                width, coords = float(path[2]) * scale, path[3:]
                for i in range(0, len(coords) - 2, 2):
                    track = pcbnew.PCB_TRACK(board)
                    track.SetStart(point(coords[i], coords[i + 1]))
                    track.SetEnd(point(coords[i + 2], coords[i + 3]))
                    track.SetWidth(mm(width))
                    track.SetLayer(layer)
                    track.SetNet(net)
                    board.Add(track)
            elif item[0] == "via":
                size = re.search(r"_(\d+):(\d+)_um", str(item[1]))
                via = pcbnew.PCB_VIA(board)
                via.SetPosition(point(item[2], item[3]))
                via.SetViaType(pcbnew.VIATYPE_THROUGH)
                via.SetWidth(mm(int(size.group(1)) / 1000))
                via.SetDrill(mm(int(size.group(2)) / 1000))
                via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                via.SetNet(net)
                board.Add(via)


def unrouted_count(board):
    board.BuildConnectivity()
    return board.GetConnectivity().GetUnconnectedCount(False)


# --------------------------------------------------------------------------- checks and outputs
def run(cmd):
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise SystemExit("FAILED: %s\n%s%s" % (" ".join(cmd), res.stdout, res.stderr))
    return res.stdout


def check_netlist(sch_path, board, work):
    """Schematic netlist (as KiCad reads it) and PCB pad nets must both equal design.py."""
    out = os.path.join(work, NAME + ".net")
    run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "-o", out, sch_path])
    with open(out, encoding="utf-8") as fh:
        tree = parse_sexpr(fh.read())
    sch = {}
    for n in child(tree, "nets")[1:]:
        name = str(child(n, "name")[1]).lstrip("/")
        for node in n:
            if isinstance(node, list) and node[0] == "node":
                sch[(str(child(node, "ref")[1]), str(child(node, "pin")[1]))] = name
    want = {(c["ref"], pin): net for c in design.COMPONENTS for pin, net in c["nets"].items()}
    errors = []
    for key, net in want.items():
        if sch.get(key) != net:
            errors.append("schematic %s.%s: %s != %s" % (key[0], key[1], sch.get(key), net))
    for key, net in sch.items():
        if not key[0].startswith("#") and key not in want and not net.startswith("unconnected-"):
            errors.append("schematic %s.%s unexpectedly on %s" % (key[0], key[1], net))
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            key = (fp.GetReference(), pad.GetNumber())
            if want.get(key, "") != pad.GetNetname():
                errors.append("pcb %s.%s: %s != %s" % (key[0], key[1], pad.GetNetname(), want.get(key)))
    if errors:
        raise SystemExit("NETLIST MISMATCH\n" + "\n".join(errors))
    return len(want)


def write_outputs(sch_path, pcb_path, fab):
    gerber_dir = os.path.join(fab, "gerber")
    shutil.rmtree(gerber_dir, ignore_errors=True)
    os.makedirs(gerber_dir)
    layers = "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"
    run(["kicad-cli", "pcb", "export", "gerbers", "-o", gerber_dir + "/", "-l", layers,
         "--subtract-soldermask", "--no-x2", pcb_path])
    run(["kicad-cli", "pcb", "export", "drill", "-o", gerber_dir + "/", "--format", "excellon",
         "--excellon-separate-th", "--excellon-units", "mm", pcb_path])
    with zipfile.ZipFile(os.path.join(fab, NAME + "_gerber.zip"), "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(os.listdir(gerber_dir)):
            zf.write(os.path.join(gerber_dir, f), f)
    shutil.rmtree(gerber_dir)

    pos = os.path.join(fab, "_pos.csv")
    run(["kicad-cli", "pcb", "export", "pos", "-o", pos, "--format", "csv", "--units", "mm",
         "--side", "front", "--smd-only", pcb_path])
    with open(pos, newline="") as fh:
        rows = list(csv.DictReader(fh))
    os.remove(pos)
    with open(os.path.join(fab, NAME + "_cpl.csv"), "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for row in rows:
            wr.writerow([row["Ref"], row["PosX"], row["PosY"], "Top", row["Rot"]])

    groups = {}
    for comp in design.COMPONENTS:
        groups.setdefault((comp["part"], comp["value"], comp["fp"], comp["smt"], comp["dnp"]), []).append(comp["ref"])
    with open(os.path.join(fab, NAME + "_bom.csv"), "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "MPN", "Description", "Qty",
                     "Assembly", "LCSC number check"])
        for (part, value, fp, smt, dnp), refs in groups.items():
            info = design.PARTS[part]
            how = "not populated" if dnp else ("SMT (fab)" if smt else "THT (by hand)")
            check = {"S": "search snippet", "M": "unchecked"}[info["src"]] if info["lcsc"] else "select manually"
            wr.writerow([value, ",".join(refs), fp.split(":")[1], info["lcsc"], info["mpn"], info["desc"],
                         len(refs), how, check])

    run(["kicad-cli", "sch", "export", "pdf", "-o", os.path.join(fab, NAME + "_schematic.pdf"), sch_path])
    run(["kicad-cli", "pcb", "export", "pdf", "-o", os.path.join(fab, NAME + "_pcb_top.pdf"),
         "-l", "F.Cu,F.SilkS,F.Fab,Edge.Cuts", pcb_path])
    run(["kicad-cli", "pcb", "export", "pdf", "-o", os.path.join(fab, NAME + "_pcb_bottom.pdf"),
         "-l", "B.Cu,B.SilkS,Edge.Cuts", "--mirror", pcb_path])


# DRC entries that do not block fabrication: silkscreen cosmetics, and the notice that the
# build machine has no footprint library table. Any other entry stops the build.
DRC_COSMETIC = {"lib_footprint_issues", "silk_edge_clearance", "silk_over_copper", "silk_overlap"}
PROJECT_FILES = [NAME + ext for ext in (".kicad_sch", ".kicad_pcb", ".kicad_pro", ".kicad_sym")] + ["sym-lib-table"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--freerouting", required=True, help="path to the Freerouting jar")
    ap.add_argument("--work", default="/tmp/ping_lamp_build", help="scratch directory")
    ap.add_argument("--reuse-session", action="store_true",
                    help="reuse the stored routing if it was made from the same placement and netlist")
    args = ap.parse_args()

    # Everything is built in the scratch directory. The project files and fabrication outputs in
    # the repository are replaced only after the netlist, connectivity and DRC checks have passed.
    build = os.path.join(args.work, "project")
    shutil.rmtree(build, ignore_errors=True)
    os.makedirs(build)
    sch_path = os.path.join(build, NAME + ".kicad_sch")
    pcb_path = os.path.join(build, NAME + ".kicad_pcb")

    write_project_library(os.path.join(build, NAME + ".kicad_sym"))
    holes = build_schematic(sch_path)
    board, nets = build_board(pcb_path, holes)
    pins = check_netlist(sch_path, board, args.work)
    print("netlist: %d pins, schematic == PCB == design.py" % pins)

    autoroute(board, args.freerouting, args.work, args.reuse_session)
    add_ground_zones(board, nets["GND"])
    pcbnew.SaveBoard(pcb_path, board)

    # Zone filling needs a board that is attached to a project, i.e. one loaded from disk.
    board = pcbnew.LoadBoard(pcb_path)
    apply_rules(board)
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    print("ground stitching vias: %d" % add_stitching(board, board.FindNet("GND")))
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(pcb_path, board)
    write_project(os.path.join(build, NAME + ".kicad_pro"))     # after SaveBoard, which rewrites it

    unrouted = unrouted_count(board)
    print("unrouted connections: %d" % unrouted)
    report = os.path.join(build, NAME + "_drc.txt")
    pcbnew.WriteDRCReport(board, report, pcbnew.EDA_UNITS_MILLIMETRES, True)
    with open(report) as fh:
        counts = collections.Counter(re.findall(r"^\[(\w+)\]", fh.read(), re.M))
    blocking = {kind: n for kind, n in counts.items() if kind not in DRC_COSMETIC}
    print("DRC: %s" % (", ".join("%s x%d" % item for item in sorted(counts.items())) or "clean"))
    if unrouted or blocking:
        raise SystemExit("BUILD REJECTED: %d unrouted, blocking DRC entries %s.\n"
                         "The repository files were left untouched; the failed build is in %s"
                         % (unrouted, blocking or "none", build))

    fab = os.path.join(HERE, "fab")
    os.makedirs(fab, exist_ok=True)
    for name in PROJECT_FILES:
        shutil.copyfile(os.path.join(build, name), os.path.join(HERE, name))
    shutil.copyfile(report, os.path.join(fab, NAME + "_drc.txt"))
    write_outputs(os.path.join(HERE, NAME + ".kicad_sch"), os.path.join(HERE, NAME + ".kicad_pcb"), fab)
    print("outputs written to", fab)


if __name__ == "__main__":
    sys.exit(main())
