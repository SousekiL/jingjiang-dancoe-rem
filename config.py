# -*- coding: utf-8 -*-
"""
config.py
=========
荆江段 REM (Relative Elevation Model) 项目全局配置。

修改本文件即可自定义区域范围、配色、采样密度等参数。
"""

import os

# ==================== 1. 地理范围 (WGS84) ====================
#
# 荆江段：从湖北枝江到湖南城陵矶，涵盖著名的"九曲回肠"。
#
# 默认范围 (宽松) —— 包含完整荆江 + 周边江汉平原、洞庭湖平原
BBOX_WGS84 = {
    'west': 111.0,
    'south': 29.0,
    'east': 113.5,
    'north': 30.5
}

# 紧凑范围 —— 更聚焦九曲回肠核心段 (石首-监利-岳阳)
BBOX_WGS84_TIGHT = {
    'west': 111.8,
    'south': 29.2,
    'east': 113.2,
    'north': 30.3
}

USE_TIGHT_BBOX = False  # 设为 True 则使用紧凑范围

def get_bbox():
    """返回 (west, south, east, north) 元组"""
    b = BBOX_WGS84_TIGHT if USE_TIGHT_BBOX else BBOX_WGS84
    return (b['west'], b['south'], b['east'], b['north'])


# ==================== 2. 坐标系 ====================
# UTM Zone 49N (108°E–114°E) 完美覆盖荆江段，单位：米
UTM_CRS = "EPSG:32649"


# ==================== 3. REM 算法参数 ====================

# 沿河流中心线采样间距 (米)。
# 值越小越平滑，但计算量越大。30m DEM 建议 100~200m。
RIVER_SAMPLE_SPACING = 150.0

# IDW 插值最近邻数量
IDW_K_NEIGHBORS = 12

# IDW 距离衰减指数 (2 = 平方反比，最常用)
IDW_POWER = 2.0

# 不再使用距离遮罩（之前这是导致效果差的根本原因）
# 设为极大值让整个 DEM 都参与计算，由 colormap 自然控制远处变暗
REM_BUFFER_M = 99999999

# IDW 分块处理块大小 (像素)。内存较小时可改小 (如 1024)。
IDW_BLOCK_SIZE = 2048


# ==================== 4. 可视化参数 ====================

# REM 可视化高度范围 (米)。
# 河面=0，高出河面 0~VIZ_MAX 的像素会被映射到色带。
# 超出 VIZ_MAX 的像素全部压为黑色。
# 江汉平原相对高程多在 0~20m，默认值 25 适合。
VIZ_MIN = 0
VIZ_MAX = 10

# 默认 Dan Coe 风格色带。
# 可选: 'electric_blue' | 'cyan_neon' | 'magenta_glow' | 'gold_ember'
VIZ_CMAP = 'electric_blue'


# ==================== 5. 路径配置 ====================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

DEM_RAW = os.path.join(DATA_DIR, "dem_raw.tif")
DEM_PROJ = os.path.join(DATA_DIR, "dem_proj.tif")
REM_TIF = os.path.join(OUTPUT_DIR, "rem.tif")
VIZ_TIF = os.path.join(OUTPUT_DIR, "rem_visualization.tif")
VIZ_PNG = os.path.join(OUTPUT_DIR, "rem_visualization.png")

# 自动创建目录
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
