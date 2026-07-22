<script setup lang="ts">
import Callboard from './components/Callboard.vue';
import ArchiveRoom from './rooms/ArchiveRoom.vue';
import FaceRoom from './rooms/FaceRoom.vue';
import FoleyRoom from './rooms/FoleyRoom.vue';
import ForgeRoom from './rooms/ForgeRoom.vue';
import HouseFaceRoom from './rooms/HouseFaceRoom.vue';
import HouseStageRoom from './rooms/HouseStageRoom.vue';
import KilnRoom from './rooms/KilnRoom.vue';
import NightShiftRoom from './rooms/NightShiftRoom.vue';
import RackRoom from './rooms/RackRoom.vue';
import ShelfRoom from './rooms/ShelfRoom.vue';
import StageRoom from './rooms/StageRoom.vue';
import {activeTab as active, loadFootage} from './stores/booth';

// one footage fetch feeds the three thumb rows, like the old boot-time load
loadFootage().catch(() => {});

// The eleven rooms, in the old front's tab order. Plain reactive tab state —
// no router; the booth never had deep links (#00063 §1A).
const TABS = [
    {id: 'forge', label: 'Forge', room: ForgeRoom},
    {id: 'kiln', label: 'The Kiln', room: KilnRoom},
    {id: 'rack', label: 'The Curing Rack', room: RackRoom},
    {id: 'shelf', label: 'The Prop Shelf', room: ShelfRoom},
    {id: 'nightshift', label: 'The Night Shift', room: NightShiftRoom},
    {id: 'stage', label: 'The Stage', room: StageRoom},
    {id: 'face', label: 'Face Shop', room: FaceRoom},
    {id: 'foley', label: 'Foley Booth', room: FoleyRoom},
    {id: 'archive', label: 'The Canisters', room: ArchiveRoom},
    {id: 'house-stage', label: 'Stage UI', room: HouseStageRoom},
    {id: 'house-face', label: 'Face Shop UI', room: HouseFaceRoom},
];
</script>

<template>
  <main>
    <header>
      <h1>The Prompter's Box<small>the booth that feeds the lines</small></h1>
    </header>

    <Callboard />

    <nav role="tablist">
      <button
        v-for="t in TABS" :key="t.id" role="tab"
        :aria-selected="active === t.id" :data-tab="t.id"
        @click="active = t.id"
      >{{ t.label }}</button>
    </nav>

    <section v-for="t in TABS" v-show="active === t.id" :id="`tab-${t.id}`" :key="t.id">
      <component :is="t.room" :active="active === t.id" />
    </section>
  </main>
</template>

<style>
header {
  display: flex; flex-wrap: wrap; align-items: baseline; gap: 14px 28px;
  padding: 30px 0 14px; border-bottom: 1px solid var(--drape-edge);
}
h1 {
  font-family: var(--display); font-weight: 500;
  font-size: 26px; letter-spacing: .22em; text-transform: uppercase;
  color: var(--lamp);
}
h1 small { display: block; font-size: 11px; letter-spacing: .3em; color: var(--dim); font-weight: 400; }

nav { display: flex; gap: 4px; margin: 22px 0 26px; flex-wrap: wrap; }
nav button {
  background: none; border: none; border-bottom: 2px solid transparent;
  color: var(--dim); cursor: pointer; border-radius: 0;
  font-family: var(--display); font-size: 13px; letter-spacing: .2em; text-transform: uppercase;
  padding: 8px 16px;
}
nav button[aria-selected="true"] { color: var(--lamp); border-bottom-color: var(--lamp); }
nav button:hover { color: var(--paper); }

@media (max-width: 640px) {
  header { padding-top: 20px; }
}
</style>
