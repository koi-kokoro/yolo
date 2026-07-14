import { formatInputSize, resolveRuntimeModelIdentity } from '@/utils/semanticModelIdentity'

describe('semantic model identity', () => {
  const runtimeInfo = {
    model_name: 'YOLO26s Semantic',
    model_version: 'v2-hr1024-yolo26s-sem-full-e50-b4-m1',
    model_sha256: 'a27221923f7ee87a104c8a749e2629de58c522091bcdef273240d197ee78d634',
    input_size: [1024, 1024],
    engine: 'ONNX Runtime',
    provider: 'CPUExecutionProvider',
  }

  it('uses runtime metadata as the deployed model identity', () => {
    expect(resolveRuntimeModelIdentity({ runtimeInfo })).toEqual({
      modelName: 'YOLO26s Semantic',
      modelVersion: 'v2-hr1024-yolo26s-sem-full-e50-b4-m1',
      modelSha256: 'a27221923f7ee87a104c8a749e2629de58c522091bcdef273240d197ee78d634',
      inputSize: [1024, 1024],
      engine: 'ONNX Runtime',
      provider: 'CPUExecutionProvider',
      source: 'runtime',
    })
    expect(formatInputSize(runtimeInfo.input_size)).toBe('1024 × 1024')
  })

  it('prefers task inference metadata over the current runtime', () => {
    const identity = resolveRuntimeModelIdentity({
      runtimeInfo,
      inferenceMetadata: {
        model_name: 'Archived Runtime Model',
        model_version: 'inference-version',
        input_size: [768, 768],
        engine: 'task-engine',
        provider: 'task-provider',
      },
    })

    expect(identity).toMatchObject({
      modelName: 'Archived Runtime Model',
      modelVersion: 'inference-version',
      inputSize: [768, 768],
      engine: 'task-engine',
      provider: 'task-provider',
      source: 'inference_metadata',
    })
  })

  it('does not substitute a database task association for runtime identity', () => {
    expect(resolveRuntimeModelIdentity({
      runtimeInfo: null,
      inferenceMetadata: null,
      taskModelVersion: { version: 'baseline-e50-i512-b2' },
    })).toEqual({
      modelName: '—',
      modelVersion: '—',
      modelSha256: undefined,
      inputSize: undefined,
      engine: '—',
      provider: '—',
      source: 'unavailable',
    })
    expect(formatInputSize(undefined)).toBe('—')
  })
})
