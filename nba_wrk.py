import streamlit as st
import json
import base64
from nba_api.stats.static import players
from nba_api.stats.static import teams as static_teams
from nba_api.stats.endpoints import leaguedashplayerstats, leaguedashteamstats, PlayerGameLog, scoreboardv3
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

# ── Board persistence helpers ────────────────────────────────────────────────────
def _board_to_qp(board: list) -> str:
    """Serialize board → base64 string safe for a query param."""
    data = []
    for entry in board:
        item = entry.copy()
        if isinstance(item.get('timestamp'), datetime):
            item['timestamp'] = item['timestamp'].isoformat()
        data.append(item)
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()

def _qp_to_board(qp_val: str) -> list:
    """Deserialize base64 query param → board list."""
    try:
        data = json.loads(base64.urlsafe_b64decode(qp_val.encode()).decode())
        for entry in data:
            if isinstance(entry.get('timestamp'), str):
                try:
                    entry['timestamp'] = datetime.fromisoformat(entry['timestamp'])
                except Exception:
                    pass
        return data
    except Exception:
        return []

def _save_board():
    """Write current board into query params (called after every mutation)."""
    if st.session_state.my_board:
        st.query_params['board'] = _board_to_qp(st.session_state.my_board)
    else:
        st.query_params.pop('board', None)

# ── Session state ───────────────────────────────────────────────────────────────
if 'my_board' not in st.session_state:
    # Restore from query params on first load
    qp_board = st.query_params.get('board', '')
    st.session_state.my_board = _qp_to_board(qp_board) if qp_board else []
if 'filter_teams' not in st.session_state:
    st.session_state.filter_teams = None
if 'pending_load' not in st.session_state:
    st.session_state.pending_load = None
if 'board_order' not in st.session_state:
    st.session_state.board_order = []  # list of (player, stat, line) tuples defining sort order

# ── Team abbreviation lookup ────────────────────────────────────────────────────
@st.cache_data(ttl=86400)
def get_team_abbr_map():
    all_teams = static_teams.get_teams()
    return {str(t['id']): t['abbreviation'] for t in all_teams}

team_abbr_map = get_team_abbr_map()

# ── Opponent Defensive Rankings ─────────────────────────────────────────────────
# Maps stat category → NBA API column → label
DEF_STAT_MAP = {
    'PTS':     ('OPP_PTS',   'PTS allowed'),
    'REB':     ('OPP_REB',   'REB allowed'),
    'AST':     ('OPP_AST',   'AST allowed'),
    'STL':     ('OPP_STL',   'STL allowed'),
    'BLK':     ('OPP_BLK',   'BLK allowed'),
    'TOV':     ('OPP_TOV',   'TOV forced'),
    'FG3M':    ('OPP_FG3M',  '3PM allowed'),
    'Pts+Reb': ('OPP_PTS',   'PTS allowed'),   # fallback to PTS
    'Pts+Ast': ('OPP_PTS',   'PTS allowed'),
    'PRA':     ('OPP_PTS',   'PTS allowed'),
    'Ast+Reb': ('OPP_AST',   'AST allowed'),
    'Stl+Blk': ('OPP_STL',   'STL allowed'),
}

@st.cache_data(ttl=3600)
def get_opp_def_rankings(season: str):
    """Returns dict: team_abbr → {col: (rank, per_game_avg, total_teams)}"""
    try:
        df_opp = leaguedashteamstats.LeagueDashTeamStats(
            season=season,
            measure_type_detailed_defense="Opponent",
            per_mode_simple="PerGame",
        ).get_data_frames()[0]
        if df_opp.empty:
            return {}
        result = {}
        opp_cols = [c for c in df_opp.columns if c.startswith('OPP_')]
        for col in opp_cols:
            if col not in df_opp.columns:
                continue
            # Lower is better defensively for most stats (fewer allowed)
            # Exception: OPP_TOV — more TOV forced = better defense
            ascending = col != 'OPP_TOV'
            ranked = df_opp[['TEAM_ABBREVIATION', col]].copy()
            ranked['rank'] = ranked[col].rank(method='min', ascending=ascending).astype(int)
            for _, row in ranked.iterrows():
                abbr = row['TEAM_ABBREVIATION']
                if abbr not in result:
                    result[abbr] = {}
                result[abbr][col] = (int(row['rank']), round(float(row[col]), 1), len(ranked))
        return result
    except Exception:
        return {}

