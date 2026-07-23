#!/usr/bin/env node

import { defineCommand } from "citty"
import consola from "consola"

import { applyEnterpriseDomain, enterpriseArgs } from "./lib/enterprise"
import { ensurePaths, githubTokenPath } from "./lib/paths"
import { state } from "./lib/state"
import { setupGitHubToken } from "./lib/token"

interface RunAuthOptions {
  verbose: boolean
  showToken: boolean
  enterpriseUrl?: string
}

export async function runAuth(options: RunAuthOptions): Promise<void> {
  if (options.verbose) {
    consola.level = 5
    consola.info("Verbose logging enabled")
  }

  state.showToken = options.showToken
  const enterpriseDomain = applyEnterpriseDomain(options.enterpriseUrl)
  if (enterpriseDomain) {
    consola.info(`Using GitHub Enterprise tenant ${enterpriseDomain}`)
  }

  await ensurePaths()
  await setupGitHubToken({ force: true })
  consola.success("GitHub token written to", githubTokenPath(enterpriseDomain))
}

export const auth = defineCommand({
  meta: {
    name: "auth",
    description: "Run GitHub auth flow without running the server",
  },
  args: {
    verbose: {
      alias: "v",
      type: "boolean",
      default: false,
      description: "Enable verbose logging",
    },
    "show-token": {
      type: "boolean",
      default: false,
      description: "Show GitHub token on auth",
    },
    ...enterpriseArgs,
  },
  run({ args }) {
    return runAuth({
      verbose: args.verbose,
      showToken: args["show-token"],
      enterpriseUrl: args["enterprise-url"] as string | undefined,
    })
  },
})
