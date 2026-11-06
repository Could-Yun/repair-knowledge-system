<template>
  <span class="app-icon" v-html="svg" aria-hidden="true"></span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ name: { type: String, required: true } })

// 统一 24x24 viewBox；line 类用 stroke=currentColor，solid 类用 fill=currentColor
const L = (inner) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`
const F = (inner) => `<svg viewBox="0 0 24 24" fill="currentColor">${inner}</svg>`

const ICONS = {
  home:    L('<path d="M3 11.5 12 4l9 7.5"/><path d="M5 10v10h14V10"/>'),
  bolt:    F('<path d="M13 2 4 14h6l-1 8 9-12h-6l2-8z"/>'),
  search:  L('<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>'),
  clipboard: L('<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4.5V3h6v1.5"/><path d="M8.5 10h7M8.5 14h7M8.5 18h4"/>'),
  check:   L('<path d="M4 12.5 9 17.5 20 6.5"/>'),
  'check-circle': L('<circle cx="12" cy="12" r="9"/><path d="m8.5 12 2.2 2.2L15.5 9.5"/>'),
  x:       L('<path d="M6 6l12 12M18 6 6 18"/>'),
  'x-circle': L('<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>'),
  warning: L('<path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4M12 17.5v.5"/>'),
  folder:  L('<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'),
  'folder-open': L('<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2H3z"/><path d="M3 9h18l-2 9a2 2 0 0 1-2 1.5H5A2 2 0 0 1 3 18z"/>'),
  doc:     L('<path d="M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M14 3v5h5"/>'),
  monitor: L('<rect x="4" y="4" width="16" height="12" rx="2"/><path d="M9 20h6M12 16v4"/>'),
  user:    L('<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5c0-3.6 3.4-5.5 7.5-5.5s7.5 1.9 7.5 5.5"/>'),
  clock:   L('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
  hourglass: L('<path d="M7 3h10M7 21h10M7 3c0 5 10 5 10 14M17 3c0 5-10 5-10 14"/>'),
  edit:    L('<path d="M5 19h3l9-9-3-3-9 9z"/><path d="m13 6 3 3"/>'),
  note:    L('<rect x="5" y="4" width="14" height="16" rx="2"/><path d="M8 9h8M8 13h8M8 17h5"/>'),
  eye:     L('<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'),
  'eye-off': L('<path d="M3 3l18 18"/><path d="M10.6 6.1A10 10 0 0 1 12 6c6 0 10 6 10 6a16 16 0 0 1-3 3.5M6.2 7.7A16 16 0 0 0 2 12s4 6 10 6a10 10 0 0 0 3.6-.7"/>'),
  trash:   L('<path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13"/>'),
  robot:   L('<rect x="5" y="8" width="14" height="11" rx="2"/><path d="M12 4v4M9 13h.01M15 13h.01"/>'),
  plus:    L('<path d="M12 5v14M5 12h14"/>'),
  image:   L('<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m4 18 5-5 4 4 3-3 4 4"/>'),
  camera:  L('<path d="M4 8h3l2-2h6l2 2h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13" r="3.5"/>'),
  save:    L('<path d="M5 4h11l3 3v13H5z"/><path d="M8 4v5h7V4M8 20v-6h8v6"/>'),
  compass: L('<circle cx="12" cy="12" r="9"/><path d="m15 9-2 5-4 2 2-5z"/>'),
  book:    L('<path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 0-3 3z"/><path d="M5 4v16"/>'),
  'volume-on':  L('<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16 9a4 4 0 0 1 0 6"/>'),
  'volume-off': L('<path d="M4 9v6h4l5 4V5L8 9z"/><path d="m17 9 4 6M21 9l-4 6"/>'),
  up:      L('<path d="M12 19V6M6 11l6-6 6 6"/>'),
  lock:    L('<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>'),
  phone:   L('<rect x="7" y="3" width="10" height="18" rx="2"/><path d="M11 18h2"/>'),
  wrench:  L('<path d="M14 7a4 4 0 0 1-5 5L5 16l3 3 4-4a4 4 0 0 0 5-5l-2 2-2-2 2-2z"/>'),
  tools:   L('<path d="M14 7a4 4 0 0 1-5 5L5 16l3 3 4-4a4 4 0 0 0 5-5l-2 2-2-2 2-2z"/>'),
  flag:    L('<path d="M6 21V4M6 4h11l-2 4 2 4H6"/>'),
  menu:    L('<path d="M4 7h16M4 12h16M4 17h16"/>'),
  inbox:   L('<path d="M3 13l3-8h12l3 8v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/><path d="M3 13h5l1 3h6l1-3h5"/>'),
  rocket:  L('<path d="M5 19c0-3 1-5 7-11 3 3 3 3 6 6-6 6-8 7-11 7l-2-2z"/><path d="M9 15l-4 4"/>'),
  dot:     F('<circle cx="12" cy="12" r="6"/>'),
  mic:     L('<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>'),
  pin:     L('<path d="M9 4h6l-1 6 3 3H7l3-3z"/><path d="M12 16v4"/>'),
  web:     L('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3v18M5 7c4 3 10 3 14 0M5 17c4-3 10-3 14 0"/>'),
  target:  L('<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="1"/>'),
  back:    L('<path d="M9 7 4 12l5 5M4 12h11a5 5 0 0 1 0 10"/>'),
  briefcase: L('<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'),
  bulb:    L('<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 1 4 10.5c-.7.7-1 1.3-1 2.5H9c0-1.2-.3-1.8-1-2.5A6 6 0 0 1 12 3z"/>'),
  printer: L('<path d="M7 9V4h10v5"/><rect x="4" y="9" width="16" height="7" rx="1"/><path d="M7 14h10v6H7z"/>'),
  gear:    L('<circle cx="12" cy="12" r="3.2"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.5 5.5l2 2M16.5 16.5l2 2M18.5 5.5l-2 2M7.5 16.5l-2 2"/>'),
  screw:   L('<circle cx="12" cy="12" r="8"/><path d="M9 9l6 6M9 15l6-6"/>'),
  siren:   L('<path d="M6 18a6 6 0 0 1 12 0z"/><path d="M4 21h16M12 6V3M6 8 4 6M18 8l2-2"/>'),
  help:    L('<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 0 1 4 1.8c0 1.7-2.5 2-2.5 3.7M12 17.5v.5"/>'),
}

const svg = computed(() => ICONS[props.name] || ICONS.dot)
</script>

<style scoped>
.app-icon { display: inline-flex; align-items: center; justify-content: center; width: 1em; height: 1em; vertical-align: -0.13em; line-height: 0; }
.app-icon :deep(svg) { width: 1em; height: 1em; display: block; }
</style>
