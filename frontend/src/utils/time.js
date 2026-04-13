const IST_TIMEZONE = 'Asia/Kolkata'

const hasExplicitTimezone = (text) => /([zZ]|[+-]\d{2}:\d{2})$/.test(text)

const normalizeTimestampString = (value) => {
  let normalized = value.trim()
  if (!normalized) return normalized

  // Convert "YYYY-MM-DD HH:mm:ss" to ISO-like.
  if (/^\d{4}-\d{2}-\d{2} \d/.test(normalized)) {
    normalized = normalized.replace(' ', 'T')
  }

  // Backend often returns timezone-less ISO strings from SQLite.
  // Treat them as UTC explicitly so IST conversion is correct.
  if (
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?$/.test(normalized) &&
    !hasExplicitTimezone(normalized)
  ) {
    normalized = `${normalized}Z`
  }

  return normalized
}

const toDate = (value) => {
  if (!value) return null
  if (value instanceof Date) {
    const date = new Date(value.getTime())
    return Number.isNaN(date.getTime()) ? null : date
  }

  const raw = typeof value === 'string' ? normalizeTimestampString(value) : value
  const date = new Date(raw)
  return Number.isNaN(date.getTime()) ? null : date
}

const formatParts = (value, options) => {
  const date = toDate(value)
  if (!date) return null

  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: IST_TIMEZONE,
    hour12: false,
    ...options,
  }).formatToParts(date)

  return Object.fromEntries(
    parts
      .filter((part) => part.type !== 'literal')
      .map((part) => [part.type, part.value]),
  )
}

export const formatISTDateTime = (value) => {
  const parts = formatParts(value, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })

  if (!parts) return 'N/A'
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second} IST`
}

export const formatISTShort = (value) => {
  const date = toDate(value)
  if (!date) return 'N/A'

  const base = new Intl.DateTimeFormat('en-IN', {
    timeZone: IST_TIMEZONE,
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)

  return `${base} IST`
}