def get_def_rank_badge(opp_team: str, stat: str, rankings: dict) -> str:
    """Returns an HTML badge string for defensive rank of opp_team vs stat."""
    if not opp_team or not rankings or opp_team not in rankings:
        return ""
    api_col, label = DEF_STAT_MAP.get(stat, (None, None))
    if not api_col:
        return ""
    team_data = rankings.get(opp_team, {})
    if api_col not in team_data:
        return ""
    rank, avg, total = team_data[api_col]
    # Color: top 10 = green (easy), bottom 10 = red (tough), else yellow
    if rank <= 10:
        color = '#00ff88'
        difficulty = 'Easy'
    elif rank >= total - 9:
        color = '#ff5555'
        difficulty = 'Tough'
    else:
        color = '#ffcc00'
        difficulty = 'Mid'
    return (
        f"<span style='background:{color};color:#000;padding:1px 6px;"
        f"border-radius:4px;font-size:0.78em;font-weight:700;'>"
        f"DEF #{rank}/{total} {difficulty} ({avg} {label}/g)</span>"
    )

# ── Today's NBA Games ───────────────────────────────────────────────────────────
today_str = date.today().strftime("%Y-%m-%d")

@st.cache_data(ttl=300)
def get_todays_games(game_date: str):
    try:
        sb = scoreboardv3.ScoreboardV3(game_date=game_date, league_id="00")
        header_df    = sb.game_header.get_data_frame()
        line_score_df = sb.line_score.get_data_frame()

        if header_df.empty:
            return [], 0

        # line_score has 2 rows per game (away first, home second) with teamTricode
        # Build a lookup: gameId -> [away_tricode, home_tricode]
        team_by_game = {}
        for _, row in line_score_df.iterrows():
            gid = str(row['gameId'])
            team_by_game.setdefault(gid, []).append(row['teamTricode'])

        games = []
        seen_ids = set()
        for _, row in header_df.iterrows():
            game_id_str = str(row['gameId'])
            if game_id_str in seen_ids:
                continue
            seen_ids.add(game_id_str)

            tricodes = team_by_game.get(game_id_str, ['???', '???'])
            away_abbr = tricodes[0] if len(tricodes) > 0 else '???'
            home_abbr = tricodes[1] if len(tricodes) > 1 else '???'
            status    = row.get('gameStatusText', '')

            if game_id_str[3:5] == '04':
                game_type = ' 🏆'
            elif game_id_str[3:5] == '05':
                game_type = ' 🎟️'
            else:
                game_type = ''

            games.append({
                'away': away_abbr,
                'home': home_abbr,
                'status': status,
                'game_type': game_type,
            })
        return games, len(games)
    except Exception as e:
        st.warning(f"Could not load today's games: {str(e)}")
        return [], 0

games_today, num_games = get_todays_games(today_str)

# Matchup lookup
matchup_lookup = {}
for g in games_today:
    label = f"{g['away']} @ {g['home']}{g.get('game_type', '')}"
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
    """Returns the opponent abbreviation for the selected game."""
    if not selected_game_label or selected_game_label == "— All Players —":
        return None
    for g in games_today:
        label = f"{g['away']} @ {g['home']}{g.get('game_type', '')}  ({g['status']})"
        if label == selected_game_label:
            return g['home'] if g['away'] == player_team else g['away']
    return None

# ── Apply pending_load (from clicking a pinned prop) ────────────────────────────
if st.session_state.pending_load is not None:
    _pl = st.session_state.pending_load
    st.session_state.pending_load = None
    # Game filter: find the matching label for the player's team
    _team = _pl.get('team')
    _matched_game = "— All Players —"
    for g in games_today:
        label = f"{g['away']} @ {g['home']}{g.get('game_type', '')}  ({g['status']})"
        if _team and _team in (g['away'], g['home']):
            _matched_game = label
            break
    st.session_state['game_filter_select'] = _matched_game
    # Player: find matching display string (name • team)
    _player_name = _pl.get('player')
    _player_team = _pl.get('team')
    _player_display = f"{_player_name} • {_player_team}" if _player_name and _player_team else None
    if _player_display:
        st.session_state['player_select'] = _player_display
    # Stat
    _stat = _pl.get('stat')
    if _stat:
        st.session_state['stat_select'] = _stat
    # Line
    _line = _pl.get('line')
    if _line is not None:
        try:
            st.session_state['line_key'] = float(_line)
        except (ValueError, TypeError):
            pass

# ── Sidebar: Game Filter + Player ───────────────────────────────────────────────
st.sidebar.markdown("### Today's Games & Player")

top_filters = st.sidebar.columns([2.2, 2.8])

