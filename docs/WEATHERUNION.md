# Weather Union current-weather integration (scaffold)

Status: implemented locally; owner-approved account created; API key obtained and
stored in the secure vault; two bounded live validation calls succeeded. No real key
or sample weather is shipped. No model-accuracy improvement is claimed.

## What it adds

- One bounded, key-authenticated GET to the documented coordinate endpoint.
- A separate `weatherunion-status` CLI that distinguishes configuration from access.
- `weatherunion-fetch` stores latest-received daily point weather in `context_signal`.
- Feature names carry units: `wu_temperature_c`, `wu_humidity_pct`,
  `wu_wind_speed_mps`, `wu_wind_direction_deg`, `wu_rain_intensity_mm_min`,
  `wu_rain_today_mm`. These are not prices or IMD rainfall-deficit signals.
- Missing values remain null; rain-gauge-only devices cannot emit AWS measurements.
- Unsupported locations, temporary unavailability (even HTTP 200), bad responses,
  authentication failures, quota exhaustion and network errors fail closed.
- Request headers and error bodies are not printed; settings mask the secret.
- Repeated site/date imports replace the previous receipt, rather than duplicating
  measurements. Receipt timestamps are UTC; daily buckets use Asia/Kolkata.

## Verified access and limits (checked 9 Oct 2026)

- Signed-up dashboard displayed `Today's API usage` as `0/1000` and
  `API limits will reset after 12 AM` before validation. Two bounded live calls were
  then made, one direct contract check and one through this integration.
- The signed Terms & Conditions say: "The availability and access to free API's for
  each profile ... shall be valid for a maximum of 60,000 API's in a particular
  financial year." Additional access requires contacting info@weatherunion.com.
- The public site advertises free API access, while saying unusually high enterprise
  usage may lead Zomato to ask for payment. No fee schedule or paid plan was shown.
- One live rain-gauge station response returned HTTP 200 with only rain measurements;
  all non-rain fields were null. The integration stored two measured values and kept
  the other features null rather than inventing values.

## Terms that shape product use

- The T&Cs permit using Weather Union to download available weather information and
  integrate with the supplied API keys.
- The same T&Cs say data other than the historical IMD weather-facts data belongs to
  Zomato, and broadly prohibit modifying, copying, scraping, displaying, publishing,
  licensing, selling, renting, leasing, lending, transferring or otherwise
  commercializing rights to the Zomato Services or content. Internal API integration
  is expressly permitted, but public redistribution or commercial republishing of raw
  content is not clearly permitted; get written clarification before doing that.
- There is no monetary liability cap in the reviewed T&Cs. Zomato excludes special,
  incidental, indirect, consequential and punitive damages, provides the service
  "AS IS" and "AS AVAILABLE", and disclaims responsibility for losses from API use.
- Zomato may suspend access for actions associated with breach and may terminate
  immediately for breach or specified misconduct. The user may terminate by deleting
  the Weather Union account.

## Enable after review

1. Use the account's API key only from the approved secret store; put it only in the
   runtime environment as `VERVANA_WEATHERUNION_API_KEY`, never in git, logs, URLs or chat.
2. Initialize/upgrade the platform database through the existing setup flow.
3. Check the supported station coordinates in the vendor locality list. Use a
   site-specific region label, not an entire district. The older vendor API PDF
   states the coordinate endpoint serves locations within 2 km of a device.
4. Run `uv run vervana supply weatherunion-status`.
5. Run `uv run vervana supply weatherunion-fetch LATITUDE LONGITUDE SITE_LABEL`.
   There is no automatic collector/scheduler in this change. Respect the verified
   1,000/day dashboard limit and 60,000/profile/financial-year T&C cap. Do not retry
   429 responses automatically.

## Limits that matter to procurement and forecasting

This is current local weather, not forecasts, historical weather, yield estimates,
mandi arrivals, executed prices or a national farm-weather dataset. The live response
schema does not expose a station observation timestamp. `received_at` records when
we fetched it, NOT when the station measured it. Station freshness remains unknown.
`rain_accumulation` is today's rainfall since midnight IST, not a seasonal deficit.
Temperature is a point reading, not a daily max/average. A city or mandi station
cannot stand in for the commodity's growing district. Coverage must be checked.

The existing forecast runner remains unchanged. Its univariate baseline and release
threshold are preserved. These features build the data-source seam for later work;
do not add them to historical training from today's readings. Prospective modeling
needs an immutable timestamped weather archive with observed/available times, verified
site-to-market/crop mapping, sufficient paired price/arrivals history, missingness and
coverage checks, and walk-forward comparisons against the existing baseline. Daily
latest-receipt context rows alone are NOT leakage-safe historical training data.

## Sources

- https://www.weatherunion.com/
- https://www.weatherunion.com/dashboard/#tag/default/GET/get_weather_data
- https://www.weatherunion.com/tnc/ and linked PDF:
  https://b.zmtcdn.com/data/file_assets/4f2b1aeb48ea8c87519e7f2bd652b6811715149430.pdf
- https://www.weatherunion.com/privacy/ and linked PDF:
  https://b.zmtcdn.com/data/file_assets/a30e8625c9d0558910ac3c5b0a5ae22d1715149469.pdf
- Vendor API reference dated 8 May 2024:
  https://b.zmtcdn.com/data/file_assets/915d4e8e95d067c47e1ae38d77d572b21715104204.pdf
- Supported locality list linked by current dashboard:
  https://b.zmtcdn.com/data/file_assets/65fa362da3aa560a92f0b8aeec0dfda31713163042.pdf
