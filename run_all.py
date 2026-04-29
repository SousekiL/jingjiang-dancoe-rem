#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_all.py
==========
一键执行全部流程：DEM 预处理 → REM 生成 → 可视化渲染。

用法:
    python run_all.py [--cmap cmap_name]

可选参数:
    --cmap  指定配色方案 (默认 electric_blue)
            可选: electric_blue, cyan_neon, magenta_glow, gold_ember, ocean_depth, volcanic_red

示例:
    python run_all.py
    python run_all.py --cmap magenta_glow
"""

import sys
import argparse
import subprocess

COMMANDS = [
    ("步骤 1/3: DEM 预处理", ["python", "01_download_dem.py"]),
    ("步骤 2/3: REM 生成", ["python", "02_make_rem.py"]),
]


def run_step(label, cmd):
    print("\n" + "=" * 70)
    print(label)
    print("=" * 70)
    result = subprocess.run(cmd, shell=False)
    if result.returncode != 0:
        print(f"\n[ERROR] {label} 执行失败，退出码: {result.returncode}")
        print("        请根据上方错误信息排查问题。")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="一键运行荆江 REM 全流程")
    parser.add_argument("--cmap", type=str, default="electric_blue",
                        choices=['electric_blue', 'cyan_neon', 'magenta_glow',
                                 'gold_ember', 'ocean_depth', 'volcanic_red'],
                        help="可视化配色方案")
    args = parser.parse_args()

    for label, cmd in COMMANDS:
        run_step(label, cmd)

    # 步骤3 传入配色参数
    viz_cmd = ["python", "03_visualize_dancoe.py", "--cmap", args.cmap]
    run_step("步骤 3/3: Dan Coe 风格可视化", viz_cmd)

    print("\n" + "=" * 70)
    print("🎉 全流程执行完毕!")
    print("=" * 70)
    print("\n输出成果位于 output/ 目录:")
    print("  - rem_visualization.png      (高清观赏图)")
    print("  - rem_visualization.tif      (带坐标的 GeoTIFF)")
    print("  - rem.tif                    (原始 REM 数据)")
    print("  - colorbar_*.png             (色带图例)")
    print("\n祝制图顺利!")


if __name__ == "__main__":
    main()
