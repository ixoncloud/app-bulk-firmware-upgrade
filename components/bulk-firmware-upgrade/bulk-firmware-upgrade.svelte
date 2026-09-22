<script lang="ts">
  import { onMount, untrack } from "svelte";
  import { SvelteSet } from "svelte/reactivity";
  import type {
    Agent,
    AgentTypeFile,
    ComponentContext,
    Group,
    IxApiResponse,
    Role,
    MyUser,
    User,
  } from "@ixon-cdk/types";

  let { context }: { context: ComponentContext } = $props();

  // Types
  interface AgentTypeRef {
    publicId: string;
    name: string;
  }

  // One group in the firmware dropdown: one agent type, or a family.
  interface AgentTypeGroup {
    key: string;
    label: string;
    agentTypePublicIds: string[];
  }

  // A firmware version.
  interface FirmwareOption {
    id: string;
    groupKey: string;
    version: string;
    fileIdByAgentType: Record<string, string>;
    latest: boolean; // True for the newest version offered in this group.
    allowed: boolean; // False while the version is still inside its release cooldown.
    daysRemaining: number | null; // Days left in the cooldown; null when selectable, or when no release date was found.
  }

  // A firmware version before the cooldown rules have been applied.
  interface FirmwareCandidate {
    groupKey: string;
    version: string;
    fileIdByAgentType: Record<string, string>;
    latest: boolean; // Flagged newest by at least one agent type in the group.
    releaseDate: string | null; // The API's own date, when it has one.
    notes: string;
  }

  // An entry in the group picker.
  interface GroupOption {
    id: string;
    // The group's own name, used on the filter button.
    name: string;
    // The group and its type shown in the panel.
    label: string;
    typeName: string;
    typeOrder: number;
  }

  // Why a device cannot take the selected firmware.
  type Ineligibility =
    "incompatible" | "up-to-date" | "offline" | "locked" | null;

  // The subset of a change-notification message this component reads.
  interface ChangeNotification {
    act?: string;
    sel?: { typ?: string }[];
    dat?: Agent[];
  }

  // Constants. Plain objects, not TS enums: Svelte only strips types.
  const TableAgentsStatus = {
    Started: 1,
    Completed: 2,
    Failed: 3,
  } as const;

  const UiState = {
    Loading: 1, // Fetching the fleet and the firmware versions.
    Ready: 2, // The fleet is on screen, waiting for a target version and a selection.
    StartInstall: 3,
    InstallingFirmware: 4,
    InstalledFirmware: 5,
    NoWebsocketStartingInstall: 6,
    NoWebsocketStartedInstall: 7,
    NoPermission: 8, // No role of this user grants managing devices.
  } as const;

  // Agent types that share a firmware track, matched on the type name.
  const AGENT_TYPE_FAMILIES: { label: string; typeNames: string[] }[] = [
    {
      label: "SecureEdge & SecureEdge Pro",
      typeNames: ["SecureEdge", "SecureEdge Pro"],
    },
  ];

  const PAGE_SIZE = "1000";
  const FIRMWARE_COOLDOWN_DAYS = 14; // Firmware becomes selectable this many days after its release date.
  const INSTALL_BATCH_SIZE = 5; // Upgrades are requested in batches so the table fills up progressively.
  const INSTALL_TIMEOUT_MS = 30 * 60 * 1000; // A device silent this long after its request counts as failed.
  const WEBSOCKET_RENEWAL_MS = 3_300_000; // Renew the WebSocket auth token 5 minutes before it expires.
  const NARROW_WIDTH_PX = 580;
  const WIDE_COLUMNS_WIDTH_PX = 800; // Below this the Type and Groups columns are dropped.
  const TEXT_UPDATES_LOCKED = "Firmware updates are locked for this device.";

  // Reactive state
  let rootEl: HTMLElement | undefined = $state();
  let width: number | null = $state(null);
  const isNarrow = $derived(width !== null && width <= NARROW_WIDTH_PX);
  let uiState: number = $state(UiState.Loading);

  let selectedFirmware: FirmwareOption | null = $state(null);
  let agentTypeGroups: AgentTypeGroup[] = $state([]);
  let firmwareList: FirmwareOption[] = $state([]);
  let allAgents: Agent[] = $state([]);

  const selectedAgentIds = new SvelteSet<string>();
  let sortColumn: string = $state("name");
  let sortAscending = $state(true);
  let lastToggledIndex: number | null = null;
  let deviceSearch = $state("");
  const selectedGroupIds = new SvelteSet<string>(); // Group ids the table is filtered to; empty means every group.
  let groupPickerOpen = $state(false);
  let groupPickerEl: HTMLElement | undefined = $state();
  let groupSearch = $state("");
  let groupNamesById: Map<string, string> = $state(new Map());
  let groupParentById: Map<string, string> = $state(new Map());
  let groupChildrenById: Map<string, string[]> = $state(new Map());
  let companyGroupIds: Set<string> = $state(new Set());
  let groupTypeById: Map<string, { name: string; order: number }> = $state(
    new Map(),
  );
  let deviceSpecificGroups: Map<string, string> = $state(new Map());

  let installTargets: Agent[] = $state([]); // The devices an installation was actually started for.
  let tableAgentsStatus: number | null = $state(null);
  let agentsStatusStarted: Agent[] = $state([]);
  let agentsStatusCompleted: Agent[] = $state([]);
  let agentsStatusFailed: Agent[] = $state([]);

  let activeWebsocket: boolean | null = $state(null);
  let allRequestsSent = $state(false); // True once an upgrade has been requested for every target device.

  let agentsStatusStartedBackup: Agent[] = [];
  let activeWebsocketConn: WebSocket | undefined;
  let timerWebsocketRenewal: ReturnType<typeof setTimeout> | undefined;
  let timerInstallTimeout: ReturnType<typeof setTimeout> | undefined;
  let groupsLoaded: Promise<void> | null = null;
  let websocketWarningShown = false;
  // Public id -> why this device failed, for the CSV
  let failureReasons = new Map<string, string>();

  // Status bar and dialog texts

  const TEXT_TIME_INDICATION =
    "After an installation has started, it usually takes 2 to 5 minutes for the installation to complete. Do not turn off or unplug the device during this period.\n\n";
  const TEXT_WEBSOCKET_ERROR =
    "Installation progression cannot be displayed because the WebSocket connection failed. Please contact your local IT to allow your browser's WebSocket connection for future uses of this app and in the meantime see the Portal or Fleet Manager for each device's connection status and firmware version.\n\n";
  const TEXT_FAILED_DEVICES =
    'Devices with status "Failed" have not been able to complete their firmware installation: the installation could not be started, the device did not come back online within 30 minutes, or it came back online still running its old firmware version.\n\n';
  const TEXT_SUPPORT_WEBSITE =
    'The "Firmware upgrade" article on our support website provides help with any unsuccessful firmware installations (support.ixon.cloud).';
  const TEXT_EXPORT_RESULTS = "Export installation results as CSV";
  const TEXT_BACK_TO_LIST = "Back to device list";
  const TEXT_NO_PERMISSION =
    "Your user cannot access, manage or update devices. Please, contact your administrator for assistance.";

  // States during which upgrades have been requested but not all settled.
  const INSTALLING_STATES: number[] = [
    UiState.StartInstall,
    UiState.InstallingFirmware,
    UiState.NoWebsocketStartingInstall,
  ];

  const loading = $derived(uiState === UiState.Loading);
  const installing = $derived(INSTALLING_STATES.includes(uiState));
  const firmwareSelectDisabled = $derived(loading || installing);

  // Why this device cannot take the firmware, or null. First reason wins.
  function ineligibilityOf(
    agent: Agent,
    firmware: FirmwareOption | null,
  ): Ineligibility {
    if (!firmware) return "incompatible";
    const typeId = agent.type?.publicId ?? "";
    if (!(typeId in firmware.fileIdByAgentType)) return "incompatible";
    if (agent.lastSeenAgentUserAgent?.firmwareVersion === firmware.version) {
      return "up-to-date";
    }
    if (!agent.mdrServer) return "offline";
    if (agent.firmwareUpdateLocked) return "locked";
    return null;
  }

  // Connectivity only. A lock shows as a padlock next to the row.
  function statusTextFor(agent: Agent): string {
    return agent.mdrServer ? "Online" : "Offline";
  }

  function isUpgradable(agent: Agent): boolean {
    return ineligibilityOf(agent, selectedFirmware) === null;
  }

  // Greyed out because the chosen firmware cannot go on it.
  function isBlocked(agent: Agent): boolean {
    return selectedFirmware !== null && !isUpgradable(agent);
  }

  // Devices the selected firmware can actually be installed on.
  const upgradableAgents = $derived(allAgents.filter(isUpgradable));
  const selectedAgents = $derived(
    upgradableAgents.filter((agent) => selectedAgentIds.has(agent.publicId)),
  );
  const allSelected = $derived(
    upgradableAgents.length > 0 &&
      selectedAgents.length === upgradableAgents.length,
  );
  // Ticking is only possible once there is a target version to install.
  const selectable = $derived(
    uiState === UiState.Ready &&
      selectedFirmware !== null &&
      tableAgentsStatus === null,
  );
  const canStartInstallation = $derived(
    uiState === UiState.Ready && selectedAgents.length > 0,
  );
  // A finished run with failures can be repeated for just those devices.
  const canRetry = $derived(
    uiState === UiState.InstalledFirmware && agentsStatusFailed.length > 0,
  );
  const installButtonEnabled = $derived(canStartInstallation || canRetry);

  // Shows a cell's full text on hover, but only while it is clipped.
  function cellTooltip(node: HTMLElement) {
    const tooltip = context.createTooltip(node, {
      message: "",
      disabled: true,
      position: "top",
    });
    const sync = () => {
      // data-tooltip wins; otherwise the cell's own text, and only when clipped
      const explicit = node.dataset.tooltip;
      if (explicit) {
        tooltip.setMessage(explicit);
        tooltip.enable();
        return;
      }
      if (node.scrollWidth <= node.clientWidth) {
        tooltip.disable();
        return;
      }
      tooltip.setMessage(node.textContent?.trim() ?? "");
      tooltip.enable();
    };
    node.addEventListener("pointerenter", sync);
    return {
      destroy() {
        node.removeEventListener("pointerenter", sync);
        tooltip.destroy();
      },
    };
  }

  // Clicking a row toggles it, except when the click was the checkbox.
  function handleRowClick(event: MouseEvent, index: number): void {
    if (!selectable) return;
    const agent = visibleAgents[index];
    if (!agent || !isUpgradable(agent)) return;
    const target = event.target as HTMLElement | null;
    // The checkbox handles its own click, so do not toggle twice
    if (target?.tagName === "INPUT") return;
    applySelection(
      index,
      !selectedAgentIds.has(agent.publicId),
      event.shiftKey,
    );
  }

  // `change` carries no modifier keys, so shift is noted on the way down.
  let rangeModifier = false;
  function noteRangeModifier(event: MouseEvent): void {
    rangeModifier = event.shiftKey;
  }

  function handleCheckboxChange(event: Event, index: number): void {
    const input = event.currentTarget as HTMLInputElement;
    applySelection(index, input.checked, rangeModifier);
    rangeModifier = false;
  }

  function setSelected(agent: Agent, selected: boolean): void {
    if (selected) {
      selectedAgentIds.add(agent.publicId);
    } else {
      selectedAgentIds.delete(agent.publicId);
    }
  }

  // Selects one row, or with shift held, the range since the last one.
  function applySelection(
    index: number,
    selected: boolean,
    extendRange: boolean,
  ): void {
    const agent = visibleAgents[index];
    if (!agent || !isUpgradable(agent)) return;

    if (extendRange && lastToggledIndex !== null) {
      const from = Math.min(lastToggledIndex, index);
      const to = Math.max(lastToggledIndex, index);
      for (let i = from; i <= to; i++) {
        const row = visibleAgents[i];
        // A range steps over anything the firmware cannot be installed on
        if (row && isUpgradable(row)) setSelected(row, selected);
      }
    } else {
      setSelected(agent, selected);
    }
    if (extendRange) {
      // Shift-clicking also extends the browser's text selection, which paints
      // the rows blue over the tick marks
      window.getSelection()?.removeAllRanges();
    }
    lastToggledIndex = index;
  }

  // With a selection, clears all of it. Otherwise ticks the shown rows.
  function toggleVisibleAgents(event: Event): void {
    if (selectedAgentIds.size > 0) {
      selectedAgentIds.clear();
    } else {
      for (const agent of upgradableVisibleAgents) {
        selectedAgentIds.add(agent.publicId);
      }
    }
    syncHeaderCheckbox(event.currentTarget as HTMLInputElement);
  }

  // Written straight to the DOM: Svelte skips writes it thinks are no-ops.
  function syncHeaderCheckbox(input: HTMLInputElement | null): void {
    if (!input) return;
    input.checked = allVisibleSelected;
    input.indeterminate = someVisibleSelected;
  }

  const firmwareButtonLabel = $derived.by(() => {
    switch (uiState) {
      case UiState.Loading:
        return isNarrow ? "Loading" : "Loading devices";
      case UiState.Ready:
        return isNarrow ? "Select firmware" : "Select target firmware";
      default:
        // Once an installation starts the dropdown shows the target version
        return selectedFirmware?.version ?? "";
    }
  });

  const installButtonLabel = $derived.by(() => {
    switch (uiState) {
      case UiState.Loading:
        return isNarrow ? "Loading" : "Loading devices";
      case UiState.Ready: {
        if (!selectedFirmware) return "Select a target firmware";
        if (upgradableAgents.length === 0) {
          return isNarrow
            ? "No devices eligible"
            : "No devices can be upgraded";
        }
        const selected = selectedAgents.length;
        if (selected === 0) return "No devices selected";
        if (isNarrow) return `Install (${selected})`;
        return allSelected
          ? `Install on all eligible devices (${selected})`
          : `Install on ${selected} of ${upgradableAgents.length} devices`;
      }
      case UiState.StartInstall:
      case UiState.InstallingFirmware:
        return isNarrow
          ? "Installing firmware"
          : `Installing on ${installTargets.length} device(s)`;
      case UiState.NoWebsocketStartingInstall:
        return "Installing firmware";
      case UiState.InstalledFirmware:
        if (agentsStatusFailed.length === 0) return "Installations finished";
        return isNarrow
          ? `Retry (${agentsStatusFailed.length})`
          : `Retry ${agentsStatusFailed.length} failed device(s)`;
      case UiState.NoWebsocketStartedInstall:
        return "Installations started";
      default:
        return "No firmware selected";
    }
  });

  const statusLabel = $derived.by(() => {
    switch (uiState) {
      case UiState.InstalledFirmware:
        return "Installations finished";
      case UiState.NoWebsocketStartedInstall:
        return "Installations started";
      default:
        return isNarrow ? "Installing" : "Installing firmware";
    }
  });

  const installButtonStyling = $derived(
    installButtonEnabled
      ? "startInstallationButtonStyleEnabled"
      : "startInstallationButtonStyleDisabled",
  );
  const statusTitleStyling = $derived(
    isNarrow
      ? "installationStatusTitleStyleIsNarrow"
      : "installationStatusTitleStyle",
  );
  const tableWrapperStyling = $derived(
    isNarrow ? "tableWrapperIsNarrow" : "tableWrapper",
  );
  const hrBottomStyling = $derived(isNarrow ? "hrBottomIsNarrow" : "hrBottom");
  const hrRightStyling = $derived(isNarrow ? "hrRightIsNarrow" : "hrRight");
  const spinnerRowStyling = $derived(isNarrow ? "nonSpinnerRow" : "spinnerRow");

  const showInstallingFirmwareStatus = $derived(activeWebsocket !== null);

  // The one-line totals above the table.
  const scopeSummary = $derived.by(() => {
    if (uiState === UiState.Loading) return "";
    const total = allAgents.length;
    if (total === 0) return "";
    if (!selectedFirmware) {
      return total === 1 ? "1 device" : `${total} devices`;
    }
    return `${upgradableAgents.length} of ${total} devices can be upgraded to ${selectedFirmware.version}`;
  });

  // Follows the selected status tab; before an install, the eligible rows
  const tableAgents = $derived.by(() => {
    switch (tableAgentsStatus) {
      case TableAgentsStatus.Started:
        return agentsStatusStarted;
      case TableAgentsStatus.Completed:
        return agentsStatusCompleted;
      case TableAgentsStatus.Failed:
        return agentsStatusFailed;
      default:
        return allAgents;
    }
  });

  const searchTerm = $derived(deviceSearch.trim().toLowerCase());

  // Only groups that hold devices are offered.
  const groupOptions = $derived.by((): GroupOption[] => {
    const ids = new Set<string>();
    for (const agent of allAgents) {
      for (const id of agentGroupIds(agent)) {
        ids.add(id);
        // A parent is offered too: picking it covers its whole branch
        for (const parent of parentsOf(id)) ids.add(parent);
      }
    }

    const options: GroupOption[] = [...ids].map((id) => {
      const type = groupTypeById.get(id);
      const path = pathOf(id);
      return {
        id,
        name: groupNamesById.get(id) || "Unnamed group",
        typeName: type?.name ?? "",
        typeOrder: type?.order ?? Number.MAX_SAFE_INTEGER,
        // The type is carried in the label, so it is searchable
        label: type?.name ? `${type.name} · ${path}` : path,
      };
    });

    options.sort(
      (a, b) =>
        a.typeOrder - b.typeOrder ||
        a.typeName.localeCompare(b.typeName) ||
        a.label.localeCompare(b.label),
    );

    return options;
  });

  // Picking a group also covers everything beneath it.
  const selectedGroupIdsWithChildren = $derived.by(() => {
    const expanded = new Set<string>(selectedGroupIds);
    const queue = [...selectedGroupIds];
    while (queue.length > 0) {
      const id = queue.pop() as string;
      for (const child of groupChildrenById.get(id) ?? []) {
        if (!expanded.has(child)) {
          expanded.add(child);
          queue.push(child);
        }
      }
    }
    return expanded;
  });

  const groupFilterActive = $derived(selectedGroupIds.size > 0);

  const groupButtonLabel = $derived.by(() => {
    if (selectedGroupIds.size === 0) return "All groups";
    if (selectedGroupIds.size > 1) return `${selectedGroupIds.size} groups`;
    const [onlyId] = selectedGroupIds;
    return (
      groupOptions.find((option) => option.id === onlyId)?.name ?? "1 group"
    );
  });

  function matchesGroupFilter(agent: Agent): boolean {
    if (selectedGroupIds.size === 0) return true;
    return agentGroupIds(agent).some((id) =>
      selectedGroupIdsWithChildren.has(id),
    );
  }

  // An inline dropdown: `openSelectPanel` only reports back on dismissal.
  const groupPickerOptions = $derived.by(() => {
    const term = groupSearch.trim().toLowerCase();
    if (!term) return groupOptions;
    return groupOptions.filter((option) =>
      option.label.toLowerCase().includes(term),
    );
  });

  function toggleGroup(id: string): void {
    if (selectedGroupIds.has(id)) {
      selectedGroupIds.delete(id);
    } else {
      selectedGroupIds.add(id);
    }
  }

  function clearGroupFilter(): void {
    selectedGroupIds.clear();
  }

  function toggleGroupPicker(): void {
    groupPickerOpen = !groupPickerOpen;
    if (groupPickerOpen) groupSearch = "";
  }

  // Click outside, focus leaving, or Escape closes the dropdown.
  $effect(() => {
    if (!groupPickerOpen) return;

    const closeIfOutside = (event: Event) => {
      if (!groupPickerEl) return;
      const path = event.composedPath();
      const inside = path.length
        ? path.includes(groupPickerEl)
        : groupPickerEl.contains(event.target as Node | null);
      if (!inside) groupPickerOpen = false;
    };
    const onPointerDown = (event: PointerEvent) => closeIfOutside(event);
    const onFocusIn = (event: FocusEvent) => closeIfOutside(event);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") groupPickerOpen = false;
    };

    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("focusin", onFocusIn, true);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("focusin", onFocusIn, true);
      document.removeEventListener("keydown", onKeyDown);
    };
  });

  function matchesSearch(agent: Agent, term: string): boolean {
    const haystack = [
      agent.name,
      agent.serialNumber,
      agent.lastSeenAgentUserAgent?.firmwareVersion,
    ];
    return haystack.some((value) => (value ?? "").toLowerCase().includes(term));
  }

  // How deep a group sits in the hierarchy; deeper means more specific.
  function depthOf(groupId: string): number {
    return parentsOf(groupId).length;
  }

  // Group names of a device, most specific first.
  function agentGroupNames(agent: Agent): string {
    return agentGroupIds(agent)
      .map((id) => ({ id, name: groupNamesById.get(id) || "" }))
      .filter((entry) => entry.name !== "")
      .sort(
        (a, b) => depthOf(b.id) - depthOf(a.id) || a.name.localeCompare(b.name),
      )
      .map((entry) => entry.name)
      .join(", ");
  }

  function compareBySortColumn(a: Agent, b: Agent): number {
    switch (sortColumn) {
      case "serial":
        return (a.serialNumber ?? "").localeCompare(
          b.serialNumber ?? "",
          undefined,
          {
            numeric: true,
          },
        );
      case "firmware":
        // Version order, not alphabetical: 3.9 must sort below 3.10
        return compareVersions(
          a.lastSeenAgentUserAgent?.firmwareVersion ?? "",
          b.lastSeenAgentUserAgent?.firmwareVersion ?? "",
        );
      case "type":
        return (a.type?.name ?? "").localeCompare(b.type?.name ?? "");
      case "groups":
        return agentGroupNames(a).localeCompare(agentGroupNames(b));
      case "status":
        return statusTextFor(a).localeCompare(statusTextFor(b));
      default:
        return byName(a, b);
    }
  }

  // The rows actually on screen: the active status tab, minus the filters.
  const visibleAgents = $derived.by(() => {
    const rows = tableAgents.filter(
      (agent) =>
        matchesGroupFilter(agent) &&
        (!searchTerm || matchesSearch(agent, searchTerm)),
    );
    const direction = sortAscending ? 1 : -1;
    // Name is the tie-breaker so equal values keep a stable, readable order
    return [...rows].sort(
      (a, b) => direction * (compareBySortColumn(a, b) || byName(a, b)),
    );
  });

  // Type and group are dropped on smaller cards, where there is no room.
  const showWideColumns = $derived(
    width !== null && width >= WIDE_COLUMNS_WIDTH_PX,
  );

  const tableColumns = $derived.by(() => {
    const columns = [{ key: "name", label: "Name", className: "columnName" }];
    if (showWideColumns) {
      columns.push({ key: "type", label: "Type", className: "columnType" });
      columns.push({
        key: "groups",
        label: "Groups",
        className: "columnGroups",
      });
    }
    columns.push({
      key: "serial",
      label: "Serial number",
      className: "columnSerialNumber",
    });
    columns.push({
      key: "firmware",
      label: "Firmware",
      className: "columnFirmware",
    });
    columns.push({
      key: "status",
      label: "Status",
      className: "columnStatus",
    });
    return columns;
  });

  function sortBy(column: string): void {
    if (sortColumn === column) {
      sortAscending = !sortAscending;
    } else {
      sortColumn = column;
      sortAscending = true;
    }
  }

  function ariaSort(column: string): "ascending" | "descending" | "none" {
    if (sortColumn !== column) return "none";
    return sortAscending ? "ascending" : "descending";
  }
  const filterActive = $derived(groupFilterActive || searchTerm !== "");
  const searchHasHits = $derived(visibleAgents.length > 0);

  // The rows on screen that the selected firmware can be installed on.
  const upgradableVisibleAgents = $derived(visibleAgents.filter(isUpgradable));

  const allVisibleSelected = $derived(
    selectedAgentIds.size > 0 &&
      upgradableVisibleAgents.length > 0 &&
      upgradableVisibleAgents.every((agent) =>
        selectedAgentIds.has(agent.publicId),
      ),
  );
  // Half-ticked whenever a selection exists that the box does not fully show.
  const someVisibleSelected = $derived(
    !allVisibleSelected && selectedAgentIds.size > 0,
  );

  const startedStatusStyling = $derived(
    tableAgentsStatus === TableAgentsStatus.Completed ||
      tableAgentsStatus === TableAgentsStatus.Failed
      ? "statusNotSelected"
      : "statusSelected",
  );
  const completedStatusStyling = $derived(
    tableAgentsStatus === TableAgentsStatus.Completed
      ? "statusSelected"
      : "statusNotSelected",
  );
  const failedStatusStyling = $derived(
    tableAgentsStatus === TableAgentsStatus.Failed
      ? "statusSelected"
      : "statusNotSelected",
  );

  // Blank API values read as "N/A" rather than as an empty cell.
  function orNotAvailable(value: string | null | undefined): string {
    return value && value.trim() !== "" ? value : "N/A";
  }

  // For example: "3.31 (latest) — available in 5 days"
  function firmwareOptionLabel(firmware: FirmwareOption): string {
    let label = firmware.version;
    if (firmware.latest) label += " (latest)";
    if (!firmware.allowed) {
      const days = firmware.daysRemaining;
      label +=
        days === null
          ? " — release date unknown"
          : ` — available in ${days} day${days === 1 ? "" : "s"}`;
    }
    return label;
  }

  function showAgents(status: number): void {
    tableAgentsStatus = status;
  }

  // Puts the whole fleet back on screen after a run. The chosen firmware is
  // kept, so a second batch can be started without picking it again.
  function backToDeviceList(): void {
    tableAgentsStatus = null;
    installTargets = [];
    agentsStatusStarted = [];
    agentsStatusCompleted = [];
    agentsStatusFailed = [];
    agentsStatusStartedBackup = [];
    failureReasons = new Map();
    selectedAgentIds.clear();
    activeWebsocket = null;
    activeWebsocketConn?.close();
    clearTimeout(timerWebsocketRenewal);
    clearTimeout(timerInstallTimeout);
    allRequestsSent = false;
    uiState = UiState.Ready;
  }

  // API layer
  function apiHeaders(): Record<string, string> {
    return {
      "Content-Type": "application/json",
      Authorization: `Bearer ${context.appData.accessToken.secretId}`,
      "Api-Application": context.appData.apiAppId,
      "Api-Company": context.appData.company.publicId,
      "Api-Version": context.appData.apiVersion,
    };
  }

  // Builds an API url. `filters` is repeated once per filter expression.
  function buildApiUrl(
    routeName: string,
    params: Record<string, string | null> = {},
    filters: string[] = [],
  ): string {
    const cleanParams: Record<string, string> = {};
    for (const [key, value] of Object.entries(params)) {
      if (value) {
        cleanParams[key] = value;
      }
    }
    let url = context.getApiUrl(routeName, cleanParams);
    if (filters.length > 0) {
      const separator = url.includes("?") ? "&" : "?";
      url +=
        separator +
        filters
          .map((filter) => `filters=${encodeURIComponent(filter)}`)
          .join("&");
    }
    return url;
  }

  async function apiGet<T>(
    routeName: string,
    params: Record<string, string | null> = {},
    filters: string[] = [],
  ): Promise<IxApiResponse<T>> {
    const response = await fetch(buildApiUrl(routeName, params, filters), {
      headers: apiHeaders(),
      method: "GET",
    });
    const body = await response.json();
    if (!response.ok) {
      throw new Error(`${routeName} failed (${response.status})`);
    }
    return body as IxApiResponse<T>;
  }

  async function apiPost(
    routeName: string,
    params: Record<string, string | null> = {},
    data: unknown = {},
  ): Promise<void> {
    const response = await fetch(buildApiUrl(routeName, params), {
      headers: apiHeaders(),
      method: "POST",
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      throw new Error(
        `${routeName} failed (${response.status}${await apiErrorDetail(response)})`,
      );
    }
  }

  // What the API said about a rejected request, for the CSV. The body carries
  // a message and often a list of field errors; both are worth keeping.
  async function apiErrorDetail(response: Response): Promise<string> {
    try {
      const body = await response.json();
      const parts: string[] = [];
      if (typeof body?.message === "string") parts.push(body.message);
      for (const issue of body?.errors ?? []) {
        const field = issue?.field ? `${issue.field}: ` : "";
        if (issue?.message) parts.push(`${field}${issue.message}`);
      }
      const detail = parts.join(" — ").replace(/\s+/g, " ").trim();
      return detail ? `: ${detail}` : "";
    } catch {
      return "";
    }
  }

  // Follows `moreAfter` until every page has been collected.
  async function apiGetAll<T>(
    routeName: string,
    params: Record<string, string | null> = {},
    filters: string[] = [],
  ): Promise<T[]> {
    let items: T[] = [];
    let pageAfter: string | null = null;
    for (;;) {
      const page: IxApiResponse<T[]> = await apiGet<T[]>(
        routeName,
        { ...params, "page-size": PAGE_SIZE, "page-after": pageAfter },
        filters,
      );
      items = items.concat(page.data ?? []);
      pageAfter = page.moreAfter ?? null;
      if (!pageAfter) {
        return items;
      }
    }
  }

  // Version comparison
  function parseVersion(version: string): {
    release: number[];
    suffix: string;
  } {
    const cleaned = version.trim().toLowerCase().replace(/^v/, "");
    const match = cleaned.match(/^(\d+(?:\.\d+)*)(.*)$/);
    if (!match) {
      return { release: [], suffix: cleaned };
    }
    return {
      release: match[1].split(".").map(Number),
      suffix: match[2].replace(/^[-_+.]/, ""),
    };
  }

  // Natural version ordering: returns <0, 0 or >0 (a vs b).
  function compareVersions(a: string, b: string): number {
    const versionA = parseVersion(a);
    const versionB = parseVersion(b);
    const length = Math.max(versionA.release.length, versionB.release.length);
    for (let i = 0; i < length; i++) {
      const numberA = versionA.release[i] ?? 0;
      const numberB = versionB.release[i] ?? 0;
      if (numberA !== numberB) {
        return numberA < numberB ? -1 : 1;
      }
    }
    // A plain release (1.2.3) outranks a pre-release (1.2.3-rc1)
    if (!versionA.suffix && versionB.suffix) return 1;
    if (versionA.suffix && !versionB.suffix) return -1;
    if (versionA.suffix !== versionB.suffix) {
      return versionA.suffix < versionB.suffix ? -1 : 1;
    }
    return 0;
  }

  // Release date extraction. The API's releaseDate is used when it has one;
  // older files only carry a date in the free-text notes, so those are
  // scanned as a fallback. No date at all means the version is not offered.

  const MONTH_NAMES: Record<string, number> = {
    jan: 1,
    january: 1,
    feb: 2,
    february: 2,
    mar: 3,
    march: 3,
    apr: 4,
    april: 4,
    may: 5,
    jun: 6,
    june: 6,
    jul: 7,
    july: 7,
    aug: 8,
    august: 8,
    sep: 9,
    sept: 9,
    september: 9,
    oct: 10,
    october: 10,
    nov: 11,
    november: 11,
    dec: 12,
    december: 12,
  };

  const ISO_DATE = /\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b/g;
  const DAY_MONTH_NAME_YEAR =
    /\b(\d{1,2})(?:st|nd|rd|th)?[\s-]+([A-Za-z]{3,9})\.?[\s,-]+(\d{4})\b/g;
  const MONTH_NAME_DAY_YEAR =
    /\b([A-Za-z]{3,9})\.?[\s-]+(\d{1,2})(?:st|nd|rd|th)?[\s,-]+(\d{4})\b/g;
  const DAY_MONTH_YEAR = /\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b/g;

  // Returns null for impossible dates such as 31 February.
  function makeDate(year: number, month: number, day: number): Date | null {
    if (month < 1 || month > 12) return null;
    if (day < 1 || day > 31) return null;
    if (year < 1970 || year > 2999) return null;
    const date = new Date(year, month - 1, day);
    const isRealDate =
      date.getFullYear() === year &&
      date.getMonth() === month - 1 &&
      date.getDate() === day;
    return isRealDate ? date : null;
  }

  // The API's own release date: "2026-09-17", possibly with a time after it.
  // Parsed by hand because `new Date("2026-09-17")` is UTC midnight, which
  // lands on the previous day west of Greenwich.
  function parseReleaseDate(value: string | null | undefined): Date | null {
    if (!value) return null;
    const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
    return match ? makeDate(+match[1], +match[2], +match[3]) : null;
  }

  function findReleaseDate(notes: string): Date | null {
    if (!notes) return null;
    const candidates: { index: number; date: Date }[] = [];

    const collect = (
      pattern: RegExp,
      toDate: (match: RegExpMatchArray) => Date | null,
    ) => {
      for (const match of notes.matchAll(pattern)) {
        const date = toDate(match);
        if (date && match.index !== undefined) {
          candidates.push({ index: match.index, date });
        }
      }
    };

    collect(ISO_DATE, (m) => makeDate(+m[1], +m[2], +m[3]));

    collect(DAY_MONTH_NAME_YEAR, (m) => {
      const month = MONTH_NAMES[m[2].toLowerCase()];
      return month ? makeDate(+m[3], month, +m[1]) : null;
    });

    collect(MONTH_NAME_DAY_YEAR, (m) => {
      const month = MONTH_NAMES[m[1].toLowerCase()];
      return month ? makeDate(+m[3], month, +m[2]) : null;
    });

    collect(DAY_MONTH_YEAR, (m) => {
      let day = +m[1];
      let month = +m[2];
      if (month > 12 && day <= 12) {
        [day, month] = [month, day];
      }
      return makeDate(+m[3], month, day);
    });

    if (candidates.length === 0) return null;
    candidates.sort((a, b) => a.index - b.index);
    return candidates[0].date;
  }

  function startOfToday(): Date {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
  }

  function daysBetween(from: Date, to: Date): number {
    return Math.floor((to.getTime() - from.getTime()) / 86_400_000);
  }

  // The distinct agent types present in a set of devices.
  function collectAgentTypes(agents: Agent[]): AgentTypeRef[] {
    const agentTypes: AgentTypeRef[] = [];
    const seen = new Set<string>();
    for (const agent of agents) {
      const type = agent.type;
      if (!type || seen.has(type.publicId)) continue;
      seen.add(type.publicId);
      agentTypes.push({ publicId: type.publicId, name: type.name ?? "" });
    }
    return agentTypes;
  }

  // Folds the agent types that share a firmware track into one group each.
  function groupAgentTypes(agentTypes: AgentTypeRef[]): AgentTypeGroup[] {
    const groups: AgentTypeGroup[] = [];
    const byKey = new Map<string, AgentTypeGroup>();

    for (const agentType of agentTypes) {
      const family = AGENT_TYPE_FAMILIES.find((candidate) =>
        candidate.typeNames.includes(agentType.name),
      );
      const key = family ? `family:${family.label}` : agentType.publicId;

      let group = byKey.get(key);
      if (!group) {
        group = {
          key,
          label: family ? family.label : agentType.name,
          agentTypePublicIds: [],
        };
        byKey.set(key, group);
        groups.push(group);
      }
      group.agentTypePublicIds.push(agentType.publicId);
    }
    return groups;
  }

  // Every version on offer, newest first, one entry per version per group.
  async function fetchFirmwareCandidates(
    groups: AgentTypeGroup[],
  ): Promise<FirmwareCandidate[]> {
    const candidates: FirmwareCandidate[] = [];
    const byGroupAndVersion = new Map<string, FirmwareCandidate>();

    for (const group of groups) {
      for (const agentTypePublicId of group.agentTypePublicIds) {
        const page = await apiGet<AgentTypeFile[]>("AgentTypeFileList", {
          publicId: agentTypePublicId,
          "page-size": PAGE_SIZE,
          fields: "publicId,name,code,latest,releaseDate,notes",
        });
        for (const file of page.data ?? []) {
          const version = file.code ?? "";
          const key = `${group.key}|${version}`;

          let candidate = byGroupAndVersion.get(key);
          if (!candidate) {
            candidate = {
              groupKey: group.key,
              version,
              fileIdByAgentType: {},
              latest: false,
              releaseDate: null,
              notes: "",
            };
            byGroupAndVersion.set(key, candidate);
            candidates.push(candidate);
          }
          candidate.fileIdByAgentType[agentTypePublicId] = file.publicId;
          candidate.latest ||= file.latest ?? false;
          // Cast: releaseDate is served but may not be in the CDK's typings yet
          candidate.releaseDate ??=
            (file as { releaseDate?: string | null }).releaseDate ?? null;
          if (!candidate.notes) candidate.notes = file.notes ?? "";
        }
      }
    }

    candidates.sort((a, b) => compareVersions(b.version, a.version));
    return candidates;
  }

  // Drops versions newer than `latest`, then applies the release cooldown.
  function applyCooldown(candidates: FirmwareCandidate[]): FirmwareOption[] {
    const latestSeen = new Set<string>();
    const cooldownCleared = new Set<string>();
    const options: FirmwareOption[] = [];
    const today = startOfToday();

    for (const candidate of candidates) {
      const isFirstOfGroup = !latestSeen.has(candidate.groupKey);
      if (candidate.latest) {
        latestSeen.add(candidate.groupKey);
      } else if (isFirstOfGroup) {
        continue; // Newer than the version marked as latest
      }

      let allowed = true;
      let daysRemaining: number | null = null;

      if (!cooldownCleared.has(candidate.groupKey)) {
        const releaseDate =
          parseReleaseDate(candidate.releaseDate) ??
          findReleaseDate(candidate.notes);
        if (releaseDate === null) {
          // No date from either source: the cooldown cannot be shown to have
          // passed, so the version is not offered
          allowed = false;
        } else {
          const days = daysBetween(releaseDate, today);
          if (days < FIRMWARE_COOLDOWN_DAYS) {
            allowed = false;
            daysRemaining = FIRMWARE_COOLDOWN_DAYS - days;
          } else {
            cooldownCleared.add(candidate.groupKey);
          }
        }
      }

      options.push({
        id: `${candidate.groupKey}|${candidate.version}`,
        groupKey: candidate.groupKey,
        version: candidate.version,
        fileIdByAgentType: candidate.fileIdByAgentType,
        // The list runs newest first, so the first one kept per group is it
        latest: isFirstOfGroup,
        allowed,
        daysRemaining,
      });
    }
    return options;
  }

  // Orders the groups the way their firmware appears in the dropdown.
  function sortGroups(
    groups: AgentTypeGroup[],
    firmware: FirmwareOption[],
  ): AgentTypeGroup[] {
    const sorted: AgentTypeGroup[] = [];
    const seen = new Set<string>();
    for (const option of firmware) {
      if (seen.has(option.groupKey)) continue;
      const group = groups.find(
        (candidate) => candidate.key === option.groupKey,
      );
      if (group) {
        seen.add(option.groupKey);
        sorted.push(group);
      }
    }
    return sorted;
  }

  // Finding the eligible devices

  interface ManageAgentsPermissions {
    any: boolean; // True when at least one role grants "manage agents".
    companyWide: boolean; // True when that role also applies company-wide.
    roleIds: Set<string>; // Public ids of the roles that grant "manage agents".
  }

  async function fetchManageAgentsPermissions(): Promise<ManageAgentsPermissions> {
    const roles = await apiGetAll<Role>("RoleList", {
      fields: "name,publicId,permissions",
    });

    const permissions: ManageAgentsPermissions = {
      any: false,
      companyWide: false,
      roleIds: new Set(),
    };

    for (const role of roles) {
      if (!role.permissions) continue;
      const ids = role.permissions.map((permission) => permission.publicId);
      const isCompanyAdmin = ids.includes("COMPANY_ADMIN");
      const canManageAgents = isCompanyAdmin || ids.includes("MANAGE_AGENT");
      if (!canManageAgents) continue;

      permissions.any = true;
      permissions.roleIds.add(role.publicId);
      if (isCompanyAdmin || ids.includes("COMPANY_WIDE_ROLE")) {
        permissions.companyWide = true;
        break;
      }
    }
    return permissions;
  }

  // Every device in the company, with the fields eligibility needs.
  async function fetchAllAgents(): Promise<Agent[]> {
    return apiGetAll<Agent>("AgentList", {
      fields:
        "publicId,name,serialNumber,type.name,type.publicId,lastSeenAgentUserAgent.firmwareVersion,mdrServer,firmwareUpdateLocked,memberships.group.publicId",
    });
  }

  // Loads the company's groups and splits off the per-device ones.
  function loadGroups(): Promise<void> {
    groupsLoaded ??= (async () => {
      const groups = await apiGetAll<Group>("GroupList", {
        fields:
          "name,publicId,isCompanyGroup,agent.publicId,parent.publicId,type.name,type.order",
      });
      const names = new Map<string, string>();
      const parents = new Map<string, string>();
      const children = new Map<string, string[]>();
      const types = new Map<string, { name: string; order: number }>();
      const companyWide = new Set<string>();
      const perDevice = new Map<string, string>();

      for (const group of groups) {
        if (group.agent) {
          perDevice.set(group.publicId, group.agent.publicId);
          continue;
        }
        names.set(group.publicId, group.name ?? "");
        if (group.isCompanyGroup) companyWide.add(group.publicId);

        const parentId = group.parent?.publicId;
        if (parentId) {
          parents.set(group.publicId, parentId);
          children.set(parentId, [
            ...(children.get(parentId) ?? []),
            group.publicId,
          ]);
        }
        if (group.type?.name) {
          types.set(group.publicId, {
            name: group.type.name,
            order: group.type.order ?? Number.MAX_SAFE_INTEGER,
          });
        }
      }

      groupNamesById = names;
      groupParentById = parents;
      groupChildrenById = children;
      groupTypeById = types;
      companyGroupIds = companyWide;
      deviceSpecificGroups = perDevice;
    })();
    return groupsLoaded;
  }

  // Public ids from a (sub)group up to its root, the group itself excluded.
  function parentsOf(groupId: string): string[] {
    const ancestors: string[] = [];
    const seen = new Set<string>([groupId]);
    let current = groupParentById.get(groupId);
    while (current && !seen.has(current)) {
      seen.add(current);
      ancestors.push(current);
      current = groupParentById.get(current);
    }
    return ancestors;
  }

  // The group with its parents, for the picker.
  function pathOf(groupId: string): string {
    const parts = [...parentsOf(groupId)].reverse();
    parts.push(groupId);
    return parts
      .map((id) => groupNamesById.get(id) || "Unnamed group")
      .join(" / ");
  }

  // The groups a device belongs to. Its own per-device group is skipped, and
  // so is the company group: it holds every device, so users do not read it
  // as a group. Nothing offers it as a filter, "Clear filter" covers it.
  function agentGroupIds(agent: Agent): string[] {
    const ids: string[] = [];
    for (const membership of agent.memberships ?? []) {
      const id = membership.group?.publicId;
      if (!id || deviceSpecificGroups.has(id)) continue;
      if (companyGroupIds.has(id)) continue;
      ids.push(id);
    }
    return ids;
  }

  // Narrows the devices down to the ones this user is allowed to manage.
  async function filterByMembership(
    agents: Agent[],
    roleIds: Set<string>,
  ): Promise<Agent[]> {
    await loadGroups();

    const me = await apiGet<MyUser>("MyUser", { fields: "name,publicId" });
    const user = await apiGet<User>("User", {
      publicId: me.data.publicId,
      fields: "name,memberships.group.publicId,memberships.role.publicId",
    });

    const allowed: Agent[] = [];
    const added = new Set<string>();
    const add = (agent: Agent | undefined) => {
      if (!agent || added.has(agent.publicId)) return;
      added.add(agent.publicId);
      allowed.push(agent);
    };

    for (const membership of user.data.memberships ?? []) {
      const groupId = membership.group?.publicId;
      if (!groupId || !membership.role) continue;
      if (!roleIds.has(membership.role.publicId)) continue;

      const deviceId = deviceSpecificGroups.get(groupId);
      if (deviceId !== undefined) {
        add(agents.find((agent) => agent.publicId === deviceId));
      } else {
        for (const agent of agents) {
          const inGroup = (agent.memberships ?? []).some(
            (agentMembership) => agentMembership.group?.publicId === groupId,
          );
          if (inGroup) add(agent);
        }
      }
    }
    return allowed;
  }

  function byName(a: Agent, b: Agent): number {
    return (a.name ?? "").localeCompare(b.name ?? "");
  }

  // The whole fleet, narrowed to what this user is allowed to manage.
  // Null when no role grants it, which is not an empty fleet.
  async function fetchManageableAgents(): Promise<Agent[] | null> {
    const permissions = await fetchManageAgentsPermissions();
    if (!permissions.any) {
      return null;
    }

    const agents = await fetchAllAgents();
    if (permissions.companyWide) {
      // Not needed for permissions here, but the group picker still wants them
      await loadGroups();
      return agents.sort(byName);
    }
    const allowed = await filterByMembership(agents, permissions.roleIds);
    return allowed.sort(byName);
  }

  /// One request per device: a rejected one must not stop the rest.
  async function requestFirmwareUpgrade(
    firmware: FirmwareOption,
    agents: Agent[],
  ): Promise<{ started: Agent[]; rejected: Agent[] }> {
    const started: Agent[] = [];
    const rejected: Agent[] = [];

    for (const agent of agents) {
      const agentTypePublicId = agent.type?.publicId ?? "";
      const fileId = firmware.fileIdByAgentType[agentTypePublicId];
      if (!fileId) {
        // Should not happen: the list only holds types that publish this version
        console.error("No firmware file for agent type", agentTypePublicId);
        noteFailure(
          agent,
          `No firmware ${firmware.version} is published for ${agent.type?.name ?? "this device type"}`,
        );
        rejected.push(agent);
        continue;
      }
      try {
        await apiPost(
          "AgentFirmwareUpgrade",
          { agentId: agent.publicId },
          { file: { publicId: fileId } },
        );
        started.push(agent);
      } catch (error) {
        console.error("Error:", error);
        noteFailure(
          agent,
          `The upgrade request was refused. ${error instanceof Error ? error.message : String(error)}`,
        );
        rejected.push(agent);
      }
    }
    return { started, rejected };
  }

  // Lifecycle

  onMount(() => {
    if (!rootEl) return;
    width = rootEl.getBoundingClientRect().width;
    const resizeObserver = new ResizeObserver((entries) => {
      entries.forEach((entry) => {
        width = entry.contentRect.width;
      });
    });
    resizeObserver.observe(rootEl);

    loadFleet();

    return () => {
      resizeObserver.disconnect();
      activeWebsocketConn?.close();
      clearTimeout(timerWebsocketRenewal);
      clearTimeout(timerInstallTimeout);
    };
  });

  function informError(message: string): void {
    context.openAlertDialog({
      title: "Something went wrong",
      message,
      buttonText: "I understand",
    });
  }

  /// Loads the fleet and the firmware versions once, on mount.
  async function loadFleet(): Promise<void> {
    uiState = UiState.Loading;
    try {
      const agents = await fetchManageableAgents();
      if (agents === null) {
        uiState = UiState.NoPermission;
        return;
      }
      allAgents = agents;

      const groups = groupAgentTypes(collectAgentTypes(agents));
      const candidates = await fetchFirmwareCandidates(groups);
      firmwareList = applyCooldown(candidates);
      agentTypeGroups = sortGroups(groups, firmwareList);
    } catch (error) {
      console.error("Error:", error);
      informError(
        "The devices and firmware versions could not be retrieved. Please reload the page and try again.",
      );
      allAgents = [];
      agentTypeGroups = [];
      firmwareList = [];
    }
    uiState = UiState.Ready;
  }

  // Drops ticks the new firmware cannot be installed on, and says so.
  function pruneSelectionForFirmware(): void {
    let dropped = 0;
    for (const id of [...selectedAgentIds]) {
      const agent = allAgents.find((candidate) => candidate.publicId === id);
      if (!agent || !isUpgradable(agent)) {
        selectedAgentIds.delete(id);
        dropped += 1;
      }
    }
    if (dropped === 0) return;
    const count = dropped === 1 ? "1 device" : `${dropped} devices`;
    context.openToast(
      `${count} deselected: not eligible for ${selectedFirmware?.version ?? "this version"}.`,
    );
  }

  function informFirmwareNotAvailable(firmware: FirmwareOption): void {
    selectedFirmware = null;
    const rule =
      "Firmware versions become available for Bulk Firmware Upgrade 2 weeks " +
      "after they are released. ";
    context.openAlertDialog({
      title: "Available soon",
      message:
        firmware.daysRemaining === null
          ? rule +
            `The release date of firmware ${firmware.version} could not be ` +
            "determined, so it cannot be installed from here."
          : rule +
            `Firmware ${firmware.version} becomes available in ` +
            `${firmware.daysRemaining} day(s).`,
      buttonText: "I understand",
    });
  }

  // How many device names the confirmation lists before summarising.
  const CONFIRM_LIST_LIMIT = 12;

  async function confirmInstallation(
    firmware: FirmwareOption,
    targets: Agent[],
  ): Promise<boolean> {
    const devices =
      targets.length === 1 ? "1 device" : `${targets.length} devices`;

    // Ticked devices survive filter changes, so some may not be on screen
    const listed = targets
      .slice(0, CONFIRM_LIST_LIMIT)
      .map((agent) => `• ${agent.name ?? agent.publicId}`);
    const remaining = targets.length - listed.length;
    if (remaining > 0) {
      listed.push(`• and ${remaining} more`);
    }

    const confirmed = await context.openConfirmDialog({
      title: `Install firmware ${firmware.version}?`,
      message:
        `Firmware ${firmware.version} will be installed on ${devices}. ` +
        "These devices will be restarted:\n\n" +
        listed.join("\n") +
        "\n\n" +
        TEXT_TIME_INDICATION.trimEnd(),
      confirmButtonText: "Install",
      cancelButtonText: "Cancel",
      destructive: true,
    });
    return confirmed === true;
  }

  async function startFirmwareInstallation(): Promise<void> {
    const firmware = selectedFirmware;
    if (!firmware) return;
    if (canRetry) {
      await runInstallation(firmware, [...agentsStatusFailed]);
    } else {
      await runInstallation(firmware, selectedAgents);
    }
  }

  async function runInstallation(
    firmware: FirmwareOption,
    targets: Agent[],
  ): Promise<void> {
    if (targets.length === 0) return;
    if (!(await confirmInstallation(firmware, targets))) return;

    // A retry starts from a clean slate rather than adding to the last run
    agentsStatusCompleted = [];
    agentsStatusFailed = [];
    failureReasons = new Map();
    websocketWarningShown = false;
    activeWebsocketConn?.close();
    activeWebsocket = null;

    installTargets = targets;
    uiState = UiState.StartInstall;
    establishWebsocketConn();
    showAgents(TableAgentsStatus.Started);
    agentsStatusStarted = [];
    allRequestsSent = false;

    for (let i = 0; i < targets.length; i += INSTALL_BATCH_SIZE) {
      const batch = targets.slice(i, i + INSTALL_BATCH_SIZE);
      const { started, rejected } = await requestFirmwareUpgrade(
        firmware,
        batch,
      );
      agentsStatusStarted = agentsStatusStarted.concat(started);
      if (rejected.length > 0) {
        agentsStatusFailed = agentsStatusFailed.concat(rejected);
      }
    }
    agentsStatusStartedBackup = agentsStatusStarted;
    allRequestsSent = true;

    // Nothing left to wait for when every request was refused
    finishInstallationIfDone();
    timerInstallTimeout = setTimeout(abandonStragglers, INSTALL_TIMEOUT_MS);
  }

  // Gives up on devices that never reported back and closes the run.
  function abandonStragglers(): void {
    // Without a WebSocket nothing can be observed, so nothing can be concluded
    if (activeWebsocket !== true) return;
    if (agentsStatusStarted.length === 0) return;
    for (const agent of agentsStatusStarted) {
      noteFailure(
        agent,
        "The device did not come back online within 30 minutes of the request",
      );
    }
    agentsStatusFailed = agentsStatusFailed.concat(agentsStatusStarted);
    agentsStatusStarted = [];
    finishInstallationIfDone();
  }

  function finishInstallationIfDone(): void {
    // A fast device must not end the run while later batches are still queued
    if (!allRequestsSent) return;
    if (agentsStatusStarted.length !== 0) return;
    clearTimeout(timerInstallTimeout);
    const alreadyFinished = uiState === UiState.InstalledFirmware;
    uiState = UiState.InstalledFirmware;
    // A failure is worth interrupting for; a clean run speaks for itself
    if (!alreadyFinished && agentsStatusFailed.length > 0) {
      context.openAlertDialog({
        title: "Installations finished",
        message: TEXT_FAILED_DEVICES + TEXT_SUPPORT_WEBSITE,
        buttonText: "I understand",
      });
    }
    showAgents(
      agentsStatusCompleted.length !== 0
        ? TableAgentsStatus.Completed
        : TableAgentsStatus.Failed,
    );
    clearTimeout(timerWebsocketRenewal);
    activeWebsocketConn?.close();
  }

  async function fetchWebsocketAuthToken(): Promise<string | null> {
    try {
      const response = await fetch(
        context.getApiUrl("AuthTokenChangeNotificationsList"),
        {
          headers: apiHeaders(),
          body: JSON.stringify({ expiresIn: 3600 }),
          method: "POST",
        },
      );
      const body = await response.json();
      return body?.data?.secretId ?? null;
    } catch (error) {
      console.error("Error:", error);
      return null;
    }
  }

  // Re-reads a device that came back online and moves it out of "Started".
  async function settleAgent(agentPublicId: string): Promise<void> {
    const started = agentsStatusStarted.find(
      (agent) => agent.publicId === agentPublicId,
    );
    if (!started) return;

    let current: Agent | undefined;
    try {
      const response = await apiGet<Agent>("Agent", {
        publicId: agentPublicId,
        fields: "name,publicId,lastSeenAgentUserAgent.firmwareVersion",
      });
      current = response.data;
    } catch (error) {
      console.error("Error:", error);
      return;
    }

    const newVersion = current?.lastSeenAgentUserAgent?.firmwareVersion;
    const oldVersion = started.lastSeenAgentUserAgent?.firmwareVersion;
    // Back online without a version proves nothing, so it stays unconfirmed
    const succeeded = !!newVersion && newVersion !== oldVersion;

    const alreadyRecorded = (list: Agent[]) =>
      list.some((agent) => agent.publicId === agentPublicId);

    if (succeeded && !alreadyRecorded(agentsStatusCompleted)) {
      if (started.lastSeenAgentUserAgent) {
        started.lastSeenAgentUserAgent.firmwareVersion = newVersion;
      }
      agentsStatusCompleted = agentsStatusCompleted.concat(started);
    } else if (!succeeded && !alreadyRecorded(agentsStatusFailed)) {
      noteFailure(
        started,
        newVersion
          ? `The device came back online still running firmware ${newVersion}`
          : "The device came back online but reported no firmware version",
      );
      agentsStatusFailed = agentsStatusFailed.concat(started);
    }

    agentsStatusStarted = agentsStatusStarted.filter(
      (agent) => agent !== started,
    );
    finishInstallationIfDone();
  }

  async function establishWebsocketConn(): Promise<void> {
    const authToken = await fetchWebsocketAuthToken();

    activeWebsocketConn?.close();
    const conn = new WebSocket(
      context.getApiUrl("ChangeNotificationWebSocket"),
      "change-notifications",
    );
    activeWebsocketConn = conn;

    conn.onerror = () => {
      activeWebsocket = false;
      // The socket may fail after the run already settled; leave it settled
      if (!INSTALLING_STATES.includes(uiState)) return;
      uiState = UiState.NoWebsocketStartingInstall;
      agentsStatusStarted = agentsStatusStartedBackup;
      // Progress cannot be reported from here on, so say so once
      if (!websocketWarningShown) {
        websocketWarningShown = true;
        context.openAlertDialog({
          title: "Installation progress cannot be shown",
          message: TEXT_WEBSOCKET_ERROR + TEXT_SUPPORT_WEBSITE,
          buttonText: "I understand",
        });
      }
    };

    conn.onopen = () => {
      activeWebsocket = true;
      if (!INSTALLING_STATES.includes(uiState)) {
        // The run settled before the socket came up, e.g. every request was refused
        conn.close();
        return;
      }
      uiState = UiState.InstallingFirmware;
      conn.send(JSON.stringify({ aut: authToken }));
      conn.send(
        JSON.stringify({
          sub: [`Company/${context.appData.company.publicId}`],
        }),
      );
      timerWebsocketRenewal = setTimeout(
        establishWebsocketConn,
        WEBSOCKET_RENEWAL_MS,
      );
    };

    conn.onmessage = (event: MessageEvent) => {
      const notification: ChangeNotification = JSON.parse(event.data);
      // "MXT" is not exclusive, but does filter out unrelated messages
      if (notification.act !== "MXT") return;
      // All entries in .dat share the type reported in .sel[0]
      if (notification.sel?.[0]?.typ !== "Agent") return;

      for (const agent of notification.dat ?? []) {
        // An mdrServer means the device is back online
        if (agent.mdrServer?.publicId) {
          settleAgent(agent.publicId);
        }
      }
    };
  }

  // True once a run has settled, whether it succeeded or not.
  const runFinished = $derived(
    uiState === UiState.InstalledFirmware ||
      uiState === UiState.NoWebsocketStartedInstall,
  );

  function noteFailure(agent: Agent, reason: string): void {
    failureReasons.set(agent.publicId, reason);
  }

  function csvCell(value: string): string {
    return `"${value.replace(/"/g, '""')}"`;
  }

  // Saves the result of the run as a CSV.
  function exportResult(): void {
    const rows: string[][] = [
      [
        "Name",
        "Serial number",
        "Type",
        "Groups",
        "Firmware",
        "Status",
        "Error message",
      ],
    ];
    const append = (agents: Agent[], status: string) => {
      for (const agent of agents) {
        rows.push([
          agent.name ?? "",
          agent.serialNumber ?? "",
          agent.type?.name ?? "",
          agentGroupNames(agent) || "-",
          agent.lastSeenAgentUserAgent?.firmwareVersion ?? "",
          status,
          failureReasons.get(agent.publicId) ?? "",
        ]);
      }
    };
    append(agentsStatusCompleted, "Completed");
    append(agentsStatusFailed, "Failed");
    append(agentsStatusStarted, "Started, no result reported");

    const csv = rows.map((row) => row.map(csvCell).join(",")).join("\r\n");
    const stamp = new Date().toISOString().slice(0, 10);
    context.saveAsFile(
      csv,
      `firmware-upgrade-${selectedFirmware?.version ?? ""}-${stamp}.csv`,
    );
  }

  // Changing the version only changes eligibility, so drop ticks that no
  // longer apply. `untrack` keeps this depending on the selection alone.
  $effect(() => {
    const firmware = selectedFirmware;
    untrack(() => {
      if (!firmware) return;
      if (!firmware.allowed) {
        informFirmwareNotAvailable(firmware);
        return;
      }
      pruneSelectionForFirmware();
    });
  });

  // Nothing can be observed without a WebSocket, so the run ends here
  $effect(() => {
    if (activeWebsocket !== false) return;
    if (!allRequestsSent) return;
    uiState = UiState.NoWebsocketStartedInstall;
  });
</script>

<div class="component" bind:this={rootEl}>
  <div class="componentPadding">
    <div class="componentHeader">
      <h3 class="componentTitle">Bulk Firmware Upgrade</h3>
    </div>
    {#if uiState === UiState.NoPermission}
      <p class="permissionNotice">{TEXT_NO_PERMISSION}</p>
    {:else}
      <div class="componentLine">
        {#if firmwareSelectDisabled}
          <button
            disabled
            class={installButtonStyling}
            class:narrowWidth={isNarrow}
            type="button"
          >
            <div class="spinnerRow">
              {#if loading}
                <div class="spinnerSpacingRight">
                  <div class="spinner">
                    <svg
                      preserveAspectRatio="xMidYMid meet"
                      focusable="false"
                      viewBox="0 0 100 100"
                    >
                      <circle cx="50%" cy="50%" r="45" />
                    </svg>
                  </div>
                </div>
              {/if}
              {firmwareButtonLabel}
            </div>
          </button>
        {:else}
          <div class="select" class:narrowWidth={isNarrow}>
            <select bind:value={selectedFirmware}>
              <option value={null} hidden>{firmwareButtonLabel}</option>
              {#each agentTypeGroups as group (group.key)}
                <optgroup label={group.label}>
                  {#each firmwareList as firmware (firmware.id)}
                    {#if firmware.groupKey === group.key}
                      <!-- Cooldown versions show the wait, rather than being rejected later -->
                      <option value={firmware} disabled={!firmware.allowed}>
                        {firmwareOptionLabel(firmware)}
                      </option>
                    {/if}
                  {/each}
                </optgroup>
              {/each}
            </select>
          </div>
        {/if}
        <div class="buttonPadding"></div>
        <button
          disabled={!installButtonEnabled}
          class={installButtonStyling}
          class:narrowWidth={isNarrow}
          onclick={startFirmwareInstallation}
          type="button"
        >
          <div class="spinnerRow">
            {installButtonLabel}
          </div>
        </button>
      </div>
      <div class="hrTop"></div>
      <div class="searchRow">
        {#if runFinished}
          <button class="backButton" type="button" onclick={backToDeviceList}>
            <svg class="backIcon" viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"
              />
            </svg>
            <span class="backLabel">{TEXT_BACK_TO_LIST}</span>
          </button>
        {/if}
        <div class="groupPicker" bind:this={groupPickerEl}>
          <button
            class="groupButton"
            class:groupButtonActive={groupFilterActive}
            type="button"
            disabled={groupOptions.length === 0}
            aria-expanded={groupPickerOpen}
            onclick={toggleGroupPicker}
          >
            <span class="groupButtonLabel">{groupButtonLabel}</span>
            <svg
              class="groupButtonArrow"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path d="M7 10l5 5 5-5z" />
            </svg>
          </button>
          {#if groupPickerOpen}
            <div class="groupPanel">
              <input
                class="groupPanelSearch"
                type="text"
                bind:value={groupSearch}
                placeholder="Search groups"
                aria-label="Search groups"
              />
              <div class="groupPanelList">
                {#each groupPickerOptions as option (option.id)}
                  <label class="groupOption">
                    <input
                      type="checkbox"
                      checked={selectedGroupIds.has(option.id)}
                      onchange={() => toggleGroup(option.id)}
                    />
                    <span class="groupOptionLabel">{option.label}</span>
                  </label>
                {/each}
                {#if groupPickerOptions.length === 0}
                  <p class="groupPanelEmpty">No groups match</p>
                {/if}
              </div>
              {#if groupFilterActive}
                <button
                  class="groupPanelClear"
                  type="button"
                  onclick={clearGroupFilter}
                >
                  Clear filter
                </button>
              {/if}
            </div>
          {/if}
        </div>
        <div class="searchField">
          <svg class="searchIcon" viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M15.5 14h-.79l-.28-.27a6.5 6.5 0 1 0-.7.7l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0A4.5 4.5 0 1 1 14 9.5 4.5 4.5 0 0 1 9.5 14z"
            />
          </svg>
          <input
            type="text"
            bind:value={deviceSearch}
            disabled={tableAgents.length === 0}
            placeholder="Search by name, serial number or firmware"
            aria-label="Search devices"
          />
          {#if deviceSearch}
            <button
              class="searchClear"
              type="button"
              onclick={() => (deviceSearch = "")}
              aria-label="Clear search"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41z"
                />
              </svg>
            </button>
          {/if}
        </div>
        {#if filterActive}
          <span class="searchCount">
            {visibleAgents.length} of {tableAgents.length}
          </span>
        {/if}
      </div>
      <div class={tableWrapperStyling}>
        <table>
          <thead>
            <tr>
              {#if selectable}
                <th class="columnCheck">
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    indeterminate={someVisibleSelected}
                    onchange={toggleVisibleAgents}
                    aria-label={selectedAgentIds.size > 0
                      ? `Deselect all ${selectedAgentIds.size} selected devices`
                      : "Select all shown devices"}
                    data-tooltip={selectedAgentIds.size > 0
                      ? `Deselect all ${selectedAgentIds.size} selected devices`
                      : "Select all shown devices"}
                    use:cellTooltip
                  />
                </th>
              {/if}
              {#each tableColumns as column (column.key)}
                <th
                  class={column.className}
                  aria-sort={ariaSort(column.key)}
                  onclick={() => sortBy(column.key)}
                >
                  <span class="sortHeader">
                    {column.label}
                    <span
                      class="sortArrow"
                      class:sortArrowActive={sortColumn === column.key}
                    >
                      {sortColumn === column.key && !sortAscending ? "▲" : "▼"}
                    </span>
                  </span>
                </th>
              {/each}
            </tr>
          </thead>
          <tbody>
            <!-- The checkbox is the keyboard path, the row click a pointer shortcut -->
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
            {#each visibleAgents as agent, index (agent.publicId)}
              <tr
                class:rowSelectable={selectable && isUpgradable(agent)}
                class:rowBlocked={isBlocked(agent)}
                onclick={(event) => handleRowClick(event, index)}
              >
                {#if selectable}
                  <td class="columnCheck">
                    {#if agent.firmwareUpdateLocked}
                      <span
                        class="lockBadge"
                        data-tooltip={TEXT_UPDATES_LOCKED}
                        aria-label={TEXT_UPDATES_LOCKED}
                        use:cellTooltip
                      >
                        <svg viewBox="0 0 16 16" aria-hidden="true">
                          <path
                            d="M4.5 7V5a3.5 3.5 0 0 1 7 0v2h.5a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h.5Zm1.5 0h4V5a2 2 0 1 0-4 0v2Z"
                          />
                        </svg>
                      </span>
                    {:else}
                      <input
                        type="checkbox"
                        checked={selectedAgentIds.has(agent.publicId)}
                        disabled={!isUpgradable(agent)}
                        onpointerdown={noteRangeModifier}
                        onchange={(event) => handleCheckboxChange(event, index)}
                        aria-label="Select {agent.name}"
                      />
                    {/if}
                  </td>
                {/if}
                <td class="columnName" use:cellTooltip>{agent.name}</td>
                {#if showWideColumns}
                  <td class="columnType" use:cellTooltip>
                    {agent.type?.name ?? ""}
                  </td>
                  <td class="columnGroups" use:cellTooltip>
                    {agentGroupNames(agent) || "-"}
                  </td>
                {/if}
                <td class="columnSerialNumber">
                  {orNotAvailable(agent.serialNumber)}
                </td>
                <td class="columnFirmware">
                  {orNotAvailable(
                    agent.lastSeenAgentUserAgent?.firmwareVersion,
                  )}
                </td>
                <td class="columnStatus" use:cellTooltip>
                  {statusTextFor(agent)}
                </td>
              </tr>
            {/each}
            {#if filterActive && !searchHasHits}
              <tr>
                <td class="tableEmpty" colspan={tableColumns.length + 1}>
                  {#if searchTerm && !groupFilterActive}
                    No devices match “{deviceSearch.trim()}”
                  {:else}
                    No devices match the current filter
                  {/if}
                </td>
              </tr>
            {/if}
          </tbody>
        </table>
      </div>
      <div class={hrBottomStyling}></div>
      <div class="statusWrapper">
        {#if showInstallingFirmwareStatus}
          <span class={spinnerRowStyling}>
            {#if runFinished}
              <button
                class="exportButton"
                type="button"
                onclick={exportResult}
                aria-label={TEXT_EXPORT_RESULTS}
                data-tooltip={TEXT_EXPORT_RESULTS}
                use:cellTooltip
              >
                <svg class="exportIcon" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z" />
                </svg>
                {#if !isNarrow}
                  <span class="exportLabel">{TEXT_EXPORT_RESULTS}</span>
                {/if}
              </button>
            {:else}
              <span class={statusTitleStyling}>
                {statusLabel}
              </span>
            {/if}
            {#if installing}
              <span class="spinnerSpacingLeftBottom">
                <div class="spinner">
                  <svg
                    preserveAspectRatio="xMidYMid meet"
                    focusable="false"
                    viewBox="0 0 100 100"
                  >
                    <circle cx="50%" cy="50%" r="45" />
                  </svg>
                </div>
              </span>
            {/if}
          </span>
          <span class={hrRightStyling}></span>
          <span>
            <button
              class={startedStatusStyling}
              onclick={() => showAgents(TableAgentsStatus.Started)}
            >
              {#if !isNarrow}
                Started ( {agentsStatusStarted.length} / {installTargets.length}
                )
              {:else}
                Started<br /> ( {agentsStatusStarted.length} )
              {/if}
            </button>
          </span>
          {#if activeWebsocket}
            <span>
              <button
                class={completedStatusStyling}
                onclick={() => showAgents(TableAgentsStatus.Completed)}
              >
                {#if !isNarrow}
                  Completed ( {agentsStatusCompleted.length} / {installTargets.length}
                  )
                {:else}
                  Completed<br /> ( {agentsStatusCompleted.length} )
                {/if}
              </button>
            </span>
            <span>
              <button
                class={failedStatusStyling}
                onclick={() => showAgents(TableAgentsStatus.Failed)}
              >
                {#if !isNarrow}
                  Failed ( {agentsStatusFailed.length} / {installTargets.length}
                  )
                {:else}
                  Failed<br /> ( {agentsStatusFailed.length} )
                {/if}
              </button>
            </span>
          {/if}
        {:else if scopeSummary}
          <span class="scopeSummary">{scopeSummary}</span>
        {:else}
          <span></span>
        {/if}
      </div>
    {/if}
  </div>
</div>

<style>
  .component {
    color-scheme: var(--uic-color-scheme, light dark);

    --bfu-text: var(--uic-on-background, CanvasText);
    --bfu-surface: var(--uic-background, Canvas);
    --bfu-accent: var(--uic-primary, #1059d2);
    --bfu-on-accent: var(--uic-on-primary, #ffffff);

    --bfu-border: rgba(127, 127, 127, 0.32);
    --bfu-border: color-mix(in srgb, var(--bfu-text) 20%, transparent);

    --bfu-divider: rgba(127, 127, 127, 0.24);
    --bfu-divider: color-mix(in srgb, var(--bfu-text) 14%, transparent);

    --bfu-subtle: rgba(127, 127, 127, 0.16);
    --bfu-subtle: color-mix(in srgb, var(--bfu-text) 10%, transparent);

    --bfu-hover: rgba(127, 127, 127, 0.1);
    --bfu-hover: color-mix(in srgb, var(--bfu-text) 6%, transparent);

    --bfu-muted: rgba(127, 127, 127, 1);
    --bfu-muted: color-mix(in srgb, var(--bfu-text) 62%, transparent);

    --bfu-accent-tint: rgba(127, 127, 127, 0.16);
    --bfu-accent-tint: color-mix(in srgb, var(--bfu-accent) 16%, transparent);

    color: var(--bfu-text);
    font-family: var(--font-family, Roboto, "Helvetica Neue", sans-serif);
    font-size: 14px;

    --bfu-controls-bottom: 95px;
    --bfu-search-height: 44px;
    --bfu-table-top: calc(
      var(--bfu-controls-bottom) + var(--bfu-search-height)
    );
    --bfu-status-height: 43px;
    --bfu-status-height-narrow: 55px;
  }

  button,
  select {
    font: inherit;
  }

  button:focus-visible,
  select:focus-visible,
  input:focus-visible {
    outline: 2px solid var(--bfu-accent);
    outline-offset: 2px;
  }

  .componentPadding {
    padding: 8px;
  }

  .buttonPadding {
    padding: 4px;
  }

  .componentHeader {
    display: flex;
    flex-direction: row;
    height: 40px;
    box-sizing: border-box;
    white-space: nowrap;
    z-index: 1;
  }

  .componentTitle {
    flex: 1 0 auto;
    margin: 0;
    font-size: 14px;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .componentLine {
    display: flex;
    justify-content: space-between;
  }

  .permissionNotice {
    margin: 16px 0;
    max-width: 46em;
    color: var(--bfu-text);
    line-height: 1.5;
  }

  .narrowWidth {
    width: 200px;
  }

  .hrTop,
  .hrBottom,
  .hrBottomIsNarrow {
    width: calc(100% + 24px);
    display: block;
    height: 0;
    border: 0 none;
    border-top: 1px solid var(--bfu-divider);
    position: absolute;
  }

  .hrTop {
    top: var(--bfu-controls-bottom);
  }

  .hrBottom {
    bottom: var(--bfu-status-height);
  }

  .hrBottomIsNarrow {
    bottom: var(--bfu-status-height-narrow);
  }

  .hrRight,
  .hrRightIsNarrow {
    display: block;
    border-right: 1px solid var(--bfu-divider);
  }

  .hrRight {
    height: 25px;
  }

  .select {
    width: 280px;
    display: grid;
    grid-template-areas: "select";
    align-items: center;
  }

  select {
    appearance: none;
    cursor: pointer;
    height: 37px;
    text-align: center;
    border: 1px solid var(--bfu-border);
    border-radius: 4px;
    background-color: var(--bfu-surface);
    color: var(--bfu-text);
  }

  .select::after {
    content: "";
    width: 0.6em;
    height: 0.3em;
    background-color: var(--bfu-text);
    clip-path: polygon(100% 0%, 0 0%, 50% 100%);
    justify-self: right;
    pointer-events: none;
    margin-right: 0.9em;
  }

  select,
  .select::after {
    grid-area: select;
  }

  select option:disabled {
    color: var(--bfu-muted);
  }

  optgroup {
    font-style: normal;
    background-color: var(--bfu-surface);
    color: var(--bfu-text);
    text-align: left;
    text-align-last: center;
  }

  .startInstallationButtonStyleEnabled,
  .startInstallationButtonStyleDisabled {
    float: right;
    width: 280px;
    height: 37px;
    text-align: center;
    border: none;
    border-radius: 4px;
  }

  .startInstallationButtonStyleEnabled {
    cursor: pointer;
    background-color: var(--bfu-accent);
    color: var(--bfu-on-accent);
  }

  .startInstallationButtonStyleDisabled {
    cursor: default;
    background-color: var(--bfu-subtle);
    color: var(--bfu-muted);
  }

  .spinner {
    height: 19px;
    width: 19px;
    position: relative;
    animation: spinner-rotate 2000ms linear infinite;
  }

  .spinner svg {
    position: absolute;
    transform: rotate(-90deg);
    top: 0;
    left: 0;
    transform-origin: center;
    overflow: visible;
    height: 19px;
    width: 19px;
  }

  .spinner svg circle {
    fill: transparent;
    stroke: currentColor;
    transform-origin: center;
    transition: stroke-dashoffset 225ms linear;
    transition-property: stroke;
    animation-duration: 4000ms;
    animation-timing-function: cubic-bezier(0.35, 0, 0.25, 1);
    animation-iteration-count: infinite;
    animation-name: spinner-rotate-elastic;
    stroke-dasharray: 282.743px;
    stroke-width: 10%;
  }

  .spinnerRow,
  .nonSpinnerRow {
    display: flex;
    height: 100%;
    flex-direction: row;
    place-content: center;
    align-items: center;
  }

  .nonSpinnerRow {
    padding-top: 8px;
  }

  .spinnerSpacingRight {
    padding: 0 0.5em 0 0;
  }

  .spinnerSpacingLeftBottom {
    padding: 0 0 0.3em 0.5em;
  }

  @keyframes spinner-rotate {
    0% {
      transform: rotate(0deg);
    }
    100% {
      transform: rotate(360deg);
    }
  }

  @keyframes spinner-rotate-elastic {
    0% {
      stroke-dashoffset: 268.606171575px;
      transform: rotate(0);
    }
    12.5% {
      stroke-dashoffset: 56.5486677px;
      transform: rotate(0);
    }
    12.5001% {
      stroke-dashoffset: 56.5486677px;
      transform: rotateX(180deg) rotate(72.5deg);
    }
    25% {
      stroke-dashoffset: 268.606171575px;
      transform: rotateX(180deg) rotate(72.5deg);
    }
    25.0001% {
      stroke-dashoffset: 268.606171575px;
      transform: rotate(270deg);
    }
    37.5% {
      stroke-dashoffset: 56.5486677px;
      transform: rotate(270deg);
    }
    37.5001% {
      stroke-dashoffset: 56.5486677px;
      transform: rotateX(180deg) rotate(161.5deg);
    }
    50% {
      stroke-dashoffset: 268.606171575px;
      transform: rotateX(180deg) rotate(161.5deg);
    }
    50.0001% {
      stroke-dashoffset: 268.606171575px;
      transform: rotate(180deg);
    }
    62.5% {
      stroke-dashoffset: 56.5486677px;
      transform: rotate(180deg);
    }
    62.5001% {
      stroke-dashoffset: 56.5486677px;
      transform: rotateX(180deg) rotate(251.5deg);
    }
    75% {
      stroke-dashoffset: 268.606171575px;
      transform: rotateX(180deg) rotate(251.5deg);
    }
    75.0001% {
      stroke-dashoffset: 268.606171575px;
      transform: rotate(90deg);
    }
    87.5% {
      stroke-dashoffset: 56.5486677px;
      transform: rotate(90deg);
    }
    87.5001% {
      stroke-dashoffset: 56.5486677px;
      transform: rotateX(180deg) rotate(341.5deg);
    }
    100% {
      stroke-dashoffset: 268.606171575px;
      transform: rotateX(180deg) rotate(341.5deg);
    }
  }

  .statusWrapper {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 5px;
    padding: 0 8px;
    overflow: auto;
    overflow-anchor: none;
    display: flex;
    justify-content: space-between;
  }

  .iconButton {
    cursor: pointer;
    outline: 0;
    border: none;
    padding: 0;
    background-color: transparent;
    color: var(--bfu-muted);
    vertical-align: middle;
    display: inline-block;
  }

  .iconButton:hover {
    color: var(--bfu-text);
  }

  .iconButton svg {
    width: 24px;
    height: 24px;
    fill: currentColor;
  }

  .installationStatusTitleStyle,
  .installationStatusTitleStyleIsNarrow {
    margin: 0;
    color: var(--bfu-text);
    overflow: hidden;
    text-overflow: ellipsis;
    padding-bottom: 4px;
  }

  .installationStatusTitleStyleIsNarrow {
    padding-right: 8px;
  }

  .statusNotSelected,
  .statusSelected {
    cursor: pointer;
    outline: 0;
    border: none;
    border-radius: 20px;
    vertical-align: middle;
    display: inline-block;
  }

  .statusNotSelected {
    background-color: transparent;
    color: var(--bfu-muted);
    padding: 4px 12px;
  }

  .statusNotSelected:hover {
    background-color: var(--bfu-hover);
    color: var(--bfu-text);
  }

  .statusSelected {
    background-color: var(--bfu-accent-tint);
    color: var(--bfu-text);
    padding: 4px 14px;
    font-weight: 500;
  }

  .searchRow {
    position: absolute;
    left: 0;
    right: 0;
    top: var(--bfu-controls-bottom);
    z-index: 20;
    height: var(--bfu-search-height);
    padding: 0 8px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .backButton {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    gap: 4px;
    height: 32px;
    padding: 0 10px 0 6px;
    border: 1px solid var(--bfu-border);
    border-radius: 4px;
    background-color: var(--bfu-surface);
    color: var(--bfu-text);
    cursor: pointer;
    white-space: nowrap;
  }

  .backButton:hover {
    background-color: var(--bfu-hover);
  }

  .backIcon {
    width: 18px;
    height: 18px;
    fill: currentColor;
  }

  .exportButton {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px 4px 6px;
    border: none;
    border-radius: 20px;
    background-color: transparent;
    color: var(--bfu-text);
    cursor: pointer;
    white-space: nowrap;
  }

  .exportButton:hover {
    background-color: var(--bfu-hover);
  }

  .exportIcon {
    width: 20px;
    height: 20px;
    fill: currentColor;
  }

  .groupPicker {
    position: relative;
    flex: 0 1 auto;
    max-width: 40%;
    display: flex;
  }

  .groupButton {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 2px;
    height: 32px;
    padding: 0 4px 0 10px;
    border: 1px solid var(--bfu-border);
    border-radius: 4px;
    background-color: var(--bfu-surface);
    color: var(--bfu-text);
    cursor: pointer;
  }

  .groupButton:disabled {
    cursor: default;
    border-color: var(--bfu-divider);
    color: var(--bfu-muted);
  }

  .groupButtonActive {
    border-color: var(--bfu-accent);
    background-color: var(--bfu-accent-tint);
    font-weight: 500;
  }

  .groupButtonLabel {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .groupButtonArrow {
    flex: 0 0 auto;
    width: 18px;
    height: 18px;
    fill: currentColor;
  }

  .groupPanel {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    z-index: 30;
    min-width: 260px;
    max-width: 380px;
    display: flex;
    flex-direction: column;
    border: 1px solid var(--bfu-border);
    border-radius: 4px;
    background-color: var(--bfu-surface);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.18);
  }

  .groupPanelSearch {
    margin: 6px;
    height: 28px;
    box-sizing: border-box;
    padding: 0 8px;
    border: 1px solid var(--bfu-border);
    border-radius: 4px;
    background-color: var(--bfu-surface);
    color: var(--bfu-text);
    font: inherit;
  }

  .groupPanelList {
    max-height: 232px;
    overflow-y: auto;
    padding: 0 0 4px 0;
  }

  .groupOption {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 10px;
    cursor: pointer;
  }

  .groupOption:hover {
    background-color: var(--bfu-hover);
  }

  .groupOptionLabel {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .groupPanelEmpty {
    margin: 0;
    padding: 6px 10px;
    color: var(--bfu-muted);
  }

  .groupPanelClear {
    border: none;
    border-top: 1px solid var(--bfu-divider);
    background: transparent;
    color: var(--bfu-text);
    text-align: left;
    padding: 8px 10px;
    cursor: pointer;
  }

  .groupPanelClear:hover {
    background-color: var(--bfu-hover);
  }

  .searchField {
    position: relative;
    flex: 1 1 auto;
    display: flex;
    align-items: center;
    min-width: 0;
  }

  .searchField input {
    width: 100%;
    height: 32px;
    box-sizing: border-box;
    padding: 0 32px 0 32px;
    border: 1px solid var(--bfu-border);
    border-radius: 4px;
    background-color: var(--bfu-surface);
    color: var(--bfu-text);
    font: inherit;
  }

  .searchField input::placeholder {
    color: var(--bfu-muted);
  }

  .searchField input:disabled {
    cursor: default;
    border-color: var(--bfu-divider);
  }

  .searchIcon {
    position: absolute;
    left: 8px;
    width: 18px;
    height: 18px;
    fill: var(--bfu-muted);
    pointer-events: none;
  }

  .searchClear {
    position: absolute;
    right: 6px;
    display: flex;
    align-items: center;
    padding: 2px;
    border: none;
    border-radius: 50%;
    background: transparent;
    color: var(--bfu-muted);
    cursor: pointer;
  }

  .searchClear:hover {
    color: var(--bfu-text);
    background-color: var(--bfu-hover);
  }

  .searchClear svg {
    width: 16px;
    height: 16px;
    fill: currentColor;
  }

  .scopeSummary {
    align-self: center;
    color: var(--bfu-muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .searchCount {
    flex: 0 0 auto;
    color: var(--bfu-muted);
    white-space: nowrap;
  }

  .tableWrapper,
  .tableWrapperIsNarrow {
    position: absolute;
    left: 0;
    right: 0;
    top: var(--bfu-table-top);
    padding: 0 8px;
    overflow: auto;
    overflow-anchor: none;
    scrollbar-gutter: stable;
  }

  .tableWrapper {
    bottom: var(--bfu-status-height);
  }

  .tableWrapperIsNarrow {
    bottom: var(--bfu-status-height-narrow);
  }

  table {
    width: 100%;
    border-collapse: collapse;
    color: var(--bfu-text);
  }

  table th,
  table td {
    text-align: left;
    padding-right: 16px;
    white-space: nowrap;
  }

  table th:last-child,
  table td:last-child {
    padding-right: 0;
  }

  table thead th {
    position: sticky;
    top: 0;
    background: var(--bfu-surface);
    z-index: 10;
    font-weight: 600;
    padding-top: 12px;
    padding-bottom: 6px;
    box-shadow: inset 0 -1px 0 var(--bfu-divider);
  }

  table thead tr,
  table tbody tr {
    height: 28px;
  }

  table tbody tr:not(.rowBlocked):hover {
    background-color: var(--bfu-hover);
  }

  .rowBlocked {
    color: var(--bfu-muted);
    cursor: not-allowed;
  }

  .columnCheck {
    width: 34px;
    padding-right: 8px;
  }

  .lockBadge {
    display: inline-flex;
    width: 16px;
    height: 16px;
    vertical-align: middle;
    color: var(--bfu-muted);
    cursor: not-allowed;
  }

  .lockBadge svg {
    width: 100%;
    height: 100%;
    fill: currentColor;
  }

  input[type="checkbox"] {
    cursor: pointer;
    width: 16px;
    height: 16px;
    margin: 0;
    vertical-align: middle;
    accent-color: var(--bfu-accent);
  }

  input[type="checkbox"]:disabled {
    cursor: not-allowed;
  }

  .columnName {
    width: auto;
    min-width: 9em;
    max-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  table thead th {
    cursor: pointer;
    user-select: none;
  }

  .sortHeader {
    display: inline-flex;
    align-items: center;
    gap: 2px;
  }

  .sortArrow {
    font-size: 9px;
    line-height: 1;
    visibility: hidden;
  }

  .sortArrowActive {
    visibility: visible;
  }

  table thead th:hover .sortArrow {
    visibility: visible;
    color: var(--bfu-muted);
  }

  .rowSelectable {
    cursor: pointer;
  }

  .columnType,
  .columnGroups {
    width: 1%;
    max-width: 14em;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .columnStatus {
    width: 1%;
    max-width: 22em;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .columnSerialNumber,
  .columnFirmware {
    width: 1%;
    font-variant-numeric: tabular-nums;
  }

  .tableEmpty {
    padding-top: 12px;
    color: var(--bfu-muted);
  }
</style>