import os
import time
import pandas as pd
from datetime import datetime
from nba_api.stats.static import players
from nba_api.stats.endpoints import PlayerGameLog, playernextngames

# Using the dynamic season logic from your working nba_wrk.py
def get_current_season():
    today = datetime.today()
    if today.month >= 10:
        return f"{today.year}-{str(today.year + 1)[-2:]}"
    else:
        return f"{today.year-1}-{str(today.year)[-2:]}"

CURRENT_SEASON = get_current_season()
os.makedirs("data", exist_ok=True)

def update_nba_data():
    print(f"Starting Daily Update: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # 1. Update the master player list
    all_players = players.get_players()
    pd.DataFrame(all_players).to_parquet("data/players.parquet", index=False)
    print(f"Saved {len(all_players)} total players to players.parquet")

    # 2. Identify active players to reduce API load
    active_players = players.get_active_players()
    team_map = {}
    
    print(f"Fetching team data for {len(active_players)} active players...")

    for i, player in enumerate(active_players):
        pid = player['id']
        try:
            # Fetch the most recent game log to see their current team
            # This is more reliable than the league-wide stat dashboard
            log = PlayerGameLog(player_id=pid, season=CURRENT_SEASON).get_data_frames()[0]
            
            if not log.empty:
                current_team = log.iloc[0]['TEAM_ABBREVIATION']
                team_map[str(pid)] = current_team
            
            # Progress update every 50 players
            if (i + 1) % 50 == 0:
                print(f"Processed {i + 1}/{len(active_players)} players...")
            
            # Crucial: Sleep for 0.6 seconds to stay under the rate limit
            time.sleep(0.6)
            
        except Exception as e:
            print(f"Could not update {player['full_name']}: {e}")
            continue

    # 3. Save the team mapping for your Streamlit app to use
    if team_map:
        df_teams = pd.DataFrame.from_dict(team_map, orient='index', columns=['TEAM_ABBR'])
        df_teams.index.name = 'PLAYER_ID'
        df_teams.reset_index(inplace=True)
        df_teams.to_parquet("data/active_player_teams.parquet", index=False)
        print("Successfully saved active_player_teams.parquet")
    else:
        print("Warning: No team data was collected.")

if __name__ == "__main__":
    update_nba_data()
