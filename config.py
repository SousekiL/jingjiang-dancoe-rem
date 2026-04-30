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

# ==================== 4b. 风格预设 (samplecases 对齐) ====================
#
# 说明：
# - 该预设主要服务于 03_visualize_dancoe.py 的 tone mapping / bloom / 亮芯效果
# - 不影响 REM 生成流程
STYLE_PRESET = "default"  # 可选: "default" | "samplecases_blue_v1"

STYLE_PRESETS = {
    "default": {
        "tone_percentile": None,        # None 表示沿用 VIZ_MAX
        "tone_vmax_cap_factor": 8.0,
        "tone_gamma": 1.15,
        "background": "black",          # "black" | "white"
        "alpha_power": 1.0,             # 仅 white 背景使用：alpha = (1-normalized)^alpha_power
        "bloom_enabled": False,
        "bloom_sigmas_px": (2.0, 6.0, 14.0),
        "bloom_weights": (0.55, 0.30, 0.15),
        "bloom_strength": 0.0,
        "core_width_m": 0.6,            # rem<=core_width 的亮芯增强范围 (米)
        "core_strength": 0.0,
        "mainstem_enabled": False,
        "mainstem_width_m": 1200.0,
        "mainstem_color": "#003a7a",
        "mainstem_alpha": 0.0,
        "mainstem_glow_strength": 0.0,
        "shade_strength": 0.35,         # hillshade 影响强度 (越大越立体也越脏)
        "vignette_strength": 0.28,
    },
    "samplecases_blue_v1": {
        "tone_percentile": 99.5,        # 自动估计上限：更接近 samplecases 的暗部层次
        "tone_vmax_cap_factor": 6.0,    # 防止大范围高地把 vmax 拉得过高
        "tone_gamma": 1.08,
        "background": "black",
        "alpha_power": 1.0,
        "bloom_enabled": True,
        "bloom_sigmas_px": (2.0, 7.0, 16.0),
        "bloom_weights": (0.60, 0.28, 0.12),
        "bloom_strength": 0.85,
        "core_width_m": 0.8,
        "core_strength": 1.0,
        "mainstem_enabled": False,
        "mainstem_width_m": 1400.0,
        "mainstem_color": "#00c7ff",
        "mainstem_alpha": 0.0,
        "mainstem_glow_strength": 0.0,
        "shade_strength": 0.28,
        "vignette_strength": 0.30,
    },
    "samplecases_green_v1": {
        "tone_percentile": 99.2,
        "tone_vmax_cap_factor": 4.0,
        "tone_gamma": 1.02,
        "background": "white",
        "alpha_power": 1.35,
        "bloom_enabled": True,
        "bloom_sigmas_px": (1.8, 6.0, 14.0),
        "bloom_weights": (0.62, 0.26, 0.12),
        "bloom_strength": 0.55,
        "core_width_m": 1.1,
        "core_strength": 0.55,
        "mainstem_enabled": True,
        "mainstem_width_m": 2200.0,
        "mainstem_color": "#003b6f",
        "mainstem_alpha": 0.92,
        "mainstem_glow_strength": 0.35,
        "streams_enabled": True,
        "streams_width_m": 380.0,
        "streams_color": "#2aa36b",
        "streams_alpha": 0.22,
        "streams_glow_strength": 0.10,
        "shade_strength": 0.0,
        "vignette_strength": 0.0,
    },
}


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
