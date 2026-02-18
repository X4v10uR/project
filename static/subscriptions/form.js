document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("subscription-form");
    if (!form) {
        return;
    }

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
    const iconPreview = document.getElementById("service-icon-preview");
    const iconImage = document.getElementById("service-icon-image");
    const iconFallback = document.getElementById("service-icon-fallback");

    const startDateInput = document.getElementById("id_start_date");

    const passwordInput = document.getElementById("id_account_password");
    const togglePasswordButton = document.getElementById("toggle-password-btn");
    const passwordEyeOpen = document.getElementById("password-eye-open");
    const passwordEyeClosed = document.getElementById("password-eye-closed");

    const participantSeed = readJsonScript("participant-seed-data", []);
    const reminderSeed = readJsonScript("reminder-seed-data", []);

    let reminderOffsets = normalizeReminderOffsets(reminderSeed);

    initializeStatusControls();
    initializeSplitControls();
    initializeParticipantControls();
    initializeReminderControls();
    initializeServiceIconPreview();
    initializeStartDateInput();
    initializePasswordToggle();
    initializeSubmitValidation();

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

    function initializeServiceIconPreview() {
        if (!serviceNameInput || !iconImage || !iconFallback) {
            return;
        }

        const serviceMappings = {
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

        function generateIconUrl(serviceName) {
            if (!serviceName) {
                return "";
            }

            const serviceLower = serviceName.toLowerCase().trim();
            let iconName = serviceMappings[serviceLower];
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

        function updateServiceIcon() {
            const serviceName = serviceNameInput.value.trim();
            if (!serviceName) {
                if (iconPreview) {
                    iconPreview.classList.remove("hidden");
                }
                iconImage.classList.add("hidden");
                iconFallback.classList.remove("hidden");
                iconFallback.textContent = "S";
                return;
            }

            if (iconPreview) {
                iconPreview.classList.remove("hidden");
            }

            iconFallback.textContent = serviceName.charAt(0).toUpperCase();
            const iconUrl = generateIconUrl(serviceName);
            if (!iconUrl) {
                iconImage.classList.add("hidden");
                iconFallback.classList.remove("hidden");
                return;
            }

            iconImage.classList.remove("hidden");
            iconImage.src = iconUrl;
            iconImage.onload = function () {
                iconFallback.classList.add("hidden");
            };
            iconImage.onerror = function () {
                iconImage.classList.add("hidden");
                iconFallback.classList.remove("hidden");
            };
        }

        serviceNameInput.addEventListener("input", updateServiceIcon);
        updateServiceIcon();
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
});
