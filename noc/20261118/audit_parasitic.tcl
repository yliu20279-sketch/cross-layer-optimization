set arm $::env(NOC_ARM)
read_liberty NangateOpenCellLibrary_typical.lib
read_db route_$arm.odb
read_spef route_$arm.spef
report_parasitic_annotation -report_unannotated
