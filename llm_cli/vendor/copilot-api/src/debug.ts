#!/usr/bin/env node

import { defineCommand } from "citty"
import consola from "consola"
import fs from "node:fs/promises"
import os from "node:os"

import { applyEnterpriseDomain, enterpriseArgs } from "./lib/enterprise"
import { PATHS, githubTokenPath } from "./lib/paths"
import { state } from "./lib/state"

interface DebugInfo {
  version: string
  runtime: {
    name: string
    version: string
    platform: string
    arch: string
  }
  paths: {
    APP_DIR: string
    GITHUB_TOKEN_PATH: string
  }
  enterpriseDomain?: string
  tokenExists: boolean
}

interface RunDebugOptions {
  json: boolean
  enterpriseUrl?: string
}

async function getPackageVersion(): Promise<string> {
  try {
    const packageJsonPath = new URL("../package.json", import.meta.url).pathname
    // @ts-expect-error https://github.com/sindresorhus/eslint-plugin-unicorn/blob/v59.0.1/docs/rules/prefer-json-parse-buffer.md
    // JSON.parse() can actually parse buffers
    const packageJson = JSON.parse(await fs.readFile(packageJsonPath)) as {
      version: string
    }
    return packageJson.version
  } catch {
    return "unknown"
  }
}

function getRuntimeInfo() {
  const isBun = typeof Bun !== "undefined"

  return {
    name: isBun ? "bun" : "node",
    version: isBun ? Bun.version : process.version.slice(1),
    platform: os.platform(),
    arch: os.arch(),
  }
}

async function checkTokenExists(tokenPath: string): Promise<boolean> {
  try {
    const stats = await fs.stat(tokenPath)
    if (!stats.isFile()) return false

    const content = await fs.readFile(tokenPath, "utf8")
    return content.trim().length > 0
  } catch {
    return false
  }
}

async function getDebugInfo(): Promise<DebugInfo> {
  // Report the token of the tenant currently targeted, not the github.com one.
  const tokenPath = githubTokenPath(state.enterpriseDomain)
  const [version, tokenExists] = await Promise.all([
    getPackageVersion(),
    checkTokenExists(tokenPath),
  ])

  return {
    version,
    runtime: getRuntimeInfo(),
    paths: {
      APP_DIR: PATHS.APP_DIR,
      GITHUB_TOKEN_PATH: tokenPath,
    },
    enterpriseDomain: state.enterpriseDomain,
    tokenExists,
  }
}

function printDebugInfoPlain(info: DebugInfo): void {
  consola.info(`copilot-api debug

Version: ${info.version}
Runtime: ${info.runtime.name} ${info.runtime.version} (${info.runtime.platform} ${info.runtime.arch})

Paths:
- APP_DIR: ${info.paths.APP_DIR}
- GITHUB_TOKEN_PATH: ${info.paths.GITHUB_TOKEN_PATH}

Token exists: ${info.tokenExists ? "Yes" : "No"}`)
}

function printDebugInfoJson(info: DebugInfo): void {
  console.log(JSON.stringify(info, null, 2))
}

export async function runDebug(options: RunDebugOptions): Promise<void> {
  applyEnterpriseDomain(options.enterpriseUrl)
  const debugInfo = await getDebugInfo()

  if (options.json) {
    printDebugInfoJson(debugInfo)
  } else {
    printDebugInfoPlain(debugInfo)
  }
}

export const debug = defineCommand({
  meta: {
    name: "debug",
    description: "Print debug information about the application",
  },
  args: {
    json: {
      type: "boolean",
      default: false,
      description: "Output debug information as JSON",
    },
    ...enterpriseArgs,
  },
  run({ args }) {
    return runDebug({
      json: args.json,
      enterpriseUrl: args["enterprise-url"] as string | undefined,
    })
  },
})
