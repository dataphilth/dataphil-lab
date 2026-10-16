select
    team_id,
    abbr                                  as team_abbr,
    full_name                             as team_name,
    league,
    division,
    current_park_id                       as park_id,
    try_to_timestamp_ntz(last_updated)    as last_updated_at
from {{ source('raw', 'teams') }}
