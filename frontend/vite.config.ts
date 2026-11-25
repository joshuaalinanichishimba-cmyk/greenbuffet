import { readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * After a build, writes the list of every built file into the service worker,
 * so the whole system (every screen, not only the ones already opened) is on
 * the device after the first visit. The list also changes the worker's own
 * text, which is how browsers notice there is a new version to install.
 */
function offlineFileList(): Plugin {
  return {
    name: 'gb-offline-file-list',
    apply: 'build',
    closeBundle() {
      const dist = resolve(__dirname, 'dist')
      const files = readdirSync(resolve(dist, 'assets'))
        // Every font comes in two formats and every browser here reads woff2,
        // so the older format is left to be fetched only if ever asked for.
        .filter((f) => !f.endsWith('.woff') && !/-(cyrillic|vietnamese|greek)/.test(f))
        .map((f) => `/assets/${f}`)
      const worker = resolve(dist, 'sw.js')
      const text = readFileSync(worker, 'utf8').replace('const BUILT = []', `const BUILT = ${JSON.stringify(files)}`)
      writeFileSync(worker, text)
    },
  }
}

export default defineConfig({
  plugins: [vue(), offlineFileList()],
  server: {
    port: 5173,
    strictPort: true,
  },
})
