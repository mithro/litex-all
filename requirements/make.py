#!/usr/bin/env python3
import os
import os.path
import pprint
import sys

from litex.soc.cores.cpu import CPUS, CPU_VARIANTS

cpus = [c for c in sorted(CPUS.keys()) if c != "None"]

print("Found", len(cpus))
pprint.pprint(cpus)

# Create a ./requirements/XXX.txt for each CPU.
for c in cpus:
    with open('requirements/{}.txt'.format(c), 'w') as f:
        f.write("""\
# Install requirements needed to use the {c} soft CPU inside LiteX
-e git+https://github.com/litex-hub/litex-data-{c}.git#egg=litex-data-{c}
# Install the common requirements that LiteX needs
-r ./requirements/base.txt
""".format(c=c))

# Create a ./requirements/all.txt which includes *all* requirements.
with open('requirements/all.txt', 'w') as f:
    f.write("# Install requirements for *all* soft CPUs supported by LiteX!\n")
    for c in cpus:
        f.write("-r ./requirements/{}.txt\n".format(c))
    f.write("""\
# Install the common requirements that LiteX needs
-r ./requirements/base.txt
""")


# Create a ./requirements/riscv.txt which includes only RISC-V cpus
def is_riscv(gcc_triple):
    if isinstance(gcc_triple, tuple):
        return any(is_riscv(t) for t in gcc_triple)
    return 'riscv' in gcc_triple


with open('requirements/riscv.txt', 'w') as f:
    f.write("# Install requirements needed to use any of the RISC-V soft CPUs inside LiteX\n")
    for c in cpus:
        if is_riscv(CPUS[c].gcc_triple):
            f.write("-r ./requirements/{}.txt\n".format(c))
    f.write("""\
# Install the common requirements that LiteX needs
-r ./requirements/base.txt
""")
