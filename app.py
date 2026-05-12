"""
app.py  –  Busy Buffet Dashboard
Hotel Amber 85 | Atmind Data Analytics Test 2026

Run locally:
    streamlit run app.py

The Excel file is bundled in data/dataset.xlsx  (or upload via sidebar).
"""

import datetime
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from buffet_data import (
    load_clean_data,
    compute_metrics,
    SHEET_META,
    expand_table,
    INDOOR_TABLES,
    OUTDOOR_SPLIT,
    OUTDOOR_FULL,
)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Busy Buffet – Hotel Amber 85",
    page_icon="🍽️",
    layout="wide",
)

COLORS = {
    "In House": "#4C72B0",
    "Walk In":  "#DD8452",
    "Weekend":  "#55A868",
    "Weekday":  "#C44E52",
}
DAY_ORDER = [v[1] for v in SHEET_META.values()]
TOTAL_TABLES = len(INDOOR_TABLES) + len(OUTDOOR_SPLIT) + len(OUTDOOR_FULL)

# ─────────────────────────────────────────────
# DATA LOADER  (cached)
# ─────────────────────────────────────────────
DATA_PATH = "data/dataset.xlsx"

@st.cache_data
def get_data(path: str):
    df   = load_clean_data(path)
    mets = compute_metrics(df)
    return df, mets


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.title("🍽️ Busy Buffet")
    st.caption("Hotel Amber 85 | Jan 2026")
    st.divider()
    st.divider()
    section = st.radio(
        "Navigate",
        [
            "📌 Overview",
            "💬 Task 1 – Staff Comments",
            "🚫 Task 2 – Why Actions Fail",
            "⭐ Task 3 – Recommended Solution",
        ],
    )

# ─────────────────────────────────────────────
# LOAD
# ─────────────────────────────────────────────
try:
    df, mets = get_data(load_path)
except FileNotFoundError:
    st.error(
        "Dataset not found. Please upload the Excel file using the sidebar, "
        "or place it at `data/dataset.xlsx`."
    )
    st.stop()

seated = df[df["has_meal"] & (df["meal_dur_min"] >= 0)].copy()
queued = df[df["has_queue"]].copy()
seated["hour"] = (seated["meal_start_min"] // 60).astype(int)


# ═════════════════════════════════════════════
# SECTION: OVERVIEW
# ═════════════════════════════════════════════
if section == "📌 Overview":
    st.title("📌 Overview – Busy Buffet")
    st.markdown(
        "Hotel Amber 85 ran a TikTok promotion (**All-you-can-eat · ฿159 weekday / ฿199 weekend · 5-hour seating**) "
        "that caused a sudden surge in walk-in guests. This dashboard analyses 5 days of data to understand the problems "
        "and evaluate proposed solutions."
    )

    # KPI row
    wa   = mets["summary"]["total_walkaways"].iloc[0]
    pax  = int(mets["summary"]["total_pax"].iloc[0])
    grp  = int(mets["summary"]["total_groups"].iloc[0])
    awit = mets["summary"]["avg_wait_min"].iloc[0]
    ameal= mets["summary"]["avg_meal_dur_min"].iloc[0]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Groups (5 days)", grp)
    c2.metric("Total Pax",             pax)
    c3.metric("Walk-aways",            int(wa), delta=f"{mets['summary']['walkaway_pct'].iloc[0]}%", delta_color="inverse")
    c4.metric("Avg Wait Time",         f"{awit:.0f} min")
    c5.metric("Avg Meal Duration",     f"{ameal:.0f} min")

    st.divider()

    # Daily volume
    vol = mets["volume_by_day"].sort_values("day_label")
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=vol["day_label"], y=vol["groups"],
        name="Groups",
        marker_color=[COLORS["Weekend"] if t == "Weekend" else COLORS["Weekday"] for t in vol["day_type"]],
        opacity=0.75,
    ))
    fig.add_trace(go.Scatter(
        x=vol["day_label"], y=vol["pax"],
        name="Total Pax", mode="lines+markers+text",
        text=vol["pax"].astype(int), textposition="top center",
        line=dict(color="#222", width=2), marker=dict(size=8),
    ), secondary_y=True)
    fig.update_layout(
        title="Daily Volume – Groups & Pax",
        xaxis=dict(categoryorder="array", categoryarray=DAY_ORDER),
        height=380, legend=dict(orientation="h", y=1.12),
    )
    fig.update_yaxes(title_text="Groups", secondary_y=False)
    fig.update_yaxes(title_text="Total Pax", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True)

    # Heatmap
    heat = mets["occupancy_heatmap"]
    col_order = [c for c in DAY_ORDER if c in heat.columns]
    heat = heat[col_order]
    fig2 = px.imshow(
        heat, aspect="auto", color_continuous_scale="YlOrRd",
        title="Hourly Pax Heatmap (how busy each hour is per day)",
        labels={"x": "Day", "y": "Hour", "color": "Pax"},
    )
    fig2.update_yaxes(
        tickvals=list(range(6, 13)),
        ticktext=[f"{h:02d}:00" for h in range(6, 13)],
    )
    fig2.update_layout(height=360)
    st.plotly_chart(fig2, use_container_width=True)


