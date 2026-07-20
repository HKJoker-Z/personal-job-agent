# Version 2.0.1 authentication and Remember Me

Passwords are Argon2 hashes in PostgreSQL. Login returns a generic invalid-credentials error and is protected by database-backed throttling. The browser receives a random opaque Session ID; PostgreSQL stores only its hash.

Production cookies are Secure, HttpOnly, SameSite=Lax, and path `/`. Normal login creates a browser-session cookie backed by a default 30-minute idle and 24-hour absolute server Session. `remember_me=true` adds a persistent cookie and a server Session whose configurable absolute lifetime is 1–30 days, default 30. There is no infinite Session.

Login rotates a previous Session. Logout revokes the current Session and deletes the cookie. Logout-all/admin revoke-all revokes every Session. Password change revokes old Sessions and returns a rotated Session. Inactive users fail authentication. Unsafe requests require a Session-bound CSRF token and trusted Origin.

The login fields use `autocomplete="username"` and `autocomplete="current-password"` so the browser/iOS password manager can offer credential saving. Application code never persists a password.

“Remember email” is separate. It stores only a trimmed, lowercased, length-bounded, validated email under `pja.v2.login.rememberedEmail`. Turning it off deletes the key immediately. The UI renders it through React values, not `innerHTML`. Session and CSRF tokens never enter LocalStorage, SessionStorage, IndexedDB, or ordinary JavaScript cookies.
