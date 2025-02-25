#!/usr/bin/env python3

#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2021 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.gen import LiteXModule

from litex_boards.platforms import efinix_trion_t20_mipi_dev_kit

from litex.build.generic_platform import *

from litex.soc.cores.clock import *
from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *
from litex.soc.cores.led import LedChaser

# CRG ----------------------------------------------------------------------------------------------

class _CRG(LiteXModule):
    def __init__(self, platform, sys_clk_freq):
        self.cd_sys = ClockDomain()

        # # #

        clk50 = platform.request("clk50")
        rst_n = platform.request("user_btn", 0)

        # PLL
        self.pll = pll = TRIONPLL(platform)
        self.comb += pll.reset.eq(~rst_n)
        pll.register_clkin(clk50, 50e6)
        pll.create_clkout(self.cd_sys, sys_clk_freq, with_reset=True)

# BaseSoC ------------------------------------------------------------------------------------------

class BaseSoC(SoCCore):
    def __init__(self, sys_clk_freq=100e6, with_spi_flash=False, with_led_chaser=True, **kwargs):
        platform = efinix_trion_t20_mipi_dev_kit.Platform()

        # CRG --------------------------------------------------------------------------------------
        self.crg = _CRG(platform, sys_clk_freq)

        # SoCCore ----------------------------------------------------------------------------------
        SoCCore.__init__(self, platform, sys_clk_freq, ident="LiteX SoC on Efinix Trion T20 MIPI Dev Kit", **kwargs)

        # SPI Flash --------------------------------------------------------------------------------
        if with_spi_flash:
            from litespi.modules import W25Q32JV
            from litespi.opcodes import SpiNorFlashOpCodes as Codes
            self.add_spi_flash(mode="1x", module=W25Q32JV(Codes.READ_1_1_1), with_master=True)

        # Leds -------------------------------------------------------------------------------------
        if with_led_chaser:
            self.leds = LedChaser(
                pads         = platform.request_all("user_led"),
                sys_clk_freq = sys_clk_freq)

# Build --------------------------------------------------------------------------------------------

def main():
    from litex.build.parser import LiteXArgumentParser
    parser = LiteXArgumentParser(platform=efinix_trion_t20_mipi_dev_kit.Platform, description="LiteX SoC on Efinix Trion T20 MIPI Dev Kit.")
    parser.add_target_argument("--sys-clk-freq",   default=100e6, type=float, help="System clock frequency.")
    parser.add_target_argument("--with-spi-flash", action="store_true",       help="Enable SPI Flash (MMAPed).")
    args = parser.parse_args()

    soc     = BaseSoC(
        sys_clk_freq   = args.sys_clk_freq,
        with_spi_flash = args.with_spi_flash,
         **parser.soc_argdict)
    builder = Builder(soc, **parser.builder_argdict)
    if args.build:
        builder.build(**parser.toolchain_argdict)

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(builder.get_bitstream_filename(mode="sram"))

if __name__ == "__main__":
    main()
