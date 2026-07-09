const ERROR_LOG_KEY = 'rsod_error_logs'
const MAX_ERROR_LOGS = 50

function normalizeError(error) {
  if (error instanceof Error) {
    return {
      name: error.name,
      message: error.message,
      stack: error.stack,
    }
  }

  if (typeof error === 'string') {
    return {
      name: 'Error',
      message: error,
    }
  }

  return {
    name: 'UnknownError',
    message: JSON.stringify(error),
  }
}

function readErrorLogs() {
  try {
    const rawLogs = localStorage.getItem(ERROR_LOG_KEY)
    return rawLogs ? JSON.parse(rawLogs) : []
  } catch {
    return []
  }
}

function saveErrorLog(log) {
  try {
    const logs = [log, ...readErrorLogs()].slice(0, MAX_ERROR_LOGS)
    localStorage.setItem(ERROR_LOG_KEY, JSON.stringify(logs))
  } catch {
    // Ignore storage failures so reporting never breaks the app.
  }
}

function reportError(type, error, extra = {}) {
  const log = {
    type,
    error: normalizeError(error),
    extra,
    url: window.location.href,
    timestamp: new Date().toISOString(),
  }

  saveErrorLog(log)
  console.error('[ErrorReporter]', log)

  // Reserved for future backend reporting. Day4 only records errors locally.
}

export function setupErrorReporting(app) {
  if (!app) return

  app.config.errorHandler = (error, instance, info) => {
    reportError('vue', error, {
      info,
      component: instance?.type?.name || instance?.type?.__name || 'AnonymousComponent',
    })
  }

  window.onerror = (message, source, lineno, colno, error) => {
    reportError('window', error || message, {
      source,
      lineno,
      colno,
    })
  }

  window.onunhandledrejection = (event) => {
    reportError('unhandledrejection', event.reason, {
      promise: String(event.promise),
    })
  }
}

export { ERROR_LOG_KEY, MAX_ERROR_LOGS }
