import test from 'node:test'
import assert from 'node:assert/strict'
import { modelPresets, presetConfig, identifyPreset } from '../src/model-presets.js'

test('DeepSeek preset uses its endpoint, current model, max_tokens and explicit non-thinking mode', () => {
  assert.deepEqual(presetConfig('deepseek'), { provider: 'openai-compatible', base_url: 'https://api.deepseek.com/v1',
    model: 'deepseek-flash', completion_token_parameter: 'max_tokens', thinking_mode: 'disabled' })
})
test('Switching service resets DeepSeek-specific settings; custom and restored endpoints remain possible', () => {
  for (const id of ['qwen', 'kimi', 'openai', 'claude', 'custom']) assert.equal(presetConfig(id).thinking_mode, null)
  assert.equal(presetConfig('claude').provider, 'anthropic-compatible')
  assert.equal(identifyPreset({ provider: 'openai-compatible', base_url: 'http://localhost:8124/v1', model: 'custom-name' }), 'custom')
  assert.equal(identifyPreset({ ...presetConfig('deepseek'), model: 'private-model' }), 'deepseek')
  assert(!JSON.stringify(modelPresets).includes('api_key'))
})


test('only explicit acceptance model names trigger a fresh connection preset',async()=>{
 const {isAcceptanceConnection}=await import('../src/model-presets.js')
 assert.equal(isAcceptanceConnection({model:'retrieval-only-local-readiness-fixture'}),true)
 assert.equal(isAcceptanceConnection({model:'phase4-rag'}),true)
 assert.equal(isAcceptanceConnection({base_url:'http://127.0.0.1:1234/v1',model:'my-local-model'}),false)
 assert.equal(isAcceptanceConnection({model:'deepseek-flash'}),false)
})
