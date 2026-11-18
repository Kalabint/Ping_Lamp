// Ping Lamp - printed base ring for a Schneider Harmony XVU tower (60 mm)
//
// Two parts: a tray that is screwed onto the base plate and holds the round driver PCB,
// and a lid that carries the tower. Four countersunk M3 x 25 screws go through the lid,
// its spacer tubes and the PCB into the tray bosses; the tower base hides the screw heads.
//
// Coordinates: PCB component side up, x to the right, y up (KiCad y is mirrored).
// USB-C opening at +x, ESP32 antenna at +y, tower terminal block at -y.
//
// Render:  openscad -D 'part="tray"' -o tray.stl ping_lamp_base.scad
//          openscad -D 'part="lid"'  -o lid.stl  ping_lamp_base.scad

part = "assembly";            // "tray", "lid" or "assembly"

/* [Tower interface - MEASURE ON YOUR XVU BASE, the defaults are placeholders] */
tower_d            = 60;      // outer diameter of the ring = diameter of the tower base
tower_cable_hole_d = 16;      // centre hole for the tower wires (also gives access to BOOT / RESET)
tower_bolt_count   = 3;       // number of fixing screws of the tower base, 0 = none
tower_bolt_circle  = 36;      // bolt circle diameter of those screws
tower_bolt_angle   = 49;      // angle of the first screw, counter-clockwise from +x.
                              // 49 keeps three screws 19 degrees away from every spacer tube
                              // and away from the antenna at +y.
// The tower screws go from above (inside the tower base) into the lid. Nothing is loose
// below the lid, so nothing can drop onto the PCB.
tower_fix          = "thread";  // "thread": screw cuts its own thread in the plastic
                                // "insert": heat-set insert pressed in from below
tower_pilot_d      = 3.6;     // thread-forming hole (3.6 = M4 in PETG/PLA)
tower_bolt_d       = 4.3;     // clearance hole above an insert (4.3 = M4)
tower_insert_d     = 5.6;     // bore for the heat-set insert
tower_insert_h     = 4.0;     // depth of that bore; the remaining skin takes the pull-out load
tower_screw_max    = 8;       // longest thread length below the tower base that stays clear of
                              // the terminal block (lid 5.5 mm + 2.3 mm free above it)

/* [PCB - must match hardware/pcb/design.py] */
pcb_d            = 54;
pcb_t            = 1.6;
pcb_hole_radius  = 22;                   // bolt circle radius of the PCB holes
pcb_hole_angles  = [30, 150, 232, 308];
usb_angle        = 0;                    // direction of the USB-C receptacle

/* [Ring] */
pcb_gap      = 0.6;           // radial gap between PCB and wall
floor_t      = 3.0;
standoff_h   = 4.0;           // space below the PCB (terminal pins, base plate screw heads)
comp_h       = 11.5;          // space above the PCB (terminal block, wire bend)
lid_t        = 5.5;
clamp_gap    = 0.2;           // the wall ends this much below the lid, so the spacer tubes
                              // (not the wall) carry the screw force and clamp the PCB

/* [Fasteners] */
m3_clear_d   = 3.4;
m3_pilot_d   = 2.6;           // thread-forming hole for M3 in the tray boss (4.0 for heat-set inserts)
m3_head_d    = 6.6;           // countersunk head
boss_d       = 7.0;
tube_d       = 6.4;           // spacer tube, stays inside the 3.4 mm keep-out radius on the PCB
plate_screw_d      = 4.0;     // countersunk wood screws that fix the tray to the base plate
plate_screw_head_d = 8.0;
plate_screw_pos    = [[-11, 0], [11, 0]];

/* [Openings] */
usb_w        = 13.0;          // opening for the USB-C plug body
usb_h        = 7.5;
usb_z_centre = 1.65;          // receptacle centre above the PCB surface
floor_cable_hole_d = 0;       // > 0: hole in the floor for a 5 V cable to the "5V IN" pads
floor_cable_pos    = [19.5, -2];

$fn = 96;
eps = 0.01;

inner_d   = pcb_d + 2 * pcb_gap;
wall_t    = (tower_d - inner_d) / 2;
pcb_z     = floor_t + standoff_h;          // underside of the PCB
lid_z     = pcb_z + pcb_t + comp_h;        // underside of the lid
tray_h    = lid_z - clamp_gap;             // top of the wall
total_h   = lid_z + lid_t;
usb_relief = 0.8;                          // inner recess above the USB opening, see tray()

// Tower screws must stay clear of the spacer tubes.
if (tower_bolt_count > 0)
    for (i = [0 : tower_bolt_count - 1], a = pcb_hole_angles) {
        b = tower_bolt_angle + i * 360 / tower_bolt_count;
        d = norm([tower_bolt_circle / 2 * cos(b) - pcb_hole_radius * cos(a),
                  tower_bolt_circle / 2 * sin(b) - pcb_hole_radius * sin(a)]);
        assert(d >= tube_d / 2 + tower_insert_d / 2 + 0.8,
               str("tower screw at ", b, " deg is ", d, " mm from the spacer tube at ", a,
                   " deg: change tower_bolt_angle"));
    }

