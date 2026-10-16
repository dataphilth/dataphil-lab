select
    game_pk,
    home_runs,
    away_runs,
    home_runs + away_runs                 as total_runs,   -- was a GENERATED column in SQLite
    home_hits,
    away_hits,
    home_errors,
    away_errors,
    innings_played
from {{ source('raw', 'game_results') }}
