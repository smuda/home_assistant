// Disables the 1KOMMA5 integration entities that duplicate the Sungrow
// Modbus, P1 and Zaptec sensors, the Automatic Mode switch (one tap turns
// the optimiser off), and everything of the second system on the account
// (not this house). Rules, not ids: an integration reload recreates
// entities under new ids. Registry state lives in .storage, not YAML, so
// re-run this after an integration update or re-add.
// Usage, from the repo root: node 1komma5/scripts/disable_duplicates.mjs
import { readFileSync } from "node:fs";

const URL = process.env.HA_WS_URL ?? "ws://homeassistant.local:8123/api/websocket";
const TOKEN = readFileSync(
  process.env.HA_TOKEN_FILE ?? "metrics/vmconfig/homeassistant-token", "utf8").trim();
const OTHER_SYSTEM = /_00000000_0000_0000_0046_000000000000$/;
const HOUSE_SYSTEM = /_afc12081_4304_4878_97df_a160569e3faf$/;
const DUPLICATE = new RegExp(
  "[._](grid_feed_\\w+|consumption_power|solar_\\w+|battery_state_of_charge"
  + "|battery_(in|out)_power|battery_energy_(in|out)|ev_chargers_\\w+"
  + "|heat_pumps_\\w+|automatic_mode)_afc12081");

const wanted = (id) => OTHER_SYSTEM.test(id) || (HOUSE_SYSTEM.test(id) && DUPLICATE.test(id));

const ws = new WebSocket(URL);
const pending = new Map();
let nextId = 1;
let failed = 0;
const send = (msg) => { const id = nextId++; ws.send(JSON.stringify({ id, ...msg })); return id; };

ws.onmessage = ({ data }) => {
  const msg = JSON.parse(data);
  if (msg.type === "auth_required") {
    ws.send(JSON.stringify({ type: "auth", access_token: TOKEN }));
  } else if (msg.type === "auth_invalid") {
    console.error("auth failed");
    process.exit(1);
  } else if (msg.type === "auth_ok") {
    pending.set(send({ type: "config/entity_registry/list" }), null);
  } else if (msg.type === "result" && pending.get(msg.id) === null) {
    pending.delete(msg.id);
    for (const { entity_id, disabled_by } of msg.result) {
      if (!wanted(entity_id) || disabled_by) continue;
      pending.set(send({ type: "config/entity_registry/update", entity_id, disabled_by: "user" }), entity_id);
    }
    if (pending.size === 0) { console.log("nothing to disable"); ws.close(); }
  } else if (msg.type === "result") {
    const entity_id = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.success) console.log(`disabled ${entity_id}`);
    else { failed++; console.error(`FAILED ${entity_id}: ${msg.error?.message}`); }
    if (pending.size === 0) { ws.close(); process.exitCode = failed ? 1 : 0; }
  }
};
ws.onerror = (e) => { console.error(`websocket error: ${e.message ?? e}`); process.exit(1); };
