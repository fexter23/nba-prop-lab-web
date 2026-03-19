import os
import time
import pandas as pd
from datetime import datetime
from nba_api.stats.static import players
from nba_api.stats.endpoints import PlayerGameLog

# Using the dynamic season logic from your working nba_wrk.py
def get_current_season():
    today = datetime.today()
    if today.month >= 10:
        return f"{today.year}-{str(today.year + 1)[-2:]}"
    else:
        return f"{today.year-1}-{str(today.year)[-2:]}"

CURRENT_SEASON = get_current_season()
PLAYER_FILE = "data/players.parquet"
TEAM_FILE = "data/active_player_teams.parquet"

os.makedirs("data", exist_ok=True)

def update_nba_data():
    print(f"Starting Update: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # 1. Incremental Master Player List Update
    # We fetch the light static list to check for changes
    all_players_api = players.get_players()
    needs_player_update = True

    if os.path.exists(PLAYER_FILE):
        existing_players = pd.read_parquet(PLAYER_FILE)
        # Validate if the list actually needs updating by comparing counts
        if len(existing_players) == len(all_players_api):
            print("Master player list is already up to date. Skipping...")
            needs_player_update = False
    
    if needs_player_update:
        pd.DataFrame(all_players_api).to_parquet(PLAYER_FILE, index=False)
        print(f"Saved {len(all_players_api)} total players to {PLAYER_FILE}")

    # 2. Incremental Team Mapping
    active_players = players.get_active_players()
    
    # Load existing mapping to avoid redundant API calls
    if os.path.exists(TEAM_FILE):
        df_existing_teams = pd.read_parquet(TEAM_FILE)
        # Map Player ID (as string) to Team Abbreviation
        team_map = dict(zip(df_existing_teams['PLAYER_ID'].astype(str), df_existing_teams['TEAM_ABBR']))
    else:
        team_map = {}

    print(f"Checking updates for {len(active_players)} active players...")
    new_data_found = False

    for i, player in enumerate(active_players):
        pid = str(player['id'])
        
        # Skip if we already have this player's data (Incremental Logic)
        if pid in team_map:
            continue 

        try:
            # Fetch the most recent game log for the current season
            log = PlayerGameLog(player_id=pid, season=CURRENT_SEASON).get_data_frames()[0]
            
            if not log.empty:
                current_team = log.iloc[0]['TEAM_ABBREVIATION']
                team_map[pid] = current_team
                new_data_found = True
            
            # Progress update
            print(f"Added new player: {player['full_name']} ({pid})")
            
            # Rate limit protection (0.6s is safe for NBA API)
            time.sleep(0.6)
            
        except Exception as e:
            print(f"Could not update {player['full_name']}: {e}")
            continue

    # 3. Save the mapping if updates occurred
    if new_data_found:
        df_teams = pd.DataFrame.from_dict(team_map, orient='index', columns=['TEAM_ABBR'])
        df_teams.index.name = 'PLAYER_ID'
        df_teams.reset_index(inplace=True)
        df_teams.to_parquet(TEAM_FILE, index=False)
        print(f"Successfully updated {TEAM_FILE}")
    else:
        print("No new player team data to save.")

if __name__ == "__main__":
    update_nba_data()
