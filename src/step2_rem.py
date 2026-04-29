#!/usr/bin/env python3
"""
step2_rem.py — 使用 RiverREM 自动生成荆江段 REM
"""
from riverrem.REMMaker import REMMaker

import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

rem = REMMaker(
    dem=os.path.join(ROOT, 'data/dem_proj.tif'),
    out_dir=os.path.join(ROOT, 'output/'),
    interp_pts=3000,
    k=None,
    eps=0.03,
    workers=8,
    chunk_size=2e6
)
rem.make_rem()
print("\n[DONE] REM saved to output/")
