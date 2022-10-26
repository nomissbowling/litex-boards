#!/usr/bin/env python3

#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2022 JM Robles <roblesjm@gmail.com>
# Copyright (c) 2021 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex_boards.platforms import fpgawars_alhambra2

from litex.build.lattice.programmer import IceStormProgrammer
from litex.build.lattice.icestorm import icestorm_args, icestorm_argdict
from litex.soc.integration.soc_core import *
from litex.soc.integration.soc import SoCRegion
from litex.soc.integration.builder import *
from litex.soc.cores.led import LedChaser

kB = 1024
mB = 1024*kB

class _CRG(Module):
    def __init__(self, platform, sys_clk_freq):
        assert sys_clk_freq == 12e6
        self.rst = Signal()
        self.clock_domains.cd_sys = ClockDomain()
        self.clock_domains.cd_por = ClockDomain()

        sys = platform.request("clk12")
        platform.add_period_constraint(sys, 1e9/12e6)

        # Power on reset
        por_count = Signal(16, reset=2**16-1)
        por_done = Signal()
        self.comb += self.cd_por.clk.eq(ClockSignal("sys"))
        self.comb += por_done.eq(por_count == 0)
        self.sync.por += If(~por_done, por_count.eq(por_count -1))

        # Sys clk
        self.comb += self.cd_sys.clk.eq(sys)
        self.specials += AsyncResetSynchronizer(self.cd_sys, ~por_done)

class BaseSoC(SoCCore):

    def __init__(self, sys_clk_freq=int(12e6), with_led_chaser=True, bios_flash_offset=0x50000, **kwargs):

        platform = fpgawars_alhambra2.Platform()
        kwargs["integrated_rom_size"] = 0

        # SoC
        SoCCore.__init__(self, platform, sys_clk_freq, ident='Litex on Alhambra II', **kwargs)
        # SPI Flash
        from litespi.modules import N25Q032A
        from litespi.opcodes import SpiNorFlashOpCodes as Codes
        self.add_spi_flash(mode='1x', module=N25Q032A(Codes.READ_1_1_1), with_master=False)
        self.bus.add_region("rom", SoCRegion(
            origin=self.bus.regions["spiflash"].origin + bios_flash_offset,
            size=32*kB,
            linker=True
        ))
        self.cpu.set_reset_address(self.bus.regions["rom"].origin)
        
        # CRG
        self.submodules.crg = _CRG(platform, sys_clk_freq)

        # Leds
        if with_led_chaser:
            self.submodules.leds = LedChaser(pads=platform.request_all("user_leds"), sys_clk_freq=sys_clk_freq)


def main():

    from litex.soc.integration.soc import LiteXSoCArgumentParser

    parser = LiteXSoCArgumentParser(description="LiteX SoC on Lattice iCE40UP5k EVN breakout board")
    target_group = parser.add_argument_group(title="Target options")
    target_group.add_argument("--build",             action="store_true", help="Build bitstream.")
    target_group.add_argument("--sys-clk-freq",      default=12e6,        help="System clock frequency.")
    target_group.add_argument("--toolchain",     default="icestorm",   help="FPGA toolchain (radiant or prjoxide).")
    target_group.add_argument("--bios-flash-offset", default="0x50000", help="BIOS offset in SPI flash")
    target_group.add_argument("--flash",             action="store_true", help="Flash Bitstream.")
    builder_args(parser)
    soc_core_args(parser)
    icestorm_args(parser)
    args = parser.parse_args()

    soc = BaseSoC(
        bios_flash_offset = int(args.bios_flash_offset, 0),
        sys_clk_freq      = int(float(args.sys_clk_freq)),
        **soc_core_argdict(args)
    )
    builder = Builder(soc, **builder_argdict(args))
    if args.build:
        builder.build(**icestorm_argdict(args))

    if args.flash:
        flash(args.bios_flash_offset)

if __name__ == "__main__":
    main()
