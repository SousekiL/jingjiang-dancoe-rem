# AGENTS.md

## Project: jingjiang-dancoe-rem

A fully automated Python pipeline (no QGIS) that generates Dan Coe-style luminous river visualizations from publicly available DEM tiles.

- **Language / runtime**: Python 3.9+ (3.11 recommended)
- **System dependency**: GDAL ≥3.0 must be installed at OS level (`brew install gdal` on macOS, `apt install gdal-bin` on Ubuntu)
- **Virtual environment**: `conda` strongly recommended to avoid GDAL version conflicts

## Quick commands

```bash
# Create / activate environment
conda create -n jingjiang python=3.11 -y
conda activate jingjiang
pip install -r requirements.txt

# Verify GDAL Python bindings
python -c "from osgeo import gdal; print(gdal.VersionInfo())"

# Run pipeline (3 steps)
python src/01_download_dem.py              # merge tiles → crop → reproject UTM 49N
python src/02_make_rem.py                # OSM centerline → IDW → REM
python src/03_visualize_dancoe.py        # Dan Coe rendering

# Or one-shot
python src/run_all.py [--cmap <name>]
```

## Architecture & pipeline flow

| Step | Script | Key outputs | Details |
|------|--------|-------------|---------|
| 1 | `src/01_download_dem.py` | `data/dem_proj.tif` | Merge ASTER tiles (6 expected), crop to `config.py` bbox, reproject to **UTM Zone 49N (EPSG:32649)**. |
| 2 | `src/02_make_rem.py` | `output/rem.tif` | Downloads OSM `waterway=river` named “长江 / Yangtze”, samples DEM along centerline every 150 m, then runs **scipy cKDTree IDW** block-wise to interpolate a river-surface raster. REM = DEM − interpolated surface. |
| 3 | `src/03_visualize_dancoe.py` | `output/rem_visualization.png` + `.tif` + `colorbar_*.png` | Custom 7-stop colormaps, Hillshade soft-light blend, gamma, vignette, bloom presets. |

- Secondary experimental entrypoint: `src/generate_jingjiang.py` (uses GDAL `gdal_grid` for IDW, requires separate `conda env` via `riverrem` package).

## Configuration

All tunable constants live in `config.py`:
- `BBOX_WGS84` / `BBOX_WGS84_TIGHT` — study area (default 111°–113.5°E, 29°–30.5°N). Toggle `USE_TIGHT_BBOX` for faster runs.
- `RIVER_SAMPLE_SPACING` / `IDW_K_NEIGHBORS` / `IDW_POWER` — IDW controls.
- `VIZ_MAX` — colormap ceiling (default 10 m). Lower = higher-contrast ghost channels.
- `VIZ_CMAP` and `STYLE_PRESET` — rendering style.

## Data prerequisites

1. **DEM tiles** must be downloaded manually and placed in `data/` before Step 1.
   - Preferred source: Geospatial Data Cloud (https://www.gscloud.cn) → ASTER GDEM 30M.
   - Six tiles covering the default bbox: `ASTGTM_N29E111L.img`, `N29E112W`, `N29E113L`, `N30E111I`, `N30E112B`, `N30E113T`.
2. **OSM access** is required during Step 2 (`api.openstreetmap.org`). If blocked, use a VPN or manually supply a local `data/river_line.geojson` and adapt the loader in `02_make_rem.py`.

## CLI options worth knowing

```bash
# Step 2 debug exports (recommended when OSM returns many tributaries)
python src/02_make_rem.py --export-debug

# Step 3 color presets
python src/03_visualize_dancoe.py --cmap electric_blue   # default
python src/03_visualize_dancoe.py --cmap magenta_glow
python src/03_visualize_dancoe.py --cmap gold_ember
python src/03_visualize_dancoe.py --cmap cyan_neon
python src/03_visualize_dancoe.py --cmap ocean_depth
python src/03_visualize_dancoe.py --cmap volcanic_red

# Step 3 style preset aligned with reference images
python src/03_visualize_dancoe.py --preset samplecases_blue_v1
```

## Project layout

```
/
├── config.py              # tunable parameters
├── requirements.txt        # Python deps (rasterio, osmnx, geopandas, shapely, scipy, numpy, matplotlib, Pillow, tqdm, pyproj)
├── src/
│   ├── 01_download_dem.py
│   ├── 02_make_rem.py
│   ├── 03_visualize_dancoe.py
│   ├── run_all.py          # sequential runner for the 3 steps above
│   ├── generate_jingjiang.py   # experimental GDAL-grid IDW variant
│   └── step2_rem.py        # thin RiverREM wrapper
├── data/                   # DEM input tiles (user-provided); created automatically
└── output/                 # generated REM + PNG/TIF; created automatically
```

## Common gotchas

- **Missing GDAL** → `gdalwarp` not found errors in Step 1. Fix at OS level; `pip` cannot install GDAL binaries.
- **OSM empty result** → network block or bbox mismatch. Check `api.openstreetmap.org` reachability; verify DEM and river line overlap in QGIS if debugging.
- **OOM during IDW** → reduce `IDW_BLOCK_SIZE` in `config.py` (e.g., 1024 or 512), or switch to `USE_TIGHT_BBOX = True`.
- **Wrong DEM files** → ensure tiles cover the Yangtze Jingjiang reach, not another basin. `02_make_rem.py` will error with “有效采样点太少” if the river line and DEM do not overlap.
- **Do not commit** large rasters or PNG outputs. `data/` and `output/` are already gitignored.

## Conventions

- Scripts are **numbered** (`01_`, `02_`, `03_`) and intended to run in order. `run_all.py` enforces this.
- All file paths resolve relative to repo root via `config.py` `BASE_DIR`.
- UTM 49N (EPSG:32649) is hard-coded as the working CRS because it gives true-meter distances for the Jingjiang reach.
