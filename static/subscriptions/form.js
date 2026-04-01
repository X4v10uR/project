(function () {
    function initSubscriptionForm() {
    const form = document.getElementById("subscription-form");
    if (!form) {
        return;
    }
    if (form.dataset.subscriptionFormReady === "true") {
        return;
    }
    form.dataset.subscriptionFormReady = "true";

    const saveButton = document.getElementById("save-subscription-btn");
    const costInput = document.getElementById("id_cost");
    const splitError = document.getElementById("split-error");
    const sharedSettings = document.getElementById("shared-settings");
    const splitTypeInput = document.getElementById("id_split_type");
    const userShareDisplay = document.getElementById("user-share-display");
    const participantsList = document.getElementById("participants-list");
    const newParticipantNameInput = document.getElementById("new-participant-name");
    const addParticipantButton = document.getElementById("add-participant-btn");

    const remindersCheckbox = document.getElementById("id_reminders_enabled");
    const remindersToggleButton = document.getElementById("reminders-toggle-btn");
    const remindersToggleKnob = document.getElementById("reminders-toggle-knob");
    const remindersToggleLabel = document.getElementById("reminder-toggle-label");
    const offsetsSection = document.getElementById("offsets-section");
    const offsetsList = document.getElementById("offsets-list");
    const offsetsInputsContainer = document.getElementById("offset-inputs-container");
    const newOffsetDaysInput = document.getElementById("new-offset-days");
    const addOffsetButton = document.getElementById("add-offset-btn");

    const statusInput = document.getElementById("id_status");
    const statusButtons = Array.from(document.querySelectorAll("[data-status-option]"));
    const splitButtons = Array.from(document.querySelectorAll("[data-split-option]"));
    const isSharedInputs = Array.from(document.querySelectorAll('input[name="is_shared"]'));

    const serviceNameInput = document.getElementById("id_service_name");
    const displayColorInput = document.getElementById("id_display_color");
    const displayColorPicker = document.getElementById("id_display_color_picker");
    const displayColorAutoButton = document.getElementById("display-color-auto");
    const displayColorValue = document.getElementById("display-color-value");
    const displayColorSwatches = Array.from(
        document.querySelectorAll("[data-display-color-swatch]")
    );

    const startDateInput = document.getElementById("id_start_date");

    const passwordInput = document.getElementById("id_account_password");
    const togglePasswordButton = document.getElementById("toggle-password-btn");
    const passwordEyeOpen = document.getElementById("password-eye-open");
    const passwordEyeClosed = document.getElementById("password-eye-closed");
    const jumpButtons = Array.from(
        document.querySelectorAll(".sub-jump-btn[data-target]")
    );

    const participantSeed = readJsonScript("participant-seed-data", []);
    const reminderSeed = readJsonScript("reminder-seed-data", []);
    const DEFAULT_PICKER_COLOR = "#F9F871";
    const SUMMARY_SERVICE_MAP = {
        netflix: { bg: "#B5A5E7", letter: "N" },
        spotify: { bg: "#7BCFC0", letter: "S" },
        youtube: { bg: "#F4C3A8", letter: "Y" },
        github: { bg: "#AFC0DE", letter: "G" },
        "apple tv": { bg: "#F9F871", letter: "A" },
        "paramount+": { bg: "#C7BEEA", letter: "P+" },
    };
    const SERVICE_ICON_MAPPINGS = {
        "chatgpt plus": "openai",
        "chat gpt": "openai",
        openai: "openai",
        "adobe cc": "adobe",
        "adobe creative cloud": "adobe",
        "disney+": "disney-plus",
        "disney plus": "disney-plus",
        "amazon prime": "amazon-prime-video",
        "prime video": "amazon-prime-video",
        "youtube premium": "youtube",
        "google drive": "google-drive",
        "google workspace": "google-workspace",
        "microsoft 365": "microsoft-365",
        "office 365": "microsoft-365",
        icloud: "icloud",
        dropbox: "dropbox",
        github: "github",
        gitlab: "gitlab",
        bitbucket: "bitbucket",
        aws: "amazon-web-services",
        "amazon web services": "amazon-web-services",
        "google cloud": "google-cloud",
        azure: "microsoft-azure",
        "digital ocean": "digitalocean",
        linode: "linode",
        vultr: "vultr",
    };

    let reminderOffsets = normalizeReminderOffsets(reminderSeed);

    initializeStatusControls();
    initializeSplitControls();
    initializeParticipantControls();
    initializeReminderControls();
    initializeDisplayColorPicker();
    initializeStartDateInput();
    initializePasswordToggle();
    initializeSubmitValidation();
    initializeCustomSelects();
    initializeShareIndicators();
    initializeDatePicker();
    initializeSummaryPreview();
    initializeJumpSidebar();

    function initializeJumpSidebar() {
        if (!jumpButtons.length) {
            return;
        }

        const sections = jumpButtons
            .map(function (button) {
                const target = button.dataset.target || "";
                const section = document.getElementById("section-" + target);
                if (!target || !section) {
                    return null;
                }
                return { target: target, section: section };
            })
            .filter(Boolean);

        if (!sections.length) {
            return;
        }

        const jumpColumn = document.querySelector(".sub-jump-col");
        const jumpCard = jumpColumn
            ? jumpColumn.querySelector(".sub-jump-card")
            : null;

        function getJumpColor(button) {
            const rawColor = (button.style.getPropertyValue("--jump-color") || "").trim();
            return rawColor || "#E5E7EB";
        }

        jumpButtons.forEach(function (button) {
            button.style.display = "flex";
            button.style.alignItems = "center";
            button.style.gap = "7px";
            button.style.padding = "8px 10px";
            button.style.borderRadius = "10px";
            button.style.textDecoration = "none";

            const dot = button.querySelector(".sub-jump-dot");
            if (dot) {
                dot.style.width = "8px";
                dot.style.height = "8px";
                dot.style.borderRadius = "9999px";
                dot.style.border = "1.5px solid " + getJumpColor(button);
                dot.style.background = "transparent";
                dot.style.flexShrink = "0";
            }
        });

        function syncSidebarDocking() {
            if (!jumpCard) {
                return;
            }
            jumpCard.style.position = "";
            jumpCard.style.top = "";
            jumpCard.style.left = "";
            jumpCard.style.width = "";
            jumpCard.style.zIndex = "";
        }

        function getScrollableAncestor(element) {
            let node = element ? element.parentElement : null;
            while (node && node !== document.body && node !== document.documentElement) {
                const style = window.getComputedStyle(node);
                const overflowY = style ? style.overflowY : "";
                const canScroll =
                    (overflowY === "auto" || overflowY === "scroll" || overflowY === "overlay") &&
                    node.scrollHeight > node.clientHeight + 1;
                if (canScroll) {
                    return node;
                }
                node = node.parentElement;
            }
            return window;
        }

        const scrollContainer = getScrollableAncestor(sections[0].section);

        function sectionTopRelativeToContainer(section) {
            if (scrollContainer === window) {
                return section.getBoundingClientRect().top;
            }
            const sectionRect = section.getBoundingClientRect();
            const containerRect = scrollContainer.getBoundingClientRect();
            return sectionRect.top - containerRect.top;
        }

        function setActive(target) {
            jumpButtons.forEach(function (button) {
                const isActive = (button.dataset.target || "") === target;
                const jumpColor = getJumpColor(button);
                button.classList.toggle(
                    "is-active",
                    isActive
                );
                button.style.background = isActive ? jumpColor : "transparent";
                button.style.color = isActive ? "#0D0D10" : "#6B7280";
                button.style.fontWeight = isActive ? "700" : "500";

                const dot = button.querySelector(".sub-jump-dot");
                if (!dot) {
                    return;
                }
                dot.style.borderColor = isActive ? "#0D0D10" : jumpColor;
                dot.style.background = isActive ? "#0D0D10" : "transparent";
            });
        }

        function updateActiveFromScroll() {
            let activeTarget = sections[0].target;
            sections.forEach(function (entry) {
                if (sectionTopRelativeToContainer(entry.section) <= 140) {
                    activeTarget = entry.target;
                }
            });
            setActive(activeTarget);
        }

        function jumpToSection(target) {
            const entry = sections.find(function (item) {
                return item.target === target;
            });
            if (!entry) {
                return;
            }

            if (scrollContainer === window) {
                const nextTop = Math.max(
                    window.scrollY + entry.section.getBoundingClientRect().top - 20,
                    0
                );
                window.scrollTo({ top: nextTop, behavior: "smooth" });
            } else {
                const sectionRect = entry.section.getBoundingClientRect();
                const containerRect = scrollContainer.getBoundingClientRect();
                const nextTop = Math.max(
                    scrollContainer.scrollTop + sectionRect.top - containerRect.top - 20,
                    0
                );
                scrollContainer.scrollTo({ top: nextTop, behavior: "smooth" });
            }
            setActive(target);
        }

        jumpButtons.forEach(function (button) {
            button.addEventListener("click", function (event) {
                event.preventDefault();
                jumpToSection(button.dataset.target || "");
            });
        });

        let isTicking = false;
        function onScroll() {
            if (isTicking) {
                return;
            }
            isTicking = true;
            window.requestAnimationFrame(function () {
                isTicking = false;
                updateActiveFromScroll();
            });
        }

        (scrollContainer === window ? window : scrollContainer).addEventListener(
            "scroll",
            onScroll,
            { passive: true }
        );
        window.addEventListener("resize", function () {
            syncSidebarDocking();
            onScroll();
        });
        syncSidebarDocking();
        updateActiveFromScroll();
    }

    function readJsonScript(scriptId, fallback) {
        const script = document.getElementById(scriptId);
        if (!script) {
            return fallback;
        }

        try {
            return JSON.parse(script.textContent);
        } catch (error) {
            return fallback;
        }
    }

    function normalizeReminderOffsets(rawOffsets) {
        const seen = new Set();
        const normalized = [];

        rawOffsets.forEach(function (rawValue) {
            const parsed = parseInt(rawValue, 10);
            if (Number.isNaN(parsed) || parsed < 1 || parsed > 30 || seen.has(parsed)) {
                return;
            }
            seen.add(parsed);
            normalized.push(parsed);
        });

        normalized.sort(function (a, b) {
            return a - b;
        });
        return normalized;
    }

    function normalizeHexColor(rawValue) {
        const raw = String(rawValue || "").trim().toUpperCase();
        if (!raw) {
            return "";
        }

        let value = raw;
        if (value.charAt(0) !== "#") {
            value = "#" + value;
        }

        if (/^#[0-9A-F]{3}$/.test(value)) {
            value =
                "#" +
                value.charAt(1) +
                value.charAt(1) +
                value.charAt(2) +
                value.charAt(2) +
                value.charAt(3) +
                value.charAt(3);
        }

        return /^#[0-9A-F]{6}$/.test(value) ? value : "";
    }

    function isDarkColor(rawColor) {
        const color = normalizeHexColor(rawColor);
        if (!color) {
            return false;
        }

        const red = parseInt(color.slice(1, 3), 16);
        const green = parseInt(color.slice(3, 5), 16);
        const blue = parseInt(color.slice(5, 7), 16);
        const luminance = (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255;
        return luminance < 0.6;
    }

    function getPreviewTone(rawColor) {
        if (isDarkColor(rawColor)) {
            return {
                primary: "#FFFFFF",
                secondary: "rgba(255,255,255,0.78)",
                tagBackground: "rgba(255,255,255,0.2)",
                tagColor: "#FFFFFF",
            };
        }

        return {
            primary: "#1F2937",
            secondary: "#4B5563",
            tagBackground: "rgba(255,255,255,0.42)",
            tagColor: "#374151",
        };
    }

    function getAutoSummaryStyle(serviceName) {
        const normalized = (serviceName || "").trim().toLowerCase();
        const preset = SUMMARY_SERVICE_MAP[normalized];
        if (preset) {
            return preset;
        }

        const name = (serviceName || "").trim();
        return {
            bg: "#E5E7EB",
            letter: name ? name.charAt(0).toUpperCase() : "S",
        };
    }

    function getEffectiveDisplayColor(serviceName) {
        const customColor = normalizeHexColor(displayColorInput ? displayColorInput.value : "");
        if (customColor) {
            return customColor;
        }
        return getAutoSummaryStyle(serviceName).bg;
    }

    function generateIconUrl(serviceName) {
        if (!serviceName) {
            return "";
        }

        const serviceLower = serviceName.toLowerCase().trim();
        let iconName = SERVICE_ICON_MAPPINGS[serviceLower];
        if (!iconName) {
            iconName = serviceLower
                .replace(/ /g, "-")
                .replace(/\+/g, "-plus")
                .replace(/&/g, "-and")
                .replace(/\./g, "")
                .replace(/[()]/g, "")
                .replace(/_/g, "-");
        }
        return "https://cdn.jsdelivr.net/gh/selfhst/icons@main/svg/" + iconName + ".svg";
    }

    function dispatchDisplayColorChange() {
        if (!displayColorInput) {
            return;
        }
        displayColorInput.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function syncDisplayColorControls() {
        const currentColor = normalizeHexColor(displayColorInput ? displayColorInput.value : "");

        if (displayColorPicker) {
            displayColorPicker.value = currentColor || normalizeHexColor(displayColorPicker.value) || DEFAULT_PICKER_COLOR;
        }
        if (displayColorAutoButton) {
            displayColorAutoButton.classList.toggle("active", !currentColor);
        }
        if (displayColorValue) {
            displayColorValue.textContent = currentColor || "Auto";
        }
        displayColorSwatches.forEach(function (button) {
            button.classList.toggle(
                "active",
                normalizeHexColor(button.dataset.displayColorSwatch) === currentColor
            );
        });
    }

    function initializeDisplayColorPicker() {
        if (!displayColorInput || !displayColorPicker) {
            return;
        }

        displayColorInput.value = normalizeHexColor(displayColorInput.value);

        if (displayColorAutoButton) {
            displayColorAutoButton.addEventListener("click", function () {
                displayColorInput.value = "";
                syncDisplayColorControls();
                dispatchDisplayColorChange();
            });
        }

        function applyCustomColor(rawColor) {
            const color = normalizeHexColor(rawColor);
            if (!color) {
                return;
            }
            displayColorInput.value = color;
            displayColorPicker.value = color;
            syncDisplayColorControls();
            dispatchDisplayColorChange();
        }

        displayColorPicker.addEventListener("input", function () {
            applyCustomColor(displayColorPicker.value);
        });
        displayColorPicker.addEventListener("change", function () {
            applyCustomColor(displayColorPicker.value);
        });

        displayColorSwatches.forEach(function (button) {
            button.addEventListener("click", function () {
                applyCustomColor(button.dataset.displayColorSwatch);
            });
        });

        syncDisplayColorControls();
    }

    function removeClasses(element, classes) {
        classes.forEach(function (className) {
            element.classList.remove(className);
        });
    }

    function isSharedSelected() {
        const selected = form.querySelector('input[name="is_shared"]:checked');
        return selected ? selected.value === "True" : false;
    }

    function initializeStatusControls() {
        if (!statusInput || !statusButtons.length) {
            return;
        }

        const statusClassMap = {
            active: ["bg-emerald-200", "text-emerald-800"],
            paused: ["bg-orange-200", "text-orange-800"],
            cancelled: ["bg-red-200", "text-red-800"],
        };
        const inactiveClasses = ["bg-gray-100", "text-gray-500", "hover:bg-gray-200"];

        function syncStatusButtons() {
            const activeStatus = statusInput.value || "active";

            statusButtons.forEach(function (button) {
                const buttonStatus = button.dataset.statusOption;

                removeClasses(button, inactiveClasses);
                Object.keys(statusClassMap).forEach(function (key) {
                    removeClasses(button, statusClassMap[key]);
                });

                if (buttonStatus === activeStatus) {
                    button.classList.add.apply(button.classList, statusClassMap[buttonStatus] || statusClassMap.active);
                } else {
                    button.classList.add.apply(button.classList, inactiveClasses);
                }
            });
        }

        statusButtons.forEach(function (button) {
            button.addEventListener("click", function () {
                statusInput.value = button.dataset.statusOption;
                syncStatusButtons();
            });
        });

        syncStatusButtons();
    }

    function initializeSplitControls() {
        if (!splitTypeInput || !splitButtons.length || !sharedSettings) {
            return;
        }

        function syncSplitButtons() {
            const splitType = splitTypeInput.value || "equal";

            splitButtons.forEach(function (button) {
                if (button.dataset.splitOption === splitType) {
                    button.classList.add("bg-slate-900", "text-white", "shadow");
                    button.classList.remove("text-gray-500", "hover:text-gray-900");
                } else {
                    button.classList.remove("bg-slate-900", "text-white", "shadow");
                    button.classList.add("text-gray-500", "hover:text-gray-900");
                }
            });
        }

        function toggleSharedSettings() {
            if (isSharedSelected()) {
                sharedSettings.classList.remove("hidden");
            } else {
                sharedSettings.classList.add("hidden");
                if (splitError) {
                    splitError.classList.add("hidden");
                }
                if (saveButton) {
                    saveButton.disabled = false;
                }
            }
            calculateSplits();
        }

        splitButtons.forEach(function (button) {
            button.addEventListener("click", function () {
                splitTypeInput.value = button.dataset.splitOption;
                syncSplitButtons();
                calculateSplits();
            });
        });

        isSharedInputs.forEach(function (input) {
            input.addEventListener("change", toggleSharedSettings);
        });

        syncSplitButtons();
        toggleSharedSettings();
    }

    function createParticipantRow(name, share) {
        if (!participantsList) {
            return null;
        }

        const participantName = (name || "").trim();

        const row = document.createElement("div");
        row.className = "participant-row flex items-center justify-between bg-gray-50 px-4 py-2.5 rounded-lg border border-gray-200 gap-3";

        const leftWrap = document.createElement("div");
        leftWrap.className = "flex items-center gap-3 min-w-0 flex-1";

        const avatar = document.createElement("div");
        avatar.className = "w-8 h-8 bg-purple-200 rounded-full flex items-center justify-center text-xs font-bold text-purple-700 uppercase";
        avatar.textContent = participantName ? participantName.charAt(0) : "?";

        const label = document.createElement("span");
        label.className = "participant-name-label text-sm font-medium text-gray-700 truncate";
        label.textContent = participantName;

        const hiddenNameInput = document.createElement("input");
        hiddenNameInput.type = "hidden";
        hiddenNameInput.name = "participant_name";
        hiddenNameInput.className = "participant-name-input";
        hiddenNameInput.value = participantName;

        leftWrap.appendChild(avatar);
        leftWrap.appendChild(label);
        leftWrap.appendChild(hiddenNameInput);

        const shareWrap = document.createElement("div");
        shareWrap.className = "participant-share-wrap flex items-center gap-1";

        const currencyPrefix = document.createElement("span");
        currencyPrefix.className = "text-xs text-gray-500";
        currencyPrefix.textContent = "$";

        const shareInput = document.createElement("input");
        shareInput.type = "number";
        shareInput.step = "0.01";
        shareInput.name = "participant_share";
        shareInput.value = share || "";
        shareInput.placeholder = "0.00";
        shareInput.className = "participant-share-input w-20 bg-white border border-gray-200 rounded-md px-2 py-1 text-sm text-gray-700 outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent";

        shareWrap.appendChild(currencyPrefix);
        shareWrap.appendChild(shareInput);

        const removeButton = document.createElement("button");
        removeButton.type = "button";
        removeButton.className = "remove-participant text-gray-400 hover:text-red-500 p-1";
        removeButton.innerHTML = (
            '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">' +
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>' +
            "</svg>"
        );

        row.appendChild(leftWrap);
        row.appendChild(shareWrap);
        row.appendChild(removeButton);

        participantsList.appendChild(row);
        return row;
    }

    function getParticipantRows() {
        if (!participantsList) {
            return [];
        }
        return Array.from(participantsList.querySelectorAll(".participant-row"));
    }

    function getNamedParticipantRows() {
        return getParticipantRows().filter(function (row) {
            const nameInput = row.querySelector(".participant-name-input");
            return nameInput && nameInput.value.trim() !== "";
        });
    }

    function getCurrentSplitType() {
        return splitTypeInput ? splitTypeInput.value || "equal" : "equal";
    }

    function syncParticipantShareVisibility(isCustom) {
        getParticipantRows().forEach(function (row) {
            const shareWrap = row.querySelector(".participant-share-wrap");
            const shareInput = row.querySelector('input[name="participant_share"]');
            if (!shareWrap || !shareInput) {
                return;
            }

            shareWrap.classList.toggle("hidden", !isCustom);
            shareInput.readOnly = !isCustom;
        });
    }

    function calculateSplits() {
        const totalCost = normalizeCurrencyValue(costInput ? costInput.value : 0);
        const splitType = getCurrentSplitType();
        const participantRows = getParticipantRows();
        const namedParticipantRows = getNamedParticipantRows();

        if (!isSharedSelected()) {
            syncParticipantShareVisibility(false);
            if (userShareDisplay) {
                userShareDisplay.textContent = totalCost.toFixed(2);
            }
            if (splitError) {
                splitError.classList.add("hidden");
            }
            if (saveButton) {
                saveButton.disabled = false;
            }
            return;
        }

        if (splitType === "equal") {
            syncParticipantShareVisibility(false);
            const divisor = namedParticipantRows.length > 0 ? namedParticipantRows.length + 1 : 1;
            const sharePerPerson = divisor > 0 ? totalCost / divisor : totalCost;

            participantRows.forEach(function (row) {
                const nameInput = row.querySelector(".participant-name-input");
                const shareInput = row.querySelector('input[name="participant_share"]');
                if (!nameInput || !shareInput) {
                    return;
                }

                if (nameInput.value.trim() !== "") {
                    shareInput.value = sharePerPerson.toFixed(2);
                } else {
                    shareInput.value = "";
                }
            });

            if (userShareDisplay) {
                userShareDisplay.textContent = sharePerPerson.toFixed(2);
            }

            if (splitError) {
                splitError.classList.add("hidden");
            }
            if (saveButton) {
                saveButton.disabled = false;
            }
            return;
        }

        syncParticipantShareVisibility(true);

        let othersTotal = 0;
        participantRows.forEach(function (row) {
            const nameInput = row.querySelector(".participant-name-input");
            const shareInput = row.querySelector('input[name="participant_share"]');
            if (!nameInput || !shareInput || nameInput.value.trim() === "") {
                return;
            }
            othersTotal += normalizeCurrencyValue(shareInput.value);
        });

        const userShare = totalCost - othersTotal;
        if (userShareDisplay) {
            userShareDisplay.textContent = userShare.toFixed(2);
        }

        if (userShare < 0) {
            if (splitError) {
                splitError.classList.remove("hidden");
            }
            if (saveButton) {
                saveButton.disabled = true;
            }
            return;
        }

        if (splitError) {
            splitError.classList.add("hidden");
        }
        if (saveButton) {
            saveButton.disabled = false;
        }
    }

    function initializeParticipantControls() {
        if (!participantsList || !newParticipantNameInput || !addParticipantButton) {
            return;
        }

        participantSeed.forEach(function (participant) {
            createParticipantRow(participant.name || "", participant.share || "");
        });

        addParticipantButton.addEventListener("click", function () {
            const name = newParticipantNameInput.value.trim();
            if (!name) {
                return;
            }
            createParticipantRow(name, "");
            newParticipantNameInput.value = "";
            calculateSplits();
        });

        newParticipantNameInput.addEventListener("keydown", function (event) {
            if (event.key !== "Enter") {
                return;
            }
            event.preventDefault();
            addParticipantButton.click();
        });

        participantsList.addEventListener("click", function (event) {
            const removeButton = event.target.closest(".remove-participant");
            if (!removeButton) {
                return;
            }

            const row = removeButton.closest(".participant-row");
            if (!row) {
                return;
            }
            row.remove();
            calculateSplits();
        });

        participantsList.addEventListener("input", function (event) {
            if (!event.target.matches('input[name="participant_share"]')) {
                return;
            }
            calculateSplits();
        });

        if (costInput) {
            costInput.addEventListener("input", calculateSplits);
        }

        calculateSplits();
    }

    function renderReminderOffsets() {
        if (!offsetsList || !offsetsInputsContainer) {
            return;
        }

        offsetsList.innerHTML = "";
        offsetsInputsContainer.innerHTML = "";

        if (!reminderOffsets.length) {
            const emptyMsg = document.createElement("p");
            emptyMsg.className = "text-xs text-gray-400 w-full";
            emptyMsg.textContent = "No custom offsets. Default notification logic is used.";
            offsetsList.appendChild(emptyMsg);
            return;
        }

        reminderOffsets.forEach(function (days) {
            const tag = document.createElement("span");
            tag.className = "inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium bg-slate-900 text-white shadow-sm";
            tag.dataset.days = String(days);

            const text = document.createElement("span");
            text.textContent = days + " day" + (days === 1 ? "" : "s") + " before";

            const removeButton = document.createElement("button");
            removeButton.type = "button";
            removeButton.className = "ml-2 inline-flex items-center justify-center w-4 h-4 rounded-full bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white";
            removeButton.innerHTML = (
                '<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">' +
                '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>' +
                "</svg>"
            );

            const hiddenInput = document.createElement("input");
            hiddenInput.type = "hidden";
            hiddenInput.name = "reminder_offsets";
            hiddenInput.value = String(days);

            tag.appendChild(text);
            tag.appendChild(removeButton);
            offsetsList.appendChild(tag);
            offsetsInputsContainer.appendChild(hiddenInput);
        });
    }

    function setReminderSectionState() {
        if (!remindersCheckbox || !remindersToggleButton || !remindersToggleKnob || !remindersToggleLabel || !offsetsSection) {
            return;
        }

        const enabled = remindersCheckbox.checked;
        remindersToggleLabel.textContent = enabled ? "On" : "Off";
        remindersToggleButton.classList.toggle("bg-slate-900", enabled);
        remindersToggleButton.classList.toggle("bg-gray-200", !enabled);
        remindersToggleKnob.classList.toggle("translate-x-5", enabled);
        remindersToggleKnob.classList.toggle("translate-x-0", !enabled);
        offsetsSection.classList.toggle("hidden", !enabled);
    }

    function initializeReminderControls() {
        if (
            !remindersCheckbox ||
            !remindersToggleButton ||
            !offsetsList ||
            !offsetsInputsContainer ||
            !newOffsetDaysInput ||
            !addOffsetButton
        ) {
            return;
        }

        remindersToggleButton.addEventListener("click", function () {
            remindersCheckbox.checked = !remindersCheckbox.checked;
            setReminderSectionState();
        });

        remindersCheckbox.addEventListener("change", setReminderSectionState);

        addOffsetButton.addEventListener("click", function () {
            const value = parseInt(newOffsetDaysInput.value, 10);
            if (Number.isNaN(value) || value < 1 || value > 30) {
                return;
            }

            if (reminderOffsets.indexOf(value) !== -1) {
                newOffsetDaysInput.value = "";
                return;
            }

            reminderOffsets.push(value);
            reminderOffsets = normalizeReminderOffsets(reminderOffsets);
            newOffsetDaysInput.value = "";
            renderReminderOffsets();
        });

        newOffsetDaysInput.addEventListener("keydown", function (event) {
            if (event.key !== "Enter") {
                return;
            }
            event.preventDefault();
            addOffsetButton.click();
        });

        offsetsList.addEventListener("click", function (event) {
            const removeButton = event.target.closest("button");
            if (!removeButton) {
                return;
            }

            const tag = removeButton.closest("[data-days]");
            if (!tag) {
                return;
            }

            const days = parseInt(tag.dataset.days, 10);
            reminderOffsets = reminderOffsets.filter(function (value) {
                return value !== days;
            });
            renderReminderOffsets();
        });

        renderReminderOffsets();
        setReminderSectionState();
    }

    function initializeStartDateInput() {
        if (!startDateInput) {
            return;
        }

        function syncDateMode() {
            if (startDateInput.value) {
                startDateInput.type = "date";
                return;
            }
            startDateInput.type = "text";
        }

        startDateInput.addEventListener("focus", function () {
            startDateInput.type = "date";
        });

        startDateInput.addEventListener("blur", syncDateMode);
        syncDateMode();
    }

    function initializePasswordToggle() {
        if (!togglePasswordButton || !passwordInput || !passwordEyeOpen || !passwordEyeClosed) {
            return;
        }

        togglePasswordButton.addEventListener("click", function () {
            const shouldShow = passwordInput.type === "password";
            passwordInput.type = shouldShow ? "text" : "password";
            passwordEyeOpen.classList.toggle("hidden", shouldShow);
            passwordEyeClosed.classList.toggle("hidden", !shouldShow);
        });
    }

    function initializeCustomSelects() {
        const maps = [
            {
                select: "id_category",
                trigger: "catTrig",
                value: "catVal",
                drop: "catDrop",
                placeholder: "Select a category",
                usePlaceholder: true,
            },
            {
                select: "id_billing_cycle",
                trigger: "cycTrig",
                value: "cycVal",
                drop: "cycDrop",
                placeholder: "Select billing cycle",
                usePlaceholder: true,
            },
            {
                select: "id_card",
                trigger: "cardTrig",
                value: "cardVal",
                drop: "cardDrop",
                placeholder: "Select a saved card",
                usePlaceholder: true,
            },
        ];

        const activeMaps = maps
            .map(function (mapConfig) {
                const selectEl = document.getElementById(mapConfig.select);
                const triggerEl = document.getElementById(mapConfig.trigger);
                const valueEl = document.getElementById(mapConfig.value);
                const dropEl = document.getElementById(mapConfig.drop);
                if (!selectEl || !triggerEl || !valueEl || !dropEl) {
                    return null;
                }
                return {
                    config: mapConfig,
                    selectEl: selectEl,
                    triggerEl: triggerEl,
                    valueEl: valueEl,
                    dropEl: dropEl,
                };
            })
            .filter(Boolean);

        if (!activeMaps.length) {
            return;
        }

        function closeDrops(exceptId) {
            activeMaps.forEach(function (map) {
                if (map.dropEl.id !== exceptId) {
                    map.dropEl.classList.remove("open");
                }
            });
        }

        activeMaps.forEach(function (map) {
            const selectEl = map.selectEl;
            const triggerEl = map.triggerEl;
            const valueEl = map.valueEl;
            const dropEl = map.dropEl;
            const mapConfig = map.config;

            dropEl.innerHTML = "";
            Array.from(selectEl.options).forEach(function (option) {
                if (!option.value) {
                    return;
                }

                const item = document.createElement("div");
                item.className = "sel-opt";
                item.dataset.value = option.value;
                item.innerHTML =
                    '<span></span><svg class="chk" viewBox="0 0 24 24" fill="none" stroke="#030213" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>';
                item.querySelector("span").textContent = option.textContent.trim();
                item.addEventListener("click", function () {
                    selectEl.value = option.value;
                    selectEl.dispatchEvent(new Event("change", { bubbles: true }));
                    sync();
                    closeDrops();
                });
                dropEl.appendChild(item);
            });

            function sync() {
                const hasValue = selectEl.value !== "";
                const selectedOption = selectEl.options[selectEl.selectedIndex];
                valueEl.textContent = hasValue && selectedOption ? selectedOption.textContent.trim() : mapConfig.placeholder;
                if (mapConfig.usePlaceholder) {
                    triggerEl.classList.toggle("ph", !hasValue);
                }

                dropEl.querySelectorAll(".sel-opt").forEach(function (item) {
                    item.classList.toggle("selected", item.dataset.value === selectEl.value);
                });
            }

            triggerEl.addEventListener("click", function () {
                const shouldOpen = !dropEl.classList.contains("open");
                closeDrops();
                dropEl.classList.toggle("open", shouldOpen);
            });

            selectEl.addEventListener("change", sync);
            sync();
        });

        document.addEventListener("click", function (event) {
            activeMaps.forEach(function (map) {
                if (
                    !map.triggerEl.contains(event.target) &&
                    !map.dropEl.contains(event.target)
                ) {
                    map.dropEl.classList.remove("open");
                }
            });
        });
    }

    function initializeShareIndicators() {
        const justMeIndicator = document.getElementById("rJustMe");
        const sharedIndicator = document.getElementById("rShared");
        if (!justMeIndicator && !sharedIndicator) {
            return;
        }

        function syncShareIndicator() {
            const current = isSharedInputs.find(function (input) {
                return input.checked;
            });
            const value = current ? current.value : "False";

            if (justMeIndicator) {
                justMeIndicator.className = "radio" + (value === "False" ? " on" : "");
            }
            if (sharedIndicator) {
                sharedIndicator.className = "radio" + (value === "True" ? " on" : "");
            }
        }

        isSharedInputs.forEach(function (input) {
            input.addEventListener("change", syncShareIndicator);
        });

        syncShareIndicator();
    }

    function initializeDatePicker() {
        const dateInput = startDateInput;
        const dateTrigger = document.getElementById("dateTrig");
        const dateLabel = document.getElementById("dateLabel");
        const calendar = document.getElementById("calPop");
        const calendarLabel = document.getElementById("calLabel");
        const calendarDays = document.getElementById("calDays");
        const calendarPrev = document.getElementById("calPrev");
        const calendarNext = document.getElementById("calNext");

        if (!dateInput || !dateTrigger || !dateLabel || !calendar || !calendarLabel || !calendarDays) {
            return;
        }

        const months = [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ];

        function parseIso(raw) {
            if (!/^\d{4}-\d{2}-\d{2}$/.test(raw || "")) {
                return null;
            }
            const parts = raw.split("-").map(Number);
            return new Date(parts[0], parts[1] - 1, parts[2]);
        }

        function toIso(date) {
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, "0");
            const day = String(date.getDate()).padStart(2, "0");
            return year + "-" + month + "-" + day;
        }

        let selectedDate = parseIso(dateInput.value);
        let year = selectedDate ? selectedDate.getFullYear() : new Date().getFullYear();
        let month = selectedDate ? selectedDate.getMonth() : new Date().getMonth();

        function setDateLabel() {
            if (!selectedDate) {
                dateTrigger.classList.add("nodate");
                dateTrigger.classList.remove("hasdate");
                dateLabel.textContent = "Pick a date";
                return;
            }

            dateTrigger.classList.remove("nodate");
            dateTrigger.classList.add("hasdate");
            dateLabel.textContent =
                months[selectedDate.getMonth()] +
                " " +
                selectedDate.getDate() +
                ", " +
                selectedDate.getFullYear();
        }

        function renderCalendar() {
            calendarLabel.textContent = months[month] + " " + year;

            const firstDay = new Date(year, month, 1).getDay();
            const daysInMonth = new Date(year, month + 1, 0).getDate();
            const previousMonthDays = new Date(year, month, 0).getDate();
            let html = "";

            for (let i = firstDay - 1; i >= 0; i--) {
                html +=
                    '<button type="button" class="cal-day out" disabled>' +
                    (previousMonthDays - i) +
                    "</button>";
            }

            for (let day = 1; day <= daysInMonth; day++) {
                const isSelected =
                    selectedDate &&
                    selectedDate.getDate() === day &&
                    selectedDate.getMonth() === month &&
                    selectedDate.getFullYear() === year;
                html +=
                    '<button type="button" class="cal-day' +
                    (isSelected ? " sel" : "") +
                    '" data-day="' +
                    day +
                    '">' +
                    day +
                    "</button>";
            }

            calendarDays.innerHTML = html;
        }

        dateTrigger.addEventListener("click", function () {
            calendar.classList.toggle("open");
            renderCalendar();
        });

        calendarDays.addEventListener("click", function (event) {
            const button = event.target.closest("[data-day]");
            if (!button) {
                return;
            }

            const day = Number(button.dataset.day);
            selectedDate = new Date(year, month, day);
            dateInput.value = toIso(selectedDate);
            dateInput.dispatchEvent(new Event("change", { bubbles: true }));
            calendar.classList.remove("open");
            setDateLabel();
        });

        if (calendarPrev) {
            calendarPrev.addEventListener("click", function () {
                month -= 1;
                if (month < 0) {
                    month = 11;
                    year -= 1;
                }
                renderCalendar();
            });
        }

        if (calendarNext) {
            calendarNext.addEventListener("click", function () {
                month += 1;
                if (month > 11) {
                    month = 0;
                    year += 1;
                }
                renderCalendar();
            });
        }

        document.addEventListener("click", function (event) {
            if (!calendar.contains(event.target) && !dateTrigger.contains(event.target)) {
                calendar.classList.remove("open");
            }
        });

        setDateLabel();
    }

    function initializeSummaryPreview() {
        const summarySection = document.getElementById("sumSec");
        if (!serviceNameInput || !summarySection) {
            return;
        }

        const planInput = document.getElementById("id_plan_name");
        const currencyInput = document.getElementById("id_currency");
        const billingCycleInput = document.getElementById("id_billing_cycle");
        const cardInput = document.getElementById("id_card");
        const categoryInput = document.getElementById("id_category");
        const summaryIconImage = document.getElementById("sumServiceIconImage");
        const summaryLetter = document.getElementById("sumLetter");
        const summaryName = document.getElementById("sumName");
        const summaryPlan = document.getElementById("sumPlan");
        const summaryCost = document.getElementById("sumCost");
        const summaryCycle = document.getElementById("sumCycle");
        const summaryPay = document.getElementById("sumPay");
        const summaryTags = document.getElementById("sumTags");
        const currencyMap = {
            USD: "$",
            EUR: "EUR ",
            GBP: "GBP ",
            INR: "INR ",
            CAD: "CAD ",
            AUD: "AUD ",
        };
        const shortMonths = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        let latestSummaryIconUrl = "";

        function parseIso(raw) {
            if (!/^\d{4}-\d{2}-\d{2}$/.test(raw || "")) {
                return null;
            }
            const parts = raw.split("-").map(Number);
            return new Date(parts[0], parts[1] - 1, parts[2]);
        }

        function getSelectedCardLabel() {
            if (!cardInput || !cardInput.value || cardInput.selectedIndex < 0) {
                return "No card selected";
            }
            const selected = cardInput.options[cardInput.selectedIndex];
            return selected ? selected.textContent.trim() : "No card selected";
        }

        function formatDateForSummary(rawDate) {
            const parsedDate = parseIso(rawDate || "");
            if (!parsedDate) {
                return "";
            }
            return (
                shortMonths[parsedDate.getMonth()] +
                " " +
                parsedDate.getDate() +
                ", " +
                parsedDate.getFullYear()
            );
        }

        function updateSummary() {
            const serviceName = (serviceNameInput.value || "").trim();
            const hasServiceName = Boolean(serviceName);
            const service = getAutoSummaryStyle(serviceName);
            const resolvedColor = getEffectiveDisplayColor(serviceName);
            const tone = getPreviewTone(resolvedColor);
            summarySection.style.display = "block";
            summarySection.style.backgroundColor = resolvedColor;

            if (summaryLetter) {
                summaryLetter.textContent = service.letter;
                summaryLetter.style.color = tone.primary;
                summaryLetter.classList.remove("hidden");
            }

            if (summaryIconImage) {
                summaryIconImage.classList.add("hidden");
                summaryIconImage.alt = "";
                latestSummaryIconUrl = "";

                if (hasServiceName) {
                    const iconUrl = generateIconUrl(serviceName);
                    if (iconUrl) {
                        latestSummaryIconUrl = iconUrl;
                        summaryIconImage.src = iconUrl;
                        summaryIconImage.alt = serviceName + " icon";
                        summaryIconImage.onload = function () {
                            if (latestSummaryIconUrl !== iconUrl) {
                                return;
                            }
                            summaryIconImage.classList.remove("hidden");
                            if (summaryLetter) {
                                summaryLetter.classList.add("hidden");
                            }
                        };
                        summaryIconImage.onerror = function () {
                            if (latestSummaryIconUrl !== iconUrl) {
                                return;
                            }
                            summaryIconImage.classList.add("hidden");
                            if (summaryLetter) {
                                summaryLetter.classList.remove("hidden");
                            }
                        };
                    }
                }
            }
            if (summaryName) {
                summaryName.textContent = hasServiceName ? serviceName : "Service Name";
                summaryName.style.color = tone.primary;
            }

            const plan = planInput ? (planInput.value || "").trim() : "";
            if (summaryPlan) {
                summaryPlan.style.display = "block";
                summaryPlan.textContent = plan || "Select a plan to start";
                summaryPlan.style.color = tone.secondary;
            }

            const rawCost = costInput ? (costInput.value || "").trim() : "";
            const parsedCost = parseFloat(rawCost);
            if (summaryCost) {
                if (rawCost && !Number.isNaN(parsedCost)) {
                    const code = currencyInput ? (currencyInput.value || "").trim().toUpperCase() || "USD" : "USD";
                    summaryCost.textContent = (currencyMap[code] || code + " ") + parsedCost.toFixed(2);
                } else {
                    summaryCost.textContent = "$0.00";
                }
                summaryCost.style.display = "block";
                summaryCost.style.color = tone.primary;
            }

            if (summaryCycle) {
                const formattedDate = formatDateForSummary(startDateInput ? startDateInput.value : "");
                summaryCycle.style.display = "block";
                summaryCycle.textContent = formattedDate || "Select a date";
                summaryCycle.style.color = tone.secondary;
            }

            if (summaryPay) {
                summaryPay.textContent = getSelectedCardLabel();
                summaryPay.style.color = tone.secondary;
            }

            if (summaryTags) {
                const tags = [];
                if (categoryInput && categoryInput.value && categoryInput.selectedIndex >= 0) {
                    tags.push(categoryInput.options[categoryInput.selectedIndex].textContent);
                }
                if (statusInput && statusInput.value) {
                    tags.push(statusInput.value);
                }
                if (billingCycleInput && billingCycleInput.value && billingCycleInput.selectedIndex >= 0) {
                    tags.push(billingCycleInput.options[billingCycleInput.selectedIndex].textContent);
                }
                const startDateLabel = formatDateForSummary(startDateInput ? startDateInput.value : "");
                if (startDateLabel) {
                    tags.push("Starts " + startDateLabel);
                }

                const sharedSelected = isSharedInputs.find(function (input) {
                    return input.checked;
                });
                const participantCount = participantsList
                    ? participantsList.querySelectorAll(".participant-row").length
                    : 0;
                if (sharedSelected && sharedSelected.value === "True" && participantCount > 0) {
                    tags.push(
                        "Shared with " +
                            participantCount +
                            " " +
                            (participantCount === 1 ? "person" : "people")
                    );
                }
                if (!tags.length) {
                    tags.push("Draft preview");
                }

                summaryTags.innerHTML = tags
                    .map(function (tag) {
                        return (
                            '<span style="font-size:12px;background:' +
                            tone.tagBackground +
                            ";border-radius:10px;padding:4px 8px;color:" +
                            tone.tagColor +
                            ';text-transform:capitalize;">' +
                            tag.replace(/</g, "&lt;") +
                            "</span>"
                        );
                    })
                    .join("");
            }
        }

        ["id_service_name", "id_plan_name", "id_cost", "id_currency", "id_billing_cycle", "id_category", "id_start_date"].forEach(
            function (id) {
                const element = document.getElementById(id);
                if (!element) {
                    return;
                }
                element.addEventListener("input", updateSummary);
                element.addEventListener("change", updateSummary);
            }
        );

        statusButtons.forEach(function (button) {
            button.addEventListener("click", function () {
                setTimeout(updateSummary, 0);
            });
        });

        if (displayColorInput) {
            displayColorInput.addEventListener("change", updateSummary);
        }
        if (cardInput) {
            cardInput.addEventListener("change", updateSummary);
        }

        isSharedInputs.forEach(function (input) {
            input.addEventListener("change", updateSummary);
        });

        if (participantsList) {
            new MutationObserver(updateSummary).observe(participantsList, {
                childList: true,
                subtree: true,
            });
        }

        updateSummary();
    }

    function initializeSubmitValidation() {
        form.addEventListener("submit", function (event) {
            if (!isSharedSelected()) {
                return;
            }

            const namedParticipants = getNamedParticipantRows();
            if (!namedParticipants.length) {
                event.preventDefault();
                window.alert("Please add at least one participant for a shared subscription.");
                return;
            }

            if (splitError && !splitError.classList.contains("hidden")) {
                event.preventDefault();
            }
        });
    }

    function normalizeCurrencyValue(rawValue) {
        const parsed = parseFloat(rawValue);
        if (Number.isNaN(parsed) || parsed < 0) {
            return 0;
        }
        return parsed;
    }
    }

    function runInit() {
        initSubscriptionForm();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", runInit);
    } else {
        runInit();
    }

    document.addEventListener("subly:content-loaded", runInit);
})();
