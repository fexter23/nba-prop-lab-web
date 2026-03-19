import os
import time
import pandas as pd
from datetime import datetime, date
from nba_api.stats.static import teams as static_teams
from nba_api.stats.endpoints import PlayerGameLog, scoreboardv2

# Configuration
DATA_DIR = "data"
LOGS_FILE = os.path.join(DATA_DIR, "player_logs_l10.parquet")
TEAM_MAP_FILE = os.path.join(DATA_DIR, "active_player_teams.parquet")

def get_current_season():
    today = datetime.today()
    return f"{today.year}-{str(today.year + 1)[-2:]}" if today.month >= 10 else f"{today.year-1}-{str(today.year)[-2:]}"

def sync_daily_data():
    print(f"--- Starting Daily L10 Sync: {datetime.now().strftime('%Y-%m-%d %H:%M')} ---")
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # 1. Get today's teams from Scoreboard
    try:
        sb = scoreboardv2.ScoreboardV2(game_date=date.today().strftime("%Y-%m-%d"))
        games = sb.game_header.get_data_frame()
        if games.empty:
            print("No games scheduled for today.")
            return
        
        home_ids = games['HOME_TEAM_ID'].astype(str).tolist()
        visitor_ids = games['VISITOR_TEAM_ID'].astype(str).tolist()
        today_team_ids = set(home_ids + visitor_ids)
        
        all_teams = static_teams.get_teams()
        id_to_abbr = {str(t['id']): t['abbreviation'] for t in all_teams}
        today_team_abbrs = {id_to_abbr[tid] for tid in today_team_ids if tid in id_to_abbr}
        
        print(f"Teams playing today: {', '.join(sorted(today_team_abbrs))}")
    except Exception as e:
        print(f"Error fetching scoreboard: {e}")
        return

    # 2. Load existing player-team mapping
    if not os.path.exists(TEAM_MAP_FILE):
        print(f"Error: {TEAM_MAP_FILE} not found. Please run update_nba_data.py first.")
        return
    
    df_players = pd.read_parquet(TEAM_MAP_FILE)
    active_players_today = df_players[df_players['TEAM_ABBR'].isin(today_team_abbrs)]
    
    if active_players_today.empty:
        print("No players found in mapping for today's teams.")
        return

    # 3. Load existing local logs
    master_logs = pd.read_parquet(LOGS_FILE) if os.path.exists(LOGS_FILE) else pd.DataFrame()

    # 4. Fetch logs (Last 10) for these players
    new_logs_list = []
    total = len(active_players_today)
    print(f"Updating logs for {total} players...")
    
    for i, (_, row) in enumerate(active_players_today.iterrows()):
        pid = row['PLAYER_ID']
        try:
            log = PlayerGameLog(
                player_id=pid, 
                season=get_current_season(), 
                last_n_games=10
            ).get_data_frames()[0]
            
            if not log.empty:
                new_logs_list.append(log)
            
            if (i + 1) % 20 == 0 or (i + 1) == total:
                print(f"Progress: {i+1}/{total}")
            
            time.sleep(0.7) # Rate limit safety
        except Exception as e:
            print(f"Failed for Player ID {pid}: {e}")

    # 5. Save and Merge
    if new_logs_list:
        new_df = pd.concat(new_logs_list, ignore_index=True)
        pids_updated = new_df['Player_ID'].unique()
        
        if not master_logs.empty:
            master_logs = master_logs[~master_logs['Player_ID'].isin(pids_updated)]
        
        final_logs = pd.concat([master_logs, new_df], ignore_index=True)
        final_logs.to_parquet(LOGS_FILE, index=False)
        print(f"Successfully saved L10 logs for {len(pids_updated)} players.")

if __name__ == "__main__":
    sync_daily_data()
