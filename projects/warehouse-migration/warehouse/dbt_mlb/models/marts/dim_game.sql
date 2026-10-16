-- One row per game: schedule/context joined to the final score.
-- Results are nullable: scheduled or postponed games have no result row.
select
    g.game_pk,
    g.game_date,
    g.season,
    g.home_team_abbr,
    g.away_team_abbr,
    g.park_id,
    g.home_pitcher_id,
    g.away_pitcher_id,
    g.umpire_id,
    g.weather_temp_f,
    g.weather_wind_mph,
    g.weather_wind_dir,
    g.game_status,
    r.home_runs,
    r.away_runs,
    r.total_runs,
    r.innings_played,
    r.game_pk is not null     as has_result
from {{ ref('stg_games') }} g
left join {{ ref('stg_game_results') }} r on r.game_pk = g.game_pk
