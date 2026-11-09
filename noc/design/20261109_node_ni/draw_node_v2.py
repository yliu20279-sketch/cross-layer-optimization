"""Component-level Node/NI drawing. No RTL/performance validation is implied.

Sources: DATE 2013 Fig.1(b), EIGEN HPCA 2025 Fig.5(c), RHT_NoC 2025 Fig.8.
The current project topology, not a reference paper, determines CS adjacency.
"""
from pathlib import Path
from html import escape
from PIL import Image, ImageDraw, ImageFont
import math
import json

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "figures"
OUT.mkdir(exist_ok=True)
BLACK = "#1d1d1d"
BLUE = "#176b91"
GRAY = "#73797d"


class Figure:
    def __init__(self, width, height):
        self.image = Image.new("RGB", (width * 2, height * 2), "white")
        self.pen = ImageDraw.Draw(self.image)
        self.svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', '<rect width="100%" height="100%" fill="white"/>']
        self.text_boxes = []
        self.lines = []

    def line(self, a, b, color=BLACK, dash=False, track=True):
        if track:
            self.lines.append((a, b))
        if dash:
            length = math.dist(a, b)
            count = max(1, math.ceil(length / 6))
            for i in range(0, count, 2):
                p = tuple(a[k] + (b[k] - a[k]) * i / count for k in (0, 1))
                q = tuple(a[k] + (b[k] - a[k]) * min(i + 1, count) / count for k in (0, 1))
                self.pen.line([tuple(2 * v for v in p), tuple(2 * v for v in q)], fill=color, width=3)
        else:
            self.pen.line([tuple(2 * v for v in a), tuple(2 * v for v in b)], fill=color, width=3)
        self.svg.append(f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="{color}" stroke-width="1.4"' + (' stroke-dasharray="6 6"' if dash else '') + '/>')

    def arrow(self, a, b, color=BLACK, dash=False):
        self.line(a, b, color, dash)
        theta = math.atan2(b[1] - a[1], b[0] - a[0])
        points = [b] + [(b[0] - 9 * math.cos(theta + delta), b[1] - 9 * math.sin(theta + delta)) for delta in (-0.36, 0.36)]
        self.pen.polygon([tuple(2 * v for v in p) for p in points], fill=color)
        self.svg.append('<polygon points="' + ' '.join(f'{x},{y}' for x, y in points) + f'" fill="{color}"/>')

    def path(self, points, color=BLACK, arrow=True, dash=False):
        for a, b in zip(points[:-2], points[1:-1]):
            self.line(a, b, color, dash)
        if arrow:
            self.arrow(points[-2], points[-1], color, dash)
        else:
            self.line(points[-2], points[-1], color, dash)

    def rect(self, x, y, width, height, color=BLACK):
        self.pen.rectangle((2*x, 2*y, 2*(x+width), 2*(y+height)), fill="white", outline=color, width=3)
        self.svg.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="white" stroke="{color}" stroke-width="1.4"/>')

    def text(self, x, y, text, size=22, bold=False, anchor="middle", color=BLACK):
        font = ImageFont.truetype("C:/Windows/Fonts/" + ("timesbd.ttf" if bold else "times.ttf"), size*2)
        self.pen.text((2*x, 2*y), text, font=font, anchor={"middle":"mm", "start":"lm", "end":"rm"}[anchor], fill=color)
        width = font.getlength(text)/2
        left = x - width/2 if anchor == "middle" else x - width if anchor == "end" else x
        self.text_boxes.append((text, (left, y-size*.43, left+width, y+size*.43)))
        self.svg.append(f'<text x="{x}" y="{y}" font-family="Times New Roman,serif" font-size="{size}" font-weight="{700 if bold else 400}" dominant-baseline="middle" text-anchor="{anchor}" fill="{color}">{escape(text)}</text>')

    def circle(self, x, y, radius):
        self.pen.ellipse((2*(x-radius), 2*(y-radius), 2*(x+radius), 2*(y+radius)), fill="white", outline=GRAY, width=3)
        self.svg.append(f'<circle cx="{x}" cy="{y}" r="{radius}" fill="white" stroke="{GRAY}" stroke-width="1.5"/>')

    def save(self, name):
        self.image.save(OUT / (name + ".png"))
        (OUT / (name + ".svg")).write_text("\n".join(self.svg + ["</svg>"]), encoding="utf-8", newline="\n")


def main():
    f = Figure(1810, 1130)
    f.text(365, 48, "(a) Node organization", 29, True)
    f.text(1270, 48, "(b) Design of the network interface", 29, True)

    # Complete node boundary; adjacent switches are outside this boundary.
    f.rect(35, 105, 660, 765)
    f.text(60, 128, "Node", 24, True, "start")
    f.rect(65, 175, 260, 170)
    f.text(195, 205, "NPU cluster", 25, True)
    f.rect(85, 240, 125, 70)
    f.text(147, 275, "MAC array", 20)
    f.rect(225, 240, 80, 70)
    f.text(265, 262, "Vector", 20)
    f.text(265, 287, "unit", 20)

    f.rect(395, 175, 265, 170)
    f.text(527, 205, "Scratchpad memory", 24, True)
    f.text(527, 267, "Banked local SRAM", 22)
    f.text(527, 313, "Weights and activations", 19)

    f.rect(170, 430, 355, 95)
    f.text(347, 460, "SRAM access controller", 24, True)
    f.text(347, 496, "Bank arbitration", 22)
    f.arrow((200, 345), (200, 430))
    f.arrow((235, 430), (235, 345))
    f.text(163, 386, "Read / write", 20, anchor="end")
    f.arrow((445, 430), (445, 345))
    f.arrow((480, 345), (480, 430))
    f.text(510, 386, "Bank access", 20, anchor="start")

    f.rect(110, 650, 260, 110)
    f.text(240, 684, "Network interface", 25, True)
    f.text(240, 724, "(NI)", 23)
    f.arrow((210, 525), (210, 650))
    f.arrow((245, 650), (245, 525))
    f.text(270, 577, "Send reads /", 20, anchor="start")
    f.text(270, 606, "receive writes", 20, anchor="start")

    f.rect(470, 650, 170, 110)
    f.text(555, 706, "Router", 27, True)
    f.arrow((370, 680), (470, 680))
    f.arrow((470, 725), (370, 725))
    f.text(420, 661, "Send", 18)
    f.text(420, 746, "Receive", 18)
    # Paired arrows denote separate transmit/receive wires.
    for a, b in [((545,650),(545,610)), ((565,610),(565,650)),
                 ((640,690),(675,690)), ((675,713),(640,713)),
                 ((545,760),(545,810)), ((565,810),(565,760))]:
        f.arrow(a,b)
    f.path([(490,650),(490,615),(450,615)])
    f.path([(450,635),(510,635),(510,650)])
    f.text(555, 590, "N", 20)
    f.text(677, 665, "E", 20)
    f.text(555, 835, "S", 20)
    f.text(435, 625, "W", 20)

    # Interior-node example, matching the nine-lower/four-upper topology.
    # No switch numbering, no node-to-upper-CS wire, no lower-CS direct link.
    locations = ("NW", "NE", "SW", "SE")
    for location, cx in zip(locations, (140,205,270,335)):
        f.circle(cx, 970, 24)
        f.text(cx, 970, "CS", 19, True, color=GRAY)
        f.arrow((cx-10,760), (cx-10,948), BLUE)
        f.arrow((cx+10,948), (cx+10,760), BLUE)
        f.text(cx, 1015, location, 21)
    f.text(240, 1060, "Adjacent lower-level CSs", 21)
    f.text(240, 1089, "(interior node)", 21)

    # NI is expanded only to the level needed to explain data/control movement.
    f.rect(770, 160, 1000, 710)
    f.text(795, 187, "Network interface (NI)", 25, True, "start")
    f.rect(850, 280, 275, 100)
    f.text(987, 314, "DMA read engine", 24, True)
    f.text(987, 353, "Packet formation", 22)
    f.arrow((790, 330), (850, 330))
    f.text(795, 250, "SRAM read", 21, anchor="start")

    f.rect(1280, 280, 270, 100)
    f.text(1415, 314, "Transmit queues", 24, True)
    f.text(1415, 353, "Path selection", 22)
    f.arrow((1125,330),(1280,330))
    f.text(1202, 309, "Packets", 20)
    f.arrow((1550,305),(1695,305))
    f.arrow((1550,355),(1695,355))
    f.text(1630, 280, "To Router", 21)
    f.text(1630, 392, "To lower CSs", 21)

    f.rect(1280, 650, 270, 120)
    f.text(1415, 679, "Receive queues", 24, True)
    f.text(1415, 719, "Packet-type decode", 21)
    f.text(1415, 750, "and receive arbitration", 21)
    f.arrow((1695,680),(1550,680))
    f.arrow((1695,730),(1550,730))
    f.text(1630, 650, "From Router", 21)
    f.text(1630, 767, "From lower CSs", 21)

    f.rect(850, 650, 275, 120)
    f.text(987, 689, "Receive reorder buffer", 23, True)
    f.text(987, 735, "DMA write-back", 22)
    f.arrow((1280,710),(1125,710))
    f.text(1202, 689, "Data", 20)
    f.arrow((850,710),(790,710))
    f.text(795, 801, "SRAM write", 21, anchor="start")

    f.rect(1280, 465, 270, 90, BLUE)
    f.text(1415, 495, "Configuration", 23, True, color=BLUE)
    f.text(1415, 530, "packet forwarding", 22, color=BLUE)
    f.arrow((1415,650),(1415,555), BLUE, dash=True)
    f.arrow((1415,465),(1415,380), BLUE, dash=True)
    f.text(1440, 606, "Configuration", 20, anchor="start", color=BLUE)
    f.text(1440, 632, "packets", 20, anchor="start", color=BLUE)

    f.text(1270, 926, "Each adjacent CS has separate send and receive links.", 22)
    f.text(1270, 963, "NPU and NI share SRAM bank service.", 22)
    f.line((995, 1008), (1060, 1008), BLUE, dash=True)
    f.text(1080, 1008, "Configuration packets inside the NI", 21, anchor="start")
    f.text(905, 1051, "DMA: direct memory access.", 20, anchor="start")
    f.text(905, 1083, "CSs are named by their position relative to the node.", 20, anchor="start")
    f.text(905, 1110, "Design of a node and its network interface.", 24, True)

    f.save("03_node_straight_links")
    metadata = {
        "status": "component-level architecture drawing, not RTL validated",
        "reference_scope": {
            "DATE2013_Fig1b": "compute, scratchpad, DMA, NI and Router organization",
            "EIGEN_HPCA2025_Fig5c": "separate programmable-switch and packet-router attachment",
            "RHT_NoC_TVLSI2025_Fig8": "explicit injection/ejection and NI-side buffering"
        },
        "node_components": ["NPU cluster", "banked local SRAM", "SRAM access controller", "NI", "Router"],
        "adjacent_lower_CS_count": {"corner": 1, "edge": 2, "interior": 4},
        "node_upper_CS_direct_connection": False,
        "CS_direction_mapping": {"NW":"SE", "NE":"SW", "SW":"NE", "SE":"NW"},
        "SRAM_policy": "shared bank arbitration; no independent bandwidth assumed for CS traffic",
        "receive_reorder_scope": "packets/fragments of the same transfer; not unrelated global traffic",
        "configuration_path": "network receive -> NI type decode -> forwarding -> transmit -> existing lower-CS link",
        "unresolved_implementation": ["queue and reorder capacities", "CS-side configuration capture and upper-CS forwarding", "SRAM banks/ports and service bandwidth", "packet format and flow-control timing"],
        "diagram_dimensions": [1810,1130],
        "figure_files": ["figures/03_node_straight_links.png", "figures/03_node_straight_links.svg"],
        "physical_audit": {
            "configuration_gap": "Forwarding packets into the data TX block alone does not write the CS configuration register; capture/decode, target selection, write interface and safe update must be specified.",
            "missing_control_detail": ["DMA request descriptors and completion", "finite-buffer ready/credit return", "per-link receive buffering", "transfer/fragment identity, offset and completion for reorder/writeback"],
            "drawing_changes": "Removed ambiguous SRAM decorative lines; placed each adjacent CS below its NI connection and made all CS data-link segments vertical. No NI protocol/RTL change."
        }
    }
    (ROOT / "node_reference_based.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Generated 03_node_straight_links.png / .svg and node_reference_based.json")


if __name__ == "__main__":
    main()
