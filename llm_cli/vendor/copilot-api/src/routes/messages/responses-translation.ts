import {
  type ResponsesContentPart,
  type ResponsesInputItem,
  type ResponsesPayload,
  type ResponsesResult,
  type ResponsesStreamEvent,
  type ResponsesTool,
} from "~/services/copilot/create-responses"

import {
  type AnthropicAssistantMessage,
  type AnthropicMessage,
  type AnthropicMessagesPayload,
  type AnthropicResponse,
  type AnthropicStreamEventData,
  type AnthropicTextBlock,
  type AnthropicThinkingBlock,
  type AnthropicTool,
  type AnthropicToolResultBlock,
  type AnthropicToolUseBlock,
  type AnthropicUserContentBlock,
  type AnthropicUserMessage,
} from "./anthropic-types"

// The Responses API rejects a `user` longer than this; Claude Code sends
// identifiers well past it, so the value is truncated rather than dropped to
// keep per-user grouping upstream.
const MAX_USER_LENGTH = 64

// Request translation: Anthropic Messages -> OpenAI Responses

export function translateToResponses(
  payload: AnthropicMessagesPayload,
): ResponsesPayload {
  return {
    model: payload.model,
    instructions: handleSystemPrompt(payload.system),
    input: payload.messages.flatMap(translateMessage),
    max_output_tokens: payload.max_tokens,
    temperature: payload.temperature,
    top_p: payload.top_p,
    stream: payload.stream,
    user: truncateUser(payload.metadata?.user_id),
    tools: translateTools(payload.tools),
    tool_choice: translateToolChoice(payload.tool_choice),
  }
}

function truncateUser(user: string | undefined): string | undefined {
  if (!user) return undefined
  return user.length > MAX_USER_LENGTH ? user.slice(0, MAX_USER_LENGTH) : user
}

function handleSystemPrompt(
  system: AnthropicMessagesPayload["system"],
): string | null {
  if (!system) return null
  if (typeof system === "string") return system
  return system.map((block) => block.text).join("\n\n")
}

function translateMessage(message: AnthropicMessage): Array<ResponsesInputItem> {
  return message.role === "user" ?
      handleUserMessage(message)
    : handleAssistantMessage(message)
}

function handleUserMessage(
  message: AnthropicUserMessage,
): Array<ResponsesInputItem> {
  if (typeof message.content === "string") {
    return [
      { type: "message", role: "user", content: message.content },
    ]
  }

  const items: Array<ResponsesInputItem> = []

  // Tool results become their own function_call_output items, kept before the
  // remaining user content to preserve call -> output -> user ordering.
  for (const block of message.content) {
    if (block.type === "tool_result") {
      items.push({
        type: "function_call_output",
        call_id: block.tool_use_id,
        output: mapToolResultContent(block),
      })
    }
  }

  const contentParts = mapUserContent(
    message.content.filter((block) => block.type !== "tool_result"),
  )
  if (contentParts.length > 0) {
    items.push({ type: "message", role: "user", content: contentParts })
  }

  return items
}

function mapToolResultContent(block: AnthropicToolResultBlock): string {
  return typeof block.content === "string" ? block.content : ""
}

function mapUserContent(
  blocks: Array<AnthropicUserContentBlock>,
): Array<ResponsesContentPart> {
  const parts: Array<ResponsesContentPart> = []
  for (const block of blocks) {
    if (block.type === "text") {
      parts.push({ type: "input_text", text: block.text })
    } else if (block.type === "image") {
      parts.push({
        type: "input_image",
        image_url: `data:${block.source.media_type};base64,${block.source.data}`,
      })
    }
  }
  return parts
}

function handleAssistantMessage(
  message: AnthropicAssistantMessage,
): Array<ResponsesInputItem> {
  if (typeof message.content === "string") {
    return [
      {
        type: "message",
        role: "assistant",
        content: [{ type: "output_text", text: message.content }],
      },
    ]
  }

  const items: Array<ResponsesInputItem> = []
  const textParts: Array<ResponsesContentPart> = []

  for (const block of message.content) {
    if (block.type === "text") {
      textParts.push({ type: "output_text", text: block.text })
    } else if (block.type === "tool_use") {
      items.push({
        type: "function_call",
        call_id: block.id,
        name: block.name,
        arguments: JSON.stringify(block.input),
      })
    }
    // thinking blocks are not replayed to the Responses API.
  }

  if (textParts.length > 0) {
    items.unshift({
      type: "message",
      role: "assistant",
      content: textParts,
    })
  }

  return items
}

