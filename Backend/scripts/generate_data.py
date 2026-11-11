# ColdTrace labeled simulator. Seeded; Exception_Type is injected ground truth.
import numpy as np, pandas as pd, sys
from scipy.signal import lfilter

SEED = 42
rng = np.random.default_rng(SEED)
ts = pd.date_range("2022-01-01 00:00", "2026-10-31 23:30", freq="30min")
n = len(ts)
hour = ts.hour.values + ts.minute.values / 60
doy = ts.dayofyear.values
dow = ts.dayofweek.values
month = ts.month.values
yrs = (ts - ts[0]).total_seconds().values / (365.25 * 86400)
year = ts.year.values

LOCS = {
    "JHB-DC01": dict(city="Johannesburg", tmean=17.5, tseas=4.5, tdiur=7.0, hum=55, humseas=12, sgn=+1, dist=1.05, out=1.0, wh_off=0.0),
    "DBN-DC02": dict(city="Durban",       tmean=21.5, tseas=4.0, tdiur=4.5, hum=75, humseas=6,  sgn=+1, dist=1.00, out=1.2, wh_off=0.2),
    "CPT-DC03": dict(city="Cape Town",    tmean=17.0, tseas=5.0, tdiur=5.5, hum=68, humseas=-10, sgn=-1, dist=0.90, out=0.8, wh_off=-0.1),
}
OUT_RATE = {2022: 0.35, 2023: 0.30, 2024: 0.12, 2025: 0.12, 2026: 0.12}  # floored after 2024 so test split has enough events


def ar(phi, sigma):
    return lfilter([1.0], [1.0, -phi], rng.normal(0, sigma, n))


def cat(latent, cats, cum):
    thr = np.quantile(latent, cum)
    return np.array(cats, dtype=object)[np.searchsorted(thr, latent)]


