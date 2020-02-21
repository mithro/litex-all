# This file is Copyright (c) 2016-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# This file is Copyright (c) 2016 Tim 'mithro' Ansell <mithro@mithis.com>
# License: BSD

"""Built In Self Test (BIST) modules for testing LiteDRAM functionality."""

from functools import reduce
from operator import xor

from migen import *
from migen.genlib.cdc import MultiReg
from migen.genlib.cdc import PulseSynchronizer
from migen.genlib.cdc import BusSynchronizer

from litex.soc.interconnect.csr import *

from litedram.common import LiteDRAMNativePort
from litedram.frontend.axi import LiteDRAMAXIPort
from litedram.frontend.dma import LiteDRAMDMAWriter, LiteDRAMDMAReader

# LFSR ---------------------------------------------------------------------------------------------

class LFSR(Module):
    """Linear-Feedback Shift Register to generate a pseudo-random sequence.

    Parameters
    ----------
    n_out : int
        Width of the output data signal.
    n_state : int
        LFSR internal state
    taps : list of int
        LFSR taps (from polynom)

    Attributes
    ----------
    o : out
        Output data
    """
    def __init__(self, n_out, n_state, taps):
        self.o = Signal(n_out)

        # # #

        state  = Signal(n_state)
        curval = [state[i] for i in range(n_state)]
        curval += [0]*(n_out - n_state)
        for i in range(n_out):
            nv = ~reduce(xor, [curval[tap] for tap in taps])
            curval.insert(0, nv)
            curval.pop()

        self.sync += [
            state.eq(Cat(*curval[:n_state])),
            self.o.eq(Cat(*curval))
        ]

# Counter ------------------------------------------------------------------------------------------

class Counter(Module):
    """Simple incremental counter.

    Parameters
    ----------
    n_out : int
        Width of the output data signal.

    Attributes
    ----------
    o : out
        Output data
    """
    def __init__(self, n_out):
        self.o = Signal(n_out)

        # # #

        self.sync += self.o.eq(self.o + 1)

# Generator ----------------------------------------------------------------------------------------

@CEInserter()
class Generator(Module):
    """Address/Data Generator.

    Parameters
    ----------
    n_out : int
        Width of the output data signal.

    Attributes
    ----------
    random_enable : in
        Enable Random (LFSR)

    o : out
        Output data
    """
    def __init__(self, n_out, n_state, taps):
        self.random_enable = Signal()
        self.o = Signal(n_out)

        # # #

        lfsr  = LFSR(n_out, n_state, taps)
        count = Counter(n_out)
        self.submodules += lfsr, count

        self.comb += \
            If(self.random_enable,
                self.o.eq(lfsr.o)
            ).Else(
                self.o.eq(count.o)
            )


