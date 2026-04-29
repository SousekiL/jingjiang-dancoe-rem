#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01_download_dem.py
====================
自动下载 / 处理荆江段 DEM (数字高程模型)。

功能:
- 若已安装 elevation 库，尝试自动从 AWS S3 下载 SRTM 30m DEM；
- 若自动下载失败，检查 data/ 目录下是否已有用户手动下载的 DEM；
- 使用 gdalwarp 裁剪并重投影至 UTM Zone 49N (EPSG:32649)；
- 输出 data/dem_proj.tif

运行:
    python 01_download_dem.py
"""

import os
import sys
import subprocess
import shutil
from config import *


def try_auto_download():
    """尝试使用 elevation 库自动下载 SRTM 30m DEM (无需登录)。"""
    try:
        import elevation
    except ImportError:
        print("[INFO] `elevation` 库未安装，跳过自动下载。")
        print("       如需自动下载，可执行: pip install elevation")
        return False

    bbox = get_bbox()  # w, s, e, n
    print(f"[AUTO] 尝试自动下载 SRTM DEM (范围: {bbox})")
    print("       数据源: AWS Terrain Tiles (SRTM 30m)")
    print("       国内访问可能较慢，请耐心等待...")

    try:
        # elevation 库 bounds 参数: (west, south, east, north)
        elevation.clip(bounds=bbox, output=DEM_RAW, margin='0%')
        print(f"[OK] 自动下载完成 -> {DEM_RAW}")
        return True
    except Exception as e:
        print(f"[WARN] 自动下载失败: {e}")
        print("       将尝试使用 data/ 目录下的手动下载文件。")
        return False


def find_manual_dem():
    """扫描 data/ 目录，查找用户手动放置的 DEM 文件。"""
    if not os.path.isdir(DATA_DIR):
        return None

    exts = ('.tif', '.tiff', '.hgt', '.img', '.grd')
    candidates = [
        os.path.join(DATA_DIR, f)
        for f in os.listdir(DATA_DIR)
        if f.lower().endswith(exts)
    ]

    if not candidates:
        return None

    # 优先返回文件名含 dem / srtm / aster 的文件
    for c in candidates:
        if any(k in os.path.basename(c).lower() for k in ('dem', 'srtm', 'aster', 'alos')):
            return c
    return candidates[0]


def crop_and_reproject(input_path, output_path):
    """调用 gdalwarp 裁剪并重投影到 UTM 49N。"""
    bbox = get_bbox()  # w, s, e, n

    cmd = [
        "gdalwarp",
        "-overwrite",
        "-t_srs", UTM_CRS,
        "-te", str(bbox[0]), str(bbox[1]), str(bbox[2]), str(bbox[3]),
        "-te_srs", "EPSG:4326",
        "-tr", "30", "30",       # 强制输出 30m 分辨率 (米)
        "-r", "bilinear",
        "-of", "GTiff",
        "-co", "COMPRESS=DEFLATE",
        "-co", "TILED=YES",
        input_path, output_path
    ]

    print(f"[RUN] {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        print("[ERROR] 未找到 `gdalwarp` 命令。")
        print("        请确保 GDAL 已安装并加入系统 PATH:")
        print("          macOS: brew install gdal")
        print("          Ubuntu: sudo apt-get install gdal-bin")
        print("          Windows: 使用 OSGeo4W 安装 GDAL")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] gdalwarp 执行失败: {e}")
        sys.exit(1)

    print(f"[OK] 裁剪与重投影完成 -> {output_path}")


def print_manual_guide():
    """打印手动获取 DEM 的详细指引。"""
    bbox = get_bbox()
    print("=" * 70)
    print("【手动获取 DEM 数据详细指引】")
    print("=" * 70)

    print("\n>>> 推荐方式：地理空间数据云 (gscloud.cn, 中国境内速度最快)")
    print("-" * 70)
    print("  1. 访问 https://www.gscloud.cn 并注册/登录（支持 QQ 登录）")
    print("  2. 点击顶部菜单: 高级检索")
    print("  3. 数据集选择:  DEM数字高程数据")
    print("  4. 产品选择:    ASTER GDEM 30M 分辨率数字高程数据")
    print("     (或 SRTM DEM 90M / 30M，视可用性而定)")
    print("  5. 空间范围 -> 选择'经纬度'，输入以下范围:")
    print(f"       最小经度 (West) : {bbox[0]}")
    print(f"       最小纬度 (South): {bbox[1]}")
    print(f"       最大经度 (East) : {bbox[2]}")
    print(f"       最大纬度 (North): {bbox[3]}")
    print("  6. 点击'检索'，勾选所有结果项，批量下载 (.zip)")
    print("  7. 解压后将 .tif 格式的 DEM 文件放入本项目的 data/ 目录")
    print("     (只需放原始栅格文件，不需要 .ovr 或 .aux.xml)")

    print("\n>>> 备用方式：NASA EarthData (SRTM 30m)")
    print("-" * 70)
    print("  1. 访问 https://earthexplorer.usgs.gov/")
    print("  2. 注册 NASA EarthData 账号（免费）")
    print("  3. 搜索栏输入 'SRTM', 选择 'SRTM 1 Arc-Second Global'")
    print("  4. 用坐标或地图工具框选荆江范围，下载 GeoTIFF")
    print("  5. 将所有 .tif 放入 data/ 目录")

    print("\n>>> 备用方式：OpenTopography")
    print("-" * 70)
    print("  1. 访问 https://portal.opentopography.org/datasetMetadata")
    print("  2. 搜索 'SRTM GL1' 或 'NASA DEM', 注册并下载")

    print("\n>>> 完成后再次运行:")
    print("     python 01_download_dem.py")
    print("=" * 70)


def main():
    print("=" * 70)
    print("步骤 1/3: 准备 DEM 数据")
    print("=" * 70)

    os.makedirs(DATA_DIR, exist_ok=True)

    # 情况 A: 已经存在处理好的投影 DEM，直接复用
    if os.path.exists(DEM_PROJ):
        print(f"[INFO] 已存在处理后的 DEM: {DEM_PROJ}")
        print("       如需重新生成，请删除该文件再运行。")
        return

    # 情况 B: 自动下载
    dem_source = None
    if try_auto_download():
        dem_source = DEM_RAW
    else:
        # 情况 C: 查找手动下载的 DEM
        manual_path = find_manual_dem()
        if manual_path:
            print(f"[INFO] 检测到手动下载的 DEM: {manual_path}")
            dem_source = manual_path
        else:
            print("[ERROR] 未找到任何 DEM 数据源。")
            print_manual_guide()
            sys.exit(1)

    # 执行裁剪 + 重投影
    crop_and_reproject(dem_source, DEM_PROJ)

    # 清理原始下载文件（可选）
    if dem_source == DEM_RAW and os.path.exists(DEM_RAW):
        print(f"[INFO] 保留原始下载文件: {DEM_RAW}")

    print("\n[COMPLETE] DEM 处理完成!")
    print(f"          输出: {DEM_PROJ}")
    print("          下一步: python 02_make_rem.py")


if __name__ == "__main__":
    main()
