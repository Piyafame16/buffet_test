import datetime
import numpy as np
import pandas as pd

# ─────────────────────────────────────────────
# 1. CONSTANTS
# ─────────────────────────────────────────────

# Sheet name → (ISO date, weekday label, weekday type)
SHEET_META = {
    "133": ("2026-01-03", "Sat 3 Jan",  "Weekend"),
    "143": ("2026-01-04", "Sun 4 Jan",  "Weekend"),
    "153": ("2026-01-05", "Mon 5 Jan",  "Weekday"),
    "173": ("2026-01-07", "Wed 7 Jan",  "Weekday"),
    "183": ("2026-01-08", "Thu 8 Jan",  "Weekday"),
}

INDOOR_TABLES   = {"1A","1B","2A","2B","3A","3B","4A","4B","5A","5B","6A","6B"}
OUTDOOR_SPLIT   = {"7A","7B","7C","8A","8B","8C","9A","9B","9C","10A","10B","11A","11B"}
OUTDOOR_FULL    = {"12","13","14","15","16"}
QUEUE_AREA      = {"99"}
TABLE_ZONE_MAP  = (
    {t: "Indoor"     for t in INDOOR_TABLES}
  | {t: "Outdoor"    for t in OUTDOOR_SPLIT | OUTDOOR_FULL}
  | {t: "Queue Area" for t in QUEUE_AREA}
)


# ─────────────────────────────────────────────
# 2. HELPERS
# ─────────────────────────────────────────────

def _time_to_minutes(val) -> float:
    """
    datetime.time → float minutes since midnight.
    Returns np.nan for NaN / None / unparseable values.
    """
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return np.nan
    if isinstance(val, datetime.time):
        return val.hour * 60 + val.minute + val.second / 60
    # String fallback (e.g. "08:30:00")
    try:
        t = datetime.time.fromisoformat(str(val))
        return t.hour * 60 + t.minute + t.second / 60
    except Exception:
        return np.nan


def expand_table(raw_table) -> list[str]:
    """
    Parse raw table_no. values into a list of unit table IDs.

    Examples:
        "13-14"  → ["13", "14"]
        "1A-1B"  → ["1A", "1B"]
        "7A"     → ["7A"]
        6        → ["6"]
    """
    s = str(raw_table).strip()
    if "-" in s:
        return [p.strip() for p in s.split("-")]
    return [s]


def _classify_zone(unit_table: str) -> str:
    return TABLE_ZONE_MAP.get(unit_table.strip(), "Unknown")


def _primary_zone(raw_table) -> str:
    """Zone of the first (or only) table unit in a booking."""
    units = expand_table(raw_table)
    return _classify_zone(units[0])


# ─────────────────────────────────────────────
# 3. LOAD & CLEAN
# ─────────────────────────────────────────────

