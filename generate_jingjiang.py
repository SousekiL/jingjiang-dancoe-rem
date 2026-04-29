#!/usr/bin/env python3
"""
generate_jingjiang.py — 荆江 Dan Coe 风格完整生成
====================================================
核心：gdal_grid IDW + 极端高对比 colormap
"""
import os, sys, json, numpy as np, warnings
from PIL import Image
import rasterio
from shapely.geometry import box
from shapely.ops import linemerge, unary_union
import geopandas as gpd

warnings.filterwarnings('ignore')

BASE   = os.path.dirname(os.path.abspath(__file__))
DEM    = os.path.join(BASE, "data/dem_proj.tif")
REM    = os.path.join(BASE, "output/rem_gdal.tif")
R_SURF = os.path.join(BASE, "output/river_surface.tif")
HS     = os.path.join(BASE, "output/hillshade.tif")
PTS    = os.path.join(BASE, "output/river_pts.shp")
PNG    = os.path.join(BASE, "output/jingjiang_blue.png")
TIF    = os.path.join(BASE, "output/jingjiang_blue.tif")

os.makedirs(os.path.join(BASE, "output"), exist_ok=True)

# ═══════════════════════════════════════════════════════
#  Step 1: OSM → 完整长江中心线
# ═══════════════════════════════════════════════════════
print("=" * 60)
print("Step 1: OSM 获取长江中心线")
print("=" * 60)

from osgeo import ogr, osr, gdal
import osmnx as ox
ox.settings.log_console = False
ox.settings.use_cache = True

bbox = box(111.0, 29.0, 113.5, 30.5)
print("  查询 Overpass...")
gdf = ox.features.features_from_polygon(bbox, tags={"waterway": "river"})

nm = gdf['name'].astype(str)
yz = gdf[nm.str.contains('长江|Yangtze|扬子江', case=False, na=False)].copy()
lines = yz[yz.geom_type.isin(['LineString', 'MultiLineString'])].copy()
print(f"  长江段: {len(lines)} 条")

# 合并 → 投影 → 简化
utm = lines.to_crs("EPSG:32649")
merged = linemerge(utm.geometry.tolist())
if merged.geom_type == "MultiLineString":
    parts = sorted(merged.geoms, key=lambda g: g.length, reverse=True)
    merged = parts[0]
merged = merged.simplify(10, preserve_topology=True)
print(f"  主河道: {merged.length/1000:.1f} km")

# ═══════════════════════════════════════════════════════
#  Step 2: 密集采样 → gdal_grid IDW → REM
# ═══════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 2: 采样 + IDW + REM")
print("=" * 60)

# 删除旧文件
for f in [REM, R_SURF, HS]:
    try: os.unlink(f)
    except: pass

# 每 30m 一点
sp = 30
dist = np.arange(0, merged.length, sp)
pts = [(merged.interpolate(d).x, merged.interpolate(d).y) for d in dist]
print(f"  采样 {len(pts)} 个点")

# 从 DEM 读高程
with rasterio.open(DEM) as s:
    nd = s.nodata if s.nodata is not None else 32767
    zz = [v[0] for v in s.sample(pts)]
    zz = [z if z is not None and not np.isnan(z) and z != nd else np.nan for z in zz]
zz = np.array(zz)
valid = ~np.isnan(zz)
pts = np.array(pts)[valid]
zz = zz[valid]
print(f"  有效: {len(zz)} 点, 高程 {zz.min():.0f} ~ {zz.max():.0f}m")

# 写 shapefile
ds = ogr.GetDriverByName("ESRI Shapefile").CreateDataSource(PTS)
sr = osr.SpatialReference()
sr.ImportFromEPSG(32649)
lyr = ds.CreateLayer("pts", sr, ogr.wkbPoint)
lyr.CreateField(ogr.FieldDefn("elev", ogr.OFTReal))
for i in range(len(zz)):
    f = ogr.Feature(lyr.GetLayerDefn())
    f.SetGeometry(ogr.CreateGeometryFromWkt(f"POINT({pts[i,0]} {pts[i,1]})"))
    f.SetField("elev", float(zz[i]))
    lyr.CreateFeature(f)
ds = lyr = None

# gdal_grid IDW
with rasterio.open(DEM) as s:
    b = s.bounds
    W, H = s.width, s.height

print(f"  gdal_grid IDW (尺寸 {W}x{H})...")
ret = os.system(f"""
    gdal_grid -outsize {W} {H} 
    -a invdist:power=2:smoothing=0:radius1=3000:radius2=8000:max_points=20:nodata=-9999 
    -txe {b.left} {b.right} -tye {b.bottom} {b.top} 
    -zfield elev -of GTiff -ot Float32 -l pts 
    {PTS} {R_SURF}
""".replace('\n', ' '))
if ret != 0:
    print("  ERROR: gdal_grid 失败")
    sys.exit(1)

