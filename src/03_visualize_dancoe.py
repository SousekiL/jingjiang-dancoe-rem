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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
    'samplecases_green': [
        (0.000, '#f6fff4'),
        (0.020, '#c9f4b4'),
        (0.080, '#74d98f'),
        (0.220, '#2cb6a2'),
        (0.450, '#1686b0'),
        (0.750, '#0b4b83'),
        (1.000, '#061a3a'),
    ],
}


def build_colormap(name):
    stops = COLOR_SCHEMES.get(name, COLOR_SCHEMES['electric_blue'])
    pos = np.array([s[0] for s in stops], dtype=np.float32)
    cols = [s[1] for s in stops]

    def hex_to_rgb01(h):
        h = h.lstrip("#")
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
        return np.array([r, g, b], dtype=np.float32)

    rgb = np.stack([hex_to_rgb01(c) for c in cols], axis=0)  # Kx3

    n = 1024
    xs = np.linspace(0.0, 1.0, n, dtype=np.float32)
    lut = np.empty((n, 4), dtype=np.float32)
    for ch in range(3):
        lut[:, ch] = np.interp(xs, pos, rgb[:, ch])
    lut[:, 3] = 1.0
    return lut


def generate_hillshade(dem_path, mask=None):
    """
    Generate hillshade in [0,1].
    Prefer GDAL if available; otherwise fall back to a NumPy gradient-based hillshade.
    """
    try:
        from osgeo import gdal  # type: ignore

        tmp = dem_path.replace(".tif", "_hs.tif")
        gdal.DEMProcessing(
            tmp,
            dem_path,
            "hillshade",
            computeEdges=True,
            azimuth=315,
            altitude=35,
            zFactor=3,
        )
        with rasterio.open(tmp) as s:
            hs = s.read(1).astype(np.float32)
        os.unlink(tmp)
    except Exception:
        # Fallback: approximate hillshade from gradients
        with rasterio.open(dem_path) as s:
            dem = s.read(1).astype(np.float32)
            src_nodata = s.nodata
            if src_nodata is not None:
                dem = np.where(dem == src_nodata, np.nan, dem)
            # pixel size (meters in projected CRS)
            dx = float(abs(s.transform.a)) if s.transform is not None else 30.0
            dy = float(abs(s.transform.e)) if s.transform is not None else 30.0

        dem_filled = np.where(np.isnan(dem), np.nanmedian(dem), dem)
        gy, gx = np.gradient(dem_filled, dy, dx)
        slope = np.arctan(np.sqrt(gx * gx + gy * gy))
        aspect = np.arctan2(-gx, gy)

        az = np.deg2rad(315.0)
        alt = np.deg2rad(35.0)
        hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
        hs = (hs + 1.0) / 2.0
        hs = hs.astype(np.float32)

    hs = np.clip((hs - np.nanmin(hs)) / (np.nanmax(hs) - np.nanmin(hs) + 1e-10), 0, 1)
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


def _soft_light(base, blend):
    """
    base/blend in [0,1], returns [0,1]
    """
    base = np.clip(base, 0, 1)
    blend = np.clip(blend, 0, 1)
    return np.where(
        blend <= 0.5,
        base - (1 - 2 * blend) * base * (1 - base),
        base + (2 * blend - 1) * (np.sqrt(base + 1e-12) - base),
    )


def _apply_bloom(rgb01, glow01, sigmas_px, weights, strength):
    from scipy.ndimage import gaussian_filter

    if strength <= 0:
        return rgb01

    glow = np.clip(glow01, 0, 1).astype(np.float32)
    bloom = np.zeros_like(glow, dtype=np.float32)
    for sigma, w in zip(sigmas_px, weights):
        if sigma <= 0 or w <= 0:
            continue
        bloom += float(w) * gaussian_filter(glow, sigma=float(sigma))

    bloom = np.clip(bloom, 0, 1)
    bloom_rgb = np.dstack([bloom, bloom, bloom])
    return np.clip(rgb01 + float(strength) * bloom_rgb, 0, 1)


def _hex_to_rgb01(h):
    h = h.lstrip("#")
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return np.array([r, g, b], dtype=np.float32)


