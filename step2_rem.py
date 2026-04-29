#!/usr/bin/env python3
"""
step2_rem.py — 使用 RiverREM 自动生成荆江段 REM
"""
from riverrem.REMMaker import REMMaker

rem = REMMaker(
    dem='data/dem_proj.tif',
    out_dir='output/',
    interp_pts=3000,
    k=None,
    eps=0.03,
    workers=8,
    chunk_size=2e6
)
rem.make_rem()
print("\n[DONE] REM saved to output/")
