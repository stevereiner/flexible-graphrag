import { createApp, h } from 'vue'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import App from './App.vue'
import { installSourceAuth } from './auth/sourceAuth'
import { installApiConnection } from './apiConnection'
import { isTauri } from './desktop/tauri'
import { syncLocalRoots } from './desktop/localRoots'
import BackendGate from './desktop/BackendGate.vue'

// Alfresco sign-in for search / AI chat (attaches the ticket, asks when the stores need it)
installSourceAuth()

// The desktop app gives the backend back the local folders the user added (it keeps them in
// memory only)
const sendLocalRoots = () => {
  syncLocalRoots().then((r) => { if (!r.ok) console.warn('Local folders not sent to the backend:', r.message) })
}

const vuetify = createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: 'light'
  }
})

// Backend URL + API token first (the first requests go out on mount). In the desktop app the
// backend may still be starting: BackendGate waits for it before rendering the app.
installApiConnection().finally(() => {
  const app = isTauri()
    ? createApp({ render: () => h(BackendGate, { onReady: sendLocalRoots }, { default: () => h(App) }) })
    : createApp(App)
  app.use(vuetify)
  app.mount('#app')
})
