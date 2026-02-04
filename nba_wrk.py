# nba_wrk.py – ICE PROP LAB • Single Player + Persistent Opponent

import streamlit as st
from nba_api.stats.static import players
from nba_api.stats.endpoints import leaguedashplayerstats, PlayerGameLog
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="ICE PROP LAB", layout="wide", initial_sidebar_state="expanded")

# ── Initialize session state for board ─────────────────────────────────────────
if 'my_board' not in st.session_state:
    st.session_state.my_board = []

# ── Season helpers ──────────────────────────────────────────────────────────────
def get_current_season():
    today = datetime.today()
    if today.month >= 10:
        return f"{today.year}-{str(today.year + 1)[-2:]}"
    else:
        return f"{today.year-1}-{str(today.year)[-2:]}"

CURRENT_SEASON = get_current_season()
current_year = int(CURRENT_SEASON.split('-')[0])
PREVIOUS_SEASON = f"{current_year - 1}-{str(current_year)[-2:]}"

# ── Styling ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main {background: linear-gradient(135deg, #0a1a2f 0%, #001122 100%);}
    h1, h2, h3 {font-family: 'Exo 2', sans-serif; color: #00e0ff !important;
                text-shadow: 0 0 20px #00e0ff, 0 0 40px rgba(0,224,255,0.5);}
    .stButton>button {background: linear-gradient(45deg, #003366, #00aaff) !important;
                      color: white !important; border: 2px solid #00e0ff !important;
                      font-weight: 700; border-radius: 12px; box-shadow: 0 0 25px rgba(0,224,255,0.6);}
    div[data-baseweb="select"] > div {background: rgba(0,224,255,0.08) !important;
                                      border: 1px solid #00aaff !important; color: #00e0ff !important;}
    table {width: 100%; border-collapse: collapse; 
           font-family: 'Exo 2', sans-serif; color: #00e0ff;
           background: rgba(10,30,60,0.7); border: 1px solid #00aaff;
           border-radius: 10px; overflow: hidden;
           box-shadow: 0 0 20px rgba(0,170,255,0.3);}
    th {background: linear-gradient(90deg, #003366, #001122);
        color: #00ffff; padding: 10px; text-align: center;
        font-weight: 700; border-bottom: 2px solid #00e0ff;}
    td {padding: 12px; text-align: left; vertical-align: top;
        border-bottom: 1px solid rgba(0,224,255,0.12);}
</style>
""", unsafe_allow_html=True)

# ── Helpers ─────────────────────────────────────────────────────────────────────
def dropdown_values():
    return [None] + [round(x, 1) for x in np.arange(0.5, 60.6, 1.0)]

def get_player_id(name):
    for p in players.get_players():
        if p['full_name'].lower() == name.lower():
            return p['id']
    return None

@st.cache_data(ttl=7200)
def get_active_players():
    for season in [CURRENT_SEASON, PREVIOUS_SEASON]:
        try:
            df = leaguedashplayerstats.LeagueDashPlayerStats(
                season=season, season_type_all_star="Regular Season").get_data_frames()[0]
            if not df.empty and len(df) > 80:
                return set(df.PLAYER_ID)
        except:
            continue
    return set()

@st.cache_data(ttl=300)
def get_player_games(pid):
    for season in [CURRENT_SEASON, PREVIOUS_SEASON]:
        try:
            gamelog = PlayerGameLog(player_id=str(pid), season=season,
                                   season_type_all_star='Regular Season')
            df = gamelog.get_data_frames()[0]
            if not df.empty:
                df["GAME_DATE_DT"] = pd.to_datetime(df["GAME_DATE"])
                df["GAME_DATE"] = df["GAME_DATE_DT"].dt.strftime("%m/%d")
                df["PLAYER_ID"] = pid
                df = df.sort_values("GAME_DATE_DT", ascending=False).reset_index(drop=True)
                return df
        except:
            continue
    return pd.DataFrame()

# ── Load active players ─────────────────────────────────────────────────────────
active_ids = get_active_players()
player_list = sorted([p["full_name"] for p in players.get_players() if p["id"] in active_ids])

common_teams = sorted(['ATL','BOS','BKN','CHA','CHI','CLE','DAL','DEN','DET','GSW','HOU','IND','LAC','LAL','MEM','MIA','MIL','MIN','NOP','NYK','OKC','ORL','PHI','PHX','POR','SAC','SAS','TOR','UTA','WAS','UNKNOWN'])

if 'next_opponent' not in st.session_state:
    st.session_state.next_opponent = "BOS"

# ── Sidebar ─────────────────────────────────────────────────────────────────────

# Player & Opponent selectors side-by-side
sidebar_cols = st.sidebar.columns([3, 2])

with sidebar_cols[0]:
    selected_player = st.selectbox(
        "Player",
        ["— Choose player —"] + player_list,
        key="sidebar_player_select",
        label_visibility="collapsed"
    )

with sidebar_cols[1]:
    next_opp = st.selectbox(
        "Opponent",
        common_teams,
        index=common_teams.index(st.session_state.next_opponent) if st.session_state.next_opponent in common_teams else 0,
        key="sidebar_opp_select",
        label_visibility="collapsed"
    )

# Auto-set opponent for famous players (optional)
if selected_player != "— Choose player —" and st.session_state.next_opponent == "BOS":
    if "James" in selected_player:
        st.session_state.next_opponent = "LAL"
    elif "Dončić" in selected_player:
        st.session_state.next_opponent = "DAL"
    elif "Jokić" in selected_player:
        st.session_state.next_opponent = "DEN"

if next_opp != st.session_state.next_opponent:
    st.session_state.next_opponent = next_opp

# ── My Board Sidebar Expander ───────────────────────────────────────────────────
with st.sidebar.expander(f"📋 My Board ({len(st.session_state.my_board)})", expanded=len(st.session_state.my_board) > 0):
    if not st.session_state.my_board:
        st.caption("No props saved yet. Pin interesting lines with 📌")
    else:
        for i, item in enumerate(st.session_state.my_board[:]):
            col1, col2 = st.columns([6, 1])
            with col1:
                odds_display = f"   {item['odds']}" if item.get('odds') else ""
                st.markdown(
                    f"<strong>{item['player']}</strong> vs {item['opponent']}<br>"
                    f"<small>{item['stat']} {item['line']}{odds_display}  {item['hitrate_str']}</small><br>"
                    f"<small style='color:#88ccff'>{item['timestamp']}</small>",
                    unsafe_allow_html=True
                )
            with col2:
                if st.button("×", key=f"remove_board_{i}", help="Remove from board"):
                    st.session_state.my_board.pop(i)
                    st.rerun()

        if st.button("🗑️ Clear All", type="primary", use_container_width=True):
            st.session_state.my_board = []
            st.rerun()

# ── Display Settings ────────────────────────────────────────────────────────────
st.sidebar.markdown("### Display Settings")
games_to_show = st.sidebar.selectbox(
    "Recent games to show",
    [5, 10, 15, 20],
    index=2,  # default = 15
    key="games_to_show_select"
)

# Spacer
st.sidebar.markdown("<br>", unsafe_allow_html=True)

# Refresh button (now below the games selector)
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# ────────────────────────────────────────────────────────────────────────────────
# Main content starts here
# ────────────────────────────────────────────────────────────────────────────────

# Early exit if no player selected
if selected_player == "— Choose player —":
    st.info("Select a player to begin.")
    st.stop()

pid = get_player_id(selected_player)
if not pid:
    st.error("Player not found.")
    st.stop()

with st.spinner("Loading game logs..."):
    df = get_player_games(pid)
    if df.empty:
        st.error("No game data found.")
        st.stop()

df["PLAYER_NAME"] = selected_player

# Composite stats
df["Pts+Ast"] = df["PTS"] + df["AST"]
df["Pts+Reb"] = df["PTS"] + df["REB"]
df["Ast+Reb"] = df["AST"] + df["REB"]
df["Stl+Blk"] = df["STL"] + df["BLK"]
df["PRA"] = df["PTS"] + df["REB"] + df["AST"]

stats = ['PTS', 'REB', 'Pts+Reb', 'AST', 'STL', 'BLK', 'TOV', 'FG3M',
         'Pts+Ast', 'Ast+Reb', 'Stl+Blk', 'PRA']

# ── Prop line selectors ─────────────────────────────────────────────────────────
cols = st.columns(12)
lines = {}
for i, stat in enumerate(stats):
    with cols[i % 12]:
        val = st.selectbox(
            stat,
            dropdown_values(),
            format_func=lambda x: "—" if x is None else f"{x}",
            key=f"line_{stat}"
        )
        if val is not None:
            lines[stat] = val

# ── 1. HIT RATE SUMMARY ─────────────────────────────────────────────────────────
if lines:
    pdata = df.sort_values("GAME_DATE_DT", ascending=False)

    odds_options = [
        "", "-110", "-105", "-115", "-120", "-125", "-130", "-135", "-140", "-145", "-150",
        "-155", "-160", "-165", "-170", "-175", "-180", "-185", "-190", "-195", "-200",
        "+100", "+105", "+110", "+115", "+120", "+125", "+130", "+135", "+140", "+145",
        "+150", "+155", "+160", "+165", "+200"
    ]

    for stat, line in lines.items():
        over_list = []
        for w in [5, 10, 15]:
            if len(pdata) >= w:
                recent = pdata.head(w)
                overs = (recent[stat] > line).sum()
                pct = overs / w * 100
                over_list.append(pct)

        hit_str_parts = []
        for i, w in enumerate([5, 10, 15]):
            if len(pdata) >= w:
                pct = over_list[i]
                color = "#00ff88" if pct > 73 else "#ffcc00" if pct >= 60 else "#ff5555"
                hit_str_parts.append(f"<span style='color:{color}'>{pct:.0f}%</span>")
            else:
                hit_str_parts.append("—")

        hit_str = " | ".join(hit_str_parts)

        if over_list:
            avg_o = np.mean(over_list)
            avg_u = 100 - avg_o
            o_color = "#00ff88" if avg_o > 75 else "#ffcc00" if avg_o >= 61 else "#ff5555"
            u_color = "#00ff88" if avg_u > 75 else "#ffcc00" if avg_u >= 61 else "#ff5555"
            avg_text = f" — AVG: <span style='color:{o_color}'>O {avg_o:.0f}%</span> / <span style='color:{u_color}'>U {avg_u:.0f}%</span>"
        else:
            avg_text = " — —"

        content = f"<center><strong>{stat} {line}</strong><strong> {hit_str}{avg_text}</strong></center>"

        col_content, col_odds, col_pin = st.columns([5.5, 3.5, 1])

        with col_content:
            st.markdown(
                f"<div style='background:rgba(10,30,60,0.7); padding:6px; border-radius:10px; border:1px solid #00aaff;'>{content}</div>",
                unsafe_allow_html=True
            )

        with col_odds:
            selected_odds = st.selectbox(
                "Odds",
                options=odds_options,
                index=0,
                format_func=lambda x: x if x else "— no odds —",
                key=f"odds_select_{selected_player}_{stat}_{line}",
                label_visibility="collapsed"
            )

        with col_pin:
            if st.button("📌", key=f"save_{selected_player}_{stat}_{line}_{selected_odds}", help="Pin to My Board"):
                entry = {
                    "player": selected_player,
                    "opponent": next_opp,
                    "stat": stat,
                    "line": f"{line:.1f}",
                    "odds": selected_odds if selected_odds else "",
                    "hitrate_str": f"{hit_str}{avg_text}",
                    "timestamp": datetime.now().strftime("%m/%d %H:%M")
                }

                exists = any(
                    e["player"] == entry["player"] and
                    e["stat"] == entry["stat"] and
                    e["line"] == entry["line"] and
                    e.get("odds", "") == entry["odds"]
                    for e in st.session_state.my_board
                )

                if not exists:
                    st.session_state.my_board.append(entry)
                    odds_part = f"   {entry['odds']}" if entry['odds'] else ""
                    st.toast(f"Pinned {stat} {entry['line']}{odds_part}", icon="📌")
                else:
                    st.toast("Already pinned", icon="ℹ️")
else:
    st.info("Select prop lines to see hit rates.")

# ── 2. RECENT PERFORMANCE ───────────────────────────────────────────────────────
recent = df.head(games_to_show)

if lines:
    cols = st.columns(min(3, len(lines)))
    
    for i, (stat, line) in enumerate(lines.items()):
        with cols[i % 3]:
            fig = go.Figure()
            colors = ["#00ff88" if v > line else "#ff4444" for v in recent[stat]]
            
            fig.add_trace(go.Bar(
                x=recent["GAME_DATE"], 
                y=recent[stat],
                marker_color=colors,
                text=recent[stat].round(1),
                textposition="inside",
                textfont=dict(color="#000000"),
                hovertemplate="Date: %{x}<br>Stat: %{y}<br>Line: " + str(line) + "<extra></extra>"
            ))
            fig.add_hline(y=line, line_color="#00ffff", line_width=3, line_dash="dash")
            
            fig.update_layout(
                height=320, 
                showlegend=False,
                plot_bgcolor="rgba(0,0,0,0)", 
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#00e0ff",
                margin=dict(t=20, b=40, l=30, r=30),
                yaxis_title=stat
            )
            st.plotly_chart(fig, use_container_width=True)

# ── 3. RECENT MINUTES PLAYED ────────────────────────────────────────────────────
fig_min = go.Figure()

colors = []
for m in recent['MIN']:
    if m >= 35:
        colors.append("#00ff88")
    elif m >= 30:
        colors.append("#88ff88")
    elif m >= 25:
        colors.append("#ffff88")
    elif m >= 20:
        colors.append("#ffcc88")
    else:
        colors.append("#ff8888")

fig_min.add_trace(go.Bar(
    x=recent["GAME_DATE"],
    y=recent["MIN"],
    marker_color=colors,
    text=recent["MIN"].round(1),
    textposition="auto",
    textfont=dict(color="#000000"),
    hovertemplate="Date: %{x}<br>Minutes: %{y}<extra></extra>"
))

avg_min = recent["MIN"].mean()
fig_min.add_hline(
    y=avg_min,
    line_dash="dot",
    line_color="#00e0ff",
    annotation_text=f"Avg: {avg_min:.1f}",
    annotation_position="top right",
    annotation_font_color="#00e0ff"
)

fig_min.update_layout(
    height=340,
    showlegend=False,
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font_color="#00e0ff",
    margin=dict(t=40, b=40, l=30, r=30),
    yaxis_title="Minutes",
    yaxis_range=[0, max(45, recent["MIN"].max() + 5)]
)

st.plotly_chart(fig_min, use_container_width=True)

# ── 4. GAME LOG vs OPPONENT ─────────────────────────────────────────────────────
opp_mask = (
    df['MATCHUP'].str.contains(f"vs. {next_opp}", case=False) |
    df['MATCHUP'].str.contains(f"@ {next_opp}", case=False) |
    df['MATCHUP'].str.endswith(next_opp)
)

vs_opp = df[opp_mask].sort_values("GAME_DATE_DT", ascending=False)

if vs_opp.empty:
    st.caption(f"No games found vs {next_opp}")
else:
    avg = vs_opp[stats].mean().round(1)
    avg_row = {
        "GAME_DATE": "",
        "MATCHUP": "",
        "MIN": vs_opp["MIN"].mean().round(1),
        "PLAYER_NAME": f"AVG vs {next_opp}"
    }
    avg_row.update(avg.to_dict())

    df_display = pd.concat([vs_opp[['GAME_DATE','MATCHUP','MIN'] + stats], pd.DataFrame([avg_row])], ignore_index=True)

    def highlight_avg(row):
        if row["GAME_DATE"] == "":
            return ['background-color: rgba(0, 180, 120, 0.18)'] * len(row)
        return [''] * len(row)

    st.dataframe(
        df_display.style.format({c: "{:.1f}" for c in ['MIN'] + stats})
                      .apply(highlight_avg, axis=1),
        use_container_width=True
    )

# ── 5. Recent game log + averages ───────────────────────────────────────────────
with st.expander("📊 Recent Game Log + Averages", expanded=False):
    display_cols = ['GAME_DATE', 'MATCHUP', 'MIN'] + stats
    log = recent[display_cols].copy()

    avg = recent[stats].mean().round(1)
    avg_row = {
        "GAME_DATE": "",
        "MATCHUP": "",
        "MIN": recent["MIN"].mean().round(1),
        **avg.to_dict()
    }

    final = pd.concat([log, pd.DataFrame([avg_row])], ignore_index=True)

    st.dataframe(
        final.style.format({c: "{:.1f}" for c in ['MIN'] + stats}),
        use_container_width=True
    )

# ── Footer ──────────────────────────────────────────────────────────────────────
st.markdown("<p style='text-align:center; color:#88f0ff; padding:4rem;'>ICE PROP LAB • SYSTEM ACTIVE • 2025-26</p>", unsafe_allow_html=True)