const API = "/api/studio/worlds";
let selectedPackage = null;
let selectedCollection = null;

function element(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children) node.append(child);
  return node;
}

function closeModal() {
  document.querySelector(".world-portability-backdrop")?.remove();
}

function modal(title, content, actions = []) {
  closeModal();
  const actionRow = element("div", { class: "world-portability-actions" });
  actions.forEach(({ label, primary, action }) => actionRow.append(element("button", {
    class: primary ? "world-portability-primary" : "", text: label, onclick: action,
  })));
  const dialog = element("section", { class: "world-portability-modal", role: "dialog", "aria-modal": "true", "aria-label": title }, [
    element("span", { class: "world-portability-eyebrow", text: "ARCHON / PORTABLE WORLD" }),
    element("h2", { text: title }), content, actionRow,
  ]);
  const backdrop = element("div", { class: "world-portability-backdrop", onclick: (event) => { if (event.target === backdrop) closeModal(); } }, [dialog]);
  document.body.append(backdrop);
  dialog.querySelector("button")?.focus();
}

function details(rows) {
  const list = element("dl", { class: "world-portability-details" });
  rows.forEach(([label, value]) => {
    const row = element("div");
    row.append(element("dt", { text: label }), element("dd", { text: value || "Not recorded" }));
    list.append(row);
  });
  return list;
}

function showError(message) {
  modal("World package rejected", element("p", { class: "world-portability-error", text: message || "The package is invalid." }), [
    { label: "Close", primary: true, action: closeModal },
  ]);
}

function openWorld(ruleId) {
  closeModal();
  const worlds = [...document.querySelectorAll("nav button")].find((button) => button.textContent.trim() === "Worlds");
  worlds?.click();
  setTimeout(() => {
    const card = [...document.querySelectorAll(".world-card")].find((item) => item.textContent.includes(`Rule ${ruleId}`));
    card?.click();
  }, 800);
}

function openWorldAtlas() {
  closeModal();
  const worlds = [...document.querySelectorAll("nav button")].find((button) => button.textContent.trim() === "Worlds");
  worlds?.click();
}

async function inspectPackage(file) {
  selectedPackage = await file.arrayBuffer();
  modal("Inspecting World", element("p", { text: "Validating package structure, checksums and scientific identity…" }));
  let response;
  let payload;
  try {
    response = await fetch(`${API}/import/inspect`, { method: "POST", headers: { "Content-Type": "application/vnd.archon.world+zip" }, body: selectedPackage });
    payload = await response.json();
  } catch (error) {
    showError(`Could not inspect the local package: ${error.message}`);
    return;
  }
  if (!response.ok || ["INVALID", "UNSUPPORTED_VERSION"].includes(payload.status)) {
    showError(payload.error || "The package is not compatible with this ARCHON release.");
    return;
  }
  const body = element("div");
  if (payload.preview_base64) {
    body.append(element("img", { class: "world-portability-preview", src: `data:${payload.preview_media_type};base64,${payload.preview_base64}`, alt: "Portable World preview" }));
  }
  body.append(details([
    ["Original ID", `Rule ${payload.original_rule_id}`],
    ["World UID", payload.world_uid],
    ["Source", payload.source_archon_version ? `ARCHON ${payload.source_archon_version}` : "ARCHON version not recorded"],
  ]));
  if (payload.status === "ALREADY_EXISTS") {
    body.append(element("div", { class: "world-portability-state", text: `World already exists · Local ID: Rule ${payload.existing_local_rule_id}` }));
    modal("World already exists", body, [
      { label: "Cancel", action: closeModal },
      { label: "Open World", primary: true, action: () => openWorld(payload.existing_local_rule_id) },
    ]);
    return;
  }
  body.append(element("div", { class: "world-portability-state", text: `New World · Will be assigned local ID: Rule ${payload.prospective_local_rule_id}` }));
  modal("Import World", body, [
    { label: "Cancel", action: closeModal },
    { label: "Import", primary: true, action: importSelected },
  ]);
}

