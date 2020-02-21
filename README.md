
## Set up instructions

### Installing

To install the LiteX ecosystem you need to;

 1. Use `pip` to install the base requirements (`requirements.txt`).
 2. Then for each CPU type you wish to use with LiteX you will need to;
   * Use `pip` to install the requirements for the given CPU
     `requirements.CPU.txt` (For example, `requirements.vexriscv.txt`).
   * Install a C compiler to be used with the given CPU.

### Installing as a user

To install as a user, make sure you supply `--user` to the

```bash

# Install the base requirements
pip install --user requirements.txt

# Install the requirements for the CPUs you want to use.
pip install --user requirements.vexriscv.txt

# Download and install a RISCV C compiler
XXXXXX
```

### Install system wide

```bash
# Install the base requirements
sudo pip install requirements.txt

# Install the requirements for the CPUs you want to use.
sudo pip install requirements.vexriscv.txt

# Download and install a RISCV C compiler
XXXXXX
```

### Using a virtual env

```bash
# Setup virtualenv
virtualenv --python=python3 venv
source venv/bin/activate

# Install the base requirements
pip install requirements.txt

# Install the requirements for the CPUs you want to use.
pip install --user requirements.vexriscv.txt

# Download and install a RISCV C compiler
XXXXXX
```

### Using conda

```
# Create a conda environment
conda env create --name litex --path env
conda activate litex

# Install the base requirements
pip install requirements.txt

# Install the requirements for the CPUs you want to use.
pip install --user requirements.vexriscv.txt

# Download and install a RISCV C compiler
conda install gcc-cross-rv32
```