def gen(loc_id, p):
    seas = np.cos(2 * np.pi * (doy - 15) / 365.25)
    amb = p["tmean"] + p["tseas"] * seas + p["tdiur"] * np.cos(2 * np.pi * (hour - 15) / 24) + ar(0.97, 0.35)
    amb_hum = np.clip(p["hum"] + p["humseas"] * seas + 8 * np.cos(2 * np.pi * (hour - 5) / 24) + ar(0.95, 1.2), 20, 100)

    # activity
    A = 0.15 + 0.85 * np.exp(-((hour - 11.5) / 4.5) ** 2)
    A *= np.select([dow == 5, dow == 6], [0.5, 0.25], 1.0)
    A *= np.where(np.isin(month, [11, 12]), 1.15, 1.0) * (1 + 0.04 * yrs)
    A *= rng.lognormal(0, 0.1, n)

    # outages / equipment faults
    pstep = np.array([OUT_RATE[y] for y in year]) * p["out"] / 48 * (1 + 1.5 * np.exp(-((hour - 19) / 2) ** 2))
    lab = np.full(n, "NONE", dtype=object)
    out = np.zeros(n)
    comp = np.zeros(n)
    drop = np.zeros(n)
    drops = []
    for s in np.flatnonzero(rng.random(n) < pstep):
        d = rng.integers(2, 9)
        big = rng.random() < 0.5
        amp = rng.uniform(2.5, 6.0) if big else rng.uniform(0.1, 0.6)
        out[s:s + d] = np.maximum(out[s:s + d], amp)
        if big:
            lab[s:s + d] = "TEMP_EXCURSION"
    for s in np.flatnonzero(rng.random(n) < 0.06 / 48):
        d = rng.integers(6, 25)
        out[s:s + d] = np.maximum(out[s:s + d], rng.uniform(1.5, 4.0))
        comp[s:s + d] = 1
        lab[s:s + d] = "COOLING_FAILURE"
    for s in np.flatnonzero(rng.random(n) < 0.2 / 48):
        d = rng.integers(4, 17)
        drop[s:s + d] = 1
        drops.append((s, d))
        lab[s:s + d] = "SENSOR_DROPOUT"
    exc = lfilter([0.15], [1, -0.85], out)
    event = (out > 0.5).astype(float)

    wt = np.clip(4.6 + p["wh_off"] + 0.05 * (amb - 18) + 0.4 * A + exc + ar(0.92, 0.3), 0, 11.97)
    wh = np.clip(0.5 * amb_hum + 0.5 * 65 + 0.8 * exc + ar(0.9, 1.0), 35, 95)
    for s, d in drops:
        m = min(d, n - s)
        wt[s:s + m] = wt[max(s - 1, 0)] + rng.normal(0, 0.005, m)
        wh[s:s + m] = wh[max(s - 1, 0)]

    # categoricals
    rush = np.exp(-((hour - 7.5) / 1.5) ** 2) + np.exp(-((hour - 17) / 1.8) ** 2)
    rush *= (dow < 5)
    tz = rng.normal(0, 1, n) + 1.0 * rush + 0.25 * (loc_id.startswith("JHB")) + 0.3 * event
    traffic = cat(tz, ["Low", "Medium", "High", "Severe"], [0.298, 0.691, 0.930])
    tidx = pd.Series(traffic).map({"Low": 0, "Medium": 1, "High": 2, "Severe": 3}).values
    rain = p["sgn"] * seas
    rz = rng.normal(0, 1, n) + 0.6 * np.clip(rain, 0, None) + 0.1 * yrs
    road = cat(rz, ["Good", "Moderate", "Poor"], [0.519, 0.868])
    ridx = pd.Series(road).map({"Good": 0, "Moderate": 1, "Poor": 2}).values
    dz = rng.normal(0, 1, n) + 1.2 * event + 0.15 * tidx
    disr = cat(dz, ["None", "Minor", "Moderate", "Major"], [0.35, 0.71, 0.93])
    didx = pd.Series(disr).map({"None": 0, "Minor": 1, "Moderate": 2, "Major": 3}).values
    sens = cat(rng.normal(0, 1, n), ["Low", "Medium", "High"], [0.301, 0.72])
    sidx = pd.Series(sens).map({"Low": 0, "Medium": 1, "High": 2}).values

    # transit
    dist = np.clip(np.exp(rng.normal(5.056, 0.48, n)) * p["dist"], 20, 650)
    planned = np.clip(dist / np.clip(rng.normal(38, 8, n), 20, 70), 0.5, 20)
    speed = np.clip(rng.normal(52, 14, n) - 3.0 * tidx, 10, 90)
    tdel = np.clip(np.array([0.25, 0.6, 1.1, 1.8])[tidx] * rng.lognormal(0, 0.3, n), 0.05, 2.6)
    rdel = np.where(ridx == 0, 0, np.where(ridx == 1, rng.gamma(2, 0.15, n), rng.gamma(2, 0.45, n)))
    rdel = np.clip(rdel, 0, 1.4)
    xdel = rng.exponential(np.array([0.06, 0.12, 0.3, 0.8])[didx])
    delay = tdel + rdel + xdel
    actual = planned + delay
    window = rng.uniform(1.5, 12, n)
    urg = cat(rng.normal(0, 1, n) - 0.15 * (window - 6.7) / 3, ["Low", "Medium", "High", "Critical"], [0.199, 0.557, 0.899])

    # vehicle / ops
    age = rng.integers(1, 16, n)
    cool = np.clip(56.7 + 1.2 * (amb - 18.5) + 2 * exc - 30 * comp + 10 * (lab == "TEMP_EXCURSION") + rng.normal(0, 11, n), 5, 100)
    fuel = np.clip(rng.normal(62, 17.5, n), 10, 100)
    eng = np.clip(rng.normal(61.5, 14.5, n) + 2 * (tidx - 1), 15, 100)
    load_min = np.clip(5 + rng.gamma(2.2, 6.8, n) * (1 + 0.2 * A), 5, 90)
    unload_min = np.clip(5 + rng.gamma(2.0, 5.3, n) * (1 + 0.2 * A), 5, 80)
    handling = np.clip(1 + rng.poisson(9.0 * A), 1, 8)

    temp = np.clip(4.5 + 0.6 * exc + 0.08 * (amb - 18.5) + rng.normal(0, 2.5, n), -2, 12)
    tvar = np.clip(rng.gamma(3.3, 0.56, n) + 0.3 * exc, 0.1, 5.5)
    hum = np.clip(rng.normal(67.8, 12, n) + 0.5 * (amb_hum - 65) / 2, 35, 95)
    hvar = np.clip(rng.gamma(3.6, 1.7, n), 0.5, 20)

    # freshness / spoilage
    f0 = np.clip(100 - rng.gamma(2.2, 1.9, n) - 0.4 * sidx, 84, 100)
    sf = np.array([0.8, 1.0, 1.4])[sidx]
    loss = (0.4 * actual * sf + 0.15 * handling + 0.35 * tvar + 0.3 * np.clip(temp - 6, 0, None) * sf
            + 0.1 * delay + rng.normal(0, 0.8, n))
    loss = np.clip(loss, 0.1, None)
    f1 = np.clip(f0 - loss, 0, 100)
    z = -0.85 + 0.55 * (loss - 4.45) + 0.3 * (sidx - 1) + 0.35 * exc + rng.normal(0, 0.3, n)
    spoil = 1 / (1 + np.exp(-z))

    energy = np.clip(10 + 0.1 * dist * cool / 57 + 1.5 * actual + 0.3 * (amb - 18.5) + rng.normal(0, 4, n), 10, 118.2)
    infl = 1.06 ** (yrs - 2.4)
    cost = np.clip((250 + 0.9 * dist + 3.2 * energy + 6 * age + 25 * delay + 20 * didx + 60 + rng.normal(0, 60, n)) * infl, 213.35, 1291.4)
    sensor = np.clip(100 - rng.gamma(1.9, 3.4, n) * (1 + 2 * event), 77, 100)
    sensor = np.where(drop == 1, rng.uniform(15, 55, n), sensor)
    flex = np.clip(rng.normal(64.3, 10, n) - 4 * (tidx - 1.08) - 2 * (ridx - 0.6), 26, 96)

    score = (actual - window) / 3 + 1.5 * spoil + 0.3 * didx + rng.normal(0, 0.3, n)
    status = cat(score, ["On_Time", "At_Risk", "Delayed"], [0.55, 0.82])

    df = pd.DataFrame({
        "Timestamp": ts, "Storage_Location_ID": loc_id, "Storage_Location": p["city"],
        "Temperature_C": temp, "Humidity_Percent": hum, "Temperature_Variation": tvar, "Humidity_Variation": hvar,
        "Vehicle_Age_Years": age, "Cooling_Load_Percent": cool, "Fuel_Level_Percent": fuel, "Vehicle_Speed_kmph": speed,
        "Engine_Load_Percent": eng, "Route_Distance_km": dist, "Traffic_Level": traffic, "Road_Condition": road,
        "Planned_Transit_Time_hr": planned, "Traffic_Delay_hr": tdel, "Road_Delay_hr": rdel, "Transit_Delay_hr": delay,
        "Actual_Transit_Time_hr": actual, "Remaining_Time_Window_hr": window, "Delivery_Urgency": urg,
        "Warehouse_Temperature_C": wt, "Warehouse_Humidity_Percent": wh, "Loading_Duration_min": load_min,
        "Unloading_Duration_min": unload_min, "Handling_Events": handling, "Product_Sensitivity": sens,
        "Initial_Freshness_Percent": f0, "Estimated_Freshness_Percent": f1, "Spoilage_Risk": spoil,
        "Energy_Consumption_kWh": energy, "Operational_Cost": cost, "Disruption_Level": disr,
        "Sensor_Connectivity": sensor, "Route_Flexibility": flex, "Delivery_Status": status, "Exception_Type": lab,
    })
    return df


df = pd.concat([gen(k, v) for k, v in LOCS.items()], ignore_index=True).sort_values(["Timestamp", "Storage_Location_ID"]).reset_index(drop=True)
num = df.select_dtypes("float").columns
df[num] = df[num].round(3)
out = sys.argv[1] if len(sys.argv) > 1 else "cold_chain_labeled_2022_2026.csv"
df.to_csv(out, index=False)
print(df.shape, df.Timestamp.min(), df.Timestamp.max())
