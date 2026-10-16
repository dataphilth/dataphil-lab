select
    game_pk,
    try_to_date(game_date)                as game_date,
    season,
    home_team                             as home_team_abbr,
    away_team                             as away_team_abbr,
    park_id,
    home_pitcher_id,
    away_pitcher_id,
    ump_id                                as umpire_id,
    weather_temp_f,
    weather_wind_mph,
    weather_wind_dir,
    weather_humidity,
    game_status,
    try_to_timestamp_ntz(first_pitch_ts)  as first_pitch_at
from {{ source('raw', 'games') }}
