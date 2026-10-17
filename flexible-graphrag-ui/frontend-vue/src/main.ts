import { createApp } from 'vue'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import App from './App.vue'
import { installSourceAuth } from './auth/sourceAuth'

// Alfresco sign-in for search / AI chat (attaches the ticket, asks when the stores need it)
installSourceAuth()

const app = createApp(App)

const vuetify = createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: 'light'
  }
})

app.use(vuetify)
app.mount('#app')