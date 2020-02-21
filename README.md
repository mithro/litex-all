
# Setting Up

## Installing

To install the LiteX ecosystem you need to;

 1. Make sure you have all the git submodules.
 2. Then for each CPU type you wish to use with LiteX you will need to;
   * Use `pip` to install the requirements for the given CPU
     `requirements.CPU.txt` (For example, `requirements.vexriscv.txt`).
   * Install a C compiler to be used with the given CPU.

### Installing as a user

To install as a user, make sure you supply `--user` to the

```shell-session
# Make sure you have all the submodules
git submodule update --init --recursive

# Install the requirements for the CPUs you want to use, this will also install
# any common requirements.
pip install --user ./requirements/vexriscv.txt

# Download and install a RISCV C compiler
XXXXXX
```

### Install system wide

```shell-session
# Make sure you have all the submodules
git submodule update --init --recursive

# Install the requirements for the CPUs you want to use, this will also install
# any common requirements.
sudo pip install requirements/vexriscv.txt

# Download and install a RISCV C compiler
XXXXXX
```

### Using a virtual env

```shell-session
# Make sure you have all the submodules
git submodule update --init --recursive

# Setup virtualenv
virtualenv --python=python3 venv
source venv/bin/activate

# Install the requirements for the CPUs you want to use, this will also install
# any common requirements.
pip install --user requirements/vexriscv.txt

# Download and install a RISCV C compiler
XXXXXX
```

### Using conda

```shell-session
# Make sure you have all the submodules
git submodule update --init --recursive

# Create a conda environment
conda env create --name litex --path env
conda activate litex

# Install the requirements for the CPUs you want to use, this will also install
# any common requirements.
pip install --user requirements/vexriscv.txt

# Download and install a RISCV C compiler
conda install gcc-cross-rv32
```

# Using LiteX for your project

There are a couple of ways to use LiteX for your project.

## Submodule in the whole LiteX ecosystem

```shell-session
# Create an initial commit
git init
touch README.md
git add README.md
git commit -m"First commit"

# Submodule in the whole LiteX ecosystem
git submodule add https://github.com/enjoy-digital/litex.git third_party/litex

# Set up your requirements.txt file
cat > requirements.txt <<EOF
-r third_party/litex/requirements/vexriscv.txt
EOF

# Follow the same set up instructions as LiteX itself.
...
```

## Submodule in specific bits of the LiteX ecosystem

```shell-session
# Create an initial commit
git init
touch README.md
git add README.md
git commit -m"First commit"

# Submodule in the whole LiteX ecosystem
git submodule add https://github.com/enjoy-digital/litex-core.git third_party/litex-core
git submodule add https://github.com/enjoy-digital/litedram.git third_party/litedram
git submodule add https://github.com/enjoy-digital/liteeth.git third_party/liteeth
git submodule add https://github.com/litex-hub/litex-data-vexriscv.git third_party/litex-data-vexriscv

# Set up your requirements.txt file
cat > requirements.txt <<EOF
-e ./third_party/litex-core
-e ./third_party/litedram
-e ./third_party/liteeth
-e ./third_party/litex-data-vexriscv
EOF

# Follow the same set up instructions as LiteX itself.
...
```

# Developing

The LiteX ecosystem setup uses three important concepts;
 * Python packages and `requirements.txt` files
 * Python namespace modules
 * `git subtrees`

Python packages and `requirements.txt` files should be familiar to most Python
developers. LiteX ecosystem uses a couple of features which are less commonly
know about;
 * `-e` -- Editable installs, this is where pip installs a Python module's
   source files in a way that you can continue to edit the files in your source
   tree.

 * `./XXXX` -- Relative install pathways, this tells pip to install from the
   source found in a local directory rather than downloading from PyPi.

 * `-r` -- Recursive requirements files. This lets a requirements file include
   another requirements file.

To allow LiteX to be install from multiple Python modules (IE `litex-core`,
`litex-boards`, etc), "Python namespace modules" are used. LiteX uses the
["pkgutil-style namespace packages"](https://packaging.python.org/guides/packaging-namespace-packages/#pkgutil-style-namespace-packages)
as recommended by the [Python Packaging Authority](https://packaging.python.org).

Finally, to provide a unified LiteX ecosystem, LiteX uses a little known
alternative to "git submodules" called
["git subtrees"](https://github.com/git/git/blob/master/contrib/subtree/git-subtree.txt).

To make things *mildly* easier, there are a couple of small scripts for working
with git subtrees. They are;

 * `./.github/trees/trees.py` - Lists the subtrees inside this module.

 * `./.github/trees/push.sh` - Splits apart any commits in the master repo and
   pushes them into the individual `liteXXXX` repositories.

   Note: To keep the master repo and the individual `liteXXX` repositories
   closely in sync, this is automatically run by Travis CI on any commit to the
   master branch of the master repo.

 * `./.github/trees/pull.sh` - Pulls any changes in the individual `liteXXX`
   repositories into the common repo.

   Note: To keep the master repo and the individual `liteXXX` repositories
   closely in sync, a bot automatically runs this script and sends pull
   requests to the master repository. If the tests pass on Travis CI, then the
   pull request is also automatically merged.

