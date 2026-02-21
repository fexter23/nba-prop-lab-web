# scripts/update_nba_data.py
from nba_api.stats.static import players
from nba_api.stats.endpoints import leaguedashplayerstats
import pandas as pd
import time
from datetime import datetime
from requests.exceptions import ReadTimeout, ConnectionError, RequestException

print(f"Starting NBA data update — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")

# ── 1. All players (static-ish, changes rarely) ─────────────────────────────────
all_players = players.get_players()
df_players = pd.DataFrame(all_players)
df_players.to_parquet("data/players.parquet", index=False)
print(f"Saved {len(df_players)} players")

# ── 2. Active players + current teams (with retries, longer timeout & headers) ──
team_map = {}
seasons = ["2025-26", "2024-25"]  # ← update to match your CURRENT_SEASON logic

# Browser-like headers to appear less like a bot
custom_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.nba.com/',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Origin': 'https://www.nba.com',
    'Connection': 'keep-alive',
}

for season in seasons:
    for attempt in range(3):  # retry up to 3 times
        try:
            print(f"Attempt {attempt+1}/3 to fetch {season}...")
            
            df = leaguedashplayerstats.LeagueDashPlayerStats(
                season=season,
                season_type_all_star="Regular Season",
                headers=custom_headers,
                timeout=90                      # increased from default 30s
            ).get_data_frames()[0]
            
            print(f"Raw dataframe shape for {season}: {df.shape}")
            # print(df.head(2))                 # uncomment for debugging
            
            if not df.empty and len(df) > 80:
                df = df[df['TEAM_ABBREVIATION'].notna() & (df['TEAM_ABBREVIATION'] != '')]
                team_map = dict(zip(df['PLAYER_ID'].astype(str), df['TEAM_ABBREVIATION']))
                print(f"Success → Got {len(team_map)} active players from {season}")
                break  # exit retry loop and season loop
                
        except (ReadTimeout, ConnectionError, RequestException) as e:
            print(f"Attempt {attempt+1} failed for {season}: {type(e).__name__}: {e}")
            if attempt < 2:
                print(f"Waiting 30 seconds before retry...")
                time.sleep(30)
            else:
                print(f"All {attempt+1} attempts failed for {season}")
        except Exception as e:
            print(f"Unexpected error for {season}: {type(e).__name__}: {e}")
            break  # don't retry on non-network errors

    if team_map:
        break  # stop after successful season

# ── Fallback: try to keep previous data if fetch completely failed ──────────────
if not team_map:
    print("Warning: No active team data retrieved in any attempt")
    try:
        existing = pd.read_parquet("data/active_player_teams.parquet")
        if not existing.empty:
            team_map = dict(zip(existing['PLAYER_ID'].astype(str), existing['TEAM_ABBR']))
            print(f"Fallback → reusing previous data ({len(team_map)} players)")
    except Exception as e:
        print(f"Could not load fallback file: {e}")

# ── Save result if we have data ─────────────────────────────────────────────────
if team_map:
    df_teams = pd.DataFrame.from_dict(team_map, orient='index', columns=['TEAM_ABBR'])
    df_teams.index.name = 'PLAYER_ID'
    df_teams.reset_index(inplace=True)
    df_teams.to_parquet("data/active_player_teams.parquet", index=False)
    print(f"Saved active player teams file ({len(df_teams)} rows)")
else:
    print("No data to save for active_player_teams.parquet")

print("Update finished.")