def get_ashift_awidth(dram_port):
    if isinstance(dram_port, LiteDRAMNativePort):
        ashift = log2_int(dram_port.data_width//8)
        awidth = dram_port.address_width + ashift
    elif isinstance(dram_port, LiteDRAMAXIPort):
        ashift = log2_int(dram_port.data_width//8)
        awidth = dram_port.address_width
    else:
        raise NotImplementedError
    return ashift, awidth

# _LiteDRAMBISTGenerator ---------------------------------------------------------------------------

@ResetInserter()
class _LiteDRAMBISTGenerator(Module):
    def __init__(self, dram_port):
        ashift, awidth = get_ashift_awidth(dram_port)
        self.start       = Signal()
        self.done        = Signal()
        self.run         = Signal(reset=1)
        self.ready       = Signal()
        self.base        = Signal(awidth)
        self.end         = Signal(awidth)
        self.length      = Signal(awidth)
        self.random_data = Signal()
        self.random_addr = Signal()
        self.ticks       = Signal(32)

        # # #

        # Data / Address generators ----------------------------------------------------------------
        data_gen = Generator(31, n_state=31, taps=[27, 30]) # PRBS31
        addr_gen = Generator(31, n_state=31, taps=[27, 30])
        self.submodules += data_gen, addr_gen
        self.comb += data_gen.random_enable.eq(self.random_data)
        self.comb += addr_gen.random_enable.eq(self.random_addr)

        # mask random address to the range <base, end), range size must be power of 2
        addr_mask = Signal(awidth)
        self.comb += addr_mask.eq((self.end - self.base) - 1)

        # DMA --------------------------------------------------------------------------------------
        dma = LiteDRAMDMAWriter(dram_port)
        self.submodules += dma

        cmd_counter = Signal(dram_port.address_width, reset_less=True)

        # Data / Address FSM -----------------------------------------------------------------------
        fsm = FSM(reset_state="IDLE")
        self.submodules += fsm
        fsm.act("IDLE",
            If(self.start,
                NextValue(cmd_counter, 0),
                NextState("RUN")  # always send first data on `start` even without `run` signal
            ),
            NextValue(self.ticks, 0)
        )
        fsm.act("WAIT",
            If(self.run,
                NextState("RUN")
            ),
            NextValue(self.ticks, self.ticks + 1)
        )
        fsm.act("RUN",
            dma.sink.valid.eq(1),
            If(dma.sink.ready,
                self.ready.eq(1),
                data_gen.ce.eq(1),
                addr_gen.ce.eq(1),
                NextValue(cmd_counter, cmd_counter + 1),
                If(cmd_counter == (self.length[ashift:] - 1),
                    NextState("DONE")
                ).Elif(~self.run,
                    NextState("WAIT")
                )
            ),
            NextValue(self.ticks, self.ticks + 1)
        )
        fsm.act("DONE",
            self.ready.eq(1),
            self.done.eq(1)
        )

        if isinstance(dram_port, LiteDRAMNativePort): # addressing in dwords
            dma_sink_addr = dma.sink.address
        elif isinstance(dram_port, LiteDRAMAXIPort):  # addressing in bytes
            dma_sink_addr = dma.sink.address[ashift:]
        else:
            raise NotImplementedError

        self.comb += dma_sink_addr.eq(self.base[ashift:] + (addr_gen.o & addr_mask))
        self.comb += dma.sink.data.eq(data_gen.o)


@ResetInserter()
class _LiteDRAMPatternGenerator(Module):
    def __init__(self, dram_port, init=[]):
        ashift, awidth = get_ashift_awidth(dram_port)
        self.start  = Signal()
        self.done   = Signal()
        self.run    = Signal(reset=1)
        self.ready  = Signal()
        self.ticks  = Signal(32)

        # # #

        # Data / Address pattern -------------------------------------------------------------------
        addr_init, data_init = zip(*init)
        addr_mem = Memory(dram_port.address_width, len(addr_init), init=addr_init)
        data_mem = Memory(dram_port.data_width,    len(data_init), init=data_init)
        addr_port = addr_mem.get_port(async_read=True)
        data_port = data_mem.get_port(async_read=True)
        self.specials += addr_mem, data_mem, addr_port, data_port

        # DMA --------------------------------------------------------------------------------------
        dma = LiteDRAMDMAWriter(dram_port)
        self.submodules += dma

        cmd_counter = Signal(dram_port.address_width, reset_less=True)

        # Data / Address FSM -----------------------------------------------------------------------
        fsm = FSM(reset_state="IDLE")
        self.submodules += fsm
        fsm.act("IDLE",
            If(self.start,
                NextValue(cmd_counter, 0),
                NextState("RUN")
            ),
            NextValue(self.ticks, 0)
        )
        fsm.act("WAIT",
            If(self.run,
                NextState("RUN")
            ),
            NextValue(self.ticks, self.ticks + 1)
        )
        fsm.act("RUN",
            dma.sink.valid.eq(1),
            If(dma.sink.ready,
                self.ready.eq(1),
                NextValue(cmd_counter, cmd_counter + 1),
                If(cmd_counter == (len(init) - 1),
                    NextState("DONE")
                ).Elif(~self.run,
                    NextState("WAIT")
                )
            ),
            NextValue(self.ticks, self.ticks + 1)
        )
        fsm.act("DONE",
            self.ready.eq(1),
            self.done.eq(1)
        )

        if isinstance(dram_port, LiteDRAMNativePort): # addressing in dwords
            dma_sink_addr = dma.sink.address
        elif isinstance(dram_port, LiteDRAMAXIPort):  # addressing in bytes
            dma_sink_addr = dma.sink.address[ashift:]
        else:
            raise NotImplementedError

        self.comb += [
            addr_port.adr.eq(cmd_counter),
            dma_sink_addr.eq(addr_port.dat_r),
            data_port.adr.eq(cmd_counter),
            dma.sink.data.eq(data_port.dat_r),
        ]

# LiteDRAMBISTGenerator ----------------------------------------------------------------------------

class LiteDRAMBISTGenerator(Module, AutoCSR):
    """DRAM memory pattern generator.

    Attributes
    ----------
    reset : in
        Reset the module.

    start : in
        Start the generation.

    done : out
        The module has completed writing the pattern.

    run : in
        Continue generation of new write commands.

    ready : out
        Enabled for one cycle after write command has been sent.

    base : in
        DRAM address to start from.

    end : in
        Max DRAM address.

    length : in
        Number of DRAM words to write.

    random_data : in
        Enable random data (LFSR)

    random_addr : in
        Enable random address (LFSR). Wrapped to (end - base), so may not be unique.

    ticks : out
        Duration of the generation.
    """
    def __init__(self, dram_port):
        ashift, awidth = get_ashift_awidth(dram_port)
        self.reset       = CSR()
        self.start       = CSR()
        self.done        = CSRStatus()
        self.run         = CSRStorage(reset=1)
        self.ready       = CSRStatus()
        self.base        = CSRStorage(awidth)
        self.end         = CSRStorage(awidth)
        self.length      = CSRStorage(awidth)
        self.random      = CSRStorage(fields=[
            CSRField("data", size=1),
            CSRField("addr", size=1),
        ])
        self.ticks       = CSRStatus(32)

        # # #

        clock_domain = dram_port.clock_domain

        core = _LiteDRAMBISTGenerator(dram_port)
        core = ClockDomainsRenamer(clock_domain)(core)
        self.submodules += core

        if clock_domain != "sys":
            reset_sync = PulseSynchronizer("sys", clock_domain)
            start_sync = PulseSynchronizer("sys", clock_domain)
            self.submodules += reset_sync, start_sync
            self.comb += [
                reset_sync.i.eq(self.reset.re),
                core.reset.eq(reset_sync.o),

                start_sync.i.eq(self.start.re),
                core.start.eq(start_sync.o)
            ]

            done_sync = BusSynchronizer(1, clock_domain, "sys")
            self.submodules += done_sync
            self.comb += [
                done_sync.i.eq(core.done),
                self.done.status.eq(done_sync.o)
            ]

            run_sync = BusSynchronizer(1, clock_domain, "sys")
            ready_sync = BusSynchronizer(1, clock_domain, "sys")
            self.submodules += run_sync, ready_sync
            self.comb += [
                run_sync.i.eq(self.run.storage),
                core.run.eq(run_sync.o),

                ready_sync.i.eq(core.ready),
                self.ready.status.eq(ready_sync.o),
            ]

            base_sync   = BusSynchronizer(awidth, "sys", clock_domain)
            end_sync    = BusSynchronizer(awidth, "sys", clock_domain)
            length_sync = BusSynchronizer(awidth, "sys", clock_domain)
            self.submodules += base_sync, end_sync, length_sync
            self.comb += [
                base_sync.i.eq(self.base.storage),
                core.base.eq(base_sync.o),

                end_sync.i.eq(self.end.storage),
                core.end.eq(end_sync.o),

                length_sync.i.eq(self.length.storage),
                core.length.eq(length_sync.o)
            ]

            self.specials += [
                MultiReg(self.random.fields.data, core.random_data, clock_domain),
                MultiReg(self.random.fields.addr, core.random_addr, clock_domain),
            ]

            ticks_sync = BusSynchronizer(32, clock_domain, "sys")
            self.submodules += ticks_sync
            self.comb += [
                ticks_sync.i.eq(core.ticks),
                self.ticks.status.eq(ticks_sync.o)
            ]
        else:
            self.comb += [
                core.reset.eq(self.reset.re),
                core.start.eq(self.start.re),
                self.done.status.eq(core.done),
                core.run.eq(self.run.storage),
                self.ready.status.eq(core.ready),
                core.base.eq(self.base.storage),
                core.end.eq(self.end.storage),
                core.length.eq(self.length.storage),
                core.random_data.eq(self.random.fields.data),
                core.random_addr.eq(self.random.fields.addr),
                self.ticks.status.eq(core.ticks)
            ]

# _LiteDRAMBISTChecker -----------------------------------------------------------------------------

@ResetInserter()
class _LiteDRAMBISTChecker(Module, AutoCSR):
    def __init__(self, dram_port):
        ashift, awidth = get_ashift_awidth(dram_port)
        self.start       = Signal()
        self.done        = Signal()
        self.run         = Signal(reset=1)
        self.ready       = Signal()
        self.base        = Signal(awidth)
        self.end         = Signal(awidth)
        self.length      = Signal(awidth)
        self.random_data = Signal()
        self.random_addr = Signal()
        self.ticks       = Signal(32)
        self.errors      = Signal(32)

        # # #

        # Data / Address generators ----------------------------------------------------------------
        data_gen = Generator(31, n_state=31, taps=[27, 30]) # PRBS31
        addr_gen = Generator(31, n_state=31, taps=[27, 30])
        self.submodules += data_gen, addr_gen
        self.comb += data_gen.random_enable.eq(self.random_data)
        self.comb += addr_gen.random_enable.eq(self.random_addr)

        # mask random address to the range <base, end), range size must be power of 2
        addr_mask = Signal(awidth)
        self.comb += addr_mask.eq((self.end - self.base) - 1)

        # DMA --------------------------------------------------------------------------------------
        dma = LiteDRAMDMAReader(dram_port)
        self.submodules += dma

        # Address FSM ------------------------------------------------------------------------------
        cmd_counter = Signal(dram_port.address_width, reset_less=True)

        cmd_fsm = FSM(reset_state="IDLE")
        self.submodules += cmd_fsm
        cmd_fsm.act("IDLE",
            If(self.start,
                NextValue(cmd_counter, 0),
                If(self.run,
                    NextState("RUN")
                ).Else(
                    NextState("WAIT")
                )
            )
        )
        cmd_fsm.act("WAIT",
            If(self.run,
                NextState("RUN")
            )
        )
        cmd_fsm.act("RUN",
            dma.sink.valid.eq(1),
            If(dma.sink.ready,
                self.ready.eq(1),
                addr_gen.ce.eq(1),
                NextValue(cmd_counter, cmd_counter + 1),
                If(cmd_counter == (self.length[ashift:] - 1),
                    NextState("DONE")
                ).Elif(~self.run,
                    NextState("WAIT")
                )
            )
        )
        cmd_fsm.act("DONE")

        if isinstance(dram_port, LiteDRAMNativePort): # addressing in dwords
            dma_sink_addr = dma.sink.address
        elif isinstance(dram_port, LiteDRAMAXIPort):  # addressing in bytes
            dma_sink_addr = dma.sink.address[ashift:]
        else:
            raise NotImplementedError

        self.comb += dma_sink_addr.eq(self.base[ashift:] + (addr_gen.o & addr_mask))

        # Data FSM ---------------------------------------------------------------------------------
        data_counter = Signal(dram_port.address_width, reset_less=True)

        data_fsm = FSM(reset_state="IDLE")
        self.submodules += data_fsm
        data_fsm.act("IDLE",
            If(self.start,
                NextValue(data_counter, 0),
                NextValue(self.errors, 0),
                NextState("RUN")
            ),
            NextValue(self.ticks, 0)
        )

        data_fsm.act("RUN",
            dma.source.ready.eq(1),
            If(dma.source.valid,
                data_gen.ce.eq(1),
                NextValue(data_counter, data_counter + 1),
                If(dma.source.data != data_gen.o[:min(len(data_gen.o), dram_port.data_width)],
                    NextValue(self.errors, self.errors + 1)
                ),
                If(data_counter == (self.length[ashift:] - 1),
                    NextState("DONE")
                )
            ),
            NextValue(self.ticks, self.ticks + 1)
        )
        data_fsm.act("DONE",
            self.done.eq(1)
        )

@ResetInserter()
class _LiteDRAMPatternChecker(Module, AutoCSR):
    def __init__(self, dram_port, init=[]):
        ashift, awidth = get_ashift_awidth(dram_port)
        self.start  = Signal()
        self.done   = Signal()
        self.run    = Signal(reset=1)
        self.ready  = Signal()
        self.ticks  = Signal(32)
        self.errors = Signal(32)

        # # #

        # Data / Address pattern -------------------------------------------------------------------
        addr_init, data_init = zip(*init)
        addr_mem = Memory(dram_port.address_width, len(addr_init), init=addr_init)
        data_mem = Memory(dram_port.data_width,    len(data_init), init=data_init)
        addr_port = addr_mem.get_port(async_read=True)
        data_port = data_mem.get_port(async_read=True)
        self.specials += addr_mem, data_mem, addr_port, data_port

        # DMA --------------------------------------------------------------------------------------
        dma = LiteDRAMDMAReader(dram_port)
        self.submodules += dma

        # Address FSM ------------------------------------------------------------------------------
        cmd_counter = Signal(dram_port.address_width, reset_less=True)

        cmd_fsm = FSM(reset_state="IDLE")
        self.submodules += cmd_fsm
        cmd_fsm.act("IDLE",
            If(self.start,
                NextValue(cmd_counter, 0),
                If(self.run,
                    NextState("RUN")
                ).Else(
                    NextState("WAIT")
                )
            )
        )
        cmd_fsm.act("WAIT",
            If(self.run,
                NextState("RUN")
            ),
            NextValue(self.ticks, self.ticks + 1)
        )
        cmd_fsm.act("RUN",
            dma.sink.valid.eq(1),
            If(dma.sink.ready,
                self.ready.eq(1),
                NextValue(cmd_counter, cmd_counter + 1),
                If(cmd_counter == (len(init) - 1),
                    NextState("DONE")
                ).Elif(~self.run,
                    NextState("WAIT")
                )
            )
        )
        cmd_fsm.act("DONE")

        if isinstance(dram_port, LiteDRAMNativePort): # addressing in dwords
            dma_sink_addr = dma.sink.address
        elif isinstance(dram_port, LiteDRAMAXIPort):  # addressing in bytes
            dma_sink_addr = dma.sink.address[ashift:]
        else:
            raise NotImplementedError

        self.comb += [
            addr_port.adr.eq(cmd_counter),
            dma_sink_addr.eq(addr_port.dat_r),
        ]

        # Data FSM ---------------------------------------------------------------------------------
        data_counter = Signal(dram_port.address_width, reset_less=True)

        expected_data = Signal.like(dma.source.data)
        self.comb += [
            data_port.adr.eq(data_counter),
            expected_data.eq(data_port.dat_r),
        ]

        data_fsm = FSM(reset_state="IDLE")
        self.submodules += data_fsm
        data_fsm.act("IDLE",
            If(self.start,
                NextValue(data_counter, 0),
                NextValue(self.errors, 0),
                NextState("RUN")
            ),
            NextValue(self.ticks, 0)
        )

        data_fsm.act("RUN",
            dma.source.ready.eq(1),
            If(dma.source.valid,
                NextValue(data_counter, data_counter + 1),
                If(dma.source.data != expected_data,
                    NextValue(self.errors, self.errors + 1)
                ),
                If(data_counter == (len(init) - 1),
                    NextState("DONE")
                )
            ),
            NextValue(self.ticks, self.ticks + 1)
        )
        data_fsm.act("DONE",
            self.done.eq(1)
        )

# LiteDRAMBISTChecker ------------------------------------------------------------------------------

class LiteDRAMBISTChecker(Module, AutoCSR):
    """DRAM memory pattern checker.

    Attributes
    ----------
    reset : in
        Reset the module
    start : in
        Start the checking

    done : out
        The module has completed checking

    run : in
        Continue reading of subsequent locations.
    ready : out
        Enabled for one cycle after read command has been sent.

    base : in
        DRAM address to start from.
    end : in
        Max DRAM address.
    length : in
        Number of DRAM words to check.

    random_data : in
        Enable random data (LFSR)
    random_addr : in
        Enable random address (LFSR). Wrapped to (end - base), so may not be unique.

    ticks: out
        Duration of the check.

    errors : out
        Number of DRAM words which don't match.
    """
    def __init__(self, dram_port):
        ashift, awidth = get_ashift_awidth(dram_port)
        self.reset       = CSR()
        self.start       = CSR()
        self.done        = CSRStatus()
        self.run         = CSRStorage(reset=1)
        self.ready       = CSRStatus()
        self.base        = CSRStorage(awidth)
        self.end         = CSRStorage(awidth)
        self.length      = CSRStorage(awidth)
        self.random      = CSRStorage(fields=[
            CSRField("data", size=1),
            CSRField("addr", size=1),
        ])
        self.ticks       = CSRStatus(32)
        self.errors      = CSRStatus(32)

        # # #

        clock_domain = dram_port.clock_domain

        core = _LiteDRAMBISTChecker(dram_port)
        core = ClockDomainsRenamer(clock_domain)(core)
        self.submodules += core

        if clock_domain != "sys":
            reset_sync = PulseSynchronizer("sys", clock_domain)
            start_sync = PulseSynchronizer("sys", clock_domain)
            self.submodules += reset_sync, start_sync
            self.comb += [
                reset_sync.i.eq(self.reset.re),
                core.reset.eq(reset_sync.o),

                start_sync.i.eq(self.start.re),
                core.start.eq(start_sync.o)
            ]

            done_sync = BusSynchronizer(1, clock_domain, "sys")
            self.submodules += done_sync
            self.comb += [
                done_sync.i.eq(core.done),
                self.done.status.eq(done_sync.o)
            ]

            run_sync = BusSynchronizer(1, clock_domain, "sys")
            ready_sync = BusSynchronizer(1, clock_domain, "sys")
            self.submodules += run_sync, ready_sync
            self.comb += [
                run_sync.i.eq(self.run.storage),
                core.run.eq(run_sync.o),

                ready_sync.i.eq(core.ready),
                self.ready.status.eq(ready_sync.o),
            ]

            base_sync = BusSynchronizer(awidth, "sys", clock_domain)
            end_sync = BusSynchronizer(awidth, "sys", clock_domain)
            length_sync = BusSynchronizer(awidth, "sys", clock_domain)
            self.submodules += base_sync, end_sync, length_sync
            self.comb += [
                base_sync.i.eq(self.base.storage),
                core.base.eq(base_sync.o),

                end_sync.i.eq(self.end.storage),
                core.end.eq(end_sync.o),

                length_sync.i.eq(self.length.storage),
                core.length.eq(length_sync.o)
            ]

            self.specials += [
                MultiReg(self.random.fields.data, core.random_data, clock_domain),
                MultiReg(self.random.fields.addr, core.random_addr, clock_domain),
            ]

            ticks_sync = BusSynchronizer(32, clock_domain, "sys")
            self.submodules += ticks_sync
            self.comb += [
                ticks_sync.i.eq(core.ticks),
                self.ticks.status.eq(ticks_sync.o)
            ]

            errors_sync = BusSynchronizer(32, clock_domain, "sys")
            self.submodules += errors_sync
            self.comb += [
                errors_sync.i.eq(core.errors),
                self.errors.status.eq(errors_sync.o)
            ]
        else:
            self.comb += [
                core.reset.eq(self.reset.re),
                core.start.eq(self.start.re),
                self.done.status.eq(core.done),
                core.run.eq(self.run.storage),
                self.ready.status.eq(core.ready),
                core.base.eq(self.base.storage),
                core.end.eq(self.end.storage),
                core.length.eq(self.length.storage),
                core.random_data.eq(self.random.fields.data),
                core.random_addr.eq(self.random.fields.addr),
                self.ticks.status.eq(core.ticks),
                self.errors.status.eq(core.errors)
            ]
