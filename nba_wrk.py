# nba_wrk.py – NBA Hit Tracker • Single Player + Persistent Opponent + DvP Panel

import streamlit as st
import json
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
    return f"{today.year}-{str(today.year + 1)[-2:]}" if today.month >= 10 else f"{today.year-1}-{str(today.year)[-2:]}"

CURRENT_SEASON = get_current_season()
current_year = int(CURRENT_SEASON.split('-')[0])
PREVIOUS_SEASON = f"{current_year - 1}-{str(current_year)[-2:]}"

st.set_page_config(page_title="NBA Hit Tracker", layout="wide", initial_sidebar_state="expanded")

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

# ── Helpers ─────────────────────────────────────────────────────────────────────
def dropdown_values():
    return [None] + [round(x, 1) for x in np.arange(0.5, 60.6, 1.0)]

def get_player_id(name):
    for p in players.get_players():
        if p['full_name'].lower() == name.lower():
            return p['id']
    return None

# ── Sidebar: Game Filter + Player ───────────────────────────────────────────────
st.sidebar.markdown("### Today's Games & Player")

top_filters = st.sidebar.columns([2.2, 2.8])

with top_filters[0]:
    game_options = ["— All Players —"]
    game_labels_to_teams = {"— All Players —": None}
    for g in games_today:
        label = f"{g['away']} @ {g['home']}  ({g['status']})"
        game_options.append(label)
        game_labels_to_teams[label] = (g['away'], g['home'])

    selected_game_label = st.selectbox(
        "Filter by game", game_options, index=0,
        label_visibility="collapsed", key="game_filter_select"
    )

    if selected_game_label == "— All Players —":
        st.session_state.filter_teams = None
    else:
        st.session_state.filter_teams = game_labels_to_teams[selected_game_label]

with top_filters[1]:
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

    player_team_map = get_active_players_with_teams()

    player_options = []
    for p in players.get_players():
        pid_str = str(p["id"])
        if pid_str not in player_team_map:
            continue
        team = player_team_map[pid_str]
        if st.session_state.filter_teams is not None and team not in st.session_state.filter_teams:
            continue
        player_options.append((f"{p['full_name']} • {team}", p['full_name']))

    player_options.sort(key=lambda x: x[1].lower())
    player_list_display = [opt[0] for opt in player_options]

    selected_display = st.selectbox(
        "Player", ["— Choose player —"] + player_list_display,
        key="player_select", label_visibility="collapsed"
    )

selected_player = next((clean for disp, clean in player_options if disp == selected_display), None)
pid = get_player_id(selected_player) if selected_player else None
player_team = player_team_map.get(str(pid), "???") if pid else "???"

# ── Stat • Line • Odds • Pin • Download (All on ONE line) ───────────────────────
st.sidebar.markdown("### Stat • Line • Odds • Actions")

available_stats = ['PTS', 'FG3M','AST','REB', 'Ast+Reb', 'STL', 'BLK', 'TOV', 'FGM', 'FGA',  
                   'FG3A', '2PM', '2PA', 'Pts+Reb', 'Pts+Ast', 'Stl+Blk', 'PRA']

odds_options = ["", "-300", "-275", "-250","-245","-240","-235","-230", "-225", "-220",
                "-215","-210","-205","-200", "-195","-190", "-185","-180","-175", "-170",
                "-165","-160", "-155", "-150", "-145", "-140", "-135", "-130", "-125",
                "-120", "-115", "-112" ,"-110", "-105", "-100", "+100", "+102", "+105",
                "+110", "+115", "+118", "+120", "+125", "+130", "+135", "+140", "+145",
                "+150", "+155", "+160", "+165", "+170", "+175", "+180", "+185", "+190",
                "+195", "+200", "+210", "+220", "+230", "+240", "+250", "+275", "+300"]

lines = {}
selected_stat = None
odds_key = None
pin_clicked = False   # ← Fixed: Initialized here

