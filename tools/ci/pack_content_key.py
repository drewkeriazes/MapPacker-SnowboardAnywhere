#!/usr/bin/env python3
"""FEAT-251: the content key of a built pack (publish_pack.content_key: a hash of what the pack holds, leaving out
meta.json's build stamps), so two builds of the same synthetic pack from different code give the same key. The
render-budgets job in checks.yml keys its reused result on main's and the PR's keys.

python tools/ci/pack_content_key.py <pack_dir>   (prints 16 hex characters; needs numpy and pillow, as the pipeline)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "pipeline"))
from publish_pack import content_key  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 2 or not os.path.isfile(os.path.join(sys.argv[1], "meta.json")):
        sys.exit("usage: pack_content_key.py <pack_dir> (a folder with meta.json)")
    print(content_key(sys.argv[1]))
