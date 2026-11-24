import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
// The demo's two typefaces, bundled with the app rather than fetched from
// Google, so the till looks the same with the internet down.
import '@fontsource/montserrat/700.css'
import '@fontsource/montserrat/800.css'
import '@fontsource/montserrat/900.css'
import '@fontsource/karla/400.css'
import '@fontsource/karla/500.css'
import '@fontsource/karla/600.css'
import '@fontsource/karla/700.css'
import '@fontsource/karla/800.css'
import './styles.css'
import { applyTheme, savedTheme } from './services/theme'

// Before anything is drawn, so the screen never flashes the wrong theme.
applyTheme(savedTheme())

createApp(App).use(createPinia()).use(router).mount('#app')
