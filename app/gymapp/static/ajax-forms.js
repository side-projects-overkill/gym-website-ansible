// Escape user/server values before interpolating them into innerHTML.
function escapeHtml(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g,
        (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* Progressive enhancement for the handful of frequently-used log/check-in
 * forms (log weight/metric, log an exercise, gym/walk check-in). These all
 * still work as plain HTML forms (POST -> redirect) if JS is unavailable,
 * but with JS on they submit via background fetch() instead, so the page
 * never reloads and the scroll position never jumps around on mobile or
 * desktop. Server side, this is opted into per-request via an
 * X-Requested-With header - see `_wants_json()` in member.py/attendance.py/
 * walking.py - which then returns JSON instead of a redirect. */

function ajaxSubmitForm(form, { onSuccess, onError } = {}) {
    return fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
    })
        .then(async (res) => {
            let data = null;
            try {
                data = await res.json();
            } catch (err) {
                data = null;
            }
            if (!data || data.ok === false) {
                if (onError) onError((data && data.message) || "Something went wrong.");
                return;
            }
            if (onSuccess) onSuccess(data);
        })
        .catch(() => {
            if (onError) onError("Network error - please try again.");
        });
}

function showAjaxNote(anchorEl, message, kind) {
    let note = anchorEl.querySelector(":scope > .ajax-note");
    if (!note) {
        note = document.createElement("div");
        note.className = "ajax-note";
        anchorEl.appendChild(note);
    }
    note.textContent = message;
    note.classList.remove("is-error", "is-success", "is-visible");
    note.classList.add(kind === "error" ? "is-error" : "is-success");
    // Reflow so the transition re-triggers even if a note is already showing.
    void note.offsetWidth;
    note.classList.add("is-visible");
    clearTimeout(note._hideTimer);
    note._hideTimer = setTimeout(() => note.classList.remove("is-visible"), 2600);
}

document.addEventListener("DOMContentLoaded", () => {
    // ---- Inline exercise quick-log, inside the workout accordion --------
    document.querySelectorAll("form.exercise-log-form").forEach((form) => {
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            const button = form.querySelector("button[type=submit]");
            const row = form.closest("tr");
            const lastLoggedCell = row && row.querySelector(".last-log");
            if (button) button.disabled = true;

            ajaxSubmitForm(form, {
                onSuccess: (data) => {
                    if (lastLoggedCell && data.last_log) {
                        const w = data.last_log.weight_kg;
                        const r = data.last_log.reps;
                        const weightText = w != null ? `${escapeHtml(w)}kg` : "-";
                        const repsText = r != null ? ` &times; ${escapeHtml(r)}` : "";
                        const suggestionHtml = data.suggestion
                            ? `<span class="progressive-suggestion">\ud83d\udcc8 ${escapeHtml(data.suggestion)}</span>`
                            : "";
                        lastLoggedCell.innerHTML =
                            `<span class="last-log-value">${weightText}${repsText}</span>` +
                            `<span class="last-log-date">${escapeHtml(data.last_log.log_date)}</span>` +
                            suggestionHtml;
                    }
                    form.reset();
                    showAjaxNote(form, "Logged!", "success");
                },
                onError: (message) => showAjaxNote(form, message, "error"),
            }).finally(() => {
                if (button) button.disabled = false;
            });
        });
    });

    // ---- Gym / walk quick check-in (dashboard + attendance/walking pages) --
    document.querySelectorAll("form.checkin-form").forEach((form) => {
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            const button = form.querySelector("button[type=submit]");
            if (button) button.disabled = true;

            ajaxSubmitForm(form, {
                onSuccess: (data) => {
                    const doneHtml = form.dataset.doneHtml;
                    if (doneHtml) {
                        const wrapper = document.createElement("div");
                        wrapper.innerHTML = doneHtml.trim();
                        form.replaceWith(wrapper.firstElementChild);
                    } else {
                        showAjaxNote(form, data.message, "success");
                    }
                },
                onError: (message) => {
                    if (button) button.disabled = false;
                    showAjaxNote(form, message, "error");
                },
            });
        });
    });

    // ---- Tracker page: "Log a New Entry" ---------------------------------
    const trackerForm = document.getElementById("trackerLogForm");
    if (trackerForm) {
        trackerForm.addEventListener("submit", (event) => {
            event.preventDefault();
            ajaxSubmitForm(trackerForm, {
                onSuccess: (data) => {
                    const tbody = document.getElementById("historyTbody");
                    if (tbody && data.log) {
                        const emptyRow = tbody.querySelector(".history-empty");
                        if (emptyRow) emptyRow.remove();

                        const esc = escapeHtml;
                        const tr = document.createElement("tr");
                        tr.innerHTML =
                            `<td data-label="Date">${esc(data.log.log_date)}</td>` +
                            `<td data-label="Metric">${esc(data.log.label)}</td>` +
                            `<td data-label="Value"><strong>${esc(data.log.value)}</strong> ${esc(data.log.unit)}</td>` +
                            `<td data-label="Note">${esc(data.log.notes)}</td>` +
                            `<td><form method="post" action="/tracker/${encodeURIComponent(data.log.id)}/delete" ` +
                            `onsubmit="return confirm('Delete this entry?');">` +
                            `<button class="icon-delete" type="submit" aria-label="Delete entry" title="Delete">✕</button></form></td>`;
                        tbody.insertBefore(tr, tbody.firstChild);
                    }

                    const valueInput = document.getElementById("value");
                    const notesInput = document.getElementById("notes");
                    if (valueInput) {
                        valueInput.value = "";
                        valueInput.focus();
                    }
                    if (notesInput) notesInput.value = "";

                    showAjaxNote(trackerForm, "Logged!", "success");

                    if (data.log && typeof window.reloadTrendChartIfMatches === "function") {
                        window.reloadTrendChartIfMatches(data.log.metric_key);
                    }
                },
                onError: (message) => showAjaxNote(trackerForm, message, "error"),
            });
        });
    }
});

// ---- "Repeat last" quick-log prefill (Feature C) ---------------------------
// ↻ buttons live inside each exercise's inline log form; clicking one just
// fills the weight/reps inputs with that exercise's last logged values.
document.addEventListener("click", (event) => {
    const btn = event.target.closest(".exercise-repeat");
    if (!btn) return;
    const form = btn.closest("form");
    if (!form) return;
    const weight = form.querySelector('input[name="weight_kg"]');
    const reps = form.querySelector('input[name="reps"]');
    if (weight && btn.dataset.weight) weight.value = btn.dataset.weight;
    if (reps && btn.dataset.reps) reps.value = btn.dataset.reps;
    (reps || weight)?.focus();
});