with top_filters[0]:
    game_options = ["— All Players —"]
    game_labels_to_teams = {"— All Players —": None}

    for g in games_today:
        label = f"{g['away']} @ {g['home']}{g.get('game_type', '')}  ({g['status']})"
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
        season_types = ["Playoffs", "PlayIn", "Regular Season"]
        for season in [CURRENT_SEASON, PREVIOUS_SEASON]:
            combined = {}
            for stype in season_types:
                try:
                    df = leaguedashplayerstats.LeagueDashPlayerStats(
                        season=season, season_type_all_star=stype
                    ).get_data_frames()[0]
                    if not df.empty:
                        df = df[df['TEAM_ABBREVIATION'].notna() & (df['TEAM_ABBREVIATION'] != '')]
                        combined.update(dict(zip(df['PLAYER_ID'].astype(str), df['TEAM_ABBREVIATION'])))
                except:
                    continue
            if len(combined) > 80:
                return combined
        return {}

    player_team_map = get_active_players_with_teams()

    player_options = []
    for p in players.get_players():
        pid_str = str(p["id"])
        if pid_str not in player_team_map:
            continue
        team = player_team_map[pid_str]
        if st.session_state.filter_teams is not None:
            if team not in st.session_state.filter_teams:
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

# ── Stat • Line • Odds ─────────────────────────────────────────────────────────
available_stats = ['PTS', 'FG3M','AST','REB', 'Ast+Reb', 'STL', 'BLK', 'TOV', 'FGM', 'FGA',  
                   'FG3A', '2PM', '2PA', 'Pts+Reb', 'Pts+Ast', 'Stl+Blk', 'PRA']

odds_options = ["", "-300", "-275", "-250","-245","-240","-235","-230", "-225", "-220",
                "-215","-210","-205","-200", "-195","-190", "-185","-180","-175", "-170",
                "-165","-160", "-155", "-150", "-145", "-140", "-135", "-130", "-125",
                "-120", "-115", "-112" ,"-110", "-105", "-100", "+100", "+102", "+105",
                "+110", "+115", "+118", "+120", "+122", "+125", "+130", "+135", "+140", "+145",
                "+150", "+155", "+160", "+165", "+170", "+175", "+180", "+185", "+190",
                "+195", "+200", "+210", "+220", "+230", "+240", "+250", "+275", "+300"]

lines = {}
selected_stat = None
odds_key = None

if selected_player:
    col_stat, col_line, col_odds = st.sidebar.columns([1.8, 1.6, 1.6])
    
    with col_stat:
        selected_stat = st.selectbox(
            "Stat", ["— Select stat —"] + available_stats, 
            index=1, key="stat_select", label_visibility="collapsed"
        )
    
    with col_line:
        line_val = st.selectbox(
            "Line", dropdown_values(), 
            format_func=lambda x: "—" if x is None else f"{x:.1f}", 
            key="line_key", label_visibility="collapsed"
        )
        if line_val is not None and selected_stat and selected_stat != "— Select stat —":
            lines[selected_stat] = line_val
    
    with col_odds:
        odds_key = f"odds_{selected_player}_{selected_stat if selected_stat else 'none'}"
        st.selectbox("Odds", odds_options, key=odds_key, label_visibility="collapsed")
else:
    st.sidebar.info("Select a player to load options")

# ── Load Player Game Log ────────────────────────────────────────────────────────
df = None
if pid:
    @st.cache_data(ttl=300)
    def get_player_games_cached(pid_str):
        season_types = [
            ("Playoffs", "Playoffs"),
            ("PlayIn", "Play-In"),
            ("Regular Season", "Regular"),
        ]
        all_frames = []
        for season in [CURRENT_SEASON, PREVIOUS_SEASON]:
            for stype_api, stype_label in season_types:
                try:
                    df_log = PlayerGameLog(
                        player_id=pid_str,
                        season=season,
                        season_type_all_star=stype_api
                    ).get_data_frames()[0]
                    if not df_log.empty:
                        df_log["GAME_TYPE"] = stype_label
                        all_frames.append(df_log)
                except:
                    continue
            if all_frames:
                break  # found data for current season, stop

        if not all_frames:
            return pd.DataFrame()

        combined = pd.concat(all_frames, ignore_index=True)
        combined["GAME_DATE_DT"] = pd.to_datetime(combined["GAME_DATE"], format="%b %d, %Y", errors="coerce").fillna(
            pd.to_datetime(combined["GAME_DATE"], format="mixed", errors="coerce")
        )
        combined["GAME_DATE"] = combined["GAME_DATE_DT"].dt.strftime("%m/%d")
        combined = combined.drop_duplicates(subset=["GAME_ID"]) if "GAME_ID" in combined.columns else combined
        return combined.sort_values("GAME_DATE_DT", ascending=False).reset_index(drop=True)

    df = get_player_games_cached(str(pid))
    if not df.empty:
        df["Pts+Ast"] = df["PTS"] + df["AST"]
        df["Pts+Reb"] = df["PTS"] + df["REB"]
        df["Ast+Reb"] = df["AST"] + df["REB"]
        df["Stl+Blk"] = df["STL"] + df["BLK"]
        df["PRA"]     = df["PTS"] + df["REB"] + df["AST"]