if selected_player:
    cols = st.sidebar.columns([1.5, 1.3, 1.3, 0.9, 0.9])
    
    with cols[0]:
        selected_stat = st.selectbox(
            "Stat", ["— Select stat —"] + available_stats, 
            index=1, key="stat_select", label_visibility="collapsed"
        )
    
    with cols[1]:
        line_val = st.selectbox(
            "Line", dropdown_values(), 
            format_func=lambda x: "—" if x is None else f"{x:.1f}", 
            key="line_key", label_visibility="collapsed"
        )
        if line_val is not None and selected_stat and selected_stat != "— Select stat —":
            lines[selected_stat] = line_val
    
    with cols[2]:
        odds_key = f"odds_{selected_player}_{selected_stat if selected_stat else 'none'}"
        st.selectbox("Odds", odds_options, key=odds_key, label_visibility="collapsed")
    
    with cols[3]:
        pin_clicked = st.button("📌 Pin", use_container_width=True, type="primary")
    
    with cols[4]:
        def get_board_json():
            data = []
            for entry in st.session_state.my_board:
                item = entry.copy()
                if isinstance(item.get('timestamp'), datetime):
                    item['timestamp'] = item['timestamp'].isoformat()
                data.append(item)
            return json.dumps(data)

        st.download_button(
            label="↓ Board",
            data=get_board_json(),
            file_name=f"board_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
            use_container_width=True
        )
else:
    st.sidebar.info("Select a player above")

# ── Pin Logic ───────────────────────────────────────────────────────────────────
if pin_clicked and selected_player and selected_stat and selected_stat != "— Select stat —" and \
   selected_stat in lines and df is not None and not df.empty:   # df check moved after df is defined

    line = lines[selected_stat]
    pdata = df.sort_values("GAME_DATE_DT", ascending=False).copy()

    windows = [5, 10]
    windows = [w for w in windows if len(pdata) >= w]

    over_list = []
    for w in windows:
        recent_w = pdata.head(w)
        hit_pct = (recent_w[selected_stat] > line).mean() * 100
        over_list.append(hit_pct)

    window_labels = [f"L{w}" for w in windows]
    parts = []
    for pct, lbl in zip(over_list, window_labels):
        color = '#00ff88' if pct > 73 else '#ffcc00' if pct >= 60 else '#ff5555'
        parts.append(f"<span style='color:{color}'>{pct:.0f}%</span> ({lbl})")
    
    hit_str = " | ".join(parts)
    recent_avg_min_val = pdata.head(10)["MIN"].mean()

    results = (pdata[selected_stat] > line).tolist()
    streak_type = "O" if results[0] else "U"
    streak_count = 0
    for r in results:
        if (r and streak_type == "O") or (not r and streak_type == "U"):
            streak_count += 1
        else:
            break

    avg_o = np.mean(over_list)
    avg_u = 100 - avg_o
    avg_color_o = '#00ff88' if avg_o > 75 else '#ffcc00' if avg_o >= 61 else '#ff5555'
    avg_color_u = '#00ff88' if avg_u > 75 else '#ffcc00' if avg_u >= 61 else '#ff5555'
    
    avg_text = (
        f" AVG: <span style='color:{avg_color_o}'>O {avg_o:.0f}%</span> / "
        f"<span style='color:{avg_color_u}'>U {avg_u:.0f}%</span> | "
        f"**Avg MIN: {recent_avg_min_val:.1f}** | **{streak_type}{streak_count}**"
    )
    hitrate_str = hit_str + avg_text

    player_matchup = matchup_lookup.get(player_team, "Other/Unknown")
    
    entry = {
        "player": selected_player,
        "team": player_team,
        "matchup": player_matchup,
        "stat": selected_stat,
        "line": f"{line:.1f}",
        "odds": st.session_state.get(odds_key, ""),
        "hitrate_str": hitrate_str,
        "timestamp": datetime.now()
    }

    if not any(e['player'] == entry['player'] and e['stat'] == entry['stat'] and e['line'] == entry['line'] 
               for e in st.session_state.my_board):
        st.session_state.my_board.append(entry)
        st.toast(f"Pinned → {selected_player} • {selected_stat} {line}", icon="📌")
        st.rerun()