def _rasterize_mainstem_mask(reference_geojson_utm, out_shape, out_transform, out_crs, width_m):
    try:
        import geopandas as gpd
    except Exception:
        return None

    if not os.path.exists(reference_geojson_utm):
        return None

    try:
        gdf = gpd.read_file(reference_geojson_utm)
        if gdf.empty:
            return None
        if gdf.crs is None:
            gdf = gdf.set_crs(UTM_CRS)
        if out_crs is not None and str(gdf.crs) != str(out_crs):
            gdf = gdf.to_crs(out_crs)
        geom = gdf.geometry.iloc[0]
        if geom is None or geom.is_empty:
            return None
    except Exception:
        return None

    px = float(abs(out_transform.a)) if out_transform is not None else 30.0
    width_px = max(1.0, float(width_m) / px)

    from rasterio.features import rasterize

    # burn a thin centerline first
    base = rasterize(
        [(geom, 1)],
        out_shape=out_shape,
        transform=out_transform,
        fill=0,
        dtype="uint8",
        all_touched=True,
    ).astype(bool)

    # thicken via dilation to approximate width_m
    try:
        from scipy.ndimage import binary_dilation

        iterations = int(np.ceil(width_px / 2.0))
        mask = binary_dilation(base, iterations=iterations)
        return mask
    except Exception:
        return base


def _rasterize_buffered_lines(reference_geojson, out_shape, out_transform, out_crs, width_m):
    """
    Rasterize buffered linework (good for tributary 'capillary' overlays).
    width_m is approximate full width in meters.
    """
    try:
        import geopandas as gpd
    except Exception:
        return None

    if not os.path.exists(reference_geojson):
        return None

    try:
        gdf = gpd.read_file(reference_geojson)
        if gdf.empty:
            return None
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        if out_crs is not None and str(gdf.crs) != str(out_crs):
            gdf = gdf.to_crs(out_crs)
    except Exception:
        return None

    if width_m <= 0:
        return None

    try:
        buffered = gdf.geometry.buffer(float(width_m) / 2.0, cap_style=2, join_style=2)
        geom = buffered.unary_union
    except Exception:
        return None

    from rasterio.features import rasterize

    mask = rasterize(
        [(geom, 1)],
        out_shape=out_shape,
        transform=out_transform,
        fill=0,
        dtype="uint8",
        all_touched=True,
    ).astype(bool)
    return mask

