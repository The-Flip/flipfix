/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';

const { syncPillUI, syncDropdownSelection } = require('./settable_pill.js');

// ── Helpers ────────────────────────────────────────────────────

const UPDATE_URL = '/machines/test-machine/inline-update/';

/**
 * Build a pill-style settable dropdown (sidebar style).
 */
function createPillDropdown({ field, action, pillClass, iconName, label, items }) {
  const wrapper = document.createElement('div');
  wrapper.dataset.updateUrl = UPDATE_URL;

  const dropdown = document.createElement('div');
  dropdown.className = 'dropdown';

  const trigger = document.createElement('button');
  trigger.className = `pill ${pillClass}`;
  trigger.dataset.pillField = field;
  trigger.dataset.action = action;

  if (iconName) {
    const icon = document.createElement('i');
    icon.className = `fa-solid meta fa-${iconName}`;
    icon.dataset.pillIcon = '';
    trigger.appendChild(icon);
  }

  const labelEl = document.createElement('span');
  labelEl.dataset.pillLabel = '';
  labelEl.textContent = label;
  trigger.appendChild(labelEl);

  dropdown.appendChild(trigger);

  const menu = document.createElement('div');
  menu.className = 'dropdown__menu hidden';
  menu.setAttribute('role', 'menu');
  for (const item of items) {
    const el = document.createElement('div');
    el.className = 'dropdown__item';
    if (item.selected) el.classList.add('dropdown__item--selected');
    el.setAttribute('role', 'menuitemradio');
    el.setAttribute('aria-checked', String(!!item.selected));
    el.dataset.value = item.value;
    el.dataset.label = item.label;
    if (item.pillClass) el.dataset.pillClass = item.pillClass;
    if (item.btnClass) el.dataset.btnClass = item.btnClass;
    if (item.icon) el.dataset.icon = item.icon;
    el.textContent = item.label;
    menu.appendChild(el);
  }
  dropdown.appendChild(menu);
  wrapper.appendChild(dropdown);
  return wrapper;
}

/**
 * Build a button-style settable dropdown (mobile action style).
 */
function createButtonDropdown({ field, action, btnClass, iconName, items, titlePrefix }) {
  const wrapper = document.createElement('div');
  wrapper.className = 'mobile-actions';
  wrapper.dataset.updateUrl = UPDATE_URL;

  const dropdown = document.createElement('div');
  dropdown.className = 'dropdown';

  const trigger = document.createElement('button');
  trigger.className = btnClass;
  trigger.dataset.pillField = field;
  trigger.dataset.action = action;
  trigger.dataset.triggerStyle = 'button';
  if (titlePrefix) {
    trigger.title = titlePrefix + 'Good';
    trigger.dataset.titlePrefix = titlePrefix;
  }

  if (iconName) {
    const icon = document.createElement('i');
    icon.className = `fa-solid status-icon fa-${iconName}`;
    trigger.appendChild(icon);
  }

  dropdown.appendChild(trigger);

  const menu = document.createElement('div');
  menu.className = 'dropdown__menu hidden';
  menu.setAttribute('role', 'menu');
  for (const item of items) {
    const el = document.createElement('div');
    el.className = 'dropdown__item';
    if (item.selected) el.classList.add('dropdown__item--selected');
    el.setAttribute('role', 'menuitemradio');
    el.setAttribute('aria-checked', String(!!item.selected));
    el.dataset.value = item.value;
    el.dataset.label = item.label;
    if (item.pillClass) el.dataset.pillClass = item.pillClass;
    if (item.btnClass) el.dataset.btnClass = item.btnClass;
    if (item.icon) el.dataset.icon = item.icon;
    el.textContent = item.label;
    menu.appendChild(el);
  }
  dropdown.appendChild(menu);
  wrapper.appendChild(dropdown);
  return wrapper;
}

const STATUS_ITEMS = [
  {
    value: 'good',
    label: 'Good',
    pillClass: 'pill--status-good',
    btnClass: 'btn--status-good',
    icon: 'check',
    selected: true,
  },
  {
    value: 'fixing',
    label: 'Fixing',
    pillClass: 'pill--status-fixing',
    btnClass: 'btn--status-fixing',
    icon: 'wrench',
    selected: false,
  },
  {
    value: 'broken',
    label: 'Broken',
    pillClass: 'pill--status-broken',
    btnClass: 'btn--status-broken',
    icon: 'circle-xmark',
    selected: false,
  },
];

// ── Tests ──────────────────────────────────────────────────────

