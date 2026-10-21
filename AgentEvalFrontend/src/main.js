import { createApp } from 'vue'
import App from './App.vue'
import './design-tokens.css'
import './style.css'
import './ui-foundations.css'
import './calibration.css'
import './visual-workspace.css'
import {installControlAnalytics} from './analytics-controls.js'
import {analytics,loadUmami} from './analytics.js'
loadUmami()
// Touch the local visit clock without recording keys, pointers or form values.
for (const name of ['pointerdown','keydown']) document.addEventListener(name,analytics.activity,{passive:true})
const app=createApp(App)
installControlAnalytics(app)
app.mount('#app')
