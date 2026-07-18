document.addEventListener("DOMContentLoaded", () => {
    // Elements
    const repoForm = document.getElementById("index-form");
    const runForm = document.getElementById("run-form");
    const collectionSelect = document.getElementById("collection-select");
    const logsTerminal = document.getElementById("logs-terminal");
    const clearLogsBtn = document.getElementById("clear-logs-btn");
    
    // Form buttons
    const indexBtn = document.getElementById("index-btn");
    const runBtn = document.getElementById("run-btn");
    
    // Tab elements
    const tabBtns = document.querySelectorAll(".tab-btn");
    const tabContents = document.querySelectorAll(".tab-content");
    const tabBtnPlan = document.getElementById("tab-btn-plan");
    const tabBtnPatches = document.getElementById("tab-btn-patches");
    
    // Plan elements
    const planGoal = document.getElementById("plan-goal");
    const planTaskType = document.getElementById("plan-task-type");
    const planContext = document.getElementById("plan-context");
    const planSubtasks = document.getElementById("plan-subtasks");
    
    // Patch elements
    const patchSummary = document.getElementById("patch-summary");
    const diffsContainer = document.getElementById("diffs-container");
    
    // Config elements
    const configForm = document.getElementById("config-form");
    const configStatus = document.getElementById("config-status");
    const cfgModelName = document.getElementById("cfg-model-name");
    const cfgModelProvider = document.getElementById("cfg-model-provider");
    const cfgApiKey = document.getElementById("cfg-api-key");
    const cfgEmbeddingModel = document.getElementById("cfg-embedding-model");
    const cfgChunkSize = document.getElementById("cfg-chunk-size");
    const cfgChunkOverlap = document.getElementById("cfg-chunk-overlap");
    const cfgTopK = document.getElementById("cfg-top-k");
    const cfgFetchK = document.getElementById("cfg-fetch-k");
    const cfgThreshold = document.getElementById("cfg-threshold");
    const cfgContextChars = document.getElementById("cfg-context-chars");
    const cfgReviewCycles = document.getElementById("cfg-review-cycles");
    
    let activeEventSource = null;

    // Load available collections
    async function loadCollections() {
        try {
            const res = await fetch("/api/collections");
            if (!res.ok) throw new Error("Failed to fetch collections");
            const data = await res.json();
            
            // Keep current selection if valid
            const currentSel = collectionSelect.value;
            
            collectionSelect.innerHTML = '<option value="">-- Select Collection --</option>';
            data.collections.forEach(col => {
                const opt = document.createElement("option");
                opt.value = col;
                opt.textContent = col;
                collectionSelect.appendChild(opt);
            });
            
            if (data.collections.includes(currentSel)) {
                collectionSelect.value = currentSel;
            }
        } catch (err) {
            console.error("Error loading collections:", err);
            appendLogLine("ERROR | Failed to list collections from backend.", "error");
        }
    }
    
    loadCollections();

    // Tab switching logic
    tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            if (btn.disabled) return;
            
            // Remove active classes
            tabBtns.forEach(b => b.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));
            
            // Add active classes
            btn.classList.add("active");
            const targetId = btn.getAttribute("data-tab");
            document.getElementById(targetId).classList.add("active");
        });
    });

    // Helper to append log lines
    function appendLogLine(text, type = "info") {
        const line = document.createElement("div");
        line.classList.add("log-line", type);
        line.textContent = text;
        logsTerminal.appendChild(line);
        logsTerminal.scrollTop = logsTerminal.scrollHeight;
    }

    // Helper to clear logs
    clearLogsBtn.addEventListener("click", () => {
        logsTerminal.innerHTML = '<div class="log-line info">Console cleared. Waiting for user task...</div>';
    });

    // Disable all inputs while running
    function setFormState(disabled) {
        document.querySelectorAll("input, textarea, select, button.primary-btn, button.success-btn").forEach(el => {
            el.disabled = disabled;
        });
        if (disabled) {
            indexBtn.textContent = "Processing...";
            runBtn.textContent = "Processing...";
        } else {
            indexBtn.textContent = "Index Repository";
            runBtn.textContent = "Generate Patch";
        }
    }

    // Connect to log stream
    function connectStream(sessionId, onComplete) {
        if (activeEventSource) {
            activeEventSource.close();
        }
        
        appendLogLine("INFO | Handshaking with execution stream...", "info");
        
        activeEventSource = new EventSource(`/api/stream/${sessionId}`);
        
        activeEventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                if (data.type === "log") {
                    // Detect warn or error prefixes to format logs
                    let logType = "info";
                    const lowerMsg = data.message.toLowerCase();
                    if (lowerMsg.includes(" | error | ") || lowerMsg.includes("exception")) {
                        logType = "error";
                    } else if (lowerMsg.includes(" | warning | ") || lowerMsg.includes("warn")) {
                        logType = "warn";
                    } else if (lowerMsg.includes("success")) {
                        logType = "success";
                    }
                    appendLogLine(data.message, logType);
                } else if (data.type === "result") {
                    appendLogLine("SUCCESS | Stream completed successfully.", "success");
                    activeEventSource.close();
                    activeEventSource = null;
                    setFormState(false);
                    if (onComplete) onComplete(data.payload);
                } else if (data.type === "error") {
                    appendLogLine(`ERROR | Agent process encountered error: ${data.message}`, "error");
                    activeEventSource.close();
                    activeEventSource = null;
                    setFormState(false);
                } else if (data.type === "step") {
                    if (data.step === "planner") {
                        updatePlannerStep(data.data);
                        updateStepCardStatus("step-reader", "running");
                    } else if (data.step === "reader") {
                        updateReaderStep(data.data);
                        updateStepCardStatus("step-writer", "running");
                    } else if (data.step === "writer") {
                        updateWriterStep(data.data);
                        updateStepCardStatus("step-reviewer", "running");
                    } else if (data.step === "reviewer") {
                        addReviewerCycle(data.cycle, data.data);
                    } else if (data.step === "revision") {
                        addRevisionCycle(data.cycle, data.data);
                        const badge = document.getElementById("step-reviewer").querySelector(".step-badge");
                        if (badge) {
                            badge.className = "step-badge running";
                            badge.textContent = "running";
                        }
                    }
                }
            } catch (err) {
                console.error("Stream parse error:", err);
            }
        };
        
        activeEventSource.onerror = (err) => {
            console.error("Stream connection error:", err);
            appendLogLine("ERROR | Log stream connection interrupted.", "error");
            activeEventSource.close();
            activeEventSource = null;
            setFormState(false);
        };
    }

    // Render Execution Plan
    function renderPlan(plan) {
        planGoal.textContent = plan.goal || "-";
        planTaskType.textContent = plan.task_type || "-";
        
        planContext.innerHTML = "";
        if (plan.required_context && plan.required_context.length) {
            plan.required_context.forEach(ctx => {
                const li = document.createElement("li");
                li.textContent = ctx;
                planContext.appendChild(li);
            });
        } else {
            planContext.innerHTML = "<li>None</li>";
        }
        
        planSubtasks.innerHTML = "";
        if (plan.subtasks && plan.subtasks.length) {
            plan.subtasks.forEach(task => {
                const li = document.createElement("li");
                li.textContent = task;
                planSubtasks.appendChild(li);
            });
        } else {
            planSubtasks.innerHTML = "<li>None</li>";
        }
        
        // Enable Plan tab
        tabBtnPlan.removeAttribute("disabled");
    }

    // Render Code Diffs
    function renderPatches(result) {
        patchSummary.textContent = result.patch.summary || "-";
        diffsContainer.innerHTML = "";
        
        // Show warnings if task changes failed logic reviews
        if (!result.approved) {
            const warningAlert = document.createElement("div");
            warningAlert.classList.add("warning-alert-card");
            warningAlert.innerHTML = `
                <h4>Review Logic Rejected</h4>
                <p>No code implementation was approved by the reviewer agent after reaching the maximum review cycles. As the AutoPR-AI tool is currently under development, it may fail with certain complex tasks. Please try running the task again with a different or more descriptive prompt.</p>
            `;
            diffsContainer.appendChild(warningAlert);
            
            const pipelineAlert = document.createElement("div");
            pipelineAlert.classList.add("warning-alert-card");
            pipelineAlert.innerHTML = `
                <h4>Review Logic Rejected</h4>
                <p>No code implementation was approved by the reviewer agent after reaching the maximum review cycles. As the AutoPR-AI tool is currently under development, it may fail with certain complex tasks. Please try running the task again with a different or more descriptive prompt.</p>
            `;
            pipelineContainer.prepend(pipelineAlert);
        }
        
        if (!result.patch.changes || !result.patch.changes.length) {
            diffsContainer.innerHTML = "<p>No file changes proposed.</p>";
            return;
        }
        
        result.patch.changes.forEach(change => {
            const card = document.createElement("div");
            card.classList.add("file-diff-card");
            
            const header = document.createElement("div");
            header.classList.add("file-diff-header");
            
            const title = document.createElement("span");
            title.classList.add("file-diff-title");
            title.textContent = change.path;
            
            const action = document.createElement("span");
            action.classList.add("file-diff-action", change.action);
            action.textContent = change.action;
            
            header.appendChild(title);
            header.appendChild(action);
            card.appendChild(header);
            
            const body = document.createElement("div");
            body.classList.add("file-diff-body");
            
            if (change.explanation) {
                const exp = document.createElement("div");
                exp.classList.add("diff-explanation");
                exp.textContent = `Explanation: ${change.explanation}`;
                body.appendChild(exp);
            }
            
            // Render changes based on action
            if (change.action === "create") {
                const pre = document.createElement("pre");
                pre.classList.add("diff-create-full-code");
                pre.textContent = change.code || "";
                body.appendChild(pre);
            } else if (change.action === "delete") {
                const delMsg = document.createElement("div");
                delMsg.classList.add("diff-explanation");
                delMsg.textContent = "File will be deleted from the repository.";
                body.appendChild(delMsg);
            } else if (change.action === "modify") {
                const blocksList = document.createElement("div");
                blocksList.classList.add("diff-blocks-list");
                
                change.edits.forEach((edit, idx) => {
                    const block = document.createElement("div");
                    block.classList.add("diff-block-unit");
                    
                    const blockHead = document.createElement("div");
                    blockHead.classList.add("diff-block-header");
                    blockHead.textContent = `Search/Replace Block #${idx + 1}`;
                    block.appendChild(blockHead);
                    
                    const blockCode = document.createElement("div");
                    blockCode.classList.add("diff-block-code");
                    
                    // Old code lines (Red)
                    edit.old_code.split("\n").forEach(line => {
                        const div = document.createElement("div");
                        div.classList.add("diff-line", "del");
                        div.textContent = `- ${line}`;
                        blockCode.appendChild(div);
                    });
                    
                    // New code lines (Green)
                    edit.new_code.split("\n").forEach(line => {
                        const div = document.createElement("div");
                        div.classList.add("diff-line", "ins");
                        div.textContent = `+ ${line}`;
                        blockCode.appendChild(div);
                    });
                    
                    block.appendChild(blockCode);
                    blocksList.appendChild(block);
                });
                
                body.appendChild(blocksList);
            }
            
            card.appendChild(body);
            diffsContainer.appendChild(card);
        });
        
        // Enable and switch to Patches tab
        tabBtnPatches.removeAttribute("disabled");
        tabBtnPatches.click();
    }

    // Index repository submission
    repoForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const repoUrl = document.getElementById("repo-url").value.trim();
        const collectionName = document.getElementById("col-name").value.trim();
        
        if (!repoUrl || !collectionName) return;
        
        setFormState(true);
        appendLogLine(`INFO | Requesting indexing for repository ${repoUrl}...`, "info");
        
        // Switch to logs tab
        document.getElementById("tab-btn-logs").click();
        
        try {
            const res = await fetch("/api/index", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ repo_url: repoUrl, collection_name: collectionName })
            });
            
            if (!res.ok) throw new Error("Index request failed");
            const data = await res.json();
            
            connectStream(data.session_id, async () => {
                await loadCollections();
                appendLogLine(`SUCCESS | Collection "${collectionName}" successfully indexed. Ready for tasks.`, "success");
            });
        } catch (err) {
            console.error("Index submission error:", err);
            appendLogLine(`ERROR | Index request failed: ${err.message}`, "error");
            setFormState(false);
        }
    });

    // Run task submission
    runForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const colName = collectionSelect.value;
        const taskText = document.getElementById("task-request").value.trim();
        
        if (!colName || !taskText) return;
        
        setFormState(true);
        appendLogLine(`INFO | Submitting programming task to collection "${colName}"...`, "info");
        
        // Switch to pipeline tab
        document.getElementById("tab-btn-pipeline").click();
        initializePipeline();
        
        // Disable result tabs while running a new task
        tabBtnPlan.setAttribute("disabled", "true");
        tabBtnPatches.setAttribute("disabled", "true");
        
        try {
            const res = await fetch("/api/run", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ collection_name: colName, request: taskText })
            });
            
            if (!res.ok) throw new Error("Run request failed");
            const data = await res.json();
            
            connectStream(data.session_id, (payload) => {
                // Populate plan and patches
                renderPlan(payload.plan);
                renderPatches(payload);
            });
        } catch (err) {
            console.error("Run submission error:", err);
            appendLogLine(`ERROR | Run request failed: ${err.message}`, "error");
            setFormState(false);
        }
    });

    // Load configuration values from server
    async function loadConfig() {
        try {
            const res = await fetch("/api/config");
            if (!res.ok) throw new Error("Failed to load configuration");
            const data = await res.json();
            
            cfgModelName.value = data.model_name || "";
            cfgModelProvider.value = data.model_provider || "";
            cfgEmbeddingModel.value = data.embedding_model_name || "";
            cfgChunkSize.value = data.chunk_size || 1000;
            cfgChunkOverlap.value = data.chunk_overlap || 200;
            cfgTopK.value = data.default_top_k || 5;
            cfgFetchK.value = data.default_fetch_k || 20;
            cfgThreshold.value = data.default_score_threshold || 0.5;
            cfgContextChars.value = data.max_context_chars || 30000;
            cfgReviewCycles.value = data.max_review_cycles || 4;
            
            if (data.has_api_key) {
                cfgApiKey.value = "••••••••••••";
            } else {
                cfgApiKey.value = "";
            }
        } catch (err) {
            console.error("Error loading config:", err);
            appendLogLine("ERROR | Failed to retrieve settings from server.", "error");
        }
    }

    // Save configuration settings
    configForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        configStatus.className = "config-status";
        configStatus.style.display = "none";
        
        const payload = {
            model_name: cfgModelName.value.trim(),
            model_provider: cfgModelProvider.value.trim(),
            api_key: cfgApiKey.value === "••••••••••••" ? "••••••••••••" : cfgApiKey.value.trim(),
            embedding_model_name: cfgEmbeddingModel.value.trim(),
            chunk_size: parseInt(cfgChunkSize.value, 10),
            chunk_overlap: parseInt(cfgChunkOverlap.value, 10),
            default_top_k: parseInt(cfgTopK.value, 10),
            default_fetch_k: parseInt(cfgFetchK.value, 10),
            default_score_threshold: parseFloat(cfgThreshold.value),
            max_context_chars: parseInt(cfgContextChars.value, 10),
            max_review_cycles: parseInt(cfgReviewCycles.value, 10)
        };
        
        try {
            const res = await fetch("/api/config", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            if (!res.ok) throw new Error("Save request failed");
            
            configStatus.textContent = "Configuration saved successfully.";
            configStatus.classList.add("success");
            configStatus.style.display = "block";
            
            appendLogLine("SUCCESS | Local configuration values successfully saved.", "success");
            
            setTimeout(() => {
                configStatus.style.display = "none";
            }, 3000);
        } catch (err) {
            console.error("Error saving config:", err);
            configStatus.textContent = `Error saving configuration: ${err.message}`;
            configStatus.classList.add("error");
            configStatus.style.display = "block";
            appendLogLine(`ERROR | Save request failed: ${err.message}`, "error");
        }
    });

    // Populate config on load
    loadConfig();

    const pipelineContainer = document.getElementById("pipeline-container");

    function initializePipeline() {
        pipelineContainer.innerHTML = "";
        createStepCard("step-planner", "Step 1: Planner Agent", "running");
        createStepCard("step-reader", "Step 2: Reader Agent", "pending");
        createStepCard("step-writer", "Step 3: Writer Agent", "pending");
        createStepCard("step-reviewer", "Step 4: Reviewer Agent", "pending");
    }

    function createStepCard(id, title, status) {
        const card = document.createElement("div");
        card.id = id;
        card.classList.add("step-card");
        if (status === "running") card.classList.add("active");
        
        const header = document.createElement("div");
        header.classList.add("step-header");
        
        const titleEl = document.createElement("span");
        titleEl.classList.add("step-title");
        titleEl.textContent = title;
        
        const badge = document.createElement("span");
        badge.classList.add("step-badge", status);
        badge.textContent = status;
        
        header.appendChild(titleEl);
        header.appendChild(badge);
        card.appendChild(header);
        
        const body = document.createElement("div");
        body.classList.add("step-body");
        body.textContent = status === "pending" ? "Waiting to execute..." : "Executing agent instructions...";
        card.appendChild(body);
        
        pipelineContainer.appendChild(card);
    }

    function updateStepCardStatus(id, status, text = "") {
        const card = document.getElementById(id);
        if (!card) return;
        
        if (status === "running") {
            card.classList.add("active");
        } else {
            card.classList.remove("active");
        }
        
        const badge = card.querySelector(".step-badge");
        if (badge) {
            badge.className = `step-badge ${status}`;
            badge.textContent = status;
        }
        
        const body = card.querySelector(".step-body");
        if (body && text) {
            body.innerHTML = text;
        }
    }

    function updatePlannerStep(plan) {
        const subtasksHtml = plan.subtasks.map(t => `<li>${t}</li>`).join("");
        const contextHtml = plan.required_context.map(c => `<li>${c}</li>`).join("");
        
        const html = `
            <div style="margin-bottom: 0.75rem; color: var(--text-primary);"><strong>Goal:</strong> ${plan.goal}</div>
            <div class="step-body-grid">
                <div class="step-card-detail">
                    <h4>Task Type</h4>
                    <p>${plan.task_type}</p>
                </div>
                <div class="step-card-detail">
                    <h4>Required Context</h4>
                    <ul class="list-context" style="margin-top: 0.25rem;">${contextHtml}</ul>
                </div>
            </div>
            <div style="margin-top: 0.75rem;">
                <h4 style="font-size: 0.8rem; color: var(--text-primary); margin-bottom: 0.25rem;">Proposed Subtasks</h4>
                <ol class="step-list" style="padding-left: 1rem;">${subtasksHtml}</ol>
            </div>
        `;
        updateStepCardStatus("step-planner", "completed", html);
    }

    function updateReaderStep(readerResult) {
        const filesHtml = readerResult.relevant_files.map(f => `<li>${f}</li>`).join("");
        const html = `
            <div style="margin-bottom: 0.75rem; color: var(--text-primary);"><strong>Analysis:</strong> ${readerResult.analysis}</div>
            <div class="step-body-grid">
                <div class="step-card-detail">
                    <h4>Repository Summary</h4>
                    <p>${readerResult.repository_summary}</p>
                </div>
                <div class="step-card-detail">
                    <h4>Identified Relevant Files</h4>
                    <ul class="step-list" style="margin-top: 0.25rem; list-style-type: square; padding-left: 1rem;">${filesHtml}</ul>
                </div>
            </div>
        `;
        updateStepCardStatus("step-reader", "completed", html);
    }

    function updateWriterStep(writerResult) {
        const changesSummary = writerResult.changes.map(c => {
            return `<li><span class="file-diff-action ${c.action}" style="font-size: 0.7rem; font-weight: 700; margin-right: 0.5rem; text-transform: uppercase;">${c.action}</span> ${c.path} - <em>${c.explanation}</em></li>`;
        }).join("");
        
        const html = `
            <div style="margin-bottom: 0.75rem; color: var(--text-primary);"><strong>Change Summary:</strong> ${writerResult.summary}</div>
            <div>
                <h4 style="font-size: 0.8rem; color: var(--text-primary); margin-bottom: 0.25rem;">Proposed Code Modifications</h4>
                <ul class="step-list" style="list-style-type: none; padding-left: 0; margin-left: 0;">${changesSummary}</ul>
            </div>
        `;
        updateStepCardStatus("step-writer", "completed", html);
    }

    function addReviewerCycle(cycle, reviewResult) {
        const reviewerCard = document.getElementById("step-reviewer");
        if (!reviewerCard) return;
        
        reviewerCard.classList.remove("active");
        const status = reviewResult.approved ? "completed" : "rejected";
        
        const badge = reviewerCard.querySelector(".step-badge");
        if (badge) {
            badge.className = `step-badge ${status}`;
            badge.textContent = status;
        }
        
        const body = reviewerCard.querySelector(".step-body");
        if (body.textContent.includes("Waiting to execute...") || body.textContent.includes("Executing agent instructions...")) {
            body.innerHTML = "";
        }
        
        const cycleCard = document.createElement("div");
        cycleCard.style.marginTop = cycle > 1 ? "1.5rem" : "0";
        cycleCard.style.paddingTop = cycle > 1 ? "1.5rem" : "0";
        if (cycle > 1) {
            cycleCard.style.borderTop = "1px solid var(--border-color)";
        }
        
        const checklist = reviewResult.checklist;
        const issuesHtml = reviewResult.issues && reviewResult.issues.length 
            ? reviewResult.issues.map(i => `<li>[${i.severity.toUpperCase()}] ${i.file ? i.file + ': ' : ''}${i.message} <em>(Rec: ${i.recommendation})</em></li>`).join("")
            : "<li>None</li>";
            
        cycleCard.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                <strong style="color: var(--text-primary); font-size: 0.85rem;">Review Cycle #${cycle} Decision</strong>
                <span class="step-badge ${reviewResult.approved ? 'completed' : 'rejected'}">${reviewResult.approved ? 'Approved' : 'Rejected'}</span>
            </div>
            <div style="margin-bottom: 0.75rem; color: var(--text-secondary);"><strong>Audit Summary:</strong> ${reviewResult.summary}</div>
            <div class="step-body-grid">
                <div class="step-card-detail">
                    <h4>Evaluation Checklist</h4>
                    <div style="font-size: 0.75rem; margin-top: 0.25rem; color: var(--text-secondary);">
                        <div>Goal satisfied: ${checklist.user_request_satisfied ? 'Yes' : 'No'}</div>
                        <div>Plan followed: ${checklist.execution_plan_satisfied ? 'Yes' : 'No'}</div>
                        <div>No security warnings: ${checklist.no_security_regressions ? 'Yes' : 'No'}</div>
                    </div>
                </div>
                <div class="step-card-detail">
                    <h4>Reviewer Issues & Feedback</h4>
                    <ul class="step-list issues" style="list-style-type: square; padding-left: 1rem; margin-top: 0.25rem;">${issuesHtml}</ul>
                </div>
            </div>
        `;
        body.appendChild(cycleCard);
    }

    function addRevisionCycle(cycle, writerResult) {
        const reviewerCard = document.getElementById("step-reviewer");
        if (!reviewerCard) return;
        
        const body = reviewerCard.querySelector(".step-body");
        
        const revisionCard = document.createElement("div");
        revisionCard.style.marginTop = "1rem";
        revisionCard.style.padding = "0.75rem 1rem";
        revisionCard.style.backgroundColor = "var(--bg-color)";
        revisionCard.style.border = "1px solid var(--border-color)";
        revisionCard.style.borderRadius = "4px";
        
        const changesSummary = writerResult.changes.map(c => {
            return `<li><span class="file-diff-action ${c.action}" style="font-size: 0.7rem; font-weight: 700; margin-right: 0.5rem; text-transform: uppercase;">${c.action}</span> ${c.path}</li>`;
        }).join("");
        
        revisionCard.innerHTML = `
            <div style="font-weight: 600; font-size: 0.8rem; margin-bottom: 0.25rem; color: var(--text-primary);">Writer Revision Cycle #${cycle} (Draft Updated)</div>
            <p style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.5rem;"><strong>Summary:</strong> ${writerResult.summary}</p>
            <ul class="step-list" style="list-style-type: none; margin-left: 0; padding-left: 0; font-size: 0.75rem;">${changesSummary}</ul>
        `;
        body.appendChild(revisionCard);
    }
});