async function importSelected() {
  if (!selectedPackage) return;
  modal("Importing World", element("p", { text: "Committing the validated World to the canonical Atlas…" }));
  try {
    const response = await fetch(`${API}/import`, { method: "POST", headers: { "Content-Type": "application/vnd.archon.world+zip" }, body: selectedPackage });
    const payload = await response.json();
    if (!response.ok || ["INVALID", "UNSUPPORTED_VERSION"].includes(payload.status)) {
      showError(payload.error);
      return;
    }
    const localId = payload.local_rule_id || payload.existing_local_rule_id;
    const body = element("div", {}, [
      element("p", { text: payload.status === "IMPORTED" ? "The World is now part of this installation's canonical Atlas." : "This World was already present." }),
      details([["Local ID", `Rule ${localId}`], ["World UID", payload.world_uid]]),
    ]);
    modal(payload.status === "IMPORTED" ? "World imported" : "World already exists", body, [
      { label: "Close", action: closeModal },
      { label: "Open World", primary: true, action: () => openWorld(localId) },
    ]);
  } catch (error) {
    showError(`Import failed safely: ${error.message}`);
  }
}

function choosePackage() {
  const input = element("input", { type: "file", accept: ".archon-world,application/vnd.archon.world+zip" });
  input.hidden = true;
  input.addEventListener("change", () => input.files?.[0] && inspectPackage(input.files[0]));
  document.body.append(input);
  input.click();
  setTimeout(() => input.remove(), 60000);
}

function collectionWorldList(worlds) {
  const list = element("div", { class: "world-portability-collection-list" });
  worlds.slice(0, 100).forEach((world) => {
    const destination = world.status === "ALREADY_EXISTS"
      ? `Existing Rule ${world.existing_local_rule_id}`
      : `New Rule ${world.prospective_local_rule_id || world.local_rule_id}`;
    list.append(element("div", { class: "world-portability-collection-row" }, [
      element("span", { text: `Rule ${world.original_rule_id}` }),
      element("span", { text: destination }),
      element("small", { text: world.world_uid }),
    ]));
  });
  if (worlds.length > 100) {
    list.append(element("p", { text: `…and ${worlds.length - 100} more Worlds` }));
  }
  return list;
}

async function inspectWorldCollection(file) {
  selectedCollection = file;
  modal("Inspecting World collection", element("p", { text: "Validating every embedded World, checksum and scientific identity without changing the Atlas…" }));
  try {
    const response = await fetch(`${API}/import-all/inspect`, {
      method: "POST", headers: { "Content-Type": "application/vnd.archon.world-collection+zip" }, body: selectedCollection,
    });
    const payload = await response.json();
    if (!response.ok || ["INVALID", "UNSUPPORTED_VERSION"].includes(payload.status)) {
      showError(payload.error || "The World collection is not compatible with this ARCHON release.");
      return;
    }
    const body = element("div", {}, [
      details([
        ["Worlds", String(payload.world_count)],
        ["New", String(payload.new_count)],
        ["Already present", String(payload.existing_count)],
        ["Source", payload.source_archon_version ? `ARCHON ${payload.source_archon_version}` : "ARCHON version not recorded"],
      ]),
      collectionWorldList(payload.worlds || []),
    ]);
    if (payload.status === "ALREADY_EXISTS") {
      body.append(element("div", { class: "world-portability-state", text: "Every World in this collection already exists locally. Nothing will be changed." }));
      modal("World collection already imported", body, [
        { label: "Close", action: closeModal },
        { label: "Open Worlds", primary: true, action: openWorldAtlas },
      ]);
      return;
    }
    body.append(element("div", { class: "world-portability-state", text: `${payload.new_count} new World${payload.new_count === 1 ? "" : "s"} will be committed together. ${payload.existing_count} duplicate${payload.existing_count === 1 ? "" : "s"} will be skipped.` }));
    modal("Import World collection", body, [
      { label: "Cancel", action: closeModal },
      { label: "Import collection", primary: true, action: importSelectedCollection },
    ]);
  } catch (error) {
    showError(`Could not inspect the local collection: ${error.message}`);
  }
}

