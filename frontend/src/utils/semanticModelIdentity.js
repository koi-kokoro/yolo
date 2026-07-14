const EMPTY_VALUE = '—'

function firstValue(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== '')
}

export function formatInputSize(value, fallback = EMPTY_VALUE) {
  if (!Array.isArray(value) || value.length === 0) return fallback
  return value.join(' × ')
}

export function resolveRuntimeModelIdentity({ inferenceMetadata, runtimeInfo } = {}) {
  const metadata = inferenceMetadata || {}
  const runtime = runtimeInfo || {}

  return {
    modelName: firstValue(metadata.model_name, runtime.model_name, EMPTY_VALUE),
    modelVersion: firstValue(metadata.model_version, runtime.model_version, EMPTY_VALUE),
    modelSha256: firstValue(metadata.model_sha256, runtime.model_sha256),
    inputSize: firstValue(metadata.input_size, runtime.input_size),
    engine: firstValue(metadata.engine, runtime.engine, EMPTY_VALUE),
    provider: firstValue(metadata.provider, metadata.device, runtime.provider, EMPTY_VALUE),
    source: metadata.model_version || metadata.model_name ? 'inference_metadata' : runtime.model_version || runtime.model_name ? 'runtime' : 'unavailable',
  }
}
