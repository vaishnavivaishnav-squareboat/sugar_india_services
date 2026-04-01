import { defineConfig, loadEnv, transformWithEsbuild } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, "");

  return {
    plugins: [
      // Treat .js files inside src/ as JSX before Vite's import-analysis runs
      {
        name: "treat-js-files-as-jsx",
        enforce: "pre",
        async transform(code, id) {
          if (!id.match(/\/src\/.*\.js$/)) return null;
          return transformWithEsbuild(code, id, { loader: "jsx" });
        },
      },
      react(),
    ],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "src"),
      },
    },
    server: {
      port: 3000,
      open: false,
    },
    build: {
      outDir: "build",
      sourcemap: false,
    },
    optimizeDeps: {
      esbuildOptions: {
        loader: {
          ".js": "jsx",
        },
      },
    },
    // Expose env vars that start with VITE_ to the client
    envPrefix: "VITE_",
  };
});
