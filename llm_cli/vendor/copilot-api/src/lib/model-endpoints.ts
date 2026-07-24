// Some Copilot models are only served by the OpenAI Responses API
// (`/responses`) and reject `/chat/completions` with
// `unsupported_api_for_model`. The upstream `/models` catalog does not flag the
// endpoint, so routing uses this prefix list as a fast path; anything missing
// from it is caught by the runtime fallback keyed on ERROR_UNSUPPORTED_API.

// Model id prefixes known to be served exclusively by `/responses`.
const RESPONSES_ONLY_PREFIXES = [
  "gpt-5.6-",
  "gpt-5.5",
  "gpt-5.4",
  "gpt-5.3-codex",
]

// Upstream error code returned when a model rejects `/chat/completions`.
export const ERROR_UNSUPPORTED_API = "unsupported_api_for_model"

// True when the model is already known to need `/responses`.
export const usesResponsesApi = (model: string): boolean =>
  RESPONSES_ONLY_PREFIXES.some((prefix) => model.startsWith(prefix))
