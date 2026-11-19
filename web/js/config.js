// VERITAS site configuration. A classic (non-module) script: pages load it before their modules.
// onlineApi = the public online engine (Hugging Face Docker Space, free cpu-basic). The lab picks its engine in this
// order: same-origin /api/health (booth laptop, or the Space itself) -> onlineApi -> showcase mode (the Evidence-locker
// exhibits open their real saved engine reports). Redeploy the engine with scripts/build_hf_space.py.
// No online engine is deployed for the fair (Hugging Face Docker Spaces need a paid plan), so onlineApi is empty and
// the hosted lab goes straight to showcase mode. To enable one later: deploy the Space, then set
//   onlineApi: "https://ahamedinmotion42-veritas.hf.space"
window.VERITAS_CONFIG = { onlineApi: "" };
