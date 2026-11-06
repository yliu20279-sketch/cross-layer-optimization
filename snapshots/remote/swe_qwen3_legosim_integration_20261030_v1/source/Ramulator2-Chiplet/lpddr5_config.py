import ramulator

frontend = ramulator.frontend.External(clock_ratio=1)

dram = ramulator.dram.LPDDR5(
    org_preset="LPDDR5_8Gb_x16",
    timing_preset="LPDDR5_6400",
    rank=1,
)


controller = ramulator.controller.LPDDR5(
    dram=dram,
    scheduler=ramulator.scheduler.FRFCFS(),
    refresh_manager=ramulator.refresh_manager.AllBank(),
    row_policy=ramulator.row_policy.Open(),
    addr_mapper=ramulator.addr_mapper.RoBaRaCoCh(),
    wck_sync_mode="need_sync",
)

memory_system = ramulator.memory_system.GenericDRAM(
    clock_ratio=1,
    controllers=[controller],
    channel_mapper=ramulator.channel_mapper.CacheLineInterleave(),
)

sim = ramulator.Simulation(frontend, memory_system)
