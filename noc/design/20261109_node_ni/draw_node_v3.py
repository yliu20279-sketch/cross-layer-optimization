"""Node, finite NI streams, and the NI-to-CS configuration interface.

Architectural/interface proposal. Does not claim RTL, timing, or performance PASS.
"""
from pathlib import Path
import json
import math
from draw_node_v2 import Figure, BLACK, BLUE, GRAY

ROOT = Path(__file__).resolve().parent


def vertical_bridge(f, x, y, color=GRAY):
    """A non-junction crossing of a vertical control wire over a data wire."""
    f.line((x,y-7),(x,y+7),"white",track=False)
    points=[(x+7*math.sin(t),y-7*math.cos(t)) for t in [i*math.pi/24 for i in range(25)]]
    for a,b in zip(points,points[1:]):
        f.line(a,b,color)


def main():
    f=Figure(2180,1380)
    f.text(365,48,"(a) Node organization",29,True)
    f.text(1460,48,"(b) Network interface and CS configuration",29,True)
    f.rect(35,105,660,765)
    f.text(60,128,"Node",24,True,"start")

    f.rect(65,175,260,170)
    f.text(195,205,"NPU cluster",25,True)
    f.rect(85,240,125,70);f.text(147,275,"MAC array",20)
    f.rect(225,240,80,70);f.text(265,262,"Vector",20);f.text(265,287,"unit",20)
    f.rect(395,175,265,170)
    f.text(527,205,"Scratchpad memory",24,True)
    f.text(527,267,"Banked local SRAM",22)
    f.text(527,313,"Weights and activations",19)
    f.rect(170,430,355,95)
    f.text(347,460,"SRAM access controller",24,True)
    f.text(347,496,"Bank arbitration",22)
    for a,b in [((200,345),(200,430)),((235,430),(235,345)),((445,430),(445,345)),((480,345),(480,430))]:
        f.arrow(a,b)
    f.text(163,386,"Read / write",20,anchor="end")
    f.text(510,386,"Bank access",20,anchor="start")

    f.rect(110,650,260,110)
    f.text(240,684,"Network interface",25,True);f.text(240,724,"(NI)",23)
    f.arrow((210,525),(210,650));f.arrow((245,650),(245,525))
    f.text(270,577,"Send reads /",20,anchor="start")
    f.text(270,606,"receive writes",20,anchor="start")
    f.path([(65,220),(50,220),(50,615),(160,615),(160,650)],GRAY,dash=True)
    f.arrow((50,220),(65,220),GRAY,dash=True)
    f.text(70,560,"Transfer",19,anchor="start",color=GRAY)
    f.text(70,586,"control",19,anchor="start",color=GRAY)

    f.rect(470,650,170,110);f.text(555,706,"Router",27,True)
    f.arrow((370,680),(470,680));f.arrow((470,725),(370,725))
    f.text(420,661,"Send",18);f.text(420,746,"Receive",18)
    for a,b in [((545,650),(545,610)),((565,610),(565,650)),((640,690),(675,690)),((675,713),(640,713)),((545,760),(545,810)),((565,810),(565,760))]:
        f.arrow(a,b)
    f.path([(490,650),(490,615),(450,615)])
    f.path([(450,635),(510,635),(510,650)])
    for x,y,t in [(555,590,"N"),(677,665,"E"),(555,835,"S"),(435,625,"W")]:
        f.text(x,y,t,20)

    for location,cx in zip(("NW","NE","SW","SE"),(140,205,270,335)):
        f.circle(cx,970,24);f.text(cx,970,"CS",19,True,color=GRAY)
        f.arrow((cx-10,760),(cx-10,948))
        f.arrow((cx+10,948),(cx+10,760))
        f.text(cx,1015,location,21)
    # Panel (a) shows the four symmetric DATA attachments only.
    # The independent per-CS configuration assignment is expanded in panel (b),
    # rather than overlaid as an unexplained special wire to the SE data circle.
    f.text(240,1060,"Adjacent lower-level CSs",21)
    f.text(240,1089,"(interior node)",21)
    f.text(365,1145,"CS data links shown; configuration interface in (b).",21)

    # NI: packetization, independent ingress queues, and finite fragment staging.
    f.rect(770,105,745,1080)
    f.text(795,133,"Network interface (NI)",25,True,"start")
    f.rect(825,185,270,100)
    f.text(960,210,"Transfer controller",24,True)
    f.text(960,244,"Transfer descriptors",20)
    f.text(960,272,"Request / pause / completion",19)
    f.arrow((790,215),(825,215),GRAY,dash=True)
    f.arrow((825,235),(790,235),GRAY,dash=True)
    f.text(790,166,"NPU / host",20,anchor="start")

    f.rect(825,360,270,120)
    f.text(960,390,"DMA read engine",24,True)
    f.text(960,426,"Packet formation",21)
    f.text(960,458,"Transfer ID + byte offset",19)
    f.arrow((960,285),(960,360),GRAY,dash=True)
    f.text(980,320,"Read request",19,anchor="start",color=GRAY)
    f.arrow((790,420),(825,420));f.text(830,335,"SRAM read",20,anchor="start")

    f.rect(1190,360,265,120)
    f.text(1322,394,"Transmit queues",24,True)
    f.text(1322,435,"Packet-level path selection",20)
    f.arrow((1095,420),(1190,420))
    f.arrow((1455,390),(1595,390));f.text(1582,363,"To Router",19)
    f.arrow((1455,445),(1595,445));f.text(1582,476,"To lower CSs",19)

    f.rect(1190,770,265,130)
    f.text(1322,798,"Receive queues",24,True)
    f.text(1322,838,"One queue per data link",20)
    f.text(1322,875,"Type decode + arbitration",20)
    f.arrow((1595,800),(1455,800));f.text(1582,765,"From Router",19)
    f.arrow((1595,850),(1455,850));f.text(1582,882,"From lower CSs",18)

    f.rect(825,770,270,130)
    f.text(960,799,"Receive reassembly buffer",22,True)
    f.text(960,839,"Transfer ID + byte offset",19)
    f.text(960,875,"Receipt bitmap",21)
    f.arrow((1190,835),(1095,835))
    f.rect(825,1030,270,90)
    f.text(960,1060,"SRAM write-back",24,True)
    f.text(960,1095,"Commit received fragments",20)
    f.arrow((960,900),(960,1030))
    f.text(980,964,"Data + offset",19,anchor="start")
    f.arrow((825,1060),(790,1060));f.text(830,1004,"SRAM write",20,anchor="start")
    f.path([(1095,1075),(1135,1075),(1135,855),(1095,855)],GRAY,dash=True)
    f.text(1155,1050,"Write accepted",19,anchor="start",color=GRAY)
    # A completed transfer is reported only once every fragment is committed.
    f.path([(825,1095),(735,1095),(735,250),(825,250)],GRAY,dash=True)
    f.text(825,1153,"Completion",19,anchor="start",color=GRAY)
    # Receive descriptors preallocate finite reassembly contexts.
    f.path([(825,270),(800,270),(800,735),(915,735),(915,770)],GRAY,dash=True)
    vertical_bridge(f,800,420)
    f.text(930,716,"Receive descriptor",19,anchor="start",color=GRAY)

    # Configuration packets arrive over ordinary Mesh, independent of CS data.
    f.rect(1190,540,265,100,BLUE)
    f.text(1322,573,"Configuration queue",23,True,color=BLUE)
    f.text(1322,612,"Separate from data queues",19,color=BLUE)
    f.arrow((1322,540),(1322,480),BLUE,dash=True)
    f.text(1340,513,"Mesh replies",18,anchor="start",color=BLUE)
    f.arrow((1322,770),(1322,640),BLUE,dash=True)
    f.text(1343,700,"Configuration",19,anchor="start",color=BLUE)
    f.text(1343,725,"packets",19,anchor="start",color=BLUE)
    f.path([(1190,580),(1160,580),(1160,160),(1065,160),(1065,185)],GRAY,dash=True)
    f.arrow((1160,580),(1190,580),GRAY,dash=True)
    vertical_bridge(f,1160,420)
    f.text(1175,516,"NI control",19,anchor="start",color=GRAY)

    # The CS-side decoder, rather than the NI data TX path, writes the register.
    f.rect(1650,500,490,665)
    f.text(1895,521,"Configuration of one assigned CS",23,True)
    f.rect(1690,555,330,95,BLUE)
    f.text(1855,585,"Command decoder",24,True,color=BLUE)
    f.text(1855,624,"Target selection + write control",19,color=BLUE)
    f.arrow((1455,590),(1690,590),BLUE,dash=True)
    f.text(1582,546,"Configuration",19,color=BLUE)
    f.text(1582,572,"command",19,color=BLUE)
    f.arrow((1690,630),(1455,630),BLUE,dash=True)
    f.text(1567,660,"Response",19,color=BLUE)
    f.rect(1690,730,330,100)
    f.text(1855,762,"Configuration register",24,True)
    f.text(1855,804,"Input / output select + enable",20)
    f.arrow((1855,650),(1855,730),BLUE,dash=True)
    f.text(1875,688,"Register write",20,anchor="start",color=BLUE)
    f.path([(1855,830),(1855,870),(2070,870)])
    f.text(1980,902,"To local CS MUXs",21)
    f.rect(1690,950,330,85,BLUE)
    f.text(1855,978,"Upper-CS configuration relay",22,True,color=BLUE)
    f.text(1855,1011,"Only where an upper CS exists",19,color=BLUE)
    f.path([(2020,603),(2100,603),(2100,994),(2020,994)],BLUE,dash=True)
    f.arrow((2045,603),(2020,603),BLUE,dash=True)
    f.arrow((1855,1035),(1855,1090),BLUE,dash=True)
    f.arrow((1875,1090),(1875,1035),BLUE,dash=True)
    f.text(1855,1121,"To attached upper CS",21,color=BLUE)
    f.text(1895,1193,"Each lower CS has one assigned NI: its NW node.",20)

    # Keep explanations short; the interface contract carries exact rules.
    f.text(1470,1219,"All fragments are placed by offset; completion follows the final SRAM write.",21)
    f.line((800,1260),(855,1260));f.text(870,1260,"Data stream",21,anchor="start")
    f.line((1120,1260),(1175,1260),BLUE,dash=True);f.text(1190,1260,"Configuration",21,anchor="start")
    f.line((1465,1260),(1520,1260),GRAY,dash=True);f.text(1535,1260,"Transfer control / status",21,anchor="start")
    f.text(1470,1300,"Each stream carries data and valid; ready returns in the reverse direction.",21)
    f.text(1470,1335,"DMA: direct memory access.  ID: identifier.  CS: configurable switch.",20)
    f.text(1090,1366,"Design of a node and its configuration interface.",25,True)
    f.save("05_node_configuration_assignment")

    lower=[]
    upper_map={0:9,2:10,6:11,8:12}
    for r in range(3):
        for c in range(3):
            cs=3*r+c
            lower.append({"lower_CS":cs,"owner_node":4*r+c,"owner_location":"NW","upper_CS":upper_map.get(cs)})
    meta={
        "status":"architecture and interface contract proposal; not RTL validated",
        "diagram_dimensions":[2180,1380],
        "figure_files":["figures/05_node_configuration_assignment.png","figures/05_node_configuration_assignment.svg"],
        "schematic_policy":"panel (a) shows symmetric adjacent-CS data links only; panel (b) shows the per-CS fixed configuration interface. Omission of configuration wires from (a) does not remove them from the design or cost.",
        "node_upper_CS_direct_data_link":False,
        "CS_direction_mapping":{"NW":"SE","NE":"SW","SW":"NE","SE":"NW"},
        "configuration_ownership":lower,
        "configuration_transport":"ordinary Mesh packet -> owner NI reserved configuration queue -> fixed local command/response interface -> CS-side decoder -> configuration register",
        "upper_configuration_transport":"owner NI -> corresponding lower CS configuration decoder/relay -> fixed vertical local control interface -> upper CS configuration decoder/register",
        "new_control_wiring":"9 owner-NI to lower-CS local interfaces; 4 lower-to-upper local interfaces. Not new data links and not a zero-wire configuration scheme.",
        "safe_update":"pause new CS transfers at all NIs, drain admitted transfers and writes, collect responses through Mesh, write configuration, wait for all write responses, resume",
        "packet_multipath":"whole packets only; fragments of one transfer may use different paths; no intra-packet flit striping",
        "receive_placement":"finite staging buffers, descriptor lookup by source+transfer ID, fixed-size fragments except final, offset-directed writes, receipt bitmap updated only on SRAM acceptance",
        "completion":"all expected fragment bitmap bits set after SRAM writes; duplicates and out-of-range fragments rejected",
        "flow_control":"data/valid forward and ready backward, finite per-link data queues, separate configuration queue, fair RX and SRAM arbitration",
        "details_in_text":["finite queue/context parameters","request and response fields","clock-domain assumptions","address bounds","resume barrier and failure handling"],
        "not_verified":["RTL and CDC","link/ready timing","area/power","NoC or application performance"]
    }
    (ROOT/"node_interface_v3.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8",newline="\n")
    print("Generated 05_node_configuration_assignment.png/.svg and node_interface_v3.json")


if __name__=="__main__":
    main()