def load_clean_data(path: str) -> pd.DataFrame:
    """
    Read all sheets, unify, clean, and engineer features.

    Parameters
    ----------
    path : str
        Path to the Excel workbook.

    Returns
    -------
    pd.DataFrame
        One row per service group with all derived columns.
    """
    xl = pd.ExcelFile(path)

    frames = []
    for sheet, (date_str, day_label, day_type) in SHEET_META.items():
        raw = xl.parse(sheet)

        # Keep only the 8 core columns (sheet 183 has extra junk columns)
        core_cols = [
            "service_no.", "pax", "queue_start", "queue_end",
            "table_no.", "meal_start", "meal_end", "Guest_type",
        ]
        raw = raw[core_cols].copy()

        # Attach date metadata
        raw["date"]     = pd.to_datetime(date_str)
        raw["day_label"]= day_label
        raw["day_type"] = day_type          # "Weekend" / "Weekday"
        raw["sheet"]    = sheet

        frames.append(raw)

    df = pd.concat(frames, ignore_index=True)

    # ── 3a. Standardise text columns ───────────────────────────────
    df["Guest_type"] = (
        df["Guest_type"]
        .astype(str)
        .str.strip()
        .str.title()           # "Walk In" / "In House"
    )
    df["table_no."] = df["table_no."].astype(str).str.strip()

    # ── 3b. Convert times → float minutes since midnight ──────────
    time_cols = ["queue_start", "queue_end", "meal_start", "meal_end"]
    for col in time_cols:
        df[f"{col}_min"] = df[col].apply(_time_to_minutes)

    # ── 3c. Derived durations (minutes) ───────────────────────────
    df["wait_time_min"] = df["queue_end_min"] - df["queue_start_min"]
    df["meal_dur_min"]  = df["meal_end_min"]  - df["meal_start_min"]

    # ── 3d. Boolean flags ─────────────────────────────────────────
    df["has_queue"]          = df["queue_start_min"].notna()
    df["has_meal"]           = df["meal_start_min"].notna()
    df["is_walkaway"]        = df["has_queue"] & ~df["has_meal"]
    df["is_direct_seating"]  = ~df["has_queue"] & df["has_meal"]
    df["is_waited_seated"]   = df["has_queue"]  & df["has_meal"]

    # ── 3e. Table zone ────────────────────────────────────────────
    df["table_zone"] = df["table_no."].apply(
        lambda x: _primary_zone(x) if x not in ("nan", "NaN", "") else "Unknown"
    )

    # ── 3f. Sanity / data quality flags ──────────────────────────
    df["has_data"]     = df["has_meal"] | df["has_queue"]   # at least one time exists
    df["negative_dur"] = df["meal_dur_min"] < 0             # data entry error
    df["long_stay"]    = df["meal_dur_min"] > 300           # > 5 hours (flag outlier)

    return df


# ─────────────────────────────────────────────
# 4. METRIC CALCULATORS
# ─────────────────────────────────────────────