# ═════════════════════════════════════════════
# SECTION: TASK 1
# ═════════════════════════════════════════════
elif section == "💬 Task 1 – Staff Comments":
    st.title("💬 Task 1 – Proving Staff Comments")

    tab1, tab2, tab3 = st.tabs([
        "Comment 1 – In-house wait & walk-aways",
        "Comment 2 – Busy every day",
        "Comment 3 – Walk-in sit all day",
    ])

    # ── Comment 1 ────────────────────────────────────────────────
    with tab1:
        st.subheader("\"In-house guests wait for tables. Walk-in guests queue then leave.\"")

        col_a, col_b = st.columns(2)

        with col_a:
            fig = px.box(
                queued.dropna(subset=["wait_time_min"]),
                x="Guest_type", y="wait_time_min", color="Guest_type",
                color_discrete_map=COLORS, points="all", notched=True,
                title="Wait Time by Guest Type",
                labels={"wait_time_min": "Wait Time (min)", "Guest_type": ""},
            )
            fig.update_layout(showlegend=False, height=400)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(mets["wait_by_guest"], use_container_width=True, hide_index=True)

        with col_b:
            wa_df = df[df["is_walkaway"]].copy()
            wa_day = (
                wa_df.groupby(["day_label", "Guest_type"])
                .size().reset_index(name="count")
            )
            fig2 = px.bar(
                wa_day, x="day_label", y="count", color="Guest_type",
                color_discrete_map=COLORS, barmode="group",
                title="Walk-aways by Day & Guest Type",
                labels={"day_label": "Day", "count": "Walk-aways"},
                category_orders={"day_label": DAY_ORDER},
            )
            fig2.update_layout(height=400)
            st.plotly_chart(fig2, use_container_width=True)

            # walk-away rate
            rate = mets["walkaway_rate"].copy()
            fig3 = px.bar(
                rate, x="day_label", y="walkaway_rate_pct",
                text="walkaway_rate_pct",
                title="Walk-away Rate (% of queued groups that left)",
                color="walkaway_rate_pct", color_continuous_scale="Reds",
                category_orders={"day_label": DAY_ORDER},
            )
            fig3.update_traces(texttemplate="%{text}%", textposition="outside")
            fig3.update_layout(height=350, showlegend=False)
            st.plotly_chart(fig3, use_container_width=True)

        st.info(
            "✅ **Confirmed.** Walk-in guests wait ~38 min on average vs ~28 min for In-house. "
            "On Monday 5 Jan, **24% of queued groups walked away** without eating."
        )

    # ── Comment 2 ────────────────────────────────────────────────
    with tab2:
        st.subheader("\"We are very busy every day. This buffet is impossible to sustain.\"")

        vol = mets["volume_by_day"].sort_values("day_label")
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(
            x=vol["day_label"], y=vol["groups"],
            name="Groups",
            marker_color=[COLORS["Weekend"] if t == "Weekend" else COLORS["Weekday"] for t in vol["day_type"]],
        ))
        fig.add_trace(go.Scatter(
            x=vol["day_label"], y=vol["pax"],
            name="Pax", mode="lines+markers+text",
            text=vol["pax"].astype(int), textposition="top center",
            line=dict(color="#222", width=2),
        ), secondary_y=True)
        fig.update_layout(
            title="Daily Traffic – Groups & Pax",
            xaxis=dict(categoryorder="array", categoryarray=DAY_ORDER),
            height=400, legend=dict(orientation="h"),
        )
        st.plotly_chart(fig, use_container_width=True)

        heat = mets["occupancy_heatmap"]
        col_order = [c for c in DAY_ORDER if c in heat.columns]
        heat = heat[col_order]
        fig2 = px.imshow(
            heat, aspect="auto", color_continuous_scale="YlOrRd",
            title="Hourly Pax Heatmap",
            labels={"x": "Day", "y": "Hour", "color": "Pax"},
        )
        fig2.update_yaxes(tickvals=list(range(6,13)), ticktext=[f"{h:02d}:00" for h in range(6,13)])
        fig2.update_layout(height=350)
        st.plotly_chart(fig2, use_container_width=True)

        st.info(
            "✅ **Confirmed.** All 5 days show 57–86 groups. Peak hour 07:00–09:00 is consistently packed. "
            "However the problem is **not volume itself** — it's that long dwell times reduce table turnover."
        )

    # ── Comment 3 ────────────────────────────────────────────────
    with tab3:
        st.subheader("\"Walk-in customers sit the whole day. We can't find seats for in-house guests.\"")

        col_a, col_b = st.columns(2)

        with col_a:
            fig = px.box(
                seated, x="Guest_type", y="meal_dur_min", color="Guest_type",
                color_discrete_map=COLORS, points="all", notched=True,
                title="Meal Duration by Guest Type",
                labels={"meal_dur_min": "Meal Duration (min)", "Guest_type": ""},
            )
            fig.add_hline(y=90,  line_dash="dash", line_color="red",    annotation_text="90 min")
            fig.add_hline(y=120, line_dash="dot",  line_color="orange",  annotation_text="120 min")
            fig.update_layout(showlegend=False, height=420)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(mets["meal_dur_by_guest"], use_container_width=True, hide_index=True)

        with col_b:
            bins   = [0, 30, 60, 90, 120, 150, 180, 999]
            labels = ["<30","30-60","60-90","90-120","120-150","150-180","180+"]
            seated2 = seated.copy()
            seated2["dur_bucket"] = pd.cut(seated2["meal_dur_min"], bins=bins, labels=labels, right=False)
            dist = seated2.groupby(["Guest_type","dur_bucket"], observed=True).size().reset_index(name="count")
            fig2 = px.bar(
                dist, x="dur_bucket", y="count", color="Guest_type",
                color_discrete_map=COLORS, barmode="group",
                title="Meal Duration Distribution",
                labels={"dur_bucket":"Duration","count":"Groups"},
                category_orders={"dur_bucket": labels},
            )
            fig2.update_layout(height=420)
            st.plotly_chart(fig2, use_container_width=True)

        # Gantt
        st.markdown("#### Table Occupancy Timeline (select day)")
        sel_day = st.selectbox("Day", DAY_ORDER, key="gantt_day")
        BASE = pd.Timestamp("2026-01-01")
        tl = mets["occupancy_timeline"]
        sub = tl[tl["day_label"] == sel_day].copy()
        sub["Start"] = BASE + pd.to_timedelta(sub["meal_start_min"], unit="m")
        sub["End"]   = BASE + pd.to_timedelta(sub["meal_end_min"],   unit="m")
        sub = sub.sort_values("table_unit")
        fig3 = px.timeline(
            sub, x_start="Start", x_end="End", y="table_unit",
            color="Guest_type", color_discrete_map=COLORS,
            title=f"Table Occupancy – {sel_day}",
            labels={"Guest_type":"Guest Type","table_unit":"Table"},
        )
        fig3.update_xaxes(tickformat="%H:%M")
        fig3.update_layout(height=520)
        st.plotly_chart(fig3, use_container_width=True)

        st.info(
            "✅ **Confirmed.** Walk-in median meal duration = **66 min** vs In-house = **39 min**. "
            "Walk-in guests stay 70% longer on average, directly reducing table turnover."
        )


