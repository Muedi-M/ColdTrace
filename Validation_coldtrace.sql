-- ColdTrace BigQuery Data Validation Queries
-- Replace `your-project.coldtrace_warehouse.sample_14d` and column names
-- with your exact deployed project, dataset, table, and timestamp/temp columns.

-- 1. Row count & basic completeness check on sample_14d (expected: 2,016 rows)
SELECT
  COUNT(*) AS total_rows,
  COUNTIF(timestamp IS NULL OR temperature_c IS NULL) AS null_critical_fields,
  MIN(timestamp) AS min_timestamp,
  MAX(timestamp) AS max_timestamp
FROM `your-project.coldtrace_warehouse.sample_14d`
WHERE DATE(timestamp) BETWEEN DATE('2026-11-01') AND DATE('2026-11-30');

-- 2. Pharmaceutical safe-band excursion check (2.0°C to 8.0°C)
SELECT
  location_id,
  COUNTIF(temperature_c < 2.0 OR temperature_c > 8.0) AS excursion_alerts,
  MIN(temperature_c) AS min_temp_c,
  MAX(temperature_c) AS max_temp_c,
  ROUND(AVG(temperature_c), 2) AS avg_temp_c
FROM `your-project.coldtrace_warehouse.sample_14d`
WHERE DATE(timestamp) BETWEEN DATE('2026-11-01') AND DATE('2026-11-30')
GROUP BY location_id
ORDER BY location_id;

-- 3. Sensor dropout / flat-run gap check (audit benchmark: 48.0h total dropout)
WITH ordered_readings AS (
  SELECT
    location_id,
    timestamp,
    temperature_c,
    LAG(timestamp) OVER (PARTITION BY location_id ORDER BY timestamp) AS prev_timestamp,
    LAG(temperature_c) OVER (PARTITION BY location_id ORDER BY timestamp) AS prev_temp_c
  FROM `your-project.coldtrace_warehouse.sample_14d`
  WHERE DATE(timestamp) BETWEEN DATE('2026-11-01') AND DATE('2026-11-30')
)
SELECT
  location_id,
  COUNTIF(TIMESTAMP_DIFF(timestamp, prev_timestamp, MINUTE) > 30) AS gap_events,
  ROUND(
    SUM(
      CASE
        WHEN TIMESTAMP_DIFF(timestamp, prev_timestamp, MINUTE) > 30
        THEN TIMESTAMP_DIFF(timestamp, prev_timestamp, MINUTE) / 60.0
        ELSE 0
      END
    ),
    1
  ) AS dropout_hours
FROM ordered_readings
GROUP BY location_id
ORDER BY location_id;
