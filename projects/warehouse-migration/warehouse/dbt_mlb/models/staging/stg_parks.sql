select
    park_id,
    name                                  as park_name,
    city,
    state,
    lat,
    lon,
    altitude_ft,
    surface,
    roof,
    lf_dist_ft,
    cf_dist_ft,
    rf_dist_ft,
    run_factor,
    hr_factor_lhb,
    hr_factor_rhb,
    try_to_timestamp_ntz(last_updated)    as last_updated_at
from {{ source('raw', 'parks') }}