function translateTools(
  tools: Array<AnthropicTool> | undefined,
): Array<ResponsesTool> | undefined {
  if (!tools) return undefined
  return tools.map((tool) => ({
    type: "function",
    name: tool.name,
    description: tool.description,
    parameters: tool.input_schema,
  }))
}

function translateToolChoice(
  toolChoice: AnthropicMessagesPayload["tool_choice"],
): ResponsesPayload["tool_choice"] {
  if (!toolChoice) return undefined
  switch (toolChoice.type) {
    case "auto": {
      return "auto"
    }
    case "any": {
      return "required"
    }
    case "tool": {
      return toolChoice.name ?
          { type: "function", name: toolChoice.name }
        : undefined
    }
    case "none": {
      return "none"
    }
    default: {
      return undefined
    }
  }
}

// Response translation: OpenAI Responses -> Anthropic Messages

export function translateResponsesToAnthropic(
  response: ResponsesResult,
): AnthropicResponse {
  const textBlocks: Array<AnthropicTextBlock> = []
  const thinkingBlocks: Array<AnthropicThinkingBlock> = []
  const toolUseBlocks: Array<AnthropicToolUseBlock> = []

  for (const item of response.output) {
    if (item.type === "message") {
      for (const part of item.content) {
        if (part.type === "output_text") {
          textBlocks.push({ type: "text", text: part.text })
        }
      }
    } else if (item.type === "reasoning") {
      const text = (item.summary ?? [])
        .map((entry) => entry.text)
        .join("\n\n")
      if (text) thinkingBlocks.push({ type: "thinking", thinking: text })
    } else {
      toolUseBlocks.push({
        type: "tool_use",
        id: item.call_id,
        name: item.name,
        input: parseArguments(item.arguments),
      })
    }
  }

  const cached = response.usage?.input_tokens_details?.cached_tokens ?? 0

  return {
    id: response.id,
    type: "message",
    role: "assistant",
    model: response.model,
    content: [...thinkingBlocks, ...textBlocks, ...toolUseBlocks],
    stop_reason: toolUseBlocks.length > 0 ? "tool_use" : "end_turn",
    stop_sequence: null,
    usage: {
      input_tokens: (response.usage?.input_tokens ?? 0) - cached,
      output_tokens: response.usage?.output_tokens ?? 0,
      ...(cached > 0 && { cache_read_input_tokens: cached }),
    },
  }
}

function parseArguments(raw: string): Record<string, unknown> {
  try {
    return JSON.parse(raw) as Record<string, unknown>
  } catch {
    return {}
  }
}

// Streaming translation: Responses SSE events -> Anthropic SSE events

export interface ResponsesStreamState {
  messageStartSent: boolean
  id: string
  model: string
  nextBlockIndex: number
  sawToolCall: boolean
  outputTokens: number
  inputTokens: number
  cachedTokens: number
  // Keyed by the Responses output_index of the streamed item.
  blocks: {
    [outputIndex: number]: {
      anthropicIndex: number
      type: "text" | "thinking" | "tool_use"
    }
  }
}

export function createResponsesStreamState(): ResponsesStreamState {
  return {
    messageStartSent: false,
    id: "",
    model: "",
    nextBlockIndex: 0,
    sawToolCall: false,
    outputTokens: 0,
    inputTokens: 0,
    cachedTokens: 0,
    blocks: {},
  }
}

