'use strict';

// CAREGIVER_DATA, COLORS, DAYS, DAY_LABELS are injected in the template

function openEdit(idx) {
    const cg = CAREGIVER_DATA[idx];
    const form = document.getElementById('editForm');
    form.action = `/caregivers/${cg.id}/edit`;

    const body = document.getElementById('editBody');
    body.innerHTML = buildFormHTML(cg);
    new bootstrap.Modal(document.getElementById('editModal')).show();
}

function buildFormHTML(cg) {
    const avail = cg.availability || {};

    // Color picker
    const colorPicker = COLORS.map(c => `
        <label class="color-choice">
            <input type="radio" name="color" value="${c}" class="visually-hidden" ${cg.color === c ? 'checked' : ''}>
            <span class="color-dot" style="background:${c}" title="${c}"></span>
        </label>`).join('');

    // Availability table rows
    const dayKeys   = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday'];
    const dayShorts = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    const morningCells = dayKeys.map((d, i) => `
        <td class="text-center">
            <input type="checkbox" class="form-check-input" name="avail_${d}_morning"
                   id="em_${d}" ${(avail[d] && avail[d].morning) ? 'checked' : ''}>
        </td>`).join('');
    const eveningCells = dayKeys.map((d, i) => `
        <td class="text-center">
            <input type="checkbox" class="form-check-input" name="avail_${d}_evening"
                   id="ee_${d}" ${(avail[d] && avail[d].evening) ? 'checked' : ''}>
        </td>`).join('');

    return `<div class="row g-3">
        <div class="col-12"><h6 class="text-primary border-bottom pb-1 mb-0">Basic Information</h6></div>

        <div class="col-md-6">
            <label class="form-label fw-semibold">Full Name <span class="text-danger">*</span></label>
            <input type="text" class="form-control" name="name" value="${esc(cg.name)}" required maxlength="100">
        </div>
        <div class="col-md-6">
            <label class="form-label fw-semibold">Email <span class="text-danger">*</span></label>
            <input type="email" class="form-control" name="email" value="${esc(cg.email)}" required maxlength="120">
        </div>
        <div class="col-md-6">
            <label class="form-label fw-semibold">Phone</label>
            <input type="tel" class="form-control" name="phone" value="${esc(cg.phone)}" maxlength="20">
        </div>
        <div class="col-md-3">
            <label class="form-label fw-semibold">Pay Rate ($/hr)</label>
            <div class="input-group">
                <span class="input-group-text">$</span>
                <input type="number" class="form-control" name="pay_rate" step="0.01" min="0" max="999"
                       value="${cg.pay_rate || ''}">
            </div>
        </div>
        <div class="col-md-3">
            <label class="form-label fw-semibold">Employment</label>
            <select class="form-select" name="employment_type">
                <option value="part_time" ${cg.employment_type !== 'full_time' ? 'selected' : ''}>Part Time</option>
                <option value="full_time"  ${cg.employment_type === 'full_time'  ? 'selected' : ''}>Full Time</option>
            </select>
        </div>

        <div class="col-12 mt-1"><h6 class="text-primary border-bottom pb-1 mb-0">App Settings</h6></div>
        <div class="col-md-4">
            <label class="form-label fw-semibold">Calendar Color</label>
            <div class="color-picker-row">${colorPicker}</div>
        </div>
        <div class="col-md-4"></div>
        <div class="col-md-4 d-flex flex-column justify-content-end">
            <div class="form-check mb-2">
                <input type="checkbox" class="form-check-input" name="is_admin" id="editIsAdmin"
                       ${cg.role === 'admin' ? 'checked' : ''} ${cg.id === CURRENT_USER_ID ? 'disabled' : ''}>
                <label class="form-check-label" for="editIsAdmin">Administrator (can sign in)</label>
                ${cg.id === CURRENT_USER_ID ? '<div class="form-text mt-0">You cannot remove your own admin access.</div>' : ''}
            </div>
            <div class="form-check mb-2">
                <input type="checkbox" class="form-check-input" name="is_active" id="editIsActive"
                       ${cg.is_active ? 'checked' : ''}>
                <label class="form-check-label" for="editIsActive">Active</label>
            </div>
            <div class="form-check">
                <input type="checkbox" class="form-check-input" name="receives_full_schedule" id="editFullSched"
                       ${cg.receives_full_schedule ? 'checked' : ''}>
                <label class="form-check-label" for="editFullSched">Receives full schedule email</label>
            </div>
        </div>

        <div class="col-12 mt-1"><h6 class="text-primary border-bottom pb-1 mb-0">Emergency Contact</h6></div>
        <div class="col-md-6">
            <label class="form-label fw-semibold">Contact Name</label>
            <input type="text" class="form-control" name="emergency_contact_name"
                   value="${esc(cg.emergency_contact_name)}" maxlength="100">
        </div>
        <div class="col-md-6">
            <label class="form-label fw-semibold">Contact Phone</label>
            <input type="tel" class="form-control" name="emergency_contact_phone"
                   value="${esc(cg.emergency_contact_phone)}" maxlength="20">
        </div>

        <div class="col-12 mt-1"><h6 class="text-primary border-bottom pb-1 mb-0">Availability</h6></div>
        <div class="col-12">
            <table class="table table-bordered table-sm avail-table mb-0">
                <thead class="table-light"><tr>
                    <th style="width:110px"></th>
                    ${dayShorts.map(d => `<th class="text-center">${d}</th>`).join('')}
                </tr></thead>
                <tbody>
                    <tr>
                        <td class="small fw-semibold text-muted">
                            <i class="bi bi-sun" style="color:#ffc107"></i> Morning<br>
                            <span class="fw-normal">8am–2pm</span>
                        </td>${morningCells}</tr>
                    <tr>
                        <td class="small fw-semibold text-muted">
                            <i class="bi bi-moon" style="color:#0d6efd"></i> Evening<br>
                            <span class="fw-normal">5pm–10pm</span>
                        </td>${eveningCells}</tr>
                </tbody>
            </table>
        </div>

        <div class="col-12 mt-1"><h6 class="text-primary border-bottom pb-1 mb-0">Login Password</h6></div>
        <div class="col-md-6">
            <label class="form-label fw-semibold">New Password</label>
            <input type="password" class="form-control" name="password" autocomplete="new-password"
                   minlength="8" placeholder="Leave blank to keep existing">
            <div class="form-text">Required for administrators. At least 8 characters.</div>
        </div>
    </div>`;
}

function esc(str) {
    return String(str ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
