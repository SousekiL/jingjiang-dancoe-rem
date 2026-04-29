# 🌊 荆江 Dan Coe 风格 REM (Relative Elevation Model) 自动生成

**纯 Python 全自动流程，无需 QGIS，从公开 DEM 数据直接生成 Dan Coe 经典风格的发光河流可视化。**

聚焦中国长江荆江段（湖北枝江 → 湖南城陵矶），展现"九曲回肠"的千年古河道、牛轭湖、天然堤遗迹。黑色背景中，电光蓝色的河流脉络从黑暗中浮现，废弃古河道如幽灵般隐约可见。

---

## ⚡ 快速开始

### 前提
- Python ≥3.9，推荐 conda 管理环境
- **GDAL ≥3.0** (系统级安装): macOS `brew install gdal` / Ubuntu `sudo apt install gdal-bin`

### 1. 创建环境

```bash
conda create -n jingjiang python=3.11 -y
conda activate jingjiang
pip install -r requirements.txt
```

### 2. 获取 DEM 数据

登录 [地理空间数据云 (gscloud.cn)](https://www.gscloud.cn)，下载 **ASTER GDEM 30M** 瓦片（框选荆江区域：111.0°–113.5°E, 29.0°–30.5°N），共需 6 个 `.img` 栅格文件，放入 `data/` 目录。

> 瓦片列表：`ASTGTM_N29E111L.img`, `N29E112W`, `N29E113L`, `N30E111I`, `N30E112B`, `N30E113T`。

### 3. 一键运行

```bash
python 01_download_dem.py        # 合并 6 个瓦片 → UTM 49N 投影
python 02_make_rem.py            # OSM 长江中心线 → IDW 插值 → REM
python 03_visualize_dancoe.py    # Dan Coe 风格渲染
```

或使用**实验性脚本**（使用 GDAL `gdal_grid` IDW，精度更高）：

```bash
conda run -n rem_env python generate_jingjiang.py
```

### 4. 多配色方案

```bash
python 03_visualize_dancoe.py --cmap magenta_glow   # 玫红辉光
python 03_visualize_dancoe.py --cmap gold_ember     # 金琥珀色
python 03_visualize_dancoe.py --cmap cyan_neon      # 青色霓虹
python 03_visualize_dancoe.py --cmap ocean_depth    # 深海蓝绿
python 03_visualize_dancoe.py --cmap volcanic_red   # 火山赤红
```

---

## 📂 项目结构

```
jingjiang-dancoe-rem/
├── config.py                 # 🔧 全局参数 (范围/配色/采样间距/IDW)
├── 01_download_dem.py        # Step 1: ASTER 瓦片合并 + 裁剪投影
├── 02_make_rem.py            # Step 2: OSM 长江中心线 + KDTree IDW + REM
├── 03_visualize_dancoe.py    # Step 3: 6 套配色 + Hillshade + 暗角后处理
├── generate_jingjiang.py     # (实验) gdal_grid IDW 高精度版本
├── requirements.txt          # pip 依赖
├── README.md                 # 本文档
├── TUTORIAL.md               # 📖 从零开始详细中文教程
├── data/                     # (自动创建) DEM 输入
└── output/                   # (自动创建) REM 栅格 + PNG/TIF 成果
```

---

## 🗺️ 核心算法

```
ASTER 瓦片 (6 × 30m)                OpenStreetMap
        │                                │
        ▼                                ▼
  gdalwarp 合并投影               osmnx 筛选长江主河道
        │                                │
        ▼                                ▼
   UTM 49N DEM          ──────────  河流中心线 (155km)
   (8118×5629 px)                    采样 1035 个点
        │                                │
        ├────────  IDW 插值 ────────────┘
        │          scipy.cKDTree / gdal_grid
        ▼
  河面高程栅格 (每个像素拟合河面高度)
        │
        ▼
  REM = DEM − 河面高程  (河面=0, 两岸>0)
        │
        ▼
  自定义 7 段渐变 colormap  (0m=纯白 → 5m=电光蓝 → 10m→全黑)
  + GDAL Hillshade 柔光混合 (15%)
  + 暗角 + 伽马校正 + 锐化
        │
        ▼
  8118×5629 px PNG + GeoTIFF
```

---

## 🔬 技术要点

| 特性 | 说明 |
|------|------|
| **全自动 OSM 河道** | `osmnx` 自动下载 OSM 的 `waterway=river` 并筛选名含 "长江/Yangtze" 的线段 |
| **两种 IDW 实现** | `02_make_rem.py`: 纯 NumPy/SciPy cKDTree 分块；`generate_jingjiang.py`: GDAL gdal_grid（更精确）|
| **米级 UTM 投影** | UTM Zone 49N (EPSG:32649)，插值距离真实米制 |
| **无硬边界裁剪** | 全图有效像素参与 REM 计算，由 colormap 自然控制背景暗度 |
| **6 套配色方案** | 电光蓝、玫红辉光、金琥珀、青霓虹、深海蓝绿、火山赤红 |
| **双输出格式** | 高清 PNG (直接观赏) + 带地理坐标 GeoTIFF (QGIS 叠加卫星图) |

---

## ⚙️ 自定义参数 (`config.py`)

```python
# 荆江段精确范围 (WGS84)
BBOX_WGS84 = {'west': 111.0, 'south': 29.0, 'east': 113.5, 'north': 30.5}

# IDW 参数
RIVER_SAMPLE_SPACING = 150.0   # 采样间距 (米)
IDW_K_NEIGHBORS      = 12      # 最近邻数量
IDW_POWER            = 2.0     # 距离衰减指数

# 可视化
VIZ_MAX = 10                   # colormap 上限 (米), 超出此值全黑
VIZ_CMAP = 'electric_blue'     # 默认配色
```

---

## 📖 完整教程

参阅 [TUTORIAL.md](./TUTORIAL.md)，包含：
- GDAL 安装详解 (macOS/Ubuntu/Windows)
- 地理空间数据云逐步骤截屏指引
- 参数调优指南 (不同河段/不同 DEM 分辨率)
- 常见故障排查 (OSM 网络问题、内存不足、GDAL 版本冲突)

---

## 🙏 致谢

- **Dan Coe** — REM 可视化方法的创造者，[dancoecarto.com](https://dancoecarto.com)
- **[RiverREM](https://github.com/OpenTopography/RiverREM)** (Kenneth Larrieu / OpenTopography) — 全自动 REM Python 包
- **OpenStreetMap** — 全球免费河流矢量数据
- **ASTER GDEM** — METI/NASA 联合提供的全球 30m DEM

---

## 📄 License

代码采用 **MIT License**。DEM 数据版权归原始提供方（ASTER GDEM: METI/NASA），OSM 数据遵循 [ODbL](https://opendatacommons.org/licenses/odbl/)。
