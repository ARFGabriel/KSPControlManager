import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Pratique en developpement : on peut aussi ouvrir le dashboard depuis
    // une autre machine du reseau local sans reconfigurer quoi que ce soit.
    host: true,
  },
});
