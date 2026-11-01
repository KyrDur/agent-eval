import {defineConfig} from '@playwright/test'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
const root=path.dirname(fileURLToPath(import.meta.url))
const evidence=path.resolve(root,'../output/score-check-20261022')
// Exercise the real Vue application against saved read fixtures; no model calls.
export default defineConfig({testDir:'./tests/browser',testMatch:'score-check.spec.js',workers:1,
 timeout:30000,expect:{timeout:6000},outputDir:path.join(evidence,'browser-results'),
 reporter:[['list'],['json',{outputFile:path.join(evidence,'browser-tests.json')}]],
 use:{baseURL:'http://127.0.0.1:5211',viewport:{width:1440,height:1000},trace:'off',video:'off'},
 webServer:{command:'pnpm exec vite --host 127.0.0.1 --port 5211 --strictPort',url:'http://127.0.0.1:5211',reuseExistingServer:false}})
