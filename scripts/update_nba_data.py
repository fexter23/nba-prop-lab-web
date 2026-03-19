import os
import time
import pandas as pd
from datetime import datetime
from nba_api.stats.static import players
from nba_api.stats.endpoints import PlayerGameLog

# Using the dynamic season logic
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
    all_players_api = players.get_players()
    needs_player_update = True

    # Check if file exists AND is larger than the 8-byte Parquet minimum
    if os.path.exists(PLAYER_FILE) and os.path.getsize(PLAYER_FILE) > 8:
        try:
            existing_players = pd.read_parquet(PLAYER_FILE)
            if len(existing_players) == len(all_players_api):
                print("Master player list is already up to date. Skipping...")
                needs_player_update = False
        except Exception as e:
            print(f"Existing player file corrupted ({e}). Re-downloading...")
            needs_player_update = True
    
    if needs_player_update:
        pd.DataFrame(all_players_api).to_parquet(PLAYER_FILE, index=False)
        print(f"Saved {len(all_players_api)} total players to {PLAYER_FILE}")

    # 2. Incremental Team Mapping
    active_players = players.get_active_players()
    team_map = {}

    # Safety check for team file
    if os.path.exists(TEAM_FILE) and os.path.getsize(TEAM_FILE) > 8:
        try:
            df_existing_teams = pd.read_parquet(TEAM_FILE)
            team_map = dict(zip(df_existing_teams['PLAYER_ID'].astype(str), df_existing_teams['TEAM_ABBR']))
        except Exception as e:
            print(f"Existing team file corrupted ({e}). Resetting map...")
            team_map = {}

    print(f"Checking updates for {len(active_players)} active players...")
    new_data_found = False

    for i, player in enumerate(active_players):
        pid = str(player['id'])
        
        # Skip if we already have this player's data
        if pid in team_map:
            continue 

        try:
            log = PlayerGameLog(player_id=pid, season=CURRENT_SEASON).get_data_frames()[0]
            
            if not log.empty:
                current_team = log.iloc[0]['TEAM_ABBREVIATION']
                team_map[pid] = current_team
                new_data_found = True
                print(f"Added new player: {player['full_name']} ({current_team})")
            
            # Rate limit protection
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