# ── My Dashboard ────────────────────────────────────────────────────────────────
if st.session_state.my_board:
    dash_df = pd.DataFrame(st.session_state.my_board)
    dash_df['match_key'] = dash_df['matchup']
    
    for match, group in dash_df.groupby('match_key'):
        total_payout = 1.0
        try:
            multiplier = 1.0
            for _, row in group.iterrows():
                o = row['odds']
                if not o or o.strip() == "": continue
                val = float(str(o).replace('+', ''))
                if val > 0:
                    multiplier *= (val / 100 + 1)
                else:
                    multiplier *= (100 / abs(val) + 1)
            total_payout = multiplier
        except:
            total_payout = 1.0

        prop_count = len(group)

        col_left, col_middle, col_right = st.sidebar.columns([0.12, 0.76, 0.12])

        with col_left:
            st.checkbox("", key=f"check_{match}", label_visibility="collapsed")

        with col_middle:
            with st.expander(
                f"🏀 {match} | :green[${total_payout:.2f}] | ({prop_count})",
                expanded=True
            ):
                group_sorted = group.sort_values(by='timestamp', ascending=False)
                for _, entry in group_sorted.iterrows():
                    col_t, col_d = st.columns([0.8, 0.2])
                    with col_t:
                        odds_d = f" @ **{entry['odds']}**" if entry.get('odds') else ""
                        st.markdown(
                            f"**{entry['player']} • {entry['team']}**"
                            f" | > {entry['stat']} {entry['line']}{odds_d}<br>"
                            f"<small>{entry.get('hitrate_str', '—')}</small>",
                            unsafe_allow_html=True
                        )
                    with col_d:
                        if st.button("🗑️", key=f"del_{entry['player']}_{entry['stat']}_{str(entry.get('timestamp',''))}"):
                            st.session_state.my_board = [
                                d for d in st.session_state.my_board
                                if not (d['player'] == entry['player'] and 
                                        d['stat'] == entry['stat'] and 
                                        d['line'] == entry['line'])
                            ]
                            st.rerun()

        with col_right:
            if st.button("x", key=f"del_group_{match}", help="Delete entire group"):
                st.session_state.my_board = [
                    d for d in st.session_state.my_board
                    if d['matchup'] != match
                ]
                st.rerun()
else:
    st.sidebar.caption("No props saved. Pin some above!")

st.sidebar.divider()

# ── Load Player Game Log ────────────────────────────────────────────────────────
df = None
if pid:
    @st.cache_data(ttl=300)
    def get_player_games_cached(pid_str):
        for season in [CURRENT_SEASON, PREVIOUS_SEASON]:
            try:
                df_log = PlayerGameLog(
                    player_id=pid_str, 
                    season=season, 
                    season_type_all_star='Regular Season'
                ).get_data_frames()[0]
                if not df_log.empty:
                    df_log["GAME_DATE_DT"] = pd.to_datetime(df_log["GAME_DATE"])
                    df_log["GAME_DATE"] = df_log["GAME_DATE_DT"].dt.strftime("%m/%d")
                    return df_log.sort_values("GAME_DATE_DT", ascending=False).reset_index(drop=True)
            except:
                continue
        return pd.DataFrame()

    df = get_player_games_cached(str(pid))
    if not df.empty:
        df["Pts+Ast"] = df["PTS"] + df["AST"]
        df["Pts+Reb"] = df["PTS"] + df["REB"]
        df["Ast+Reb"] = df["AST"] + df["REB"]
        df["Stl+Blk"] = df["STL"] + df["BLK"]
        df["PRA"]     = df["PTS"] + df["REB"] + df["AST"]

# ── Main Content ────────────────────────────────────────────────────────────────
if not selected_player or df is None or df.empty:
    st.info("Select a player from the sidebar to get started.")
    st.stop()

st.markdown("---")

