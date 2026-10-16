"use strict";

(() => {
  const metadata = document.getElementById("qbe-fields");
  if (!metadata) return;
  const fields = JSON.parse(metadata.textContent);
  const labels = JSON.parse(document.getElementById("qbe-widget-labels").textContent);

  function initializeExplorer() {
    const dataElement = document.getElementById("qbe-explorer-data");
    const enhanced = document.querySelector(".qbe-explorer-enhanced");
    if (!dataElement || !enhanced) return;
    const data = JSON.parse(dataElement.textContent);
    const feedback = document.getElementById("qbe-explorer-feedback");
    const svg = enhanced.querySelector("svg");
    const svgNamespace = "http://www.w3.org/2000/svg";
    const makeSvg = (name, attributes, text) => {
      const element = document.createElementNS(svgNamespace, name);
      for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
      if (text !== undefined) element.textContent = text;
      return element;
    };

    function drawDiagram() {
      svg.replaceChildren();
      const depth = new Map([[data.root_id, 0]]);
      for (let pass = 0; pass < data.nodes.length; pass += 1) {
        for (const edge of data.edges) {
          if (depth.has(edge.source_id) && !depth.has(edge.target_id)) {
            depth.set(edge.target_id, depth.get(edge.source_id) + 1);
          }
        }
      }
      const rows = new Map();
      const positions = new Map();
      for (const node of data.nodes) {
        const column = depth.get(node.id) || 0;
        const row = rows.get(column) || 0;
        rows.set(column, row + 1);
        positions.set(node.id, {x: 30 + column * 400, y: 35 + row * 110});
      }
      const width = Math.max(240, ...[...depth.values()].map(value => 240 + value * 400));
      const height = Math.max(120, ...[...rows.values()].map(value => 50 + value * 110));
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
      svg.setAttribute("width", String(width));
      svg.setAttribute("height", String(height));
      svg.append(makeSvg("title", {}, "Registered model relationships"));
      svg.append(makeSvg("desc", {}, "An authorized diagram of registered model paths. Full paths appear in the field list."));

      const edgeGroups = new Map();
      for (const edge of data.edges) {
        const key = `${edge.source_id}|${edge.target_id}`;
        if (!edgeGroups.has(key)) edgeGroups.set(key, []);
        edgeGroups.get(key).push(edge.id);
      }
      const edgeIndexes = new Map();
      for (const edge of data.edges) {
        const source = positions.get(edge.source_id);
        const target = positions.get(edge.target_id);
        if (!source || !target) continue;
        const key = `${edge.source_id}|${edge.target_id}`;
        const siblings = edgeGroups.get(key);
        const edgeIndex = edgeIndexes.get(key) || 0;
        edgeIndexes.set(key, edgeIndex + 1);
        const offset = (edgeIndex - (siblings.length - 1) / 2) * 32;
        const x1 = source.x + 190;
        const y1 = source.y + 28;
        const x2 = target.x;
        const y2 = target.y + 28;
        svg.append(makeSvg("path", {
          d: `M ${x1} ${y1} C ${x1 + 45} ${y1 + offset}, ${x2 - 45} ${y2 + offset}, ${x2} ${y2}`,
          class: "qbe-explorer-edge",
          "marker-end": "url(#qbe-explorer-arrow)"
        }));
        svg.append(makeSvg("text", {
          x: String((x1 + x2) / 2),
          y: String((y1 + y2) / 2 + offset - 8),
          class: "qbe-explorer-edge-label",
          "text-anchor": "middle"
        }, `${edge.label} (${edge.reverse ? "reverse" : "forward"}; ${edge.multi_valued ? "many" : "one"})`));
      }

      const defs = makeSvg("defs", {});
      const marker = makeSvg("marker", {id: "qbe-explorer-arrow", viewBox: "0 0 10 10", refX: "8", refY: "5", markerWidth: "6", markerHeight: "6", orient: "auto-start-reverse"});
      marker.append(makeSvg("path", {d: "M 0 0 L 10 5 L 0 10 z", class: "qbe-explorer-arrow"}));
      defs.append(marker);
      svg.prepend(defs);

      for (const node of data.nodes) {
        const position = positions.get(node.id);
        const group = makeSvg("g", {class: `qbe-explorer-node${node.is_root ? " is-root" : ""}`});
        group.append(makeSvg("rect", {x: String(position.x), y: String(position.y), width: "190", height: "56", rx: "5"}));
        group.append(makeSvg("text", {x: String(position.x + 10), y: String(position.y + 23), class: "qbe-explorer-node-label"}, node.label));
        group.append(makeSvg("text", {x: String(position.x + 10), y: String(position.y + 42), class: "qbe-explorer-node-id"}, node.id));
        svg.append(group);
      }
    }

    function announce(message) {
      feedback.textContent = message;
    }

    enhanced.hidden = false;
    document.querySelectorAll(".qbe-explorer-actions").forEach(actions => { actions.hidden = false; });
    document.querySelectorAll("[data-explorer-action]").forEach(button => {
      const action = button.dataset.explorerAction;
      if (action === "column" && !document.querySelector('input[name="columns"]')) button.hidden = true;
      if (action === "group" && !document.querySelector('input[name="group_by"]')) button.hidden = true;
    });
    drawDiagram();

    enhanced.querySelector("#qbe-explorer-search").addEventListener("input", event => {
      const search = event.currentTarget.value.trim().toLowerCase();
      document.querySelectorAll("[data-explorer-field]").forEach(item => {
        const searchable = `${item.dataset.fieldPath} ${item.querySelector("span").textContent}`.toLowerCase();
        item.hidden = !searchable.includes(search);
      });
    });

    document.querySelectorAll("[data-explorer-action]").forEach(button => {
      button.addEventListener("click", () => {
        const path = button.dataset.fieldPath;
        const action = button.dataset.explorerAction;
        if (action === "column" || action === "group") {
          const name = action === "column" ? "columns" : "group_by";
          const control = [...document.querySelectorAll(`input[name="${name}"]`)].find(item => item.value === path);
          if (!control) {
            announce(action === "column" ? "Columns are available in Rows mode." : "Apply Summary report type before adding a grouping field.");
            document.getElementById("id_mode")?.focus();
            return;
          }
          control.checked = true;
          control.dispatchEvent(new Event("change", {bubbles: true}));
          announce(`${path} added to ${action === "column" ? "columns" : "summary grouping"}.`);
          return;
        }

        const row = [...document.querySelectorAll(".qbe-filter-row")].find(item => {
          const select = item.querySelector('select[name$="-field"]');
          const deleted = item.querySelector('input[name$="-DELETE"]');
          return select && !select.value && !deleted?.checked;
        });
        const select = row?.querySelector('select[name$="-field"]');
        if (!select) {
          announce("Add a condition row first, then choose this field.");
          document.querySelector('button[name^="action"][value^="add_condition"]')?.focus();
          return;
        }
        if (![...select.options].some(option => option.value === path)) {
          announce("This field is not available in the current report.");
          return;
        }
        select.value = path;
        select.dispatchEvent(new Event("change", {bubbles: true}));
        announce(`${path} selected as a filter field.`);
      });
    });
  }

  initializeExplorer();

  function updateValue(row) {
    const path = row.querySelector('[name$="-field"]').value;
    const operator = row.querySelector('[name$="-operator"]');
    if (!operator) return;
    const current = row.querySelector('[name$="-value"]');
    const booleanOptions = [{value: "true", label: labels.true}, {value: "false", label: labels.false}];
    let options = null;
    if (operator.value === "isnull") {
      options = booleanOptions;
    } else if (["exact", "iexact"].includes(operator.value) && fields[path]?.choices_declared) {
      options = fields[path].choices;
    } else if (fields[path]?.boolean) {
      options = booleanOptions;
    }
    const replacement = document.createElement(options !== null ? "select" : "input");
    for (const attribute of ["name", "id", "aria-describedby", "aria-invalid"]) {
      if (current.hasAttribute(attribute)) replacement.setAttribute(attribute, current.getAttribute(attribute));
    }
    if (options !== null) {
      if (!options.some(item => item.value === "")) replacement.append(new Option(labels.choose, ""));
      replacement.append(...options.map(item => new Option(item.label, item.value)));
    } else {
      replacement.type = "text";
    }
    replacement.value = current.value;
    const focused = document.activeElement === current;
    current.replaceWith(replacement);
    if (focused) replacement.focus();
  }

  function wireRow(row) {
    const field = row.querySelector('[name$="-field"]');
    const operator = row.querySelector('[name$="-operator"]');
    if (operator) {
      const updateOperators = () => {
        const previous = operator.value;
        operator.replaceChildren(...(fields[field.value]?.operators || []).map(
          item => new Option(item.label, item.value)
        ));
        if ([...operator.options].some(option => option.value === previous)) operator.value = previous;
        updateValue(row);
      };
      field.addEventListener("change", updateOperators);
      operator.addEventListener("change", () => updateValue(row));
      if (field.value) updateOperators();
    }
    const remove = row.querySelector('[name$="-DELETE"]');
    remove.addEventListener("change", () => row.classList.toggle("qbe-row-deleted", remove.checked));
  }

  document.querySelectorAll("#filter-rows .qbe-row, #ordering-rows .qbe-row, #metric-rows .qbe-row, #summary-ordering-rows .qbe-row").forEach(wireRow);
  const groupElements = [...document.querySelectorAll(".qbe-condition-group")];
  const groupMap = new Map(groupElements.map(element => [element.dataset.group, element]));
  groupElements.forEach(element => {
    const controls = element.querySelector(":scope > .qbe-group-controls");
    const parent = controls?.querySelector('[name$="-parent"]');
    parent?.addEventListener("change", () => {
      const target = groupMap.get(parent.value);
      if (target && target !== element && !element.contains(target)) {
        target.querySelector(":scope > .qbe-group-children").append(element);
        parent.focus();
      }
    });
    const remove = controls?.querySelector('input[type="checkbox"][name$="-DELETE"]');
    remove?.addEventListener("change", () => element.classList.toggle("qbe-row-deleted", remove.checked));
  });
  document.querySelectorAll(".qbe-filter-row").forEach(row => {
    const group = row.querySelector('[name$="-group"]');
    group?.addEventListener("change", () => {
      const target = groupMap.get(group.value);
      if (target) {
        target.querySelector(":scope > .qbe-group-filters").append(row);
        group.focus();
      }
    });
  });
  document.querySelectorAll(".qbe-add-row").forEach(button => {
    const prefix = button.dataset.prefix;
    if (prefix === "metrics") return;
    const total = document.getElementById(`id_${prefix}-TOTAL_FORMS`);
    const maximum = Number(document.getElementById(`id_${prefix}-MAX_NUM_FORMS`).value);
    const containers = {filters: "filter-rows", ordering: "ordering-rows", metrics: "metric-rows"};
    const container = document.getElementById(containers[prefix]);
    button.hidden = false;
    button.disabled = Number(total.value) >= maximum;
    button.addEventListener("click", () => {
      const index = Number(total.value);
      if (index >= maximum) return;
      const fragment = document.getElementById(`${prefix}-empty-form`).content.cloneNode(true);
      fragment.querySelectorAll("*").forEach(element => {
        for (const attribute of ["id", "name", "for", "aria-describedby"]) {
          if (element.hasAttribute(attribute)) {
            element.setAttribute(attribute, element.getAttribute(attribute).replaceAll("__prefix__", String(index)));
          }
        }
      });
      const row = fragment.querySelector(".qbe-row");
      container.append(fragment);
      wireRow(row);
      total.value = String(index + 1);
      button.disabled = Number(total.value) >= maximum;
      document.getElementById("qbe-feedback").textContent = button.dataset.addedMessage;
      row.querySelector("select").focus();
    });
  });
})();
