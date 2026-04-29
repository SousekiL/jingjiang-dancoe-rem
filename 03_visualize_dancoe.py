#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03_visualize_dancoe.py — Dan Coe 打印级风格渲染
========================
将 REM 渲染为 Dan Coe 风格的伪彩色可视化：
- 黑色背景中，电光蓝/玫红/金琥珀色的河流脉络从黑暗中浮现
- 当前河道极度高亮，古河道痕迹在黑暗中隐约可见
- GDAL 山体阴影叠加增强 3D 立体感
- 后处理：暗角、伽马校正、降噪、16:9 宽幅裁切
"""

import os
import sys
import warnings
import argparse
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
import rasterio
from rasterio.transform import from_bounds

from config import *

warnings.filterwarnings('ignore')

COLOR_SCHEMES = {
    'electric_blue': [
        (0.000, '#d0e8ff'),
        (0.020, '#00ccff'),
        (0.080, '#0077cc'),
        (0.200, '#003388'),
        (0.400, '#001144'),
        (0.650, '#000522'),
        (1.000, '#000000'),
    ],
    'magenta_glow': [
        (0.000, '#ffe0f0'),
        (0.020, '#ff33aa'),
        (0.080, '#cc0077'),
        (0.200, '#770044'),
        (0.400, '#330018'),
        (0.650, '#0d0005'),
        (1.000, '#000000'),
    ],
    'gold_ember': [
        (0.000, '#fff5d0'),
        (0.020, '#ffcc00'),
        (0.080, '#cc8800'),
        (0.200, '#774400'),
        (0.400, '#331800'),
        (0.650, '#0d0500'),
        (1.000, '#000000'),
    ],
    'cyan_neon': [
        (0.000, '#d4fffa'),
        (0.020, '#00ffcc'),
        (0.080, '#00aa77'),
        (0.200, '#005544'),
        (0.400, '#001a14'),
        (0.650, '#000a07'),
        (1.000, '#000000'),
    ],
    'ocean_depth': [
        (0.000, '#e0f5ff'),
        (0.020, '#00aacc'),
        (0.080, '#006688'),
        (0.200, '#003344'),
        (0.400, '#00111a'),
        (0.650, '#000608'),
        (1.000, '#000000'),
    ],
    'volcanic_red': [
        (0.000, '#fff0e0'),
        (0.020, '#ff3300'),
        (0.080, '#cc2200'),
        (0.200, '#881100'),
        (0.400, '#440800'),
        (0.650, '#1a0200'),
        (1.000, '#000000'),
    ],
}


def build_colormap(name):
    from matplotlib.colors import LinearSegmentedColormap
    stops = COLOR_SCHEMES.get(name, COLOR_SCHEMES['electric_blue'])
    pos = [s[0] for s in stops]
    cols = [s[1] for s in stops]
    return LinearSegmentedColormap.from_list(name, list(zip(pos, cols)), N=1024)


def generate_hillshade(dem_path, mask=None):
    from osgeo import gdal
    tmp = dem_path.replace('.tif', '_hs.tif')
    gdal.DEMProcessing(tmp, dem_path, 'hillshade',
                       computeEdges=True,
                       azimuth=315, altitude=35, zFactor=3)
    with rasterio.open(tmp) as s:
        hs = s.read(1).astype(np.float32)
    os.unlink(tmp)
    hs = np.clip((hs - hs.min()) / (hs.max() - hs.min() + 1e-10), 0, 1)
    if mask is not None:
        hs[~mask] = 0.5
    return hs


def add_vignette(rgb, strength=0.35):
    h, w = rgb.shape[:2]
    y = np.linspace(-1, 1, h).reshape(-1, 1)
    x = np.linspace(-1, 1, w).reshape(1, -1)
    dist = np.sqrt(x**2 + y**2)
    vignette = 1 - strength * (dist / np.sqrt(2))
    vignette = np.clip(vignette, 0, 1)
    vignette = vignette[:, :, np.newaxis]
    return np.clip(rgb * vignette, 0, 255).astype(np.float32)


def smooth_river(rem_rgb, rem_mask, radius=0.5):
    from scipy.ndimage import gaussian_filter
    smoothed = gaussian_filter(rem_rgb.astype(np.float32), sigma=(radius, radius, 0))
    return np.where(rem_mask[:, :, np.newaxis], smoothed, rem_rgb).astype(np.float32)


def gamma_correct(rgb, gamma=1.2):
    return 255 * np.power(rgb / 255.0, 1.0 / gamma)


def visualize(rem_path, cmap_name, out_png, out_tif, dem_path=None):
    print("=" * 70)
    print(f"渲染 Dan Coe 风格: {cmap_name}")
    print("=" * 70)

    with rasterio.open(rem_path) as src:
        rem = src.read(1)
        profile = src.profile
        nodata = src.nodata if src.nodata is not None else -9999
        crs = src.crs
        transform = src.transform
        width, height = src.width, src.height

    valid = (rem != nodata) & (~np.isnan(rem)) & (~np.isinf(rem))
    print(f"REM: {width}x{height}, 有效像素: {valid.sum():,} ({valid.sum()/rem.size*100:.1f}%)")

    vmin, vmax = VIZ_MIN, VIZ_MAX
    normalized = np.full(rem.shape, 1.0, dtype=np.float32)
    normalized[valid] = np.clip((rem[valid] - vmin) / (vmax - vmin), 0, 1)

    # 低于河面的像素（负REM）设为 0（最暗），河道本身也极暗
    below_river = valid & (rem < 0)
    normalized[below_river] = 0.0

    # 高于 vmax 的设为 1.0（纯黑）
    above_max = valid & (rem > vmax)
    normalized[above_max] = 1.0

    cmap = build_colormap(cmap_name)
    rgba = cmap(normalized)

    # 山体阴影
    if dem_path and os.path.exists(dem_path):
        print("[SHADE] 生成山体阴影叠加...")
        hs = generate_hillshade(dem_path, mask=valid)
    else:
        hs = np.ones(rem.shape, dtype=np.float32) * 0.5

    # 柔光混合: 阴影处变暗 30%，亮处保持
    hs_3ch = np.dstack([hs, hs, hs])
    multiplier = 0.65 + 0.35 * hs_3ch
    rgba[:, :, :3] *= multiplier
    rgba = np.clip(rgba, 0, 1)

    # 无效区域纯黑
    rgba[~valid] = [0, 0, 0, 1]

    rgb = (rgba[:, :, :3] * 255).astype(np.uint8)

    print("[POST] 后处理: 平滑河流纹理 + 伽马校正 + 暗角...")
    rgb = smooth_river(rgb, valid, radius=0.4)
    rgb = gamma_correct(rgb, gamma=1.15)
    rgb = add_vignette(rgb, strength=0.28)
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)

    # 保存 GeoTIFF
    print(f"[SAVE] GeoTIFF -> {out_tif}")
    with rasterio.open(out_tif, 'w', driver='GTiff', height=height, width=width,
                       count=3, dtype='uint8', crs=crs, transform=transform,
                       compress='deflate', tiled=True) as dst:
        for i in range(3):
            dst.write(rgb[:, :, i], i + 1)

    # 保存 PNG
    print(f"[SAVE] PNG -> {out_png}")
    Image.fromarray(rgb).save(out_png, 'PNG', compress_level=6)

    # 生成图例
    import matplotlib.pyplot as plt
    from matplotlib.cm import ScalarMappable
    fig, ax = plt.subplots(figsize=(4, 0.35))
    sm = ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=vmin, vmax=vmax))
    sm.set_array([])
    cbar = plt.colorbar(sm, cax=ax, orientation='horizontal')
    cbar.set_label("Height above river (m)", color='white', fontsize=9)
    cbar.ax.tick_params(colors='white', labelsize=8)
    fig.patch.set_facecolor('black')
    ax.set_facecolor('black')
    leg = os.path.join(OUTPUT_DIR, f"colorbar_{cmap_name}.png")
    plt.savefig(leg, dpi=150, bbox_inches='tight', facecolor='black', edgecolor='none')
    plt.close()
    print(f"[SAVE] 图例 -> {leg}")

    stats = rem[valid]
    print("\n" + "=" * 70)
    print("渲染完成!")
    print(f"  配色:        {cmap_name}")
    print(f"  范围:        {vmin} ~ {vmax} m")
    print(f"  河道高程:    {stats.min():.1f} ~ {stats.max():.1f} m")
    print(f"  已保存: {os.path.abspath(out_png)}")
    print(f"  已保存: {os.path.abspath(out_tif)}")
    print("=" * 70)


def main():
    ap = argparse.ArgumentParser(description="Dan Coe 风格 REM 渲染")
    ap.add_argument("--cmap", type=str, default=VIZ_CMAP,
                    choices=list(COLOR_SCHEMES.keys()),
                    help="配色方案")
    ap.add_argument("--no-shade", action='store_true', help="不叠加山体阴影")
    args = ap.parse_args()
    dem = None if args.no_shade else DEM_PROJ
    visualize(REM_TIF, args.cmap, VIZ_PNG, VIZ_TIF, dem_path=dem)


if __name__ == "__main__":
    main()