def compute_metrics(df: pd.DataFrame) -> dict:
    """
    Compute all analysis metrics grouped by task.

    Returns
    -------
    dict with keys:
        "summary"          – overall KPIs
        "wait_by_guest"    – wait time stats by Guest_type
        "walkaway_by_day"  – walk-away counts by day × guest type
        "walkaway_detail"  – walk-away rows with wait detail
        "meal_dur_by_guest"– meal duration stats by Guest_type
        "volume_by_day"    – daily traffic (groups + pax)
        "hourly_occupancy" – table occupancy by hour × day
        "occupancy_heatmap"– pivot: hour × day_label (pax count)
        "action_seating_cap" – % of groups that exceed X-minute thresholds
        "price_walkaway"   – weekend vs weekday walk-away rate (for pricing action)
    """
    seated = df[df["has_meal"] & ~df["negative_dur"]].copy()
    queued = df[df["has_queue"]].copy()

    metrics = {}

    # ── 4a. SUMMARY KPIs ─────────────────────────────────────────
    metrics["summary"] = pd.DataFrame([{
        "total_groups"          : len(df),
        "total_pax"             : df["pax"].sum(),
        "groups_with_queue"     : df["has_queue"].sum(),
        "groups_direct_seated"  : df["is_direct_seating"].sum(),
        "total_walkaways"       : df["is_walkaway"].sum(),
        "walkaway_pct"          : round(df["is_walkaway"].mean() * 100, 1),
        "avg_wait_min"          : round(queued["wait_time_min"].mean(), 1),
        "median_wait_min"       : round(queued["wait_time_min"].median(), 1),
        "avg_meal_dur_min"      : round(seated["meal_dur_min"].mean(), 1),
        "median_meal_dur_min"   : round(seated["meal_dur_min"].median(), 1),
    }])

    # ── 4b. WAIT TIME BY GUEST TYPE ───────────────────────────────
    # Comment 1: "In-house guests have to wait"
    metrics["wait_by_guest"] = (
        queued
        .groupby("Guest_type")["wait_time_min"]
        .agg(
            count="count",
            mean="mean",
            median="median",
            std="std",
            p25=lambda x: x.quantile(0.25),
            p75=lambda x: x.quantile(0.75),
            max="max",
        )
        .round(1)
        .reset_index()
    )

    # ── 4c. WALK-AWAY BY DAY × GUEST TYPE ────────────────────────
    wa = df[df["is_walkaway"]].copy()
    walkaway_pivot = (
        wa.groupby(["day_label", "Guest_type"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    walkaway_pivot["total"] = walkaway_pivot.select_dtypes("number").sum(axis=1)

    # Walk-away rate (walkaways / all queued groups that day)
    queued_by_day = queued.groupby("day_label").size().rename("queued_groups")
    walkaway_by_day = wa.groupby("day_label").size().rename("walkaways")
    walkaway_rate = pd.concat([queued_by_day, walkaway_by_day], axis=1).fillna(0)
    walkaway_rate["walkaway_rate_pct"] = (
        (walkaway_rate["walkaways"] / walkaway_rate["queued_groups"] * 100)
        .round(1)
    )

    metrics["walkaway_by_day"]   = walkaway_pivot
    metrics["walkaway_rate"]     = walkaway_rate.reset_index()
    metrics["walkaway_detail"]   = wa[
        ["service_no.", "pax", "date", "day_label", "Guest_type",
         "queue_start_min", "queue_end_min", "wait_time_min"]
    ].copy()

    # ── 4d. MEAL DURATION BY GUEST TYPE ──────────────────────────
    # Comment 3: "Walk-in customers sit the whole day"
    metrics["meal_dur_by_guest"] = (
        seated
        .groupby("Guest_type")["meal_dur_min"]
        .agg(
            count="count",
            mean="mean",
            median="median",
            std="std",
            p25=lambda x: x.quantile(0.25),
            p75=lambda x: x.quantile(0.75),
            max="max",
        )
        .round(1)
        .reset_index()
    )

    # Distribution buckets for histogram
    bins   = [0, 30, 60, 90, 120, 150, 180, 300, 999]
    labels = ["<30","30-60","60-90","90-120","120-150","150-180","180-300",">300"]
    seated["dur_bucket"] = pd.cut(seated["meal_dur_min"], bins=bins, labels=labels, right=False)
    metrics["meal_dur_dist"] = (
        seated.groupby(["Guest_type", "dur_bucket"], observed=True)
        .size()
        .reset_index(name="count")
    )

    # ── 4e. DAILY VOLUME ─────────────────────────────────────────
    # Comment 2: "Busy every day"
    metrics["volume_by_day"] = (
        df.groupby(["day_label", "day_type"])
        .agg(
            groups=("service_no.", "count"),
            pax=("pax", "sum"),
            walkaways=("is_walkaway", "sum"),
            queued_groups=("has_queue", "sum"),
        )
        .reset_index()
        .sort_values("day_label")
    )

    # ── 4f. HOURLY TRAFFIC (arrival wave) ─────────────────────────
    # Build arrival counts per hour using meal_start_min
    seated2 = seated.copy()
    seated2["hour"] = (seated2["meal_start_min"] // 60).astype(int)
    hourly = (
        seated2.groupby(["day_label", "hour"])
        .agg(groups=("service_no.", "count"), pax=("pax", "sum"))
        .reset_index()
    )
    metrics["hourly_traffic"] = hourly

    # Heatmap pivot: rows=hour, cols=day_label
    metrics["occupancy_heatmap"] = (
        hourly.pivot_table(index="hour", columns="day_label", values="pax", fill_value=0)
    )

    # ── 4g. OCCUPANCY TIMELINE (for Gantt / table-fill analysis) ──
    # One row per (group, unit_table) so combined tables explode to 2 rows
    timeline_rows = []
    for _, row in seated.iterrows():
        units = expand_table(row["table_no."])
        for unit in units:
            timeline_rows.append({
                "date"          : row["date"],
                "day_label"     : row["day_label"],
                "service_no."   : row["service_no."],
                "Guest_type"    : row["Guest_type"],
                "table_unit"    : unit,
                "zone"          : _classify_zone(unit),
                "meal_start_min": row["meal_start_min"],
                "meal_end_min"  : row["meal_end_min"],
                "meal_dur_min"  : row["meal_dur_min"],
                "pax"           : row["pax"],
            })
    metrics["occupancy_timeline"] = pd.DataFrame(timeline_rows)

    # ── 4h. ACTION 1: Seating cap analysis ───────────────────────
    # "What fraction of Walk-in groups exceed 90 / 120 / 150 minutes?"
    walkin_seated = seated[seated["Guest_type"] == "Walk In"].copy()
    thresholds = [60, 90, 120, 150, 180]
    cap_rows = []
    for thresh in thresholds:
        over  = (walkin_seated["meal_dur_min"] >= thresh).sum()
        total = len(walkin_seated)
        cap_rows.append({
            "cap_minutes"    : thresh,
            "groups_over_cap": int(over),
            "total_walkin"   : int(total),
            "pct_over_cap"   : round(over / total * 100, 1) if total else 0,
        })
    metrics["action_seating_cap"] = pd.DataFrame(cap_rows)

    # ── 4i. ACTION 2: Price / weekday analysis ────────────────────
    # "Would raising prices reduce weekend vs weekday demand equally?"
    metrics["volume_by_daytype"] = (
        df.groupby("day_type")
        .agg(
            groups=("service_no.", "count"),
            pax=("pax", "sum"),
            walkaways=("is_walkaway", "sum"),
            avg_wait=("wait_time_min", "mean"),
        )
        .round(1)
        .reset_index()
    )

    # ── 4j. ACTION 3: In-house queue skip analysis ────────────────
    # "How much do In-house guests actually wait vs walk-ins?"
    metrics["inhouse_queue_detail"] = queued[
        ["service_no.", "pax", "day_label", "Guest_type",
         "wait_time_min", "is_walkaway", "meal_dur_min"]
    ].sort_values("wait_time_min", ascending=False)

    return metrics


# ─────────────────────────────────────────────
# 5. QUICK SANITY CHECK  (run as script)
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys, os

    # Accept path as CLI arg, else look for file in current dir
    DEFAULT = "2026_Data_Test1_Final_-_Busy_Buffet_Dataset__1_.xlsx"
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT

    if not os.path.exists(path):
        print(f"[ERROR] File not found: {path}")
        sys.exit(1)

    print("Loading data …")
    df = load_clean_data(path)
    print(f"  Rows: {len(df)} | Cols: {len(df.columns)}")
    print(f"  Sheets: {df['sheet'].unique().tolist()}")
    print(f"  Guest types: {df['Guest_type'].unique().tolist()}")
    print(f"  Walk-aways: {df['is_walkaway'].sum()} total")
    print()

    print("Computing metrics …")
    mets = compute_metrics(df)

    print("\n── SUMMARY ─────────────────────────────────────────")
    print(mets["summary"].T.to_string(header=False))

    print("\n── WAIT TIME BY GUEST TYPE ─────────────────────────")
    print(mets["wait_by_guest"].to_string(index=False))

    print("\n── WALK-AWAYS BY DAY ───────────────────────────────")
    print(mets["walkaway_by_day"].to_string(index=False))

    print("\n── WALK-AWAY RATE ──────────────────────────────────")
    print(mets["walkaway_rate"].to_string(index=False))

    print("\n── MEAL DURATION BY GUEST TYPE ─────────────────────")
    print(mets["meal_dur_by_guest"].to_string(index=False))

    print("\n── DAILY VOLUME ─────────────────────────────────────")
    print(mets["volume_by_day"].to_string(index=False))

    print("\n── SEATING CAP IMPACT (Action 1) ───────────────────")
    print(mets["action_seating_cap"].to_string(index=False))

    print("\n── WEEKDAY vs WEEKEND (Action 2) ───────────────────")
    print(mets["volume_by_daytype"].to_string(index=False))

    print("\nDone ✓")