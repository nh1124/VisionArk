import type { RiskLevel } from "./types"

export const APPROVAL_POLICY = {
  MANUAL       : "manual",
  AUTO_IF_RULE : "auto_if_rule",
} as const

export type ApprovalPolicy = typeof APPROVAL_POLICY[keyof typeof APPROVAL_POLICY]

/** Risk levels that always require manual approval */
export const ALWAYS_MANUAL_RISK: RiskLevel[] = ["high", "critical"]

/** Default approval expiry in seconds */
export const DEFAULT_APPROVAL_EXPIRY_SECONDS = 300

/** Jobs with these types auto-approve when risk is "low" */
export const AUTO_APPROVE_LOW_RISK_TYPES: string[] = [
  "local.file",
  "local.dev",
]
