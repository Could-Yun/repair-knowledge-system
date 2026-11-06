<template>
  <router-view v-if="isLoginPage" />
  <div v-else class="app-layout tech-bg">
    <SideMenu />
    <div class="app-main">
      <TopBar />
      <main class="page-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import SideMenu from '@/components/SideMenu.vue'
import TopBar from '@/components/TopBar.vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const isLoginPage = computed(() => route.path === '/login')
</script>
