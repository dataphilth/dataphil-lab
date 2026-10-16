select
    t.team_id,
    t.team_abbr,
    t.team_name,
    t.league,
    t.division,
    t.park_id                 as home_park_id,
    p.park_name               as home_park_name
from {{ ref('stg_teams') }} t
left join {{ ref('stg_parks') }} p on p.park_id = t.park_id
