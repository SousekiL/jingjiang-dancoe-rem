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
import re
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

DEFAULT_RIVER_NAME_REGEX = r"(长江|Yangtze|扬子江)"


def _extract_name_series(gdf):
    """尽可能从 OSM 属性里提取名称列，用于正则匹配。"""
    for col in ("name", "name:en", "alt_name", "official_name", "short_name"):
        if col in gdf.columns:
            return gdf[col].astype(str).fillna("")
    return gdf.index.to_series().astype(str).fillna("")


def _lines_only_gdf(gdf):
    gdf = gdf.reset_index(drop=False).copy()
    gdf = gdf[gdf.geometry.notna()].copy()
    gdf = gdf[gdf.geom_type.isin(["LineString", "MultiLineString"])].copy()
    return gdf


def _seed_point_wgs84(bbox_wgs84, seed_lon_lat):
    if seed_lon_lat is not None:
        lon, lat = seed_lon_lat
        return Point(float(lon), float(lat))
    w, s, e, n = bbox_wgs84
    return Point((w + e) / 2.0, (s + n) / 2.0)


def _build_connectivity(geoms_utm, connect_tol_m):
    """
    在 UTM 平面上用端点距离判断线段连通性，返回邻接表。
    """
    endpoints = []
    for i, geom in enumerate(geoms_utm):
        if geom is None or geom.is_empty:
            endpoints.append((i, None, None))
            continue
        if geom.geom_type == "MultiLineString":
            parts = list(geom.geoms)
            parts.sort(key=lambda g: g.length, reverse=True)
            g = parts[0]
        else:
            g = geom
        coords = list(g.coords)
        endpoints.append((i, Point(coords[0]), Point(coords[-1])))

    adj = {i: set() for i in range(len(geoms_utm))}
    for i, a0, a1 in endpoints:
        if a0 is None:
            continue
        for j, b0, b1 in endpoints[i + 1 :]:
            if b0 is None:
                continue
            if (
                a0.distance(b0) <= connect_tol_m
                or a0.distance(b1) <= connect_tol_m
                or a1.distance(b0) <= connect_tol_m
                or a1.distance(b1) <= connect_tol_m
            ):
                adj[i].add(j)
                adj[j].add(i)
    return adj


def _select_main_river_segments(gdf_4326, bbox_wgs84, river_name_regex, seed_lon_lat, connect_tol_m):
    """
    从 bbox 范围内的 OSM 河流线段中选择“主河道”：
    1) 名称正则优先作为种子
    2) 否则使用 bbox 中心点 (或 --seed) 就近锁定
    3) 通过端点连通性扩展，聚合断裂线段
    返回: (selected_gdf_4326, candidates_gdf_4326, seed_point_4326)
    """
    candidates = _lines_only_gdf(gdf_4326)
    if candidates.empty:
        print("[ERROR] OSM 数据中没有 LineString 类型的河流要素。")
        sys.exit(1)

    seed_pt_4326 = _seed_point_wgs84(bbox_wgs84, seed_lon_lat)
    name_series = _extract_name_series(candidates)
    name_mask = name_series.str.contains(river_name_regex, flags=re.IGNORECASE, regex=True, na=False)

    candidates_utm = candidates.to_crs(UTM_CRS)
    seed_pt_utm = gpd.GeoDataFrame(geometry=[seed_pt_4326], crs="EPSG:4326").to_crs(UTM_CRS).geometry.iloc[0]

    if bool(name_mask.any()):
        start_indices = list(np.where(name_mask.to_numpy())[0])
        print(f"[OK] 名称正则命中 {len(start_indices)} 条河道段，将以此为主河道种子。")
    else:
        dists = candidates_utm.geometry.distance(seed_pt_utm)
        nearest_pos = int(np.argmin(dists.to_numpy()))
        start_indices = [nearest_pos]
        print("[WARN] 未命中河流名称正则，将使用 bbox 中心点就近锁定主河道。")

    adj = _build_connectivity(list(candidates_utm.geometry), connect_tol_m=float(connect_tol_m))

    selected = set()
    queue = list(start_indices)
    while queue:
        i = queue.pop()
        if i in selected:
            continue
        selected.add(i)
        for j in adj.get(i, ()):
            if j not in selected:
                queue.append(j)

    selected_gdf = candidates.iloc[sorted(selected)].copy()

    # 名称命中但集合太小，尝试用“就近连通集合”兜底
    if bool(name_mask.any()) and len(selected_gdf) < 3:
        dists = candidates_utm.geometry.distance(seed_pt_utm)
        nearest_pos = int(np.argmin(dists.to_numpy()))
        selected2 = set()
        queue = [nearest_pos]
        while queue:
            i = queue.pop()
            if i in selected2:
                continue
            selected2.add(i)
            for j in adj.get(i, ()):
                if j not in selected2:
                    queue.append(j)
        gdf2 = candidates.iloc[sorted(selected2)].copy()
        if len(gdf2) > len(selected_gdf):
            selected_gdf = gdf2
            print("[INFO] 名称命中集合过小，已改用就近连通集合。")

    return selected_gdf[["geometry"]], candidates[["geometry"]], seed_pt_4326


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
    print("      标签: waterway=river, 拉取河流线段...")

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

    return gdf


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


