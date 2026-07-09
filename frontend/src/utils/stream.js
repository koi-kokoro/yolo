export async function createEventStream(
  url,
  { method = 'POST', body, token, headers = {}, onMessage, onError, onDone } = {},
) {
  const controller = new AbortController()
  let done = false

  const requestHeaders = {
    Accept: 'text/event-stream',
    ...headers,
  }

  if (token) {
    requestHeaders.Authorization = `Bearer ${token}`
  }

  let requestBody = body

  if (body && !(body instanceof FormData) && typeof body !== 'string') {
    requestHeaders['Content-Type'] = requestHeaders['Content-Type'] || 'application/json'
    requestBody = JSON.stringify(body)
  }

  const stop = () => {
    if (!done) {
      controller.abort()
      done = true
    }
  }

  const task = fetch(url, {
    method,
    headers: requestHeaders,
    body: requestBody,
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok || !response.body) {
        throw new Error('流式请求失败')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''

      try {
        while (true) {
          const { done: readerDone, value } = await reader.read()

          if (readerDone) break

          buffer += decoder.decode(value, { stream: true })
          const chunks = buffer.split(/\r?\n\r?\n/)
          buffer = chunks.pop() || ''

          for (const chunk of chunks) {
            const lines = chunk.split(/\r?\n/)
            const data = lines
              .filter((line) => line.startsWith('data:'))
              .map((line) => line.slice(5).trimStart())
              .join('\n')

            if (!data) continue

            if (data === '[DONE]') {
              done = true
              onDone?.()
              return
            }

            onMessage?.(data)
          }
        }

        if (buffer.trim()) {
          const data = buffer
            .split(/\r?\n/)
            .filter((line) => line.startsWith('data:'))
            .map((line) => line.slice(5).trimStart())
            .join('\n')

          if (data === '[DONE]') {
            done = true
            onDone?.()
            return
          }

          if (data) {
            onMessage?.(data)
          }
        }

        done = true
        onDone?.()
      } finally {
        reader.releaseLock()
      }
    })
    .catch((error) => {
      if (error.name === 'AbortError') return

      onError?.(error)
      throw error
    })

  return {
    stop,
    abort: stop,
    controller,
    task,
  }
}
