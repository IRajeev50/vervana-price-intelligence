"""WeatherUnion (Zomato) hyperlocal weather - a context layer, never a price.

Real-time temperature/humidity/wind/rain (and PM2.5/PM10) from Zomato's
crowd-sourced station network, keyed by lat/long. These readings sharpen the
supply-side picture (rain near a Delhi mandi -> arrival/price risk), but they are
WEATHER, not price: nothing here ever writes to `price_observation`. Every stored
reading carries its source URL, and when the API returns no data for a locality
the capture reports it and stores nothing - it never invents a number.
"""