# ── Pin Button ──────────────────────────────────────────────────────────────────
if (selected_player and selected_stat and selected_stat != "— Select stat —" and 
    selected_stat in lines and df is not None and not df.empty and 
    st.sidebar.button("📌 Pin to Board", use_container_width=True)):

    line = lines[selected_stat]
    pdata = df.sort_values("GAME_DATE_DT", ascending=False).copy()

    windows = [5, 10]
    windows = [w for w in windows if len(pdata) >= w]

    over_list = []
    for w in windows:
        recent_w = pdata.head(w)
        hit_pct = (recent_w[selected_stat] > line).mean() * 100
        over_list.append(hit_pct)

    parts = []
    for pct in over_list:
        color = '#00ff88' if pct > 73 else '#ffcc00' if pct >= 60 else '#ff5555'
        parts.append(f"<span style='color:{color}'>{pct:.0f}%</span>")
    
    hit_str = " | ".join(parts)
    recent_avg_min_val = pdata.head(10)["MIN"].mean()

    # Current streak
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

    # Trend arrow: compare L5 avg vs L6-10 avg to detect hot/cold
    trend_arrow = "→"
    trend_color = "#ffcc00"
    if len(pdata) >= 6:
        l5_avg  = pdata.head(5)[selected_stat].mean()
        l10_avg = pdata.head(10)[selected_stat].mean() if len(pdata) >= 10 else pdata[5:][selected_stat].mean()
        diff = l5_avg - l10_avg
        threshold = max(line * 0.08, 0.5)   # 8% of line or at least 0.5
        if diff > threshold:
            trend_arrow = "↑"
            trend_color = "#00ff88"
        elif diff < -threshold:
            trend_arrow = "↓"
            trend_color = "#ff5555"
    
    avg_text = (
        f" | Avg: <span style='color:{avg_color_o}'>O {avg_o:.0f}%</span> / "
        f"<span style='color:{avg_color_u}'>U {avg_u:.0f}%</span> | "
        f"<span style='color:#fff;'> Avg MIN: {recent_avg_min_val:.1f} | {streak_type}{streak_count}</span>"
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
        "timestamp": datetime.now(),
        "trend_arrow": trend_arrow,
        "trend_color": trend_color,
        "sort_order": len(st.session_state.my_board),
    }

    if not any(
        e['player'] == entry['player'] and 
        e['stat'] == entry['stat'] and 
        e['line'] == entry['line']
        for e in st.session_state.my_board
    ):
        st.session_state.my_board.append(entry)
        _save_board()
        st.toast(f"Pinned → {selected_player} • {selected_stat} {line}", icon="📌")
        st.rerun()

