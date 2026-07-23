import type { ArgsDef } from "citty"

import { state } from "./state"

// GitHub Enterprise Cloud with data residency serves Copilot from three hosts
// derived from the tenant root: DOMAIN (OAuth device flow), api.DOMAIN (REST
// API and Copilot token exchange) and copilot-api.DOMAIN (completions). Tokens
// issued by a tenant are valid on that tenant only, so the domain must be known
// before the very first request.
const ENTERPRISE_URL_ENV = "COPILOT_ENTERPRISE_URL"

export const enterpriseArgs: ArgsDef = {
  "enterprise-url": {
    type: "string",
    description: `GitHub Enterprise tenant (e.g. mycompany.ghe.com). Can also be set via ${ENTERPRISE_URL_ENV}`,
  },
}

export function normalizeDomain(value: string | undefined): string | undefined {
  const domain = (value ?? "").replace(/^https?:\/\//, "").replace(/\/+$/, "")
  return domain || undefined
}

// Resolves the tenant from the CLI flag, falling back to the environment, and
// returns it so callers never have to read the global state back.
export function applyEnterpriseDomain(
  value: string | undefined,
): string | undefined {
  state.enterpriseDomain = normalizeDomain(
    value ?? process.env[ENTERPRISE_URL_ENV],
  )
  return state.enterpriseDomain
}
