select
    game_pk,
    batter_id                             as player_id,
    try_to_date(game_date)                as game_date,
    team_id,
    batting_order_slot,
    plate_appearances,
    at_bats,
    hits,
    runs,
    rbis,
    hits + runs + rbis                    as hrr,          -- was a GENERATED column in SQLite
    source
from {{ source('raw', 'batter_game_stats') }}
