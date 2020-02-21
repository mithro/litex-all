#!/usr/bin/env python3

import subprocess

import trees

for path, name, url in trees.trees():
    print()
    print("Pushing updates for", name, "from", path, "into", url)
    print("-"*75)
    subprocess.check_call(
        ['git', 'subtree', 'push', '-P', path, url, 'master'])
    print("-"*75)
