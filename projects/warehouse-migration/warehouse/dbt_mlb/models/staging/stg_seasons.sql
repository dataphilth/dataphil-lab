select
    season,
    try_to_date(start_date)               as start_date,
    try_to_date(end_date)                 as end_date,
    shift_ban::boolean                    as is_shift_ban,
    universal_dh::boolean                 as is_universal_dh,
    pitch_clock::boolean                  as is_pitch_clock,
    bigger_bases::boolean                 as is_bigger_bases,
    ball_era_label,
    notes
from {{ source('raw', 'seasons') }}
