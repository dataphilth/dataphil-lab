select
    mlbam_id                              as player_id,
    full_name,
    primary_position,
    bats,
    throws,
    try_to_date(debut_date)               as debut_date,
    try_to_date(birth_date)               as birth_date,
    try_to_timestamp_ntz(last_updated)    as last_updated_at
from {{ source('raw', 'players') }}
