# Debugging: Timer UI Not Updating After Start

The state is set correctly (`running: true`, etc.) in `PomodoroContext`, but the UI still shows "Start" and "1:00". This suggests the page component is not re-rendering with the new context value.

## Debugging Steps

### 1. Confirm the page receives the updated context

Add a `useEffect` in `frontend/src/app/(main)/page.tsx` that logs when `running` changes:

```tsx
useEffect(() => {
  console.log("[PomodoroPage] running changed:", running);
}, [running]);
```

- **If this logs** when you click Start → the page is re-rendering; the issue may be elsewhere (e.g. conditional rendering, wrong variable used).
- **If it never logs** → the page is not re-rendering when context changes; focus on the provider/consumer setup.

### 2. Check the component tree with React DevTools

1. Install [React DevTools](https://react.dev/learn/react-developer-tools).
2. Open DevTools → Components tab.
3. Find `PomodoroProvider` and `PomodoroPage`.
4. Confirm `PomodoroPage` is a descendant of `PomodoroProvider`.
5. After clicking Start, inspect `PomodoroProvider`’s state: does it show `running: true`?
6. Inspect `PomodoroPage`: what value does it receive for `running`?

### 3. Check for multiple providers

Search for `PomodoroProvider` in the codebase. If it appears in more than one place, the page might be reading from a different provider than the one you update.

### 4. Check layout conditional rendering

In `(main)/layout.tsx`, the layout returns a spinner when `loading || !isAuthenticated` and `PomodoroProvider` otherwise. If the auth state flips during the async start flow, the provider could unmount and remount, resetting state. Add a log:

```tsx
console.log("[MainLayout] rendering, loading:", loading, "isAuthenticated:", isAuthenticated);
```

### 5. Verify context value reference

In `PomodoroContext.tsx`, the context value is a new object each render. If it were memoized with stale dependencies, consumers might not update. Ensure the value object is not wrapped in `useMemo` with incorrect deps (or remove memoization for debugging).

### 6. Isolate the issue with a minimal test

Create a minimal component that only reads `running` and renders it:

```tsx
// Add to page.tsx temporarily
function DebugRunning() {
  const { running } = usePomodoro();
  return <div data-testid="debug-running">running: {String(running)}</div>;
}
```

Render `<DebugRunning />` next to the timer. If this shows `running: true` after Start but the button does not, the problem is in the button’s logic. If it also stays `false`, the problem is in context propagation.

### 7. Next.js App Router specifics

In the App Router, layouts and pages can be in different parts of the tree. Check:

- Is the page under a route group (e.g. `(main)`) that uses a different layout?
- Is the layout a Server Component while the page is a Client Component? (Both should be Client if they use `"use client"`.)

### 8. Check for Strict Mode double-mounting

In development, React Strict Mode mounts components twice. That can surface bugs but usually does not prevent updates. Temporarily disable Strict Mode in `next.config.ts` to see if behavior changes.
