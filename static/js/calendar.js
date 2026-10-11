'use strict';

const CSRF = () => document.querySelector('meta[name="csrf-token"]').content;

const jsonFetch = (url, method, body) =>
    fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF() },
        body: body ? JSON.stringify(body) : undefined,
    }).then(r => {
        if (r.status === 401) {
            alert('Your session has expired. Please sign in again.');
            window.location.href = '/auth/login?next=/calendar';
        }
        return r;
    });

const pad2 = n => String(n).padStart(2, '0');
const hhmm = d => `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
const fmtTime = d => {
    const h = d.getHours() % 12 || 12;
    const m = d.getMinutes() ? `:${pad2(d.getMinutes())}` : '';
    return `${h}${m}${d.getHours() < 12 ? 'am' : 'pm'}`;
};
const shiftTimes = (start, end) => {
    if (!end || end.toDateString() !== start.toDateString()) return null;
    return { start_time: hhmm(start), end_time: hhmm(end), shift_type: start.getHours() < 12 ? 'morning' : 'evening' };
};
const showWarning = data => { if (data && data.warning) alert('Heads up: ' + data.warning); };

// Shared by drag-move and resize: save the event's new date/time or revert
function saveMovedShift(info) {
    const times = shiftTimes(info.event.start, info.event.end);
    if (!times) {
        info.revert();
        alert('Shifts cannot run past midnight.');
        return;
    }
    const newDate = info.event.startStr.slice(0, 10);
    jsonFetch(`/api/events/${info.event.id}`, 'PUT', { date: newDate, ...times })
        .then(r => r.json().then(data => ({ ok: r.ok, data })))
        .then(({ ok, data }) => {
            if (!ok) { info.revert(); alert(data.error || 'Failed to update shift.'); return; }
            showWarning(data);
            window._cal.refetchEvents();
            refreshSummary(window._cal);
        })
        .catch(() => info.revert());
}

// ── FullCalendar init ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const calEl = document.getElementById('calendar');

    const calendar = new FullCalendar.Calendar(calEl, {
        initialView: 'timeGridWeek',
        headerToolbar: {
            left:   'prev,next today',
            center: 'title',
            right:  'dayGridMonth,timeGridWeek,timeGridDay',
        },
        slotMinTime: '07:00:00',
        slotMaxTime: '23:00:00',
        slotDuration: '01:00:00',
        height: 'calc(100vh - 210px)',
        expandRows: true,
        editable: IS_ADMIN,
        nowIndicator: true,
        firstDay: 0,                    // start on Sunday
        droppable: IS_ADMIN,

        // ── Tile dropped onto calendar → create shift immediately ──────────
        eventReceive(info) {
            const caregiverId = info.draggedEl.dataset.caregiverId;   // reliable source
            const dropDate    = info.event.startStr.slice(0, 10);

            // Timed views use the dropped time; month view (all-day drop) falls back to a morning shift
            let body = { caregiver_id: caregiverId, date: dropDate, shift_type: 'morning', notes: '' };
            if (!info.event.allDay) {
                const times = shiftTimes(info.event.start, info.event.end);
                if (!times) {
                    info.event.remove();
                    alert('Shifts cannot run past midnight.');
                    return;
                }
                body = { ...body, ...times };
            }

            info.event.remove(); // remove placeholder; real event added after API call

            jsonFetch('/api/events', 'POST', body)
            .then(r => r.json().then(data => ({ ok: r.ok, data })))
            .then(({ ok, data }) => {
                if (!ok || data.error) { alert(data.error || 'Failed to create shift.'); return; }
                showWarning(data);
                window._cal.refetchEvents();
                refreshSummary(window._cal);
            })
            .catch(err => alert('Failed to create shift: ' + err.message));
        },

        // ── Load events from API ──
        events(info, success, fail) {
            fetch(`/api/events?start=${info.startStr}&end=${info.endStr}`,
                  { headers: { 'X-CSRFToken': CSRF() } })
                .then(r => {
                    if (r.status === 401) window.location.href = '/auth/login?next=/calendar';
                    return r.json();
                })
                .then(success)
                .catch(fail);
        },

        // ── Render custom event HTML ──
        eventContent(arg) {
            const p = arg.event.extendedProps;
            const { start, end } = arg.event;
            // Built from live start/end so the label tracks the drag position
            const label = start && end && !arg.event.allDay
                ? `${fmtTime(start)}\u2013${fmtTime(end)}`
                : (p.shift_label || '');
            return {
                html: `<div class="fc-event-custom">
                    <div class="fc-event-name">${esc(arg.event.title)}</div>
                    <div class="fc-event-shift">${esc(label)}</div>
                    ${p.notes ? `<div class="fc-event-notes"><i class="bi bi-sticky"></i> ${esc(p.notes)}</div>` : ''}
                </div>`,
            };
        },

        // ── Click event ──
        eventClick(info) {
            if (IS_ADMIN) openEditModal(info.event);
            else          openViewModal(info.event);
        },

        // ── Drag to new date/time, or resize to change length ──
        eventDrop: saveMovedShift,
        eventResize: saveMovedShift,
    });

    calendar.render();
    refreshSummary(calendar);
    window._cal = calendar;

    // ── External drag: caregiver tiles → calendar ──────────────────────
    if (IS_ADMIN) {
        const tilesEl = document.getElementById('caregiver-tiles');
        if (tilesEl) {
            new FullCalendar.Draggable(tilesEl, {
                itemSelector: '.caregiver-tile',
                eventData(el) {
                    return {
                        title: el.dataset.caregiverName,
                        duration: '06:00',
                        backgroundColor: el.dataset.color,
                        borderColor: el.dataset.color,
                        textColor: '#ffffff',
                        extendedProps: {
                            caregiver_id: el.dataset.caregiverId,
                            caregiver_name: el.dataset.caregiverName,
                        },
                    };
                },
            });
        }
    }
});

// ── Weekly summary bar ─────────────────────────────────────────────────────
function refreshSummary(cal) {
    const ws = cal
        ? cal.view.currentStart.toISOString().slice(0, 10)
        : new Date().toISOString().slice(0, 10);

    fetch(`/api/weekly-summary?week_start=${ws}`)
        .then(r => r.json())
        .then(data => {
            const dots = data.caregivers.map(c =>
                `<span style="color:${c.color}">●</span><span class="text-muted"> ${esc(c.name)}: ${c.hours}h</span>`
            ).join('&nbsp; ');

            if (!data.target_hours) {
                document.getElementById('weekSummary').innerHTML = dots;
                return;
            }
            const pct = Math.min(100, Math.round((data.total_hours / data.target_hours) * 100));
            const cls = pct >= 100 ? 'text-success' : pct >= 70 ? 'text-warning' : 'text-danger';

            document.getElementById('weekSummary').innerHTML =
                `<span class="${cls} fw-bold">${data.total_hours}h</span>`
                + `<span class="text-muted">/${data.target_hours}h &nbsp;·&nbsp;</span>`
                + dots;
        })
        .catch(() => {});
}

// ── Add Shift ──────────────────────────────────────────────────────────────
function submitAddShift() {
    const caregiverId = document.getElementById('addCaregiver').value;
    const shiftDate   = document.getElementById('addDate').value;
    const shiftType   = document.querySelector('input[name="addShiftType"]:checked')?.value;
    const notes       = document.getElementById('addNotes').value.trim();

    if (!caregiverId || !shiftDate) {
        alert('Please select a caregiver and date.');
        return;
    }

    jsonFetch('/api/events', 'POST', { caregiver_id: caregiverId, date: shiftDate, shift_type: shiftType, notes })
        .then(r => r.json())
        .then(data => {
            if (data.error) { alert(data.error); return; }
            showWarning(data);
            window._cal.refetchEvents();
            refreshSummary(window._cal);
            hideModal('addShiftModal');
            // reset
            document.getElementById('addCaregiver').value = '';
            document.getElementById('addNotes').value = '';
            document.querySelector('input[name="addShiftType"][value="morning"]').checked = true;
        });
}

// ── Edit Shift ─────────────────────────────────────────────────────────────
function openEditModal(event) {
    const p = event.extendedProps;
    document.getElementById('editShiftId').value   = event.id;
    document.getElementById('editDate').value       = event.startStr.slice(0, 10);
    document.getElementById('editCaregiver').value  = p.caregiver_id;
    document.getElementById('editNotes').value      = p.notes || '';
    document.getElementById(p.shift_type === 'morning' ? 'editMorning' : 'editEvening').checked = true;
    showModal('editShiftModal');
}

function submitEditShift() {
    const id          = document.getElementById('editShiftId').value;
    const caregiverId = document.getElementById('editCaregiver').value;
    const shiftDate   = document.getElementById('editDate').value;
    const shiftType   = document.querySelector('input[name="editShiftType"]:checked')?.value;
    const notes       = document.getElementById('editNotes').value.trim();

    jsonFetch(`/api/events/${id}`, 'PUT', { caregiver_id: caregiverId, date: shiftDate, shift_type: shiftType, notes })
        .then(r => r.json())
        .then(data => {
            if (data.error) { alert(data.error); return; }
            showWarning(data);
            window._cal.refetchEvents();
            refreshSummary(window._cal);
            hideModal('editShiftModal');
        });
}

// ── Copy previous week into the visible week ────────────────────────────────────────────────────────────
function copyLastWeek() {
    const cal = window._cal;
    if (cal.view.type !== 'timeGridWeek') {
        alert('Switch to week view first.');
        return;
    }
    const ws = cal.view.currentStart;
    const weekStart = `${ws.getFullYear()}-${pad2(ws.getMonth() + 1)}-${pad2(ws.getDate())}`;
    if (!confirm(`Copy last week's shifts into the week of ${weekStart}?`)) return;

    jsonFetch('/api/copy-week', 'POST', { week_start: weekStart })
        .then(r => r.json())
        .then(data => {
            if (data.error) { alert(data.error); return; }
            alert(`Copied ${data.copied} shift(s)` + (data.skipped ? `, skipped ${data.skipped} already present or inactive.` : '.'));
            cal.refetchEvents();
            refreshSummary(cal);
        })
        .catch(err => alert('Failed to copy week: ' + err.message));
}

