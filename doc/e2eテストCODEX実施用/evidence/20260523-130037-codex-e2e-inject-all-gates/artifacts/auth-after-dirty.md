# Authentication Specification

## Session Policy

source id: session-policy

SESSION_POLICY_ACTIVE は login 後の session 境界を定義する。

## Logout Policy

source id: logout-policy

SESSION_POLICY_TERMINATED は logout 後の session 境界を定義する。

## Dirty Gate Addition

source id: dirty-gate-addition

DIRTY_GATE_ADDITION は各 inject command が内部 gate で止まることを確認するための変更である。
