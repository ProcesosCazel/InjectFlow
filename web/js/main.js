/*
InjectFlow
---------------------------------------------------------------------------
Proyecto: Automatización de hojas de parámetros de proceso

Autor:
    Ing. José Antonio Guzmán Trujillo
    Becario de Procesos | Industrias Cazel
    tecnicosprocesos@cazel.mx
    2026
---------------------------------------------------------------------------
*/

(() => {
  "use strict";

  const APP = Object.freeze({
    name: "InjectFlow",
    version: "v3.0",
    year: "2026",
  });

  const POPUP_TYPES = Object.freeze({
    info: {
      label: "Información",
      icon: "i",
    },
    success: {
      label: "Completado",
      icon: "✓",
    },
    warning: {
      label: "Advertencia",
      icon: "!",
    },
    error: {
      label: "Error",
      icon: "×",
    },
    confirm: {
      label: "Confirmación",
      icon: "?",
    },
    processing: {
      label: "Procesando",
      icon: "…",
    },
  });

  const SCREEN_NAMES = Object.freeze(["home", "logs", "preview"]);
  const VALID_FILE_TYPES = Object.freeze(["param", "resul"]);

  const DEFAULT_INPUT_POLICY = Object.freeze({
    inputMode: "DAT_OPTIONAL_RESUL", paramExtension: ".dat",
    paramDisplay: "Param.dat", supportsResultants: true,
    requiresInjectionControl: true,
  });
  let machineOptions = [];
  let machineChangeSerial = 0;
  let machineChangeQueue = Promise.resolve();

  const state = {
    currentScreen: "home",
    paramFile: null,
    resulFile: null,
    machine: "",
    mold: "",
    injectionControl: "",
    inputPolicy: { ...DEFAULT_INPUT_POLICY },
    machineSyncPending: false,
    machineSyncFailed: false,
    generation: {
      active: false,
      progress: 0,
      status: "",
    },
    backend: {
      available: false,
      ready: false,
      apiVersion: "",
      renderer: "",
      sessionId: "",
      pingOk: false,
      pythonSignalReceived: false,
      manualSelectorsLoaded: false,
      machineCount: 0,
      injectionControlCount: 0,
      fileDialogsEnabled: false,
      dragDropBound: false,
      fileInputsEnabled: false,
      generationEnabled: false,
      openOutputFolderEnabled: false,
      openGeneratedOutputEnabled: false,
      latestOutput: null,
      historyEnabled: false,
      historyLoaded: false,
      historyCount: 0,
      previewEnabled: false,
      previewLoaded: false,
      previewName: "",
      lastGeneration: null,
      lastError: "",
    },
  };

  const dom = {};

  let initialized = false;
  let activePopupResolver = null;
  let popupPreviousFocus = null;
  let previewObjectUrl = null;
  let previewLoadActive = false;
  let previewReloadQueued = false;

  function byId(id) {
    return document.getElementById(id);
  }

  function cacheDom() {
    Object.assign(dom, {
      homeSection: byId("home-section"),
      logsSection: byId("logs-section"),
      previewSection: byId("preview-section"),

      paramTitle: byId("param-upload-title"),
      paramHelp: byId("param-upload-help"),
      resulPanel: byId("resul-upload-panel"),
      injectionControlPanel: byId("injection-control-panel"),
      paramDropZone: byId("param-drop-zone"),
      paramUploadButton: byId("param-upload-button"),
      paramRemoveButton: byId("param-remove-button"),
      paramUploadStatus: byId("param-upload-status"),

      resulDropZone: byId("resul-drop-zone"),
      resulUploadButton: byId("resul-upload-button"),
      resulRemoveButton: byId("resul-remove-button"),
      resulUploadStatus: byId("resul-upload-status"),

      machineSelect: byId("machine-select"),
      moldInput: byId("mold-input"),
      injectionControlSelect: byId("inj-ctrl-select"),

      summaryContent: byId("summary-content"),
      generateButton: byId("generate-button"),
      generationStatus: byId("generation-status"),

      loadingBarDiv: byId("loading-bar-div"),
      loadingBar: byId("loading-bar"),
      loadingBarPercent: byId("loading-bar-percent"),

      openPreviewButton: byId("open-preview-button"),
      openSheetButton: byId("open-sheet-button"),
      openFolderButton: byId("open-folder-button"),
      openLogsButton: byId("open-logs-button"),

      logsContent: byId("logs-content"),
      clearHistoryButton: byId("clear-history-button"),
      returnButton: byId("return-button"),

      previewContent: byId("preview-content"),
      refreshPreviewButton: byId("refresh-preview-button"),
      returnPreviewButton: byId("return-preview-button"),

      popupSection: byId("popup-section"),
      popupOverlay: byId("popup-overlay"),
      popupDialog: byId("popup-dialog"),
      popupIcon: byId("popup-icon"),
      popupTypeLabel: byId("popup-type-label"),
      popupTitle: byId("popup-title"),
      popupCloseButton: byId("popup-close-button"),
      popupMessage: byId("popup-message"),
      popupSecondaryMessage: byId("popup-secondary-message"),

      popupDetails: byId("popup-details"),
      popupDetailsTitle: byId("popup-details-title"),
      popupDetailsContent: byId("popup-details-content"),

      popupMissingParams: byId("popup-missing-params"),
      popupMissingParamsCount: byId("popup-missing-params-count"),
      popupMissingParamsList: byId("popup-missing-params-list"),

      popupProgress: byId("popup-progress"),
      popupProgressText: byId("popup-progress-text"),
      popupProgressPercent: byId("popup-progress-percent"),
      popupProgressTrack: document.querySelector(
        "#popup-progress .popup-progress-track",
      ),
      popupProgressBar: byId("popup-progress-bar"),

      popupTechnicalDetails: byId("popup-technical-details"),
      popupTechnicalText: byId("popup-technical-text"),

      popupTertiaryButton: byId("popup-tertiary-button"),
      popupSecondaryButton: byId("popup-secondary-button"),
      popupPrimaryButton: byId("popup-primary-button"),

      appVersion: byId("app-version"),
      appYear: byId("app-year"),
    });
  }

  /**
   * Alterna la clase hidden en un elemento DOM.
   *
   * @param {HTMLElement | null} element - Elemento a actualizar.
   * @param {boolean} hidden - Si debe ocultarse.
   */
  function setHidden(element, hidden) {
    if (!element) {
      return;
    }

    element.classList.toggle("hidden", Boolean(hidden));
  }

  /**
   * Actualiza el texto visible de un nodo HTML.
   *
   * @param {HTMLElement | null} element - Elemento objetivo.
   * @param {*} value - Valor a mostrar.
   */
  function setText(element, value = "") {
    if (!element) {
      return;
    }

    element.textContent = value == null ? "" : String(value);
  }

  function clampPercent(value) {
    const parsed = Number(value);

    if (!Number.isFinite(parsed)) {
      return 0;
    }

    return Math.min(100, Math.max(0, parsed));
  }

  function emit(name, detail = {}) {
    document.dispatchEvent(
      new CustomEvent(name, {
        detail,
      }),
    );
  }

  function getState() {
    return {
      currentScreen: state.currentScreen,
      paramFile: state.paramFile ? { ...state.paramFile } : null,
      resulFile: state.resulFile ? { ...state.resulFile } : null,
      machine: state.machine,
      mold: state.mold,
      injectionControl: state.injectionControl,
      inputPolicy: { ...state.inputPolicy },
      machineSyncPending: state.machineSyncPending,
      machineSyncFailed: state.machineSyncFailed,
      generation: { ...state.generation },
      backend: { ...state.backend },
    };
  }

  /* -----------------------------------------------------------------------
   * Application metadata
   * --------------------------------------------------------------------- */

  function setAppMetadata({ version = APP.version, year = APP.year } = {}) {
    setText(dom.appVersion, version);
    setText(dom.appYear, year);
  }

  /* -----------------------------------------------------------------------
   * Screen navigation
   * --------------------------------------------------------------------- */

  /**
   * Muestra una pantalla del flujo principal de la aplicación.
   *
   * @param {"home" | "logs" | "preview"} screenName - Nombre de la vista activa.
   */
  function showScreen(screenName) {
    if (!SCREEN_NAMES.includes(screenName)) {
      throw new Error(`Pantalla no válida: ${screenName}`);
    }

    state.currentScreen = screenName;

    setHidden(dom.homeSection, screenName !== "home");
    setHidden(dom.logsSection, screenName !== "logs");
    setHidden(dom.previewSection, screenName !== "preview");

    emit("injectflow:screen-changed", {
      screen: screenName,
    });
  }

  /* -----------------------------------------------------------------------
   * File UI states
   * --------------------------------------------------------------------- */

  function normalizeFileInfo(fileInfo) {
    if (!fileInfo) {
      return null;
    }

    if (typeof fileInfo === "string") {
      return {
        name: fileInfo,
        path: "",
      };
    }

    return {
      name: fileInfo.name || "",
      path: fileInfo.path || "",
      extension: fileInfo.extension || "",
      size: Number(fileInfo.size || 0),
      source: fileInfo.source || "",
      selectedAt: fileInfo.selectedAt || "",
    };
  }

  /**
   * Asigna un archivo a la sección de entrada correspondiente.
   *
   * @param {"param" | "resul"} kind - Tipo de archivo.
   * @param {File | {name: string, path?: string} | null} fileInfo - Información del archivo.
   */
  function updateFileDropZoneState(kind, fileInfo = null) {
    const isParam = kind === "param";
    const zone = isParam ? dom.paramDropZone : dom.resulDropZone;

    if (!zone) {
      return;
    }

    const textElement = zone.querySelector(".file-drop-zone-text");
    const expectedName = isParam ? state.inputPolicy.paramDisplay : "Resul.csv";
    const loaded = Boolean(fileInfo?.name);

    zone.classList.toggle("file-loaded", loaded);
    zone.setAttribute(
      "aria-label",
      loaded
        ? `${expectedName} cargado correctamente: ${fileInfo.name}`
        : `Área para seleccionar o arrastrar el archivo ${expectedName}`,
    );

    if (!textElement) {
      return;
    }

    if (loaded) {
      textElement.textContent = `Archivo cargado: ${fileInfo.name}`;
      return;
    }

    textElement.replaceChildren(
      document.createTextNode("Arrastra y suelta aquí el archivo "),
    );

    const codeElement = document.createElement("code");
    codeElement.textContent = expectedName;
    textElement.appendChild(codeElement);
  }

  function setFile(kind, fileInfo = null) {
    if (!VALID_FILE_TYPES.includes(kind)) {
      throw new Error(`Tipo de archivo no válido: ${kind}`);
    }

    const normalized = normalizeFileInfo(fileInfo);
    const isParam = kind === "param";

    if (isParam) {
      state.paramFile = normalized;
    } else {
      state.resulFile = normalized;
    }

    const statusElement = isParam
      ? dom.paramUploadStatus
      : dom.resulUploadStatus;

    if (normalized?.name) {
      setText(statusElement, `Archivo seleccionado: ${normalized.name}`);
    } else {
      setText(statusElement, "");
    }

    updateFileDropZoneState(kind, normalized);

    const removeButton = isParam
      ? dom.paramRemoveButton
      : dom.resulRemoveButton;

    if (removeButton) {
      removeButton.disabled =
        !state.backend.fileInputsEnabled || !normalized?.name;
    }

    updateSummary();
    updateGenerateState();

    emit("injectflow:file-state-changed", {
      kind,
      file: normalized ? { ...normalized } : null,
    });
  }

  function setFileStatus(kind, message = "") {
    const statusElement =
      kind === "param"
        ? dom.paramUploadStatus
        : kind === "resul"
          ? dom.resulUploadStatus
          : null;

    if (!statusElement) {
      throw new Error(`Tipo de archivo no válido: ${kind}`);
    }

    setText(statusElement, message);
  }

  function setFileControlsEnabled(enabled = true) {
    const active = Boolean(enabled) && !state.machineSyncPending && !state.machineSyncFailed;
    const resultsEnabled = active && state.inputPolicy.supportsResultants;
    state.backend.fileInputsEnabled = active;

    if (dom.paramUploadButton) {
      dom.paramUploadButton.disabled = !active;
    }

    if (dom.resulUploadButton) {
      dom.resulUploadButton.disabled = !resultsEnabled;
    }

    if (dom.paramRemoveButton) {
      dom.paramRemoveButton.disabled = !active || !state.paramFile;
    }

    if (dom.resulRemoveButton) {
      dom.resulRemoveButton.disabled = !resultsEnabled || !state.resulFile;
    }

    for (const zone of [dom.paramDropZone, dom.resulDropZone]) {
      if (!zone) {
        continue;
      }

      const zoneEnabled = zone === dom.resulDropZone ? resultsEnabled : active;
      zone.setAttribute("aria-disabled", zoneEnabled ? "false" : "true");
    }
  }

  /* -----------------------------------------------------------------------
   * Selects and manual fields
   * --------------------------------------------------------------------- */

  function populateSelect(
    selectElement,
    items,
    { placeholder = "Selecciona una opción", selectedValue = "" } = {},
  ) {
    if (!selectElement) {
      return;
    }

    selectElement.replaceChildren();

    const placeholderOption = document.createElement("option");
    placeholderOption.value = "";
    placeholderOption.textContent = placeholder;
    placeholderOption.disabled = true;
    placeholderOption.selected = !selectedValue;
    selectElement.appendChild(placeholderOption);

    for (const item of items || []) {
      const option = document.createElement("option");

      if (typeof item === "object" && item !== null) {
        option.value = String(item.value ?? "");
        option.textContent = String(item.label ?? item.value ?? "");
      } else {
        option.value = String(item);
        option.textContent = String(item);
      }

      if (option.value === String(selectedValue)) {
        option.selected = true;
      }

      selectElement.appendChild(option);
    }
  }

  function setMachineOptions(items, selectedValue = "") {
    machineOptions = Array.isArray(items) ? items.map((item) => ({ ...item })) : [];
    populateSelect(dom.machineSelect, items, {
      placeholder: "Selecciona una máquina",
      selectedValue,
    });

    state.machine = selectedValue || "";
    updateSummary();
  }

  function setInjectionControlOptions(items, selectedValue = "") {
    populateSelect(dom.injectionControlSelect, items, {
      placeholder: "Selecciona el control de inyección",
      selectedValue,
    });

    state.injectionControl = selectedValue || "";
    updateSummary();
  }

  function normalizeInputPolicy(raw = {}) {
    return {
      inputMode: raw.inputMode || DEFAULT_INPUT_POLICY.inputMode,
      paramExtension: raw.paramExtension || DEFAULT_INPUT_POLICY.paramExtension,
      paramDisplay: raw.paramDisplay || DEFAULT_INPUT_POLICY.paramDisplay,
      supportsResultants: raw.supportsResultants !== false,
      requiresInjectionControl: raw.requiresInjectionControl !== false,
    };
  }

  function applyFamilyPresentation(rawPolicy = {}) {
    state.inputPolicy = normalizeInputPolicy(rawPolicy);
    const policy = state.inputPolicy;
    const xmlOnly = !policy.supportsResultants;
    dom.homeSection?.classList.toggle("xml-only", xmlOnly);
    setText(byId("process-data-title"), `${xmlOnly ? 2 : 3}. Datos del proceso`);
    setText(byId("summary-gen-title"), `${xmlOnly ? 3 : 4}. Resumen y generaci\u00f3n`);
    setText(dom.paramTitle, xmlOnly ? "1. Par\u00e1metros XML" : "1. Param.dat");
    setText(dom.paramHelp, xmlOnly
      ? "Selecciona el XML descargado de la m\u00e1quina. Jupiter utiliza solo par\u00e1metros."
      : "Selecciona el archivo Param.dat descargado directamente de la m\u00e1quina de inyecci\u00f3n.");
    for (const [element, hidden] of [
      [dom.resulPanel, xmlOnly],
      [dom.injectionControlPanel, !policy.requiresInjectionControl],
    ]) {
      if (element) {
        element.hidden = hidden;
        element.classList.toggle("hidden", hidden);
      }
    }
    if (dom.injectionControlSelect) {
      dom.injectionControlSelect.disabled = !policy.requiresInjectionControl ||
        state.generation.active || !state.backend.manualSelectorsLoaded;
    }
    updateFileDropZoneState("param", state.paramFile);
    updateSummary();
  }

  async function setMachine(value = "") {
    const machine = String(value || "").trim().toUpperCase();
    const serial = ++machineChangeSerial;
    state.machine = machine;
    state.machineSyncFailed = false;
    if (dom.machineSelect) dom.machineSelect.value = machine;
    const option = machineOptions.find((item) => item.value === machine);
    applyFamilyPresentation(option || DEFAULT_INPUT_POLICY);
    // Remove incompatible state immediately in the UI; Python independently
    // clears the registered paths. Neither side deletes any physical file.
    if (state.paramFile && !String(state.paramFile.path || state.paramFile.name)
      .toLowerCase().endsWith(state.inputPolicy.paramExtension)) setFile("param", null);
    if (!state.inputPolicy.supportsResultants) setFile("resul", null);
    if (!bridgeAvailable()) {
      state.machineSyncPending = false;
      updateGenerateState();
      return null;
    }
    state.machineSyncPending = true;
    setFileControlsEnabled(false);
    updateGenerateState();
    // Serialize changes so a slow response cannot leave Python on an older
    // machine after the user rapidly changes the selector twice.
    const operation = machineChangeQueue.catch(() => {}).then(() =>
      window.pywebview.api.set_machine(machine));
    machineChangeQueue = operation;
    try {
      const response = await operation;
      if (serial !== machineChangeSerial) return response;
      if (!response?.ok) throw new Error(response?.error?.message || "No se pudo cambiar de maquina.");
      applyFamilyPresentation(response.policy);
      setFile("param", response.files?.param || null);
      setFile("resul", response.files?.resul || null);
      return response;
    } catch (error) {
      if (serial === machineChangeSerial) {
        state.machineSyncFailed = true;
        state.backend.lastError = normalizeBridgeError(error);
        setFileStatus("param", state.backend.lastError);
      }
      return null;
    } finally {
      if (serial === machineChangeSerial) {
        state.machineSyncPending = false;
        setFileControlsEnabled(!state.generation.active &&
          (state.backend.fileDialogsEnabled || state.backend.dragDropBound));
        updateSummary();
        updateGenerateState();
      }
    }
  }

  function setMold(value = "") {
    state.mold = String(value || "").trim();

    if (dom.moldInput && dom.moldInput.value !== state.mold) {
      dom.moldInput.value = state.mold;
    }

    updateSummary();
    updateGenerateState();
  }

  function setInjectionControl(value = "") {
    state.injectionControl = String(value || "");

    if (dom.injectionControlSelect) {
      dom.injectionControlSelect.value = state.injectionControl;
    }

    updateSummary();
    updateGenerateState();
  }

  function setHomeControlsEnabled(enabled = true) {
    const controls = [
      dom.paramUploadButton,
      dom.paramRemoveButton,
      dom.resulUploadButton,
      dom.resulRemoveButton,
      dom.machineSelect,
      dom.moldInput,
      dom.injectionControlSelect,
      dom.generateButton,
    ];

    for (const control of controls) {
      if (control) {
        control.disabled = !enabled;
      }
    }
  }

  function setGenerateEnabled(enabled = true) {
    if (dom.generateButton) {
      dom.generateButton.disabled = !enabled;
    }
  }

  /* -----------------------------------------------------------------------
   * Summary
   * --------------------------------------------------------------------- */

  function createSummaryRow(label, value, optional = false) {
    const row = document.createElement("div");
    row.className = "summary-row";

    const labelElement = document.createElement("span");
    labelElement.className = "summary-label";
    labelElement.textContent = label;

    const valueElement = document.createElement("span");
    valueElement.className = "summary-value";

    const resolvedValue =
      value && String(value).trim()
        ? String(value)
        : optional
          ? "No seleccionado (opcional)"
          : "Pendiente";

    valueElement.textContent = resolvedValue;

    row.append(labelElement, valueElement);

    return row;
  }

  function generationModeLabel() {
    if (!state.inputPolicy.supportsResultants) return "Solo par\u00e1metros (XML)";
    return state.resulFile
      ? "Parámetros + Resultantes"
      : "Solo Param.dat";
  }

  function updateGenerateState() {
    const ready = Boolean(
      state.backend.generationEnabled &&
      !state.generation.active &&
      !state.machineSyncPending && !state.machineSyncFailed &&
      state.paramFile?.path &&
      state.machine &&
      state.mold &&
      (!state.inputPolicy.requiresInjectionControl || state.injectionControl)
    );

    setGenerateEnabled(ready);
    return ready;
  }

  function updateSummary() {
    if (!dom.summaryContent) {
      return;
    }

    const rows = [createSummaryRow(state.inputPolicy.paramDisplay, state.paramFile?.name || "")];
    if (state.inputPolicy.supportsResultants) {
      rows.push(createSummaryRow("Resul.csv", state.resulFile?.name || "", true));
    }
    rows.push(createSummaryRow("Modo", generationModeLabel()),
      createSummaryRow("Máquina", state.machine), createSummaryRow("Molde", state.mold));
    if (state.inputPolicy.requiresInjectionControl) {
      rows.push(createSummaryRow("Control de inyección", state.injectionControl));
    }
    dom.summaryContent.replaceChildren(...rows);
  }

  /* -----------------------------------------------------------------------
   * Main generation progress
   * --------------------------------------------------------------------- */

  function setGenerationProgress(
    percent,
    status = "",
    { visible = true, indeterminate = false } = {},
  ) {
    const safePercent = clampPercent(percent);
    const isIndeterminate = Boolean(indeterminate);

    state.generation.active = visible;
    state.generation.progress = safePercent;
    state.generation.status = String(status || "");

    setHidden(dom.loadingBarDiv, !visible);
    dom.loadingBarDiv?.classList.toggle("is-indeterminate", isIndeterminate);

    if (dom.loadingBar) {
      dom.loadingBar.style.width = isIndeterminate ? "" : `${safePercent}%`;
    }

    setText(
      dom.loadingBarPercent,
      isIndeterminate ? "…" : `${Math.round(safePercent)}%`,
    );
    setText(dom.generationStatus, state.generation.status);

    if (dom.loadingBarDiv) {
      if (isIndeterminate) {
        dom.loadingBarDiv.removeAttribute("aria-valuenow");
        dom.loadingBarDiv.setAttribute("aria-valuetext", state.generation.status);
      } else {
        dom.loadingBarDiv.setAttribute(
          "aria-valuenow",
          String(Math.round(safePercent)),
        );
        dom.loadingBarDiv.removeAttribute("aria-valuetext");
      }
    }

    updateGenerateState();
  }

  function hideGenerationProgress({ clearStatus = false } = {}) {
    state.generation.active = false;
    setHidden(dom.loadingBarDiv, true);
    dom.loadingBarDiv?.classList.remove("is-indeterminate");

    if (clearStatus) {
      state.generation.status = "";
      setText(dom.generationStatus, "");
    }

    updateGenerateState();
  }

  /* -----------------------------------------------------------------------
   * Logs and preview placeholders
   * --------------------------------------------------------------------- */

  function renderLogs(items = []) {
    if (!dom.logsContent) {
      return;
    }

    dom.logsContent.replaceChildren();

    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = "No hay registros disponibles.";
      dom.logsContent.appendChild(empty);
      return;
    }

    const list = document.createElement("div");
    list.className = "logs-list";

    for (const item of items) {
      const entry = document.createElement("div");
      entry.className = "logs-entry";

      if (typeof item === "string") {
        entry.textContent = item;
      } else {
        const title = document.createElement("strong");
        title.textContent = item.title || "Registro";

        const detail = document.createElement("span");
        detail.textContent = item.detail || "";

        entry.append(title, detail);
      }

      list.appendChild(entry);
    }

    dom.logsContent.appendChild(list);
  }

  function renderHistory(payload = {}) {
    if (!dom.logsContent) {
      return;
    }

    const items = Array.isArray(payload?.items) ? payload.items : [];
    const retentionDays = Number(payload?.retentionDays || 90);
    const cleanupWarning = String(payload?.cleanupWarning || "");

    if (dom.clearHistoryButton) {
      dom.clearHistoryButton.disabled = items.length === 0;
    }

    dom.logsContent.replaceChildren();

    const summary = document.createElement("div");
    summary.className = "history-summary";

    const summaryText = document.createElement("div");
    summaryText.className = "history-summary-text";

    const count = document.createElement("strong");
    count.textContent = `${items.length} ${items.length === 1 ? "registro" : "registros"}`;

    const retention = document.createElement("span");
    retention.textContent = `Historial vigente: últimos ${retentionDays} días`;

    summaryText.append(count, retention);
    summary.appendChild(summaryText);

    if (cleanupWarning) {
      const warning = document.createElement("p");
      warning.className = "history-warning";
      warning.textContent = cleanupWarning;
      summary.appendChild(warning);
    }

    dom.logsContent.appendChild(summary);

    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "empty-state history-empty-state";
      empty.textContent =
        "El historial se creará automáticamente después de la primera generación exitosa.";
      dom.logsContent.appendChild(empty);
      return;
    }

    const list = document.createElement("div");
    list.className = "logs-list history-list";

    for (const item of items) {
      const entry = document.createElement("article");
      entry.className = "logs-entry history-entry";

      const header = document.createElement("div");
      header.className = "history-entry-header";

      const titleGroup = document.createElement("div");
      titleGroup.className = "history-entry-title-group";

      const title = document.createElement("strong");
      const mold = String(item?.mold || "Sin molde");
      const machine = String(item?.machine || "—");
      title.textContent = `${mold} · Máquina ${machine}`;

      const timestamp = document.createElement("span");
      timestamp.className = "history-entry-time";
      timestamp.textContent = String(item?.timestamp || "Fecha no disponible");

      titleGroup.append(title, timestamp);
      header.appendChild(titleGroup);

      const fileExists = Boolean(item?.file?.exists);
      const badge = document.createElement("span");
      badge.className = `history-status-badge ${fileExists ? "is-available" : "is-missing"}`;
      badge.textContent = fileExists ? "Disponible" : "No disponible";
      header.appendChild(badge);

      const details = document.createElement("div");
      details.className = "history-entry-details";

      const addDetail = (label, value) => {
        const row = document.createElement("div");
        row.className = "history-detail";

        const labelElement = document.createElement("span");
        labelElement.className = "history-detail-label";
        labelElement.textContent = label;

        const valueElement = document.createElement("span");
        valueElement.className = "history-detail-value";
        valueElement.textContent = String(value || "—");

        row.append(labelElement, valueElement);
        details.appendChild(row);
      };

      addDetail("Modo", item?.mode);
      addDetail("Archivo", item?.file?.name);

      entry.append(header, details);

      if (fileExists && item?.file?.name) {
        const actions = document.createElement("div");
        actions.className = "history-entry-actions";

        const openButton = document.createElement("button");
        openButton.type = "button";
        openButton.className = "btn btn-secondary history-open-button";
        openButton.textContent = "Abrir hoja";
        openButton.addEventListener("click", () => {
          void openHistoryOutput(String(item.file.name));
        });

        actions.appendChild(openButton);
        entry.appendChild(actions);
      }

      list.appendChild(entry);
    }

    dom.logsContent.appendChild(list);
  }

  function setPreviewContent(content = "") {
    if (!dom.previewContent) {
      return;
    }

    dom.previewContent.replaceChildren();

    if (content instanceof Node) {
      dom.previewContent.appendChild(content);
      return;
    }

    const message = document.createElement("p");
    message.className = "preview-message";
    message.textContent = String(content || "Vista previa no disponible.");

    dom.previewContent.appendChild(message);
  }

  function revokePreviewObjectUrl() {
    if (!previewObjectUrl) {
      return;
    }

    URL.revokeObjectURL(previewObjectUrl);
    previewObjectUrl = null;
  }

  function updatePreviewState() {
    if (!dom.openPreviewButton) {
      return;
    }

    const available = Boolean(
      state.backend.ready &&
        state.backend.previewEnabled &&
        state.backend.latestOutput?.exists,
    );

    dom.openPreviewButton.disabled = !available;
    dom.openPreviewButton.title = available
      ? `Vista previa de ${state.backend.latestOutput?.name || "la hoja generada"}`
      : "Disponible después de generar una hoja de parámetros en esta sesión";
  }

  function formatFileSize(sizeBytes) {
    const bytes = Number(sizeBytes || 0);
    if (!Number.isFinite(bytes) || bytes <= 0) {
      return "";
    }

    if (bytes < 1024) {
      return `${Math.round(bytes)} B`;
    }
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function previewBase64ToObjectUrl(base64, mimeType = "application/pdf") {
    const binary = window.atob(String(base64 || ""));
    const chunkSize = 1024 * 256;
    const chunks = [];

    for (let offset = 0; offset < binary.length; offset += chunkSize) {
      const slice = binary.slice(offset, offset + chunkSize);
      const bytes = new Uint8Array(slice.length);
      for (let index = 0; index < slice.length; index += 1) {
        bytes[index] = slice.charCodeAt(index);
      }
      chunks.push(bytes);
    }

    return URL.createObjectURL(new Blob(chunks, { type: mimeType }));
  }

  function renderPreviewPayload(payload = {}) {
    if (!dom.previewContent) {
      return;
    }

    const encoded = String(payload.base64 || "");
    if (!encoded) {
      throw new Error("Python no devolvió el documento de vista previa.");
    }

    revokePreviewObjectUrl();
    previewObjectUrl = previewBase64ToObjectUrl(
      encoded,
      String(payload.mimeType || "application/pdf"),
    );

    const wrapper = document.createElement("div");
    wrapper.className = "preview-document";

    const header = document.createElement("div");
    header.className = "preview-document-header";

    const identity = document.createElement("div");
    identity.className = "preview-document-identity";

    const fileName = document.createElement("strong");
    fileName.className = "preview-document-name";
    fileName.textContent = String(payload.name || "Hoja de parámetros");

    const metadata = document.createElement("span");
    metadata.className = "preview-document-meta";
    const metadataParts = [];
    if (payload.sheet) {
      metadataParts.push(`Hoja ${payload.sheet}`);
    }
    const sizeLabel = formatFileSize(payload.sizeBytes);
    if (sizeLabel) {
      metadataParts.push(sizeLabel);
    }
    metadata.textContent = metadataParts.join(" · ");

    identity.append(fileName, metadata);

    const badge = document.createElement("span");
    badge.className = "preview-session-badge";
    badge.textContent = "Sesión actual";

    header.append(identity, badge);

    const frame = document.createElement("iframe");
    frame.className = "preview-pdf-frame";
    frame.title = `Vista previa de ${payload.name || "la hoja de parámetros"}`;
    frame.src = `${previewObjectUrl}#toolbar=0&navpanes=0&view=FitH`;
    frame.loading = "eager";

    wrapper.append(header, frame);
    dom.previewContent.replaceChildren(wrapper);

    state.backend.previewLoaded = true;
    state.backend.previewName = String(payload.name || "");
  }

  function showPreviewLoading() {
    if (!dom.previewContent) {
      return;
    }

    const loading = document.createElement("div");
    loading.className = "preview-loading";
    loading.setAttribute("role", "status");
    loading.setAttribute("aria-live", "polite");

    const spinner = document.createElement("span");
    spinner.className = "preview-loading-spinner";
    spinner.setAttribute("aria-hidden", "true");

    const text = document.createElement("span");
    text.textContent = "Preparando vista previa…";

    loading.append(spinner, text);
    dom.previewContent.replaceChildren(loading);
  }

  /* -----------------------------------------------------------------------
   * Popup system
   * --------------------------------------------------------------------- */

  function clearPopupDynamicContent() {
    setText(dom.popupSecondaryMessage, "");
    setHidden(dom.popupSecondaryMessage, true);

    setHidden(dom.popupDetails, true);
    setText(dom.popupDetailsTitle, "Detalles");

    if (dom.popupDetailsContent) {
      dom.popupDetailsContent.replaceChildren();
    }

    setHidden(dom.popupMissingParams, true);
    setText(dom.popupMissingParamsCount, "0");

    if (dom.popupMissingParamsList) {
      dom.popupMissingParamsList.replaceChildren();
    }

    setHidden(dom.popupProgress, true);
    setPopupProgress(0, "Procesando...");

    if (dom.popupTechnicalDetails) {
      dom.popupTechnicalDetails.open = false;
    }

    setHidden(dom.popupTechnicalDetails, true);
    setText(dom.popupTechnicalText, "");
  }

  function renderPopupDetails(details, title = "Detalles") {
    if (!details || !dom.popupDetailsContent) {
      return;
    }

    setText(dom.popupDetailsTitle, title);
    dom.popupDetailsContent.replaceChildren();

    const entries = Array.isArray(details)
      ? details.map((value, index) => [String(index + 1), value])
      : Object.entries(details);

    for (const [label, value] of entries) {
      const row = document.createElement("div");
      row.className = "popup-detail-row";

      const labelElement = document.createElement("span");
      labelElement.className = "popup-detail-label";
      labelElement.textContent = String(label);

      const valueElement = document.createElement("span");
      valueElement.className = "popup-detail-value";
      valueElement.textContent = value == null ? "" : String(value);

      row.append(labelElement, valueElement);
      dom.popupDetailsContent.appendChild(row);
    }

    setHidden(dom.popupDetails, entries.length === 0);
  }

  function renderMissingParameters(parameters = []) {
    if (!Array.isArray(parameters) || !parameters.length) {
      setHidden(dom.popupMissingParams, true);
      return;
    }

    dom.popupMissingParamsList.replaceChildren();

    for (const parameter of parameters) {
      const item = document.createElement("li");
      item.textContent = String(parameter);
      dom.popupMissingParamsList.appendChild(item);
    }

    setText(dom.popupMissingParamsCount, String(parameters.length));

    setHidden(dom.popupMissingParams, false);
  }

  function configurePopupButton(button, config, fallbackText, action) {
    if (!button) {
      return;
    }

    if (config === false || config == null) {
      button.onclick = null;
      button.classList.remove("btn-danger");
      setHidden(button, true);
      return;
    }

    const buttonConfig = typeof config === "string" ? { text: config } : config;

    button.classList.toggle("btn-danger", Boolean(buttonConfig.danger));
    setText(button, buttonConfig.text || fallbackText);

    button.onclick = () => {
      if (typeof buttonConfig.onClick === "function") {
        buttonConfig.onClick();
      }

      closePopup(action);
    };

    setHidden(button, false);
  }

  function setPopupProgress(
    percent,
    text = "Procesando...",
    { indeterminate = false } = {},
  ) {
    const safePercent = clampPercent(percent);
    const isIndeterminate = Boolean(indeterminate);

    setText(dom.popupProgressText, text);
    setText(
      dom.popupProgressPercent,
      isIndeterminate ? "Procesando…" : `${Math.round(safePercent)}%`,
    );

    dom.popupProgress?.classList.toggle("is-indeterminate", isIndeterminate);

    if (dom.popupProgressBar) {
      dom.popupProgressBar.style.width = isIndeterminate ? "" : `${safePercent}%`;
    }

    if (dom.popupProgressTrack) {
      if (isIndeterminate) {
        dom.popupProgressTrack.removeAttribute("aria-valuenow");
        dom.popupProgressTrack.setAttribute("aria-valuetext", text);
      } else {
        dom.popupProgressTrack.setAttribute(
          "aria-valuenow",
          String(Math.round(safePercent)),
        );
        dom.popupProgressTrack.removeAttribute("aria-valuetext");
      }
    }
  }

  function showPopup({
    type = "info",
    title = "",
    message = "",
    secondaryMessage = "",
    details = null,
    detailsTitle = "Detalles",
    missingParameters = [],
    technicalDetails = "",
    progress = null,
    primaryButton = { text: "Aceptar" },
    secondaryButton = false,
    tertiaryButton = false,
    showCloseButton = true,
    closeOnOverlay = false,
  } = {}) {
    const popupType = POPUP_TYPES[type] || POPUP_TYPES.info;

    if (activePopupResolver) {
      activePopupResolver("replaced");
      activePopupResolver = null;
    }

    popupPreviousFocus =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;

    clearPopupDynamicContent();

    dom.popupDialog?.classList.remove(
      ...Object.keys(POPUP_TYPES).map((key) => `popup-${key}`),
    );
    dom.popupDialog?.classList.add(`popup-${type}`);

    setText(dom.popupIcon, popupType.icon);
    setText(dom.popupTypeLabel, popupType.label);
    setText(dom.popupTitle, title);
    setText(dom.popupMessage, message);

    if (secondaryMessage) {
      setText(dom.popupSecondaryMessage, secondaryMessage);
      setHidden(dom.popupSecondaryMessage, false);
    }

    if (details) {
      renderPopupDetails(details, detailsTitle);
    }

    renderMissingParameters(missingParameters);

    if (technicalDetails) {
      setText(dom.popupTechnicalText, technicalDetails);
      setHidden(dom.popupTechnicalDetails, false);
    }

    if (progress) {
      setPopupProgress(progress.percent ?? 0, progress.text || "Procesando...");
      setHidden(dom.popupProgress, false);
    }

    configurePopupButton(
      dom.popupPrimaryButton,
      primaryButton,
      "Aceptar",
      "primary",
    );

    configurePopupButton(
      dom.popupSecondaryButton,
      secondaryButton,
      "Cancelar",
      "secondary",
    );

    configurePopupButton(
      dom.popupTertiaryButton,
      tertiaryButton,
      "Opción",
      "tertiary",
    );

    setHidden(dom.popupCloseButton, !showCloseButton);

    dom.popupCloseButton.onclick = showCloseButton
      ? () => closePopup("close")
      : null;

    dom.popupOverlay.onclick = closeOnOverlay
      ? () => closePopup("overlay")
      : null;

    setHidden(dom.popupSection, false);
    dom.popupSection.setAttribute("aria-hidden", "false");

    window.setTimeout(() => {
      dom.popupDialog?.focus();
    }, 0);

    return new Promise((resolve) => {
      activePopupResolver = resolve;
    });
  }

  function closePopup(action = "close") {
    if (!dom.popupSection) {
      return;
    }

    setHidden(dom.popupSection, true);
    dom.popupSection.setAttribute("aria-hidden", "true");

    dom.popupCloseButton.onclick = null;
    dom.popupOverlay.onclick = null;
    dom.popupPrimaryButton.onclick = null;
    dom.popupSecondaryButton.onclick = null;
    dom.popupTertiaryButton.onclick = null;

    if (activePopupResolver) {
      activePopupResolver(action);
      activePopupResolver = null;
    }

    if (popupPreviousFocus?.focus) {
      popupPreviousFocus.focus();
    }

    popupPreviousFocus = null;
  }

  function showInfoPopup(title, message, options = {}) {
    return showPopup({
      ...options,
      type: "info",
      title,
      message,
    });
  }

  function showSuccessPopup(title, message, options = {}) {
    return showPopup({
      ...options,
      type: "success",
      title,
      message,
    });
  }

  function showWarningPopup(title, message, options = {}) {
    return showPopup({
      ...options,
      type: "warning",
      title,
      message,
    });
  }

  function showErrorPopup(title, message, options = {}) {
    return showPopup({
      ...options,
      type: "error",
      title,
      message,
    });
  }

  function showConfirmPopup(title, message, options = {}) {
    return showPopup({
      ...options,
      type: "confirm",
      title,
      message,
      primaryButton: options.primaryButton || { text: "Continuar" },
      secondaryButton: options.secondaryButton || { text: "Cancelar" },
    });
  }

  function showProcessingPopup(
    title,
    message,
    { percent = 0, progressText = "Procesando...", ...options } = {},
  ) {
    return showPopup({
      ...options,
      type: "processing",
      title,
      message,
      progress: {
        percent,
        text: progressText,
      },
      primaryButton: false,
      secondaryButton: false,
      tertiaryButton: false,
      showCloseButton: false,
      closeOnOverlay: false,
    });
  }

  /* -----------------------------------------------------------------------
   * PyWebView bridge - Pasos 6 a 10
   * --------------------------------------------------------------------- */

  let backendConnecting = false;
  let backendBootstrap = null;
  let manualSelectorsPayload = null;
  let bridgeTestPopupShown = false;
  let selectorsTestPopupShown = false;
  let filesTestInstructionsShown = false;
  let filesTestPopupShown = false;
  let generationTestInstructionsShown = false;
  let historyTestPopupShown = false;
  let previewTestInstructionsShown = false;
  let previewTestPopupShown = false;
  let genVTestInstructionsShown = false;
  let genIIITestInstructionsShown = false;

  function bridgeAvailable() {
    return Boolean(window.pywebview?.api);
  }

  function normalizeBridgeError(error) {
    if (!error) {
      return "Error desconocido del puente JavaScript ↔ Python.";
    }

    if (error instanceof Error) {
      return error.message || String(error);
    }

    if (typeof error === "object" && error.message) {
      return String(error.message);
    }

    return String(error);
  }

  function getBridgeStatus() {
    return {
      available: state.backend.available,
      ready: state.backend.ready,
      apiVersion: state.backend.apiVersion,
      renderer: state.backend.renderer,
      sessionId: state.backend.sessionId,
      pingOk: state.backend.pingOk,
      pythonSignalReceived: state.backend.pythonSignalReceived,
      manualSelectorsLoaded: state.backend.manualSelectorsLoaded,
      machineCount: state.backend.machineCount,
      injectionControlCount: state.backend.injectionControlCount,
      fileDialogsEnabled: state.backend.fileDialogsEnabled,
      dragDropBound: state.backend.dragDropBound,
      fileInputsEnabled: state.backend.fileInputsEnabled,
      generationEnabled: state.backend.generationEnabled,
      openOutputFolderEnabled: state.backend.openOutputFolderEnabled,
      openGeneratedOutputEnabled: state.backend.openGeneratedOutputEnabled,
      latestOutput: state.backend.latestOutput
        ? { ...state.backend.latestOutput }
        : null,
      historyEnabled: state.backend.historyEnabled,
      historyLoaded: state.backend.historyLoaded,
      historyCount: state.backend.historyCount,
      previewEnabled: state.backend.previewEnabled,
      previewLoaded: state.backend.previewLoaded,
      previewName: state.backend.previewName,
      lastGeneration: state.backend.lastGeneration
        ? { ...state.backend.lastGeneration }
        : null,
      inputFiles: {
        param: state.paramFile ? { ...state.paramFile } : null,
        resul: state.resulFile ? { ...state.resulFile } : null,
      },
      lastError: state.backend.lastError,
      bootstrap: backendBootstrap ? { ...backendBootstrap } : null,
      manualSelectors: manualSelectorsPayload
        ? {
            counts: { ...(manualSelectorsPayload.counts || {}) },
            source: { ...(manualSelectorsPayload.source || {}) },
          }
        : null,
    };
  }

  function maybeShowSelectorsTestSuccess() {
    if (
      selectorsTestPopupShown ||
      !backendBootstrap?.bridge?.selectorsTest ||
      !state.backend.ready ||
      !state.backend.manualSelectorsLoaded
    ) {
      return;
    }

    selectorsTestPopupShown = true;

    void showSuccessPopup(
      "Paso 7 completado",
      "Los selectores manuales se cargaron correctamente desde Python.",
      {
        details: {
          "Máquinas activas": String(state.backend.machineCount),
          "Controles de inyección": String(
            state.backend.injectionControlCount,
          ),
          "Fuente de máquinas":
            manualSelectorsPayload?.source?.machines || "Mapeo.xlsx",
          Hoja: manualSelectorsPayload?.source?.sheet || "Machines",
        },
        secondaryMessage:
          "Cierra este mensaje y verifica que puedas seleccionar una máquina y un modo de control de inyección.",
        primaryButton: { text: "Aceptar" },
      },
    );
  }

  async function loadManualSelectors() {
    if (!bridgeAvailable()) {
      return null;
    }

    if (dom.machineSelect) {
      dom.machineSelect.disabled = true;
    }

    if (dom.injectionControlSelect) {
      dom.injectionControlSelect.disabled = true;
    }

    try {
      const result = await window.pywebview.api.get_manual_selectors();

      if (!result?.ok) {
        throw new Error("Python no pudo cargar los selectores manuales.");
      }

      if (!Array.isArray(result.machines) || !result.machines.length) {
        throw new Error("Mapeo.xlsx no devolvió máquinas activas.");
      }

      if (
        !Array.isArray(result.injectionControls) ||
        !result.injectionControls.length
      ) {
        throw new Error(
          "No se recibieron opciones para el control de inyección.",
        );
      }

      setMachineOptions(result.machines);
      setInjectionControlOptions(result.injectionControls);

      manualSelectorsPayload = result;
      state.backend.manualSelectorsLoaded = true;
      state.backend.lastError = "";
      state.backend.machineCount = Number(result.counts?.machines || 0);
      state.backend.injectionControlCount = Number(
        result.counts?.injectionControls || 0,
      );

      if (dom.machineSelect) {
        dom.machineSelect.disabled = false;
      }

      if (dom.injectionControlSelect) {
        dom.injectionControlSelect.disabled = false;
      }

      emit("injectflow:manual-selectors-loaded", {
        machineCount: state.backend.machineCount,
        injectionControlCount: state.backend.injectionControlCount,
      });

      maybeShowSelectorsTestSuccess();
      return result;
    } catch (error) {
      const message = normalizeBridgeError(error);

      manualSelectorsPayload = null;
      state.backend.manualSelectorsLoaded = false;
      state.backend.machineCount = 0;
      state.backend.injectionControlCount = 0;
      state.backend.lastError = message;

      setMachineOptions([]);
      setInjectionControlOptions([]);

      if (dom.machineSelect) {
        dom.machineSelect.disabled = true;
      }

      if (dom.injectionControlSelect) {
        dom.injectionControlSelect.disabled = true;
      }

      console.error("InjectFlow selector load error:", error);

      emit("injectflow:manual-selectors-error", {
        message,
      });

      void showErrorPopup(
        "No se pudieron cargar los selectores",
        "InjectFlow no pudo leer la configuración de máquinas o los modos de control de inyección.",
        {
          secondaryMessage: message,
          technicalDetails: String(error?.stack || error || message),
          primaryButton: { text: "Aceptar" },
        },
      );

      return null;
    }
  }

  function fileKindLabel(kind) {
    return kind === "param" ? state.inputPolicy.paramDisplay : "Resul.csv";
  }

  function fileSourceLabel(source) {
    if (source === "drop") {
      return "Drag & Drop";
    }

    if (source === "dialog") {
      return "Selector de archivos";
    }

    return source || "N/D";
  }

  function showFileSelectionError(result, fallbackMessage = "") {
    const error = result?.error || {};

    void showErrorPopup(
      error.title || "No se pudo cargar el archivo",
      error.message || fallbackMessage || "El archivo seleccionado no es válido.",
      {
        technicalDetails: error.technical || "",
        primaryButton: { text: "Aceptar" },
      },
    );
  }

  function maybeShowFilesTestInstructions() {
    if (
      filesTestInstructionsShown ||
      !backendBootstrap?.bridge?.filesTest ||
      !state.backend.ready ||
      !state.backend.fileDialogsEnabled ||
      !state.backend.dragDropBound
    ) {
      return;
    }

    filesTestInstructionsShown = true;

    void showInfoPopup(
      "Validación del Paso 8",
      "Prueba los dos mecanismos de carga de archivos.",
      {
        secondaryMessage:
          "Selecciona uno de los archivos con el botón Subir archivo y arrastra el otro directamente a su zona. Puedes hacerlo en cualquier orden.",
        details: {
          "Param.dat": "Archivo con extensión .dat",
          "Resul.csv": "Archivo con extensión .csv",
          "Objetivo": "Validar selector nativo + Drag & Drop",
        },
        primaryButton: { text: "Comenzar prueba" },
      },
    );
  }

  function maybeShowFilesTestSuccess() {
    if (
      filesTestPopupShown ||
      !backendBootstrap?.bridge?.filesTest ||
      !state.paramFile ||
      !state.resulFile
    ) {
      return;
    }

    const sources = new Set([
      state.paramFile.source,
      state.resulFile.source,
    ]);

    if (!sources.has("dialog") || !sources.has("drop")) {
      return;
    }

    filesTestPopupShown = true;

    void showSuccessPopup(
      "Paso 8 completado",
      "La selección manual y el Drag & Drop funcionan correctamente.",
      {
        details: {
          "Param.dat": `${state.paramFile.name} · ${fileSourceLabel(state.paramFile.source)}`,
          "Resul.csv": `${state.resulFile.name} · ${fileSourceLabel(state.resulFile.source)}`,
          "Selector nativo": "OK",
          "Drag & Drop": "OK",
        },
        secondaryMessage:
          "Puedes quitar cualquiera de los dos archivos y volver a seleccionarlo. Resul.csv seguirá siendo opcional para la generación del Paso 9.",
        primaryButton: { text: "Aceptar" },
      },
    );
  }

  function applyFileSelection(result) {
    const kind = String(result?.kind || "").toLowerCase();

    if (!VALID_FILE_TYPES.includes(kind)) {
      return false;
    }

    if (result?.cancelled) {
      return false;
    }

    if (!result?.ok) {
      showFileSelectionError(
        result,
        `No se pudo cargar ${fileKindLabel(kind)}.`,
      );
      return false;
    }

    if (!result.file?.name || !result.file?.path) {
      showFileSelectionError(
        result,
        `Python no devolvió una ruta válida para ${fileKindLabel(kind)}.`,
      );
      return false;
    }

    setFile(kind, result.file);
    state.backend.lastError = "";

    emit("injectflow:file-selected", {
      kind,
      file: { ...result.file },
      source: result.file.source || "",
    });

    if (Number(result.ignoredCount || 0) > 0) {
      void showWarningPopup(
        "Se utilizó un solo archivo",
        `InjectFlow recibió varios archivos para ${fileKindLabel(kind)} y utilizó únicamente el primero.`,
        {
          secondaryMessage: `Archivos adicionales ignorados: ${Number(result.ignoredCount || 0)}`,
          primaryButton: { text: "Aceptar" },
        },
      );
    }

    maybeShowFilesTestSuccess();
    return true;
  }

  async function requestInputFile(kind) {
    if (state.machineSyncPending || state.machineSyncFailed ||
        (kind === "resul" && !state.inputPolicy.supportsResultants)) return null;
    if (!VALID_FILE_TYPES.includes(kind)) {
      throw new Error(`Tipo de archivo no válido: ${kind}`);
    }

    if (!bridgeAvailable() || !state.backend.ready) {
      void showErrorPopup(
        "Python no está disponible",
        "InjectFlow todavía no puede abrir el selector de archivos.",
        {
          primaryButton: { text: "Aceptar" },
        },
      );
      return null;
    }

    if (!state.backend.fileDialogsEnabled) {
      void showErrorPopup(
        "Selector no disponible",
        "La función de selección de archivos no está habilitada en esta versión del puente.",
        {
          primaryButton: { text: "Aceptar" },
        },
      );
      return null;
    }

    try {
      const result = await window.pywebview.api.select_input_file(kind);
      applyFileSelection(result);
      return result;
    } catch (error) {
      const message = normalizeBridgeError(error);
      state.backend.lastError = message;

      console.error("InjectFlow file dialog error:", error);

      void showErrorPopup(
        "No se pudo seleccionar el archivo",
        `Ocurrió un error al abrir ${fileKindLabel(kind)}.`,
        {
          secondaryMessage: message,
          technicalDetails: String(error?.stack || error || message),
          primaryButton: { text: "Aceptar" },
        },
      );

      return null;
    }
  }

  async function clearInputFile(kind) {
    if (!VALID_FILE_TYPES.includes(kind)) {
      throw new Error(`Tipo de archivo no válido: ${kind}`);
    }

    if (!bridgeAvailable() || !state.backend.ready) {
      setFile(kind, null);
      return null;
    }

    try {
      const result = await window.pywebview.api.clear_input_file(kind);

      if (!result?.ok) {
        throw new Error(`Python no pudo quitar ${fileKindLabel(kind)}.`);
      }

      setFile(kind, null);

      emit("injectflow:file-cleared", {
        kind,
      });

      return result;
    } catch (error) {
      const message = normalizeBridgeError(error);
      state.backend.lastError = message;

      void showErrorPopup(
        "No se pudo quitar el archivo",
        `Ocurrió un error al quitar ${fileKindLabel(kind)}.`,
        {
          secondaryMessage: message,
          technicalDetails: String(error?.stack || error || message),
          primaryButton: { text: "Aceptar" },
        },
      );

      return null;
    }
  }

  async function syncInputFiles() {
    if (!bridgeAvailable() || !state.backend.ready) {
      return null;
    }

    try {
      const result = await window.pywebview.api.get_input_files();

      if (!result?.ok) {
        return null;
      }

      if (result.policy) applyFamilyPresentation(result.policy);
      setFile("param", result.files?.param || null);
      setFile("resul", result.files?.resul || null);
      return result;
    } catch (error) {
      console.error("InjectFlow input file sync error:", error);
      return null;
    }
  }

  function receiveFileSelection(payload = {}) {
    applyFileSelection(payload);
  }

  function findInjectionControlCode(value) {
    const text = String(value || "");
    const options = manualSelectorsPayload?.injectionControls || [];
    const match = options.find(
      (item) =>
        String(item?.value ?? "") === text ||
        String(item?.label ?? "") === text ||
        String(item?.code ?? "") === text,
    );

    return match ? Number(match.code) : null;
  }

  function generationMissingParameters() {
    const missing = [];

    if (!state.paramFile?.path) {
      missing.push(state.inputPolicy.paramDisplay);
    }
    if (!state.machine) {
      missing.push("Máquina");
    }
    if (!state.mold) {
      missing.push("Molde");
    }
    if (state.inputPolicy.requiresInjectionControl && !state.injectionControl) {
      missing.push("Control de inyección");
    }
    if (state.machineSyncPending || state.machineSyncFailed) {
      missing.push("Confirmar seleccion de maquina");
    }

    return missing;
  }

  function setGenerationBusy(busy) {
    const active = Boolean(busy);

    state.generation.active = active;

    if (dom.machineSelect) {
      dom.machineSelect.disabled = active || !state.backend.manualSelectorsLoaded;
    }

    if (dom.moldInput) {
      dom.moldInput.disabled = active;
    }

    if (dom.injectionControlSelect) {
      dom.injectionControlSelect.disabled =
        active || !state.backend.manualSelectorsLoaded || !state.inputPolicy.requiresInjectionControl;
    }

    setFileControlsEnabled(
      !active &&
        (state.backend.fileDialogsEnabled || state.backend.dragDropBound),
    );

    updateGenerateState();
  }

  function receiveGenerationProgress(payload = {}) {
    const percent = Number(payload?.percent || 0);
    const message = String(payload?.message || "Procesando…");
    const indeterminate = Boolean(payload?.indeterminate);

    setGenerationProgress(percent, message, {
      visible: true,
      indeterminate,
    });
    setPopupProgress(percent, message, { indeterminate });
  }

  function updateOpenSheetState() {
    if (!dom.openSheetButton) {
      return;
    }

    const available = Boolean(
      state.backend.ready &&
        state.backend.openGeneratedOutputEnabled &&
        state.backend.latestOutput?.exists,
    );

    dom.openSheetButton.disabled = !available;

    if (available) {
      const name = String(state.backend.latestOutput?.name || "").trim();
      dom.openSheetButton.title = name
        ? `Abrir ${name}`
        : "Abrir la hoja de parámetros generada en esta sesión";
    } else {
      dom.openSheetButton.title =
        "Disponible después de generar una hoja de parámetros en esta sesión";
    }
  }

  async function syncLatestOutput() {
    if (
      !bridgeAvailable() ||
      !state.backend.ready ||
      !state.backend.openGeneratedOutputEnabled
    ) {
      state.backend.latestOutput = null;
      updateOpenSheetState();
      updatePreviewState();
      return null;
    }

    try {
      const result = await window.pywebview.api.get_latest_output();

      if (!result?.ok) {
        throw new Error(
          result?.error?.message || "No se pudo consultar la última hoja generada.",
        );
      }

      state.backend.latestOutput = result?.available && result?.output
        ? { ...result.output }
        : null;
      updateOpenSheetState();
      updatePreviewState();
      return result;
    } catch (error) {
      state.backend.latestOutput = null;
      updateOpenSheetState();
      updatePreviewState();
      state.backend.lastError = normalizeBridgeError(error);
      return null;
    }
  }

  async function openGeneratedOutput() {
    if (
      !bridgeAvailable() ||
      !state.backend.ready ||
      !state.backend.openGeneratedOutputEnabled
    ) {
      void showErrorPopup(
        "Hoja no disponible",
        "InjectFlow todavía no puede abrir la hoja generada.",
        { primaryButton: { text: "Aceptar" } },
      );
      return null;
    }

    try {
      const result = await window.pywebview.api.open_latest_output();

      if (!result?.ok) {
        const error = result?.error || {};
        throw new Error(error.message || "No se pudo abrir la hoja generada.");
      }

      state.backend.latestOutput = {
        name: String(result.name || ""),
        path: String(result.path || ""),
        exists: true,
        source: String(result.source || ""),
      };
      updateOpenSheetState();

      emit("injectflow:generated-output-opened", {
        output: { ...state.backend.latestOutput },
      });

      return result;
    } catch (error) {
      const message = normalizeBridgeError(error);
      state.backend.lastError = message;

      // La hoja pudo haberse movido/eliminado después de habilitar el botón.
      await syncLatestOutput();

      void showErrorPopup(
        "No se pudo abrir la hoja",
        message,
        {
          technicalDetails: String(error?.stack || error || message),
          primaryButton: { text: "Aceptar" },
        },
      );
      return null;
    }
  }


  function maybeShowGenVTestInstructions() {
    if (
      genVTestInstructionsShown ||
      !backendBootstrap?.bridge?.genVTest ||
      !state.backend.generationEnabled
    ) {
      return;
    }

    genVTestInstructionsShown = true;

    void showInfoPopup(
      "Validación del Paso 12 - Haitian Zeres Gen V",
      "Genera una hoja real utilizando una máquina Haitian Zeres Gen V.",
      {
        secondaryMessage:
          "Utiliza archivos reales de una de las máquinas Gen V y revisa después la hoja generada y su Vista previa.",
        details: {
          "Máquinas Gen V": "112C, 114B, 114C, 124A, 125A, 126A, 129, 130",
          "Plantilla esperada": "Haitian Zeres Gen V.xlsx",
          "Layout": "NAVE1_V1",
          "Prueba recomendada": "Con Resul.csv si está disponible",
        },
        primaryButton: { text: "Comenzar prueba" },
      },
    );
  }

  function maybeShowGenIIITestInstructions() {
    if (
      genIIITestInstructionsShown ||
      !backendBootstrap?.bridge?.genIIITest ||
      !state.backend.generationEnabled
    ) {
      return;
    }

    genIIITestInstructionsShown = true;

    void showInfoPopup(
      "Validación del Paso 13 - Haitian Zeres Gen III",
      "Genera una hoja real utilizando una máquina Haitian Zeres Gen III.",
      {
        secondaryMessage:
          "Para esta familia se recomienda validar primero el flujo Solo Param.dat y revisar después la hoja generada y su Vista previa.",
        details: {
          "Máquinas Gen III": "101B, 102B, 103A, 104B, 105A, 106B, 107C, 108C, 111B, 111C, 113C, 115B, 116C, 117B, 123B, 127, 128, 131",
          "Plantilla esperada": "Haitian Zeres Gen III_500.xlsx",
          "Layout": "ZERES_GENIII_V1",
          "Prueba recomendada": "Solo Param.dat",
        },
        primaryButton: { text: "Comenzar prueba" },
      },
    );
  }

  function maybeShowPreviewTestInstructions() {
    if (
      previewTestInstructionsShown ||
      !backendBootstrap?.bridge?.previewTest ||
      !state.backend.previewEnabled
    ) {
      return;
    }

    previewTestInstructionsShown = true;

    void showInfoPopup(
      "Validación del Paso 11",
      "Genera una hoja de parámetros en esta sesión y después abre Vista previa.",
      {
        secondaryMessage:
          "La vista previa debe mostrarse dentro de InjectFlow y no debe habilitarse con hojas de sesiones anteriores.",
        details: {
          "Origen permitido": "Solo sesión actual",
          "Formato de vista previa": "PDF temporal",
          "Archivo original": "No se modifica",
        },
        primaryButton: { text: "Comenzar prueba" },
      },
    );
  }

  function maybeShowPreviewTestSuccess(payload = {}) {
    if (
      previewTestPopupShown ||
      !backendBootstrap?.bridge?.previewTest ||
      !state.backend.previewLoaded
    ) {
      return;
    }

    previewTestPopupShown = true;

    void showSuccessPopup(
      "Paso 11 completado",
      "La Vista Previa real se cargó correctamente dentro de InjectFlow.",
      {
        details: {
          Archivo: String(payload.name || state.backend.previewName || "N/D"),
          Hoja: String(payload.sheet || "N/D"),
          Tamaño: formatFileSize(payload.sizeBytes) || "N/D",
          Origen: "Sesión actual",
        },
        secondaryMessage:
          "Verifica visualmente que el formato, combinaciones y contenido coincidan con la hoja generada.",
        primaryButton: { text: "Aceptar" },
      },
    );
  }

  async function loadCurrentPreview({ manual = false } = {}) {
    if (
      !bridgeAvailable() ||
      !state.backend.ready ||
      !state.backend.previewEnabled ||
      !state.backend.latestOutput?.exists
    ) {
      setPreviewContent(
        "Genera una hoja de parámetros en esta sesión antes de abrir la vista previa.",
      );
      return null;
    }

    if (previewLoadActive) {
      if (manual) {
        previewReloadQueued = true;
      }
      return null;
    }

    previewLoadActive = true;
    previewReloadQueued = false;

    state.backend.previewLoaded = false;
    state.backend.previewName = "";
    showPreviewLoading();

    try {
      const result = await window.pywebview.api.get_current_preview();
      if (!result?.ok || !result?.available || !result?.preview) {
        const error = result?.error || {};
        throw new Error(error.message || "No se pudo crear la vista previa.");
      }

      renderPreviewPayload(result.preview);
      state.backend.lastError = "";

      emit("injectflow:preview-loaded", {
        name: String(result.preview?.name || ""),
        cached: Boolean(result.cached),
      });

      maybeShowPreviewTestSuccess(result.preview);
      return result;
    } catch (error) {
      const message = normalizeBridgeError(error);
      state.backend.lastError = message;
      state.backend.previewLoaded = false;
      state.backend.previewName = "";

      setPreviewContent(
        "Vista previa no disponible. Presiona Refresh para volver a intentar.",
      );
      return null;
    } finally {
      previewLoadActive = false;

      if (previewReloadQueued && state.currentScreen === "preview") {
        previewReloadQueued = false;
        window.setTimeout(() => {
          void loadCurrentPreview();
        }, 100);
      }
    }
  }

  async function openOutputFolder() {
    if (
      !bridgeAvailable() ||
      !state.backend.ready ||
      !state.backend.openOutputFolderEnabled
    ) {
      void showErrorPopup(
        "Carpeta no disponible",
        "InjectFlow todavía no puede abrir la carpeta de salida.",
        { primaryButton: { text: "Aceptar" } },
      );
      return null;
    }

    try {
      const result = await window.pywebview.api.open_output_folder();

      if (!result?.ok) {
        const error = result?.error || {};
        throw new Error(error.message || "No se pudo abrir la carpeta de salida.");
      }

      return result;
    } catch (error) {
      const message = normalizeBridgeError(error);
      state.backend.lastError = message;

      void showErrorPopup(
        "No se pudo abrir la carpeta",
        message,
        {
          technicalDetails: String(error?.stack || error || message),
          primaryButton: { text: "Aceptar" },
        },
      );
      return null;
    }
  }

  function maybeShowHistoryTestSuccess(payload = {}) {
    if (
      historyTestPopupShown ||
      !backendBootstrap?.bridge?.historyTest ||
      !state.backend.historyEnabled ||
      !payload?.ok
    ) {
      return;
    }

    historyTestPopupShown = true;

    const cleanupWarning = String(payload?.cleanupWarning || "");
    const options = {
      details: {
        "Registros cargados": Number(payload?.count || 0),
        "Retención": `${Number(payload?.retentionDays || 90)} días`,
        "Fuente": "data/Historial.csv",
        "Orden": "Más reciente primero",
      },
      technicalDetails: cleanupWarning,
      primaryButton: { text: "Aceptar" },
    };

    if (cleanupWarning) {
      void showWarningPopup(
        "Paso 10 cargado con advertencia",
        "El historial se mostró, pero la limpieza automática requiere revisión.",
        options,
      );
    } else {
      void showSuccessPopup(
        "Paso 10 completado",
        "El historial real de generaciones se cargó correctamente en InjectFlow.",
        options,
      );
    }
  }

  async function loadHistory({ showErrors = true } = {}) {
    if (!bridgeAvailable() || !state.backend.ready || !state.backend.historyEnabled) {
      const message = "El historial todavía no está disponible en esta sesión.";
      renderLogs([message]);

      if (showErrors) {
        void showErrorPopup("Historial no disponible", message, {
          primaryButton: { text: "Aceptar" },
        });
      }
      return null;
    }

    if (dom.clearHistoryButton) {
      dom.clearHistoryButton.disabled = true;
    }

    if (dom.logsContent) {
      dom.logsContent.replaceChildren();
      const loading = document.createElement("p");
      loading.className = "empty-state history-loading-state";
      loading.textContent = "Cargando historial de generación…";
      dom.logsContent.appendChild(loading);
    }

    try {
      const result = await window.pywebview.api.get_history();

      if (!result?.ok) {
        const error = result?.error || {};
        throw new Error(error.message || "No se pudo leer Historial.csv.");
      }

      state.backend.historyLoaded = true;
      state.backend.historyCount = Number(result.count || 0);
      renderHistory(result);
      maybeShowHistoryTestSuccess(result);

      emit("injectflow:history-loaded", {
        count: state.backend.historyCount,
        retentionDays: Number(result.retentionDays || 90),
      });

      return result;
    } catch (error) {
      const message = normalizeBridgeError(error);
      state.backend.historyLoaded = false;
      state.backend.lastError = message;
      renderLogs([`No se pudo cargar el historial: ${message}`]);

      if (showErrors) {
        void showErrorPopup("No se pudo cargar el historial", message, {
          technicalDetails: String(error?.stack || error || message),
          primaryButton: { text: "Aceptar" },
        });
      }
      return null;
    }
  }

  async function openHistoryOutput(fileName) {
    if (!bridgeAvailable() || !state.backend.ready || !state.backend.historyEnabled) {
      return null;
    }

    try {
      const result = await window.pywebview.api.open_history_output(fileName);
      if (!result?.ok) {
        const error = result?.error || {};
        throw new Error(error.message || "No se pudo abrir la hoja del historial.");
      }
      return result;
    } catch (error) {
      const message = normalizeBridgeError(error);
      state.backend.lastError = message;

      void showWarningPopup("Archivo no disponible", message, {
        technicalDetails: String(error?.stack || error || message),
        primaryButton: { text: "Aceptar" },
      });
      return null;
    }
  }

  async function requestClearHistory() {
    if (!bridgeAvailable() || !state.backend.ready || !state.backend.historyEnabled) {
      return null;
    }

    const currentCount = Number(state.backend.historyCount || 0);
    if (currentCount <= 0) {
      return null;
    }

    const action = await showConfirmPopup(
      "Borrar todo el historial",
      "¿Estás seguro de que deseas borrar todo el historial de generación?",
      {
        secondaryMessage:
          "Esta acción eliminará únicamente los registros del historial. Las hojas Excel generadas permanecerán en la carpeta output.",
        details: {
          "Registros a borrar": currentCount,
          "Archivos Excel": "No se eliminarán",
        },
        primaryButton: {
          text: "Borrar historial",
          danger: true,
        },
        secondaryButton: { text: "Cancelar" },
      },
    );

    if (action !== "primary") {
      return null;
    }

    if (dom.clearHistoryButton) {
      dom.clearHistoryButton.disabled = true;
    }

    try {
      const result = await window.pywebview.api.clear_history();
      if (!result?.ok) {
        const error = result?.error || {};
        throw new Error(error.message || "No se pudo borrar el historial.");
      }

      state.backend.historyLoaded = true;
      state.backend.historyCount = 0;

      await loadHistory({ showErrors: false });

      void showSuccessPopup(
        "Historial borrado",
        "Se eliminaron todos los registros del historial correctamente.",
        {
          secondaryMessage:
            "Las hojas de parámetros generadas no fueron eliminadas de la carpeta output.",
          primaryButton: { text: "Aceptar" },
        },
      );

      emit("injectflow:history-cleared", {
        removedCount: Number(result.removedCount || currentCount),
      });

      return result;
    } catch (error) {
      const message = normalizeBridgeError(error);
      state.backend.lastError = message;

      void showErrorPopup("No se pudo borrar el historial", message, {
        technicalDetails: String(error?.stack || error || message),
        primaryButton: { text: "Aceptar" },
      });

      if (dom.clearHistoryButton) {
        dom.clearHistoryButton.disabled = state.backend.historyCount <= 0;
      }

      return null;
    }
  }

  function maybeShowGenerationTestInstructions() {
    if (
      generationTestInstructionsShown ||
      !backendBootstrap?.bridge?.generationTest ||
      !state.backend.generationEnabled
    ) {
      return;
    }

    generationTestInstructionsShown = true;

    void showInfoPopup(
      "Validación del Paso 9",
      "Genera una hoja real con los mismos archivos que utilizabas en la versión 1.3.",
      {
        secondaryMessage:
          "Prueba primero un caso representativo. Si no cargas Resul.csv, InjectFlow utilizará automáticamente el modo Solo Param.dat.",
        details: {
          "Param.dat": "Obligatorio",
          "Resul.csv": "Opcional",
          "Sin Resul.csv": "Solo Param.dat",
          "Con Resul.csv": "Parámetros + Resultantes",
          "Motor": "app.main.run() de la base validada",
        },
        primaryButton: { text: "Comenzar prueba" },
      },
    );
  }

  async function requestGeneration() {
    if (!bridgeAvailable() || !state.backend.ready) {
      void showErrorPopup(
        "Python no está disponible",
        "InjectFlow todavía no puede ejecutar la generación.",
        { primaryButton: { text: "Aceptar" } },
      );
      return null;
    }

    if (!state.backend.generationEnabled) {
      void showErrorPopup(
        "Generación no disponible",
        "La capacidad de generación no está habilitada en esta versión del puente.",
        { primaryButton: { text: "Aceptar" } },
      );
      return null;
    }

    const missing = generationMissingParameters();
    if (missing.length) {
      void showWarningPopup(
        "Faltan datos para generar",
        "Completa la información obligatoria antes de generar la hoja.",
        {
          missingParameters: missing,
          primaryButton: { text: "Aceptar" },
        },
      );
      return null;
    }

    const injectionCode = findInjectionControlCode(state.injectionControl);
    if (state.inputPolicy.requiresInjectionControl &&
        (!Number.isInteger(injectionCode) || ![0, 1].includes(injectionCode))) {
      void showErrorPopup(
        "Control de inyección inválido",
        "No se pudo traducir el modo de control de inyección seleccionado.",
        { primaryButton: { text: "Aceptar" } },
      );
      return null;
    }

    const mode = generationModeLabel();
    setGenerationBusy(true);
    setGenerationProgress(
      4,
      `Preparando generación (${mode})…`,
      { visible: true },
    );

    void showProcessingPopup(
      "Generando hoja de parámetros",
      "InjectFlow está procesando la información y generando la hoja de parámetros.",
      {
        percent: 4,
        progressText: `Preparando generación (${mode})…`,
        secondaryMessage: "Mantén InjectFlow abierto mientras se completa la generación.",
      },
    );

    try {
      const result = await window.pywebview.api.generate_sheet({
        machine: state.machine,
        mold: state.mold,
        injectionControl: state.injectionControl,
        injectionControlCode: injectionCode,
      });

      closePopup("generation-finished");

      if (!result?.ok || !result?.generated) {
        const error = result?.error || {};
        const status = String(result?.status || "error");
        const popup = status === "warning" ? showWarningPopup : showErrorPopup;

        setText(
          dom.generationStatus,
          status === "warning"
            ? "La generación fue detenida por una advertencia de configuración."
            : "No se pudo generar la hoja de parámetros.",
        );

        void popup(
          error.title || "No se pudo generar la hoja",
          error.message || "El motor de generación devolvió un error.",
          {
            missingParameters: result?.missingParameters || [],
            technicalDetails: error.technical || "",
            primaryButton: { text: "Aceptar" },
          },
        );

        return result;
      }

      state.backend.historyLoaded = false;
      state.backend.lastGeneration = {
        status: result.status || "success",
        mode: result.mode || mode,
        machine: result.machine || state.machine,
        mold: result.mold || state.mold,
        outputName: result.output?.name || "",
        outputPath: result.output?.path || "",
        warningCount: Number(result.warningCount || 0),
      };
      state.backend.latestOutput = result.output?.exists
        ? {
            name: String(result.output?.name || ""),
            path: String(result.output?.path || ""),
            exists: true,
            source: "session",
          }
        : null;
      revokePreviewObjectUrl();
      state.backend.previewLoaded = false;
      state.backend.previewName = "";
      setPreviewContent();
      updateOpenSheetState();
      updatePreviewState();

      const processWarnings = Array.isArray(result.processWarnings)
        ? result.processWarnings
        : [];
      const parameterWarnings = Array.isArray(result.parameterWarnings)
        ? result.parameterWarnings
        : [];
      const generationWarnings = [...processWarnings, ...parameterWarnings];
      const historyWarning = String(result.history?.warning || "");
      const hasWarnings = generationWarnings.length > 0 || Boolean(historyWarning);

      setGenerationProgress(
        100,
        hasWarnings
          ? `Hoja generada con advertencias: ${result.output?.name || "archivo generado"}`
          : `Hoja generada correctamente: ${result.output?.name || "archivo generado"}`,
        { visible: true },
      );

      const details = {
        "Archivo": result.output?.name || "N/D",
        "Modo": result.mode || mode,
        "Máquina": result.machine || state.machine,
        "Molde": result.mold || state.mold,
        "Control de inyección": result.injectionControl?.label || state.injectionControl,
        "Plantilla": result.template?.file || "N/D",
        "Grupo": result.template?.group || "N/D",
        "Operaciones": result.plan?.operations ?? "N/D",
        "Celdas verificadas": result.verification?.checkedCells ?? "N/D",
      };

      const commonOptions = {
        details,
        technicalDetails: historyWarning || "",
        tertiaryButton: state.backend.openOutputFolderEnabled
          ? {
              text: "Abrir carpeta",
              onClick: () => {
                void openOutputFolder();
              },
            }
          : false,
        secondaryButton:
          state.backend.openGeneratedOutputEnabled && state.backend.latestOutput?.exists
            ? {
                text: "Abrir hoja",
                onClick: () => {
                  void openGeneratedOutput();
                },
              }
            : false,
        primaryButton: { text: "Aceptar" },
      };

      const genVTest = Boolean(backendBootstrap?.bridge?.genVTest);
      const genIIITest = Boolean(backendBootstrap?.bridge?.genIIITest);
      const templateGroup = String(result.template?.group || "");
      const isGenV = templateGroup === "HAITIAN_ZE_V";
      const isGenIII = templateGroup === "HAITIAN_ZE_III";

      if (genVTest && !isGenV) {
        void showWarningPopup(
          "Prueba Gen V no válida",
          "La hoja se generó correctamente, pero la máquina seleccionada no pertenece a Haitian Zeres Gen V.",
          {
            ...commonOptions,
            secondaryMessage:
              "Repite la prueba con 112C, 114B, 114C, 124A, 125A, 126A, 129 o 130.",
          },
        );
      } else if (genIIITest && !isGenIII) {
        void showWarningPopup(
          "Prueba Gen III no válida",
          "La hoja se generó correctamente, pero la máquina seleccionada no pertenece a Haitian Zeres Gen III.",
          {
            ...commonOptions,
            secondaryMessage:
              "Repite la prueba con una máquina Gen III: 101B, 102B, 103A, 104B, 105A, 106B, 107C, 108C, 111B, 111C, 113C, 115B, 116C, 117B, 123B, 127, 128 o 131.",
          },
        );
      } else if (hasWarnings) {
        void showWarningPopup(
          genVTest
            ? "Paso 12 completado con advertencias"
            : genIIITest
              ? "Paso 13 completado con advertencias"
              : backendBootstrap?.bridge?.generationTest
                ? "Paso 9 completado con advertencias"
                : "Hoja generada con advertencias",
          "La hoja fue generada y verificada, pero existen advertencias que conviene revisar.",
          {
            ...commonOptions,
            secondaryMessage: historyWarning || "La generación continuó con los datos disponibles.",
            missingParameters: generationWarnings,
          },
        );
      } else {
        void showSuccessPopup(
          genVTest
            ? "Paso 12 completado"
            : genIIITest
              ? "Paso 13 completado"
              : backendBootstrap?.bridge?.generationTest
                ? "Paso 9 completado"
                : "Hoja generada correctamente",
          genVTest
            ? "La generación real de Haitian Zeres Gen V terminó y fue verificada correctamente."
            : genIIITest
              ? "La generación real de Haitian Zeres Gen III terminó y fue verificada correctamente."
              : "La hoja de parámetros fue generada y verificada correctamente.",
          {
            ...commonOptions,
            secondaryMessage: genVTest
              ? "Revisa visualmente la hoja y la Vista previa antes de cerrar la validación Gen V."
              : genIIITest
                ? "Revisa visualmente SuckBack, Noyo/Core, HRS, Valve Gates y la Vista previa antes de cerrar la validación Gen III."
                : commonOptions.secondaryMessage,
          },
        );
      }

      emit("injectflow:generation-completed", {
        result,
      });

      return result;
    } catch (error) {
      closePopup("generation-error");

      const message = normalizeBridgeError(error);
      state.backend.lastError = message;
      setText(dom.generationStatus, "No se pudo generar la hoja de parámetros.");

      void showErrorPopup(
        "No se pudo generar la hoja",
        message,
        {
          technicalDetails: String(error?.stack || error || message),
          primaryButton: { text: "Aceptar" },
        },
      );

      return null;
    } finally {
      setGenerationBusy(false);
      updateGenerateState();
    }
  }

  function maybeShowBridgeTestSuccess() {
    if (
      bridgeTestPopupShown ||
      !backendBootstrap?.bridge?.testMode ||
      !state.backend.ready ||
      !state.backend.pingOk ||
      !state.backend.pythonSignalReceived
    ) {
      return;
    }

    bridgeTestPopupShown = true;

    void showSuccessPopup(
      "Paso 6 completado",
      "La comunicación bidireccional JavaScript ↔ Python está funcionando correctamente.",
      {
        details: {
          "API del puente": state.backend.apiVersion || "N/D",
          Renderer: state.backend.renderer || "N/D",
          "JS → Python": "OK",
          "Python → JS": "OK",
        },
        primaryButton: { text: "Aceptar" },
      },
    );
  }

  async function pingBackend(payload = {}) {
    if (!bridgeAvailable()) {
      return {
        ok: false,
        reply: "unavailable",
      };
    }

    const result = await window.pywebview.api.ping(payload);
    state.backend.pingOk = Boolean(result?.ok && result?.reply === "pong");
    maybeShowBridgeTestSuccess();
    return result;
  }

  async function connectBackend() {
    if (state.backend.ready) {
      return backendBootstrap;
    }

    if (backendConnecting) {
      return null;
    }

    if (!bridgeAvailable()) {
      state.backend.available = false;
      return null;
    }

    // Se marca antes de init() para evitar un handshake duplicado si
    // pywebviewready ocurre antes de DOMContentLoaded.
    backendConnecting = true;

    if (!initialized) {
      init();
    }

    state.backend.available = true;
    state.backend.lastError = "";

    try {
      const client = {
        app: APP.name,
        version: APP.version,
        screen: state.currentScreen,
        userAgent: navigator.userAgent,
      };

      const bootstrap = await window.pywebview.api.bootstrap(client);

      if (!bootstrap?.ok) {
        throw new Error("Python rechazó el handshake inicial.");
      }

      backendBootstrap = bootstrap;
      state.backend.ready = true;
      state.backend.apiVersion = String(bootstrap.bridge?.apiVersion || "");
      state.backend.renderer = String(bootstrap.bridge?.renderer || "");
      state.backend.sessionId = String(bootstrap.bridge?.sessionId || "");
      state.backend.fileDialogsEnabled = Boolean(
        bootstrap.capabilities?.file_dialogs,
      );
      state.backend.generationEnabled = Boolean(
        bootstrap.capabilities?.generation,
      );
      state.backend.openOutputFolderEnabled = Boolean(
        bootstrap.capabilities?.open_output_folder,
      );
      state.backend.openGeneratedOutputEnabled = Boolean(
        bootstrap.capabilities?.open_generated_output,
      );
      state.backend.previewEnabled = Boolean(bootstrap.capabilities?.preview);
      state.backend.historyEnabled = Boolean(bootstrap.capabilities?.history);
      state.backend.dragDropBound = Boolean(
        bootstrap.bridge?.dragDropBound || state.backend.dragDropBound,
      );
      setFileControlsEnabled(
        state.backend.fileDialogsEnabled || state.backend.dragDropBound,
      );
      if (dom.openFolderButton) {
        dom.openFolderButton.disabled = !state.backend.openOutputFolderEnabled;
      }
      updateOpenSheetState();
      updatePreviewState();
      if (dom.openLogsButton) {
        dom.openLogsButton.disabled = !state.backend.historyEnabled;
      }

      if (bootstrap.app) {
        setAppMetadata({
          version: bootstrap.app.version || APP.version,
          year: bootstrap.app.year || APP.year,
        });
      }

      await window.pywebview.api.notify_ui_ready({
        screen: state.currentScreen,
        app: APP.name,
        version: APP.version,
      });

      if (bootstrap.capabilities?.manual_selectors) {
        await loadManualSelectors();
      }

      if (bootstrap.capabilities?.file_dialogs || bootstrap.capabilities?.drag_drop) {
        await syncInputFiles();
      }

      await pingBackend({
        source: "javascript",
        action: "step6-handshake",
      });

      emit("injectflow:backend-ready", {
        bootstrap,
      });

      updateGenerateState();
      maybeShowBridgeTestSuccess();
      maybeShowFilesTestInstructions();
      maybeShowGenerationTestInstructions();
      maybeShowPreviewTestInstructions();
      maybeShowGenVTestInstructions();
      maybeShowGenIIITestInstructions();
      return bootstrap;
    } catch (error) {
      const message = normalizeBridgeError(error);

      state.backend.ready = false;
      state.backend.lastError = message;

      console.error("InjectFlow bridge error:", error);

      emit("injectflow:backend-error", {
        message,
      });

      return null;
    } finally {
      backendConnecting = false;
    }
  }

  function receivePythonSignal(payload = {}) {
    state.backend.available = true;
    state.backend.pythonSignalReceived = true;

    if (payload?.renderer) {
      state.backend.renderer = String(payload.renderer);
    }

    if (payload?.apiVersion) {
      state.backend.apiVersion = String(payload.apiVersion);
    }

    if (typeof payload?.dragDropBound === "boolean") {
      state.backend.dragDropBound = payload.dragDropBound;
      setFileControlsEnabled(
        state.backend.fileDialogsEnabled || state.backend.dragDropBound,
      );
    }

    if (payload?.dragDropError) {
      state.backend.lastError = String(payload.dragDropError);
    }

    emit("injectflow:python-signal", {
      ...payload,
    });

    maybeShowBridgeTestSuccess();
    maybeShowSelectorsTestSuccess();
    maybeShowFilesTestInstructions();
    maybeShowGenerationTestInstructions();
    maybeShowPreviewTestInstructions();
    maybeShowGenVTestInstructions();
    maybeShowGenIIITestInstructions();
  }

  window.InjectFlowBridge = Object.freeze({
    connect: connectBackend,
    ping: pingBackend,
    loadManualSelectors,
    requestInputFile,
    clearInputFile,
    syncInputFiles,
    requestGeneration,
    syncLatestOutput,
    openGeneratedOutput,
    loadCurrentPreview,
    openOutputFolder,
    loadHistory,
    openHistoryOutput,
    getStatus: getBridgeStatus,
    receivePythonSignal,
    receiveFileSelection,
    receiveGenerationProgress,
  });

  window.addEventListener(
    "pywebviewready",
    () => {
      void connectBackend();
    },
    { once: true },
  );

  /* -----------------------------------------------------------------------
   * Events
   * --------------------------------------------------------------------- */

  function bindDropZoneActivation(element, eventName) {
    if (!element) {
      return;
    }

    element.addEventListener("click", () => {
      emit(eventName);
    });

    element.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        emit(eventName);
      }
    });
  }

  function bindDropZoneVisuals(element) {
    if (!element) {
      return;
    }

    element.addEventListener("dragenter", (event) => {
      event.preventDefault();
      element.classList.add("drag-over");
    });

    element.addEventListener("dragover", (event) => {
      event.preventDefault();
      element.classList.add("drag-over");
    });

    element.addEventListener("dragleave", (event) => {
      const nextTarget = event.relatedTarget;

      if (!(nextTarget instanceof Node) || !element.contains(nextTarget)) {
        element.classList.remove("drag-over");
      }
    });

    element.addEventListener("drop", (event) => {
      event.preventDefault();
      element.classList.remove("drag-over");
    });
  }

  function bindEvents() {
    dom.paramUploadButton?.addEventListener("click", () => {
      emit("injectflow:param-upload-requested");
      void requestInputFile("param");
    });

    dom.paramRemoveButton?.addEventListener("click", () => {
      emit("injectflow:param-remove-requested");
      void clearInputFile("param");
    });

    dom.resulUploadButton?.addEventListener("click", () => {
      emit("injectflow:resul-upload-requested");
      void requestInputFile("resul");
    });

    dom.resulRemoveButton?.addEventListener("click", () => {
      emit("injectflow:resul-remove-requested");
      void clearInputFile("resul");
    });

    bindDropZoneActivation(
      dom.paramDropZone,
      "injectflow:param-upload-requested",
    );

    bindDropZoneActivation(
      dom.resulDropZone,
      "injectflow:resul-upload-requested",
    );

    bindDropZoneVisuals(dom.paramDropZone);
    bindDropZoneVisuals(dom.resulDropZone);

    dom.paramDropZone?.addEventListener("click", () => {
      void requestInputFile("param");
    });

    dom.paramDropZone?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        void requestInputFile("param");
      }
    });

    dom.resulDropZone?.addEventListener("click", () => {
      void requestInputFile("resul");
    });

    dom.resulDropZone?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        void requestInputFile("resul");
      }
    });

    dom.machineSelect?.addEventListener("change", (event) => {
      void setMachine(event.target.value || "");

      emit("injectflow:machine-changed", {
        machine: state.machine,
      });
    });

    dom.moldInput?.addEventListener("input", (event) => {
      state.mold = event.target.value.trim();
      updateSummary();
      updateGenerateState();

      emit("injectflow:mold-changed", {
        mold: state.mold,
      });
    });

    dom.injectionControlSelect?.addEventListener("change", (event) => {
      state.injectionControl = event.target.value || "";
      updateSummary();
      updateGenerateState();

      emit("injectflow:injection-control-changed", {
        injectionControl: state.injectionControl,
      });
    });

    dom.generateButton?.addEventListener("click", () => {
      emit("injectflow:generate-requested", {
        state: getState(),
      });
      void requestGeneration();
    });

    dom.openPreviewButton?.addEventListener("click", () => {
      if (dom.openPreviewButton.disabled) {
        return;
      }

      showScreen("preview");

      emit("injectflow:preview-opened");
      void loadCurrentPreview();
    });

    dom.refreshPreviewButton?.addEventListener("click", () => {
      emit("injectflow:preview-refresh-requested");
      void loadCurrentPreview({ manual: true });
    });

    dom.returnPreviewButton?.addEventListener("click", () => {
      showScreen("home");
    });

    dom.openSheetButton?.addEventListener("click", () => {
      emit("injectflow:generated-output-open-requested");
      void openGeneratedOutput();
    });

    dom.openLogsButton?.addEventListener("click", () => {
      showScreen("logs");

      emit("injectflow:logs-opened");
      void loadHistory();
    });

    dom.clearHistoryButton?.addEventListener("click", () => {
      emit("injectflow:history-clear-requested", {
        count: state.backend.historyCount,
      });
      void requestClearHistory();
    });

    dom.returnButton?.addEventListener("click", () => {
      showScreen("home");
    });

    dom.openFolderButton?.addEventListener("click", () => {
      emit("injectflow:open-folder-requested");
      void openOutputFolder();
    });

    document.addEventListener("keydown", (event) => {
      if (
        event.key === "Escape" &&
        dom.popupSection &&
        !dom.popupSection.classList.contains("hidden") &&
        !dom.popupCloseButton.classList.contains("hidden")
      ) {
        closePopup("escape");
      }
    });
  }

  /* -----------------------------------------------------------------------
   * Initialization
   * --------------------------------------------------------------------- */

  /**
   * Inicializa la capa visual de la aplicación.
   *
   * Este punto centraliza el registro de elementos del DOM, configuraciones
   * iniciales, suscripciones a eventos y renderizados base del flujo principal.
   */
  function init() {
    if (initialized) {
      return;
    }

    cacheDom();
    setAppMetadata();
    setFileControlsEnabled(false);
    setGenerateEnabled(false);

    if (dom.openSheetButton) {
      dom.openSheetButton.disabled = true;
      dom.openSheetButton.title =
        "Disponible después de generar una hoja de parámetros";
    }

    if (dom.openPreviewButton) {
      dom.openPreviewButton.disabled = true;
      dom.openPreviewButton.title =
        "Disponible después de generar una hoja de parámetros en esta sesión";
    }

    if (dom.openFolderButton) {
      dom.openFolderButton.disabled = true;
    }

    if (dom.openLogsButton) {
      dom.openLogsButton.disabled = true;
    }

    if (dom.machineSelect) {
      dom.machineSelect.disabled = true;
    }

    if (dom.injectionControlSelect) {
      dom.injectionControlSelect.disabled = true;
    }

    bindEvents();
    updateSummary();
    renderLogs([]);
    setPreviewContent();
    hideGenerationProgress({
      clearStatus: true,
    });
    showScreen("home");

    initialized = true;

    emit("injectflow:ui-ready", {
      app: {
        ...APP,
      },
    });

    // Fallback: si pywebviewready ocurrió antes de DOMContentLoaded, conecta aquí.
    if (bridgeAvailable() && !state.backend.ready) {
      void connectBackend();
    }
  }

/**
 * API pública de la capa visual.
 *
 * Se expone al entorno global para que futuras integraciones con Python o
 * servicios del sistema puedan reutilizar la UI sin depender de la estructura
 * interna del documento HTML.
 *
 * @namespace InjectFlowUI
 */
  window.InjectFlowUI = Object.freeze({
    init,
    getState,

    showScreen,

    setAppMetadata,

    setFile,
    setFileStatus,
    setFileControlsEnabled,

    setMachineOptions,
    setInjectionControlOptions,
    setMachine,
    setMold,
    setInjectionControl,

    setHomeControlsEnabled,
    setGenerateEnabled,

    updateSummary,
    updateGenerateState,

    setGenerationProgress,
    hideGenerationProgress,

    renderLogs,
    renderHistory,
    loadHistory,
    requestClearHistory,
    setPreviewContent,

    showPopup,
    closePopup,
    showInfoPopup,
    showSuccessPopup,
    showWarningPopup,
    showErrorPopup,
    showConfirmPopup,
    showProcessingPopup,
    setPopupProgress,
  });

  document.addEventListener("DOMContentLoaded", init);
})();
