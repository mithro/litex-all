#!/usr/bin/env python3
import os.path
import setuptools
import sys


MODULES_SETUP = {}


def import_setup_py(setup_py):
    """Get the data from the setup() call in a setup.py file."""
    setuptools._setup = setuptools.setup
    try:
        # Mock out the setuptools.setup function to just stash the data.
        def fake_setup(name, **kw):
            MODULES_SETUP[name] = kw
        setuptools.setup = fake_setup

        setup_dir = os.path.dirname(setup_py)
        orig_dir = os.path.abspath(os.curdir)
        try:
            os.chdir(setup_dir)
            sys.path.insert(0, '.')
            MODULES_SETUP.clear()
            exec("import setup")
            assert len(MODULES_SETUP) == 1, MODULES_SETUP
            data = list(MODULES_SETUP.items())
            del sys.modules['setup']
            MODULES_SETUP.clear()
            return data[0]
        finally:
            sys.path.pop(0)
            os.chdir(orig_dir)
    finally:
        setuptools.setup = setuptools._setup


def trees():
    files = sorted(os.listdir())
    for d in files:
        if not os.path.isdir(d):
            continue
        setup_py = os.path.join(d, 'setup.py')
        if not os.path.exists(setup_py):
            continue
        name, data = import_setup_py(setup_py)

        src_url = None
        # setup(download_url='https://github.com/XXXX')
        src_url = data.get('download_url', src_url)
        # setup(project_urls={'Source':'https://github.com/XXXX'})
        src_url = data.get('project_urls', {}).get('Source', src_url)
        yield os.path.abspath(d), name, src_url


if __name__ == "__main__":
    for d, name, src in trees():
        print("{:60s}".format(d), "is", "{:10s}".format(name), "from", src)