# ── My Dashboard ────────────────────────────────────────────────────────────────
if st.session_state.my_board:
    dash_df = pd.DataFrame(st.session_state.my_board)
    # Ensure sort_order exists for older pinned entries
    if 'sort_order' not in dash_df.columns:
        dash_df['sort_order'] = range(len(dash_df))
        for i, entry in enumerate(st.session_state.my_board):
            entry.setdefault('sort_order', i)
    dash_df['match_key'] = dash_df['matchup']

    def _move_prop(player, stat, line, direction):
        """Swap sort_order of the target prop with its neighbour within the same matchup."""
        board = st.session_state.my_board
        matchup = next((e['matchup'] for e in board if e['player']==player and e['stat']==stat and e['line']==line), None)
        if matchup is None:
            return
        group = sorted([e for e in board if e['matchup']==matchup], key=lambda x: x.get('sort_order', 0))
        idx = next((i for i, e in enumerate(group) if e['player']==player and e['stat']==stat and e['line']==line), None)
        if idx is None:
            return
        swap_idx = idx + direction
        if swap_idx < 0 or swap_idx >= len(group):
            return
        # Swap sort_order values
        a_key = (group[idx]['player'],  group[idx]['stat'],  group[idx]['line'])
        b_key = (group[swap_idx]['player'], group[swap_idx]['stat'], group[swap_idx]['line'])
        a_order = group[idx].get('sort_order', idx)
        b_order = group[swap_idx].get('sort_order', swap_idx)
        for e in board:
            if (e['player'], e['stat'], e['line']) == a_key:
                e['sort_order'] = b_order
            elif (e['player'], e['stat'], e['line']) == b_key:
                e['sort_order'] = a_order

    # Compact CSS injected once
    st.sidebar.markdown("""
<style>
/* tighten expander padding */
[data-testid="stExpander"] details { padding: 0 !important; }
[data-testid="stExpander"] summary { padding: 4px 8px !important; font-size:0.82em !important; }
/* shrink button height */
div[data-testid="stHorizontalBlock"] button[kind="secondary"] {
    padding: 1px 5px !important; font-size: 0.75em !important; min-height: 0 !important; height: 22px !important;
}
/* tighten spacing between board rows */
.prop-row { margin: 0; padding: 2px 0; line-height: 1.3; }
</style>""", unsafe_allow_html=True)

    for match, group in dash_df.groupby('match_key'):
        total_payout = 1.0
        try:
            multiplier = 1.0
            for _, row in group.iterrows():
                o = row['odds']
                if not o or o.strip() == "": continue
                val = float(str(o).replace('+', ''))
                multiplier *= (val / 100 + 1) if val > 0 else (100 / abs(val) + 1)
            total_payout = multiplier
        except:
            total_payout = 1.0

        prop_count = len(group)
        col_left, col_middle, col_right = st.sidebar.columns([0.09, 0.79, 0.12])

        with col_left:
            st.checkbox("", key=f"check_{match}", label_visibility="collapsed")

        with col_middle:
            with st.expander(
                f"🏀 {match}  💰{total_payout:.2f}x  ({prop_count})",
                expanded=True
            ):
                group_sorted = group.sort_values(by='sort_order', ascending=True)
                group_list   = list(group_sorted.iterrows())

                for i, (_, entry) in enumerate(group_list):
                    is_first = (i == 0)
                    is_last  = (i == len(group_list) - 1)

                    t_arrow = entry.get('trend_arrow', '→')
                    t_color = entry.get('trend_color', '#ffcc00')
                    odds_d  = f" <span style='color:#aaa'>@ {entry['odds']}</span>" if entry.get('odds') else ""

                    # Compact single-block prop card
                    st.markdown(
                        f"<div class='prop-row' style='border-left:2px solid {t_color};padding-left:5px;margin-bottom:3px'>"
                        f"<span style='color:{t_color};font-weight:700'>{t_arrow}</span> "
                        f"<strong style='font-size:0.85em'>{entry['player']} <span style='color:#88aaff'>•</span> {entry['team']}</strong>"
                        f"<span style='font-size:0.82em'> &gt; {entry['stat']} {entry['line']}{odds_d}</span><br>"
                        f"<span style='font-size:0.72em;color:#aaa'>{entry.get('hitrate_str','—')}</span>"
                        f"</div>",
                        unsafe_allow_html=True
                    )

                    # Action row: ↑ ↓ 🔍 🗑 all inline, minimal height
                    btn_cols = st.columns([0.18, 0.18, 0.32, 0.32])
                    with btn_cols[0]:
                        if not is_first:
                            if st.button("↑", key=f"up_{entry['player']}_{entry['stat']}_{entry['line']}_{i}", help="Move up"):
                                _move_prop(entry['player'], entry['stat'], entry['line'], -1)
                                _save_board()
                                st.rerun()
                    with btn_cols[1]:
                        if not is_last:
                            if st.button("↓", key=f"dn_{entry['player']}_{entry['stat']}_{entry['line']}_{i}", help="Move down"):
                                _move_prop(entry['player'], entry['stat'], entry['line'], +1)
                                _save_board()
                                st.rerun()
                    with btn_cols[2]:
                        if st.button("🔍 Load", key=f"load_{entry['player']}_{entry['stat']}_{str(entry.get('timestamp',''))}", help="Load this prop", use_container_width=True):
                            st.session_state.pending_load = {
                                'player': entry['player'],
                                'team':   entry['team'],
                                'stat':   entry['stat'],
                                'line':   entry['line'],
                            }
                            st.rerun()
                    with btn_cols[3]:
                        if st.button("🗑 Del", key=f"del_{entry['player']}_{entry['stat']}_{str(entry.get('timestamp',''))}", help="Remove prop", use_container_width=True):
                            st.session_state.my_board = [
                                d for d in st.session_state.my_board
                                if not (d['player'] == entry['player'] and
                                        d['stat']   == entry['stat']   and
                                        d['line']   == entry['line'])
                            ]
                            _save_board()
                            st.rerun()

        with col_right:
            if st.button("✕", key=f"del_group_{match}", help="Delete entire group"):
                st.session_state.my_board = [
                    d for d in st.session_state.my_board
                    if d['matchup'] != match
                ]
                _save_board()
                st.rerun()
