import {defineConfig} from '@playwright/test'
import path from 'node:path'
const evidence=path.resolve('../output/run-recovery-20261022')
export default defineConfig({testDir:'./tests/browser',testMatch:'run-recovery.spec.js',workers:1,
 timeout:30000,expect:{timeout:6000},outputDir:path.join(evidence,'browser-results'),
 reporter:[['list'],['json',{outputFile:path.join(evidence,'browser-tests.json')}]],
 use:{baseURL:'http://127.0.0.1:5212',viewport:{width:1440,height:1000},trace:'off',video:'off'},
 webServer:{command:'pnpm exec vite --host 127.0.0.1 --port 5212 --strictPort',url:'http://127.0.0.1:5212',reuseExistingServer:false}})
