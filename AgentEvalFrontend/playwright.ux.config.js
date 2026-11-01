import base from './playwright.config.js'
import {defineConfig} from '@playwright/test'
import path from 'node:path'
const evidence=path.resolve('../output/ux-implementation-20261030/browser')
export default defineConfig({...base,testMatch:'ux-simplification.spec.js',outputDir:path.join(evidence,'results'),
 reporter:[['list'],['json',{outputFile:path.join(evidence,'tests.json')}]],
 use:{...base.use,viewport:{width:1440,height:1000}},
 webServer:base.webServer.map(server=>({...server,env:{...server.env,AGENTEVAL_TEST_EVIDENCE_DIR:evidence}}))})
