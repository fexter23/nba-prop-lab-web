# nba_wrk.py – ICE PROP LAB • Optimized for Local L10 Parquet
import streamlit as st
import json
import os
from nba_api.stats.static import players
from nba_api.stats.static import teams as static_teams
from nba_api.stats.endpoints import leaguedashplayerstats, PlayerGameLog, scoreboardv2
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, date

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

st.set_page_config(page_title="ICE PROP LAB", layout="wide", initial_sidebar_state="expanded")

# ── Session state ───────────────────────────────────────────────────────────────
if 'my_board' not in st.session_state:
    st.session_state.my_board = []
if 'filter_teams' not in st.session_state:
    st.session_state.filter_teams = None 

# ── Team abbreviation lookup ────────────────────────────────────────────────────
@st.cache_data(ttl=86400)
def get_team_abbr_map():
    all_teams = static_teams.get_teams()
    return {str(t['id']): t['abbreviation'] for t in all_teams}

team_abbr_map = get_team_abbr_map()

# ── Today's NBA Games ───────────────────────────────────────────────────────────
today_str = date.today().strftime("%Y-%m-%d")

@st.cache_data(ttl=300)
def get_todays_games(game_date: str):
    try:
        sb = scoreboardv2.ScoreboardV2(game_date=game_date, league_id="00", day_offset=0)
        game_header_df = sb.game_header.get_data_frame()
        if game_header_df.empty: return [], 0
        game_header_df = game_header_df.drop_duplicates(subset=['GAME_ID'])
        
        games = []
        for _, row in game_header_df.iterrows():
            visitor_id = str(row['VISITOR_TEAM_ID'])
            home_id    = str(row['HOME_TEAM_ID'])
            games.append({
                'away': team_abbr_map.get(visitor_id, '???'),
                'home': team_abbr_map.get(home_id, '???'),
                'status': row['GAME_STATUS_TEXT'],
            })
        return games, len(games)
    except:
        return [], 0

games_today, num_games = get_todays_games(today_str)
matchup_lookup = {}
for g in games_today:
    label = f"{g['away']} @ {g['home']}"
    matchup_lookup[g['away']] = label
    matchup_lookup[g['home']] = label

# ── Sidebar: Data Source & Game Filter ─────────────────────────────────────────
st.sidebar.markdown("### Today's Games")

# Display sync time for the L10 local data
if os.path.exists("data/player_logs_l10.parquet"):
    mtime = os.path.getmtime("data/player_logs_l10.parquet")
    sync_time = datetime.fromtimestamp(mtime).strftime("%m/%d %H:%M")
    st.sidebar.caption(f"Last L10 Sync: {sync_time}")

game_options = ["— All Players —"]
game_labels_to_teams = {"— All Players —": None}
for g in games_today:
    label = f"{g['away']} @ {g['home']}  ({g['status']})"
    game_options.append(label)
    game_labels_to_teams[label] = (g['away'], g['home'])

selected_game_label = st.sidebar.selectbox("Filter players by game", game_options, index=0, label_visibility="collapsed")

if selected_game_label == "— All Players —":
    st.session_state.filter_teams = None
else:
    st.session_state.filter_teams = game_labels_to_teams[selected_game_label]

# ── Data Loading Helpers ───────────────────────────────────────────────────────
def dropdown_values():
    return [None] + [round(x, 1) for x in np.arange(0.5, 60.6, 1.0)]

def get_player_id(name):
    if os.path.exists("data/players.parquet"):
        try:
            df_p = pd.read_parquet("data/players.parquet")
            match = df_p[df_p['full_name'].str.lower() == name.lower()]
            if not match.empty: return match.iloc[0]['id']
        except: pass
    for p in players.get_players():
        if p['full_name'].lower() == name.lower(): return p['id']
    return None

@st.cache_data(ttl=7200)
def get_active_players_with_teams():
    if os.path.exists("data/active_player_teams.parquet"):
        try:
            df_local = pd.read_parquet("data/active_player_teams.parquet")
            return dict(zip(df_local['PLAYER_ID'].astype(str), df_local['TEAM_ABBR']))
        except: pass
    return {}

player_team_map = get_active_players_with_teams()

@st.cache_data(ttl=86400)
def get_base_player_list():
    if os.path.exists("data/players.parquet"):
        try: return pd.read_parquet("data/players.parquet").to_dict('records')
        except: pass
    return players.get_players()

all_players = get_base_player_list()
player_options = []
for p in all_players:
    pid_str = str(p["id"])
    if pid_str not in player_team_map: continue
    team = player_team_map[pid_str]
    if st.session_state.filter_teams is not None:
        if team not in st.session_state.filter_teams: continue
    player_options.append((f"{p['full_name']} • {team}", p['full_name']))

player_options.sort(key=lambda x: x[1].lower())
player_list_display = [opt[0] for opt in player_options]

available_stats = ['PTS', 'FG3M', 'AST', 'REB', 'Ast+Reb', 'STL', 'BLK', 'TOV', 'Pts+Reb', 'Pts+Ast', 'Stl+Blk', 'PRA']
odds_options = ["", "-110", "-115", "-120", "+100", "+110", "+120"]

# ── Sidebar: Player & Stat Selection ──────────────────────────────────────────
top_row = st.sidebar.columns([3, 2])
with top_row[0]:
    selected_display = st.selectbox("Player", ["— Choose player —"] + player_list_display, key="player_select", label_visibility="collapsed")
with top_row[1]:
    selected_stat = st.selectbox("Stat", ["— Select —"] + available_stats, index=1, key="stat_select", label_visibility="collapsed")

selected_player = next((clean for disp, clean in player_options if disp == selected_display), None)
pid = get_player_id(selected_player) if selected_player else None
player_team = player_team_map.get(str(pid), "???") if pid else "???"