else:
    st.sidebar.caption("No props saved. Pin some above!")

# ── Download / Upload Board ─────────────────────────────────────────────────────
def get_board_json():
    data = []
    for entry in st.session_state.my_board:
        item = entry.copy()
        if isinstance(item.get('timestamp'), datetime):
            item['timestamp'] = item['timestamp'].isoformat()
        data.append(item)
    return json.dumps(data)

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
        for entry in data:
            if isinstance(entry.get('timestamp'), str):
                entry['timestamp'] = datetime.fromisoformat(entry['timestamp'])
        st.session_state.my_board = data
        _save_board()
        st.sidebar.success("Board restored successfully!")
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Error loading file: {e}")

# ── Main Content ────────────────────────────────────────────────────────────────
if not selected_player or df is None or df.empty:
    st.info("Select a player from the sidebar to get started.")
    st.stop()

# Load defensive rankings (cached, non-blocking)
def_rankings = get_opp_def_rankings(CURRENT_SEASON)
opponent = get_opponent_from_game(selected_game_label, player_team)

st.markdown("---")

# ── Two-column layout: Hit Rate + Charts (left) | VS Opponent Log (right) ───────
col_left, col_right = st.columns([11, 9], gap="large")

with col_left:
    st.markdown("#### 📈 Hit Rate & Recent Games")

    if lines:
        pdata = df.sort_values("GAME_DATE_DT", ascending=False).copy()

        for stat, line in lines.items():
            windows = [5, 10]
            windows = [w for w in windows if len(pdata) >= w]

            over_list = []
            for w in windows:
                recent_w = pdata.head(w)
                hit_pct = (recent_w[stat] > line).mean() * 100
                over_list.append(hit_pct)

            parts = []
            for pct in over_list:
                color = '#00ff88' if pct > 73 else '#ffcc00' if pct >= 60 else '#ff5555'
                parts.append(f"<span style='color:{color}'>{pct:.0f}%</span>")

            hit_str = " | ".join(parts)
            avg_o = np.mean(over_list)
            avg_u = 100 - avg_o
            avg_color_o = '#00ff88' if avg_o > 75 else '#ffcc00' if avg_o >= 61 else '#ff5555'
            avg_color_u = '#00ff88' if avg_u > 75 else '#ffcc00' if avg_u >= 61 else '#ff5555'

            avg_text = f" AVG: <span style='color:{avg_color_o}'>O {avg_o:.0f}%</span> / <span style='color:{avg_color_u}'>U {avg_u:.0f}%</span>"

            badge_html = ""
            if opponent:
                badge_html = get_def_rank_badge(opponent, stat, def_rankings)
                if badge_html:
                    badge_html = f" &nbsp;{badge_html}"

            st.markdown(
                f"<div style='background:#1e1e2e;padding:10px;border-radius:8px;margin:8px 0;'>"
                f"<strong>{stat} {line}</strong> {hit_str}{avg_text}{badge_html}</div>",
                unsafe_allow_html=True
            )

            # Minutes Projection — right below the hit rate pill
            recent_min_data = df.head(10)
            if len(recent_min_data) >= 3:
                x_min = np.arange(len(recent_min_data))
                y_min = recent_min_data["MIN"].values
                slope_min, _ = np.polyfit(x_min, y_min, 1)
                recent_avg_min = recent_min_data["MIN"].mean()
                projected_min = recent_avg_min + slope_min
                min_color = '#00ff88' if projected_min >= 32 else '#ffcc00' if projected_min >= 28 else '#ff5555'
                concern_min = "🟢 Solid" if projected_min >= 32 else "🟡 Some concern" if projected_min >= 28 else "🔴 High risk"
                arrow_min = "↑" if slope_min > 0.3 else "↓" if slope_min < -0.3 else "→"
                st.markdown(
                    f"<div style='background:#1e1e2e;padding:8px 10px;border-radius:8px;margin:-4px 0 8px 0;font-size:0.88em;'>"
                    f"<b>Proj. MIN:</b> <span style='color:{min_color};font-weight:700'>≈ {projected_min:.1f}</span>"
                    f" &nbsp;|&nbsp; <b>Avg L10:</b> {recent_avg_min:.1f}"
                    f" &nbsp;|&nbsp; <b>Trend:</b> <span style='color:{min_color}'>{arrow_min} {slope_min:+.1f}</span>"
                    f" &nbsp;|&nbsp; {concern_min}"
                    f"</div>",
                    unsafe_allow_html=True
                )

            if len(pdata) > 0:
                n = min(10, len(pdata))
                recent_data = pdata.head(n)
                fig = go.Figure()
                colors = ["#00ff88" if v > line else "#ff4444" for v in recent_data[stat]]
                text_colors = ["#000" if val > 10 else "#fff" for val in recent_data[stat]]

                fig.add_trace(go.Bar(
                    x=recent_data["GAME_DATE"],
                    y=recent_data[stat],
                    marker_color=colors,
                    text=recent_data[stat].round(1),
                    textposition="inside",
                    textfont={"color": text_colors, "size": 11}
                ))
                fig.add_hline(y=line, line_dash="dash", line_color="#00ffff",
                              annotation_text=f"line = {line}", annotation_position="top right",
                              annotation_font_size=11)

                fig.update_layout(
                    height=220,
                    margin=dict(t=25, b=30, l=30, r=15),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    font_color="#00e0ff",
                    xaxis=dict(title=None, tickfont=dict(size=10)),
                    yaxis=dict(title=stat, tickfont=dict(size=10), title_font=dict(size=11)),
                )
                st.plotly_chart(fig, use_container_width=True)