# ═════════════════════════════════════════════
# SECTION: TASK 2
# ═════════════════════════════════════════════
elif section == "🚫 Task 2 – Why Actions Fail":
    st.title("🚫 Task 2 – Why Each Proposed Action Won't Work")

    tab1, tab2, tab3 = st.tabs([
        "Action 1 – Reduce Seating Time",
        "Action 2 – Raise Price to ฿259",
        "Action 3 – Queue Skip for In-house",
    ])

    # ── Action 1 ─────────────────────────────────────────────────
    with tab1:
        st.subheader("Action 1: Reduce seating time (5h → less)")
        st.markdown(
            "**Why it seems logical:** Walk-in guests sit too long → cap their time.  \n"
            "**Why it won't work alone:** Most guests already leave well within any reasonable cap."
        )

        walkin = seated[seated["Guest_type"] == "Walk In"].copy()
        walkin_sorted = walkin["meal_dur_min"].dropna().sort_values()
        cdf_y = np.arange(1, len(walkin_sorted)+1) / len(walkin_sorted) * 100

        col_a, col_b = st.columns(2)

        with col_a:
            cap_df = mets["action_seating_cap"]
            fig = px.bar(
                cap_df, x="cap_minutes", y="pct_over_cap",
                text="pct_over_cap",
                title="% of Walk-in Groups Affected by Each Cap",
                labels={"cap_minutes": "Cap (minutes)", "pct_over_cap": "% Affected"},
                color="pct_over_cap", color_continuous_scale="Blues",
            )
            fig.update_traces(texttemplate="%{text}%", textposition="outside")
            fig.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=walkin_sorted, y=cdf_y, mode="lines",
                line=dict(color=COLORS["Walk In"], width=2.5),
                name="Walk-in CDF",
            ))
            for cap, color, label in [(90,"red","90 min"),(120,"orange","120 min"),(150,"green","150 min")]:
                pct = (walkin["meal_dur_min"] < cap).mean() * 100
                fig2.add_vline(x=cap, line_dash="dash", line_color=color,
                               annotation_text=f"{label} ({pct:.0f}% already left)")
            fig2.update_layout(
                title="Cumulative % of Walk-in Guests Who Have Left",
                xaxis_title="Minutes Since Seated",
                yaxis_title="Cumulative % Departed",
                height=400,
            )
            st.plotly_chart(fig2, use_container_width=True)

        st.dataframe(cap_df, use_container_width=True, hide_index=True)
        st.warning(
            "🚫 **At a 90-min cap:** only 27.6% of Walk-in guests would be affected — "
            "72% already leave on their own. The cap adds friction and bad customer experience "
            "without meaningfully increasing table turnover."
        )

    # ── Action 2 ─────────────────────────────────────────────────
    with tab2:
        st.subheader("Action 2: Raise price to ฿259 every day")
        st.markdown(
            "**Why it seems logical:** Higher price → fewer customers → less crowding.  \n"
            "**Why it won't work:** Customers who queue 30–40+ minutes are already price-insensitive."
        )

        col_a, col_b = st.columns(2)

        with col_a:
            daytype = mets["volume_by_daytype"]
            fig = make_subplots(rows=1, cols=2, subplot_titles=["Total Groups","Total Pax"])
            for i, col in enumerate(["groups","pax"]):
                fig.add_trace(go.Bar(
                    x=daytype["day_type"], y=daytype[col],
                    marker_color=[COLORS["Weekend"], COLORS["Weekday"]],
                    text=daytype[col].astype(int), textposition="outside",
                    showlegend=False,
                ), row=1, col=i+1)
            fig.update_layout(title="Weekday vs Weekend Volume", height=380)
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            wa = df[df["is_walkaway"]].copy()
            fig2 = px.histogram(
                wa.dropna(subset=["wait_time_min"]),
                x="wait_time_min", color="Guest_type",
                color_discrete_map=COLORS, nbins=12,
                barmode="overlay", opacity=0.75,
                title="How Long Walk-aways Waited Before Leaving",
                labels={"wait_time_min": "Wait Time (min)"},
            )
            fig2.update_layout(height=380)
            st.plotly_chart(fig2, use_container_width=True)

        # FIX: volume_by_day already has 'walkaways' from compute_metrics — no re-merge needed
        merged = mets["volume_by_day"].sort_values("day_label").copy()
        merged["walkaways"] = merged["walkaways"].fillna(0)
        merged["walkaway_pct"] = (merged["walkaways"] / merged["groups"] * 100).round(1)

        fig3 = px.scatter(
            merged, x="pax", y="walkaways",
            text="day_label", size=merged["walkaways"].clip(lower=1),
            color="day_type", color_discrete_map=COLORS,
            title="Walk-aways vs Total Pax per Day",
            labels={"pax": "Total Pax (demand)", "walkaways": "Walk-aways (capacity signal)"},
        )
        fig3.update_traces(textposition="top center")
        fig3.update_layout(height=380)
        st.plotly_chart(fig3, use_container_width=True)

        st.warning(
            "🚫 **Walk-aways only occur when the place is completely full (Mon = peak day). "
            "Customers waited 30–60+ min before giving up — they wanted to eat here. "
            "Raising price punishes loyal customers and may destroy revenue without fixing the capacity problem.**"
        )

    # ── Action 3 ─────────────────────────────────────────────────
    with tab3:
        st.subheader("Action 3: Queue skip priority for in-house guests")
        st.markdown(
            "**Why it seems logical:** In-house guests are the hotel's core customers.  \n"
            "**Why it won't work:** Queue-skipping can't create tables that don't exist."
        )

        col_a, col_b = st.columns(2)

        with col_a:
            q_compare = (
                queued.groupby("Guest_type")
                .agg(queued_groups=("service_no.","count"), walkaways=("is_walkaway","sum"),
                     avg_wait=("wait_time_min","mean"))
                .round(1).reset_index()
            )
            fig = px.bar(
                q_compare.melt(id_vars="Guest_type", value_vars=["queued_groups","walkaways"]),
                x="Guest_type", y="value", color="variable", barmode="group",
                title="Queued vs Walk-away Groups by Guest Type",
                labels={"value":"Groups","variable":""},
                color_discrete_sequence=["#4C72B0","#DD8452"],
            )
            fig.update_layout(height=380)
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            mon = seated[seated["day_label"] == "Mon 5 Jan"].copy()
            time_range = list(range(6*60, 12*60+1))
            occ_rows = []
            for t in time_range:
                occ = mon[(mon["meal_start_min"] <= t) & (mon["meal_end_min"] > t)]
                occ_rows.append({"minute": t, "tables": len(occ), "pax": occ["pax"].sum()})
            occ_df = pd.DataFrame(occ_rows)
            occ_df["time_str"] = occ_df["minute"].apply(lambda m: f"{m//60:02d}:{m%60:02d}")

            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=occ_df["time_str"], y=occ_df["tables"],
                fill="tozeroy", mode="lines",
                line=dict(color="#4C72B0"), name="Tables in use",
            ))
            fig2.add_hline(y=TOTAL_TABLES, line_dash="dash", line_color="red",
                           annotation_text=f"All {TOTAL_TABLES} tables")
            fig2.update_xaxes(
                tickvals=[f"{h:02d}:{m:02d}" for h in range(6,13) for m in [0,30]],
                tickangle=45,
            )
            fig2.update_layout(
                title="Table Occupancy – Mon 5 Jan (Peak Day)",
                xaxis_title="Time", yaxis_title="Tables Occupied",
                height=380,
            )
            st.plotly_chart(fig2, use_container_width=True)

        st.warning(
            f"🚫 **On peak day (Mon 5 Jan), nearly all {TOTAL_TABLES} tables are full from 08:00–10:30. "
            "Queue-skipping just changes *who* waits, not *how long* the wait is. "
            "In-house guests would still be stuck behind a full restaurant.**"
        )


