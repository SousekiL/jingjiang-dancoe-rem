# 🌊 荆江段 Dan Coe 风格 REM (Relative Elevation Model) 完全制作教程

> 目标：使用 Python 纯代码全自动流程，从公开 DEM 数据生成类似 Dan Coe LiDAR 河流图的 "电光蓝/霓虹辉光" 可视化效果。
> 区域：长江荆江段（湖北枝江 — 湖南城陵矶），涵盖著名的"九曲回肠"古河道遗迹。

---

## 📑 目录

1. [项目结构与原理概述](#1-项目结构与原理概述)
2. [环境准备与安装](#2-环境准备与安装)
3. [数据准备：获取荆江段 DEM](#3-数据准备获取荆江段-dem)
4. [核心流程三步走](#4-核心流程三步走)
5. [自定义参数详解](#5-自定义参数详解)
6. [常见问题与排错](#6-常见问题与排错)
7. [进阶玩法（多配色/后处理/多河段）](#7-进阶玩法)
8. [参考资料与工具链](#8-参考资料与工具链)

---

## 1. 项目结构与原理概述

### 1.1 什么是 REM？

**REM (Relative Elevation Model，相对高程模型)** 是一种数据处理方法：

- **标准 DEM**：高程 0 = 海平面，河流下游比上游低。
- **REM**：高程 0 = **河流水面**，两侧高程表示 "高出河面多少米"。

这样处理后，河道本身被抹平为 "0"，而古河道、河漫滩、牛轭湖、天然堤等历史河道遗迹的微弱起伏就会被极度放大，形成宛如"发光的河道脉络"从黑暗中浮现的震撼视觉效果。

### 1.2 本项目结构

```
jingjiang-rem/
├── config.py                  # 全局配置（范围、配色、参数）
├── 01_download_dem.py         # 步骤1：DEM 下载 / 裁剪 / 投影
├── 02_make_rem.py             # 步骤2：OSM 获取河流 → IDW 插值 → REM
├── 03_visualize_dancoe.py     # 步骤3：伪彩色渲染 + 导出 PNG/GeoTIFF
├── requirements.txt           # Python 依赖
└── TUTORIAL.md                # 本教程（你正在看的）

运行后自动生成的目录：
├── data/                      # 原始 / 处理后的栅格数据
│   ├── dem_raw.tif            # 下载的原始 DEM (可选)
│   ├── dem_proj.tif           # 裁剪 + 投影到 UTM 49N 的 DEM
│   └── river_line_reference.geojson   # OSM 获取的河流参考线
└── output/                    # 输出成果
    ├── rem.tif                # 原始 REM 浮点栅格 (高度超出河面的米数)
    ├── rem_visualization.png       # Dan Coe 风格高清 PNG
    ├── rem_visualization.tif       # 带地理坐标的可视化 GeoTIFF
    └── colorbar_electric_blue.png   # 色带图例
```

### 1.3 核心算法流程

```
┌─────────────────┐
│   获取 DEM      │   (SRTM/ASTER, 30m)
│  (荆江段裁剪)    │
└────────┬────────┘
         │
         v
┌─────────────────┐
│ OSM 获取长江    │   (waterway=river, 自动筛选"长江/Yangtze")
│  主河道中心线    │
└────────┬────────┘
         │
         v
┌─────────────────┐
│ 沿中心线采样    │   (每 150m 取一点，从 DEM 读高程)
│ (x, y, z) 序列  │
└────────┬────────┘
         │
         v
┌─────────────────┐     scipy.spatial.cKDTree
│ IDW 插值河面    │     -------------------------
│ 到全图每个像素   │     每个像素: 找K个最近河流点
└────────┬────────┘     加权平均 = 拟合河面高程
         │
         v
┌─────────────────┐
│   REM 栅格      │     REM(i,j) = DEM(i,j) - 河面(i,j)
│ = DEM - 河面    │     远处无效像素设为 NoData (黑色)
└────────┬────────┘
         │
         v
┌─────────────────┐     自定义 colormap (电光蓝渐变到黑)
│ Dan Coe 伪彩色  │     0m(河面)= #e0f7ff (亮蓝)
│  渲染 + 叠加    │     10m= #0088ff | 25m= #001133 (暗)
│  Hillshade      │     >25m = 纯黑
└─────────────────┘
```

---

## 2. 环境准备与安装

### 2.1 前置系统依赖 (必须)

无论何种操作系统，都需要先安装 `GDAL`：

#### macOS (推荐用 Homebrew)

```bash
brew install gdal
```

#### Ubuntu / Debian / WSL

```bash
sudo apt-get update
sudo apt-get install gdal-bin libgdal-dev
```

#### Windows

1. 下载 [OSGeo4W 安装器](https://trac.osgeo.org/osgeo4w/)
2. 选择 "Express Install" 或 "Advanced Install"
3. 搜索并安装 `gdal`、`python3-gdal`
4. 将 GDAL 的 bin 目录加入系统 PATH

### 2.2 Python 环境创建

推荐用 `conda` 管理环境（避免 GDAL 版本冲突）：

```bash
# 创建 Python 3.11 环境
conda create -n jingjiang_env python=3.11 -y

# 激活 (每次运行前都要激活)
conda activate jingjiang_env

# 安装本项目依赖
pip install -r requirements.txt

# 额外验证 GDAL Python 绑定是否工作
python -c "from osgeo import gdal; print(gdal.VersionInfo())"
# 应输出类似 3050000 的数字（表示 3.5.0）
```

如果不使用 conda，用 `venv` 也可以：

```bash
python -m venv jingjiang_env
source jingjiang_env/bin/activate    # macOS/Linux
# jingjiang_env\Scripts\activate     # Windows

pip install -r requirements.txt
```

### 2.3 依赖包说明

| 包名 | 用途 |
|------|------|
| rasterio | 栅格 I/O、地理坐标读写 |
| shapely | 几何操作 (LineString 采样、简并) |
| geopandas | GeoDataFrame、投影转换 |
| osmnx | 从 OpenStreetMap 下载河流中心线 |
| scipy | scipy.spatial.cKDTree (IDW 插值核心) |
| numpy | 数组运算 |
| matplotlib | 色带图例生成 |
| Pillow | 高效 PNG 输出 |
| tqdm | 进度条 |
| pyproj | 坐标系转换 |

---

## 3. 数据准备：获取荆江段 DEM

### 3.1 推荐方式：地理空间数据云 (gscloud.cn)

**最适合中国大陆用户，下载速度快，免费。**

1. **注册账号**
   - 访问 https://www.gscloud.cn
   - 点击右上角注册（支持手机号或邮箱，也可用 QQ 扫码）
   - 登录

2. **检索 DEM 数据**
   - 顶部菜单 → **高级检索**
   - 数据集：选择 `DEM数字高程数据`
   - 产品：选择 `ASTER GDEM 30M 分辨率数字高程数据`（或 `SRTM DEM 90M`）
   
3. **设定空间范围（荆江段）**
   - 空间范围选择 → **经纬度**
   - 输入以下坐标（即 `config.py` 中默认范围）：
     - 最小经度: 111.0
     - 最小纬度: 29.0
     - 最大经度: 113.5
     - 最大纬度: 30.5
   - 或者手动在左侧地图上大致框选荆江区域

4. **下载**
   - 点击 **检索**，勾选所有结果项
   - 点击 **批量下载** → 下载 `.zip`
   - 解压后将所有 `.tif` 文件放入本项目的 `data/` 目录下
   - (如果有镶嵌线 `.tfw` 等附属文件可以忽略)

### 3.2 备用方式：NASA EarthData

- https://earthexplorer.usgs.gov/
- 搜索 "SRTM 1 Arc-Second Global"
- 框选荆江区域下载 `.tif` 放入 `data/` 目录

### 3.3 备用方式：自动下载

```bash
pip install elevation  # 额外安装
```

`01_download_dem.py` 已内置自动下载逻辑（数据源为 AWS S3 上的 Terrain Tiles），但国内访问可能较慢或失败。

---

## 4. 核心流程三步走

所有命令都在项目根目录下执行，且确保 `conda activate jingjiang_env`（或使用对应的 venv）。

### 步骤 1：DEM 预处理

```bash
python 01_download_dem.py
```

**功能**：
- 检查 `data/` 目录中是否有手动下载的 `.tif` DEM
- 自动裁剪到荆江范围
- 重投影到 **UTM Zone 49N (EPSG:32649)** —— 这是最适合荆江段的米级坐标系
- 生成 `data/dem_proj.tif`

**输出确认**：
```
[OK] 裁剪与重投影完成 -> data/dem_proj.tif
```

**常见问题**：
- 提示 "未找到任何 DEM 数据源" → 请先把下载的 `.tif` 放入 `data/` 目录
- 提示 "gdalwarp 命令未找到" → 请按 2.1 节安装 GDAL

---

### 步骤 2：REM 生成

```bash
python 02_make_rem.py
```

**功能**：
1. 从 OpenStreetMap (OSM) 查询荆江段范围内的 `waterway=river`
2. 自动筛选 `name` 包含 "长江" / "Yangtze" 的主河道
3. 投影到 UTM 并合并所有河道段为一条连续的中心线
4. 沿中心线每 `150米` 采样一个点，读取 DEM 高程
5. 使用 **scipy.spatial.cKDTree + IDW (反距离权重)** 插值：
   - 对 DEM 中每一个像素，找到最近的 12 个河流采样点
   - 按 **平方反比** 加权平均，得到该位置的"拟合河面高程"
   - 与像素距离最近河流点超过 25km 的像素设为 NoData
6. 计算 `REM = DEM - 河面高程`
7. 输出 `output/rem.tif`

**运行时间**：
| 区域大小 | 预计时间 |
|---------|---------|
| 宽松范围 (111E-113.5E, 29N-30.5N) | 15~30 分钟 |
| 紧凑范围 (111.8E-113.2E, 29.2N-30.3N) | 5~10 分钟 |

**进度提示**：
```
[OSM] 正在查询 OpenStreetMap ...
[PROC] 合并河道段并投影到 UTM...
[DEM] 沿河道采样 892 个点 (间距 150m)...
[REM] 构建 KDTree (892 个河道点)...
[REM] 分块处理: 45/45 [████████████████] 100%
[OK]   REM 生成完成 -> output/rem.tif
```

**网络问题**：
- OSM 查询需要联网访问 `api.openstreetmap.org`，国内可能被墙
- **解决方案**：开启全局 VPN 代理后重试，或使用国内 OSM 镜像（需修改脚本 `osmnx` 的 endpoint）

---

### 步骤 3：Dan Coe 风格渲染

```bash
# 默认: 经典电光蓝
python 03_visualize_dancoe.py

# 切换为其他配色:
python 03_visualize_dancoe.py --cmap magenta_glow   # 玫红辉光
python 03_visualize_dancoe.py --cmap gold_ember     # 金琥珀
python 03_visualize_dancoe.py --cmap cyan_neon      # 青色霓虹
```

**输出文件**：
| 文件 | 说明 |
|------|------|
| `output/rem_visualization.png` | 高清 PNG (无地理坐标，直接观赏) |
| `output/rem_visualization.tif` | 带地理坐标的 GeoTIFF (可在 QGIS 继续调色/叠加) |
| `output/colorbar_electric_blue.png` | 色带图例 |

**渲染效果原理**：
- REM 值 `0` (河面) → `#e0f7ff` (亮白蓝)
- REM 值 `0~10m` → `#00ccff` → `#0088ff` (电光蓝渐变)
- REM 值 `10~25m` → `#0044aa` → `#001133` (暗蓝→近黑)
- REM 值 `>25m` → `#000000` (纯黑，隐入背景)
- 负值 (低于河面/水面) → 同样设为最亮，代表当前水道

---

## 5. 自定义参数详解

所有可调参数集中在 `config.py`：

### 5.1 地理范围

```python
# 默认: 涵盖完整荆江 + 江汉平原 + 洞庭湖平原
BBOX_WGS84 = {
    'west': 111.0,
    'south': 29.0,
    'east': 113.5,
    'north': 30.5
}

# 紧凑范围: 只聚焦九曲回肠核心段 (石首-监利-岳阳)
BBOX_WGS84_TIGHT = {
    'west': 111.8,
    'south': 29.2,
    'east': 113.2,
    'north': 30.3
}

USE_TIGHT_BBOX = False   # 设为 True 使用紧凑范围
```

### 5.2 REM 算法参数

```python
RIVER_SAMPLE_SPACING = 150.0   # 河流采样间距 (米)。越小越平滑但越慢
IDW_K_NEIGHBORS = 12           # IDW 最近邻数量。建议 8~20
IDW_POWER = 2.0                # IDW 距离衰减指数 (1=线性, 2=平方，最常用)
REM_BUFFER_M = 25000           # 有效范围半径 (米)。只计算河流两侧 25km 内
IDW_BLOCK_SIZE = 2048          # 分块处理大小 (像素)。内存小可改为 1024
```

**调参建议**：

| 参数 | 效果 |
|------|------|
| `IDW_K_NEIGHBORS` 增大 (如 50) | 河面更平滑，但可能丢失局部弯曲细节 |
| `IDW_K_NEIGHBORS` 减小 (如 4) | 更贴合河道弯曲，但可能出现锯齿 |
| `IDW_POWER` 增大 (如 3) | 远处点影响更小，插值更局部化 |
| `REM_BUFFER_M` 增大 | 显示更远的地形，但 "黑暗背景" 效果减弱 |

### 5.3 可视化参数

```python
VIZ_MIN = 0    # 可视化下限 (河面高程)
VIZ_MAX = 25   # 可视化上限 (超出此值的像素全黑)

# 配色选择
VIZ_CMAP = 'electric_blue'   # 默认电光蓝
# 可选: 'cyan_neon', 'magenta_glow', 'gold_ember', 'ocean_depth', 'volcanic_red'
```

| 配色名 | Dan Coe 对应风格 | 适用氛围 |
|--------|----------------|---------|
| `electric_blue` | 经典电光蓝 (Alabama River) | 通用，最还原 |
| `cyan_neon` | 青色霓虹 | 科技/未来感 |
| `magenta_glow` | 玫红辉光 (Lena River Delta) | 极地/冷峻 |
| `gold_ember` | 金琥珀色 | 历史/温暖 |
| `ocean_depth` | 深海蓝绿 | 沉静/深邃 |
| `volcanic_red` | 火山赤红 | 壮丽/力量感 |

---

## 6. 常见问题与排错

### 6.1 OSM 查询失败 / 超时

**现象**：
```
[ERROR] OSM 在该范围内未返回任何河流数据
```

**排查**：
1. 检查网络是否能访问 `https://api.openstreetmap.org`
2. 尝试开启 VPN
3. 如果无法联网，改用 **方案 B**：
   - 在 QGIS 中绘制一条荆江段中心线（只需一条线要素）
   - `Layer → Save Features As → data/river_line.geojson`
   - 需要在 `02_make_rem.py` 中修改 `_get_river_from_osm` 为读取本地文件

### 6.2 "有效采样点太少"

**现象**：
```
[ERROR] 从 DEM 采样的有效高程点太少
```

**原因**：
- OSM 获取的河流中心线坐标与 DEM 覆盖范围不重叠
- DEM 是 "泾河流域" 而不是长江

**解决**：
- 检查 `data/` 中是否混入了错误的 DEM 文件
- 在 QGIS 中打开 `data/dem_proj.tif` 和 `data/river_line_reference.geojson`，目视检查覆盖范围

### 6.3 内存不足 (OOM)

**现象**：
```
MemoryError
```

**解决**：
- 编辑 `config.py`，减小 `IDW_BLOCK_SIZE`（如 `1024` 或 `512`）
- 将 `USE_TIGHT_BBOX` 设为 `True`
- 如果仍不够，建议换用更高配置机器，或改用基于 GDAL 命令行的分块方案

### 6.4 河流不连续 / 中间断开

**现象**：REM 中某段河流缺失 / OSM 河道有多段线，合并后断开。

**解决**：
- `02_make_rem.py` 已自动取最长的一段作为主河道，这能避免大部分问题
- 如果断开恰好出现在你最关心的河段，建议手动绘制整条平滑中心线

---

## 7. 进阶玩法

### 7.1 在 QGIS 中查看 REM 并自定义调色

`output/rem_visualization.tif` 可以直接拖进 QGIS：

1. 打开 QGIS → `Layer → Add Layer → Add Raster Layer`
2. 选择 `output/rem_visualization.tif`
3. 它自带地理坐标，可与卫星影像、水系图叠加
4. 如果你想用 QGIS 重新调色：
   - 打开 `output/rem.tif`（原始的浮点 REM）
   - `右键 → Properties → Symbology → Render type: Singleband pseudocolor`
   - Min: 0, Max: 25
   - Color ramp: 自定义 (黑→深蓝→亮蓝→白)

### 7.2 批量导出所有配色

```bash
# bash 脚本
for cmap in electric_blue cyan_neon magenta_glow gold_ember ocean_depth volcanic_red; do
    python 03_visualize_dancoe.py --cmap $cmap
done
```

### 7.3 处理长江其他河段

只需修改 `config.py` 中的 `BBOX_WGS84`：

| 河段 | 建议范围 (W,S,E,N) |
|------|-------------------|
| 金沙江虎跳峡 | (100.0, 26.8, 100.5, 27.2) |
| 三峡段 | (110.0, 30.5, 111.5, 31.2) |
| 武汉段 | (113.5, 29.8, 114.6, 30.8) |
| 长江口三角洲 | (120.5, 30.5, 122.5, 32.0) |

同时修改 `UTM_CRS` 到对应 UTM 带（可用 [epsg.io](https://epsg.io) 查询）。

### 7.4 后期 Photoshop 增强

`rem_visualization.png` 可以直接用 Photoshop / GIMP 后处理：

1. 微调色阶 (Levels)：拉高暗部，进一步压缩背景
2. 添加微妙纹理 (Film Grain)：减少色带断层感
3. 添加暗角 (Vignette)：强化中心发光效果
4. 可选锐化 (Unsharp Mask) + "叠加"混合模式的 Hillshade 层

---

## 8. 参考资料与工具链

| 资源 | 链接 | 说明 |
|------|------|------|
| Dan Coe 官方教程 | [dancoecarto.com](https://dancoecarto.com/creating-rems-in-qgis-the-idw-method) | REM 的始祖，基于 QGIS |
| RiverREM (Python 包) | [github.com/klarrieu/RiverREM](https://github.com/klarrieu/RiverREM) | 另一款全自动 REM 工具 |
| 地理空间数据云 | [gscloud.cn](https://www.gscloud.cn) | 中国首选 DEM 数据源 |
| NASA EarthData | [earthexplorer.usgs.gov](https://earthexplorer.usgs.gov) | 国际 DEM 数据源 |
| 荆江百科 (了解你要画的对象) | [百度百科-荆江](https://baike.baidu.com/item/%E8%8D%86%E6%B1%9F) | ... |

---

**祝制图顺利！如果你成功生成了荆江的 Dan Coe 风格地图，欢迎分享你的成果配色与心得。** 🗺️
