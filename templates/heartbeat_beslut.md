# Heartbeat batteribeslut

`sensor.heartbeat_batteribeslut` is the 1KOMMA5 optimiser's current
battery decision as a number, so that it survives HA's Prometheus
export (which drops text states) and shows up in the Grafana
"1KOMMA5 Heartbeat" dashboard.

| Code | Plan calendar event         | Meaning                      |
| ---- | --------------------------- | ---------------------------- |
| 0    | none active                 | battery runs freely          |
| 1    | Battery: no discharge       | battery held, no discharge   |
| 2    | Battery: charge from grid   | battery charged from grid    |
| 3    | anything else               | new decision type, look here |

Source is `calendar.sh10_0rt_20_battery_plan_...`: its state is `on`
during a plan event and `message` holds the event title. The decision
sensor was not used because "charge from grid" has only been seen in
the calendar. Code 3 exists so that a decision type the integration
adds later shows up instead of silently reading as 0.
