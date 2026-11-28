# User research — guide, survey and evidence log

Purpose: replace assumptions about the operations lead with evidence. Record only real
conversations. If an interview did not happen, the row stays empty.

## Representative persona scenarios (submitted with the capstone)

Composed by the team from the cited evidence (WHO, SA NDoH SOP, alarm-fatigue studies) to describe the users ColdTrace serves. They are illustrative personas, **not** verbatim interview quotes; the evidence log below records real interviews only.

| # | Pain point | Persona | Scenario |
|---|---|---|---|
| 1 | Manual logging & overnight blind spots | Clinic Sister, primary healthcare | “Between morning patient queues and stock counts, writing down fridge temperatures on paper twice a day feels like a tick-box exercise—if the temperature spikes at 2 AM, nobody knows until 7 AM.” |
| 2 | Alarm fatigue from routine door openings | Dispensary Pharmacist | “When the fridge beeps every time someone opens the door to grab vials, staff start ignoring it. By the time we realize it's an actual cooling failure, we're scrambling to move stock.” |
| 3 | Power fluctuations & quarantine uncertainty | Cold-Chain Logistics Coordinator | “During power fluctuations or sensor dropouts, our biggest stress is not knowing how long the unit stayed above 8°C—we either risk wasting good vials or second-guess whether a batch needs to be quarantined.” |

## Who to talk to (aim: 3 interviews + 10 survey responses after BUILD)

| Segment | Example roles | Where to find them |
|---|---|---|
| Storage / DC operations | Cold-room supervisor, warehouse shift lead | Pharma wholesalers, 3PL cold stores, food distributors |
| QA / pharmacy | Responsible pharmacist, QA officer | Retail pharmacy, hospital pharmacy, depot QA |
| Clinic / EPI | Nurse responsible for vaccine fridge | Public clinics, private GP practices |

## 15-minute interview guide

1. Walk me through the last time a fridge or cold room went out of range. How did you find out?
2. How long between the failure and someone acting? Who acted?
3. What alarms or loggers do you have today? How many alerts in a normal week? How many are real?
4. When an alert fires, what do you do, step by step? Who signs off that stock is safe or destroyed?
5. What records do auditors or inspectors ask for afterwards? How long does it take to produce them?
6. What would make you trust an automatic alert enough to hold a shipment?
7. (Show the console, 2 minutes) What is the first thing you would click? What is missing?

## 5-question survey (Google Form)

1. Role and type of site.
2. In the last 3 months, how many temperature excursions did your site have? (0 / 1–2 / 3–5 / 6+)
3. How did you usually find out? (live alarm / logger review / staff noticed / after stock was affected)
4. Roughly what share of temperature alerts are false or non-actionable? (<25 % / 25–50 % / 50–75 % / >75 %)
5. Rank: earlier detection · fewer false alarms · audit-ready records · knowing which batches are at risk.

## Evidence log

| # | Date | Role / site type (no names) | Key quote | Pain point | Feature it supports |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |

Survey responses: n = __ (link to anonymised results sheet)

## Pain point → feature map (update once evidence is in)

| Pain point (hypothesis until confirmed above) | ColdTrace feature |
|---|---|
| Failure found after stock is damaged | Random Forest catches excursions in 0.5 h median, cooling failures in 1.0 h |
| Slow drifts and frozen sensors never trip a fixed alarm | Three exception types incl. SENSOR_DROPOUT flat-run detection |
| Alarm fatigue | Debounced alerts, false-alert rate reported per location-day |
| "Which stock is at risk?" | Alert → batch → shipment join; out-of-band shipments held |
| Audit takes days | Hash-chained case events, sealed evidence, `/api/cases/{id}/events` export |
| Nobody owns the alert | Assignment, review/close SLAs, overdue list |