# ── Load Game Log (L10 Parquet vs API) ────────────────────────────────────────
df = None
if pid:
    @st.cache_data(ttl=300)
    def get_player_data(pid_str):
        # 1. Try local incremental parquet
        if os.path.exists("data/player_logs_l10.parquet"):
            try:
                all_logs = pd.read_parquet("data/player_logs_l10.parquet")
                player_log = all_logs[all_logs['Player_ID'].astype(str) == pid_str].copy()
                if not player_log.empty:
                    return player_log, "✅ Local Parquet"
            except: pass
        
        # 2. Fallback to API
        try:
            log = PlayerGameLog(player_id=pid_str, season=CURRENT_SEASON, last_n_games=10).get_data_frames()[0]
            if not log.empty:
                return log, "⚠️ Live API (Fallback)"
        except: pass
        return pd.DataFrame(), "No Data"

    df_raw, source_label = get_player_data(str(pid))
    st.sidebar.markdown(f"**Data Source:** {source_label}")

    if not df_raw.empty:
        df = df_raw.copy()
        df["GAME_DATE_DT"] = pd.to_datetime(df["GAME_DATE"])
        df["GAME_DATE"] = df["GAME_DATE_DT"].dt.strftime("%m/%d")
        # Calc derived stats
        df["Pts+Ast"] = df["PTS"] + df["AST"]
        df["Pts+Reb"] = df["PTS"] + df["REB"]
        df["Ast+Reb"] = df["AST"] + df["REB"]
        df["Stl+Blk"] = df["STL"] + df["BLK"]
        df["PRA"]     = df["PTS"] + df["REB"] + df["AST"]
        df = df.sort_values("GAME_DATE_DT", ascending=False).reset_index(drop=True)

# ── Sidebar: Lines & Pinning ──────────────────────────────────────────────────
lines = {}
if selected_stat and selected_stat != "— Select —" and df is not None:
    st.sidebar.markdown(f"**{selected_stat} line**")
    l_col, o_col = st.sidebar.columns(2)
    with l_col:
        val = st.selectbox(f"{selected_stat} line", dropdown_values(), key=f"line_{selected_stat}", label_visibility="collapsed")
        if val: lines[selected_stat] = val
    with o_col:
        odds_key = f"odds_{selected_player}_{selected_stat}"
        st.selectbox("Odds", odds_options, key=odds_key, label_visibility="collapsed")

    if st.sidebar.button("📌", use_container_width=True):
        line = lines[selected_stat]
        pdata = df.head(10)
        
        # Hit Rate Formatting
        windows = [5, 10]
        parts = []
        for w in windows:
            if len(df) >= w:
                pct = (df.head(w)[selected_stat] > line).mean() * 100
                color = '#00ff88' if pct > 73 else '#ffcc00' if pct >= 60 else '#ff5555'
                parts.append(f"<span style='color:{color}'>{pct:.0f}%</span> (L{w})")
        
        # Streak & Minutes
        results = (df[selected_stat] > line).tolist()
        streak_type = "O" if results[0] else "U"
        count = 0
        for r in results:
            if (r and streak_type == "O") or (not r and streak_type == "U"): count += 1
            else: break
        
        hit_str = " | ".join(parts) + f" | **{streak_type}{count}** | {df.head(10)['MIN'].mean():.1f}m"
        
        st.session_state.my_board.append({
            "player": selected_player, "team": player_team, 
            "matchup": matchup_lookup.get(player_team, "Other"), 
            "stat": selected_stat, "line": f"{line:.1f}", 
            "odds": st.session_state.get(odds_key, ""), 
            "hitrate_str": hit_str, "timestamp": datetime.now()
        })
        st.rerun()

# ── Sidebar: Dashboard Management ─────────────────────────────────────────────
if st.session_state.my_board:
    st.sidebar.divider()
    dash_df = pd.DataFrame(st.session_state.my_board)
    for match, group in dash_df.groupby('matchup'):
        with st.sidebar.expander(f"🏀 {match} ({len(group)})", expanded=True):
            for i, entry in group.iterrows():
                st.markdown(f"**{entry['player']}** | > {entry['stat']} {entry['line']} ({entry['odds']})<br><small>{entry['hitrate_str']}</small>", unsafe_allow_html=True)
                if st.button("🗑️", key=f"del_{i}"):
                    st.session_state.my_board.pop(i)
                    st.rerun()

# ── Main Content ──────────────────────────────────────────────────────────────
if not selected_player or df is None:
    st.info("Select a player from the sidebar to view detailed analytics.")
else:
    st.header(f"{selected_player} ({player_team})")
    
    # 1. Visualization
    if selected_stat in lines:
        line_val = lines[selected_stat]
        fig = go.Figure()
        colors = ["#00ff88" if v > line_val else "#ff4444" for v in df.head(10)[selected_stat]]
        fig.add_trace(go.Bar(x=df.head(10)["GAME_DATE"], y=df.head(10)[selected_stat], marker_color=colors, text=df.head(10)[selected_stat]))
        fig.add_hline(y=line_val, line_dash="dash", line_color="#00ffff", annotation_text=f"Line: {line_val}")
        fig.update_layout(title=f"Last 10 Games: {selected_stat}", height=400, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

    # 2. Raw Data Table
    st.subheader("Recent Performance")
    display_cols = ["GAME_DATE", "MATCHUP", "WL", "MIN", "PTS", "REB", "AST", "PRA", "FG3M"]
    st.dataframe(df[display_cols].head(10), use_container_width=True, hide_index=True)

st.markdown("<p style='text-align:center; color:#88f0ff; margin-top:50px;'>ICE PROP LAB • 2026</p>", unsafe_allow_html=True)
