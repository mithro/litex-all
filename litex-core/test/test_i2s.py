# This file is Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# License: BSD

import unittest

from migen import *

from litex.soc.cores.i2s import S7I2SSlave


class TestI2S(unittest.TestCase):
    def test_s7i2sslave_syntax(self):
        i2s_pads = Record([("rx", 1), ("tx", 1), ("sync", 1), ("clk", 1)])
        i2s = S7I2SSlave(pads=i2s_pads, fifo_depth=256)

