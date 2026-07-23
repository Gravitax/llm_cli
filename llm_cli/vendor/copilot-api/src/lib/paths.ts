import fs from "node:fs/promises"
import os from "node:os"
import path from "node:path"

import { state } from "./state"

const APP_DIR = path.join(os.homedir(), ".local", "share", "copilot-api")

const GITHUB_TOKEN_PATH = path.join(APP_DIR, "github_token")

export const PATHS = {
  APP_DIR,
  GITHUB_TOKEN_PATH,
}

// One token file per tenant: a github.com token and an enterprise token are not
// interchangeable, and silently reusing the wrong one only fails later, deep in
// the API. Switching domains therefore triggers a fresh login instead.
export function githubTokenPath(domain?: string): string {
  return domain ? `${GITHUB_TOKEN_PATH}.${domain}` : GITHUB_TOKEN_PATH
}

export async function ensurePaths(): Promise<void> {
  await fs.mkdir(PATHS.APP_DIR, { recursive: true })
  await ensureFile(githubTokenPath(state.enterpriseDomain))
}

async function ensureFile(filePath: string): Promise<void> {
  try {
    await fs.access(filePath, fs.constants.W_OK)
  } catch {
    await fs.writeFile(filePath, "")
    await fs.chmod(filePath, 0o600)
  }
}
