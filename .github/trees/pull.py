#!/usr/bin/env python3

import subprocess

import trees

for path, name, url in trees.trees():
    print()
    print("Pulling updates for", name, "into", path, "from", url)
    print("-"*75)
    subprocess.check_call(
        ['git', 'subtree', 'pull', '-P', path, url, 'master'])
    print("-"*75)
