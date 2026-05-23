# Authentication Service

## Login
Users sign in with email and password. Successful login creates a session.
Administrator accounts require multi-factor authentication.

## Session Expiry
Sessions expire after 24 hours of inactivity. Logout invalidates the active session immediately.

## API Access
Service accounts authenticate with API keys and bypass the interactive login screen.
