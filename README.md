# Introduction

Bulk Firmware Upgrade is a UI Component that installs one firmware version on many IXON
devices at once, and follows each installation to completion. It lists the whole fleet, lets you narrow it
down by group or search, and starts the upgrade on every device you tick.

Every API call is made from the browser with `ComponentContext`, so it runs with the
permissions of the user looking at it and never sees more of the fleet than
that user is allowed to manage.

## Features

**General**

- Multi-select group filter with its own search box. Picking a parent group
  includes every group beneath it. Groups that hold no devices are not offered.
- Free-text search over name, serial number and firmware version.
- Both filters affect the view only. A device you ticked stays selected when
  you change filters, and the confirmation dialog names every device before
  anything is installed.
- A padlock icon replaces the checkbox on locked devices. This happens when a device is under factory audit, which grants the factory the authority to block firmware upgrades by the machine builder. The boolean controlling this behaviour is the `firmwareUpdateLocked` field of an Agent.

**Device eligibility**

Devices are never hidden for being ineligible: they are greyed out, with the
cursor showing they cannot be picked. The reasons, in the order they are
reported:

| Reason | Meaning |
| --- | --- |
| Not compatible | The version is not published for this device's agent type |
| Already up to date | The device is already running the target version |
| Offline | The device has no connection, so nothing can be installed |
| Locked | `firmwareUpdateLocked` is set, so upgrades are blocked by policy |

**Firmware versions**

- Versions are grouped per agent type, newest first, with the newest marked
  `(latest)`.
- Agent types that share a firmware track are merged into one group. Out of the
  box, SecureEdge and SecureEdge Pro are listed together as one track; a
  version is offered for whichever types in the family actually publish it.
- A **14-day release cooldown**: a version released less than two weeks ago is
  shown with the wait remaining (e.g. `3.31 (latest) — available in 9 days`) and
  cannot be selected. A bulk tool multiplies the blast radius of a bad release,
  so new versions go through the normal one-device-at-a-time flow first.
- Versions newer than the one flagged `latest` are not listed at all.

**Running an upgrade, and failures**

- Upgrades are requested in batches of five, so the progress table fills up
  instead of waiting on one long round trip. Each device is requested
  separately: one rejected request does not stop the others.
- Progress is followed over the change-notification WebSocket. A device that
  comes back online reporting a different firmware version counts as
  **Completed**; one that returns on its old version, or reports no version at
  all, counts as **Failed**.
- A device that never reports back is given up on after **30 minutes**, so one
  silent device cannot leave the component spinning forever.
- If the WebSocket cannot connect, the run still starts, but it cannot report progress.
- A finished run with failures offers a retry for only the failed devices, and
  the whole run can be exported as a CSV.

## Requirements

- A component workspace based on
  [ixoncloud/component-workspace](https://github.com/ixoncloud/component-workspace)
  (see below).
- **Svelte 5.** The component uses runes (`$state`, `$derived`, `$effect`) and
  `SvelteSet`.
- **`@ixon-cdk/types`** for the platform types:

  ```sh
  $ npm install -D @ixon-cdk/types
  ```

- **`"target": "ES2020"`** in the UI project's `tsconfig.json`. The default
  `@tsconfig/svelte` target is ES2017, which does not have `String.matchAll`.

## Getting started

You need [Node.js](https://nodejs.org/) and an IXON Cloud account. Clone this
repository and install the CDK and its dependencies:

```sh
$ npm install
```

Then run the component in the simulator, which rebuilds and reloads on every
change to the source. Point it at your own company from the simulator settings
to work with real devices:

```sh
$ npx cdk simulate bulk-firmware-upgrade
```

## Deploying


When you are ready to use it in the platform, log in and deploy. Deploying
prompts for a **company ID** and a **page-component-template ID**; see
[Deploying UI Components](https://developer.ixon.cloud/docs/deploying-ui-components),
steps 4 and 5, for where to find them.

```sh
$ npx cdk login
$ npx cdk deploy bulk-firmware-upgrade
$ npx cdk publish bulk-firmware-upgrade
```

## Permissions

The component only shows devices the current user may actually upgrade. It
reads the user's roles and keeps the ones granting `MANAGE_AGENT` (or
`COMPANY_ADMIN`). A company-wide role means the whole fleet; otherwise the
fleet is narrowed to the devices reachable through that user's group
memberships, including IXON's per-device groups.

A user with no such role sees an empty list rather than devices they cannot act
on.

## Documentation and support

- [UI Component development docs](https://developer.ixon.cloud/docs/getting-started-ui-components)
- [@ixon-cdk/runner](https://www.npmjs.com/package/@ixon-cdk/runner) (every workspace command)