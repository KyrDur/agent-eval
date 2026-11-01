import {defineConfig} from '@playwright/test'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
const root=path.dirname(fileURLToPath(import.meta.url))
const evidence=path.resolve(root,'../output/experiment-entry-20261022')
// These checks mock only the read API and exercise the real Vue application.
// They do not need a Python backend or call a model service.
export default defineConfig({testDir:'./tests/browser',testMatch:'experiment-entry.spec.js',workers:1,
 timeout:30000,expect:{timeout:6000},outputDir:path.join(evidence,'browser-results'),
 reporter:[['list'],['json',{outputFile:path.join(evidence,'browser-tests.json')}]],
 use:{baseURL:'http://127.0.0.1:5210',viewport:{width:1440,height:1000},trace:'off',video:'off'},
 webServer:{command:'pnpm exec vite --host 127.0.0.1 --port 5210 --strictPort',url:'http://127.0.0.1:5210',reuseExistingServer:false}})
