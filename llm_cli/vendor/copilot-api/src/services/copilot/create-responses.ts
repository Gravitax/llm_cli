import consola from "consola"
import { events } from "fetch-event-stream"

import { copilotHeaders, copilotBaseUrl } from "~/lib/api-config"
import { HTTPError } from "~/lib/error"
import { state } from "~/lib/state"

// Client for the OpenAI Responses API (`/responses`) exposed by Copilot for the
// models that reject `/chat/completions`. Mirrors create-chat-completions.ts:
// same auth headers and base URL, different endpoint and payload shape.
export const createResponses = async (payload: ResponsesPayload) => {
  if (!state.copilotToken) throw new Error("Copilot token not found")

  const enableVision = payload.input.some(
    (item) =>
      item.type === "message"
      && typeof item.content !== "string"
      && item.content.some((part) => part.type === "input_image"),
  )

  // An agent turn is one that already carries assistant or tool output.
  const isAgentCall = payload.input.some(
    (item) =>
      item.type === "function_call"
      || item.type === "function_call_output"
      || (item.type === "message" && item.role === "assistant"),
  )

  const headers: Record<string, string> = {
    ...copilotHeaders(state, enableVision),
    "X-Initiator": isAgentCall ? "agent" : "user",
  }

  const response = await fetch(`${copilotBaseUrl(state)}/responses`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    consola.error("Failed to create responses", response)
    throw new HTTPError("Failed to create responses", response)
  }

  if (payload.stream) {
    return events(response)
  }

  return (await response.json()) as ResponsesResult
}

// Payload types

export interface ResponsesPayload {
  model: string
  input: Array<ResponsesInputItem>
  instructions?: string | null
  max_output_tokens?: number | null
  temperature?: number | null
  top_p?: number | null
  stream?: boolean | null
  tools?: Array<ResponsesTool> | null
  tool_choice?:
    | "none"
    | "auto"
    | "required"
    | { type: "function"; name: string }
    | null
  user?: string | null
}

export type ResponsesInputItem =
  | ResponsesMessageItem
  | ResponsesFunctionCallItem
  | ResponsesFunctionCallOutputItem

export interface ResponsesMessageItem {
  type: "message"
  role: "user" | "assistant" | "system" | "developer"
  content: string | Array<ResponsesContentPart>
}

export interface ResponsesFunctionCallItem {
  type: "function_call"
  call_id: string
  name: string
  arguments: string
}

export interface ResponsesFunctionCallOutputItem {
  type: "function_call_output"
  call_id: string
  output: string
}

export type ResponsesContentPart =
  | { type: "input_text"; text: string }
  | { type: "output_text"; text: string }
  | { type: "input_image"; image_url: string }

export interface ResponsesTool {
  type: "function"
  name: string
  description?: string
  parameters: Record<string, unknown>
}

// Non-streaming response types

export interface ResponsesResult {
  id: string
  object: "response"
  model: string
  status?: string
  output: Array<ResponsesOutputItem>
  usage?: ResponsesUsage
}

export type ResponsesOutputItem =
  | ResponsesOutputMessage
  | ResponsesReasoningItem
  | ResponsesFunctionCall

export interface ResponsesOutputMessage {
  type: "message"
  role: "assistant"
  content: Array<{ type: "output_text"; text: string }>
}

export interface ResponsesReasoningItem {
  type: "reasoning"
  summary?: Array<{ type: "summary_text"; text: string }>
}

export interface ResponsesFunctionCall {
  type: "function_call"
  id?: string
  call_id: string
  name: string
  arguments: string
}

export interface ResponsesUsage {
  input_tokens: number
  output_tokens: number
  input_tokens_details?: {
    cached_tokens?: number
  }
}

// Streaming event types (subset used by the translation layer)

export interface ResponsesStreamEvent {
  type: string
  // response.output_text.delta / response.function_call_arguments.delta
  delta?: string
  item_id?: string
  output_index?: number
  // response.output_item.added / .done
  item?: ResponsesOutputItem & { id?: string; call_id?: string }
  // response.completed / .incomplete
  response?: ResponsesResult
}
