# scripts/update_nba_data.py
from nba_api.stats.static import players
from nba_api.stats.endpoints import leaguedashplayerstats
import pandas as pd
import os
from datetime import datetime

print(f"Starting NBA data update — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")

# 1. All players (static-ish, changes rarely)
all_players = players.get_players()
df_players = pd.DataFrame(all_players)
df_players.to_parquet("data/players.parquet", index=False)
print(f"Saved {len(df_players)} players")

# 2. Active players + current teams (this changes during season)
# Try current season first, fall back to previous
team_map = {}
seasons = ["2025-26", "2024-25"]  # ← update to match your CURRENT_SEASON logic

for season in seasons:
    try:
        df = leaguedashplayerstats.LeagueDashPlayerStats(
            season=season,
            season_type_all_star="Regular Season"
        ).get_data_frames()[0]
        
        if not df.empty and len(df) > 80:
            df = df[df['TEAM_ABBREVIATION'].notna() & (df['TEAM_ABBREVIATION'] != '')]
            team_map = dict(zip(df['PLAYER_ID'].astype(str), df['TEAM_ABBREVIATION']))
            print(f"Got {len(team_map)} active players from {season}")
            break
    except Exception as e:
        print(f"Season {season} failed: {e}")

if team_map:
    df_teams = pd.DataFrame.from_dict(team_map, orient='index', columns=['TEAM_ABBR'])
    df_teams.index.name = 'PLAYER_ID'
    df_teams.reset_index(inplace=True)
    df_teams.to_parquet("data/active_player_teams.parquet", index=False)
else:
    print("Warning: No active team data retrieved")

print("Update finished.")