def visualize(rem_path, cmap_name, out_png, out_tif, dem_path=None, preset_name="default", write_colorbar=False):
    print("=" * 70)
    print(f"渲染 Dan Coe 风格: {cmap_name}")
    print(f"Preset: {preset_name}")
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

    preset = STYLE_PRESETS.get(preset_name, STYLE_PRESETS.get("default", {}))
    vmin = VIZ_MIN
    vmax = VIZ_MAX

    tone_percentile = preset.get("tone_percentile")
    if tone_percentile is not None:
        stats_mask = valid & (rem >= 0)
        if stats_mask.any():
            vmax_auto = float(np.percentile(rem[stats_mask].astype(np.float32), float(tone_percentile)))
            if np.isfinite(vmax_auto) and vmax_auto > vmin:
                vmax_cap_factor = float(preset.get("tone_vmax_cap_factor", 8.0))
                vmax_cap = max(float(VIZ_MAX), float(VIZ_MAX) * vmax_cap_factor)
                vmax = min(vmax_auto, vmax_cap)
                if vmax < vmax_auto:
                    print(f"[TONE] vmax 使用 p{tone_percentile}: {vmax_auto:.2f} m, 但已封顶到 {vmax:.2f} m")
                else:
                    print(f"[TONE] vmax 使用 p{tone_percentile}: {vmax:.2f} m")
    normalized = np.full(rem.shape, 1.0, dtype=np.float32)
    normalized[valid] = np.clip((rem[valid] - vmin) / (vmax - vmin), 0, 1)

    # 低于河面的像素（负REM）设为 0（最暗），河道本身也极暗
    below_river = valid & (rem < 0)
    normalized[below_river] = 0.0

    # 高于 vmax 的设为 1.0（纯黑）
    above_max = valid & (rem > vmax)
    normalized[above_max] = 1.0

    lut = build_colormap(cmap_name)  # Nx4
    idx = (normalized * (lut.shape[0] - 1)).astype(np.int32)
    idx = np.clip(idx, 0, lut.shape[0] - 1)
    rgba = lut[idx]

    background = str(preset.get("background", "black")).lower()

    # 山体阴影
    if dem_path and os.path.exists(dem_path):
        print("[SHADE] 生成山体阴影叠加...")
        hs = generate_hillshade(dem_path, mask=valid)
    else:
        hs = np.ones(rem.shape, dtype=np.float32) * 0.5

    # 柔光混合：soft-light 更接近 samplecases 的暗部塑形
    shade_strength = float(preset.get("shade_strength", 0.35))
    if shade_strength > 0:
        hs_3ch = np.dstack([hs, hs, hs]).astype(np.float32)
        base = rgba[:, :, :3].astype(np.float32)
        shaded = _soft_light(base, hs_3ch)
        rgba[:, :, :3] = np.clip((1 - shade_strength) * base + shade_strength * shaded, 0, 1)
    rgba = np.clip(rgba, 0, 1)

    # 无效区域：按背景色填充
    if background == "white":
        rgba[~valid] = [1, 1, 1, 1]
    else:
        rgba[~valid] = [0, 0, 0, 1]

    rgb01 = rgba[:, :, :3].astype(np.float32)

    # 白底：用 alpha 将颜色“洗”到纸白（更接近 samplecases 的水彩感）
    if background == "white":
        alpha_power = float(preset.get("alpha_power", 1.25))
        alpha = np.clip(1.0 - normalized, 0.0, 1.0)
        alpha = np.power(alpha, alpha_power).astype(np.float32)
        alpha[~valid] = 0.0
        paper = np.ones_like(rgb01, dtype=np.float32)
        rgb01 = paper * (1.0 - alpha[:, :, None]) + rgb01 * alpha[:, :, None]

    core_width_m = float(preset.get("core_width_m", 0.6))
    core_strength = float(preset.get("core_strength", 0.0))
    bloom_enabled = bool(preset.get("bloom_enabled", False))
    bloom_strength = float(preset.get("bloom_strength", 0.0))
    bloom_sigmas_px = tuple(preset.get("bloom_sigmas_px", (2.0, 6.0, 14.0)))
    bloom_weights = tuple(preset.get("bloom_weights", (0.55, 0.30, 0.15)))

    if core_strength > 0 or (bloom_enabled and bloom_strength > 0):
        glow_mask = valid & (rem >= 0)
        glow = np.zeros(rem.shape, dtype=np.float32)
        if glow_mask.any():
            scale = max(core_width_m, 1e-3)
            glow_vals = np.exp(-np.clip(rem[glow_mask].astype(np.float32), 0, None) / scale)
            glow[glow_mask] = glow_vals

        if core_strength > 0:
            core = np.clip(glow ** 1.35, 0, 1)
            core_rgb = np.dstack([core, core, core])
            rgb01 = np.clip(rgb01 + (0.55 * core_strength) * core_rgb, 0, 1)

        if bloom_enabled and bloom_strength > 0:
            rgb01 = _apply_bloom(
                rgb01,
                glow01=glow,
                sigmas_px=bloom_sigmas_px,
                weights=bloom_weights,
                strength=bloom_strength,
            )

    # 主干道增强：用参考中心线加粗后叠加（让 mainstem 更明显）
    if bool(preset.get("mainstem_enabled", False)):
        ref = os.path.join(DATA_DIR, "river_line_reference_utm.geojson")
        ms_width_m = float(preset.get("mainstem_width_m", 2000.0))
        ms_alpha = float(preset.get("mainstem_alpha", 0.85))
        ms_glow_strength = float(preset.get("mainstem_glow_strength", 0.25))
        ms_color = _hex_to_rgb01(str(preset.get("mainstem_color", "#003b6f")))
        ms_mask = _rasterize_mainstem_mask(
            reference_geojson_utm=ref,
            out_shape=rem.shape,
            out_transform=transform,
            out_crs=crs,
            width_m=ms_width_m,
        )
        if ms_mask is not None and ms_mask.any():
            overlay = np.broadcast_to(ms_color[None, None, :], rgb01.shape)
            rgb01 = np.clip(rgb01 * (1.0 - ms_alpha * ms_mask[:, :, None]) + overlay * (ms_alpha * ms_mask[:, :, None]), 0, 1)
            if ms_glow_strength > 0:
                rgb01 = _apply_bloom(
                    rgb01,
                    glow01=ms_mask.astype(np.float32),
                    sigmas_px=(2.0, 7.0, 16.0),
                    weights=(0.60, 0.28, 0.12),
                    strength=ms_glow_strength,
                )

    # 支流/毛细血管线条：从 OSM 候选线段生成更细的线网叠加
    if bool(preset.get("streams_enabled", False)):
        streams_width_m = float(preset.get("streams_width_m", 320.0))
        streams_alpha = float(preset.get("streams_alpha", 0.18))
        streams_glow_strength = float(preset.get("streams_glow_strength", 0.08))
        streams_color = _hex_to_rgb01(str(preset.get("streams_color", "#2aa36b")))

        candidates = os.path.join(DATA_DIR, "river_candidates_wgs84.geojson")
        streams_mask = _rasterize_buffered_lines(
            reference_geojson=candidates,
            out_shape=rem.shape,
            out_transform=transform,
            out_crs=crs,
            width_m=streams_width_m,
        )
        if streams_mask is not None and streams_mask.any():
            overlay = np.broadcast_to(streams_color[None, None, :], rgb01.shape)
            a = streams_alpha * streams_mask[:, :, None]
            rgb01 = np.clip(rgb01 * (1.0 - a) + overlay * a, 0, 1)
            if streams_glow_strength > 0:
                rgb01 = _apply_bloom(
                    rgb01,
                    glow01=streams_mask.astype(np.float32),
                    sigmas_px=(1.5, 5.0, 12.0),
                    weights=(0.62, 0.26, 0.12),
                    strength=streams_glow_strength,
                )

    rgb = (rgb01 * 255).astype(np.uint8)

    print("[POST] 后处理: 平滑河流纹理 + 伽马校正 + 暗角...")
    rgb = smooth_river(rgb, valid, radius=0.4)
    tone_gamma = float(preset.get("tone_gamma", 1.15))
    rgb = gamma_correct(rgb, gamma=tone_gamma)
    vignette_strength = float(preset.get("vignette_strength", 0.28))
    rgb = add_vignette(rgb, strength=vignette_strength)
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

    if write_colorbar:
        # 生成图例（可选，避免某些环境下 matplotlib/fontconfig 崩溃）
        import matplotlib.pyplot as plt
        from matplotlib.cm import ScalarMappable
        from matplotlib.colors import LinearSegmentedColormap

        # reconstruct a matplotlib colormap just for the colorbar
        stops = COLOR_SCHEMES.get(cmap_name, COLOR_SCHEMES["electric_blue"])
        cmap = LinearSegmentedColormap.from_list(cmap_name, [(p, c) for p, c in stops], N=1024)

        fig, ax = plt.subplots(figsize=(4, 0.35))
        sm = ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=vmin, vmax=vmax))
        sm.set_array([])
        cbar = plt.colorbar(sm, cax=ax, orientation="horizontal")
        cbar.set_label("Height above river (m)", color="white", fontsize=9)
        cbar.ax.tick_params(colors="white", labelsize=8)
        fig.patch.set_facecolor("black")
        ax.set_facecolor("black")
        leg = os.path.join(OUTPUT_DIR, f"colorbar_{cmap_name}.png")
        plt.savefig(leg, dpi=150, bbox_inches="tight", facecolor="black", edgecolor="none")
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
    ap.add_argument("--preset", type=str, default=STYLE_PRESET,
                    choices=sorted(STYLE_PRESETS.keys()),
                    help="渲染风格预设")
    ap.add_argument("--no-shade", action='store_true', help="不叠加山体阴影")
    ap.add_argument("--colorbar", action="store_true", help="额外输出色带图例 PNG（需要 matplotlib）")
    args = ap.parse_args()
    dem = None if args.no_shade else DEM_PROJ
    visualize(
        REM_TIF,
        args.cmap,
        VIZ_PNG,
        VIZ_TIF,
        dem_path=dem,
        preset_name=args.preset,
        write_colorbar=bool(args.colorbar),
    )


if __name__ == "__main__":
    main()