function deleteShift() {
    if (!confirm('Delete this shift?')) return;
    const id = document.getElementById('editShiftId').value;
    jsonFetch(`/api/events/${id}`, 'DELETE')
        .then(r => {
            if (r.ok) {
                window._cal.refetchEvents();
                refreshSummary(window._cal);
                hideModal('editShiftModal');
            }
        });
}

// ── View (read-only) Shift ─────────────────────────────────────────────────
function openViewModal(event) {
    const p = event.extendedProps;
    document.getElementById('viewShiftTitle').textContent = event.title;
    document.getElementById('viewShiftBody').innerHTML = `
        <dl class="row mb-0">
            <dt class="col-sm-4">Shift</dt>
            <dd class="col-sm-8">${esc(p.shift_label)}</dd>
            <dt class="col-sm-4">Date</dt>
            <dd class="col-sm-8">${esc(event.startStr.slice(0, 10))}</dd>
            <dt class="col-sm-4">Duration</dt>
            <dd class="col-sm-8">${p.duration_hours}h</dd>
            ${p.notes ? `<dt class="col-sm-4">Notes</dt><dd class="col-sm-8">${esc(p.notes)}</dd>` : ''}
        </dl>`;
    showModal('viewShiftModal');
}

// ── Send schedule via Power Automate ──────────────────────────────────────
function sendSchedule() {
    if (!confirm('Send the weekly schedule to all recipients via Power Automate?')) return;
    const btn = document.getElementById('sendBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Sending…';

    const weekStart = window._cal.view.currentStart.toISOString().slice(0, 10);

    jsonFetch('/api/send-schedule', 'POST', { week_start: weekStart })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'success') {
                alert('Schedule sent successfully!');
            } else if (data.status === 'no_webhook') {
                alert('Power Automate webhook URL not configured.\n\nSet the POWER_AUTOMATE_WEBHOOK_URL environment variable to enable email sending.\n\nYour schedule payload is in the browser console.');
                console.log('Schedule payload:', data.payload);
            } else {
                alert('Error sending schedule:\n' + data.message);
            }
        })
        .catch(() => alert('Network error. Please try again.'))
        .finally(() => {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-send me-1"></i>Send Schedule';
        });
}

// ── Helpers ────────────────────────────────────────────────────────────────
function esc(str) {
    return String(str ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function showModal(id) {
    new bootstrap.Modal(document.getElementById(id)).show();
}

function hideModal(id) {
    bootstrap.Modal.getInstance(document.getElementById(id))?.hide();
}
