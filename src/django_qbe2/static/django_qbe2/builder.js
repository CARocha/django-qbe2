"use strict";

(() => {
  const metadata = document.getElementById("qbe-fields");
  if (!metadata) return;
  const fields = JSON.parse(metadata.textContent);
  const labels = JSON.parse(document.getElementById("qbe-widget-labels").textContent);

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
    const containers = {filters: "filter-rows", ordering: "ordering-rows", metrics: "metric-rows", summary_ordering: "summary-ordering-rows"};
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
