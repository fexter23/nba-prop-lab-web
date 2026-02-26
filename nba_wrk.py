# nba_wrk.py – ICE PROP LAB • Single Player + Persistent Opponent + DvP Panel

import streamlit as st
import json
from nba_api.stats.static import players
from nba_api.stats.static import teams as static_teams
from nba_api.stats.endpoints import leaguedashplayerstats, PlayerGameLog, scoreboardv2
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, date
from collections import defaultdict

st.set_page_config(page_title="ICE PROP LAB", layout="wide", initial_sidebar_state="expanded")

# ── Session state ───────────────────────────────────────────────────────────────
if 'my_board' not in st.session_state:
    st.session_state.my_board = []
if 'next_opponent' not in st.session_state:
    st.session_state.next_opponent = None
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

# Create a lookup for player team -> current matchup label
matchup_lookup = {}
for g in games_today:
    label = f"{g['away']} @ {g['home']}"
    matchup_lookup[g['away']] = label
    matchup_lookup[g['home']] = label

# ── Game filter dropdown – top of sidebar ──────────────────────────────────────
st.sidebar.markdown("**Today's Matchups**")

if num_games == 0:
    st.sidebar.caption("No games found today")
    selected_game = None
else:
    game_options = ["— All Games —"]
    game_values  = [None]

    for g in games_today:
        label = f"{g['away']} @ {g['home']}  •  {g['status']}"
        game_options.append(label)
        game_values.append((g['away'], g['home']))

    current_filter = st.session_state.filter_teams
    default_index = 0
    if current_filter:
        try:
            match_label = f"{current_filter[0]} @ {current_filter[1]}"
            # Find index matching the label portion
            for i, opt in enumerate(game_options):
                if match_label in opt:
                    default_index = i
                    break
        except ValueError:
            pass

    selected_idx = st.sidebar.selectbox(
        "Filter by game",
        options=range(len(game_options)),
        format_func=lambda i: game_options[i],
        index=default_index,
        label_visibility="collapsed",
        key="game_filter_select"
    )

    selected_game = game_values[selected_idx]

    if selected_game is None:
        if st.session_state.filter_teams is not None:
            st.session_state.filter_teams = None
            st.session_state.next_opponent = None
    else:
        away, home = selected_game
        if st.session_state.filter_teams != (away, home):
            st.session_state.filter_teams = (away, home)
            st.session_state.next_opponent = home

if st.session_state.filter_teams:
    a, h = st.session_state.filter_teams
    st.sidebar.caption(f"Active filter: **{a} @ {h}**")
else:
    st.sidebar.caption(f"{num_games} game{'s' if num_games != 1 else ''} today" if num_games > 0 else "No games scheduled")

st.sidebar.markdown("---")

# ── Season helpers ──────────────────────────────────────────────────────────────
def get_current_season():
    today = datetime.today()
    return f"{today.year}-{str(today.year + 1)[-2:]}" if today.month >= 10 else f"{today.year-1}-{str(today.year)[-2:]}"

CURRENT_SEASON = get_current_season()
current_year = int(CURRENT_SEASON.split('-')[0])
PREVIOUS_SEASON = f"{current_year - 1}-{str(current_year)[-2:]}"

