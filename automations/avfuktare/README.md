# Avfuktare - notis när tanken är full

Larmar till telefonen när en avfuktare troligen är full och har
stängt av sig i väntan på att tömmas. Bygger i första hand på
strömförbrukningen från en Shelly-plugg, inte på Tuya-molnet.

## Bakgrund

Två avfuktare står i förråden och stänger av sig själva när tanken
är full. Det är lätt att missa, så vatten hinner byggas upp i luften
igen. En Shelly Plug S Gen3 sitter på den inre enheten (Otto) och
matar strömförbrukningen till Home Assistant.

En kompressoravfuktare stannar kompressorn när tanken är full - den
slutar göra vatten och väntar på tömning. Då faller effekten till i
princip noll och ligger kvar där tills du tömmer. Det är den
signaturen vi larmar på.

## Verifierad signatur

Uppmätt på en riktig full-cykel (Otto, 2026-07-04):

| Läge                     | Effekt          | Längd i mätningen |
|--------------------------|-----------------|-------------------|
| Avfuktar (kompressor på) | ~234 W, stabilt | 08:27-11:40       |
| FULL (kompressor stoppad)| 0 W, platt      | 11:41-14:37 (~3h) |
| Tömd, igång igen         | ~234 W          | från 14:38        |

Full-läget är alltså ~0 W, inte fläktnivå. Ett tidigt stickprov
visade ~34 W en kort stund, men det var en övergång vid
installationen, inte fullt-läget. Under hela 0 W-platån var pluggen
fortfarande på och elpriset lågt, så det var varken en urdragen
plugg eller en prisavstängning - det var full tank.

Detektionen: effekten vid eller under en låg tröskel (standard
10 W) ihållande i minst `low_duration` (standard 30 min) medan
pluggen är på och elpriset lågt.

## Varför inte bara Tuya?

Otto exponerar `binary_sensor.otto_dehumidifier_tank_full` via Tuya.
Det är den rätta signalen när den fungerar. Men i praktiken:

- Tuya är molnberoende och har stått `unavailable` i veckor - även
  under full-cykeln ovan gav den inget värde alls. Home Assistant
  exporterar inte ens något till VictoriaMetrics medan den är
  otillgänglig.
- Shelly är lokal och alltid tillgänglig.

Därför är effektsignaturen primär och Tuya bara ett komplement som
ger direktlarm när det råkar fungera. Den yttre enheten har ingen
Tuya-sensor alls och vilar helt på effekten.

## Att skilja 0 W-full från andra 0 W-lägen

Tre saker kan ge 0 W. Detektionen skiljer dem så här:

- Urdragen eller frånslagen plugg. Switchen är då off, och villkoret
  att pluggen ska vara på tar bort det fallet.
- Prisavstängd. Prisstyrningen
  (`scripts/set_dehumidify_from_electricity_price`) stänger av när
  elpriset når 1.0 kr. Då är 0 W avsiktligt. Prisvillkoret larmar
  bara när priset är lågt, det vill säga när enheten borde vara
  igång. Verifierat: under full-cykeln var priset 0.11-0.14 kr, så
  larmet hade gått korrekt.
- Nådd målfukt. Stannar också kompressorn, men återupptar när fukten
  stiger igen. En full tank ligger på 0 W tills du tömmer;
  `low_duration` skiljer dem åt.

Kvarvarande känt fall: om någon trycker på enhetens egen av-knapp
(plugg på, pris lågt) ser det ut som full. I praktiken står de alltid
på, så det är inget problem här.

## Filer

| Fil                              | Roll |
|----------------------------------|------|
| `tank_full_notify.blueprint.yaml`| Blueprint - själva logiken, en instans per avfuktare |
| `inneforrad_otto.yaml`           | Aktiv instans för Otto (Shelly + Tuya) |
| `uteforrad.yaml`                 | Förberedd instans för uteförrådet (aktiveras när en Shelly sätts dit) |

Effektsensorn och pluggens on/off läggs också till i prometheus-
filtret i `metrics/hass/configuration.yaml` så förbrukningen
långtidslagras i VictoriaMetrics och kan grafas i Grafana.

## Installation

En egen blueprint kan inte skapas direkt i gränssnittet. Blueprints-
fliken har bara Import blueprint, som tar en URL, så du måste antingen
importera den från GitHub eller lägga filen på plats. Instansen (själva
automationen) skapas sedan från blueprinten i gränssnittet.

### 1. Få in blueprinten

Alternativ A - importera från URL (rekommenderas, helt i GUI:t).
Repot är publikt, så när filen är pushad till GitHub:

1. Settings → Automations & Scenes → fliken Blueprints.
2. Klicka Import blueprint (längst ner till höger).
3. Klistra in URL:en:
   `https://github.com/smuda/home_assistant/blob/main/automations/avfuktare/tank_full_notify.blueprint.yaml`
4. Preview → Import. Blueprinten dyker upp i listan.

HA hämtar bara filen och lägger den på rätt plats själv; att den ligger
under `automations/avfuktare/` i repot spelar ingen roll.

Alternativ B - lägg filen via File editor (om du inte vill pusha). Det
du ser i File editor är redan innehållet i `/config`, så det finns
ingen `config`-mapp att gå in i - leta efter `blueprints` direkt i
roten. Skapa en ny fil och skriv hela sökvägen i sökvägsrutan (mappar
skapas automatiskt):
`blueprints/automation/avfuktare/tank_full_notify.blueprint.yaml`
Klistra in innehållet och spara.

### 2. Skapa automationen från blueprinten

1. Settings → Automations & Scenes → Create automation.
2. Use blueprint → välj "Avfuktare full - notis (effekt + valfri
   Tuya)".
3. Fyll i fälten enligt `inneforrad_otto.yaml` (effektsensor,
   strömbrytare, Tuya tank_full på, notistjänst, påminnelse 6 h).
   Resten kan stå kvar på standard.

### 3. Långtidsloggning av effekten

Lägg in ändringen i `metrics/hass/configuration.yaml` (Shelly-effekt
och switch i prometheus-filtret) och starta om så VictoriaMetrics
börjar skrapa den. Behövs för att grafa full-cykler och finjustera
trösklarna.

## Justering

Standardvärdena bygger på den verifierade full-cykeln, men kan
finjusteras per enhet:

- `full_power_max` (standard 10 W) - effekt vid eller under detta
  räknas som stoppad, alltså kandidat för full. Ligger väl under de
  ~234 W enheten drar igång.
- `low_duration` (standard 30 min) - hur länge effekten ska ha legat
  lågt innan larm. Full-platån varade ~3 h, så 30 min är väl
  tilltaget mot korta pauser.
- `running_power_min` (standard 100 W) - över detta räknas som igång
  igen, används för den valfria tömd-notisen.
- `use_price_gate` och `price_off_above` (standard på respektive
  1.0 kr) - larma bara när priset är under tröskeln. Matcha
  prisstyrningens tröskel.
- `reminder_hours` (standard 6 h i Otto-instansen) - upprepa notisen
  så länge tanken är full. 0 = larma bara en gång.

## Andra enheten (uteförrådet)

`fan.avfuktare` och `humidifier.avfuktare` saknar idag både
effektmätare och tank_full-sensor. När en Shelly-plugg sätts dit:
fyll i de nya entiteterna i `uteforrad.yaml`, avkommentera, och ladda
om. Verifiera trösklarna mot den enhetens egen full-cykel -
kompressoreffekten kan skilja sig från Ottos.
