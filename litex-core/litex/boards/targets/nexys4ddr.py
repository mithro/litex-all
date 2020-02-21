#!/usr/bin/env python3

# This file is Copyright (c) 2018-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# License: BSD

import argparse

from migen import *

from litex.boards.platforms import nexys4ddr

from litex.soc.cores.clock import *
from litex.soc.integration.soc_sdram import *
from litex.soc.integration.builder import *

from litedram.modules import MT47H64M16
from litedram.phy import s7ddrphy

from liteeth.phy.rmii import LiteEthPHYRMII
from liteeth.mac import LiteEthMAC

from litesdcard.phy import SDPHY
from litesdcard.clocker import SDClockerS7
from litesdcard.core import SDCore
from litesdcard.bist import BISTBlockGenerator, BISTBlockChecker
from litex.soc.cores.timer import Timer

# CRG ----------------------------------------------------------------------------------------------

class _CRG(Module):
    def __init__(self, platform, sys_clk_freq):
        self.clock_domains.cd_sys       = ClockDomain()
        self.clock_domains.cd_sys2x     = ClockDomain(reset_less=True)
        self.clock_domains.cd_sys2x_dqs = ClockDomain(reset_less=True)
        self.clock_domains.cd_clk200    = ClockDomain()
        self.clock_domains.cd_eth       = ClockDomain()
        self.clock_domains.cd_sdcard    = ClockDomain(reset_less=True)

        # # #

        self.sd_clk_freq = int(100e6)

        self.submodules.pll = pll = S7MMCM(speedgrade=-1)
        self.comb += pll.reset.eq(~platform.request("cpu_reset"))
        pll.register_clkin(platform.request("clk100"), 100e6)
        pll.create_clkout(self.cd_sys,       sys_clk_freq)
        pll.create_clkout(self.cd_sys2x,     2*sys_clk_freq)
        pll.create_clkout(self.cd_sys2x_dqs, 2*sys_clk_freq, phase=90)
        pll.create_clkout(self.cd_clk200,    200e6)
        pll.create_clkout(self.cd_eth,       50e6)
        pll.create_clkout(self.cd_sdcard,    self.sd_clk_freq)

        self.submodules.idelayctrl = S7IDELAYCTRL(self.cd_clk200)

# BaseSoC ------------------------------------------------------------------------------------------

class BaseSoC(SoCSDRAM):
    def __init__(self, sys_clk_freq=int(100e6), **kwargs):
        platform = nexys4ddr.Platform()

        # SoCSDRAM ---------------------------------------------------------------------------------
        SoCSDRAM.__init__(self, platform, clk_freq=sys_clk_freq, **kwargs)

        # CRG --------------------------------------------------------------------------------------
        self.submodules.crg = _CRG(platform, sys_clk_freq)

        # DDR2 SDRAM -------------------------------------------------------------------------------
        if not self.integrated_main_ram_size:
            self.submodules.ddrphy = s7ddrphy.A7DDRPHY(platform.request("ddram"),
                memtype      = "DDR2",
                nphases      = 2,
                sys_clk_freq = sys_clk_freq)
            self.add_csr("ddrphy")
            sdram_module = MT47H64M16(sys_clk_freq, "1:2")
            self.register_sdram(self.ddrphy,
                geom_settings   = sdram_module.geom_settings,
                timing_settings = sdram_module.timing_settings)

    def add_ethernet(self):
        mem_map = {
            "ethmac": 0xb0000000,
        }
        mem_map.update(self.mem_map)

        # phy
        self.submodules.ethphy = LiteEthPHYRMII(
            clock_pads = self.platform.request("eth_clocks"),
            pads       = self.platform.request("eth"))
        self.add_csr("ethphy")
        # mac
        self.submodules.ethmac = LiteEthMAC(
            phy        = self.ethphy,
            dw         = 32,
            interface  = "wishbone",
            endianness = self.cpu.endianness)
        self.add_memory_region("ethmac", self.mem_map["ethmac"], 0x2000, type="io")
        self.add_wb_slave(self.mem_map["ethmac"], self.ethmac.bus, 0x2000)
        self.add_csr("ethmac")
        self.add_interrupt("ethmac")
        # timing constraints
        self.platform.add_period_constraint(self.ethphy.crg.cd_eth_rx.clk, 1e9/25e6)
        self.platform.add_period_constraint(self.ethphy.crg.cd_eth_tx.clk, 1e9/25e6)
        self.platform.add_false_path_constraints(
            self.crg.cd_sys.clk,
            self.ethphy.crg.cd_eth_rx.clk,
            self.ethphy.crg.cd_eth_tx.clk)

    def add_sdcard(self):
        sdcard_pads = self.platform.request("sdcard")
        self.comb += sdcard_pads.rst.eq(0)
        self.submodules.sdclk = SDClockerS7(clkin=ClockSignal("sdcard"), clkin_freq=self.crg.sd_clk_freq)
        self.submodules.sdphy = SDPHY(sdcard_pads, self.platform.device)
        self.submodules.sdcore = SDCore(self.sdphy)
        self.submodules.sdtimer = Timer()
        self.add_csr("sdclk")
        self.add_csr("sdphy")
        self.add_csr("sdcore")
        self.add_csr("sdtimer")

        self.submodules.bist_generator = BISTBlockGenerator(random=True)
        self.submodules.bist_checker = BISTBlockChecker(random=True)
        self.add_csr("bist_generator")
        self.add_csr("bist_checker")
        self.comb += [
            self.sdcore.source.connect(self.bist_checker.sink),
            self.bist_generator.source.connect(self.sdcore.sink)
        ]
        self.platform.add_period_constraint(self.sdclk.cd_sd.clk, period_ns(self.crg.sd_clk_freq))
        self.platform.add_period_constraint(self.sdclk.cd_sd_fb.clk, period_ns(self.crg.sd_clk_freq))
        self.platform.add_false_path_constraints(
            self.crg.cd_sys.clk,
            self.sdclk.cd_sd.clk,
            self.sdclk.cd_sd_fb.clk)

# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LiteX SoC on Nexys4DDR")
    builder_args(parser)
    soc_sdram_args(parser)
    parser.add_argument("--sys-clk-freq", default=75e6,
                        help="system clock frequency (default=75MHz)")
    parser.add_argument("--with-ethernet", action="store_true",
                        help="enable Ethernet support")
    parser.add_argument("--with-sdcard", action="store_true",
                        help="enable SDCard support")
    args = parser.parse_args()

    soc = BaseSoC(sys_clk_freq=int(float(args.sys_clk_freq)), **soc_sdram_argdict(args))
    if args.with_ethernet:
        soc.add_ethernet()
    if args.with_sdcard:
        soc.add_sdcard()
    builder = Builder(soc, **builder_argdict(args))
    builder.build()


if __name__ == "__main__":
    main()
