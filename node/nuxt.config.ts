export default defineNuxtConfig({
  devtools: { enabled: false },
  ssr: false,
  srcDir: "src",
  modules: ["@nuxt/ui", "@pinia/nuxt"],
  colorMode: { preference: "dark" },
  runtimeConfig: {
    public: { apiBase: "" },
  },
  ui: { icons: ["ic", "carbon"] },
  app: {
    head: { title: "Chennai TMS" }
  },
})
