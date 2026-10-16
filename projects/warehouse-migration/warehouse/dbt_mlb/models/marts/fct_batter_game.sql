-- Grain: one row per batter per game (batters with >= 1 plate appearance).
-- Foreign keys point at dim_player, dim_team, dim_game, dim_season.
select
    b.game_pk,
    b.player_id,
    b.team_id,
    g.season,
    b.game_date,
    g.park_id,
    b.batting_order_slot,
    b.plate_appearances,
    b.at_bats,
    b.hits,
    b.runs,
    b.rbis,
    b.hrr
from {{ ref('stg_batter_game_stats') }} b
left join {{ ref('stg_games') }} g on g.game_pk = b.game_pk
