# 🌊 荆江段 Dan Coe 风格 REM (Relative Elevation Model) 自动生成

**纯 Python 全自动流程，无需 QGIS，从公开 DEM 数据直接生成 Dan Coe 经典风格的发光河流可视化。**

聚焦长江荆江段（湖北枝江 → 湖南城陵矶），展现"九曲回肠"的千年古河道、牛轭湖、天然堤遗迹。

![原理示意](TUTORIAL.md) <!-- 教程中有详细图解 -->

> 🎨 **效果预览**：黑色背景中，电光蓝色的河流脉络从黑暗中浮现，两侧的废弃古河道、河漫滩纹理宛如发光的神经脉络。

---

## ⚡ 快速开始 (三步)

### 前提
- Python 3.9+
- GDAL (>=3.0) 已安装 (macOS: `brew install gdal` / Ubuntu: `sudo apt install gdal-bin`)

### 1. 安装依赖

```bash
conda create -n jingjiang python=3.11 -y
conda activate jingjiang
pip install -r requirements.txt
```

### 2. 获取 DEM 数据

**推荐**：登录 [地理空间数据云](https://www.gscloud.cn)，搜索 `ASTER GDEM 30M`，框选荆江区域 (111.0-113.5°E, 29.0-30.5°N)，下载 `.tif` 后放入本项目的 `data/` 目录。

### 3. 运行全流程

```bash
# 步骤1: DEM 裁剪 + 投影
python 01_download_dem.py

# 步骤2: OSM 获取长江 → IDW 插值 → REM 生成
python 02_make_rem.py

# 步骤3: Dan Coe 风格伪彩色渲染 (电光蓝)
python 03_visualize_dancoe.py
```

成果自动输出到 `output/` 目录：
- `rem_visualization.png` —— 高清 PNG (直接观赏)
- `rem_visualization.tif` —— 带地理坐标 GeoTIFF (可在 QGIS 继续处理)
- `rem.tif` —— 原始 REM 浮点栅格 (科研用)

### 切换配色

```bash
python 03_visualize_dancoe.py --cmap magenta_glow   # 玫红辉光
python 03_visualize_dancoe.py --cmap gold_ember     # 金琥珀色
python 03_visualize_dancoe.py --cmap cyan_neon      # 青色霓虹
```

---

## 📂 项目结构

```
jingjiang-rem/
├── config.py              # 🔧 全局参数 (范围/配色/采样间距)
├── 01_download_dem.py     # 步骤1: DEM 预处理
├── 02_make_rem.py       # 步骤2: REM 自动生成 (OSM + IDW + scipy cKDTree)
├── 03_visualize_dancoe.py # 步骤3: 伪彩色渲染
├── requirements.txt       # Python 依赖
├── README.md            # 本文档 (快速入门)
├── TUTORIAL.md          # 📖 详细教程 (数据获取/参数调优/故障排查)
├── data/                # 自动创建 (存放输入 DEM)
└── output/              # 自动创建 (存放输出成果)
```

---

## 🔬 技术亮点

| 特性 | 说明 |
|------|------|
| **全自动 OSM 河流提取** | 无需手动绘制中心线，`osmnx` 自动从 OpenStreetMap 下载并筛选长江主河道 |
| **纯 NumPy/SciPy IDW** | 不依赖 QGIS/ArcGIS 插值工具，`cKDTree` 分块处理大规模栅格 |
| **米级 UTM 投影** | 全程使用 UTM Zone 49N (EPSG:32649)，确保插值距离单位为真实米 |
| **距离裁剪** | 自动将超出河流 25km 范围的像素设为 NoData，保证 "夜光" 效果纯净 |
| **自定义色带引擎** | 内置 6 套 Dan Coe 风格配色 (电光蓝、玫红、琥珀、青霓虹等) |
| **GeoTIFF + PNG 双输出** | 同时输出带坐标的 GIS 栅格和可直接发社交媒体的高清图 |

---

## 📖 详细教程

- **环境搭建**、**数据获取详细步骤**、**参数调优指南**、**常见问题排错** 请参阅：[TUTORIAL.md](./TUTORIAL.md)

---

## 📄 许可

本项目脚本采用 **MIT License**。
DEM 数据请遵守原始数据源许可（如 ASTER GDEM 由 METI/NASA 提供，免费使用）。
OpenStreetMap 数据遵循 [ODbL](https://opendatacommons.org/licenses/odbl/)。

---

## 🙏 致谢

- **Dan Coe** —— REM 可视化方法的创造者，启发了本项目所有艺术风格
- **Kenneth Larrieu** —— [RiverREM](https://github.com/klarrieu/RiverREM) Python 包，验证了全自动 REM 的可行性
- **OpenStreetMap 贡献者** —— 提供了全球免费河流数据

---

**欢迎提 Issue / PR / 分享你的荆江地图！** 🗺️