# ── Styling ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main {background: linear-gradient(135deg, #0a1a2f 0%, #001122 100%);}
    h1, h2, h3 {font-family: 'Exo 2', sans-serif; color: #00e0ff !important; text-shadow: 0 0 20px #00e0ff;}
    .stButton>button {background: linear-gradient(45deg, #003366, #00aaff) !important; color: white !important; border: 1px solid #00e0ff !important; font-weight: 700; border-radius: 8px;}
    .hit-box {background:rgba(10,30,60,0.7); padding:10px; border-radius:10px; border:1px solid #00aaff; margin-bottom:12px;}
    .highlight-stat {background: rgba(0, 180, 120, 0.18); padding: 6px 10px; border-radius: 6px; border-left: 4px solid #00cc88;}
</style>
""", unsafe_allow_html=True)

# ── Helpers ─────────────────────────────────────────────────────────────────────
def dropdown_values():
    return [None] + [round(x, 1) for x in np.arange(0.5, 60.6, 1.0)]

def get_player_id(name):
    for p in players.get_players():
        if p['full_name'].lower() == name.lower(): return p['id']
    return None

def get_hitrate_edge(hitrate_str: str) -> float:
    if not hitrate_str or "AVG:" not in hitrate_str: return 0.0
    try:
        avg_part = hitrate_str.split("AVG:")[1]
        o_pct = float(avg_part.split("O ")[1].split("%")[0].strip())
        return max(o_pct, 100 - o_pct) - 50
    except: return 0.0

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

@st.cache_data(ttl=300)
def get_player_games(pid):
    for season in [CURRENT_SEASON, PREVIOUS_SEASON]:
        try:
            df = PlayerGameLog(player_id=str(pid), season=season, season_type_all_star='Regular Season').get_data_frames()[0]
            if not df.empty:
                df["GAME_DATE_DT"] = pd.to_datetime(df["GAME_DATE"])
                df["GAME_DATE"] = df["GAME_DATE_DT"].dt.strftime("%m/%d")
                return df.sort_values("GAME_DATE_DT", ascending=False).reset_index(drop=True)
        except: continue
    return pd.DataFrame()

# ── Load and Filter Player List ────────────────────────────────────────────────
player_team_map = get_active_players_with_teams()
player_options = []
for p in players.get_players():
    pid_str = str(p["id"])
    if pid_str in player_team_map:
        team = player_team_map[pid_str]
        if st.session_state.filter_teams and team not in st.session_state.filter_teams: 
            continue
        player_options.append((f"{p['full_name']} • {team}", p['full_name']))

player_options.sort(key=lambda x: x[1].lower())
player_list_display = [opt[0] for opt in player_options]
player_list_clean = [opt[1] for opt in player_options]

common_teams = ["— Any —"] + sorted(['ATL','BOS','BKN','CHA','CHI','CLE','DAL','DEN','DET','GSW','HOU','IND','LAC','LAL','MEM','MIA','MIL','MIN','NOP','NYK','OKC','ORL','PHI','PHX','POR','SAC','SAS','TOR','UTA','WAS'])

available_stats = ['PTS', 'REB', 'AST', 'STL', 'BLK', 'TOV', 'FGM', 'FGA', 'FG3M', 'FG3A', '2PM', '2PA', 'Pts+Reb', 'Pts+Ast', 'Ast+Reb', 'Stl+Blk', 'PRA']
odds_options = ["", "-300", "-275", "-250", "-225", "-200", "-190", "-180", "-170", "-160", "-155", "-150", "-145", "-140", "-135", "-130", "-125", "-120", "-115", "-110", "-105", "-100", "+100", "+105", "+110", "+115", "+118", "+120", "+125", "+130", "+135", "+140", "+145", "+150", "+155", "+160", "+165", "+170", "+175", "+180", "+185", "+190", "+195", "+200", "+210", "+220", "+230", "+240", "+250", "+275", "+300"]

# ── Sidebar ─────────────────────────────────────────────────────────────────────
top_row = st.sidebar.columns([3, 2, 2])
with top_row[0]:
    selected_display = st.selectbox("Player", ["— Choose player —"] + player_list_display, key="player_select", label_visibility="collapsed")
with top_row[1]:
    selected_stat = st.selectbox("Stat", ["— Select stat —"] + available_stats, index=1, key="stat_select", label_visibility="collapsed")
with top_row[2]:
    default_opp_idx = 0
    if st.session_state.next_opponent and st.session_state.next_opponent in common_teams:
        default_opp_idx = common_teams.index(st.session_state.next_opponent)
    
    next_opp = st.selectbox("Opponent", common_teams, index=default_opp_idx, key="opp_select", label_visibility="collapsed")

st.session_state.next_opponent = None if next_opp == "— Any —" else next_opp

selected_player = next((clean for disp, clean in player_options if disp == selected_display), None)
pid = get_player_id(selected_player) if selected_player else None
player_team = player_team_map.get(str(pid), "???") if pid else "???"

lines = {}
if selected_stat and selected_stat != "— Select stat —":
    st.sidebar.markdown(f"**{selected_stat} line**")
    val = st.sidebar.selectbox(f"{selected_stat} line", dropdown_values(), format_func=lambda x: "—" if x is None else f"{x}", key=f"line_{selected_stat}", label_visibility="collapsed")
    if val is not None: lines[selected_stat] = val

# --- My Board Grouped by Game ---
st.sidebar.header(f"📋 My Board ({len(st.session_state.my_board)})")
if not st.session_state.my_board:
    st.sidebar.caption("No props saved. Pin with 📌")
else:
    board_sorted = sorted(st.session_state.my_board, key=lambda x: (get_hitrate_edge(x.get("hitrate_str","")), x.get("timestamp","")), reverse=True)
    grouped = defaultdict(list)
    for item in board_sorted:
        matchup = item.get("matchup", "Other")
        grouped[matchup].append(item)
    
    for matchup, props in grouped.items():
        with st.sidebar.expander(f"🏀 {matchup}", expanded=True):
            for item in props:
                col1, col2 = st.columns([6,1])
                with col1:
                    odds_d = f" {item['odds']}" if item.get('odds') else ""
                    st.markdown(f"**{item['player']} • {item['team']}**<br><small>{item['stat']} {item['line']}{odds_d} {item['hitrate_str']}</small>", unsafe_allow_html=True)
                with col2:
                    if st.button("×", key=f"rm_{item['player']}_{item['stat']}_{item['timestamp']}"):
                        st.session_state.my_board = [i for i in st.session_state.my_board if i != item]
                        st.rerun()

st.sidebar.markdown("---")
bottom_row = st.sidebar.columns([2, 1])
with bottom_row[0]: 
    games_to_show = st.selectbox("Recent games", [5,10,15,20], index=2, label_visibility="collapsed")
with bottom_row[1]:
    if st.button("🔄"): 
        st.cache_data.clear()
        st.rerun()

# ── Data Management (Bottom) ──────────────────────────────────────────────────
st.sidebar.markdown("### 💾 Data Management")

def get_board_json():
    # Helper to serialize timestamps to ISO strings
    data = []
    for entry in st.session_state.my_board:
        item = entry.copy()
        # Ensure timestamp is string for JSON
        if isinstance(item.get('timestamp'), datetime):
            item['timestamp'] = item['timestamp'].isoformat()
        data.append(item)
    return json.dumps(data)

# Create a dynamic filename: board_YYYYMMDD_HHMM.json
dynamic_filename = f"board_{datetime.now().strftime('%Y%m%d_%H%M')}.json"

st.sidebar.download_button(
    label="Download Board", 
    data=get_board_json(), 
    file_name=dynamic_filename, 
    mime="application/json"
)

uploaded_file = st.sidebar.file_uploader("Upload Board", type="json")
if uploaded_file is not None:
    try:
        data = json.load(uploaded_file)
        # Convert the ISO string back into a datetime object for each entry
        for entry in data:
            if isinstance(entry.get('timestamp'), str):
                entry['timestamp'] = datetime.fromisoformat(entry['timestamp'])
        
        st.session_state.my_board = data
        st.sidebar.success("Board restored successfully!")
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Error loading file: {e}")

# ── Main content ────────────────────────────────────────────────────────────────
if not selected_player:
    st.info("Select a player from the sidebar.")
    st.stop()

df = get_player_games(pid)
if df.empty: 
    st.stop()

df["Pts+Ast"] = df["PTS"] + df["AST"]
df["Pts+Reb"] = df["PTS"] + df["REB"]
df["Ast+Reb"] = df["AST"] + df["REB"]
df["Stl+Blk"] = df["STL"] + df["BLK"]
df["PRA"]     = df["PTS"] + df["REB"] + df["AST"]

if st.session_state.next_opponent:
    opp = st.session_state.next_opponent
    df_filtered = df[df['MATCHUP'].str.contains(opp)]
    table_title = f"Games vs {opp} (last {len(df_filtered)})"
else:
    df_filtered = df
    table_title = f"Recent Game Log (last 15)"

st.markdown("---")

if lines:
    pdata = df.sort_values("GAME_DATE_DT", ascending=False)
    for stat, line in lines.items():
        over_list = []
        for w in [5,10,15]:
            if len(pdata) >= w: 
                over_list.append((pdata.head(w)[stat] > line).mean() * 100)
        
        parts = [f"<span style='color:{('#00ff88' if p > 73 else '#ffcc00' if p >= 60 else '#ff5555')}'>{p:.0f}%</span>" for p in over_list]
        hit_str = " | ".join(parts)
        avg_o = np.mean(over_list)
        avg_u = 100 - avg_o
        avg_text = f" — AVG: <span style='color:{('#00ff88' if avg_o > 75 else '#ffcc00' if avg_o >= 61 else '#ff5555')}'>O {avg_o:.0f}%</span> / <span style='color:{('#00ff88' if avg_u > 75 else '#ffcc00' if avg_u >= 61 else '#ff5555')}'>U {avg_u:.0f}%</span>"
        
        c1, c2, c3 = st.columns([6, 3, 1])
        with c1: 
            st.markdown(f"<div class='hit-box'><strong>{stat} {line}</strong> {hit_str}{avg_text}</div>", unsafe_allow_html=True)
        with c2: 
            odds_key = f"odds_{selected_player}_{stat}"
            st.selectbox("Odds", odds_options, key=odds_key, label_visibility="collapsed")
        with c3:
            if st.button("📌", key=f"pin_{stat}"):
                player_matchup = matchup_lookup.get(player_team, "Other/Unknown")
                
                entry = {
                    "player": selected_player, 
                    "team": player_team, 
                    "matchup": player_matchup,
                    "stat": stat, 
                    "line": f"{line:.1f}", 
                    "odds": st.session_state.get(odds_key, ""), 
                    "hitrate_str": hit_str + avg_text, 
                    "timestamp": datetime.now()
                }
                if not any(e['player']==entry['player'] and e['stat']==entry['stat'] and e['line']==entry['line'] for e in st.session_state.my_board):
                    st.session_state.my_board.append(entry)
                    st.toast(f"Pinned {selected_player}", icon="📌")
                    st.rerun()

        fig = go.Figure()
        colors = ["#00ff88" if v > line else "#ff4444" for v in df.head(15)[stat]]
        fig.add_trace(go.Bar(x=df.head(15)["GAME_DATE"], y=df.head(15)[stat], marker_color=colors, text=df.head(15)[stat].round(1), textposition="inside"))
        fig.add_hline(y=line, line_dash="dash", line_color="#00ffff")
        fig.update_layout(height=280, margin=dict(t=10,b=10), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#00e0ff")
        st.plotly_chart(fig, use_container_width=True)

recent_min = df.head(games_to_show)
if len(recent_min) >= 3:
    x_min = np.arange(len(recent_min))
    y_min = recent_min["MIN"].values
    slope_min, intercept_min = np.polyfit(x_min, y_min, 1)
    recent_avg_min = recent_min["MIN"].mean()
    projected_min = recent_avg_min + slope_min

    concern_min = "🟢 Solid" if projected_min >= 32 else "🟡 Some concern <32" if projected_min >= 28 else "🔴 High risk"
    arrow_min = "↑" if slope_min > 0.3 else "↓" if slope_min < -0.3 else "→"
    st.markdown(f"**Projected next min**: ≈ **{projected_min:.1f}**  ({arrow_min} {slope_min:.1f} min/game) — **{concern_min}**")

    fig_min = go.Figure()
    colors_min = ["#00ff88" if m >= 35 else "#88ff88" if m >= 30 else "#ffff88" if m >= 25 else "#ffcc88" if m >= 20 else "#ff8888" for m in recent_min["MIN"]]
    fig_min.add_trace(go.Bar(x=recent_min["GAME_DATE"], y=recent_min["MIN"], marker_color=colors_min, text=recent_min["MIN"].round(1), textposition="auto", textfont=dict(color="#000")))
    fig_min.add_hline(y=recent_avg_min, line_dash="dot", line_color="#00e0ff", annotation_text=f"Avg: {recent_avg_min:.1f}", annotation_position="top right")
    fig_min.add_trace(go.Scatter(x=recent_min["GAME_DATE"], y=slope_min * x_min + intercept_min, mode='lines', line=dict(color='#00e0ff', width=2, dash='dash')))
    fig_min.update_layout(height=340, showlegend=False, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#00e0ff", margin=dict(t=20,b=40,l=30,r=30))
    st.plotly_chart(fig_min, use_container_width=True)

with st.expander(f"📊 {table_title}", expanded=False):
    display_cols = ["GAME_DATE", "MATCHUP", "WL", "MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV", "FG3M", "+/-"]
    available_cols = [c for c in display_cols if c in df_filtered.columns]
    
    def highlight_minutes(val):
        if pd.isna(val): return ''
        color = '#00cc88' if val >= 32 else '#ffcc00' if val >= 28 else '#ff5555'
        return f'background-color: {color}; color: black'
    
    styled_df = df_filtered.head(15)[available_cols].style\
        .format(precision=1)\
        .map(highlight_minutes, subset=pd.IndexSlice[:, ['MIN'] if 'MIN' in available_cols else []])
    
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

st.markdown("<p style='text-align:center; color:#88f0ff; padding-top:2rem;'>ICE PROP LAB • 2025-26</p>", unsafe_allow_html=True)