with col_right:
    if opponent and df is not None and not df.empty:
        def_badge = ""
        if selected_stat and selected_stat != "— Select stat —":
            def_badge = get_def_rank_badge(opponent, selected_stat, def_rankings)

        st.markdown(f"#### 📊 vs {opponent} — {CURRENT_SEASON}")
        if def_badge:
            st.markdown(f"**{opponent} Defense** — {selected_stat}: {def_badge}", unsafe_allow_html=True)

        current_season_games = df[df['SEASON_ID'].str.contains(CURRENT_SEASON.split('-')[0], na=False)].copy()
        vs_opp = current_season_games[
            current_season_games['MATCHUP'].str.contains(opponent, na=False)
        ].copy()

        if not vs_opp.empty:
            games_vs = len(vs_opp)
            avg_pts = vs_opp["PTS"].mean()
            avg_reb = vs_opp["REB"].mean()
            avg_ast = vs_opp["AST"].mean()
            avg_min = vs_opp["MIN"].mean()

            # Hit rate inline with averages
            hr_html = ""
            if selected_stat and selected_stat in lines:
                _line = lines[selected_stat]
                hit_rate_vs = (vs_opp[selected_stat] > _line).mean() * 100
                hr_color = '#00ff88' if hit_rate_vs > 65 else '#ffcc00' if hit_rate_vs >= 50 else '#ff5555'
                hr_html = (
                    f" &nbsp;|&nbsp; <b>Hit Rate</b> ({selected_stat} {_line}): "
                    f"<span style='color:{hr_color};font-size:1.1em;font-weight:700'>{hit_rate_vs:.0f}%</span>"
                )

            st.markdown(
                f"<div style='background:#1e1e2e;padding:8px 10px;border-radius:8px;margin:4px 0 8px 0;font-size:0.88em;'>"
                f"<b>G:</b> {games_vs} &nbsp;|&nbsp; <b>MIN:</b> {avg_min:.1f} &nbsp;|&nbsp; "
                f"<b>PTS:</b> {avg_pts:.1f} &nbsp;|&nbsp; <b>REB:</b> {avg_reb:.1f} &nbsp;|&nbsp; <b>AST:</b> {avg_ast:.1f}"
                f"{hr_html}"
                f"</div>",
                unsafe_allow_html=True
            )

            # Shooting % — same pill style as the averages row
            shoot_items = []
            if "FGM" in vs_opp.columns and "FGA" in vs_opp.columns and vs_opp["FGA"].sum() > 0:
                fg3m_sum = vs_opp["FG3M"].sum() if "FG3M" in vs_opp.columns else 0
                fg3a_sum = vs_opp["FG3A"].sum() if "FG3A" in vs_opp.columns else 0
                fg2m = vs_opp["FGM"].sum() - fg3m_sum
                fg2a = vs_opp["FGA"].sum() - fg3a_sum
                if fg2a > 0:
                    pct_2p = fg2m / fg2a * 100
                    c2 = '#00ff88' if pct_2p >= 50 else '#ffcc00' if pct_2p >= 42 else '#ff5555'
                    shoot_items.append(f"<b>2P%:</b> <span style='color:{c2};font-weight:700'>{pct_2p:.1f}%</span>")
            if "FG3M" in vs_opp.columns and "FG3A" in vs_opp.columns and vs_opp["FG3A"].sum() > 0:
                fg3m = vs_opp["FG3M"].sum()
                fg3a = vs_opp["FG3A"].sum()
                pct_3p = fg3m / fg3a * 100
                c3 = '#00ff88' if pct_3p >= 37 else '#ffcc00' if pct_3p >= 32 else '#ff5555'
                shoot_items.append(f"<b>3P%:</b> <span style='color:{c3};font-weight:700'>{pct_3p:.1f}%</span>")
            if "FTM" in vs_opp.columns and "FTA" in vs_opp.columns and vs_opp["FTA"].sum() > 0:
                ftm = vs_opp["FTM"].sum()
                fta = vs_opp["FTA"].sum()
                pct_ft = ftm / fta * 100
                cft = '#00ff88' if pct_ft >= 80 else '#ffcc00' if pct_ft >= 70 else '#ff5555'
                shoot_items.append(f"<b>FT%:</b> <span style='color:{cft};font-weight:700'>{pct_ft:.1f}%</span>")
            if shoot_items:
                st.markdown(
                    f"<div style='background:#1e1e2e;padding:8px 10px;border-radius:8px;margin:4px 0 8px 0;font-size:0.88em;'>"
                    + " &nbsp;|&nbsp; ".join(shoot_items)
                    + "</div>",
                    unsafe_allow_html=True
                )

            vs_opp_disp = vs_opp.copy()
            for _col, a, b in [("Pts+Reb", "PTS", "REB"), ("Pts+Ast", "PTS", "AST"),
                                ("Ast+Reb", "AST", "REB"), ("Stl+Blk", "STL", "BLK")]:
                if a in vs_opp_disp.columns and b in vs_opp_disp.columns:
                    vs_opp_disp[_col] = vs_opp_disp[a] + vs_opp_disp[b]
            if all(c in vs_opp_disp.columns for c in ["PTS", "REB", "AST"]):
                vs_opp_disp["PRA"] = vs_opp_disp["PTS"] + vs_opp_disp["REB"] + vs_opp_disp["AST"]

            display_cols_vs = ["GAME_DATE", "WL", "MIN", "PTS", "REB", "AST",
                                "STL", "BLK", "TOV", "FG3M", "PRA", "+/-"]
            available_vs = [c for c in display_cols_vs if c in vs_opp_disp.columns]

            styled_vs = vs_opp_disp[available_vs].style\
                .format(precision=1)\
                .map(lambda val: 'background-color: #00cc88; color: black' if pd.notna(val) and val >= 32 else '',
                     subset=['MIN'] if 'MIN' in available_vs else [])

            st.dataframe(styled_vs, use_container_width=True, hide_index=True, height=320)

        else:
            st.info(f"No games vs **{opponent}** in {CURRENT_SEASON} yet.")
    else:
        st.markdown("#### 📊 vs Opponent")
        st.caption("Select a game filter in the sidebar to see matchup history.")


