(() => {
    "use strict";

    const ANALYSIS_TAB_ID = "analysis-tab";
    const ANALYSIS_CONTENT_ID = "analysis-content";

    function makeElement(tag, className, text) {
        const element = document.createElement(tag);
        if (className) {
            element.className = className;
        }
        if (text !== undefined && text !== null) {
            element.textContent = String(text);
        }
        return element;
    }

    function appendDefinition(container, label, value, options = {}) {
        if (value === undefined || value === null || value === "") {
            return null;
        }
        const row = makeElement("div", "analysis-definition");
        row.appendChild(makeElement("span", "analysis-definition-label", label));
        const valueElement = makeElement(
            options.code ? "code" : "span",
            "analysis-definition-value",
            value,
        );
        row.appendChild(valueElement);
        container.appendChild(row);
        return row;
    }

    function appendCodeBlock(container, value, className = "") {
        if (value === undefined || value === null || value === "") {
            return null;
        }
        const pre = makeElement("pre", `analysis-code ${className}`.trim());
        pre.appendChild(makeElement("code", "", value));
        container.appendChild(pre);
        return pre;
    }

    function priorityClass(priority) {
        return ["low", "medium", "high"].includes(priority) ? priority : "low";
    }

    const PRIORITY_RANK = { none: 0, low: 1, medium: 2, high: 3 };

    function priorityRank(priority) {
        return PRIORITY_RANK[priority] || 0;
    }

    // Highest review priority across an action's findings ("none" when it has none).
    function actionPriority(action) {
        let best = "none";
        for (const finding of action.findings || []) {
            const priority = priorityClass(finding.review_priority);
            if (priorityRank(priority) > priorityRank(best)) {
                best = priority;
            }
        }
        return best;
    }

    // Distinct review priorities present across an action's findings, so a card can
    // be matched by ANY priority it contains, not only its single highest one.
    function actionPriorities(action) {
        const present = new Set();
        for (const finding of action.findings || []) {
            present.add(priorityClass(finding.review_priority));
        }
        return present;
    }

    function actionIsScript(action) {
        const kind = (action.type && action.type.kind) || "";
        return kind === "jscript" || kind === "vbscript";
    }

    // Deferred custom actions read their command line from CustomActionData, so the
    // presence of that cross-reference is a reliable signal; fall back to scanning the
    // decoded type flags/capabilities for deferred/rollback/commit scheduling.
    function actionIsDeferred(action) {
        if (action.custom_action_data && action.custom_action_data.length) {
            return true;
        }
        const type = action.type || {};
        const tokens = []
            .concat(type.flags || [], type.capabilities || [])
            .join(" ")
            .toLowerCase();
        return /defer|rollback|commit|in-?script/.test(tokens);
    }

    function actionIsInvoked(action) {
        return !!(action.invocations && action.invocations.length);
    }

    function findingsByPriority(findings) {
        return (findings || [])
            .slice()
            .sort(
                (a, b) =>
                    priorityRank(priorityClass(b.review_priority)) -
                    priorityRank(priorityClass(a.review_priority)),
            );
    }

    function appendPriorityChip(container, priority, label = null) {
        const normalized = priorityClass(priority);
        container.appendChild(
            makeElement(
                "span",
                `analysis-chip analysis-priority-${normalized}`,
                label || `${normalized} review`,
            ),
        );
    }

    function appendFinding(container, finding) {
        const priority = priorityClass(finding.review_priority);
        const item = makeElement(
            "div",
            `analysis-finding analysis-priority-${priority}`,
        );
        const heading = makeElement("div", "analysis-finding-heading");
        heading.appendChild(
            makeElement("span", "analysis-priority", `${priority} review`),
        );
        heading.appendChild(
            makeElement("strong", "", finding.title || finding.category || "Review item"),
        );
        item.appendChild(heading);
        if (finding.category) {
            item.appendChild(
                makeElement("div", "analysis-finding-category", finding.category),
            );
        }
        if (finding.detail) {
            item.appendChild(
                makeElement("div", "analysis-finding-detail", finding.detail),
            );
        }
        container.appendChild(item);
        return item;
    }

    function appendDataReference(container, reference, binary) {
        if (!reference) {
            return;
        }
        const row = appendDefinition(
            container,
            "Data",
            reference.label ||
                `${reference.table}[${(reference.primary_keys || []).join(", ")}]`,
            { code: true },
        );
        if (row) {
            row.classList.add("analysis-data-reference");
            row.dataset.binaryRequest = JSON.stringify({
                kind: "table",
                table: reference.table,
                primary_keys: reference.primary_keys || [],
            });
        }
        if (binary) {
            appendDefinition(
                container,
                "Payload",
                `${Number(binary.size).toLocaleString()} bytes · ${binary.format} · ` +
                    `SHA-256 ${binary.sha256}`,
                { code: true },
            );
        }
    }

    function renderInvocations(container, invocations) {
        if (!invocations || !invocations.length) {
            appendDefinition(container, "Invocation sites", "None found");
            return;
        }
        const details = makeElement("details", "analysis-details");
        details.appendChild(
            makeElement(
                "summary",
                "",
                `Referenced from ${invocations.length} package location(s)`,
            ),
        );
        const list = makeElement("ul", "analysis-list");
        for (const invocation of invocations) {
            const item = makeElement("li");
            let text = invocation.table || "Unknown table";
            if (invocation.sequence !== null && invocation.sequence !== undefined) {
                text += ` @ ${invocation.sequence}`;
            }
            if (invocation.trigger) {
                text += ` (${invocation.trigger})`;
            }
            if (invocation.condition) {
                text += ` if ${invocation.condition}`;
            }
            if (invocation.allowed === false) {
                text += " [invalid or unreachable]";
            }
            item.appendChild(makeElement("div", "", text));
            if (invocation.note) {
                item.appendChild(
                    makeElement("div", "analysis-note", invocation.note),
                );
            }
            list.appendChild(item);
        }
        details.appendChild(list);
        container.appendChild(details);
    }

    function renderCustomActionData(container, assignments) {
        if (!assignments || !assignments.length) {
            return;
        }
        const section = makeElement("section", "analysis-indirection");
        section.appendChild(
            makeElement("h6", "analysis-subheading", "Deferred action reads CustomActionData"),
        );
        const list = makeElement("ul", "analysis-list");
        for (const assignment of assignments) {
            const item = makeElement("li");
            const prefix = assignment.setter_action
                ? `Property[${assignment.property}] set by CustomAction ` +
                  `"${assignment.setter_action}"`
                : `Initial Property[${assignment.property}] value`;
            item.appendChild(makeElement("div", "", prefix));
            item.appendChild(
                makeElement("code", "analysis-inline-code", assignment.resolved_value),
            );
            if (assignment.invocations && assignment.invocations.length) {
                const locations = assignment.invocations.map((invocation) => {
                    const sequence =
                        invocation.sequence === null || invocation.sequence === undefined
                            ? ""
                            : ` @ ${invocation.sequence}`;
                    const condition = invocation.condition
                        ? ` if ${invocation.condition}`
                        : "";
                    return `${invocation.table}${sequence}${condition}`;
                });
                item.appendChild(
                    makeElement(
                        "div",
                        "analysis-note",
                        `Setter location(s): ${locations.join("; ")}`,
                    ),
                );
            }
            list.appendChild(item);
        }
        section.appendChild(list);
        container.appendChild(section);
    }

    function renderDecodedPowerShell(container, decoded) {
        if (!decoded) {
            return;
        }
        const origin = decoded.origin ? ` from ${decoded.origin}` : "";
        if (decoded.error) {
            appendDefinition(
                container,
                `Encoded PowerShell${origin}`,
                decoded.error,
            );
            return;
        }
        const details = makeElement(
            "details",
            "analysis-details analysis-decoded-powershell",
        );
        const truncated = decoded.truncated ? " · preview truncated" : "";
        details.appendChild(
            makeElement(
                "summary",
                "",
                `Decoded PowerShell${origin} · ${decoded.decoded_size} bytes · ` +
                    `${decoded.encoding}${truncated}`,
            ),
        );
        appendDefinition(details, "SHA-256", decoded.sha256, { code: true });
        appendCodeBlock(details, decoded.text_preview || "", "analysis-script-code");
        container.appendChild(details);
    }

    function renderAction(action) {
        const card = makeElement("article", "analysis-action-card");
        card.dataset.facetPriorities = Array.from(actionPriorities(action)).join(" ");
        card.dataset.facetReference = actionIsInvoked(action)
            ? "invoked"
            : "unreferenced";
        card.dataset.facetScript = String(actionIsScript(action));
        card.dataset.facetDeferred = String(actionIsDeferred(action));
        card.appendChild(
            makeElement("h4", "analysis-card-title", `CustomAction "${action.action}"`),
        );

        const type = action.type || {};
        const typeText =
            `Type ${type.value} (${type.hex || ""}) · type number ${type.type_number} · ` +
            `${type.summary || type.name || "unknown"}`;
        card.appendChild(makeElement("div", "analysis-action-type", typeText));

        const chips = makeElement("div", "analysis-chips");
        for (const capability of type.capabilities || []) {
            chips.appendChild(makeElement("span", "analysis-chip", capability));
        }
        for (const flag of type.flags || []) {
            chips.appendChild(makeElement("span", "analysis-chip", flag));
        }
        if (chips.children.length) {
            card.appendChild(chips);
        }

        appendDefinition(card, "Return", type.return_processing);
        appendDefinition(card, "Source origin", action.source_origin);
        appendDefinition(card, "Source", action.resolved_source || action.source, {
            code: true,
        });
        if (action.source && action.resolved_source && action.source !== action.resolved_source) {
            appendDefinition(card, "Source key", action.source, { code: true });
        }
        if (action.unresolved_reason) {
            appendDefinition(card, "Unresolved", action.unresolved_reason);
        }

        if (type.source_kind === "file" && action.source) {
            const row = appendDefinition(
                card,
                "Installed file",
                action.resolved_source || action.source,
                { code: true },
            );
            if (row) {
                row.classList.add("analysis-data-reference");
                row.dataset.binaryRequest = JSON.stringify({
                    kind: "file",
                    file_id: action.source,
                });
            }
        }
        appendDataReference(card, action.data_reference, action.binary);
        appendDefinition(card, "Entry point/function", action.entrypoint, { code: true });

        if (action.command) {
            card.appendChild(makeElement("h6", "analysis-subheading", "Command line"));
            appendCodeBlock(card, action.command);
        }
        if (action.launchers && action.launchers.length) {
            appendDefinition(
                card,
                "Launcher references",
                `${action.launchers.join(", ")} (command, script, or CustomActionData)`,
            );
        }

        renderDecodedPowerShell(card, action.decoded_powershell);

        if (action.script_preview) {
            const language = type.kind === "vbscript" ? "VBScript" : "JScript";
            const location = {
                none: "Inline",
                binary: "Binary-table",
                file: "Installed-file",
                property: "Property-backed",
            }[type.source_kind] || "Script";
            const details = makeElement("details", "analysis-details analysis-script");
            const truncated = action.script_preview_truncated ? " · truncated" : "";
            details.appendChild(
                makeElement(
                    "summary",
                    "",
                    `${location} ${language} preview${truncated}`,
                ),
            );
            appendCodeBlock(details, action.script_preview, "analysis-script-code");
            card.appendChild(details);
        } else if (type.kind === "jscript" || type.kind === "vbscript") {
            const language = type.kind === "vbscript" ? "VBScript" : "JScript";
            card.appendChild(
                makeElement(
                    "div",
                    "analysis-script-location",
                    `${language} source: ${type.source_kind || "unknown"}`,
                ),
            );
        }

        if (!action.command && action.target && !action.script_preview) {
            appendDefinition(card, "Target", action.resolved_target || action.target, {
                code: true,
            });
        }

        renderInvocations(card, action.invocations || []);
        renderCustomActionData(card, action.custom_action_data || []);

        if (action.findings && action.findings.length) {
            const sorted = findingsByPriority(action.findings);
            const details = makeElement("details", "analysis-details analysis-review-items");
            details.open = sorted.some(
                (finding) => finding.review_priority === "high",
            );
            details.appendChild(
                makeElement(
                    "summary",
                    "",
                    `Capabilities and review items (${sorted.length})`,
                ),
            );
            for (const finding of sorted) {
                appendFinding(details, finding);
            }
            card.appendChild(details);
        }
        return card;
    }

    function renderSummary(container, analysis) {
        const summary = analysis.summary || {};
        const summaryBox = makeElement("section", "analysis-summary");
        const tableState = summary.has_custom_action_table
            ? `${summary.custom_action_count || 0} CustomAction row(s)`
            : "No CustomAction table";
        summaryBox.appendChild(
            makeElement(
                "div",
                "analysis-summary-primary",
                `${tableState} · ${summary.finding_count || 0} review item(s)`,
            ),
        );

        // Facts with a `filter` entry become buttons that narrow the custom-action
        // list below; the rest are plain counts.
        const facts = [
            {
                label: "Invoked actions",
                value: summary.invoked_action_count || 0,
                filter: { dim: "reference", val: "invoked" },
            },
            {
                label: "Unreferenced actions",
                value: summary.unreferenced_action_count || 0,
                filter: { dim: "reference", val: "unreferenced" },
            },
            {
                label: "Scripts",
                value: summary.script_action_count || 0,
                filter: { dim: "script", val: "true" },
            },
            {
                label: "Deferred/rollback/commit",
                value: summary.deferred_action_count || 0,
                filter: { dim: "deferred", val: "true" },
            },
            { label: "Registry writes", value: summary.registry_write_count || 0 },
            { label: "Registry searches", value: summary.registry_search_count || 0 },
            { label: "Service controls", value: summary.service_control_count || 0 },
            {
                label: "Unresolved references",
                value: summary.unresolved_reference_count || 0,
            },
        ];
        const factsBox = makeElement("div", "analysis-summary-grid");
        for (const fact of facts) {
            const clickable = Boolean(fact.filter) && fact.value > 0;
            const element = makeElement(
                clickable ? "button" : "div",
                "analysis-summary-fact",
            );
            if (clickable) {
                element.type = "button";
                element.dataset.filterDim = fact.filter.dim;
                element.dataset.filterVal = fact.filter.val;
                element.setAttribute("aria-pressed", "false");
            }
            element.appendChild(
                makeElement("span", "analysis-summary-number", fact.value),
            );
            element.appendChild(makeElement("span", "", fact.label));
            factsBox.appendChild(element);
        }
        summaryBox.appendChild(factsBox);

        const priorities = summary.review_priorities || {};
        const chips = makeElement("div", "analysis-chips");
        for (const priority of ["high", "medium", "low"]) {
            if (priorities[priority]) {
                const chip = makeElement(
                    "button",
                    `analysis-chip analysis-priority-${priority}`,
                    `${priority} review: ${priorities[priority]}`,
                );
                chip.type = "button";
                chip.dataset.filterDim = "priority";
                chip.dataset.filterVal = priority;
                chip.setAttribute("aria-pressed", "false");
                chips.appendChild(chip);
            }
        }
        if (chips.children.length) {
            summaryBox.appendChild(chips);
        }
        summaryBox.appendChild(
            makeElement(
                "p",
                "analysis-disclaimer",
                "Static capability and package-fact summary. Review priority helps triage; " +
                    "it is not a malware verdict.",
            ),
        );
        container.appendChild(summaryBox);
    }

    function renderRegistrySearches(container, searches) {
        if (!searches || !searches.length) {
            return;
        }
        const section = makeElement("section", "analysis-fact-section");
        section.appendChild(
            makeElement("h4", "analysis-section-title", "Registry-backed AppSearch facts"),
        );
        for (const search of searches) {
            const card = makeElement("article", "analysis-fact-card");
            const properties = search.properties && search.properties.length
                ? search.properties.join(", ")
                : "No AppSearch property";
            card.appendChild(makeElement("h5", "analysis-card-title", properties));
            const valueName =
                search.resolved_name || search.name || "(default registry value)";
            appendDefinition(
                card,
                "Registry location",
                `${search.root}\\${search.key} · ${valueName}`,
                { code: true },
            );
            appendDefinition(card, "Signature", search.signature, { code: true });
            appendDefinition(card, "Authored locator", search.locator_kind);
            appendDefinition(card, "Possible result", search.result_kind);
            appendDefinition(card, "Registry view", search.registry_view);
            if (search.initial_values && search.initial_values.length) {
                const values = search.initial_values
                    .map((item) => `${item.property}=${JSON.stringify(item.value)}`)
                    .join("; ");
                appendDefinition(card, "Initial fallback", values, { code: true });
            }
            if (
                search.referenced_by_custom_actions &&
                search.referenced_by_custom_actions.length
            ) {
                const row = makeElement("div", "analysis-chips");
                appendPriorityChip(row, "medium");
                row.appendChild(
                    makeElement(
                        "span",
                        "analysis-reference-note",
                        `Referenced by ${search.referenced_by_custom_actions.join(", ")}`,
                    ),
                );
                card.appendChild(row);
            }
            for (const warning of search.warnings || []) {
                card.appendChild(makeElement("div", "analysis-note", `Warning: ${warning}`));
            }
            section.appendChild(card);
        }
        container.appendChild(section);
    }

    function renderServiceControls(container, controls) {
        if (!controls || !controls.length) {
            return;
        }
        const section = makeElement("section", "analysis-fact-section");
        section.appendChild(
            makeElement("h4", "analysis-section-title", "ServiceControl facts"),
        );
        for (const control of controls) {
            const card = makeElement("article", "analysis-fact-card");
            card.appendChild(
                makeElement("h5", "analysis-card-title", control.resolved_name || control.name),
            );
            appendDefinition(
                card,
                "Operations",
                control.events && control.events.length
                    ? control.events.join(", ")
                    : "No recognized event bits",
            );
            if (control.start_arguments && control.start_arguments.length) {
                appendDefinition(
                    card,
                    "Start arguments",
                    control.start_arguments.join(" · "),
                    { code: true },
                );
            }
            appendDefinition(card, "Wait behavior", control.wait_behavior);
            appendDefinition(card, "Component", control.component, { code: true });
            appendDefinition(
                card,
                "ServiceInstall match",
                control.matches_installed_service
                    ? "Matching service name found"
                    : "No matching ServiceInstall service name found",
            );
            for (const warning of control.warnings || []) {
                card.appendChild(makeElement("div", "analysis-note", `Warning: ${warning}`));
            }
            section.appendChild(card);
        }
        container.appendChild(section);
    }

    function renderRegistryWrites(container, writes) {
        if (!writes || !writes.length) {
            return;
        }
        const details = makeElement("details", "analysis-details analysis-registry-writes");
        const persistenceCount = writes.filter(
            (write) => write.persistence_categories && write.persistence_categories.length,
        ).length;
        details.appendChild(
            makeElement(
                "summary",
                "",
                `Registry writes (${writes.length}; ${persistenceCount} persistence-related)`,
            ),
        );
        const list = makeElement("div", "analysis-registry-list");
        for (const write of writes) {
            const item = makeElement("div", "analysis-registry-write");
            const name = write.name || "(default)";
            item.appendChild(
                makeElement(
                    "code",
                    "analysis-inline-code",
                    `${write.root}\\${write.key} · ${name} -> ` +
                        `${write.resolved_value ?? write.value ?? ""}`,
                ),
            );
            if (write.persistence_categories && write.persistence_categories.length) {
                const chips = makeElement("div", "analysis-chips");
                for (const category of write.persistence_categories) {
                    chips.appendChild(makeElement("span", "analysis-chip", category));
                }
                item.appendChild(chips);
            }
            list.appendChild(item);
        }
        details.appendChild(list);
        container.appendChild(details);
    }

    function renderAnalysis(container, analysis) {
        container.replaceChildren();
        renderSummary(container, analysis);

        const packageFindings = findingsByPriority(
            (analysis.findings || []).filter((finding) => !finding.action),
        );
        if (packageFindings.length) {
            const section = makeElement("section", "analysis-package-findings");
            section.appendChild(
                makeElement(
                    "h4",
                    "analysis-section-title",
                    "Package capabilities and review items",
                ),
            );
            for (const finding of packageFindings) {
                appendFinding(section, finding);
            }
            container.appendChild(section);
        }

        // Order custom actions so the ones most worth reviewing surface first, matching
        // the overview: highest review priority, then invoked before unreferenced, then
        // by name for a stable ordering.
        const actions = (analysis.custom_actions || []).slice().sort((a, b) => {
            const byPriority =
                priorityRank(actionPriority(b)) - priorityRank(actionPriority(a));
            if (byPriority) {
                return byPriority;
            }
            const byInvoked =
                (actionIsInvoked(b) ? 1 : 0) - (actionIsInvoked(a) ? 1 : 0);
            if (byInvoked) {
                return byInvoked;
            }
            return String(a.action || "").localeCompare(String(b.action || ""));
        });
        const actionSection = makeElement("section", "analysis-actions");
        actionSection.appendChild(
            makeElement("h4", "analysis-section-title", "Custom actions"),
        );
        if (!actions.length) {
            const summary = analysis.summary || {};
            const message = summary.has_custom_action_table
                ? "The CustomAction table is present but empty."
                : "The package has no CustomAction table.";
            actionSection.appendChild(makeElement("p", "", message));
        } else {
            actionSection.appendChild(makeElement("div", "analysis-filter-status"));
            const list = makeElement("div", "analysis-action-list");
            for (const action of actions) {
                list.appendChild(renderAction(action));
            }
            actionSection.appendChild(list);
        }
        container.appendChild(actionSection);

        renderRegistrySearches(container, analysis.registry_searches || []);
        renderServiceControls(container, analysis.service_controls || []);
        renderRegistryWrites(container, analysis.registry_writes || []);

        if (analysis.warnings && analysis.warnings.length) {
            const details = makeElement("details", "analysis-details analysis-warnings");
            details.appendChild(
                makeElement(
                    "summary",
                    "",
                    `Analysis warnings (${analysis.warnings.length})`,
                ),
            );
            const list = makeElement("ul", "analysis-list");
            for (const warning of analysis.warnings) {
                list.appendChild(makeElement("li", "", warning));
            }
            details.appendChild(list);
            container.appendChild(details);
        }
        setupFilters(container);
        document.dispatchEvent(
            new CustomEvent("pymsi-analysis-rendered", { detail: { container } }),
        );
    }

    // Lets the overview counts/chips narrow the custom-action list below them. Only the
    // custom-action cards are filtered; the registry/service fact sections are left as-is.
    function setupFilters(container) {
        const status = container.querySelector(".analysis-filter-status");
        const controls = Array.from(
            container.querySelectorAll("[data-filter-dim]"),
        );
        const cards = Array.from(
            container.querySelectorAll(".analysis-action-card"),
        );
        if (!status || !controls.length || !cards.length) {
            if (status) {
                status.remove();
            }
            return;
        }

        const list = container.querySelector(".analysis-action-list");
        const total = cards.length;
        const state = {
            priority: null,
            reference: null,
            script: false,
            deferred: false,
        };
        let emptyMessage = null;

        function anyActive() {
            return (
                state.priority ||
                state.reference ||
                state.script ||
                state.deferred
            );
        }

        function cardMatches(card) {
            const data = card.dataset;
            if (state.priority) {
                const present = (data.facetPriorities || "").split(" ");
                if (!present.includes(state.priority)) {
                    return false;
                }
            }
            if (state.reference && data.facetReference !== state.reference) {
                return false;
            }
            if (state.script && data.facetScript !== "true") {
                return false;
            }
            if (state.deferred && data.facetDeferred !== "true") {
                return false;
            }
            return true;
        }

        function apply() {
            let visible = 0;
            for (const card of cards) {
                const show = cardMatches(card);
                card.hidden = !show;
                if (show) {
                    visible += 1;
                }
            }

            for (const control of controls) {
                const dim = control.dataset.filterDim;
                const val = control.dataset.filterVal;
                const active =
                    dim === "priority" || dim === "reference"
                        ? state[dim] === val
                        : state[dim] === true;
                control.setAttribute("aria-pressed", active ? "true" : "false");
                control.classList.toggle("is-active", active);
            }

            status.replaceChildren();
            status.appendChild(
                makeElement(
                    "span",
                    "",
                    anyActive()
                        ? `Showing ${visible} of ${total} custom actions`
                        : `${total} custom actions`,
                ),
            );
            if (anyActive()) {
                const clear = makeElement(
                    "button",
                    "analysis-filter-clear",
                    "Clear filters",
                );
                clear.type = "button";
                clear.addEventListener("click", () => {
                    state.priority = null;
                    state.reference = null;
                    state.script = false;
                    state.deferred = false;
                    apply();
                });
                status.appendChild(clear);
            }

            if (visible === 0) {
                if (!emptyMessage) {
                    emptyMessage = makeElement(
                        "p",
                        "analysis-empty",
                        "No custom actions match the current filter.",
                    );
                }
                if (list && !emptyMessage.isConnected) {
                    list.appendChild(emptyMessage);
                }
            } else if (emptyMessage && emptyMessage.isConnected) {
                emptyMessage.remove();
            }
        }

        for (const control of controls) {
            control.addEventListener("click", () => {
                const dim = control.dataset.filterDim;
                const val = control.dataset.filterVal;
                if (dim === "priority" || dim === "reference") {
                    state[dim] = state[dim] === val ? null : val;
                } else {
                    state[dim] = !state[dim];
                }
                apply();
            });
        }

        apply();
    }

    function injectStyles() {
        if (document.getElementById("pymsi-analysis-styles")) {
            return;
        }
        const style = makeElement("style");
        style.id = "pymsi-analysis-styles";
        style.textContent = `
            #${ANALYSIS_TAB_ID} {
                line-height: 1.45;
                /* Calm, non-alarming review-priority palette. High is the strongest
                   accent, not "error red", so a high item reads as "look here first"
                   rather than "something is broken". */
                --analysis-prio-high: #5b5bd6;
                --analysis-prio-medium: #5f7d95;
                --analysis-prio-low: var(--msi-muted, #4b5563);
                --analysis-mono: var(--font-stack--monospace, ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace);
            }
            html[data-theme="dark"] #${ANALYSIS_TAB_ID},
            body[data-theme="dark"] #${ANALYSIS_TAB_ID} {
                --analysis-prio-high: #a5a3f0;
                --analysis-prio-medium: #9db8cc;
            }
            @media (prefers-color-scheme: dark) {
                html:not([data-theme="light"]) #${ANALYSIS_TAB_ID},
                body:not([data-theme="light"]) #${ANALYSIS_TAB_ID} {
                    --analysis-prio-high: #a5a3f0;
                    --analysis-prio-medium: #9db8cc;
                }
            }
            /* Section and card headings sized relative to the pane's own <h3> title so
               the tab matches Files/Tables/Summary/Streams. The pane <h3> is left to the
               theme so it stays identical to the other tabs. */
            #${ANALYSIS_TAB_ID} .analysis-section-title { font-size: 1.05rem; font-weight: 700; margin: 1.75rem 0 .85rem; padding-bottom: .3rem; border-bottom: 1px solid var(--msi-border, #d5d8de); }
            #${ANALYSIS_TAB_ID} .analysis-section-title:first-of-type { margin-top: .35rem; }
            #${ANALYSIS_TAB_ID} .analysis-card-title { font-size: 1.02rem; font-weight: 700; margin: 0 0 .5rem; }
            #${ANALYSIS_TAB_ID} .analysis-subheading { font-size: .85rem; font-weight: 600; margin: .85rem 0 .35rem; color: var(--msi-muted, #4b5563); }
            .analysis-loading, .analysis-error { padding: 1rem; border-radius: 6px; background: var(--msi-surface, #f6f7fb); color: var(--msi-foreground, #1f2933); }
            .analysis-error { border-left: 4px solid var(--msi-accent-strong, #0051a8); white-space: pre-wrap; }
            .analysis-summary { margin: 0 0 1.25rem; padding: 1rem; border: 1px solid var(--msi-border, #d5d8de); border-radius: 8px; background: var(--msi-bg, #fff); }
            .analysis-summary-primary { font-size: 1.05rem; font-weight: 700; }
            .analysis-summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr)); gap: .55rem; margin: .85rem 0; }
            .analysis-summary-fact { display: flex; flex-direction: column; gap: .1rem; padding: .55rem .6rem; border-radius: 6px; overflow-wrap: break-word; background: var(--msi-surface, #f6f7fb); border: 1px solid transparent; text-align: left; color: inherit; }
            button.analysis-summary-fact { cursor: pointer; font: inherit; }
            button.analysis-summary-fact:hover { border-color: var(--msi-accent, #06c); }
            .analysis-summary-fact.is-active { border-color: var(--msi-accent, #06c); box-shadow: inset 0 0 0 1px var(--msi-accent, #06c); }
            .analysis-summary-number { font-size: 1.15rem; font-weight: 700; }
            .analysis-disclaimer { margin: .65rem 0 0; opacity: .82; }
            .analysis-filter-status { display: flex; flex-wrap: wrap; align-items: center; gap: .6rem; margin: 0 0 .9rem; font-size: .9rem; color: var(--msi-muted, #4b5563); }
            .analysis-filter-clear { font: inherit; cursor: pointer; padding: .15rem .65rem; border: 1px solid var(--msi-border, #d5d8de); border-radius: 999px; background: var(--msi-surface, #f6f7fb); color: var(--msi-accent, #06c); }
            .analysis-filter-clear:hover { border-color: var(--msi-accent, #06c); }
            .analysis-empty { padding: .85rem; font-style: italic; color: var(--msi-muted, #4b5563); }
            .analysis-chips { display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; margin: .55rem 0; }
            .analysis-chip { display: inline-block; padding: .15rem .55rem; border: 1px solid currentColor; border-radius: 999px; font-size: .85rem; background: transparent; color: inherit; }
            button.analysis-chip { cursor: pointer; font: inherit; }
            .analysis-chip.is-active { box-shadow: inset 0 0 0 2px currentColor; font-weight: 700; }
            .analysis-priority-high { color: var(--analysis-prio-high); }
            .analysis-priority-medium { color: var(--analysis-prio-medium); }
            .analysis-priority-low { color: var(--analysis-prio-low); }
            .analysis-action-card, .analysis-fact-card { margin: 0 0 1rem; padding: 1rem; border: 1px solid var(--msi-border, #d5d8de); border-radius: 8px; overflow-wrap: anywhere; background: var(--msi-bg, #fff); }
            .analysis-action-card[hidden] { display: none; }
            .analysis-action-type { font-size: .9rem; font-weight: 400; margin-bottom: .5rem; color: var(--msi-muted, #4b5563); }
            .analysis-reference-note { font-size: .9rem; font-weight: 400; color: var(--msi-muted, #4b5563); }
            .analysis-script-location { font-size: .9rem; font-weight: 400; margin: .35rem 0; color: var(--msi-muted, #4b5563); }
            .analysis-definition { display: grid; grid-template-columns: minmax(7rem, 11rem) 1fr; gap: .6rem; align-items: start; margin: .3rem 0; }
            .analysis-definition-label { font-weight: 500; }
            .analysis-definition-value { min-width: 0; overflow-wrap: anywhere; }
            code.analysis-definition-value { font-family: var(--analysis-mono); font-size: .9em; }
            .analysis-code { max-height: 24rem; overflow: auto; margin: .35rem 0 .75rem; padding: .75rem; border-radius: 6px; background: var(--msi-surface, #f6f7fb); white-space: pre-wrap; overflow-wrap: anywhere; font-family: var(--analysis-mono); font-size: .85rem; }
            .analysis-inline-code { display: block; margin-top: .2rem; white-space: pre-wrap; overflow-wrap: anywhere; font-family: var(--analysis-mono); font-size: .85rem; }
            .analysis-details { margin: .7rem 0; }
            .analysis-details > summary { cursor: pointer; font-weight: 500; }
            .analysis-list { margin: .45rem 0; padding-left: 1.4rem; }
            .analysis-note { margin-top: .2rem; font-size: .88rem; opacity: .78; white-space: pre-wrap; }
            /* Only a thin left border + the small label carry the priority color; the
               body text stays in the normal foreground color so nothing looks "wrong". */
            .analysis-finding { margin: .55rem 0; padding: .65rem .75rem; border-left: 4px solid currentColor; border-radius: 0 6px 6px 0; background: var(--msi-surface, #f6f7fb); }
            .analysis-finding-heading { display: flex; gap: .5rem; align-items: baseline; }
            .analysis-finding-heading strong { font-weight: 600; color: var(--msi-foreground, #1f2933); }
            .analysis-priority { text-transform: uppercase; font-size: .72rem; font-weight: 700; letter-spacing: .02em; }
            .analysis-finding-category { font-size: .8rem; opacity: .75; color: var(--msi-foreground, #1f2933); }
            .analysis-finding-detail { margin-top: .25rem; white-space: pre-wrap; overflow-wrap: anywhere; color: var(--msi-foreground, #1f2933); }
            .analysis-registry-write { padding: .55rem 0; border-bottom: 1px solid var(--msi-border, #d5d8de); }
            .analysis-registry-write:last-child { border-bottom: 0; }
            @media (max-width: 700px) {
                .analysis-definition { grid-template-columns: 1fr; gap: .15rem; }
            }
        `;
        document.head.appendChild(style);
    }

    function installAnalysisMethods() {
        if (typeof MSIViewer === "undefined") {
            console.warn("pymsi analysis: MSIViewer is not available");
            return;
        }
        if (MSIViewer.prototype.loadSecurityAnalysis) {
            return;
        }

        MSIViewer.prototype.loadSecurityAnalysis = async function loadSecurityAnalysis() {
            const content = document.getElementById(ANALYSIS_CONTENT_ID);
            if (!content || !this.pyodide) {
                return;
            }
            content.replaceChildren(
                makeElement(
                    "p",
                    "analysis-loading",
                    "Analyzing custom actions, searches, registry writes, and services…",
                ),
            );
            try {
                const serialized = await this.pyodide.runPythonAsync(`
import json as _pymsi_analysis_json
_pymsi_analysis_json.dumps(
    pymsi.analyze_package(current_package).to_dict(),
    ensure_ascii=False,
)
`);
                renderAnalysis(content, JSON.parse(serialized));
            } catch (error) {
                console.error("Could not analyze MSI", error);
                content.replaceChildren(
                    makeElement(
                        "div",
                        "analysis-error",
                        `Could not analyze this MSI: ${
                            error && error.message ? error.message : error
                        }`,
                    ),
                );
            }
        };

        const originalLoadStreams = MSIViewer.prototype.loadStreams;
        MSIViewer.prototype.loadStreams = async function loadStreamsWithAnalysis(...args) {
            const result = await originalLoadStreams.apply(this, args);
            await this.loadSecurityAnalysis();
            return result;
        };
    }

    installAnalysisMethods();
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", injectStyles, { once: true });
    } else {
        injectStyles();
    }
})();
