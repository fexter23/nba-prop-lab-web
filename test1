  # nba_wrk.py – ICE PROP LAB • Single Player + Persistent Opponent + DvP Panel

import streamlit as st
from nba_api.stats.static import players
from nba_api.stats.endpoints import leaguedashplayerstats, PlayerGameLog
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="ICE PROP LAB", layout="wide", initial_sidebar_state="expanded")

# ── Session state ───────────────────────────────────────────────────────────────
if 'my_board' not in st.session_state:
    st.session_state.my_board = []
if 'next_opponent' not in st.session_state:
    st.session_state.next_opponent = "BOS"

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
    .hit-box {background:rgba(10,30,60,0.7); padding:10px; border-radius:10px; 
              border:1px solid #00aaff; margin-bottom:12px;}
    .highlight-stat {background: rgba(0, 180, 120, 0.18); padding: 6px 10px; 
                     border-radius: 6px; border-left: 4px solid #00cc88;}
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
def get_active_players_with_teams():
    for season in [CURRENT_SEASON, PREVIOUS_SEASON]:
        try:
            df = leaguedashplayerstats.LeagueDashPlayerStats(
                season=season, season_type_all_star="Regular Season"
            ).get_data_frames()[0]
            if not df.empty and len(df) > 80:
                df = df[df['TEAM_ABBREVIATION'].notna() & (df['TEAM_ABBREVIATION'] != '')]
                return dict(zip(df['PLAYER_ID'].astype(str), df['TEAM_ABBREVIATION']))
        except:
            continue
    return {}

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

def get_hitrate_edge(hitrate_str: str) -> float:
    if not hitrate_str or "AVG:" not in hitrate_str:
        return 0.0
    try:
        avg_part = hitrate_str.split("AVG:")[1]
        o_str = avg_part.split("O ")[1].split("%")[0].strip()
        o_pct = float(o_str)
        strongest = max(o_pct, 100 - o_pct)
        return strongest - 50
    except:
        return 0.0

# ── Load player-team map ────────────────────────────────────────────────────────
player_team_map = get_active_players_with_teams()

player_options = []
for p in players.get_players():
    pid_str = str(p["id"])
    if pid_str in player_team_map:
        team = player_team_map[pid_str]
        display_name = f"{p['full_name']} • {team}"
        player_options.append((display_name, p['full_name']))

player_options.sort(key=lambda x: x[1].lower())
player_list_display = [opt[0] for opt in player_options]
player_list_clean = [opt[1] for opt in player_options]

common_teams = sorted(['ATL','BOS','BKN','CHA','CHI','CLE','DAL','DEN','DET','GSW','HOU','IND','LAC','LAL','MEM','MIA','MIL','MIN','NOP','NYK','OKC','ORL','PHI','PHX','POR','SAC','SAS','TOR','UTA','WAS'])

available_stats = [
    'PTS', 'REB', 'AST', 'STL', 'BLK', 'TOV',
    'FGM', 'FGA', 'FG3M', 'FG3A', '2PM', '2PA',
    'Pts+Reb', 'Pts+Ast', 'Ast+Reb', 'Stl+Blk', 'PRA'
]

odds_options = [""] + ["-110","-105","-115","-120","-125","-130"] + ["+100","+105","+110","+115","+120","+130"] + \
               [f"-{x}" for x in range(101,301,1)] + [f"+{x}" for x in range(100,501,5) if x % 5 == 0]

# ── Sidebar ─────────────────────────────────────────────────────────────────────

# Top row: Player + Stat + Opponent (all on one line, no labels)
top_row = st.sidebar.columns([3, 2, 2])
with top_row[0]:
    selected_display = st.selectbox(
        "Player",
        ["— Choose player —"] + player_list_display,
        key="player_select",
        label_visibility="collapsed"
    )
with top_row[1]:
    selected_stat = st.selectbox(
        "Stat",
        ["— Select stat —"] + available_stats,
        index=1,
        key="stat_select",
        label_visibility="collapsed"
    )
with top_row[2]:
    next_opp = st.selectbox(
        "Opponent",
        common_teams,
        index=common_teams.index(st.session_state.next_opponent) if st.session_state.next_opponent in common_teams else 0,
        key="opp_select",
        label_visibility="collapsed"
    )

if next_opp != st.session_state.next_opponent:
    st.session_state.next_opponent = next_opp

selected_player = None
if selected_display != "— Choose player —":
    for disp, clean in zip(player_list_display, player_list_clean):
        if disp == selected_display:
            selected_player = clean
            break

player_team = "???"
pid = None
if selected_player:
    pid = get_player_id(selected_player)
    if pid and str(pid) in player_team_map:
        player_team = player_team_map[str(pid)]

# Prop line
lines = {}
if selected_stat and selected_stat != "— Select stat —":
    st.sidebar.markdown(f"**{selected_stat} line**")
    val = st.sidebar.selectbox(
        f"{selected_stat} line",
        dropdown_values(),
        format_func=lambda x: "—" if x is None else f"{x}",
        key=f"line_{selected_stat}",
        label_visibility="collapsed"
    )
    if val is not None:
        lines[selected_stat] = val

# My Board
with st.sidebar.expander(f"📋 My Board ({len(st.session_state.my_board)})", expanded=len(st.session_state.my_board)>0):
    if not st.session_state.my_board:
        st.caption("No props saved yet. Pin with 📌")
    else:
        board_sorted = sorted(
            st.session_state.my_board,
            key=lambda x: (get_hitrate_edge(x.get("hitrate_str","")), x.get("timestamp","")),
            reverse=True
        )
        for idx, item in enumerate(board_sorted):
            original_idx = st.session_state.my_board.index(item)
            col1, col2 = st.columns([6,1])
            with col1:
                odds_d = f" {item['odds']}" if item.get('odds') else ""
                st.markdown(f"**{item['player']} • {item['team']}**  \n<small>{item['stat']} {item['line']}{odds_d} {item['hitrate_str']}</small>", unsafe_allow_html=True)
            with col2:
                if st.button("×", key=f"rm_{original_idx}", help="Remove"):
                    st.session_state.my_board.pop(original_idx)
                    st.rerun()
        if st.button("🗑️ Clear All", use_container_width=True):
            st.session_state.my_board = []
            st.rerun()

st.sidebar.markdown("---")

# Bottom row: Recent games + Refresh (no label)
bottom_row = st.sidebar.columns([2, 1])
with bottom_row[0]:
    games_to_show = st.selectbox(
        "Recent games",
        [5,10,15,20],
        index=2,
        label_visibility="collapsed"
    )
with bottom_row[1]:
    if st.button("🔄", help="Refresh caches & data"):
        st.cache_data.clear()
        st.rerun()

st.sidebar.markdown("**Upload DvP**")
uploaded_file = st.sidebar.file_uploader("", type=["xlsx", "csv"], label_visibility="collapsed")

dvp_df = None
if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            dvp_df = pd.read_csv(uploaded_file)
        else:
            dvp_df = pd.read_excel(uploaded_file, sheet_name=0)

        if 'TEAM' in dvp_df.columns:
            dvp_df['TEAM'] = dvp_df['TEAM'].str.split('(').str[0].str.strip()

        team_map = {
            'Utah':'UTA','Washington':'WAS','Sacramento':'SAC','Chicago':'CHI',
            'New Orleans':'NOP','Atlanta':'ATL','Indiana':'IND','Portland':'POR',
            'Miami':'MIA','Memphis':'MEM','Dallas':'DAL','Los Angeles':'LAC',
            'Denver':'DEN','Cleveland':'CLE','Milwaukee':'MIL','Brooklyn':'BKN',
            'Orlando':'ORL','Philadelphia':'PHI','Minnesota':'MIN','Golden State':'GSW',
            'Charlotte':'CHA','San Antonio':'SAS','Phoenix':'PHX','New York':'NYK',
            'Toronto':'TOR','Detroit':'DET','Houston':'HOU','Boston':'BOS',
            'Oklahoma City':'OKC', 'LA Clippers':'LAC', 'LA Lakers':'LAL'
        }
        if 'TEAM_ABBR' not in dvp_df.columns:
            dvp_df['TEAM_ABBR'] = dvp_df['TEAM'].map(team_map).fillna(dvp_df['TEAM'].str.upper()[:3])

        for col in ['PTS','REB','AST','3PM','STL','BLK','TO']:
            if col in dvp_df.columns:
                dvp_df[f'{col}_rank'] = dvp_df[col].rank(method='min', ascending=True).astype(int)

    except Exception as e:
        st.sidebar.error(f"File error: {e}")

# ── Main content ────────────────────────────────────────────────────────────────

if not selected_player:
    st.info("Select a player to begin.")
    st.stop()

if not pid:
    st.error("Player ID not found.")
    st.stop()

with st.spinner("Loading game logs..."):
    df = get_player_games(pid)
    if df.empty:
        st.error("No game data.")
        st.stop()

df["PLAYER_NAME"] = selected_player

df["Pts+Ast"] = df["PTS"] + df["AST"]
df["Pts+Reb"] = df["PTS"] + df["REB"]
df["Ast+Reb"] = df["AST"] + df["REB"]
df["Stl+Blk"] = df["STL"] + df["BLK"]
df["2PM"] = df["FGM"] - df["FG3M"]
df["2PA"] = df["FGA"] - df["FG3A"]
df["PRA"] = df["PTS"] + df["REB"] + df["AST"]

# ── Layout ──────────────────────────────────────────────────────────────────────
left_col, right_col = st.columns([3.5, 1.5])

with left_col:
   

    if lines:
        pdata = df.sort_values("GAME_DATE_DT", ascending=False)
        for stat, line in lines.items():
            over_list = []
            for w in [5,10,15]:
                if len(pdata) >= w:
                    overs = (pdata.head(w)[stat] > line).sum()
                    pct = overs / w * 100 if w > 0 else 0
                    over_list.append(pct)

            parts = []
            for i, w in enumerate([5,10,15]):
                if len(pdata) >= w:
                    pct = over_list[i]
                    color = "#00ff88" if pct > 73 else "#ffcc00" if pct >= 60 else "#ff5555"
                    parts.append(f"<span style='color:{color}'>{pct:.0f}%</span>")
                else:
                    parts.append("—")
            hit_str = " | ".join(parts)

            if over_list:
                avg_o = np.mean(over_list)
                avg_u = 100 - avg_o
                o_c = "#00ff88" if avg_o > 75 else "#ffcc00" if avg_o >= 61 else "#ff5555"
                u_c = "#00ff88" if avg_u > 75 else "#ffcc00" if avg_u >= 61 else "#ff5555"
                avg_text = f" — AVG: <span style='color:{o_c}'>O {avg_o:.0f}%</span> / <span style='color:{u_c}'>U {avg_u:.0f}%</span>"
            else:
                avg_text = ""

            content = f"<strong>{stat} {line}</strong> {hit_str}{avg_text}"
            c1, c2, c3 = st.columns([5.5, 3.5, 1])
            with c1:
                st.markdown(f"<div class='hit-box'>{content}</div>", unsafe_allow_html=True)
            with c2:
                odds_key = f"odds_{selected_player}_{stat}_{line}"
                st.selectbox("Odds", odds_options, key=odds_key, label_visibility="collapsed")
            with c3:
                pin_key = f"pin_{selected_player}_{stat}_{line}"
                if st.button("📌", key=pin_key):
                    odds_val = st.session_state.get(odds_key, "")
                    entry = {
                        "player": selected_player, "team": player_team,
                        "opponent": next_opp, "stat": stat, "line": f"{line:.1f}",
                        "odds": odds_val, "hitrate_str": f"{hit_str}{avg_text}",
                        "timestamp": datetime.now().strftime("%m/%d %H:%M")
                    }
                    exists = any(
                        e["player"] == entry["player"] and
                        e["stat"] == entry["stat"] and
                        e["line"] == entry["line"]
                        for e in st.session_state.my_board
                    )
                    if not exists:
                        st.session_state.my_board.append(entry)
                        st.toast("Pinned", icon="📌")
                    st.rerun()

    recent = df.head(games_to_show)
    if lines:
        for stat, line in lines.items():
            fig = go.Figure()
            colors = ["#00ff88" if v > line else "#ff4444" for v in recent[stat]]
            fig.add_trace(go.Bar(x=recent["GAME_DATE"], y=recent[stat], marker_color=colors,
                                 text=recent[stat].round(1), textposition="inside", textfont=dict(color="#000")))
            fig.add_hline(y=line, line_color="#00ffff", line_dash="dash")
            fig.update_layout(height=320, showlegend=False, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                              font_color="#00e0ff", margin=dict(t=20,b=40,l=30,r=30), yaxis_title=stat)
            st.plotly_chart(fig, use_container_width=True)

    if len(recent) >= 3:
        x = np.arange(len(recent))
        y = recent["MIN"].values
        slope, intercept = np.polyfit(x, y, 1)
        recent_avg = recent["MIN"].mean()
        projected = recent_avg + slope

        concern = "🟢 Solid" if projected >= 32 else "🟡 Some concern <32" if projected >= 28 else "🟠 Moderate <28" if projected >= 25 else "🔴 High <25"
        arrow = "↑" if slope > 0.3 else "↓" if slope < -0.3 else "→"
        st.markdown(f"**Projected next min**: ≈ **{projected:.1f}**  ({arrow} {slope:.1f} min/game) — **{concern}**")

        fig_min = go.Figure()
        colors_min = []
        for m in recent["MIN"]:
            if m >= 35: colors_min.append("#00ff88")
            elif m >= 30: colors_min.append("#88ff88")
            elif m >= 25: colors_min.append("#ffff88")
            elif m >= 20: colors_min.append("#ffcc88")
            else: colors_min.append("#ff8888")

        fig_min.add_trace(go.Bar(x=recent["GAME_DATE"], y=recent["MIN"], marker_color=colors_min,
                                 text=recent["MIN"].round(1), textposition="auto", textfont=dict(color="#000")))
        fig_min.add_hline(y=recent_avg, line_dash="dot", line_color="#00e0ff",
                          annotation_text=f"Avg: {recent_avg:.1f}", annotation_position="top right")
        if len(recent) >= 3:
            trend_y = slope * x + intercept
            fig_min.add_trace(go.Scatter(x=recent["GAME_DATE"], y=trend_y, mode='lines',
                                         line=dict(color='#00e0ff', width=2, dash='dash')))
        fig_min.update_layout(height=340, showlegend=False, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                              font_color="#00e0ff", margin=dict(t=20,b=40,l=30,r=30), yaxis_title="Minutes")
        st.plotly_chart(fig_min, use_container_width=True)

# ── Defensive Context (only opponent) ──────────────────────────────────────────
with right_col:
    

    def get_matchup_indicator(stat, rank):
        if stat == 'TO':
            if rank <= 8:   return "🔴", "#ff4d4d", "very few forced"
            if rank <= 15:  return "🟠", "#ffaa00", "some pressure"
            if rank <= 22:  return "⚪", "#cccccc", "neutral"
            if rank <= 27:  return "🟢", "#88cc88", "good for Over TO"
            return "🟢🟢", "#00cc00", "excellent for Over TO"
        else:
            if rank <= 8:   return "🔴", "#ff4d4d", "very tough"
            if rank <= 15:  return "🟠", "#ffaa00", "above avg"
            if rank <= 22:  return "⚪", "#cccccc", "neutral"
            if rank <= 27:  return "🟢", "#88cc88", "favorable"
            return "🟢🟢", "#00cc00", "excellent for Over"

    if dvp_df is None or dvp_df.empty:
        st.info("Upload DvP file in sidebar")
    else:
        opp_row = dvp_df[dvp_df['TEAM_ABBR'].str.upper() == st.session_state.next_opponent.upper()]
        if not opp_row.empty:
            row = opp_row.iloc[0]
            st.markdown(f"**{st.session_state.next_opponent}** allowed (rank)")

            current_stat = selected_stat if selected_stat and selected_stat != "— Select stat —" else None

            for s in ['PTS','REB','AST','3PM','STL','BLK','TO']:
                if s in row and pd.notna(row[s]):
                    val = row[s]
                    rank = row.get(f'{s}_rank', None)
                    if rank is None:
                        st.markdown(f"• **{s}**: {val:.2f} (—)")
                        continue

                    icon, color, desc = get_matchup_indicator(s, rank)

                    highlight_class = "highlight-stat" if current_stat == s else ""

                    val_str = f"{val:.2f}"
                    rank_str = f"{rank}" if rank is not None else "—"

                    st.markdown(
                        f"<div class='{highlight_class}'>"
                        f"• {s}: {val_str} (rank {rank_str}) "
                        f"<span style='color:{color}; font-size:1.3em; font-weight:bold;'>{icon}</span> "
                        f"<small>{desc}</small>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
        else:
            st.info(f"No defensive data found for {st.session_state.next_opponent}")

st.markdown("<p style='text-align:center; color:#88f0ff; padding:3rem;'>ICE PROP LAB • 2025-26</p>", unsafe_allow_html=True)