module at_pcb_holes() {
    for (a = pcb_hole_angles) rotate([0, 0, a]) translate([pcb_hole_radius, 0, 0]) children();
}

module at_tower_bolts() {
    if (tower_bolt_count > 0)
        for (i = [0 : tower_bolt_count - 1])
            rotate([0, 0, tower_bolt_angle + i * 360 / tower_bolt_count])
                translate([tower_bolt_circle / 2, 0, 0]) children();
}

module tray() {
    difference() {
        union() {
            difference() {
                cylinder(d = tower_d, h = tray_h);
                translate([0, 0, floor_t]) cylinder(d = inner_d, h = tray_h);
            }
            at_pcb_holes() translate([0, 0, floor_t - eps]) cylinder(d = boss_d, h = standoff_h + eps);
        }
        at_pcb_holes() translate([0, 0, -eps]) cylinder(d = m3_pilot_d, h = pcb_z + 2 * eps);
        // USB-C plug opening
        rotate([0, 0, usb_angle])
            translate([inner_d / 2 - 1, -usb_w / 2, pcb_z + pcb_t + usb_z_centre - usb_h / 2])
                cube([wall_t + 2, usb_w, usb_h]);
        // The receptacle reaches to within 0.05 mm of the bore. This recess above the opening
        // lets the PCB drop straight in.
        rotate([0, 0, usb_angle])
            translate([inner_d / 2 - 1, -usb_w / 2, pcb_z + pcb_t + usb_z_centre])
                cube([1 + usb_relief, usb_w, tray_h]);
        // screws into the base plate, countersunk from the inside
        for (p = plate_screw_pos) translate([p[0], p[1], -eps]) {
            cylinder(d = plate_screw_d, h = floor_t + 2 * eps);
            translate([0, 0, floor_t - (plate_screw_head_d - plate_screw_d) / 2 + eps])
                cylinder(d1 = plate_screw_d, d2 = plate_screw_head_d, h = (plate_screw_head_d - plate_screw_d) / 2 + eps);
        }
        if (floor_cable_hole_d > 0)
            translate([floor_cable_pos[0], floor_cable_pos[1], -eps])
                cylinder(d = floor_cable_hole_d, h = floor_t + 2 * eps);
    }
}

// Lid in assembled position: top face at z = lid_t, spacer tubes pointing down.
module lid() {
    difference() {
        union() {
            cylinder(d = tower_d, h = lid_t);
            // The four spacer tubes and screws locate the lid; no lip, so nothing can foul the
            // terminal block or the USB plug at the rim.
            at_pcb_holes() translate([0, 0, -comp_h]) cylinder(d = tube_d, h = comp_h + eps);
        }
        at_pcb_holes() {
            translate([0, 0, -comp_h - eps]) cylinder(d = m3_clear_d, h = comp_h + lid_t + 2 * eps);
            translate([0, 0, lid_t - (m3_head_d - m3_clear_d) / 2])
                cylinder(d1 = m3_clear_d, d2 = m3_head_d, h = (m3_head_d - m3_clear_d) / 2 + eps);
        }
        translate([0, 0, -eps]) cylinder(d = tower_cable_hole_d, h = lid_t + 2 * eps);
        at_tower_bolts() {
            if (tower_fix == "insert") {
                translate([0, 0, -eps]) cylinder(d = tower_bolt_d, h = lid_t + 2 * eps);
                translate([0, 0, -eps]) cylinder(d = tower_insert_d, h = tower_insert_h + eps);
            } else {
                translate([0, 0, -eps]) cylinder(d = tower_pilot_d, h = lid_t + 2 * eps);
            }
        }
    }
}

module pcb_dummy() {
    color("green") translate([0, 0, pcb_z]) difference() {
        cylinder(d = pcb_d, h = pcb_t);
        at_pcb_holes() translate([0, 0, -eps]) cylinder(d = 3.2, h = pcb_t + 2 * eps);
    }
}

if (part == "tray") {
    tray();
} else if (part == "lid") {
    // printing orientation: top face on the bed
    translate([0, 0, lid_t]) rotate([180, 0, 0]) lid();
} else {
    difference() {
        union() {
            color("burlywood") tray();
            pcb_dummy();
            color("silver") translate([0, 0, lid_z]) lid();
        }
        // cut-away for the preview
        translate([0, -tower_d, -1]) cube([tower_d, tower_d, total_h + 2]);
    }
    echo(str("ring: diameter ", tower_d, " mm, height ", total_h, " mm, wall ", wall_t, " mm"));
}