def _save_river_geojson_for_reference(line_utm, seed_pt_4326=None, export_debug=False, candidates_4326=None):
    """将主河道线保存为参考 GeoJSON（可选输出候选线段用于调试）。"""
    ref_utm = os.path.join(DATA_DIR, "river_line_reference_utm.geojson")
    gdf_utm = gpd.GeoDataFrame(geometry=[line_utm], crs=UTM_CRS)
    gdf_utm.to_file(ref_utm, driver="GeoJSON")
    print(f"[INFO] 参考河道线已保存: {ref_utm}")

    ref_wgs84 = os.path.join(DATA_DIR, "river_line_reference_wgs84.geojson")
    gdf_wgs84 = gdf_utm.to_crs("EPSG:4326")
    gdf_wgs84.to_file(ref_wgs84, driver="GeoJSON")
    print(f"[INFO] 参考河道线已保存: {ref_wgs84}")

    if export_debug and seed_pt_4326 is not None:
        seed_path = os.path.join(DATA_DIR, "river_seed_point_wgs84.geojson")
        gpd.GeoDataFrame(geometry=[seed_pt_4326], crs="EPSG:4326").to_file(seed_path, driver="GeoJSON")
        print(f"[INFO] 种子点已保存: {seed_path}")

    if export_debug and candidates_4326 is not None and not candidates_4326.empty:
        cand_path = os.path.join(DATA_DIR, "river_candidates_wgs84.geojson")
        candidates_4326.to_file(cand_path, driver="GeoJSON")
        print(f"[INFO] 候选河道段已保存: {cand_path}")


def _save_selected_segments(selected_4326, export_debug=False):
    if not export_debug or selected_4326 is None or selected_4326.empty:
        return
    main_wgs84 = os.path.join(DATA_DIR, "river_mainstem_segments_wgs84.geojson")
    selected_4326.to_file(main_wgs84, driver="GeoJSON")
    print(f"[INFO] 主河道线段已保存: {main_wgs84}")

    main_utm = os.path.join(DATA_DIR, "river_mainstem_segments_utm.geojson")
    selected_4326.to_crs(UTM_CRS).to_file(main_utm, driver="GeoJSON")
    print(f"[INFO] 主河道线段已保存: {main_utm}")


def main():
    print("=" * 70)
    print("步骤 2/3: 生成 Relative Elevation Model (REM)")
    print("=" * 70)

    import argparse
    ap = argparse.ArgumentParser(description="生成 Relative Elevation Model (REM)")
    ap.add_argument("--seed", nargs=2, type=float, metavar=("LON", "LAT"),
                    help="种子点经纬度，用于锁定主河道（默认 bbox 中心点）")
    ap.add_argument("--river-name-regex", type=str, default=DEFAULT_RIVER_NAME_REGEX,
                    help=f"主河道名称正则（默认: {DEFAULT_RIVER_NAME_REGEX}）")
    ap.add_argument("--connect-tol-m", type=float, default=600.0,
                    help="河道段端点连通阈值（米），用于聚合断裂线段")
    ap.add_argument("--export-debug", action="store_true",
                    help="导出候选河道/种子点等调试 GeoJSON")
    ap.add_argument("--force", action="store_true",
                    help="即使 REM 已存在也强制重算")
    args = ap.parse_args()

    if not os.path.exists(DEM_PROJ):
        print(f"[ERROR] 未找到 DEM 数据: {DEM_PROJ}")
        print("        请先运行: python 01_download_dem.py")
        sys.exit(1)

    if os.path.exists(REM_TIF) and not args.force:
        print(f"[INFO] REM 文件已存在: {REM_TIF}")
        print("       如需重新生成，请添加参数 --force 或删除该文件再运行。")
        return

    bbox = get_bbox()

    # 1. OSM 获取河流
    osm_gdf_4326 = _get_river_from_osm(bbox)
    selected_river_4326, candidates_4326, seed_pt_4326 = _select_main_river_segments(
        osm_gdf_4326,
        bbox_wgs84=bbox,
        river_name_regex=args.river_name_regex,
        seed_lon_lat=args.seed,
        connect_tol_m=float(args.connect_tol_m),
    )
    print(f"[OK] 选中主河道段数量: {len(selected_river_4326)}")

    # 2. 合并并投影
    line_utm = _merge_and_project_river(selected_river_4326)

    # 3. 保存参考
    _save_river_geojson_for_reference(
        line_utm,
        seed_pt_4326=seed_pt_4326,
        export_debug=bool(args.export_debug),
        candidates_4326=candidates_4326 if args.export_debug else None,
    )
    _save_selected_segments(selected_river_4326, export_debug=bool(args.export_debug))

    # 4. 采样高程
    river_pts = _sample_river_elevations(line_utm, DEM_PROJ)

    # 5. IDW 插值 -> REM
    _idw_interpolate(river_pts, DEM_PROJ, REM_TIF)

    print("\n[COMPLETE] REM 生成完成!")
    print(f"          输出: {REM_TIF}")
    print("          下一步: python 03_visualize_dancoe.py")


if __name__ == "__main__":
    main()