async function importSelectedCollection() {
  if (!selectedCollection) return;
  modal("Importing World collection", element("p", { text: "Committing all new Worlds to the canonical Atlas as one transaction…" }));
  try {
    const response = await fetch(`${API}/import-all`, {
      method: "POST", headers: { "Content-Type": "application/vnd.archon.world-collection+zip" }, body: selectedCollection,
    });
    const payload = await response.json();
    if (!response.ok || ["INVALID", "UNSUPPORTED_VERSION"].includes(payload.status)) {
      showError(payload.error || "The collection was rejected without changing the Atlas.");
      return;
    }
    const body = element("div", {}, [
      element("p", { text: payload.status === "IMPORTED_COLLECTION" ? "The collection was committed to this installation's canonical Atlas." : "Every World was already present." }),
      details([
        ["Imported", String(payload.imported_count || 0)],
        ["Already present", String(payload.existing_count || 0)],
        ["Total", String(payload.world_count || 0)],
      ]),
      collectionWorldList(payload.worlds || []),
    ]);
    modal(payload.status === "IMPORTED_COLLECTION" ? "World collection imported" : "World collection already imported", body, [
      { label: "Close", action: closeModal },
      { label: "Open Worlds", primary: true, action: openWorldAtlas },
    ]);
  } catch (error) {
    showError(`Collection import failed safely: ${error.message}`);
  }
}

function chooseWorldCollection() {
  const input = element("input", { type: "file", accept: ".archon-worlds,application/vnd.archon.world-collection+zip" });
  input.hidden = true;
  input.addEventListener("change", () => input.files?.[0] && inspectWorldCollection(input.files[0]));
  document.body.append(input);
  input.click();
  setTimeout(() => input.remove(), 60000);
}

function installGlobalAction() {
  if (document.querySelector("#archon-world-import-action")) return;
  document.body.append(element("button", {
    id: "archon-world-import-action", class: "world-portability-import", text: "⇩  Import World", onclick: choosePackage,
    title: "Import a local .archon-world package",
  }));
}

function exportAllWorlds() {
  window.location.assign(`${API}/export-all`);
}

function installSettingsAction() {
  const heading = [...document.querySelectorAll("main h1")].find((node) => node.textContent.trim() === "Settings");
  const page = heading?.closest("main");
  if (!page || page.querySelector("#archon-world-export-all")) return;
  const panel = element("section", { id: "archon-world-export-all", class: "panel world-portability-settings-panel" }, [
    element("div", { class: "world-portability-settings-copy" }, [
      element("span", { class: "world-portability-eyebrow", text: "PORTABLE WORLD LIBRARY" }),
      element("h2", { text: "Import or export all Worlds" }),
      element("p", { text: "Transfer every distinct canonical Atlas World in one portable collection. Imports are validated first and committed atomically; duplicates are skipped. Results, observations, settings and machine-specific paths are not included." }),
    ]),
    element("div", { class: "world-portability-settings-actions" }, [
      element("button", { class: "world-portability-import-all", text: "⇩  Import World Collection", onclick: chooseWorldCollection }),
      element("button", { class: "world-portability-export-all", text: "⇧  Export All Worlds", onclick: exportAllWorlds }),
    ]),
  ]);
  const firstPanel = page.querySelector(".panel");
  if (firstPanel) firstPanel.before(panel);
  else page.append(panel);
}

async function installDetailAction() {
  const back = [...document.querySelectorAll(".back-link")].find((node) => node.textContent.includes("Back to World Atlas"));
  if (!back) return;
  const page = back.closest("main");
  const heading = page?.querySelector(".object-heading");
  if (!heading || heading.querySelector(".world-portability-export")) return;
  const match = page.textContent.match(/Rule\s+(\d{1,})\s+·\s+generation/);
  if (!match) return;
  const ruleId = match[1].padStart(5, "0");
  let uid = null;
  try {
    const snapshot = await fetch("/studio/snapshot.json", { cache: "no-store" }).then((response) => response.json());
    uid = snapshot.worlds?.find((world) => world.rule_id === ruleId)?.world_uid || null;
  } catch (_) {}
  const actionBox = element("div", { class: "world-portability-detail-action" });
  if (uid) actionBox.append(element("small", { text: uid }));
  actionBox.append(element("button", {
    class: "world-portability-export", text: "⇧  Export World", onclick: () => { window.location.assign(`${API}/${ruleId}/export`); },
  }));
  heading.append(actionBox);
}

installGlobalAction();
const observer = new MutationObserver(() => { installGlobalAction(); installDetailAction(); installSettingsAction(); });
observer.observe(document.documentElement, { childList: true, subtree: true });
installDetailAction();
installSettingsAction();