describe('syncPillUI', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('updates pill trigger class and label', () => {
    const pill = createPillDropdown({
      field: 'operational_status',
      action: 'update_status',
      pillClass: 'pill--status-good',
      iconName: 'check',
      label: 'Good',
      items: STATUS_ITEMS,
    });
    document.body.appendChild(pill);

    const fixingItem = pill.querySelector('[data-value="fixing"]');
    syncPillUI(UPDATE_URL, 'operational_status', 'fixing', 'Fixing', fixingItem);

    const trigger = pill.querySelector('[data-pill-field]');
    expect(trigger.classList.contains('pill--status-fixing')).toBe(true);
    expect(trigger.classList.contains('pill--status-good')).toBe(false);
    expect(trigger.querySelector('[data-pill-label]').textContent).toBe('Fixing');
  });

  it('updates pill trigger icon', () => {
    const pill = createPillDropdown({
      field: 'operational_status',
      action: 'update_status',
      pillClass: 'pill--status-good',
      iconName: 'check',
      label: 'Good',
      items: STATUS_ITEMS,
    });
    document.body.appendChild(pill);

    const brokenItem = pill.querySelector('[data-value="broken"]');
    syncPillUI(UPDATE_URL, 'operational_status', 'broken', 'Broken', brokenItem);

    const iconEl = pill.querySelector('[data-pill-icon]');
    expect(iconEl.classList.contains('fa-circle-xmark')).toBe(true);
    expect(iconEl.classList.contains('fa-check')).toBe(false);
  });

  it('updates button trigger class', () => {
    const btn = createButtonDropdown({
      field: 'operational_status',
      action: 'update_status',
      btnClass: 'btn btn--dropdown btn--status-good',
      iconName: 'check',
      items: STATUS_ITEMS,
    });
    document.body.appendChild(btn);

    const fixingItem = btn.querySelector('[data-value="fixing"]');
    syncPillUI(UPDATE_URL, 'operational_status', 'fixing', 'Fixing', fixingItem);

    const trigger = btn.querySelector('[data-pill-field]');
    expect(trigger.classList.contains('btn--status-fixing')).toBe(true);
    expect(trigger.classList.contains('btn--status-good')).toBe(false);
    // Base classes preserved
    expect(trigger.classList.contains('btn')).toBe(true);
    expect(trigger.classList.contains('btn--dropdown')).toBe(true);
  });

  it('updates button trigger icon', () => {
    const btn = createButtonDropdown({
      field: 'operational_status',
      action: 'update_status',
      btnClass: 'btn btn--dropdown btn--status-good',
      iconName: 'check',
      items: STATUS_ITEMS,
    });
    document.body.appendChild(btn);

    const brokenItem = btn.querySelector('[data-value="broken"]');
    syncPillUI(UPDATE_URL, 'operational_status', 'broken', 'Broken', brokenItem);

    const iconEl = btn.querySelector('.status-icon');
    expect(iconEl.classList.contains('fa-circle-xmark')).toBe(true);
    expect(iconEl.classList.contains('fa-check')).toBe(false);
  });

  it('updates button trigger title tooltip', () => {
    const btn = createButtonDropdown({
      field: 'operational_status',
      action: 'update_status',
      btnClass: 'btn btn--dropdown btn--status-good',
      iconName: 'check',
      items: STATUS_ITEMS,
      titlePrefix: 'Status: ',
    });
    document.body.appendChild(btn);

    const trigger = btn.querySelector('[data-pill-field]');
    expect(trigger.title).toBe('Status: Good');

    const brokenItem = btn.querySelector('[data-value="broken"]');
    syncPillUI(UPDATE_URL, 'operational_status', 'broken', 'Broken', brokenItem);

    expect(trigger.title).toBe('Status: Broken');
  });

  it('cross-syncs: clicking button item updates sidebar pill', () => {
    const pill = createPillDropdown({
      field: 'operational_status',
      action: 'update_status',
      pillClass: 'pill--status-good',
      iconName: 'check',
      label: 'Good',
      items: STATUS_ITEMS,
    });
    const btn = createButtonDropdown({
      field: 'operational_status',
      action: 'update_status',
      btnClass: 'btn btn--dropdown btn--status-good',
      iconName: 'check',
      items: STATUS_ITEMS,
    });
    document.body.appendChild(pill);
    document.body.appendChild(btn);

    // Simulate clicking "Broken" in the mobile button dropdown
    const mobileItem = btn.querySelector('[data-value="broken"]');
    syncPillUI(UPDATE_URL, 'operational_status', 'broken', 'Broken', mobileItem);

    // Sidebar pill should update
    const pillTrigger = pill.querySelector('[data-pill-field]');
    expect(pillTrigger.classList.contains('pill--status-broken')).toBe(true);
    expect(pillTrigger.classList.contains('pill--status-good')).toBe(false);
    expect(pillTrigger.querySelector('[data-pill-label]').textContent).toBe('Broken');

    // Mobile button should also update
    const btnTrigger = btn.querySelector('[data-pill-field]');
    expect(btnTrigger.classList.contains('btn--status-broken')).toBe(true);
    expect(btnTrigger.classList.contains('btn--status-good')).toBe(false);
  });

  it('cross-syncs: clicking pill item updates mobile button', () => {
    const pill = createPillDropdown({
      field: 'operational_status',
      action: 'update_status',
      pillClass: 'pill--status-good',
      iconName: 'check',
      label: 'Good',
      items: STATUS_ITEMS,
    });
    const btn = createButtonDropdown({
      field: 'operational_status',
      action: 'update_status',
      btnClass: 'btn btn--dropdown btn--status-good',
      iconName: 'check',
      items: STATUS_ITEMS,
    });
    document.body.appendChild(pill);
    document.body.appendChild(btn);

    // Simulate clicking "Fixing" in the sidebar pill dropdown
    const sidebarItem = pill.querySelector('[data-value="fixing"]');
    syncPillUI(UPDATE_URL, 'operational_status', 'fixing', 'Fixing', sidebarItem);

    // Mobile button should update
    const btnTrigger = btn.querySelector('[data-pill-field]');
    expect(btnTrigger.classList.contains('btn--status-fixing')).toBe(true);
    expect(btnTrigger.classList.contains('btn--status-good')).toBe(false);

    // Sidebar pill should also update
    const pillTrigger = pill.querySelector('[data-pill-field]');
    expect(pillTrigger.classList.contains('pill--status-fixing')).toBe(true);
  });

  it('does not touch triggers with a different data-pill-field', () => {
    const statusPill = createPillDropdown({
      field: 'operational_status',
      action: 'update_status',
      pillClass: 'pill--status-good',
      iconName: 'check',
      label: 'Good',
      items: STATUS_ITEMS,
    });
    const locationPill = createPillDropdown({
      field: 'location',
      action: 'update_location',
      pillClass: 'pill--neutral',
      iconName: 'location-dot',
      label: 'Floor',
      items: [{ value: 'floor', label: 'Floor', selected: true }],
    });
    // Both in the same update-url wrapper
    const wrapper = document.createElement('div');
    wrapper.dataset.updateUrl = UPDATE_URL;
    wrapper.appendChild(statusPill.querySelector('.dropdown'));
    wrapper.appendChild(locationPill.querySelector('.dropdown'));
    document.body.appendChild(wrapper);

    const fixingItem = wrapper.querySelector('.dropdown:first-child [data-value="fixing"]');
    syncPillUI(UPDATE_URL, 'operational_status', 'fixing', 'Fixing', fixingItem);

    // Location pill should be untouched
    const locationTrigger = wrapper.querySelectorAll('[data-pill-field]')[1];
    expect(locationTrigger.querySelector('[data-pill-label]').textContent).toBe('Floor');
  });
});

describe('syncDropdownSelection', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('syncs aria-checked and selected class across both dropdowns', () => {
    const pill = createPillDropdown({
      field: 'operational_status',
      action: 'update_status',
      pillClass: 'pill--status-good',
      iconName: 'check',
      label: 'Good',
      items: STATUS_ITEMS,
    });
    const btn = createButtonDropdown({
      field: 'operational_status',
      action: 'update_status',
      btnClass: 'btn btn--dropdown btn--status-good',
      iconName: 'check',
      items: STATUS_ITEMS,
    });
    document.body.appendChild(pill);
    document.body.appendChild(btn);

    syncDropdownSelection(UPDATE_URL, 'operational_status', 'broken');

    // Both dropdowns should mark "broken" as selected
    for (const container of [pill, btn]) {
      const items = container.querySelectorAll('.dropdown__item');
      for (const item of items) {
        const shouldBeSelected = item.dataset.value === 'broken';
        expect(item.classList.contains('dropdown__item--selected')).toBe(shouldBeSelected);
        expect(item.getAttribute('aria-checked')).toBe(String(shouldBeSelected));
      }
    }
  });
});
