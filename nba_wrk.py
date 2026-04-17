import streamlit as st
import json
from nba_api.stats.static import players
from nba_api.stats.static import teams as static_teams
from nba_api.stats.endpoints import leaguedashplayerstats, PlayerGameLog, scoreboardv2
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, date
from PIL import Image 

# ====================== FAVICON & PAGE CONFIG ======================
st.set_page_config(
    page_title="NBA Hit Tracker",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Season helpers ──────────────────────────────────────────────────────────────
def get_current_season():
    today = datetime.today()
    return f"{today.year}-{str(today.year + 1)[-2:]}" if today.month >= 10 else f"{today.year-1}-{str(today.year)[-2:]}"

CURRENT_SEASON = get_current_season()
current_year = int(CURRENT_SEASON.split('-')[0])
PREVIOUS_SEASON = f"{current_year - 1}-{str(current_year)[-2:]}"

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
    except Exception as e:
        st.warning(f"Could not load today's games: {str(e)}")
        return [], 0

games_today, num_games = get_todays_games(today_str)

matchup_lookup = {}
for g in games_today:
    label = f"{g['away']} @ {g['home']}"
    matchup_lookup[g['away']] = label
    matchup_lookup[g['home']] = label

# ── Helper Functions ────────────────────────────────────────────────────────────
def dropdown_values():
    return [None] + [round(x, 1) for x in np.arange(0.5, 60.6, 1.0)]

def get_player_id(name):
    for p in players.get_players():
        if p['full_name'].lower() == name.lower():
            return p['id']
    return None

def get_opponent_from_game(selected_game_label, player_team):
    if not selected_game_label or selected_game_label == "— All Players —":
        return None
    for g in games_today:
        label = f"{g['away']} @ {g['home']}  ({g['status']})"
        if label == selected_game_label:
            return g['home'] if g['away'] == player_team else g['away']
    return None

# ── Sidebar: Filters ────────────────────────────────────────────────────────────
st.sidebar.markdown("### Today's Games & Player")
top_filters = st.sidebar.columns([2.2, 2.8])

with top_filters[0]:
    game_options = ["— All Players —"]
    game_labels_to_teams = {"— All Players —": None}
    for g in games_today:
        label = f"{g['away']} @ {g['home']}  ({g['status']})"
        game_options.append(label)
        game_labels_to_teams[label] = (g['away'], g['home'])

    selected_game_label = st.selectbox("Filter by game", game_options, index=0, label_visibility="collapsed", key="game_filter_select")
    st.session_state.filter_teams = game_labels_to_teams[selected_game_label] if selected_game_label != "— All Players —" else None

with top_filters[1]:
    @st.cache_data(ttl=7200)
    def get_active_players_with_teams():
        for season in [CURRENT_SEASON, PREVIOUS_SEASON]:
            try:
                df = leaguedashplayerstats.LeagueDashPlayerStats(season=season, season_type_all_star="Regular Season").get_data_frames()[0]
                if not df.empty and len(df) > 80:
                    df = df[df['TEAM_ABBREVIATION'].notna() & (df['TEAM_ABBREVIATION'] != '')]
                    return dict(zip(df['PLAYER_ID'].astype(str), df['TEAM_ABBREVIATION']))
            except: continue
        return {}

    player_team_map = get_active_players_with_teams()
    player_options = []
    for p in players.get_players():
        pid_str = str(p["id"])
        if pid_str not in player_team_map: continue
        team = player_team_map[pid_str]
        if st.session_state.filter_teams and team not in st.session_state.filter_teams: continue
        player_options.append((f"{p['full_name']} • {team}", p['full_name']))

    player_options.sort(key=lambda x: x[1].lower())
    selected_display = st.selectbox("Player", ["— Choose player —"] + [opt[0] for opt in player_options], key="player_select", label_visibility="collapsed")

selected_player = next((clean for disp, clean in player_options if disp == selected_display), None)
pid = get_player_id(selected_player) if selected_player else None
player_team = player_team_map.get(str(pid), "???") if pid else "???"

# ── Stat • Line • Odds ─────────────────────────────────────────────────────────
available_stats = ['PTS', 'FG3M','AST','REB', 'Ast+Reb', 'STL', 'BLK', 'TOV', 'FGM', 'FGA', 'FG3A', '2PM', '2PA', 'Pts+Reb', 'Pts+Ast', 'Stl+Blk', 'PRA']
odds_options = ["", "-300", "-250", "-200", "-150", "-110", "+110", "+150", "+200", "+250", "+300"] # Shortened for brevity

lines = {}
selected_stat = None
odds_key = None

if selected_player:
    col_stat, col_line, col_odds = st.sidebar.columns([1.8, 1.6, 1.6])
    with col_stat:
        selected_stat = st.selectbox("Stat", ["— Select stat —"] + available_stats, index=1, key="stat_select", label_visibility="collapsed")
    with col_line:
        line_val = st.selectbox("Line", dropdown_values(), format_func=lambda x: "—" if x is None else f"{x:.1f}", key="line_key", label_visibility="collapsed")
        if line_val is not None and selected_stat != "— Select stat —": lines[selected_stat] = line_val
    with col_odds:
        odds_key = f"odds_{selected_player}_{selected_stat}"
        st.selectbox("Odds", odds_options, key=odds_key, label_visibility="collapsed")

# ── DATA FETCHING (INC. PLAY-IN) ────────────────────────────────────────────────
df = None
if pid:
    @st.cache_data(ttl=300)
    def get_all_player_games(pid_str):
        all_logs = []
        # 'Play-In' is the specific tag for Play-In Tournament games
        game_types = ['Regular Season', 'Playoffs', 'Play-In']
        
        for season in [CURRENT_SEASON, PREVIOUS_SEASON]:
            for g_type in game_types:
                try:
                    log = PlayerGameLog(player_id=pid_str, season=season, season_type_all_star=g_type).get_data_frames()[0]
                    if not log.empty:
                        all_logs.append(log)
                except: continue
        
        if not all_logs: return pd.DataFrame()
        df_full = pd.concat(all_logs, ignore_index=True)
        df_full["GAME_DATE_DT"] = pd.to_datetime(df_full["GAME_DATE"])
        df_full["GAME_DATE"] = df_full["GAME_DATE_DT"].dt.strftime("%m/%d")
        return df_full.sort_values("GAME_DATE_DT", ascending=False).reset_index(drop=True)

    df = get_all_player_games(str(pid))
    if not df.empty:
        df["Pts+Ast"] = df["PTS"] + df["AST"]
        df["Pts+Reb"] = df["PTS"] + df["REB"]
        df["Ast+Reb"] = df["AST"] + df["REB"]
        df["Stl+Blk"] = df["STL"] + df["BLK"]
        df["PRA"]     = df["PTS"] + df["REB"] + df["AST"]

# ── Dashboard & Pinning Logic (Simplified for brevity) ──────────────────────────
if (selected_player and selected_stat != "— Select stat —" and selected_stat in lines and df is not None and not df.empty and st.sidebar.button("📌 Pin to Board", use_container_width=True)):
    line = lines[selected_stat]
    pdata = df.head(10)
    hit_pct_10 = (pdata[selected_stat] > line).mean() * 100
    hit_pct_5 = (df.head(5)[selected_stat] > line).mean() * 100
    
    entry = {
        "player": selected_player, "team": player_team, "matchup": matchup_lookup.get(player_team, "N/A"),
        "stat": selected_stat, "line": f"{line:.1f}", "odds": st.session_state.get(odds_key, ""),
        "hitrate_str": f"{hit_pct_5:.0f}% | {hit_pct_10:.0f}%", "timestamp": datetime.now()
    }
    st.session_state.my_board.append(entry)
    st.rerun()

# ── Main Content ────────────────────────────────────────────────────────────────
if not selected_player or df is None or df.empty:
    st.info("Select a player to view the full game log (Regular, Playoff, and Play-In).")
    st.stop()

st.markdown(f"## {selected_player} Analysis")
if lines:
    for stat, line in lines.items():
        st.markdown(f"**{stat} > {line}**")
        n = min(15, len(df))
        fig = go.Figure(go.Bar(x=df.head(n)["GAME_DATE"], y=df.head(n)[stat], marker_color=["#00ff88" if v > line else "#ff4444" for v in df.head(n)[stat]]))
        fig.add_hline(y=line, line_dash="dash", line_color="cyan")
        st.plotly_chart(fig, use_container_width=True)

with st.expander("📊 Full Game Log (Inc. Play-In & Playoffs)", expanded=True):
    st.dataframe(df.head(20)[["GAME_DATE", "MATCHUP", "WL", "MIN", "PTS", "REB", "AST", "STL", "BLK"]], use_container_width=True, hide_index=True)
