// Spec 33: vitest runs in jsdom/node, where the `server-only` guard package
// is not resolvable. This empty stub is aliased to `server-only` in
// vitest.config.ts so server modules (e.g. `@/auth/server`) can be unit-tested.
export {};
