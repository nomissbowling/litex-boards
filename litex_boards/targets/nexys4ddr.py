#!/usr/bin/env python3

#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2018-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import os
import argparse

from migen import *

from litex_boards.platforms import nexys4ddr

from litex.soc.cores.clock import *
from litex.soc.integration.soc import SoCRegion
from litex.soc.integration.soc_core import *
from litex.soc.integration.soc_sdram import *
from litex.soc.integration.builder import *
from litex.soc.cores.led import LedChaser

from litedram.modules import MT47H64M16
from litedram.phy import s7ddrphy

from liteeth.phy.rmii import LiteEthPHYRMII

from litex.soc.cores.video import *

# CRG ----------------------------------------------------------------------------------------------

class _CRG(Module):
    def __init__(self, platform, sys_clk_freq):
        self.rst = Signal()
        self.clock_domains.cd_sys       = ClockDomain()
        self.clock_domains.cd_sys2x     = ClockDomain(reset_less=True)
        self.clock_domains.cd_sys2x_dqs = ClockDomain(reset_less=True)
        self.clock_domains.cd_idelay    = ClockDomain()
        self.clock_domains.cd_eth       = ClockDomain()
        self.clock_domains.cd_vga       = ClockDomain(reset_less=True)
        # # #

        self.submodules.pll = pll = S7MMCM(speedgrade=-1)
        self.comb += pll.reset.eq(~platform.request("cpu_reset") | self.rst)
        pll.register_clkin(platform.request("clk100"), 100e6)
        pll.create_clkout(self.cd_sys,       sys_clk_freq)
        pll.create_clkout(self.cd_sys2x,     2*sys_clk_freq)
        pll.create_clkout(self.cd_sys2x_dqs, 2*sys_clk_freq, phase=90)
        pll.create_clkout(self.cd_idelay,    200e6)
        pll.create_clkout(self.cd_eth,       50e6)
        pll.create_clkout(self.cd_vga,       40e6)
        platform.add_false_path_constraints(self.cd_sys.clk, pll.clkin) # Ignore sys_clk to pll.clkin path created by SoC's rst.

        self.submodules.idelayctrl = S7IDELAYCTRL(self.cd_idelay)

# BaseSoC ------------------------------------------------------------------------------------------

class BaseSoC(SoCCore):
    def __init__(self, sys_clk_freq=int(75e6), with_ethernet=False, with_etherbone=False, with_video_terminal=False, **kwargs):
        platform = nexys4ddr.Platform()

        # SoCCore ----------------------------------_-----------------------------------------------
        SoCCore.__init__(self, platform, sys_clk_freq,
            ident          = "LiteX SoC on Nexys4DDR",
            ident_version  = True,
            **kwargs)

        # CRG --------------------------------------------------------------------------------------
        self.submodules.crg = _CRG(platform, sys_clk_freq)

        # DDR2 SDRAM -------------------------------------------------------------------------------
        if not self.integrated_main_ram_size:
            self.submodules.ddrphy = s7ddrphy.A7DDRPHY(platform.request("ddram"),
                memtype      = "DDR2",
                nphases      = 2,
                sys_clk_freq = sys_clk_freq)
            self.add_csr("ddrphy")
            self.add_sdram("sdram",
                phy                     = self.ddrphy,
                module                  = MT47H64M16(sys_clk_freq, "1:2"),
                origin                  = self.mem_map["main_ram"],
                size                    = kwargs.get("max_sdram_size", 0x40000000),
                l2_cache_size           = kwargs.get("l2_size", 8192),
                l2_cache_min_data_width = kwargs.get("min_l2_data_width", 128),
                l2_cache_reverse        = True
            )

        # Ethernet / Etherbone ---------------------------------------------------------------------
        if with_ethernet or with_etherbone:
            self.submodules.ethphy = LiteEthPHYRMII(
                clock_pads = self.platform.request("eth_clocks"),
                pads       = self.platform.request("eth"))
            self.add_csr("ethphy")
            if with_ethernet:
                self.add_ethernet(phy=self.ethphy)
            if with_etherbone:
                self.add_etherbone(phy=self.ethphy)

        # Video Terminal ---------------------------------------------------------------------------
        if with_video_terminal:
            self.submodules.vtg = vtg = ClockDomainsRenamer("vga")(VideoTimingGenerator(default_video_timings="800x600@60Hz"))
            self.add_csr("vtg")
            #self.submodules.vgen = vgen = ClockDomainsRenamer("vga")(ColorBarsPattern())
            self.submodules.vgen = vgen = ClockDomainsRenamer("vga")(VideoTerminal(hres=800, vres=600))
            self.submodules.vphy = vphy = VideoVGAPHY(platform.request("vga"), clock_domain="vga")
            from litex.soc.interconnect import stream
            self.submodules.uart_cdc = stream.ClockDomainCrossing([("data", 8)], cd_from="sys", cd_to="vga")
            self.comb += [
                # Connect UART to Video Terminal.
                self.uart_cdc.sink.valid.eq(self.uart.source.valid & self.uart.source.ready),
                self.uart_cdc.sink.data.eq(self.uart.source.data),
                self.uart_cdc.source.connect(vgen.uart_sink),
                # Connect Video Timing Generator to Video Terminal.
                vtg.source.connect(vgen.vtg_sink),
                # Connect VideoTerminal to VideoDVIPHY.
                vgen.source.connect(vphy.sink),
            ]

        # Leds -------------------------------------------------------------------------------------
        self.submodules.leds = LedChaser(
            pads         = platform.request_all("user_led"),
            sys_clk_freq = sys_clk_freq)
        self.add_csr("leds")

# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LiteX SoC on Nexys4DDR")
    parser.add_argument("--build",              action="store_true", help="Build bitstream")
    parser.add_argument("--load",               action="store_true", help="Load bitstream")
    parser.add_argument("--sys-clk-freq",       default=75e6,        help="System clock frequency (default: 75MHz)")
    ethopts = parser.add_mutually_exclusive_group()
    ethopts.add_argument("--with-ethernet",     action="store_true", help="Enable Ethernet support")
    ethopts.add_argument("--with-etherbone",    action="store_true", help="Enable Etherbone support")
    sdopts = parser.add_mutually_exclusive_group()
    sdopts.add_argument("--with-spi-sdcard",     action="store_true", help="Enable SPI-mode SDCard support")
    sdopts.add_argument("--with-sdcard",         action="store_true", help="Enable SDCard support")
    parser.add_argument("--with-video-terminal", action="store_true", help="Enable Video Terminal (VGA)")
    builder_args(parser)
    soc_sdram_args(parser)
    args = parser.parse_args()

    soc = BaseSoC(
        sys_clk_freq        = int(float(args.sys_clk_freq)),
        with_ethernet       = args.with_ethernet,
        with_etherbone      = args.with_etherbone,
        with_video_terminal = args.with_video_terminal,
        **soc_sdram_argdict(args)
    )
    if args.with_spi_sdcard:
        soc.add_spi_sdcard()
    if args.with_sdcard:
        soc.add_sdcard()
    builder = Builder(soc, **builder_argdict(args))
    builder.build(run=args.build)

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(os.path.join(builder.gateware_dir, soc.build_name + ".bit"))

if __name__ == "__main__":
    main()
