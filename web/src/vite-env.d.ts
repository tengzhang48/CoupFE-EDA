/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_COUPFE_BACKEND?: "mock" | "fastapi";
  readonly VITE_COUPFE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