# ── Full Recent Game Log ────────────────────────────────────────────────────────
with st.expander("📊 Full Recent Game Log (Last 15)", expanded=False):
    df_disp = df.copy()
    for col, a, b in [("Pts+Reb", "PTS", "REB"), ("Pts+Ast", "PTS", "AST"),
                      ("Ast+Reb", "AST", "REB"), ("Stl+Blk", "STL", "BLK")]:
        if a in df_disp.columns and b in df_disp.columns:
            df_disp[col] = df_disp[a] + df_disp[b]
    if all(c in df_disp.columns for c in ["PTS", "REB", "AST"]):
        df_disp["PRA"] = df_disp["PTS"] + df_disp["REB"] + df_disp["AST"]

    display_cols = ["GAME_DATE", "GAME_TYPE", "MATCHUP", "WL", "MIN",
                    "PTS", "REB", "AST", "STL", "BLK", "TOV",
                    "Pts+Reb", "Pts+Ast", "Ast+Reb", "Stl+Blk", "PRA",
                    "FG3M", "FG3A", "+/-"]
    available_cols = [c for c in display_cols if c in df_disp.columns]
    
    def highlight_minutes(val):
        if pd.isna(val): return ''
        color = '#00cc88' if val >= 32 else '#ffcc00' if val >= 28 else '#ff5555'
        return f'background-color: {color}; color: black'
    
    styled_df = df_disp.head(15)[available_cols].style\
        .format(precision=1)\
        .map(highlight_minutes, subset=['MIN'] if 'MIN' in available_cols else [])
    
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

st.markdown("<p style='text-align:center; color:#88f0ff; padding-top:2rem;'>ICE PROP LAB • 2025-26</p>", unsafe_allow_html=True)
