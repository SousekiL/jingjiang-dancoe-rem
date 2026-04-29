# 🌊 Jingjiang Dan Coe-Style REM (Relative Elevation Model)

**A fully automated Python pipeline — no QGIS required — that generates Dan Coe's iconic luminous river visualizations from publicly available DEM tiles.**

Targets the Jingjiang section of China's Yangtze River (Zhicheng → Chenglingji), revealing millennia of meander migration, oxbow lakes, and ancient channel scars. Electric-blue river channels emerge from a deep black background like glowing neural pathways through time.

---

## ⚡ Quick Start

### Prerequisites
- Python ≥3.9 (conda recommended)
- **GDAL ≥3.0** (system-level): macOS `brew install gdal` / Ubuntu `sudo apt install gdal-bin`

### 1. Create environment

```bash
conda create -n jingjiang python=3.11 -y
conda activate jingjiang
pip install -r requirements.txt
```

### 2. Obtain DEM data

Log into [Geospatial Data Cloud (gscloud.cn)](https://www.gscloud.cn), download **ASTER GDEM 30M** tiles covering the Jingjiang reach (111.0°–113.5°E, 29.0°–30.5°N). Six `.img` rasters are required, placed into the `data/` directory.

> Tile list: `ASTGTM_N29E111L.img`, `N29E112W`, `N29E113L`, `N30E111I`, `N30E112B`, `N30E113T`.

### 3. Run the pipeline

```bash
python src/01_download_dem.py        # Merge 6 tiles → UTM Zone 49N projection
python src/02_make_rem.py            # OSM Yangtze centerline → IDW interpolation → REM
python src/03_visualize_dancoe.py    # Dan Coe-style rendering
```

Or use the **experimental script** (GDAL `gdal_grid` IDW, potentially more accurate):

```bash
conda create -n rem_env riverrem -c conda-forge -y
conda run -n rem_env python src/generate_jingjiang.py
```

### 4. Switch color schemes

```bash
python src/03_visualize_dancoe.py --cmap magenta_glow   # Magenta glow
python src/03_visualize_dancoe.py --cmap gold_ember     # Gold ember
python src/03_visualize_dancoe.py --cmap cyan_neon      # Cyan neon
python src/03_visualize_dancoe.py --cmap ocean_depth    # Ocean depth
python src/03_visualize_dancoe.py --cmap volcanic_red   # Volcanic red
```

---

## 📂 Project Structure

```
jingjiang-dancoe-rem/
├── config.py                 # 🔧 All tunable parameters (bbox, sampling, IDW, colormaps)
├── src/
│   ├── 01_download_dem.py    # Step 1: Merge ASTER tiles + crop + reproject to UTM 49N
│   ├── 02_make_rem.py        # Step 2: OSM Yangtze centerline + KDTree IDW + REM
│   ├── 03_visualize_dancoe.py# Step 3: 6 color schemes + Hillshade + vignette post-processing
│   ├── generate_jingjiang.py # [Experimental] gdal_grid IDW high-precision version
│   ├── run_all.py            # One-shot pipeline runner
│   └── step2_rem.py          # RiverREM wrapper
├── requirements.txt          # Python dependencies
├── README.md                 # This document
├── TUTORIAL.md               # 📖 Full Chinese walkthrough (data download, tuning, troubleshooting)
├── data/                     # (auto-created) DEM input tiles
└── output/                   # (auto-created) REM rasters + rendered PNG/TIF
```

---

## 🗺️ Core Algorithm

```
ASTER Tiles (6 × 30m)               OpenStreetMap
        │                                │
        ▼                                ▼
  gdalwarp merge + reproject       osmnx filter Yangtze mainstem
        │                                │
        ▼                                ▼
   UTM 49N DEM          ──────────  River centerline (155 km)
   (8118×5629 px)                   1,035 sample points
        │                                │
        ├────────  IDW Interpolation ────┘
        │          scipy.cKDTree / gdal_grid
        ▼
  River surface raster (interpolated water elevation per pixel)
        │
        ▼
  REM = DEM − River Surface  (channel = 0, floodplain > 0)
        │
        ▼
  Custom 7-stop colormap  (0m = pure white → 5m = electric blue → 10m → pure black)
  + GDAL Hillshade soft-light blend (15%)
  + Vignette + gamma correction + sharpening
        │
        ▼
  8118×5629 px PNG + GeoTIFF (georeferenced)
```

---

## 🔬 Technical Highlights

| Feature | Description |
|---------|-------------|
| **Automated OSM centerline** | `osmnx` downloads `waterway=river` segments and filters those named "长江 / Yangtze" |
| **Dual IDW implementations** | `02_make_rem.py`: pure NumPy/SciPy cKDTree block-based; `generate_jingjiang.py`: GDAL `gdal_grid` (more robust) |
| **Metric UTM projection** | UTM Zone 49N (EPSG:32649), true-meter interpolation distances |
| **No hard cutoff** | All valid DEM pixels participate in REM; colormap naturally fades distant terrain to black |
| **6 colormap schemes** | electric_blue, magenta_glow, gold_ember, cyan_neon, ocean_depth, volcanic_red |
| **Dual output format** | High-res PNG (ready to view) + georeferenced GeoTIFF (overlay in QGIS on satellite imagery) |

---

## ⚙️ Configuration (`config.py`)

```python
# Jingjiang extent (WGS84)
BBOX_WGS84 = {'west': 111.0, 'south': 29.0, 'east': 113.5, 'north': 30.5}

# IDW parameters
RIVER_SAMPLE_SPACING = 150.0   # Point spacing along river (meters)
IDW_K_NEIGHBORS      = 12      # Nearest neighbors for interpolation
IDW_POWER            = 2.0     # Inverse-distance exponent (2 = inverse-square)

# Visualization
VIZ_MAX = 10                   # Colormap ceiling (meters); above this → pure black
VIZ_CMAP = 'electric_blue'     # Default color scheme
```

**Pro tip:** decrease `VIZ_MAX` to 4–6 for extreme high-contrast "ghost channel" mode; increase to 20+ for gentler terrain gradients.

---

## 📖 Full Tutorial

See [TUTORIAL.md](./TUTORIAL.md) for a comprehensive Chinese-language guide covering:
- GDAL installation (macOS / Ubuntu / Windows)
- Step-by-step Geospatial Data Cloud download walkthrough
- Parameter tuning (different river reaches / DEM resolutions)
- Troubleshooting (OSM network issues, memory limits, GDAL version conflicts)

---

## 🙏 Acknowledgments

- **Dan Coe** — Creator of REM visualization, [dancoecarto.com](https://dancoecarto.com)
- **[RiverREM](https://github.com/OpenTopography/RiverREM)** (Kenneth Larrieu / OpenTopography) — Automated REM Python package
- **OpenStreetMap** — Global free river vector data
- **ASTER GDEM** — METI/NASA joint 30m global DEM

---

## 📄 License

Code: **MIT License**. DEM data: copyright belongs to original providers (ASTER GDEM: METI/NASA). OSM data: [ODbL](https://opendatacommons.org/licenses/odbl/).
