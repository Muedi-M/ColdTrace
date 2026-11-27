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



-- ============================================================================
-- ColdTrace Warehouse Telemetry Validation Suite (2022–2026 Full Dataset)
-- Table: project-6b73a1f9-ef42-4074-81a.coldtrace_warehouse.telemetry_2022_2026
-- ============================================================================

-- 5. Full Dataset Row Count, Critical Nulls & Date Span
SELECT
  COUNT(*) AS total_rows,
  COUNTIF(Timestamp IS NULL OR Storage_Location_ID IS NULL OR Warehouse_Temperature_C IS NULL) AS null_critical_fields,
  MIN(Timestamp) AS min_timestamp,
  MAX(Timestamp) AS max_timestamp
FROM `project-6b73a1f9-ef42-4074-81a.coldtrace_warehouse.telemetry_2022_2026`;

-- 6. Warehouse Safe-Band Excursion Check (<2.0°C or >8.0°C) by Hub
SELECT
  Storage_Location_ID,
  COUNTIF(Warehouse_Temperature_C < 2.0 OR Warehouse_Temperature_C > 8.0) AS excursion_rows,
  COUNTIF(Warehouse_Temperature_C < 2.0) AS below_2c_rows,
  COUNTIF(Warehouse_Temperature_C > 8.0) AS above_8c_rows,
  ROUND(MIN(Warehouse_Temperature_C), 2) AS min_wh_temp_c,
  ROUND(MAX(Warehouse_Temperature_C), 2) AS max_wh_temp_c,
  ROUND(AVG(Warehouse_Temperature_C), 2) AS avg_wh_temp_c
FROM `project-6b73a1f9-ef42-4074-81a.coldtrace_warehouse.telemetry_2022_2026`
GROUP BY Storage_Location_ID
ORDER BY Storage_Location_ID;

-- 7. Labeled Exception Counts
SELECT
  Exception_Type,
  COUNT(*) AS record_count
FROM `project-6b73a1f9-ef42-4074-81a.coldtrace_warehouse.telemetry_2022_2026`
GROUP BY Exception_Type
ORDER BY record_count DESC;

-- 8. Quarantine & Physical Sensor Range Check
SELECT
  COUNT(*) AS total_rows,
  COUNTIF(
    Timestamp IS NULL
    OR Storage_Location_ID IS NULL
    OR Warehouse_Temperature_C IS NULL
    OR Warehouse_Humidity_Percent IS NULL
    OR Cooling_Load_Percent IS NULL
    OR Sensor_Connectivity IS NULL
    OR Warehouse_Temperature_C < -50.0
    OR Warehouse_Temperature_C > 60.0
    OR Warehouse_Humidity_Percent < 0.0
    OR Warehouse_Humidity_Percent > 100.0
    OR Sensor_Connectivity < 0.0
    OR Sensor_Connectivity > 100.0
  ) AS quarantine_rows,
  COUNTIF(Exception_Type IS NULL) AS null_exception_type_rows
FROM `project-6b73a1f9-ef42-4074-81a.coldtrace_warehouse.telemetry_2022_2026`;
