# Frontend

- Based on the Vercel AI chatbot template, stripped to the chat. Reuse `components/ai-elements` and `components/ui` before writing new components.
- `/api/*` is rewritten to the FastAPI backend (`next.config.ts`). There are no API routes in Next.
- Tool results render by `output.kind` in `app/page.tsx`; types mirror the backend in `lib/types.ts`. Change both together.
- Fonts are bundled locally (`geist` package); don't reintroduce `next/font/google`, it fails offline.
