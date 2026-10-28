import { useCallback } from 'react'
import { useToast } from './toast-context'

/**
 * Wraps a mutation: toasts success/failure and refreshes data afterwards.
 * Never rejects; resolves to { ok, data } or { ok: false, error }.
 * Pass { inline: true } when the caller shows the error itself (e.g. inside a modal form).
 */
export function useAction(afterSuccess) {
  const toast = useToast()
  return useCallback(
    async (fn, successMessage, { inline = false } = {}) => {
      try {
        const data = await fn()
        if (successMessage) toast.success(successMessage)
        afterSuccess?.()
        return { ok: true, data }
      } catch (err) {
        if (!inline) toast.error(err.message)
        return { ok: false, error: err.message }
      }
    },
    [toast, afterSuccess],
  )
}