# gdal_calc: REM = DEM - river surface
os.system(f"""
    gdalwarp -overwrite -dstnodata -9999 -ot Float32 -of GTiff {DEM} /tmp/dem_nodata.tif
""")
os.system(f"""
    gdal_calc.py -A /tmp/dem_nodata.tif -B {R_SURF} 
    --calc="A-B" --outfile={REM} --NoDataValue=-9999 
    --type=Float32 --format=GTiff --co=COMPRESS=DEFLATE --overwrite
""")

# Hillshade
gdal.DEMProcessing(HS, DEM, "hillshade",
                   azimuth=315, altitude=30, zFactor=4,
                   computeEdges=True)

# ═══════════════════════════════════════════════════════
#  Step 3: Dan Coe 渲染
# ═══════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 3: Dan Coe 风格渲染")
print("=" * 60)

VIZ_MAX = 4.0

with rasterio.open(REM) as s:
    arr = s.read(1)
    prof = s.profile
    crs = s.crs
    tf  = s.transform
    nda = s.nodata if s.nodata is not None else -9999

with rasterio.open(HS) as s:
    hs = s.read(1).astype(np.float32)

valid = (arr != nda) & (~np.isnan(arr)) & (~np.isinf(arr))
print(f"  REM: {valid.sum():,} / {arr.size:,} ({valid.sum()/arr.size*100:.1f}%)")

d = arr[valid]
print(f"  REM 范围: {d.min():.1f} ~ {d.max():.1f} m, 中位数 {np.median(d):.1f}m")

# 归一化 hillshade
h_min = hs[valid].min() if valid.any() else 0
h_max = hs[valid].max() if valid.any() else 255
hs = np.where(h_max > h_min, (hs - h_min) / (h_max - h_min), 0.5).astype(np.float32)
hs[~valid] = 0.5

# 构建极端高对比 colormap
from matplotlib.colors import LinearSegmentedColormap
cmap = LinearSegmentedColormap.from_list("dc", [
    (0.00,  "#ffffff"),
    (0.008, "#e0f8ff"),
    (0.025, "#00e0ff"),
    (0.06,  "#0088cc"),
    (0.12,  "#004477"),
    (0.22,  "#001133"),
    (0.38,  "#000411"),
    (0.60,  "#000000"),
    (1.00,  "#000000"),
], N=1024)

# 归一化 REM
norm = np.full(arr.shape, 1.0, np.float32)
norm[valid] = np.clip(arr[valid] / VIZ_MAX, 0, 1)
norm[valid & (arr < 0)] = 0.0

# 应用 cmap
rgba = cmap(norm)

# 混合 hillshade (15% blend for subtle texture)
hs3 = np.dstack([hs, hs, hs])
rgba[:,:,:3] *= (0.85 + 0.15 * hs3)
rgba = np.clip(rgba, 0, 1)

# 无效区域纯黑
rgba[~valid] = [0,0,0,1]

rgb = (rgba[:,:,:3] * 255).astype(np.uint8)

# 后处理: 锐化 + 暗角
from scipy.ndimage import laplace
lap = laplace(rgb.astype(np.float32))
bright = rgb.max(axis=2) > 25
lap_msk = np.where(bright[:,:,np.newaxis], lap, 0)
rgb = np.clip(rgb.astype(np.float32) - 0.5 * lap_msk, 0, 255)

# 暗角
H, W = rgb.shape[:2]
yy = np.linspace(-1,1,H).reshape(-1,1)
xx = np.linspace(-1,1,W).reshape(1,-1)
dd = np.sqrt(xx**2 + yy**2)
vig = 1 - 0.25 * (dd/np.sqrt(2))
vig = np.clip(vig[:,:,np.newaxis], 0, 1)
rgb = np.clip(rgb * vig, 0, 255).astype(np.uint8)

# 保存
Image.fromarray(rgb).save(PNG, "PNG", compress_level=6)
print(f"  PNG: {os.path.abspath(PNG)}")

with rasterio.open(TIF, "w", driver="GTiff", height=H, width=W,
                   count=3, dtype="uint8", crs=crs, transform=tf,
                   compress="deflate", tiled=True) as dst:
    for i in range(3):
        dst.write(rgb[:,:,i], i+1)
print(f"  TIF: {os.path.abspath(TIF)}")

# 统计输出
print(f"\n  配色: Electric Blue")
print(f"  VIZ_MAX = {VIZ_MAX}m (0=白, {VIZ_MAX}=全黑)")
for lo, hi in [(-999,0),(0,0.2),(0.2,0.5),(0.5,1),(1,2),(2,VIZ_MAX),(VIZ_MAX,999)]:
    c = ((d>=lo)&(d<hi)).sum()
    pct = c/valid.sum()*100
    bar = "█"*int(pct)
    print(f"  [{lo:>6.1f}, {hi:>6.1f}]: {c:>10,} ({pct:>5.1f}%) {bar}")

print(f"\n  ✅ 完成! 打开 output/jingjiang_blue.png 查看")
