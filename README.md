# NS CalDAV Trip - Home Assistant integration

A custom Home Assistant integration that watches a CalDAV calendar (for example
your iCloud calendar) for NS share links, resolves each one into a live trip via
the NS Reisinformatie API, and exposes the **next upcoming trip** as a set of
sensors - including delay and disruption information.

The calendar is **not** shown as a calendar entity. Instead:

1. Every hour the integration scans your calendar for appointments whose text
   contains an NS share link of the form `https://www.ns.nl/rpx?s=<token>`.
2. Each link is followed through its redirects until a URL with a `ctxRecon`
   parameter is reached. The `ctxRecon` is stored in a small persistent database
   so discovery is decoupled from live polling.
3. The nearest upcoming trip is polled from the NS API. Polling gets **more
   frequent the closer departure is** (hourly when far away, every 2 minutes in
   the last 20 minutes).

## Requirements

- Home Assistant 2024.1 or newer.
- A CalDAV calendar URL with username/password.
  - For **iCloud**, create an [app-specific password](https://support.apple.com/en-us/102654)
    and use the CalDAV URL `https://caldav.icloud.com/`.
- An **NS API subscription key** (`Ocp-Apim-Subscription-Key`) for the
  *Reisinformatie API (Ns-App)* product from the
  [NS API portal](https://apiportal.ns.nl/).

## Installation

### Option A - HACS (custom repository)

1. In HACS, open the **three-dot menu -> Custom repositories**.
2. Add `https://github.com/gigadesign1/ns_caldav` and choose category **Integration**.
3. Search for **NS CalDAV Trip**, install it.
4. Restart Home Assistant.

### Option B - Manual

1. Copy the `custom_components/ns_caldav` folder into your Home Assistant
   `config/custom_components/` directory, so you end up with
   `config/custom_components/ns_caldav/`.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings -> Devices & Services -> Add Integration**.
2. Search for **NS CalDAV Trip**.
3. Fill in:
   - **CalDAV URL** (e.g. `https://caldav.icloud.com/`)
   - **Username** and **Password** (app-specific password for iCloud)
   - **NS API subscription key**
   - **Verify SSL certificate** (leave on unless you know otherwise)

### Options (after setup)

Open the integration and choose **Configure** to tune:

| Option | Default | Description |
| --- | --- | --- |
| Calendar scan interval (hours) | 1 | How often the calendar is scanned for new links |
| Calendar look-ahead (days) | 30 | How far ahead appointments are scanned |
| Leave-soon lead time (minutes) | 10 | When the `Leave soon` sensor turns on before departure |
| Delay threshold (minutes) | 1 | Minimum delay before the `Delayed` sensor turns on |

## How to add a trip

In the NS app or on ns.nl, plan a trip and use **Share** to get a link like
`https://www.ns.nl/rpx?s=Na8wW2Bk`. Paste that link into a calendar appointment
(in the title, notes/description, location, or URL field) at the time you intend
to travel. Within an hour the integration will pick it up.

## Entities

All entities are grouped under a single device, **NS Trip (Next)**, and always
reflect the nearest upcoming trip. They become `unavailable` when there is no
upcoming trip.

### Sensors

- **Departure** / **Arrival** - timestamps (planned time and delay as attributes)
- **Departure station** / **Arrival station** - station name, with `planned_time`,
  `actual_time`, `delay_minutes`, `track`, `uic_code` attributes
- **Departure track**
- **Departure delay** / **Arrival delay** - minutes
- **Duration** - minutes
- **Transfers**
- **Status** - `NORMAL`, `DISRUPTION`, `CANCELLED`, ...
- **Crowd forecast**
- **Departure in** - minutes until departure
- **Price** - total fare in EUR (base/supplement as attributes)
- **Trip summary** - `origin -> destination`, with a rich attribute set including
  a notification-ready `summary_text`, per-leg breakdown, prices and stations

### Binary sensors

- **Leave soon** - on from `departure - lead time` until departure
- **Delayed** - on when the delay exceeds the configured threshold
- **Disruption** - on when the trip is cancelled/disrupted or has messages

## Example automations

Notify when it's time to leave (uses the `Leave soon` sensor):

```yaml
automation:
  - alias: "Notify before NS trip"
    trigger:
      - platform: state
        entity_id: binary_sensor.ns_trip_next_leave_soon
        to: "on"
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: >
            Vertrek over {{ states('sensor.ns_trip_next_departure_in') }} min.
            {{ state_attr('sensor.ns_trip_next_trip_summary', 'summary_text') }}
```

Notify on delay or disruption:

```yaml
automation:
  - alias: "Notify NS delay"
    trigger:
      - platform: state
        entity_id: binary_sensor.ns_trip_next_delayed
        to: "on"
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: >
            Vertraging: {{ state_attr('sensor.ns_trip_next_trip_summary', 'summary_text') }}
```

> Entity IDs are generated from the device name; check **Developer Tools ->
> States** for the exact IDs in your installation.

## Dashboard card

The integration ships a custom Lovelace card, **NS Perronbord**, that shows the
next trip styled like an NS departure board. It is registered automatically when
the integration loads - there is **no need to add a resource manually**. (If the
card type isn't recognised the first time, do a hard refresh of the browser.)

The card has two variants:

- `board` (default) - the calm, on-time NS-blue departure screen.
- `alert` - an emphasised NS-yellow "pop-out" for when the trip is delayed or
  disrupted (shows the new departure time, delay, platform and any disruption
  message).

The card reads everything from the trip summary sensor, which it **finds
automatically** (it locates the entity exposing the `summary_text` attribute), so
it works regardless of your Home Assistant language and the resulting entity IDs.

### Basic usage (recommended)

```yaml
type: custom:ns-perronbord-card
```

That single card is all you need: it shows the calm `board` style when the trip
is on time and **automatically pops out to the emphasised `alert` style** when
the trip is delayed or disrupted (bigger card, new departure time, delay,
platform and the disruption message). No conditional cards required.

### Conditional pop-out (advanced)

If you prefer two genuinely separate cards (e.g. to place the alert in a
different spot), wrap them in built-in `conditional` cards. Note that the
integration's binary-sensor entity IDs are localized - in a Dutch instance they
are `binary_sensor.ns_trip_next_vertraagd` and
`binary_sensor.ns_trip_next_verstoring`; in English
`binary_sensor.ns_trip_next_delayed` / `..._disruption`. Check **Developer Tools
-> States** for your exact IDs and substitute them below.

```yaml
type: conditional
conditions:
  - condition: state
    entity: binary_sensor.ns_trip_next_delayed
    state: "off"
  - condition: state
    entity: binary_sensor.ns_trip_next_disruption
    state: "off"
card:
  type: custom:ns-perronbord-card
```

```yaml
type: conditional
conditions:
  - condition: or
    conditions:
      - condition: state
        entity: binary_sensor.ns_trip_next_delayed
        state: "on"
      - condition: state
        entity: binary_sensor.ns_trip_next_disruption
        state: "on"
card:
  type: custom:ns-perronbord-card
  variant: alert
```

> Because the binary sensors are `unavailable` when there is no upcoming trip,
> both conditional cards render nothing - the dashboard slot stays empty until a
> trip is scheduled.

### Options

| Option | Default | Description |
| --- | --- | --- |
| `entity` | _auto-detected_ | Override the trip summary sensor to read from |
| `variant` | `board` | `board`, or `alert` to force the emphasised style |

## Notes & limitations

- Only the **single nearest** upcoming trip is exposed. Multiple appointments are
  discovered and stored, but sensors always track the next one.
- The CalDAV/`ctxRecon` resolution relies on NS's current share-link redirect
  behaviour; if NS changes their URL scheme, discovery may need updating.
- Calendar discovery and trip polling are independent: a calendar outage does not
  stop live trip updates, and vice versa.