# ═════════════════════════════════════════════
# SECTION: TASK 3
# ═════════════════════════════════════════════
elif section == "⭐ Task 3 – Recommended Solution":
    st.title("⭐ Task 3 – Recommended Solution")

    st.markdown("""
    ### Chosen Action: Action 1 (Modified) — **90-Minute Seating Limit with Transparent Communication**

    Rather than a rigid enforcement of a cap, the recommended approach combines:
    1. **Clearly communicate a 90-minute seating window at time of booking / queue entry**
    2. **Offer a discounted second-round ticket (฿99) for guests who want to stay longer**
    3. **Reserve 2–3 tables as "In-house Fast Track"** for hotel guests (separate from Walk-in queue)

    This addresses the root cause — **table turnover** — without punishing loyal customers or destroying revenue.
    """)

    st.divider()

    # ── Impact simulation ────────────────────────────────────────
    walkin = seated[seated["Guest_type"] == "Walk In"].copy()
    walkin_over90 = walkin[walkin["meal_dur_min"] >= 90].copy()
    walkin_over90 = walkin_over90.copy()
    walkin_over90["freed_min"] = walkin_over90["meal_dur_min"] - 90
    freed_total    = walkin_over90["freed_min"].sum()
    median_meal    = walkin["meal_dur_min"].median()
    extra_seatings = freed_total / median_meal if median_meal else 0

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Walk-in groups sitting >90 min", f"{len(walkin_over90)} / {len(walkin)}", "27.6%")
    col_b.metric("Table-minutes freed (5 days)",   f"{freed_total:.0f} min")
    col_c.metric("Extra groups that could be seated (est.)", f"~{extra_seatings:.0f}")

    st.divider()
    col_a2, col_b2 = st.columns(2)

    with col_a2:
        fig = px.scatter(
            walkin_over90, x="meal_dur_min", y="freed_min",
            color="day_label", size="pax", size_max=18,
            title="Minutes Freed per Walk-in Group (if capped at 90 min)",
            labels={"meal_dur_min": "Actual Duration (min)", "freed_min": "Minutes Freed"},
        )
        fig.add_vline(x=90, line_dash="dash", line_color="red", annotation_text="90-min cap")
        fig.update_layout(height=420)
        st.plotly_chart(fig, use_container_width=True)

    with col_b2:
        total_wa   = int(df["is_walkaway"].sum())
        projected  = max(0, total_wa - int(extra_seatings))
        fig2 = go.Figure(go.Bar(
            x=["Before (actual)", "After (projected)"],
            y=[total_wa, projected],
            marker_color=["#C44E52", "#55A868"],
            text=[total_wa, projected], textposition="outside",
        ))
        fig2.update_layout(
            title="Walk-away Groups: Before vs After 90-min Cap",
            yaxis_title="Walk-away Groups",
            height=420,
        )
        st.plotly_chart(fig2, use_container_width=True)

    # CDF context
    walkin_sorted = walkin["meal_dur_min"].dropna().sort_values()
    cdf_y = np.arange(1, len(walkin_sorted)+1) / len(walkin_sorted) * 100
    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(
        x=walkin_sorted, y=cdf_y, mode="lines",
        line=dict(color=COLORS["Walk In"], width=2.5), name="Walk-in actual",
    ))
    fig3.add_vrect(x0=0, x1=90, fillcolor="green", opacity=0.07, layer="below",
                   annotation_text="72% leave naturally")
    fig3.add_vline(x=90, line_dash="dash", line_color="red",
                   annotation_text="90-min cap (72% unaffected)")
    fig3.update_layout(
        title="Walk-in Departure CDF — Most Guests Are Already Unaffected by a 90-min Cap",
        xaxis_title="Minutes Seated", yaxis_title="Cumulative % Departed",
        height=380,
    )
    st.plotly_chart(fig3, use_container_width=True)

    st.divider()
    st.markdown("""
    ### Why This Works — Personal Reasoning

    | Problem | Root Cause | Solution Addresses It? |
    |---|---|---|
    | In-house guests wait | Tables full, low turnover | ✅ Faster turnover = more free tables |
    | Walk-in walk-aways | Queue too long | ✅ More seats available per hour |
    | Staff overwhelmed | Constant full house | ✅ Predictable seat availability |

    **Key insight:** The 72% of Walk-in guests who already leave within 90 minutes are unaffected.
    Only the 28% who overstay need to be managed — and the friendliest way is to **tell them upfront**,
    not enforce it retroactively.

    Coupling this with a **Fast Track zone for In-house guests** (2–3 dedicated tables) ensures
    hotel guests always have a guaranteed path to seating, preserving the hotel's core business
    relationship without turning away walk-in revenue entirely.

    > ⚠️ *Note: The "extra ~25 groups" projection is an estimate based on total table-minutes freed
    > divided by median meal duration. Actual impact depends on timing distribution of freed tables.*
    """)