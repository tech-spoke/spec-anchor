# Authentication Specification

## Session Policy

source id: session-policy

ログイン後は SESSION_POLICY_ACTIVE を満たす active session を生成する。

## Logout Policy

source id: logout-policy

ログアウト時は SESSION_POLICY_TERMINATED を満たすよう active session を無効化する。

## Audit Policy

source id: audit-policy

AUDIT_POLICY_DIRTY_CHANGE は session lifecycle の監査記録を要求する。