# Hit rate display + Charts
if lines:
    pdata = df.sort_values("GAME_DATE_DT", ascending=False).copy()
    
    for stat, line in lines.items():
        windows = [5, 10]
        windows = [w for w in windows if len(pdata) >= w]
        
        over_list = [(pdata.head(w)[stat] > line).mean() * 100 for w in windows]
        
        window_labels = [f"L{w}" for w in windows]
        parts = []
        for pct, lbl in zip(over_list, window_labels):
            color = '#00ff88' if pct > 73 else '#ffcc00' if pct >= 60 else '#ff5555'
            parts.append(f"<span style='color:{color}'>{pct:.0f}%</span> ({lbl})")
        
        hit_str = " | ".join(parts)
        avg_o = np.mean(over_list)
        avg_u = 100 - avg_o
        avg_color_o = '#00ff88' if avg_o > 75 else '#ffcc00' if avg_o >= 61 else '#ff5555'
        avg_color_u = '#00ff88' if avg_u > 75 else '#ffcc00' if avg_u >= 61 else '#ff5555'
        
        avg_text = f" AVG: <span style='color:{avg_color_o}'>O {avg_o:.0f}%</span> / <span style='color:{avg_color_u}'>U {avg_u:.0f}%</span>"
        
        st.markdown(
            f"<div style='background:#1e1e2e;padding:12px;border-radius:8px;margin:8px 0;'>"
            f"<strong>{stat} {line}</strong> {hit_str}{avg_text}</div>",
            unsafe_allow_html=True
        )

        if len(pdata) > 0:
            n = min(10, len(pdata))
            recent_data = pdata.head(n)
            res_main = (recent_data[stat] > line).tolist()
            s_type = "O" if res_main[0] else "U"
            s_count = 0
            for r in res_main:
                if (r and s_type == "O") or (not r and s_type == "U"):
                    s_count += 1
                else:
                    break
            
            st.markdown(f"**Current Streak: {s_type}{s_count}**")
            
            fig = go.Figure()
            colors = ["#00ff88" if v > line else "#ff4444" for v in recent_data[stat]]
            text_colors = ["#000" if val > 10 else "#fff" for val in recent_data[stat]]
            
            fig.add_trace(go.Bar(
                x=recent_data["GAME_DATE"],
                y=recent_data[stat],
                marker_color=colors,
                text=recent_data[stat].round(1),
                textposition="inside",
                textfont={"color": text_colors}
            ))
            fig.add_hline(y=line, line_dash="dash", line_color="#00ffff",
                          annotation_text=f"line = {line}", annotation_position="top right")
            
            fig.update_layout(
                height=320, margin=dict(t=50, b=40, l=20, r=20),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font_color="#00e0ff", xaxis_title="Game Date", yaxis_title=stat
            )
            st.plotly_chart(fig, use_container_width=True)

# Minutes Projection
recent_min = df.head(10)
if len(recent_min) >= 3:
    x_min = np.arange(len(recent_min))
    y_min = recent_min["MIN"].values
    slope_min, intercept_min = np.polyfit(x_min, y_min, 1)
    recent_avg_min = recent_min["MIN"].mean()
    projected_min = recent_avg_min + slope_min

    concern_min = "🟢 Solid" if projected_min >= 32 else "🟡 Some concern" if projected_min >= 28 else "🔴 High risk"
    arrow_min = "↑" if slope_min > 0.3 else "↓" if slope_min < -0.3 else "→"
    
    st.markdown(f"**Projected Minutes**: ≈ **{projected_min:.1f}** | "
                f"**Avg (L10)**: **{recent_avg_min:.1f}** ({arrow_min} {slope_min:.1f}) — **{concern_min}**")

# Game Log
with st.expander("📊 Full Recent Game Log (Last 15)", expanded=False):
    display_cols = ["GAME_DATE", "MATCHUP", "WL", "MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV", "FG3M", "FG3A", "+/-"]
    available_cols = [c for c in display_cols if c in df.columns]
    
    def highlight_minutes(val):
        if pd.isna(val): return ''
        color = '#00cc88' if val >= 32 else '#ffcc00' if val >= 28 else '#ff5555'
        return f'background-color: {color}; color: black'
    
    styled_df = df.head(15)[available_cols].style\
        .format(precision=1)\
        .map(highlight_minutes, subset=['MIN'] if 'MIN' in available_cols else [])
    
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

st.markdown("<p style='text-align:center; color:#88f0ff; padding-top:2rem;'>ICE PROP LAB • 2025-26</p>", unsafe_allow_html=True)
