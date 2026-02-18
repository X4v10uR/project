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

    function initializeStatusControls() {
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
                const activeClasses = statusClassMap[buttonStatus] || statusClassMap.active;
                button.classList.remove.apply(button.classList, inactiveClasses);
                button.classList.remove.apply(button.classList, statusClassMap.active);
                button.classList.remove.apply(button.classList, statusClassMap.paused);
                button.classList.remove.apply(button.classList, statusClassMap.cancelled);

                if (buttonStatus === activeStatus) {
                    button.classList.add.apply(button.classList, activeClasses);
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

        function isSharedSelected() {
            const selected = form.querySelector('input[name="is_shared"]:checked');
            return selected ? selected.value === "True" : false;
        }

        function toggleSharedSettings() {
            if (isSharedSelected()) {
                sharedSettings.classList.remove("hidden");
            } else {
                sharedSettings.classList.add("hidden");
                splitError.classList.add("hidden");
                saveButton.disabled = false;
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
        const row = document.createElement("div");
        row.className = "participant-row flex items-center gap-2 bg-gray-50 px-3 py-2.5 rounded-lg border border-gray-200";

        const nameInput = document.createElement("input");
        nameInput.type = "text";
        nameInput.name = "participant_name";
        nameInput.value = name || "";
        nameInput.placeholder = "Participant name";
        nameInput.className = "subscription-input !py-2 !px-3 !bg-white flex-1";

        const shareWrap = document.createElement("div");
        shareWrap.className = "relative w-28 shrink-0";

        const currencyPrefix = document.createElement("span");
        currencyPrefix.className = "absolute left-2 top-1/2 -translate-y-1/2 text-sm text-gray-500";
        currencyPrefix.textContent = "$";

        const shareInput = document.createElement("input");
        shareInput.type = "number";
        shareInput.step = "0.01";
        shareInput.name = "participant_share";
        shareInput.value = share || "";
        shareInput.className = "participant-share-input subscription-input !py-2 !pl-6 !pr-2 !bg-white text-sm";

        const removeButton = document.createElement("button");
        removeButton.type = "button";
        removeButton.className = "remove-participant text-gray-400 hover:text-red-500 p-1";
        removeButton.innerHTML = (
            '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">' +
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>' +
            "</svg>"
        );

        shareWrap.appendChild(currencyPrefix);
        shareWrap.appendChild(shareInput);
        row.appendChild(nameInput);
        row.appendChild(shareWrap);
        row.appendChild(removeButton);

        participantsList.appendChild(row);
        return row;
    }

    function getParticipantRows() {
        return Array.from(participantsList.querySelectorAll(".participant-row"));
    }

    function getNamedParticipantRows() {
        return getParticipantRows().filter(function (row) {
            const nameInput = row.querySelector('input[name="participant_name"]');
            return nameInput && nameInput.value.trim() !== "";
        });
    }

    function getCurrentSplitType() {
        return splitTypeInput.value || "equal";
    }

    function calculateSplits() {
        const isShared = (form.querySelector('input[name="is_shared"]:checked') || {}).value === "True";
        if (!isShared) {
            userShareDisplay.value = normalizeCurrencyValue(costInput.value).toFixed(2);
            return;
        }

        const totalCost = normalizeCurrencyValue(costInput.value);
        const splitType = getCurrentSplitType();
        const participantRows = getParticipantRows();
        const namedParticipantRows = getNamedParticipantRows();
        const namedCount = namedParticipantRows.length;

        if (splitType === "equal") {
            const divisor = namedCount > 0 ? namedCount + 1 : 1;
            const sharePerPerson = divisor > 0 ? totalCost / divisor : totalCost;
            participantRows.forEach(function (row) {
                const shareInput = row.querySelector('input[name="participant_share"]');
                if (!shareInput) {
                    return;
                }
                shareInput.readOnly = true;
                if (row.querySelector('input[name="participant_name"]').value.trim() !== "") {
                    shareInput.value = sharePerPerson.toFixed(2);
                } else {
                    shareInput.value = "";
                }
            });
            userShareDisplay.value = sharePerPerson.toFixed(2);
            splitError.classList.add("hidden");
            saveButton.disabled = false;
            return;
        }

        let othersTotal = 0;
        participantRows.forEach(function (row) {
            const shareInput = row.querySelector('input[name="participant_share"]');
            const nameInput = row.querySelector('input[name="participant_name"]');
            if (!shareInput || !nameInput) {
                return;
            }
            shareInput.readOnly = false;
            if (nameInput.value.trim() === "") {
                return;
            }
            othersTotal += normalizeCurrencyValue(shareInput.value);
        });

        const userShare = totalCost - othersTotal;
        userShareDisplay.value = userShare.toFixed(2);
        if (userShare < 0) {
            splitError.classList.remove("hidden");
            saveButton.disabled = true;
            return;
        }

        splitError.classList.add("hidden");
        saveButton.disabled = false;
    }

    function initializeParticipantControls() {
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
            if (
                event.target.matches('input[name="participant_name"]') ||
                event.target.matches('input[name="participant_share"]')
            ) {
                calculateSplits();
            }
        });

        costInput.addEventListener("input", calculateSplits);
        calculateSplits();
    }

    function renderReminderOffsets() {
        offsetsList.innerHTML = "";
        offsetsInputsContainer.innerHTML = "";

        if (!reminderOffsets.length) {
            const emptyMsg = document.createElement("p");
            emptyMsg.className = "text-sm text-gray-400";
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
        const enabled = remindersCheckbox.checked;
        remindersToggleLabel.textContent = enabled ? "On" : "Off";
        remindersToggleButton.classList.toggle("is-on", enabled);
        offsetsSection.classList.toggle("opacity-50", !enabled);
        offsetsSection.classList.toggle("pointer-events-none", !enabled);
    }

    function initializeReminderControls() {
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
                iconPreview.classList.add("hidden");
                iconImage.classList.add("hidden");
                iconFallback.textContent = "S";
                return;
            }

            iconPreview.classList.remove("hidden");
            iconFallback.textContent = serviceName.charAt(0).toUpperCase();
            const iconUrl = generateIconUrl(serviceName);
            if (!iconUrl) {
                iconImage.classList.add("hidden");
                return;
            }

            iconImage.classList.remove("hidden");
            iconImage.src = iconUrl;
            iconImage.onerror = function () {
                iconImage.classList.add("hidden");
            };
        }

        serviceNameInput.addEventListener("input", updateServiceIcon);
        updateServiceIcon();
    }

    function initializePasswordToggle() {
        togglePasswordButton.addEventListener("click", function () {
            const shouldShow = passwordInput.type === "password";
            passwordInput.type = shouldShow ? "text" : "password";
            passwordEyeOpen.classList.toggle("hidden", shouldShow);
            passwordEyeClosed.classList.toggle("hidden", !shouldShow);
        });
    }

    function initializeSubmitValidation() {
        form.addEventListener("submit", function (event) {
            const isShared = (form.querySelector('input[name="is_shared"]:checked') || {}).value === "True";
            if (!isShared) {
                return;
            }

            const namedParticipants = getNamedParticipantRows();
            if (!namedParticipants.length) {
                event.preventDefault();
                window.alert("Please add at least one participant for a shared subscription.");
                return;
            }

            if (!splitError.classList.contains("hidden")) {
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
