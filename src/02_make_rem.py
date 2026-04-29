#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02_make_rem.py
================
全自动生成荆江段 Relative Elevation Model (REM)。

核心逻辑:
- 从 OpenStreetMap (OSM) 自动下载长江 (荆江段) 的河流中心线。
- 沿中心线等间距采样高程点 (从 DEM 读取真实高程)。
- 使用 scipy.spatial.cKDTree + IDW (反距离权重) 插值出全图每个像素对应的"河面高程"。
- REM = DEM 原始高程 − 河面高程。(河面=0, 两岸>0)
- 仅保留河流两侧 REM_BUFFER_M 范围内的像素，其余设为 NoData。
- 输出为 GeoTIFF，可直接用于下一步可视化。

运行:
    python 02_make_rem.py

依赖:
    osmnx, geopandas, shapely, rasterio, numpy, scipy, pyproj, tqdm
"""

import os
import sys
import warnings
import numpy as np
from tqdm import tqdm
import rasterio
from rasterio.transform import xy
from shapely.geometry import box, LineString, MultiLineString, Point
from shapely.ops import linemerge
import geopandas as gpd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import *

warnings.filterwarnings('ignore', category=FutureWarning)


def _get_river_from_osm(bbox_wgs84):
    """
    从 OSM 下载河流数据并返回 GeoDataFrame (EPSG:4326)。
    优先筛选 'name' 包含 '长江' / 'Yangtze' 的主河道。
    """
    try:
        import osmnx as ox
    except ImportError:
        print("[ERROR] 缺少 `osmnx` 库，无法自动获取河流数据。")
        print("        请执行: pip install osmnx")
        sys.exit(1)

    ox.settings.log_console = False
    ox.settings.use_cache = True

    w, s, e, n = bbox_wgs84
    print(f"[OSM] 正在查询 OpenStreetMap (范围: {w:.2f},{s:.2f} ~ {e:.2f},{n:.2f})...")
    print("      标签: waterway=river, 筛选主河道...")

    polygon = box(w, s, e, n)

    # 兼容不同版本 osmnx API
    try:
        gdf = ox.features.features_from_polygon(polygon, tags={"waterway": "river"})
    except AttributeError:
        try:
            gdf = ox.geometries_from_polygon(polygon, tags={"waterway": "river"})
        except AttributeError:
            print("[ERROR] osmnx API 版本不兼容，请确保 osmnx >= 1.6")
            sys.exit(1)

    if gdf is None or gdf.empty:
        print("[ERROR] OSM 在该范围内未返回任何河流数据。")
        print("        可能的原因:")
        print("          1. 区域过于偏远，OSM 数据缺失")
        print("          2. 网络连接问题 (国内访问 api.openstreetmap.org 可能被墙)")
        print("        建议:")
        print("          - 开启全局代理后重试")
        print("          - 或改用方案 B: 在 QGIS 中手动绘制河流中心线并导出为 river_line.geojson")
        sys.exit(1)

    # 筛选主河道: 名字包含 长江 / Yangtze / 扬子江
    if 'name' in gdf.columns:
        name_series = gdf['name'].astype(str).fillna('')
        mask_main = name_series.str.contains('长江', case=False) | \
                    name_series.str.contains('Yangtze', case=False) | \
                    name_series.str.contains('扬子江', case=False)
    else:
        mask_main = gdf.index.get_level_values(0).astype(str).str.contains('way', case=False)

    if mask_main.any():
        river_gdf = gdf[mask_main].copy()
        print(f"[OK] 成功筛选到 {len(river_gdf)} 条主河道段(含长江)。")
    else:
        #  Fallback: 取长度最长的线要素作为主河道
        print("[WARN] 未找到明确标记为'长江'的河道，将自动选择最长的河流线。")
        line_gdf = gdf[gdf.geom_type.isin(['LineString', 'MultiLineString'])].copy()
        if line_gdf.empty:
            print("[ERROR] OSM 数据中没有 LineString 类型的河流要素。")
            sys.exit(1)
        line_gdf['length'] = line_gdf.to_crs(UTM_CRS).geometry.length
        longest_idx = line_gdf['length'].idxmax()
        river_gdf = line_gdf.loc[[longest_idx]].copy()

    # 统一转为 LineString / MultiLineString，过滤掉多边形
    river_gdf = river_gdf[river_gdf.geom_type.isin(['LineString', 'MultiLineString'])]
    return river_gdf[['geometry']]


def _merge_and_project_river(river_gdf_4326):
    """
    合并所有河道段，投影到 UTM，并返回一条顺滑的主河道 LineString。
    """
    print("[PROC] 合并河道段并投影到 UTM...")
    merged = linemerge(river_gdf_4326.geometry.tolist())

    # 如果合并后是 MultiLineString，取最长的一段作为主河道
    if merged.geom_type == 'MultiLineString':
        parts = sorted(merged.geoms, key=lambda g: g.length, reverse=True)
        # 如果有多段，尝试把它们连起来 (可能断开很远，这里只取最长的一段以保证连续性)
        main_line = parts[0]
        print(f"       注意: OSM 河道存在 {len(parts)} 段断裂，已选取最长段作为基准。")
    else:
        main_line = merged

    # 转为 GeoDataFrame 并投影到 UTM (米)
    gdf_utm = gpd.GeoDataFrame(geometry=[main_line], crs="EPSG:4326")
    gdf_utm = gdf_utm.to_crs(UTM_CRS)
    line_utm = gdf_utm.geometry.iloc[0]

    # 简化节点，消除 OSM 原始数据的微小抖动 (Douglas-Peucker, 10m 容差)
    line_utm = line_utm.simplify(10.0, preserve_topology=True)
    print(f"[OK]   主河道投影后长度: {line_utm.length / 1000:.1f} km")
    return line_utm


def _sample_river_elevations(line_utm, dem_path):
    """
    沿主河道线每隔 spacing 米采样一个点，并从 DEM 读取高程。
    返回 Nx3 ndarray: x, y, z (UTM 坐标，米)
    """
    spacing = RIVER_SAMPLE_SPACING
    length = line_utm.length
    distances = np.arange(0, length, spacing)
    print(f"[DEM] 沿河道采样 {len(distances)} 个点 (间距 {spacing}m)...")

    pts = np.array([[line_utm.interpolate(d).x, line_utm.interpolate(d).y] for d in distances])

    # 使用 rasterio.sample 批量读取高程
    coords = [(float(x), float(y)) for x, y in pts]
    with rasterio.open(dem_path) as src:
        nodata = src.nodata if src.nodata is not None else -32768
        zs = []
        for val in src.sample(coords):
            z = val[0]
            if z is None or np.isnan(z) or z == nodata:
                z = np.nan
            zs.append(z)

    zs = np.array(zs)

    # 剔除 NaN (边界外或 DEM 空洞)
    valid = ~np.isnan(zs)
    if valid.sum() < 10:
        print("[ERROR] 从 DEM 采样的有效高程点太少，请检查 DEM 覆盖范围是否与河流重叠。")
        sys.exit(1)

    pts = pts[valid]
    zs = zs[valid]

    print(f"[OK]   有效采样点: {len(zs)} / {len(distances)} (去除了 NoData)")
    print(f"       河道高程范围: {zs.min():.1f} m ~ {zs.max():.1f} m")
    return np.column_stack([pts[:, 0], pts[:, 1], zs])


def _idw_interpolate(river_pts, dem_path, output_path):
    """
    使用 scipy.cKDTree 对整个 DEM 做分块 IDW 插值，并生成 REM。
    river_pts: N x 3 ndarray (x, y, z)
    """
    K = IDW_K_NEIGHBORS
    power = IDW_POWER
    buffer_m = REM_BUFFER_M
    block_hint = IDW_BLOCK_SIZE

    coords_xy = river_pts[:, :2]
    coords_z = river_pts[:, 2]

    print(f"[REM] 构建 KDTree ({len(coords_xy)} 个河道点)...")
    from scipy.spatial import cKDTree
    tree = cKDTree(coords_xy)

    with rasterio.open(dem_path) as src:
        profile = src.profile.copy()
        nodata_val = -9999.0
        profile.update(
            dtype='float32',
            nodata=nodata_val,
            count=1,
            compress='deflate',
            tiled=True,
            blockxsize=256,
            blockysize=256
        )

        height, width = src.height, src.width
        print(f"[REM] DEM 尺寸: {width} x {height} 像素")
        print(f"      分块大小: ~{block_hint}x{block_hint} (内存自适应)")
        print(f"      IDW 参数: K={K}, power={power}, 有效范围={buffer_m}m")

        total_pixels = width * height
        with rasterio.open(output_path, 'w', **profile) as dst:
            # 手动分块: 计算 tile 行列
            n_rows = int(np.ceil(height / block_hint))
            n_cols = int(np.ceil(width / block_hint))
            total_blocks = n_rows * n_cols

            processed = 0
            # 使用 tqdm 进度条
            with tqdm(total=total_blocks, desc="[REM] 分块处理") as pbar:
                for row_idx in range(n_rows):
                    row_off = row_idx * block_hint
                    h = min(block_hint, height - row_off)
                    for col_idx in range(n_cols):
                        col_off = col_idx * block_hint
                        w = min(block_hint, width - col_off)
                        window = rasterio.windows.Window(col_off, row_off, w, h)

                        # 读取 DEM 块
                        dem_block = src.read(1, window=window)

                        # 构造块内所有像素中心坐标
                        rows = np.arange(row_off, row_off + h)
                        cols = np.arange(col_off, col_off + w)
                        rr, cc = np.meshgrid(rows, cols, indexing='ij')
                        xs, ys = xy(src.transform, rr, cc)
                        xs = np.array(xs)
                        ys = np.array(ys)
                        pixel_coords = np.column_stack([xs.ravel(), ys.ravel()])

                        # DEM 有效掩膜
                        src_nodata = src.nodata if src.nodata is not None else -9999
                        valid = (dem_block != src_nodata) & (~np.isnan(dem_block))
                        valid_flat = valid.ravel()

                        rem_flat = np.full(dem_block.size, nodata_val, dtype=np.float32)

                        if valid_flat.any():
                            valid_px = pixel_coords[valid_flat]

                            # KDTree query K 近邻
                            distances, idx = tree.query(valid_px, k=min(K, len(coords_xy)))

                            if distances.ndim == 1:
                                distances = distances[:, np.newaxis]
                                idx = idx[:, np.newaxis]

                            # IDW 权重计算
                            zero_mask = distances < 1e-6
                            has_zero = zero_mask.any(axis=1)

                            # 普通点 (无零距离)
                            weights = 1.0 / (distances ** power + 1e-12)
                            z_neighbors = coords_z[idx]
                            z_interp = np.sum(weights * z_neighbors, axis=1) / np.sum(weights, axis=1)

                            # 零距离点: 直接取该点高程
                            if has_zero.any():
                                zero_idx = np.where(has_zero)[0]
                                for i in zero_idx:
                                    z_interp[i] = coords_z[idx[i, 0]]

                            # 距离掩膜: 最近采样点距离超过 buffer_m 则设为 NoData
                            min_dist = distances[:, 0]
                            out_of_range = min_dist > buffer_m
                            z_interp[out_of_range] = np.nan

                            # REM = DEM - 河面高程
                            rem_valid = dem_block.ravel()[valid_flat].astype(np.float32) - z_interp

                            # NaN (距离太远) 设为 NoData
                            nan_mask = np.isnan(rem_valid)
                            rem_valid[nan_mask] = nodata_val

                            rem_flat[valid_flat] = rem_valid

                        rem_block = rem_flat.reshape(dem_block.shape)
                        dst.write(rem_block, 1, window=window)
                        pbar.update(1)

    print(f"[OK]   REM 生成完成 -> {output_path}")


def _save_river_geojson_for_reference(line_utm):
    """将主河道线保存为参考 GeoJSON (可选)。"""
    ref_path = os.path.join(DATA_DIR, "river_line_reference.geojson")
    gdf = gpd.GeoDataFrame(geometry=[line_utm], crs=UTM_CRS)
    gdf.to_file(ref_path, driver='GeoJSON')
    print(f"[INFO] 参考河道线已保存: {ref_path}")


def main():
    print("=" * 70)
    print("步骤 2/3: 生成 Relative Elevation Model (REM)")
    print("=" * 70)

    if not os.path.exists(DEM_PROJ):
        print(f"[ERROR] 未找到 DEM 数据: {DEM_PROJ}")
        print("        请先运行: python 01_download_dem.py")
        sys.exit(1)

    if os.path.exists(REM_TIF):
        print(f"[INFO] REM 文件已存在: {REM_TIF}")
        print("       如需重新生成，请删除该文件再运行。")
        return

    bbox = get_bbox()

    # 1. OSM 获取河流
    river_gdf_4326 = _get_river_from_osm(bbox)

    # 2. 合并并投影
    line_utm = _merge_and_project_river(river_gdf_4326)

    # 3. 保存参考
    _save_river_geojson_for_reference(line_utm)

    # 4. 采样高程
    river_pts = _sample_river_elevations(line_utm, DEM_PROJ)

    # 5. IDW 插值 -> REM
    _idw_interpolate(river_pts, DEM_PROJ, REM_TIF)

    print("\n[COMPLETE] REM 生成完成!")
    print(f"          输出: {REM_TIF}")
    print("          下一步: python 03_visualize_dancoe.py")


if __name__ == "__main__":
    main()