// eslint-disable-next-line max-lines-per-function, complexity
export function translateResponsesChunkToAnthropicEvents(
  event: ResponsesStreamEvent,
  state: ResponsesStreamState,
): Array<AnthropicStreamEventData> {
  const events: Array<AnthropicStreamEventData> = []

  const emitMessageStart = () => {
    if (state.messageStartSent) return
    events.push({
      type: "message_start",
      message: {
        id: state.id,
        type: "message",
        role: "assistant",
        content: [],
        model: state.model,
        stop_reason: null,
        stop_sequence: null,
        usage: { input_tokens: state.inputTokens, output_tokens: 0 },
      },
    })
    state.messageStartSent = true
  }

  switch (event.type) {
    case "response.created":
    case "response.in_progress": {
      if (event.response) {
        state.id = event.response.id
        state.model = event.response.model
        state.inputTokens = event.response.usage?.input_tokens ?? 0
      }
      break
    }

    case "response.output_item.added": {
      emitMessageStart()
      const index = event.output_index ?? 0
      const item = event.item
      if (item?.type === "function_call") {
        state.sawToolCall = true
        const anthropicIndex = state.nextBlockIndex++
        state.blocks[index] = { anthropicIndex, type: "tool_use" }
        events.push({
          type: "content_block_start",
          index: anthropicIndex,
          content_block: {
            type: "tool_use",
            id: item.call_id ?? item.id ?? "",
            name: item.name ?? "",
            input: {},
          },
        })
      }
      break
    }

    case "response.output_text.delta": {
      emitMessageStart()
      const block = ensureBlock(state, event.output_index ?? 0, "text", events)
      if (event.delta) {
        events.push({
          type: "content_block_delta",
          index: block.anthropicIndex,
          delta: { type: "text_delta", text: event.delta },
        })
      }
      break
    }

    case "response.reasoning_summary_text.delta":
    case "response.reasoning_text.delta": {
      emitMessageStart()
      const block = ensureBlock(
        state,
        event.output_index ?? 0,
        "thinking",
        events,
      )
      if (event.delta) {
        events.push({
          type: "content_block_delta",
          index: block.anthropicIndex,
          delta: { type: "thinking_delta", thinking: event.delta },
        })
      }
      break
    }

    case "response.function_call_arguments.delta": {
      const block = state.blocks[event.output_index ?? 0]
      if (block && event.delta) {
        events.push({
          type: "content_block_delta",
          index: block.anthropicIndex,
          delta: { type: "input_json_delta", partial_json: event.delta },
        })
      }
      break
    }

    case "response.output_item.done": {
      const block = state.blocks[event.output_index ?? 0]
      if (block) {
        events.push({ type: "content_block_stop", index: block.anthropicIndex })
        delete state.blocks[event.output_index ?? 0]
      }
      break
    }

    case "response.completed":
    case "response.incomplete": {
      for (const key of Object.keys(state.blocks)) {
        events.push({
          type: "content_block_stop",
          index: state.blocks[Number(key)].anthropicIndex,
        })
      }
      state.blocks = {}
      const usage = event.response?.usage
      const cached = usage?.input_tokens_details?.cached_tokens ?? 0
      events.push(
        {
          type: "message_delta",
          delta: {
            stop_reason:
              event.type === "response.incomplete" ? "max_tokens"
              : state.sawToolCall ? "tool_use"
              : "end_turn",
            stop_sequence: null,
          },
          usage: {
            input_tokens: (usage?.input_tokens ?? state.inputTokens) - cached,
            output_tokens: usage?.output_tokens ?? state.outputTokens,
            ...(cached > 0 && { cache_read_input_tokens: cached }),
          },
        },
        { type: "message_stop" },
      )
      break
    }

    default: {
      break
    }
  }

  return events
}

function ensureBlock(
  state: ResponsesStreamState,
  outputIndex: number,
  type: "text" | "thinking",
  events: Array<AnthropicStreamEventData>,
): { anthropicIndex: number } {
  const existing = state.blocks[outputIndex]
  if (existing) return existing
  const anthropicIndex = state.nextBlockIndex++
  state.blocks[outputIndex] = { anthropicIndex, type }
  events.push({
    type: "content_block_start",
    index: anthropicIndex,
    content_block:
      type === "text" ?
        { type: "text", text: "" }
      : { type: "thinking", thinking: "" },
  })
  return state.blocks[outputIndex]
}
